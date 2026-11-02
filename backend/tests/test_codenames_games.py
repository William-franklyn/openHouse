import asyncio
import random

from conftest import register_socket, ws_dispatch

from app import realtime
from app.party_engines import codenames_engine


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
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "codenames"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    return party_game_id, host_ws


async def _start_four_player_game(app, room_id, member_ids, seed=1):
    """member_ids[0] is the host (red spymaster), [1] becomes blue spymaster,
    [2] red operative, [3] blue operative - matches the engine's alternating
    join-order team split."""
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


async def _setup_room_with_four(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    p3 = await join(client, data["room"]["code"], "P3")
    p4 = await join(client, data["room"]["code"], "P4")
    member_ids = [host_id, p2["member_id"], p3["member_id"], p4["member_id"]]
    return room_id, member_ids


async def test_starting_codenames_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "codenames"})

    assert _party_states(host_ws)[-1]["status"] == "lobby"
    assert _party_states(bystander_ws)[-1]["status"] == "lobby"


async def test_starting_with_fewer_than_four_players_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    await register_socket(app, room_id, p2["member_id"])
    await ws_dispatch(app, room_id, p2["member_id"], "join_party_game", {"party_game_id": party_game_id})

    try:
        await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})
        assert False, "starting with only 2 players should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_spymaster_sees_owners_operative_does_not(client, app):
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)

    red_sm_state = _party_states(sockets[member_ids[0]])[-1]
    red_op_state = _party_states(sockets[member_ids[2]])[-1]

    assert red_sm_state["my_role"] == "spymaster"
    assert all(c["owner"] is not None for c in red_sm_state["board"])

    assert red_op_state["my_role"] == "operative"
    assert all(c["owner"] is None for c in red_op_state["board"] if not c["revealed"])


async def test_only_the_active_spymaster_can_submit_a_clue(client, app):
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)

    not_spymaster = member_ids[2]  # red operative
    try:
        await ws_dispatch(
            app, room_id, not_spymaster, "party_action",
            {"party_game_id": party_game_id, "action": "clue", "word": "FRUIT", "number": 2},
        )
        assert False, "a non-spymaster giving a clue should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_a_full_clue_and_guess_cycle_reveals_the_word_and_updates_everyone(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)
    red_sm, blue_sm, red_op, blue_op = member_ids

    await ws_dispatch(
        app, room_id, red_sm, "party_action",
        {"party_game_id": party_game_id, "action": "clue", "word": "FRUIT", "number": 2},
    )
    assert await _wait_for(lambda: _party_states(sockets[red_op])[-1]["phase"] == "guessing", timeout=2.0)

    state = _party_states(sockets[red_op])[-1]
    assert state["current_clue"] == {"word": "FRUIT", "number": 2}
    assert state["guesses_remaining"] == 3

    word_id = next(c["id"] for c in state["board"] if not c["revealed"])
    await ws_dispatch(
        app, room_id, red_op, "party_action",
        {"party_game_id": party_game_id, "action": "guess", "word_id": word_id},
    )
    assert await _wait_for(lambda: _party_states(sockets[blue_sm])[-1]["phase"] == "reveal", timeout=2.0)
    revealed_state = _party_states(sockets[blue_sm])[-1]
    revealed_card = next(c for c in revealed_state["board"] if c["id"] == word_id)
    assert revealed_card["revealed"] is True
    # Blue's spymaster can see the true owner regardless of reveal status,
    # but now that it's revealed, red's operative must see it too.
    red_op_state = _party_states(sockets[red_op])[-1]
    assert next(c for c in red_op_state["board"] if c["id"] == word_id)["owner"] is not None


async def test_passing_ends_the_turn_and_switches_the_active_team(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)
    red_sm, blue_sm, red_op, blue_op = member_ids

    await ws_dispatch(
        app, room_id, red_sm, "party_action",
        {"party_game_id": party_game_id, "action": "clue", "word": "X", "number": 1},
    )
    assert await _wait_for(lambda: _party_states(sockets[red_op])[-1]["phase"] == "guessing", timeout=2.0)
    await ws_dispatch(app, room_id, red_op, "party_action", {"party_game_id": party_game_id, "action": "pass"})
    assert await _wait_for(lambda: _party_states(sockets[blue_sm])[-1]["active_team"] == "blue", timeout=2.0)


async def test_skip_round_resolves_the_current_phase_immediately(client, app):
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)
    host_id = member_ids[0]

    await ws_dispatch(app, room_id, host_id, "skip_party_round", {"party_game_id": party_game_id})
    state = _party_states(sockets[host_id])[-1]
    assert state["phase"] == "reveal"


async def test_hitting_the_assassin_ends_the_game_and_posts_a_system_message(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)
    red_sm, blue_sm, red_op, blue_op = member_ids

    await ws_dispatch(
        app, room_id, red_sm, "party_action",
        {"party_game_id": party_game_id, "action": "clue", "word": "X", "number": 1},
    )
    assert await _wait_for(lambda: _party_states(sockets[red_op])[-1]["phase"] == "guessing", timeout=2.0)

    # The operative view doesn't expose unrevealed owners, so look up the
    # assassin's real word id via the spymaster's fully-visible board.
    sm_state = _party_states(sockets[red_sm])[-1]
    assassin_id = next(c["id"] for c in sm_state["board"] if c["owner"] == "assassin")

    await ws_dispatch(
        app, room_id, red_op, "party_action",
        {"party_game_id": party_game_id, "action": "guess", "word_id": assassin_id},
    )
    assert await _wait_for(lambda: _party_states(sockets[red_sm])[-1]["status"] == "finished", timeout=2.0)
    final = _party_states(sockets[red_sm])[-1]
    assert final["winner"] == "blue"
    assert final["win_reason"] == "assassin_hit"

    messages = [e for e in sockets[red_sm].sent if e.get("type") == "message" and e.get("kind") == "system"]
    assert any("Codenames" in (m.get("text") or "") for m in messages)


async def test_real_timer_passes_an_afk_spymasters_turn(client, app, monkeypatch):
    monkeypatch.setattr(codenames_engine, "CLUE_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)
    red_sm = member_ids[0]

    # Nobody ever gives a clue - only the real server timer can resolve this.
    assert await _wait_for(lambda: _party_states(sockets[red_sm])[-1]["active_team"] == "blue", timeout=2.0)


async def test_reconnect_snapshot_resyncs_role_appropriate_board_view(client, app):
    from app import party_games as party_games_mod

    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)
    red_sm, blue_sm, red_op, blue_op = member_ids

    async with app.state.db.session() as session:
        sm_snapshot = await party_games_mod.connect_snapshot_event(session, room_id, red_sm)
        op_snapshot = await party_games_mod.connect_snapshot_event(session, room_id, red_op)

    assert all(c["owner"] is not None for c in sm_snapshot["board"])
    assert all(c["owner"] is None for c in op_snapshot["board"] if not c["revealed"])
