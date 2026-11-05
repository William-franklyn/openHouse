from conftest import register_socket, ws_dispatch

from app.config import Settings


async def create_room(client, name="Test Room", owner_name="Owner", ends_at=None):
    resp = await client.post(
        "/api/rooms", json={"name": name, "owner_name": owner_name, "ends_at": ends_at}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# 1. Room codes -------------------------------------------------------------

async def test_room_code_alphabet_and_uniqueness(client, app):
    settings: Settings = app.state.settings
    codes = set()
    for _ in range(15):
        data = await create_room(client)
        code = data["room"]["code"]
        assert len(code) == settings.ROOM_CODE_LENGTH
        assert all(ch in settings.ROOM_CODE_ALPHABET for ch in code)
        assert code not in codes
        codes.add(code)


async def test_new_code_stops_old_code_working(client):
    data = await create_room(client)
    room_id = data["room"]["id"]
    old_code = data["room"]["code"]
    token = data["session_token"]

    resp = await client.post(f"/api/rooms/{room_id}/new-code", headers=auth(token))
    assert resp.status_code == 200
    new_code = resp.json()["code"]
    assert new_code != old_code

    old_lookup = await client.get(f"/api/rooms/by-code/{old_code}")
    assert old_lookup.status_code == 404

    new_lookup = await client.get(f"/api/rooms/by-code/{new_code}")
    assert new_lookup.status_code == 200

    # existing members are unaffected: owner's session still works
    room_resp = await client.get(f"/api/rooms/{room_id}", headers=auth(token))
    assert room_resp.status_code == 200


# 2. Join policies + invites -------------------------------------------------

async def test_open_join_policy(client):
    data = await create_room(client)
    code = data["room"]["code"]

    resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Maria", "over_18": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["session_token"]


async def test_approval_join_policy(client):
    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]

    await client.patch(f"/api/rooms/{room_id}", json={"join_policy": "approval"}, headers=auth(owner_token))

    resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Maria", "over_18": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


async def test_invite_only_join_policy_single_use_and_expiry(client, app, monkeypatch):
    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]

    await client.patch(f"/api/rooms/{room_id}", json={"join_policy": "invite_only"}, headers=auth(owner_token))

    # no code at all -> bad_invite
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": "NoCode", "over_18": True})
    assert resp.status_code == 400
    assert resp.json()["code"] == "bad_invite"

    invite_resp = await client.post(f"/api/rooms/{room_id}/invites", headers=auth(owner_token))
    assert invite_resp.status_code == 200
    invite_code = invite_resp.json()["code"]

    ok = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Maria", "over_18": True, "invite_code": invite_code},
    )
    assert ok.status_code == 200

    # single use: second attempt with same invite code fails
    dupe = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Someone", "over_18": True, "invite_code": invite_code},
    )
    assert dupe.status_code == 400
    assert dupe.json()["code"] == "bad_invite"

    # expiry (mock time forward past the TTL)
    invite_resp2 = await client.post(f"/api/rooms/{room_id}/invites", headers=auth(owner_token))
    invite_code2 = invite_resp2.json()["code"]

    import datetime as dt

    import app.members as members_mod
    from app.models import utcnow

    future = utcnow() + dt.timedelta(seconds=app.state.settings.INVITE_TTL_SECONDS + 1)
    # The expiry check (`invite.expires_at < utcnow()`) runs inside
    # members.join_room, which did `from app.models import utcnow` - that
    # binds its own name, so patching app.models.utcnow wouldn't reach it.
    monkeypatch.setattr(members_mod, "utcnow", lambda: future)
    expired = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Late", "over_18": True, "invite_code": invite_code2},
    )
    assert expired.status_code == 400
    assert expired.json()["code"] == "bad_invite"


async def test_who_can_invite_setting(client):
    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]
    await client.patch(
        f"/api/rooms/{room_id}",
        json={"join_policy": "invite_only", "invite_by": "admins"},
        headers=auth(owner_token),
    )
    invite_resp = await client.post(f"/api/rooms/{room_id}/invites", headers=auth(owner_token))
    invite_code = invite_resp.json()["code"]
    join_resp = await client.post(
        f"/api/rooms/{code}/join", json={"name": "Maria", "over_18": True, "invite_code": invite_code}
    )
    member_token = join_resp.json()["session_token"]

    # invite_by=admins: member cannot create invites
    denied = await client.post(f"/api/rooms/{room_id}/invites", headers=auth(member_token))
    assert denied.status_code == 403
    assert denied.json()["code"] == "not_allowed"

    await client.patch(f"/api/rooms/{room_id}", json={"invite_by": "members"}, headers=auth(owner_token))
    allowed = await client.post(f"/api/rooms/{room_id}/invites", headers=auth(member_token))
    assert allowed.status_code == 200


async def test_invite_code_is_tracked_on_open_policy_rooms_too(client, app):
    """Regression test: open-policy rooms (the default) don't REQUIRE an
    invite code to join, but a valid one passed through a shared link
    should still be honored (marks the invite used, records who invited
    whom) rather than being silently ignored - previously the frontend
    never even sent it for non-invite_only rooms, so "Generate invite
    link" was pure decoration outside invite_only rooms."""
    from app.models import Invite, Member

    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]
    owner_member_id = data["member"]["member_id"]
    assert data["room"]["join_policy"] == "open"

    invite_resp = await client.post(f"/api/rooms/{room_id}/invites", headers=auth(owner_token))
    assert invite_resp.status_code == 200
    invite_code = invite_resp.json()["code"]

    join_resp = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Maria", "over_18": True, "invite_code": invite_code},
    )
    assert join_resp.status_code == 200
    member_id = join_resp.json()["member_id"]

    async with app.state.db.session() as session:
        invite = await session.get(Invite, invite_code)
        assert invite.used_by_member_id == member_id
        member = await session.get(Member, member_id)
        assert member.invited_by_member_id == owner_member_id

    # A missing/invalid code on an open room never blocks the join (unlike
    # invite_only) - it just goes untracked.
    second = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Someone", "over_18": True, "invite_code": "not-a-real-code"},
    )
    assert second.status_code == 200


async def test_over_18_required(client):
    data = await create_room(client)
    code = data["room"]["code"]
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Kid", "over_18": False})
    assert resp.status_code == 400
    assert resp.json()["code"] == "bad_request"


async def test_anonymous_join_name_pattern(client):
    data = await create_room(client)
    code = data["room"]["code"]
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": None, "over_18": True})
    assert resp.status_code == 200

    room_resp = await client.get(
        f"/api/rooms/{data['room']['id']}", headers=auth(resp.json()["session_token"])
    )
    assert room_resp.status_code == 200


# 3. Permission table: only the owner can delete -----------------------------

async def test_only_owner_can_delete_room(client):
    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]

    join_resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Maria", "over_18": True})
    member_token = join_resp.json()["session_token"]

    denied = await client.delete(f"/api/rooms/{room_id}", headers=auth(member_token))
    assert denied.status_code == 403
    assert denied.json()["code"] == "not_allowed"

    ok = await client.delete(f"/api/rooms/{room_id}", headers=auth(owner_token))
    assert ok.status_code == 200


# 3b. End room now (distinct from delete: no data loss) ----------------------

async def test_only_owner_can_end_room(client):
    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]

    join_resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Maria", "over_18": True})
    member_token = join_resp.json()["session_token"]

    denied = await client.post(f"/api/rooms/{room_id}/end", headers=auth(member_token))
    assert denied.status_code == 403
    assert denied.json()["code"] == "not_allowed"

    ok = await client.post(f"/api/rooms/{room_id}/end", headers=auth(owner_token))
    assert ok.status_code == 200


async def test_ending_a_room_blocks_new_joins_but_keeps_files_and_history(client):
    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]

    upload = await client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": ("note.txt", b"keep me", "text/plain")},
        headers=auth(owner_token),
    )
    file_id = upload.json()["file_id"]

    ended = await client.post(f"/api/rooms/{room_id}/end", headers=auth(owner_token))
    assert ended.status_code == 200

    blocked = await client.post(f"/api/rooms/{code}/join", json={"name": "Late", "over_18": True})
    assert blocked.status_code == 410
    assert blocked.json()["code"] == "room_ended"

    # Unlike delete, the file (and by extension chat history) is untouched -
    # ending just stamps ends_at, it doesn't run delete_room's cleanup.
    dl = await client.get(f"/api/files/{file_id}", headers=auth(owner_token))
    assert dl.status_code == 200


async def test_ending_a_room_broadcasts_to_connected_members(client, app):
    from conftest import register_socket

    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    ws = await register_socket(app, room_id, owner_id)

    await client.post(f"/api/rooms/{room_id}/end", headers=auth(owner_token))

    ended_events = [e for e in ws.sent if e.get("type") == "room_ended"]
    assert len(ended_events) == 1


# 5. Recovery code ------------------------------------------------------------

async def test_recovery_code_restores_ownership(client):
    data = await create_room(client)
    room_id = data["room"]["id"]
    recovery_code = data["recovery_code"]

    wrong = await client.post(f"/api/rooms/{room_id}/recover-owner", json={"recovery_code": "WRONGCODE123"})
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "not_allowed"

    ok = await client.post(f"/api/rooms/{room_id}/recover-owner", json={"recovery_code": recovery_code})
    assert ok.status_code == 200
    body = ok.json()
    assert body["member"]["role"] == "owner"
    new_token = body["session_token"]

    room_resp = await client.get(f"/api/rooms/{room_id}", headers=auth(new_token))
    assert room_resp.status_code == 200
    assert room_resp.json()["my_role"] == "owner"


async def test_recovery_rate_limited(client, app):
    data = await create_room(client)
    room_id = data["room"]["id"]
    settings: Settings = app.state.settings

    for _ in range(settings.RECOVERY_RATE_LIMIT):
        resp = await client.post(f"/api/rooms/{room_id}/recover-owner", json={"recovery_code": "WRONGCODE123"})
        assert resp.status_code == 403

    limited = await client.post(f"/api/rooms/{room_id}/recover-owner", json={"recovery_code": "WRONGCODE123"})
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"


# 10. Deleted / ended rooms ----------------------------------------------------

async def test_deleted_room_join_gives_room_ended_and_cleans_up(client):
    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]

    await client.delete(f"/api/rooms/{room_id}", headers=auth(owner_token))

    resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Late", "over_18": True})
    # the room's code lookup 404s once deleted (get_room_by_code excludes deleted rooms)
    assert resp.status_code == 404
    assert resp.json()["code"] == "bad_code"


async def test_ended_room_by_timer_gives_room_ended_on_join(client, app, monkeypatch):
    import datetime as dt

    from app.models import utcnow

    soon = utcnow() + dt.timedelta(seconds=5)
    data = await create_room(client, ends_at=soon.isoformat())
    code = data["room"]["code"]

    import app.models as models_mod

    monkeypatch.setattr(models_mod, "utcnow", lambda: soon + dt.timedelta(seconds=10))

    resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Late", "over_18": True})
    assert resp.status_code == 410
    assert resp.json()["code"] == "room_ended"


# 4. Deleting a room cleans up everything it owns -----------------------------

async def test_deleting_a_room_removes_pins_reactions_channels_and_members(client, app):
    from sqlalchemy import select

    from app.models import Channel, Member, MessageReaction, Pin

    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]
    owner_id = data["member"]["member_id"]

    join_resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Maria", "over_18": True})
    maria_id = join_resp.json()["member_id"]

    await register_socket(app, room_id, owner_id)
    async with app.state.db.session() as session:
        result = await session.execute(select(Channel).where(Channel.room_id == room_id))
        channel_id = result.scalars().one().id

    await ws_dispatch(app, room_id, owner_id, "send_message", {"channel_id": channel_id, "text": "hi"})
    async with app.state.db.session() as session:
        from app import messages as messages_mod

        message_id = (await messages_mod.history(session, channel_id, None, 10))[0].id

    await ws_dispatch(app, room_id, owner_id, "pin", {"message_id": message_id})
    await ws_dispatch(app, room_id, owner_id, "toggle_reaction", {"message_id": message_id, "emoji": "👍"})

    # Sanity check everything actually got created before we delete the room.
    async with app.state.db.session() as session:
        assert (await session.execute(select(Pin).where(Pin.room_id == room_id))).scalars().all()
        assert (
            await session.execute(select(MessageReaction).where(MessageReaction.message_id == message_id))
        ).scalars().all()
        assert (await session.execute(select(Channel).where(Channel.room_id == room_id))).scalars().all()
        assert (await session.execute(select(Member).where(Member.room_id == room_id))).scalars().all()

    delete_resp = await client.delete(f"/api/rooms/{room_id}", headers=auth(owner_token))
    assert delete_resp.status_code == 200

    async with app.state.db.session() as session:
        assert (await session.execute(select(Pin).where(Pin.room_id == room_id))).scalars().all() == []
        assert (
            await session.execute(select(MessageReaction).where(MessageReaction.message_id == message_id))
        ).scalars().all() == []
        assert (await session.execute(select(Channel).where(Channel.room_id == room_id))).scalars().all() == []
        assert (await session.execute(select(Member).where(Member.room_id == room_id))).scalars().all() == []


async def test_deleting_a_room_keeps_reports_for_moderation_history(client, app):
    from sqlalchemy import select

    from app.models import Report

    data = await create_room(client)
    room_id, code, owner_token = data["room"]["id"], data["room"]["code"], data["session_token"]

    join_resp = await client.post(f"/api/rooms/{code}/join", json={"name": "Bad Actor", "over_18": True})
    bad_actor_id = join_resp.json()["member_id"]

    report_resp = await client.post(
        f"/api/rooms/{room_id}/reports",
        json={"target_member_id": bad_actor_id, "reason": "being annoying"},
        headers=auth(owner_token),
    )
    assert report_resp.status_code == 200

    await client.delete(f"/api/rooms/{room_id}", headers=auth(owner_token))

    async with app.state.db.session() as session:
        reports = (await session.execute(select(Report).where(Report.room_id == room_id))).scalars().all()
        assert len(reports) == 1


# 5. Dormant room auto-deletion ------------------------------------------------

async def test_find_dormant_room_ids_only_returns_rooms_with_no_recent_activity(client, app):
    import datetime as dt

    from app import rooms as rooms_mod
    from app.models import Member, Room, utcnow

    fresh = await create_room(client, name="Fresh Room")
    stale = await create_room(client, name="Stale Room")

    old = utcnow() - dt.timedelta(days=10)
    async with app.state.db.session() as session:
        stale_room = await session.get(Room, stale["room"]["id"])
        stale_room.created_at = old
        member = await session.get(Member, stale["member"]["member_id"])
        member.last_seen_at = old
        member.created_at = old
        await session.commit()

        dormant_ids = await rooms_mod.find_dormant_room_ids(session, threshold_days=3)

    assert stale["room"]["id"] in dormant_ids
    assert fresh["room"]["id"] not in dormant_ids


async def test_a_recent_message_keeps_an_otherwise_old_room_alive(client, app):
    import datetime as dt

    from sqlalchemy import select

    from app import rooms as rooms_mod
    from app.models import Channel, Room, utcnow

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]

    old = utcnow() - dt.timedelta(days=10)
    async with app.state.db.session() as session:
        room = await session.get(Room, room_id)
        room.created_at = old
        from app.models import Member

        member = await session.get(Member, owner_id)
        member.last_seen_at = old
        member.created_at = old
        await session.commit()
        result = await session.execute(select(Channel).where(Channel.room_id == room_id))
        channel_id = result.scalars().one().id

    # A message sent "now" should keep this room off the dormant list even
    # though the room and its member both look ancient.
    await register_socket(app, room_id, owner_id)
    await ws_dispatch(app, room_id, owner_id, "send_message", {"channel_id": channel_id, "text": "still here"})

    async with app.state.db.session() as session:
        dormant_ids = await rooms_mod.find_dormant_room_ids(session, threshold_days=3)
    assert room_id not in dormant_ids


async def test_dormant_sweep_loop_actually_deletes_a_dormant_room(client, app, monkeypatch):
    import asyncio
    import datetime as dt

    from app.models import Member, Room, utcnow

    data = await create_room(client)
    room_id = data["room"]["id"]

    old = utcnow() - dt.timedelta(days=10)
    async with app.state.db.session() as session:
        room = await session.get(Room, room_id)
        room.created_at = old
        member = await session.get(Member, data["member"]["member_id"])
        member.last_seen_at = old
        member.created_at = old
        await session.commit()

    app.state.settings.DORMANT_ROOM_DAYS = 3
    app.state.settings.DORMANT_SWEEP_INTERVAL_SECONDS = 0.05

    from app import rooms as rooms_mod

    task = asyncio.create_task(
        rooms_mod.run_dormant_sweep_loop(app.state.db, app.state.storage, app.state.settings)
    )
    try:
        for _ in range(50):
            await asyncio.sleep(0.05)
            async with app.state.db.session() as session:
                refreshed = await session.get(Room, room_id)
                if refreshed.deleted_at is not None:
                    break
        else:
            assert False, "dormant room was never swept"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
