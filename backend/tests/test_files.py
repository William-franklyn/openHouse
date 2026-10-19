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


# 9. Files: size/type limits, member-only signed URLs, cleanup on delete -----

async def test_upload_under_limit_then_download(client):
    data = await create_room(client)
    room_id, token = data["room"]["id"], data["session_token"]

    content = b"hello world, this is a test file"
    resp = await client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": ("note.txt", content, "text/plain")},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    file_id = resp.json()["file_id"]

    dl = await client.get(f"/api/files/{file_id}", headers=auth(token))
    assert dl.status_code == 200
    body = dl.json()
    assert body["filename"] == "note.txt"
    assert body["size"] == len(content)
    assert "url" in body and body["url"]


async def test_upload_over_size_limit_rejected(client, app):
    data = await create_room(client)
    room_id, token = data["room"]["id"], data["session_token"]
    app.state.settings.MAX_FILE_BYTES = 10  # shrink the limit for this test

    resp = await client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": ("big.txt", b"x" * 1000, "text/plain")},
        headers=auth(token),
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "file_too_large"


async def test_upload_disallowed_type_rejected(client):
    data = await create_room(client)
    room_id, token = data["room"]["id"], data["session_token"]

    resp = await client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": ("script.exe", b"MZ\x00\x00", "application/octet-stream")},
        headers=auth(token),
    )
    assert resp.status_code == 415
    assert resp.json()["code"] == "file_type"


async def test_download_requires_membership(client):
    data = await create_room(client)
    room_id, token = data["room"]["id"], data["session_token"]

    resp = await client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": ("note.txt", b"secret stuff", "text/plain")},
        headers=auth(token),
    )
    file_id = resp.json()["file_id"]

    denied = await client.get(f"/api/files/{file_id}", headers=auth("not-a-real-token"))
    assert denied.status_code == 401
    assert denied.json()["code"] == "bad_token"

    other_room = await create_room(client, name="Other Room")
    other_token = other_room["session_token"]
    cross_room = await client.get(f"/api/files/{file_id}", headers=auth(other_token))
    assert cross_room.status_code == 400


async def test_files_deleted_when_room_deleted(client, app):
    data = await create_room(client)
    room_id, token = data["room"]["id"], data["session_token"]

    resp = await client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": ("note.txt", b"bye bye", "text/plain")},
        headers=auth(token),
    )
    file_id = resp.json()["file_id"]
    async with app.state.db.session() as session:
        from app.models import FileAsset

        asset = await session.get(FileAsset, file_id)
        storage_key = asset.storage_key
    assert await app.state.storage.get_bytes(storage_key) == b"bye bye"

    await client.delete(f"/api/rooms/{room_id}", headers=auth(token))

    try:
        await app.state.storage.get_bytes(storage_key)
        assert False, "expected the object to be gone from storage"
    except Exception:
        pass
