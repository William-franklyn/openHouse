import asyncio
import random

from conftest import register_socket, ws_dispatch

from app import realtime
from app.party_engines import buzzer_engine


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
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "buzzer"})
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


async def test_starting_buzzer_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "buzzer"})

    assert _party_states(host_ws)[-1]["status"] == "lobby"
    assert _party_states(bystander_ws)[-1]["status"] == "lobby"


async def test_no_correct_answer_is_leaked_before_reveal(client, app):
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)
    state = _party_states(sockets[member_ids[0]])[-1]
    assert "correct_index" not in state["question"]


async def test_the_second_buzz_is_rejected_once_someone_else_has_buzzed(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    await ws_dispatch(app, room_id, member_ids[0], "party_action", {"party_game_id": party_game_id, "action": "buzz"})
    try:
        await ws_dispatch(app, room_id, member_ids[1], "party_action", {"party_game_id": party_game_id, "action": "buzz"})
        assert False, "the second buzz should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_only_the_buzzer_may_submit_an_answer(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    await ws_dispatch(app, room_id, member_ids[0], "party_action", {"party_game_id": party_game_id, "action": "buzz"})
    assert await _wait_for(lambda: _party_states(sockets[member_ids[0]])[-1]["phase"] == "answering", timeout=2.0)

    try:
        await ws_dispatch(
            app, room_id, member_ids[1], "party_action",
            {"party_game_id": party_game_id, "action": "answer", "choice_index": 0},
        )
        assert False, "a non-buzzer should not be able to answer"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_a_correct_answer_awards_points(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    actor = member_ids[0]
    await ws_dispatch(app, room_id, actor, "party_action", {"party_game_id": party_game_id, "action": "buzz"})
    assert await _wait_for(lambda: _party_states(sockets[actor])[-1]["phase"] == "answering", timeout=2.0)
    state = _party_states(sockets[actor])[-1]
    question_id = state["question"]["id"]
    correct_index = next(q["correct_index"] for q in buzzer_engine._QUESTIONS if q["id"] == question_id)

    await ws_dispatch(
        app, room_id, actor, "party_action",
        {"party_game_id": party_game_id, "action": "answer", "choice_index": correct_index},
    )
    assert await _wait_for(
        lambda: any(
            r["member_id"] == actor and r["score"] == buzzer_engine.POINTS_PER_CORRECT
            for r in _party_states(sockets[actor])[-1]["scoreboard"]
        ),
        timeout=2.0,
    )


async def test_a_wrong_answer_locks_the_buzzer_out_and_reopens_buzzing(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    actor = member_ids[0]
    await ws_dispatch(app, room_id, actor, "party_action", {"party_game_id": party_game_id, "action": "buzz"})
    assert await _wait_for(lambda: _party_states(sockets[actor])[-1]["phase"] == "answering", timeout=2.0)
    state = _party_states(sockets[actor])[-1]
    question_id = state["question"]["id"]
    correct_index = next(q["correct_index"] for q in buzzer_engine._QUESTIONS if q["id"] == question_id)
    num_choices = len(state["question"]["choices"])
    wrong_index = (correct_index + 1) % num_choices

    await ws_dispatch(
        app, room_id, actor, "party_action",
        {"party_game_id": party_game_id, "action": "answer", "choice_index": wrong_index},
    )
    assert await _wait_for(lambda: _party_states(sockets[actor])[-1]["phase"] == "buzzing", timeout=2.0)
    final = _party_states(sockets[actor])[-1]
    assert actor in final["locked_out"]


async def test_skip_round_resolves_the_current_phase_immediately(client, app):
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)
    host_id = member_ids[0]

    await ws_dispatch(app, room_id, host_id, "skip_party_round", {"party_game_id": party_game_id})
    state = _party_states(sockets[host_id])[-1]
    assert state["phase"] == "reveal"


async def test_real_timer_reveals_unsolved_when_nobody_buzzes(client, app, monkeypatch):
    monkeypatch.setattr(buzzer_engine, "BUZZ_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    # Nobody ever buzzes - only the real server timer can resolve this.
    assert await _wait_for(
        lambda: _party_states(sockets[member_ids[0]])[-1]["question_number"] >= 2,
        timeout=2.0,
    )


async def test_reconnect_snapshot_is_available_to_every_participant(client, app):
    from app import party_games as party_games_mod

    room_id, member_ids = await _setup_room_with_three(client, app)
    party_game_id, sockets = await _start_three_player_game(app, room_id, member_ids)

    async with app.state.db.session() as session:
        snapshot = await party_games_mod.connect_snapshot_event(session, room_id, member_ids[0])

    assert snapshot["question"] is not None
    assert "correct_index" not in snapshot["question"]
