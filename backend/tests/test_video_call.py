import asyncio

from conftest import register_socket, ws_dispatch

from app import realtime


async def _wait_for(predicate, timeout=1.0, interval=0.02):
    """Two room-wide broadcasts issued back-to-back can race fakeredis's
    pubsub delivery (see test_realtime.py's cross-instance test for the
    same pattern) - poll instead of asserting on the very next tick."""
    elapsed = 0.0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return predicate()


async def create_room(client, name="Test Room", owner_name="Owner"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def join(client, code, name):
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": name, "over_18": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


# Video call presence (shared by both the WebRTC and Jitsi UIs) ---------------

async def test_join_call_adds_presence_and_broadcasts_to_whole_room(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    other = await join(client, data["room"]["code"], "Listener")

    owner_ws = await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    await ws_dispatch(app, room_id, owner_id, "join_call", {"mode": "webrtc"})

    for ws in (owner_ws, other_ws):
        events = [e for e in ws.sent if e.get("type") == "call_presence"]
        assert len(events) == 1
        assert events[0]["mode"] == "webrtc"
        assert events[0]["member_ids"] == [owner_id]


async def test_leave_call_removes_presence(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    ws = await register_socket(app, room_id, owner_id)

    await ws_dispatch(app, room_id, owner_id, "join_call", {"mode": "jitsi"})
    assert await realtime.call_presence_snapshot(app.state.redis, room_id, "jitsi") == [owner_id]

    await ws_dispatch(app, room_id, owner_id, "leave_call", {"mode": "jitsi"})
    assert await realtime.call_presence_snapshot(app.state.redis, room_id, "jitsi") == []

    stopped = [e for e in ws.sent if e.get("type") == "call_presence" and e["member_ids"] == []]
    assert len(stopped) == 1


async def test_webrtc_and_jitsi_presence_are_independent(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    other = await join(client, data["room"]["code"], "Listener")
    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, other["member_id"])

    await ws_dispatch(app, room_id, owner_id, "join_call", {"mode": "webrtc"})
    await ws_dispatch(app, room_id, other["member_id"], "join_call", {"mode": "jitsi"})

    assert await realtime.call_presence_snapshot(app.state.redis, room_id, "webrtc") == [owner_id]
    assert await realtime.call_presence_snapshot(app.state.redis, room_id, "jitsi") == [other["member_id"]]


async def test_join_call_rejects_unknown_mode(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    await register_socket(app, room_id, owner_id)

    try:
        await ws_dispatch(app, room_id, owner_id, "join_call", {"mode": "zoom"})
        assert False, "unknown call mode should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_disconnect_cleanup_removes_stale_presence_and_broadcasts(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    other = await join(client, data["room"]["code"], "Listener")
    owner_ws = await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    await ws_dispatch(app, room_id, owner_id, "join_call", {"mode": "webrtc"})
    await _wait_for(lambda: len(other_ws.sent) == 1)

    # Simulates main.py's disconnect `finally` block for a dropped
    # connection that never got to send leave_call.
    await realtime.cleanup_call_presence_on_disconnect(app.state.redis, app.state.hub, room_id, owner_id)

    assert await realtime.call_presence_snapshot(app.state.redis, room_id, "webrtc") == []

    def cleared():
        return [e for e in other_ws.sent if e.get("type") == "call_presence" and e["member_ids"] == []]

    await _wait_for(lambda: len(cleared()) == 1)
    assert len(cleared()) == 1


async def test_disconnect_cleanup_is_a_noop_when_nobody_was_in_a_call(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    ws = await register_socket(app, room_id, owner_id)

    await realtime.cleanup_call_presence_on_disconnect(app.state.redis, app.state.hub, room_id, owner_id)

    assert [e for e in ws.sent if e.get("type") == "call_presence"] == []


# WebRTC signaling relay: strictly peer-to-peer, never broadcast ---------------

async def test_call_offer_goes_only_to_the_target_member(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    other = await join(client, data["room"]["code"], "Listener")
    owner_ws = await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    await ws_dispatch(
        app, room_id, owner_id, "call_offer",
        {"to_member_id": other["member_id"], "sdp": {"type": "offer", "sdp": "v=0..."}},
    )

    received = [e for e in other_ws.sent if e.get("type") == "call_offer"]
    assert len(received) == 1
    assert received[0]["from_member_id"] == owner_id
    assert received[0]["sdp"] == {"type": "offer", "sdp": "v=0..."}

    # The sender's own socket must not get an echo of their own offer.
    assert [e for e in owner_ws.sent if e.get("type") == "call_offer"] == []


async def test_call_answer_and_ice_candidate_relay_to_target_only(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    other = await join(client, data["room"]["code"], "Listener")
    await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    await ws_dispatch(
        app, room_id, other["member_id"], "call_answer",
        {"to_member_id": owner_id, "sdp": {"type": "answer", "sdp": "v=0..."}},
    )
    await ws_dispatch(
        app, room_id, other["member_id"], "call_ice_candidate",
        {"to_member_id": owner_id, "candidate": {"candidate": "candidate:1 ...", "sdpMid": "0"}},
    )

    # Neither relay should loop back to the sender's own socket.
    assert [e for e in other_ws.sent if e.get("type") in ("call_answer", "ice_candidate")] == []


async def test_call_offer_requires_target_and_payload(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    await register_socket(app, room_id, owner_id)

    try:
        await ws_dispatch(app, room_id, owner_id, "call_offer", {"sdp": {"type": "offer"}})
        assert False, "missing to_member_id should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"

    try:
        await ws_dispatch(app, room_id, owner_id, "call_offer", {"to_member_id": "someone"})
        assert False, "missing sdp should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


# video_room_token exposure ----------------------------------------------------

async def test_video_room_token_present_and_unique_per_room(client):
    data_a = await create_room(client, name="Room A")
    data_b = await create_room(client, name="Room B")

    resp_a = await client.get(f"/api/rooms/{data_a['room']['id']}", headers=auth(data_a["session_token"]))
    resp_b = await client.get(f"/api/rooms/{data_b['room']['id']}", headers=auth(data_b["session_token"]))
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    token_a = resp_a.json()["video_room_token"]
    token_b = resp_b.json()["video_room_token"]
    assert token_a and token_b
    assert token_a != token_b

    # Not present on the unauthenticated preview route - that one's public,
    # and this token is a shared secret for joining the room's video call.
    preview = await client.get(f"/api/rooms/by-code/{data_a['room']['code']}")
    assert "video_room_token" not in preview.json()
