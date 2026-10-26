import json

from conftest import register_socket, ws_dispatch

from app import music_library, realtime


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


async def upload_file(client, room_id, token, filename, content=b"fake audio bytes", content_type="audio/mpeg"):
    resp = await client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": (filename, content, content_type)},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["file_id"]


# Room DJ: start/stop music, permissions, snapshot on connect ------------------

async def test_mod_can_start_music_and_room_is_notified(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")

    owner_ws = await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    file_id = await upload_file(client, room_id, token, "song.mp3")
    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": file_id})

    for ws in (owner_ws, other_ws):
        events = [e for e in ws.sent if e.get("type") == "music_started"]
        assert len(events) == 1
        assert events[0]["file_id"] == file_id
        assert events[0]["filename"] == "song.mp3"
        assert events[0]["started_by_member_id"] == owner_id


async def test_plain_member_cannot_start_or_stop_music(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    member = await join(client, data["room"]["code"], "Rando")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, member["member_id"])

    file_id = await upload_file(client, room_id, token, "song.mp3")

    try:
        await ws_dispatch(app, room_id, member["member_id"], "start_music", {"file_id": file_id})
        assert False, "plain member should not be able to start music"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": file_id})

    try:
        await ws_dispatch(app, room_id, member["member_id"], "stop_music", {})
        assert False, "plain member should not be able to stop music"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"


async def test_non_audio_file_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    await register_socket(app, room_id, owner_id)

    file_id = await upload_file(client, room_id, token, "notes.txt", content=b"hello", content_type="text/plain")

    try:
        await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": file_id})
        assert False, "non-audio file should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "file_type"


async def test_stop_music_clears_state_and_notifies(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    owner_ws = await register_socket(app, room_id, owner_id)

    file_id = await upload_file(client, room_id, token, "song.mp3")
    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": file_id})
    await ws_dispatch(app, room_id, owner_id, "stop_music", {})

    stopped = [e for e in owner_ws.sent if e.get("type") == "music_stopped"]
    assert len(stopped) == 1

    assert await realtime.music_snapshot(app.state.redis, room_id) is None


async def test_starting_new_track_replaces_previous_state(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    await register_socket(app, room_id, owner_id)

    first_id = await upload_file(client, room_id, token, "first.mp3")
    second_id = await upload_file(client, room_id, token, "second.mp3")

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})
    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": second_id})

    state = await realtime.music_snapshot(app.state.redis, room_id)
    assert state["file_id"] == second_id
    assert state["filename"] == "second.mp3"


async def test_music_snapshot_reflects_redis_state_for_late_joiners(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    await register_socket(app, room_id, owner_id)

    assert await realtime.music_snapshot(app.state.redis, room_id) is None

    file_id = await upload_file(client, room_id, token, "song.mp3")
    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": file_id})

    # This is exactly what main.py's websocket route does for a newly
    # connecting socket - a direct read, not a broadcast, so a late joiner
    # or reconnect gets caught up without needing a separate event type.
    state = await realtime.music_snapshot(app.state.redis, room_id)
    assert state["file_id"] == file_id
    started_at_ms = state["started_at_ms"]

    # Still there, unchanged, on a second read (e.g. a reconnect).
    state_again = await realtime.music_snapshot(app.state.redis, room_id)
    assert state_again["started_at_ms"] == started_at_ms


# Built-in library tracks - no upload needed -----------------------------------

async def test_mod_can_start_a_library_track(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    other = await join(client, data["room"]["code"], "Listener")

    owner_ws = await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    track = music_library.list_tracks()[0]
    await ws_dispatch(app, room_id, owner_id, "start_music", {"library_track_id": track["id"]})

    for ws in (owner_ws, other_ws):
        events = [e for e in ws.sent if e.get("type") == "music_started"]
        assert len(events) == 1
        assert events[0]["source"] == "library"
        assert events[0]["url"] == track["url"]
        assert events[0]["filename"] == track["title"]
        assert track["artist"] in events[0]["attribution"]

    state = await realtime.music_snapshot(app.state.redis, room_id)
    assert state["source"] == "library"
    assert state["url"] == track["url"]


async def test_unknown_library_track_id_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    await register_socket(app, room_id, owner_id)

    try:
        await ws_dispatch(app, room_id, owner_id, "start_music", {"library_track_id": "not-a-real-track"})
        assert False, "unknown library track id should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_plain_member_cannot_start_library_track(client, app):
    data = await create_room(client)
    room_id = data["room"]["id"]
    member = await join(client, data["room"]["code"], "Rando")
    await register_socket(app, room_id, member["member_id"])

    track = music_library.list_tracks()[0]
    try:
        await ws_dispatch(
            app, room_id, member["member_id"], "start_music", {"library_track_id": track["id"]}
        )
        assert False, "plain member should not be able to start a library track"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"


async def test_music_library_route_lists_all_tracks(client):
    resp = await client.get("/api/music-library")
    assert resp.status_code == 200
    tracks = resp.json()["tracks"]
    assert len(tracks) == 20
    assert all({"id", "title", "artist", "license", "url"} <= set(t) for t in tracks)
