import asyncio
import random

from conftest import register_socket, ws_dispatch

from app import realtime
from app.party_engines import drawing_engine


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
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "drawing"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    return party_game_id, host_ws


async def _start_three_player_game(app, room_id, member_ids, seed=1):
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


async def _setup_room_with_three(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    p3 = await join(client, data["room"]["code"], "P3")
    member_ids = [host_id, p2["member_id"], p3["member_id"]]
    return room_id, member_ids


async def test_starting_drawing_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "drawing"})

    assert _party_states(host_ws)[-1]["status"] == "lobby"
    assert _party_states(bystander_ws)[-1]["status"] == "lobby"


async def test_starting_with_fewer_than_three_players_is_rejected(client, app):
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


async def test_the_drawer_sees_the_word_everyone_else_sees_it_masked(client, app):
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    drawer_id = _party_states(sockets[member_ids[0]])[-1]["current_drawer_id"]
    drawer_state = _party_states(sockets[drawer_id])[-1]
    other_id = next(m for m in member_ids if m != drawer_id)
    other_state = _party_states(sockets[other_id])[-1]

    assert drawer_state["am_drawer"] is True
    assert "_" not in drawer_state["word"] or len(drawer_state["word"]) == drawer_state["word_length"]
    assert other_state["am_drawer"] is False
    assert set(other_state["word"].replace(" ", "")) <= {"_"}


async def test_the_drawer_cannot_submit_a_guess(client, app):
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)
    drawer_id = _party_states(sockets[member_ids[0]])[-1]["current_drawer_id"]

    try:
        await ws_dispatch(
            app, room_id, drawer_id, "party_action",
            {"party_game_id": party_game_id, "action": "guess", "text": "whatever"},
        )
        assert False, "the drawer should not be able to guess"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_a_correct_guess_from_everyone_resolves_the_turn(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    state = _party_states(sockets[member_ids[0]])[-1]
    drawer_id = state["current_drawer_id"]
    # The real secret word is only visible via the drawer's own view.
    secret_word = _party_states(sockets[drawer_id])[-1]["word"]
    guessers = [m for m in member_ids if m != drawer_id]

    for g in guessers:
        await ws_dispatch(
            app, room_id, g, "party_action",
            {"party_game_id": party_game_id, "action": "guess", "text": secret_word},
        )

    assert await _wait_for(lambda: _party_states(sockets[drawer_id])[-1]["phase"] == "reveal", timeout=2.0)
    final = _party_states(sockets[drawer_id])[-1]
    assert final["last_event"]["word"] == secret_word
    assert set(final["last_event"]["correct_guesser_ids"]) == set(guessers)


async def test_a_wrong_guess_does_not_leak_the_word_to_other_players(client, app):
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)
    drawer_id = _party_states(sockets[member_ids[0]])[-1]["current_drawer_id"]
    guesser = next(m for m in member_ids if m != drawer_id)

    await ws_dispatch(
        app, room_id, guesser, "party_action",
        {"party_game_id": party_game_id, "action": "guess", "text": "totally wrong"},
    )
    other = next(m for m in member_ids if m not in (drawer_id, guesser))
    other_state = _party_states(sockets[other])[-1]
    assert other_state["guess_log"][-1]["text"] == "totally wrong"
    assert set(other_state["word"].replace(" ", "")) <= {"_"}  # still masked


async def test_skip_round_resolves_the_current_turn_immediately(client, app):
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)
    host_id = member_ids[0]

    await ws_dispatch(app, room_id, host_id, "skip_party_round", {"party_game_id": party_game_id})
    state = _party_states(sockets[host_id])[-1]
    assert state["phase"] == "reveal"


async def test_real_timer_resolves_a_turn_with_no_guesses(client, app, monkeypatch):
    monkeypatch.setattr(drawing_engine, "DRAW_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    # Nobody ever guesses - only the real server timer can resolve the turn.
    assert await _wait_for(
        lambda: _party_states(sockets[member_ids[0]])[-1]["turn_number"] >= 2,
        timeout=2.0,
    )


async def test_reconnect_snapshot_resyncs_the_word_appropriately_per_role(client, app):
    from app import party_games as party_games_mod

    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)
    drawer_id = _party_states(sockets[member_ids[0]])[-1]["current_drawer_id"]
    other_id = next(m for m in member_ids if m != drawer_id)

    async with app.state.db.session() as session:
        drawer_snapshot = await party_games_mod.connect_snapshot_event(session, room_id, drawer_id)
        other_snapshot = await party_games_mod.connect_snapshot_event(session, room_id, other_id)

    assert drawer_snapshot["am_drawer"] is True
    assert other_snapshot["am_drawer"] is False
    assert set(other_snapshot["word"].replace(" ", "")) <= {"_"}
