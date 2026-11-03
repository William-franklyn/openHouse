from conftest import register_socket, ws_dispatch

from app.messages import REACTION_EMOJI


async def create_room(client, name="Test Room", owner_name="Owner"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def join(client, code, name):
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": name, "over_18": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def general_channel_id(app, room_id):
    from sqlalchemy import select

    from app.models import Channel

    async with app.state.db.session() as session:
        result = await session.execute(
            select(Channel).where(Channel.room_id == room_id, Channel.name == "general")
        )
        return result.scalar_one().id


async def _send_message(app, room_id, member_id, channel_id, text="hi"):
    await ws_dispatch(app, room_id, member_id, "send_message", {"channel_id": channel_id, "text": text})


def _last_reaction_event(ws):
    for event in reversed(ws.sent):
        if event.get("type") == "reaction":
            return event
    return None


async def test_toggling_a_reaction_adds_then_removes_it(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    channel_id = await general_channel_id(app, room_id)
    ws = await register_socket(app, room_id, owner_id)

    await _send_message(app, room_id, owner_id, channel_id)
    message_id = next(e for e in ws.sent if e.get("type") == "message")["id"]

    await ws_dispatch(app, room_id, owner_id, "toggle_reaction", {"message_id": message_id, "emoji": "👍"})
    added_event = _last_reaction_event(ws)
    assert added_event["added"] is True
    assert added_event["emoji"] == "👍"
    assert added_event["member_id"] == owner_id

    await ws_dispatch(app, room_id, owner_id, "toggle_reaction", {"message_id": message_id, "emoji": "👍"})
    removed_event = _last_reaction_event(ws)
    assert removed_event["added"] is False


async def test_two_members_can_react_with_the_same_emoji_independently(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    p2_id = p2["member_id"]
    channel_id = await general_channel_id(app, room_id)
    owner_ws = await register_socket(app, room_id, owner_id)
    p2_ws = await register_socket(app, room_id, p2_id)

    await _send_message(app, room_id, owner_id, channel_id)
    message_id = next(e for e in owner_ws.sent if e.get("type") == "message")["id"]

    await ws_dispatch(app, room_id, owner_id, "toggle_reaction", {"message_id": message_id, "emoji": "🔥"})
    await ws_dispatch(app, room_id, p2_id, "toggle_reaction", {"message_id": message_id, "emoji": "🔥"})

    # Both sockets should have seen both reaction broadcasts (room-wide).
    for ws in (owner_ws, p2_ws):
        fire_events = [e for e in ws.sent if e.get("type") == "reaction" and e.get("emoji") == "🔥"]
        assert {e["member_id"] for e in fire_events} == {owner_id, p2_id}
        assert all(e["added"] is True for e in fire_events)


async def test_a_member_can_react_with_multiple_different_emoji(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    channel_id = await general_channel_id(app, room_id)
    owner_token = data["session_token"]
    ws = await register_socket(app, room_id, owner_id)

    await _send_message(app, room_id, owner_id, channel_id)
    message_id = next(e for e in ws.sent if e.get("type") == "message")["id"]

    await ws_dispatch(app, room_id, owner_id, "toggle_reaction", {"message_id": message_id, "emoji": "👍"})
    await ws_dispatch(app, room_id, owner_id, "toggle_reaction", {"message_id": message_id, "emoji": "😂"})

    resp = await client.get(
        f"/api/rooms/{room_id}/channels/{channel_id}/messages", headers=auth(owner_token)
    )
    reactions = resp.json()["messages"][0]["reactions"]
    by_emoji = {r["emoji"]: r["member_ids"] for r in reactions}
    assert by_emoji == {"👍": [owner_id], "😂": [owner_id]}


async def test_reacting_with_an_unsupported_emoji_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    channel_id = await general_channel_id(app, room_id)
    ws = await register_socket(app, room_id, owner_id)
    await _send_message(app, room_id, owner_id, channel_id)
    message_id = next(e for e in ws.sent if e.get("type") == "message")["id"]

    assert "🐍" not in REACTION_EMOJI
    try:
        await ws_dispatch(app, room_id, owner_id, "toggle_reaction", {"message_id": message_id, "emoji": "🐍"})
        assert False, "expected bad_request"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_reacting_to_an_unknown_message_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    await register_socket(app, room_id, owner_id)

    try:
        await ws_dispatch(
            app, room_id, owner_id, "toggle_reaction", {"message_id": "not-a-real-id", "emoji": "👍"}
        )
        assert False, "expected bad_request"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_history_includes_reaction_summaries(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    channel_id = await general_channel_id(app, room_id)
    owner_token = data["session_token"]
    ws = await register_socket(app, room_id, owner_id)
    await _send_message(app, room_id, owner_id, channel_id)
    message_id = next(e for e in ws.sent if e.get("type") == "message")["id"]

    resp = await client.get(
        f"/api/rooms/{room_id}/channels/{channel_id}/messages", headers=auth(owner_token)
    )
    assert resp.json()["messages"][0]["reactions"] == []

    await ws_dispatch(app, room_id, owner_id, "toggle_reaction", {"message_id": message_id, "emoji": "🎉"})
    resp = await client.get(
        f"/api/rooms/{room_id}/channels/{channel_id}/messages", headers=auth(owner_token)
    )
    assert resp.json()["messages"][0]["reactions"] == [{"emoji": "🎉", "member_ids": [owner_id]}]
