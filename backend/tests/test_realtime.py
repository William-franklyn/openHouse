import asyncio

from conftest import FakeWebSocket, make_redis_client, register_socket, ws_dispatch

from app.main import create_app
from app.models import Channel


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


async def general_channel_id(app, room_id):
    async with app.state.db.session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Channel).where(Channel.room_id == room_id, Channel.name == "general")
        )
        return result.scalar_one().id


# 7. Rate limits ---------------------------------------------------------------

async def test_message_rate_limit_triggers(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    channel_id = await general_channel_id(app, room_id)

    await register_socket(app, room_id, owner_id)

    settings = app.state.settings
    for _ in range(settings.MESSAGE_RATE_LIMIT):
        await ws_dispatch(app, room_id, owner_id, "send_message", {"channel_id": channel_id, "text": "hi"})

    try:
        await ws_dispatch(app, room_id, owner_id, "send_message", {"channel_id": channel_id, "text": "hi"})
        assert False, "expected rate_limited"
    except Exception as exc:
        assert getattr(exc, "code", None) == "rate_limited"


async def test_upload_rate_limit_triggers(client, app):
    data = await create_room(client)
    room_id, token = data["room"]["id"], data["session_token"]
    settings = app.state.settings

    small_file = ("note.txt", b"hello", "text/plain")
    for _ in range(settings.UPLOAD_RATE_LIMIT):
        resp = await client.post(
            f"/api/rooms/{room_id}/files",
            files={"file": small_file},
            headers=auth(token),
        )
        assert resp.status_code == 200, resp.text

    limited = await client.post(
        f"/api/rooms/{room_id}/files", files={"file": small_file}, headers=auth(token)
    )
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"


async def test_join_rate_limit_triggers(client, app):
    data = await create_room(client)
    code = data["room"]["code"]
    settings = app.state.settings

    for _ in range(settings.JOIN_RATE_LIMIT):
        resp = await client.post(f"/api/rooms/{code}/join", json={"name": None, "over_18": True})
        assert resp.status_code == 200

    limited = await client.post(f"/api/rooms/{code}/join", json={"name": None, "over_18": True})
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"


# 8. Seq ordering + reconnect with last_seq -----------------------------------

async def test_seq_increases_with_no_gaps_under_concurrent_sends(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    channel_id = await general_channel_id(app, room_id)
    await register_socket(app, room_id, owner_id)

    # Stay within the message rate limit (tested separately) - this test is
    # only about seq ordering under concurrency, not about rate limiting.
    n = app.state.settings.MESSAGE_RATE_LIMIT
    await asyncio.gather(
        *[
            ws_dispatch(app, room_id, owner_id, "send_message", {"channel_id": channel_id, "text": f"m{i}"})
            for i in range(n)
        ]
    )

    async with app.state.db.session() as session:
        from app import messages as messages_mod

        rows = await messages_mod.history(session, channel_id, before_seq=None, limit=100)
    seqs = sorted(m.seq for m in rows)
    assert seqs == list(range(1, n + 1))


async def test_reconnect_with_last_seq_gets_exactly_missed_messages(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    channel_id = await general_channel_id(app, room_id)
    await register_socket(app, room_id, owner_id)

    for i in range(3):
        await ws_dispatch(app, room_id, owner_id, "send_message", {"channel_id": channel_id, "text": f"m{i}"})

    async with app.state.db.session() as session:
        from app import messages as messages_mod

        missed = await messages_mod.messages_after(session, channel_id, after_seq=1)
    assert [m.text for m in missed] == ["m1", "m2"]
    assert [m.seq for m in missed] == [2, 3]

    async with app.state.db.session() as session:
        from app import messages as messages_mod

        none_missed = await messages_mod.messages_after(session, channel_id, after_seq=3)
    assert none_missed == []


# 11. Two server instances share a message via Redis --------------------------

async def test_message_reaches_client_on_a_different_instance_via_redis(client, app, fake_redis_server):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    channel_id = await general_channel_id(app, room_id)

    other_redis = make_redis_client(fake_redis_server)
    other_app = create_app(settings=app.state.settings, redis_client=other_redis, storage=app.state.storage)
    await other_app.state.hub.start()
    try:
        other_ws = FakeWebSocket()
        other_app.state.hub.register(room_id, owner_id, other_ws)

        await ws_dispatch(app, room_id, owner_id, "send_message", {"channel_id": channel_id, "text": "cross-instance"})

        for _ in range(20):
            if any(e.get("type") == "message" for e in other_ws.sent):
                break
            await asyncio.sleep(0.05)

        texts = [e["text"] for e in other_ws.sent if e.get("type") == "message"]
        assert "cross-instance" in texts
    finally:
        await other_app.state.hub.stop()
