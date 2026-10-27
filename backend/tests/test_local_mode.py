"""Local mode: an owner-only, IP-only proximity gate - see rooms.set_local_mode
and members.join_room. Deliberately not GPS (see SPEC.md Decisions): this
never asks anyone for their location, it only compares request IPs."""


async def create_room(client, name="Test Room", owner_name="Owner"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def from_ip(ip):
    return {"X-Forwarded-For": ip}


async def test_owner_can_turn_on_local_mode_from_their_network(client):
    data = await create_room(client)
    room_id, token = data["room"]["id"], data["session_token"]

    resp = await client.post(
        f"/api/rooms/{room_id}/local-mode", json={"enabled": True}, headers={**auth(token), **from_ip("9.9.9.9")}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["local_mode"] is True

    # the actual IP it's pinned to is never exposed to anyone, owner included
    assert "local_mode_ip" not in resp.json()
    assert "ip" not in resp.json()


async def test_by_code_preview_reflects_local_mode_without_leaking_ip(client):
    data = await create_room(client)
    room_id, code, token = data["room"]["id"], data["room"]["code"], data["session_token"]

    preview_off = await client.get(f"/api/rooms/by-code/{code}")
    assert preview_off.json()["local_mode"] is False

    await client.post(
        f"/api/rooms/{room_id}/local-mode", json={"enabled": True}, headers={**auth(token), **from_ip("9.9.9.9")}
    )

    preview_on = await client.get(f"/api/rooms/by-code/{code}")
    assert preview_on.json()["local_mode"] is True
    assert "local_mode_ip" not in preview_on.json()


async def test_join_blocked_from_a_different_network_allowed_from_the_same_one(client):
    data = await create_room(client)
    room_id, code, token = data["room"]["id"], data["room"]["code"], data["session_token"]

    await client.post(
        f"/api/rooms/{room_id}/local-mode", json={"enabled": True}, headers={**auth(token), **from_ip("9.9.9.9")}
    )

    blocked = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Faraway", "over_18": True},
        headers=from_ip("1.1.1.1"),
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "wrong_network"

    allowed = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Nearby", "over_18": True},
        headers=from_ip("9.9.9.9"),
    )
    assert allowed.status_code == 200, allowed.text


async def test_turning_local_mode_off_allows_any_network_again(client):
    data = await create_room(client)
    room_id, code, token = data["room"]["id"], data["room"]["code"], data["session_token"]

    await client.post(
        f"/api/rooms/{room_id}/local-mode", json={"enabled": True}, headers={**auth(token), **from_ip("9.9.9.9")}
    )
    await client.post(f"/api/rooms/{room_id}/local-mode", json={"enabled": False}, headers=auth(token))

    resp = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Anyone", "over_18": True},
        headers=from_ip("1.1.1.1"),
    )
    assert resp.status_code == 200, resp.text


async def test_only_the_owner_can_toggle_local_mode(client):
    data = await create_room(client)
    code, owner_token = data["room"]["code"], data["session_token"]

    member = await client.post(
        f"/api/rooms/{code}/join", json={"name": "Member", "over_18": True}
    )
    member_token = member.json()["session_token"]

    resp = await client.post(
        f"/api/rooms/{data['room']['id']}/local-mode",
        json={"enabled": True},
        headers=auth(member_token),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "not_allowed"


async def test_join_without_local_mode_is_unaffected_by_network(client):
    data = await create_room(client)
    code = data["room"]["code"]

    resp = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Anyone", "over_18": True},
        headers=from_ip("203.0.113.5"),
    )
    assert resp.status_code == 200, resp.text
