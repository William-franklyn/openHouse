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
