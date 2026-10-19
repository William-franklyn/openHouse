from conftest import register_socket, ws_dispatch

from app.models import Member


async def create_room(client, name="Test Room", owner_name="Owner"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def join(client, code, name, device_id=None):
    resp = await client.post(
        f"/api/rooms/{code}/join", json={"name": name, "over_18": True, "device_id": device_id}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def get_member(app, member_id):
    async with app.state.db.session() as session:
        return await session.get(Member, member_id)


# 3. Permission table: remove/ban/set_role -----------------------------------

async def test_owner_can_remove_mod_and_member(client, app):
    data = await create_room(client)
    room_id, owner_id, code = data["room"]["id"], data["member"]["member_id"], data["room"]["code"]

    mod = await join(client, code, "Moddy")
    member = await join(client, code, "Membery")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, mod["member_id"])
    await register_socket(app, room_id, member["member_id"])

    await ws_dispatch(app, room_id, owner_id, "set_role", {"member_id": mod["member_id"], "role": "mod"})
    assert (await get_member(app, mod["member_id"])).role == "mod"

    await ws_dispatch(app, room_id, owner_id, "remove_member", {"member_id": mod["member_id"]})
    assert (await get_member(app, mod["member_id"])).status == "removed"

    await ws_dispatch(app, room_id, owner_id, "remove_member", {"member_id": member["member_id"]})
    assert (await get_member(app, member["member_id"])).status == "removed"


async def test_mod_cannot_remove_owner_or_other_mod(client, app):
    data = await create_room(client)
    room_id, owner_id, code = data["room"]["id"], data["member"]["member_id"], data["room"]["code"]

    mod1 = await join(client, code, "Mod1")
    mod2 = await join(client, code, "Mod2")
    member = await join(client, code, "Membery")

    for member_id in (owner_id, mod1["member_id"], mod2["member_id"], member["member_id"]):
        await register_socket(app, room_id, member_id)

    await ws_dispatch(app, room_id, owner_id, "set_role", {"member_id": mod1["member_id"], "role": "mod"})
    await ws_dispatch(app, room_id, owner_id, "set_role", {"member_id": mod2["member_id"], "role": "mod"})

    try:
        await ws_dispatch(app, room_id, mod1["member_id"], "remove_member", {"member_id": owner_id})
        assert False, "mod should not be able to remove the owner"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"

    try:
        await ws_dispatch(
            app, room_id, mod1["member_id"], "remove_member", {"member_id": mod2["member_id"]}
        )
        assert False, "mod should not be able to remove another mod"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"

    # but a mod CAN remove a plain member
    await ws_dispatch(app, room_id, mod1["member_id"], "remove_member", {"member_id": member["member_id"]})
    assert (await get_member(app, member["member_id"])).status == "removed"


async def test_set_role_owner_only(client, app):
    data = await create_room(client)
    room_id, owner_id, code = data["room"]["id"], data["member"]["member_id"], data["room"]["code"]
    a = await join(client, code, "A")
    b = await join(client, code, "B")

    for member_id in (owner_id, a["member_id"], b["member_id"]):
        await register_socket(app, room_id, member_id)

    try:
        await ws_dispatch(app, room_id, a["member_id"], "set_role", {"member_id": b["member_id"], "role": "mod"})
        assert False, "only the owner can change roles"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"

    await ws_dispatch(app, room_id, owner_id, "set_role", {"member_id": a["member_id"], "role": "mod"})
    assert (await get_member(app, a["member_id"])).role == "mod"


# 4. Ownership handover --------------------------------------------------------

async def test_ownership_handover_requires_acceptance_and_swaps_roles(client, app):
    data = await create_room(client)
    room_id, owner_id, code = data["room"]["id"], data["member"]["member_id"], data["room"]["code"]
    target = await join(client, code, "Mike")

    owner_ws = await register_socket(app, room_id, owner_id)
    target_ws = await register_socket(app, room_id, target["member_id"])

    await ws_dispatch(app, room_id, owner_id, "offer_ownership", {"member_id": target["member_id"]})
    offer_events = [e for e in target_ws.sent if e["type"] == "ownership_offer"]
    assert len(offer_events) == 1
    assert offer_events[0]["from_name"] == "Owner"

    await ws_dispatch(app, room_id, target["member_id"], "answer_ownership", {"accept": True})

    assert (await get_member(app, owner_id)).role == "member"
    assert (await get_member(app, target["member_id"])).role == "owner"

    async with app.state.db.session() as session:
        from app.models import Room

        room = await session.get(Room, room_id)
        assert room.owner_member_id == target["member_id"]

    changed_events = [e for e in owner_ws.sent if e["type"] == "ownership_changed"]
    assert len(changed_events) == 1
    assert changed_events[0]["new_owner_id"] == target["member_id"]


async def test_ownership_handover_declined_changes_nothing(client, app):
    data = await create_room(client)
    room_id, owner_id, code = data["room"]["id"], data["member"]["member_id"], data["room"]["code"]
    target = await join(client, code, "Mike")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, target["member_id"])

    await ws_dispatch(app, room_id, owner_id, "offer_ownership", {"member_id": target["member_id"]})
    await ws_dispatch(app, room_id, target["member_id"], "answer_ownership", {"accept": False})

    assert (await get_member(app, owner_id)).role == "owner"
    assert (await get_member(app, target["member_id"])).role == "member"
    assert app.state.hub.pending_offers.get(room_id) is None


# 6. Bans ----------------------------------------------------------------------

async def test_ban_blocks_rejoin_by_session_and_device(client, app):
    data = await create_room(client)
    room_id, owner_id, code = data["room"]["id"], data["member"]["member_id"], data["room"]["code"]

    victim = await join(client, code, "Guesty", device_id="device-xyz")
    victim_token = victim["session_token"]

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, victim["member_id"])

    await ws_dispatch(app, room_id, owner_id, "ban_member", {"member_id": victim["member_id"]})
    assert (await get_member(app, victim["member_id"])).status == "banned"

    # old session no longer works
    denied = await client.get(f"/api/rooms/{room_id}", headers=auth(victim_token))
    assert denied.status_code == 401
    assert denied.json()["code"] == "bad_token"

    # same device, fresh join attempt -> banned
    retry = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "NewName", "over_18": True, "device_id": "device-xyz"},
    )
    assert retry.status_code == 403
    assert retry.json()["code"] == "banned"


async def test_kicked_member_can_rejoin_with_new_join_unlike_banned(client, app):
    data = await create_room(client)
    room_id, owner_id, code = data["room"]["id"], data["member"]["member_id"], data["room"]["code"]

    member = await join(client, code, "Guesty", device_id="device-same")

    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, member["member_id"])

    await ws_dispatch(app, room_id, owner_id, "remove_member", {"member_id": member["member_id"]})
    assert (await get_member(app, member["member_id"])).status == "removed"

    retry = await client.post(
        f"/api/rooms/{code}/join",
        json={"name": "Guesty", "over_18": True, "device_id": "device-same"},
    )
    assert retry.status_code == 200
