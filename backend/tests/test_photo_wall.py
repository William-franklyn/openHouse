from conftest import register_socket, ws_dispatch

from sqlalchemy import select

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
        result = await session.execute(
            select(Channel).where(Channel.room_id == room_id, Channel.name == "general")
        )
        return result.scalar_one().id


async def upload(client, room_id, token, filename, content, content_type, channel_id=None):
    form = {"channel_id": channel_id} if channel_id else {}
    resp = await client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": (filename, content, content_type)},
        data=form,
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["file_id"]


# Photo Wall: aggregates every image shared as a chat message, room-wide ----

async def test_photo_shared_as_message_appears_in_room_photos(client, app):
    data = await create_room(client)
    room_id, owner_token = data["room"]["id"], data["session_token"]
    channel_id = await general_channel_id(app, room_id)

    file_id = await upload(client, room_id, owner_token, "party.jpg", b"fake jpeg bytes", "image/jpeg", channel_id)

    resp = await client.get(f"/api/rooms/{room_id}/photos", headers=auth(owner_token))
    assert resp.status_code == 200
    photos = resp.json()["photos"]
    assert len(photos) == 1
    assert photos[0]["file_id"] == file_id
    assert photos[0]["filename"] == "party.jpg"
    assert photos[0]["member_name"] == "Owner"


async def test_non_image_file_does_not_appear_on_wall(client, app):
    data = await create_room(client)
    room_id, owner_token = data["room"]["id"], data["session_token"]
    channel_id = await general_channel_id(app, room_id)

    await upload(client, room_id, owner_token, "notes.pdf", b"fake pdf bytes", "application/pdf", channel_id)

    resp = await client.get(f"/api/rooms/{room_id}/photos", headers=auth(owner_token))
    assert resp.json()["photos"] == []


async def test_image_uploaded_without_channel_id_does_not_appear_on_wall(client, app):
    # Mirrors how Room DJ uploads a music file - no channel_id, never a
    # chat message, so it should never surface as a "shared photo" either.
    data = await create_room(client)
    room_id, owner_token = data["room"]["id"], data["session_token"]

    await upload(client, room_id, owner_token, "cover-art.png", b"fake png bytes", "image/png", channel_id=None)

    resp = await client.get(f"/api/rooms/{room_id}/photos", headers=auth(owner_token))
    assert resp.json()["photos"] == []


async def test_photos_aggregate_across_channels_newest_last(client, app):
    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    general_id = await general_channel_id(app, room_id)

    await register_socket(app, room_id, owner_id)
    await ws_dispatch(app, room_id, owner_id, "create_channel", {"name": "random"})

    async with app.state.db.session() as session:
        result = await session.execute(
            select(Channel).where(Channel.room_id == room_id, Channel.name == "random")
        )
        random_id = result.scalar_one().id

    first_id = await upload(client, room_id, owner_token, "first.jpg", b"one", "image/jpeg", general_id)
    second_id = await upload(client, room_id, owner_token, "second.jpg", b"two", "image/jpeg", random_id)

    resp = await client.get(f"/api/rooms/{room_id}/photos", headers=auth(owner_token))
    photos = resp.json()["photos"]
    assert [p["file_id"] for p in photos] == [first_id, second_id]


async def test_deleted_message_removes_photo_from_wall(client, app):
    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    channel_id = await general_channel_id(app, room_id)
    await register_socket(app, room_id, owner_id)

    await upload(client, room_id, owner_token, "oops.jpg", b"fake", "image/jpeg", channel_id)

    resp = await client.get(f"/api/rooms/{room_id}/photos", headers=auth(owner_token))
    message_id = None
    async with app.state.db.session() as session:
        from app.models import Message

        result = await session.execute(select(Message).where(Message.channel_id == channel_id))
        message_id = result.scalars().one().id

    await ws_dispatch(app, room_id, owner_id, "delete_message", {"message_id": message_id})

    resp = await client.get(f"/api/rooms/{room_id}/photos", headers=auth(owner_token))
    assert resp.json()["photos"] == []


async def test_photos_are_room_scoped(client, app):
    data_a = await create_room(client, name="Room A")
    data_b = await create_room(client, name="Room B")
    channel_a = await general_channel_id(app, data_a["room"]["id"])

    await upload(client, data_a["room"]["id"], data_a["session_token"], "a.jpg", b"a", "image/jpeg", channel_a)

    resp = await client.get(f"/api/rooms/{data_b['room']['id']}/photos", headers=auth(data_b["session_token"]))
    assert resp.json()["photos"] == []


async def test_image_upload_broadcasts_photo_shared(client, app):
    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    channel_id = await general_channel_id(app, room_id)
    other = await join(client, data["room"]["code"], "Listener")
    other_ws = await register_socket(app, room_id, other["member_id"])

    file_id = await upload(client, room_id, owner_token, "snap.jpg", b"fake", "image/jpeg", channel_id)

    events = [e for e in other_ws.sent if e.get("type") == "photo_shared"]
    assert len(events) == 1
    assert events[0]["file_id"] == file_id
    assert events[0]["member_name"] == "Owner"


async def test_non_image_upload_does_not_broadcast_photo_shared(client, app):
    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    channel_id = await general_channel_id(app, room_id)
    owner_ws = await register_socket(app, room_id, owner_id)

    await upload(client, room_id, owner_token, "doc.txt", b"fake", "text/plain", channel_id)

    assert [e for e in owner_ws.sent if e.get("type") == "photo_shared"] == []
