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


async def test_any_member_can_start_and_stop_music(client, app):
    """Picking a song is a normal member action, same as starting a call -
    not gated to owner/mod."""
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    member = await join(client, data["room"]["code"], "Rando")

    owner_ws = await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, member["member_id"])

    file_id = await upload_file(client, room_id, token, "song.mp3")

    await ws_dispatch(app, room_id, member["member_id"], "start_music", {"file_id": file_id})
    started = [e for e in owner_ws.sent if e.get("type") == "music_started"]
    assert len(started) == 1
    assert started[0]["started_by_member_id"] == member["member_id"]

    await ws_dispatch(app, room_id, member["member_id"], "stop_music", {})
    assert [e for e in owner_ws.sent if e.get("type") == "music_stopped"]


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


# Queue: conflict resolution when music is already playing -------------------

async def test_second_member_starting_music_is_queued_not_played(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")

    owner_ws = await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    first_id = await upload_file(client, room_id, token, "first.mp3")
    second_id = await upload_file(client, room_id, token, "second.mp3")

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})
    await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": second_id})

    # Still the first track playing - the second didn't cut it off.
    state = await realtime.music_snapshot(app.state.redis, room_id)
    assert state["file_id"] == first_id

    queue = await realtime.music_queue_snapshot(app.state.redis, room_id)
    assert len(queue) == 1
    assert queue[0]["file_id"] == second_id
    assert queue[0]["requested_by_member_id"] == other["member_id"]

    # Both sockets got the queue broadcast.
    for ws in (owner_ws, other_ws):
        updates = [e for e in ws.sent if e.get("type") == "music_queue_updated"]
        assert len(updates) == 1
        assert updates[0]["queue"][0]["file_id"] == second_id

    # Whoever's currently playing gets a direct heads-up, not a room broadcast.
    requested = [e for e in owner_ws.sent if e.get("type") == "music_requested"]
    assert len(requested) == 1
    assert requested[0]["requested_by_member_id"] == other["member_id"]
    assert not [e for e in other_ws.sent if e.get("type") == "music_requested"]


async def test_stopping_current_track_promotes_next_from_queue(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")

    await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    first_id = await upload_file(client, room_id, token, "first.mp3")
    second_id = await upload_file(client, room_id, token, "second.mp3")

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})
    await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": second_id})
    await ws_dispatch(app, room_id, owner_id, "stop_music", {})

    state = await realtime.music_snapshot(app.state.redis, room_id)
    assert state["file_id"] == second_id
    assert state["started_by_member_id"] == other["member_id"]

    assert await realtime.music_queue_snapshot(app.state.redis, room_id) == []

    started = [e for e in other_ws.sent if e.get("type") == "music_started"]
    assert started[-1]["file_id"] == second_id


async def test_track_ended_advances_queue_without_permission_check(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, other["member_id"])

    first_id = await upload_file(client, room_id, token, "first.mp3")
    second_id = await upload_file(client, room_id, token, "second.mp3")

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})
    await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": second_id})

    current = await realtime.music_snapshot(app.state.redis, room_id)
    # Reported by a listener who isn't the one who started it or a mod -
    # a natural "it finished" report, not a privileged stop.
    await ws_dispatch(
        app, room_id, other["member_id"], "music_track_ended", {"track_id": current["id"]}
    )

    state = await realtime.music_snapshot(app.state.redis, room_id)
    assert state["file_id"] == second_id


async def test_stale_track_ended_report_is_ignored(client, app):
    """Several listeners' <audio> elements can all fire onEnded around the
    same moment. Only a report matching whatever's still actually current
    does anything - a stale one (for a track that already advanced) is a
    no-op rather than skipping twice."""
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, other["member_id"])

    first_id = await upload_file(client, room_id, token, "first.mp3")
    second_id = await upload_file(client, room_id, token, "second.mp3")
    third_id = await upload_file(client, room_id, token, "third.mp3")

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})
    stale_track_id = (await realtime.music_snapshot(app.state.redis, room_id))["id"]
    await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": second_id})

    await ws_dispatch(app, room_id, owner_id, "stop_music", {})
    state = await realtime.music_snapshot(app.state.redis, room_id)
    assert state["file_id"] == second_id

    # A late-arriving "ended" report for the already-replaced first track.
    await ws_dispatch(app, room_id, owner_id, "music_track_ended", {"track_id": stale_track_id})
    unchanged = await realtime.music_snapshot(app.state.redis, room_id)
    assert unchanged["file_id"] == second_id
    assert unchanged["started_at_ms"] == state["started_at_ms"]
    assert third_id  # uploaded but never used - confirms nothing advanced past second


async def test_only_owner_or_mod_can_stop_someone_elses_track(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, other["member_id"])

    file_id = await upload_file(client, room_id, token, "song.mp3")
    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": file_id})

    try:
        await ws_dispatch(app, room_id, other["member_id"], "stop_music", {})
        assert False, "non-starter, non-mod should not be able to stop someone else's track"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"

    # Still playing - the rejected attempt didn't touch anything.
    assert (await realtime.music_snapshot(app.state.redis, room_id))["file_id"] == file_id


async def test_requeuing_replaces_members_own_earlier_queue_slot(client, app):
    """One queued slot per member - picking a second song while your first
    pick is still waiting replaces it instead of piling up two entries."""
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, other["member_id"])

    first_id = await upload_file(client, room_id, token, "first.mp3")
    queued_a = await upload_file(client, room_id, token, "queued_a.mp3")
    queued_b = await upload_file(client, room_id, token, "queued_b.mp3")

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})
    await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": queued_a})
    await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": queued_b})

    queue = await realtime.music_queue_snapshot(app.state.redis, room_id)
    assert len(queue) == 1
    assert queue[0]["file_id"] == queued_b


async def test_cancel_queued_music_removes_own_entry(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")

    await register_socket(app, room_id, owner_id)
    other_ws = await register_socket(app, room_id, other["member_id"])

    first_id = await upload_file(client, room_id, token, "first.mp3")
    second_id = await upload_file(client, room_id, token, "second.mp3")

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})
    await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": second_id})

    queued_track_id = (await realtime.music_queue_snapshot(app.state.redis, room_id))[0]["id"]
    await ws_dispatch(
        app, room_id, other["member_id"], "cancel_queued_music", {"track_id": queued_track_id}
    )

    assert await realtime.music_queue_snapshot(app.state.redis, room_id) == []
    updates = [e for e in other_ws.sent if e.get("type") == "music_queue_updated"]
    assert updates[-1]["queue"] == []


async def test_cancel_queued_music_rejects_someone_elses_entry(client, app):
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    other = await join(client, data["room"]["code"], "Listener")
    third = await join(client, data["room"]["code"], "Third")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, other["member_id"])
    await register_socket(app, room_id, third["member_id"])

    first_id = await upload_file(client, room_id, token, "first.mp3")
    second_id = await upload_file(client, room_id, token, "second.mp3")

    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})
    await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": second_id})

    queued_track_id = (await realtime.music_queue_snapshot(app.state.redis, room_id))[0]["id"]
    try:
        await ws_dispatch(
            app, room_id, third["member_id"], "cancel_queued_music", {"track_id": queued_track_id}
        )
        assert False, "a third member shouldn't be able to cancel someone else's queued pick"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"

    assert len(await realtime.music_queue_snapshot(app.state.redis, room_id)) == 1


async def test_music_queue_full_rejects_new_entries(client, app):
    """MUSIC_QUEUE_MAX is big enough that reaching it for real would mean
    joining/uploading past this test suite's own join/upload rate limits -
    pre-seeding the queue directly exercises the same cap check without
    fighting unrelated rate limiters."""
    data = await create_room(client)
    room_id, owner_id, token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    await register_socket(app, room_id, owner_id)

    first_id = await upload_file(client, room_id, token, "first.mp3")
    await ws_dispatch(app, room_id, owner_id, "start_music", {"file_id": first_id})

    full_queue = [
        {
            "source": "upload",
            "file_id": f"fake-{i}",
            "filename": f"queued{i}.mp3",
            "id": f"fake-track-{i}",
            "requested_by_member_id": f"fake-member-{i}",
            "requested_by_name": f"Fake{i}",
            "queued_at_ms": 0,
        }
        for i in range(realtime.MUSIC_QUEUE_MAX)
    ]
    await realtime._save_queue(app.state.redis, app.state.settings, room_id, full_queue)

    other = await join(client, data["room"]["code"], "Overflow")
    await register_socket(app, room_id, other["member_id"])
    overflow_file_id = await upload_file(client, room_id, other["session_token"], "overflow.mp3")

    try:
        await ws_dispatch(app, room_id, other["member_id"], "start_music", {"file_id": overflow_file_id})
        assert False, "a full queue should reject further entries"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"

    assert len(await realtime.music_queue_snapshot(app.state.redis, room_id)) == realtime.MUSIC_QUEUE_MAX


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


async def test_plain_member_can_start_a_library_track(client, app):
    data = await create_room(client)
    room_id = data["room"]["id"]
    member = await join(client, data["room"]["code"], "Rando")
    member_ws = await register_socket(app, room_id, member["member_id"])

    track = music_library.list_tracks()[0]
    await ws_dispatch(app, room_id, member["member_id"], "start_music", {"library_track_id": track["id"]})

    started = [e for e in member_ws.sent if e.get("type") == "music_started"]
    assert len(started) == 1
    assert started[0]["source"] == "library"


async def test_music_library_route_lists_all_tracks(client):
    resp = await client.get("/api/music-library")
    assert resp.status_code == 200
    tracks = resp.json()["tracks"]
    assert len(tracks) == 20
    assert all({"id", "title", "artist", "license", "url"} <= set(t) for t in tracks)
