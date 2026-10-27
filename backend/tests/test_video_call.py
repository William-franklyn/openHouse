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


# Starting a call: targeted invites, not a room-wide broadcast ----------------

async def test_start_call_invites_only_named_members_not_the_whole_room(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    invitee = await join(client, data["room"]["code"], "Invitee")
    bystander = await join(client, data["room"]["code"], "Bystander")

    owner_ws = await register_socket(app, room_id, owner_id)
    invitee_ws = await register_socket(app, room_id, invitee["member_id"])
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])

    await ws_dispatch(app, room_id, owner_id, "start_call", {"invitee_ids": [invitee["member_id"]]})

    # The host learns their own new call_id through the same event shape
    # an invitee gets - no separate "here's your call_id" response needed.
    host_invites = [e for e in owner_ws.sent if e.get("type") == "call_invite"]
    assert len(host_invites) == 1
    call_id = host_invites[0]["call_id"]
    assert host_invites[0]["host_member_id"] == owner_id
    assert host_invites[0]["host_name"] == "Owner"

    invitee_invites = [e for e in invitee_ws.sent if e.get("type") == "call_invite"]
    assert len(invitee_invites) == 1
    assert invitee_invites[0]["call_id"] == call_id

    # Someone who wasn't invited gets nothing at all - not even presence,
    # since they were never told the call_id exists.
    assert [e for e in bystander_ws.sent if e.get("type") == "call_invite"] == []


async def test_start_call_auto_joins_the_host(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    invitee = await join(client, data["room"]["code"], "Invitee")
    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, invitee["member_id"])

    await ws_dispatch(app, room_id, owner_id, "start_call", {"invitee_ids": [invitee["member_id"]]})

    calls = await realtime.active_calls_for_member(app.state.redis, owner_id)
    assert len(calls) == 1
    assert calls[0]["member_ids"] == [owner_id]


async def test_start_call_requires_at_least_one_invitee(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    await register_socket(app, room_id, owner_id)

    for bad_payload in ({"invitee_ids": []}, {}):
        try:
            await ws_dispatch(app, room_id, owner_id, "start_call", bad_payload)
            assert False, "empty/missing invitee_ids should be rejected"
        except Exception as exc:
            assert getattr(exc, "code", None) == "bad_request"


async def test_start_call_rejects_invitee_outside_the_room(client, app):
    data_a = await create_room(client, name="Room A")
    data_b = await create_room(client, name="Room B")
    room_a_id, owner_a_id = data_a["room"]["id"], data_a["member"]["member_id"]
    outsider_id = data_b["member"]["member_id"]
    await register_socket(app, room_a_id, owner_a_id)

    try:
        await ws_dispatch(app, room_a_id, owner_a_id, "start_call", {"invitee_ids": [outsider_id]})
        assert False, "inviting someone from a different room should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


# Joining/leaving a specific call_id -------------------------------------------

async def test_join_call_adds_presence_and_broadcasts_to_whole_room(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    other = await join(client, data["room"]["code"], "Listener")

    owner_ws = await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    await ws_dispatch(app, room_id, owner_id, "start_call", {"invitee_ids": [other["member_id"]]})
    call_id = [e for e in owner_ws.sent if e.get("type") == "call_invite"][0]["call_id"]

    await ws_dispatch(app, room_id, other["member_id"], "join_call", {"call_id": call_id})

    # Two broadcasts land in total: one from start_call auto-joining the
    # host, one from the invitee's own join_call - check the latest state.
    for ws in (owner_ws, other_ws):
        events = [e for e in ws.sent if e.get("type") == "call_presence"]
        assert events[-1]["call_id"] == call_id
        assert sorted(events[-1]["member_ids"]) == sorted([owner_id, other["member_id"]])


async def test_leave_call_removes_presence(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    invitee = await join(client, data["room"]["code"], "Invitee")
    ws = await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, invitee["member_id"])

    await ws_dispatch(app, room_id, owner_id, "start_call", {"invitee_ids": [invitee["member_id"]]})
    call_id = [e for e in ws.sent if e.get("type") == "call_invite"][0]["call_id"]
    assert await realtime.call_presence_snapshot(app.state.redis, call_id) == [owner_id]

    await ws_dispatch(app, room_id, owner_id, "leave_call", {"call_id": call_id})
    assert await realtime.call_presence_snapshot(app.state.redis, call_id) == []

    left = [e for e in ws.sent if e.get("type") == "call_presence" and e["member_ids"] == []]
    assert len(left) == 1


async def test_two_concurrent_calls_in_the_same_room_are_independent(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    a = await join(client, data["room"]["code"], "A")
    b = await join(client, data["room"]["code"], "B")
    owner_ws = await register_socket(app, room_id, owner_id)
    a_ws = await register_socket(app, room_id, a["member_id"])
    await register_socket(app, room_id, b["member_id"])

    await ws_dispatch(app, room_id, owner_id, "start_call", {"invitee_ids": [a["member_id"]]})
    call_1 = [e for e in owner_ws.sent if e.get("type") == "call_invite"][0]["call_id"]

    # A is the host of call_2 (not owner).
    await ws_dispatch(app, room_id, a["member_id"], "start_call", {"invitee_ids": [b["member_id"]]})
    call_2 = [e for e in a_ws.sent if e.get("type") == "call_invite"][-1]["call_id"]

    assert call_1 != call_2
    assert await realtime.call_presence_snapshot(app.state.redis, call_1) == [owner_id]
    assert await realtime.call_presence_snapshot(app.state.redis, call_2) == [a["member_id"]]


async def test_join_leave_call_require_call_id(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    await register_socket(app, room_id, owner_id)

    for msg_type in ("join_call", "leave_call"):
        try:
            await ws_dispatch(app, room_id, owner_id, msg_type, {})
            assert False, f"{msg_type} without call_id should be rejected"
        except Exception as exc:
            assert getattr(exc, "code", None) == "bad_request"


# Disconnect cleanup: every call the member was part of, not just one -------

async def test_disconnect_cleanup_removes_from_every_active_call(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    a = await join(client, data["room"]["code"], "A")
    b = await join(client, data["room"]["code"], "B")
    owner_ws = await register_socket(app, room_id, owner_id)
    a_ws = await register_socket(app, room_id, a["member_id"])
    await register_socket(app, room_id, b["member_id"])

    # Owner is a participant in two different calls at once.
    await ws_dispatch(app, room_id, owner_id, "start_call", {"invitee_ids": [a["member_id"]]})
    call_1 = [e for e in owner_ws.sent if e.get("type") == "call_invite"][0]["call_id"]
    await ws_dispatch(app, room_id, a["member_id"], "join_call", {"call_id": call_1})

    await ws_dispatch(app, room_id, owner_id, "start_call", {"invitee_ids": [b["member_id"]]})
    call_2 = [e for e in owner_ws.sent if e.get("type") == "call_invite"][-1]["call_id"]

    await _wait_for(lambda: len(a_ws.sent) >= 1)

    await realtime.cleanup_call_presence_on_disconnect(app.state.redis, app.state.hub, room_id, owner_id)

    assert await realtime.call_presence_snapshot(app.state.redis, call_1) == [a["member_id"]]
    assert await realtime.call_presence_snapshot(app.state.redis, call_2) == []
    assert await realtime.active_calls_for_member(app.state.redis, owner_id) == []


async def test_disconnect_cleanup_is_a_noop_when_nobody_was_in_a_call(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    ws = await register_socket(app, room_id, owner_id)

    await realtime.cleanup_call_presence_on_disconnect(app.state.redis, app.state.hub, room_id, owner_id)

    assert [e for e in ws.sent if e.get("type") == "call_presence"] == []


# WebRTC signaling relay: strictly peer-to-peer, never broadcast ---------------
# (Unchanged by the call_id redesign - already targeted by to_member_id.)

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


# video_room_token exposure (unrelated to Jitsi removal - harmless unused
# column kept as-is rather than forcing another production migration) --------

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
