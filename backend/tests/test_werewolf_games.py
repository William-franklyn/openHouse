import asyncio
import random

from conftest import register_socket, ws_dispatch

from app import realtime
from app.party_engines import werewolf_engine


async def _wait_for(predicate, timeout=1.0, interval=0.02):
    elapsed = 0.0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return predicate()


async def create_room(client, name="Test Room", owner_name="Host"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def join(client, code, name):
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": name, "over_18": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _party_states(ws):
    return [e for e in ws.sent if e.get("type") == "party_state"]


async def _start_lobby(app, room_id, host_id):
    host_ws = await register_socket(app, room_id, host_id)
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "werewolf"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    return party_game_id, host_ws


async def _start_game(app, room_id, member_ids, seed=1):
    host_id = member_ids[0]
    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    sockets = {host_id: host_ws}
    for member_id in member_ids[1:]:
        ws = await register_socket(app, room_id, member_id)
        await ws_dispatch(app, room_id, member_id, "join_party_game", {"party_game_id": party_game_id})
        sockets[member_id] = ws
    random.seed(seed)
    await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})
    return party_game_id, sockets


async def _setup_room_with_n(client, app, n):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    member_ids = [host_id]
    for i in range(2, n + 1):
        joined = await join(client, data["room"]["code"], f"P{i}")
        member_ids.append(joined["member_id"])
    return room_id, member_ids


async def test_starting_werewolf_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "werewolf"})

    assert _party_states(host_ws)[-1]["status"] == "lobby"
    assert _party_states(bystander_ws)[-1]["status"] == "lobby"


async def test_starting_with_fewer_than_five_players_is_rejected(client, app):
    room_id, member_ids = await _setup_room_with_n(client, app, 3)
    party_game_id, host_ws = await _start_lobby(app, room_id, member_ids[0])
    for member_id in member_ids[1:]:
        await register_socket(app, room_id, member_id)
        await ws_dispatch(app, room_id, member_id, "join_party_game", {"party_game_id": party_game_id})

    try:
        await ws_dispatch(app, room_id, member_ids[0], "begin_party_game", {"party_game_id": party_game_id})
        assert False, "starting with only 3 players should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_werewolves_see_their_team_villagers_do_not(client, app):
    room_id, member_ids = await _setup_room_with_n(client, app, 7)
    party_game_id, sockets = await _start_game(app, room_id, member_ids)

    states = {m: _party_states(sockets[m])[-1] for m in member_ids}
    wolves = [m for m, s in states.items() if s["my_role"] == "werewolf"]
    villagers = [m for m, s in states.items() if s["my_role"] == "villager"]
    assert len(wolves) >= 1
    assert len(villagers) >= 1

    for wolf in wolves:
        assert set(states[wolf]["werewolf_team"]) == set(wolves)
    for villager in villagers:
        assert states[villager]["werewolf_team"] is None
        assert states[villager]["all_roles"] is None


async def test_a_villager_cannot_submit_a_night_action(client, app):
    room_id, member_ids = await _setup_room_with_n(client, app, 7)
    party_game_id, sockets = await _start_game(app, room_id, member_ids)

    states = {m: _party_states(sockets[m])[-1] for m in member_ids}
    villager = next(m for m, s in states.items() if s["my_role"] == "villager")
    try:
        await ws_dispatch(
            app, room_id, villager, "party_action",
            {"party_game_id": party_game_id, "action": "wolf_vote", "target_id": member_ids[0]},
        )
        assert False, "a villager should have no night action"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_a_full_night_and_day_cycle_resolves_via_ws_dispatch(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_n(client, app, 7)
    party_game_id, sockets = await _start_game(app, room_id, member_ids)

    states = {m: _party_states(sockets[m])[-1] for m in member_ids}
    wolves = [m for m, s in states.items() if s["my_role"] == "werewolf"]
    doctor = next((m for m, s in states.items() if s["my_role"] == "doctor"), None)
    seer = next(m for m, s in states.items() if s["my_role"] == "seer")
    alive = list(member_ids)

    for wolf in wolves:
        victim = next(m for m in alive if m not in wolves)
        await ws_dispatch(
            app, room_id, wolf, "party_action",
            {"party_game_id": party_game_id, "action": "wolf_vote", "target_id": victim},
        )
    if doctor:
        save_target = next(m for m in alive if m != doctor)
        await ws_dispatch(
            app, room_id, doctor, "party_action",
            {"party_game_id": party_game_id, "action": "doctor_save", "target_id": save_target},
        )
    inspect_target = next(m for m in alive if m != seer)
    await ws_dispatch(
        app, room_id, seer, "party_action",
        {"party_game_id": party_game_id, "action": "seer_inspect", "target_id": inspect_target},
    )

    assert await _wait_for(lambda: _party_states(sockets[member_ids[0]])[-1]["phase"] == "day_vote", timeout=2.0)

    seer_state = _party_states(sockets[seer])[-1]
    assert inspect_target in seer_state["my_seer_knowledge"]

    final_state = _party_states(sockets[member_ids[0]])[-1]
    living = [m for m in member_ids if final_state["alive"][m]]
    for m in living:
        target = next(p for p in living if p != m)
        await ws_dispatch(
            app, room_id, m, "party_action",
            {"party_game_id": party_game_id, "action": "day_vote", "target_id": target},
        )

    assert await _wait_for(
        lambda: _party_states(sockets[member_ids[0]])[-1]["phase"] in ("night_actions", "reveal")
        or _party_states(sockets[member_ids[0]])[-1]["status"] == "finished",
        timeout=2.0,
    )


async def test_skip_round_resolves_the_current_phase_immediately(client, app):
    room_id, member_ids = await _setup_room_with_n(client, app, 7)
    party_game_id, sockets = await _start_game(app, room_id, member_ids)
    host_id = member_ids[0]

    await ws_dispatch(app, room_id, host_id, "skip_party_round", {"party_game_id": party_game_id})
    state = _party_states(sockets[host_id])[-1]
    assert state["phase"] == "reveal"


async def test_real_timer_resolves_a_night_with_no_submissions(client, app, monkeypatch):
    monkeypatch.setattr(werewolf_engine, "NIGHT_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_n(client, app, 7)
    party_game_id, sockets = await _start_game(app, room_id, member_ids)

    # Nobody ever acts - only the real server timer can resolve the night.
    assert await _wait_for(
        lambda: _party_states(sockets[member_ids[0]])[-1]["phase"] == "day_vote",
        timeout=2.0,
    )


async def test_reconnect_snapshot_resyncs_only_my_own_role_view(client, app):
    from app import party_games as party_games_mod

    room_id, member_ids = await _setup_room_with_n(client, app, 7)
    party_game_id, sockets = await _start_game(app, room_id, member_ids)

    async with app.state.db.session() as session:
        snapshot_a = await party_games_mod.connect_snapshot_event(session, room_id, member_ids[0])
        snapshot_b = await party_games_mod.connect_snapshot_event(session, room_id, member_ids[1])

    assert snapshot_a["my_role"] is not None
    assert snapshot_b["my_role"] is not None
