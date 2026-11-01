import asyncio

from conftest import register_socket, ws_dispatch

from app import realtime
from app.party_engines import trivia_engine


async def _wait_for(predicate, timeout=1.0, interval=0.02):
    """Same pattern as test_video_call.py/test_chess.py - poll instead of
    asserting on the very next tick, since room-wide broadcasts can race
    fakeredis's pubsub delivery."""
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
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "trivia"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    return party_game_id, host_ws


async def _start_two_player_game(app, room_id, host_id, p2_id):
    """Host opens a lobby, p2 joins, host begins - the roster locks at
    exactly 2 participants (TriviaEngine.MIN_PARTICIPANTS)."""
    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    p2_ws = await register_socket(app, room_id, p2_id)
    await ws_dispatch(app, room_id, p2_id, "join_party_game", {"party_game_id": party_game_id})
    await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})
    return party_game_id, host_ws, p2_ws


async def test_starting_trivia_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "trivia"})

    assert _party_states(host_ws)[-1]["status"] == "lobby"
    assert _party_states(bystander_ws)[-1]["status"] == "lobby"


async def test_joining_after_begin_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    late = await join(client, data["room"]["code"], "Late")
    await register_socket(app, room_id, late["member_id"])

    party_game_id, _, _ = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    try:
        await ws_dispatch(app, room_id, late["member_id"], "join_party_game", {"party_game_id": party_game_id})
        assert False, "joining a locked roster should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_starting_below_min_participants_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    party_game_id, _ = await _start_lobby(app, room_id, host_id)

    try:
        await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})
        assert False, "starting with only the host should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_each_participant_sees_their_own_answer_but_not_the_others(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    host_question = _party_states(host_ws)[-1]
    correct = host_question.get("question") is not None  # sanity: question is present pre-answer
    assert correct
    assert "correct_index" not in host_question["question"]

    await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "choice_index": 0})

    host_state = _party_states(host_ws)[-1]
    p2_state = _party_states(p2_ws)[-1]

    # Host sees their own pick reflected back...
    assert host_state["my_answer"] == {"choice_index": 0}
    # ...but p2 only sees that the host HAS answered, never what they picked.
    assert p2_state["my_answer"] is None
    assert host_id in p2_state["answered_member_ids"]
    assert "answers" not in p2_state


async def test_everyone_answering_ends_the_round_immediately(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    question = _party_states(host_ws)[-1]["question"]
    correct = next(i for i in range(len(question["choices"])))  # any valid index works for this test

    await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "choice_index": correct})
    assert _party_states(host_ws)[-1]["phase"] == "question"

    await ws_dispatch(app, room_id, p2["member_id"], "party_action", {"party_game_id": party_game_id, "choice_index": correct})
    # No sleep needed - the second answer synchronously drives the round-over transition.
    assert _party_states(host_ws)[-1]["phase"] == "reveal"
    assert _party_states(p2_ws)[-1]["phase"] == "reveal"


async def test_answering_twice_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, _, _ = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "choice_index": 0})
    try:
        await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "choice_index": 1})
        assert False, "answering twice should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_real_timer_fires_and_reveals_the_round(client, app, monkeypatch):
    monkeypatch.setattr(trivia_engine, "ROUND_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    assert _party_states(host_ws)[-1]["phase"] == "question"
    # Nobody answers - only the real server-side timer can end this round.
    assert await _wait_for(lambda: _party_states(host_ws)[-1]["phase"] == "reveal", timeout=2.0)
    assert await _wait_for(lambda: _party_states(p2_ws)[-1]["phase"] == "reveal", timeout=2.0)


async def test_real_timer_advances_through_multiple_rounds(client, app, monkeypatch):
    monkeypatch.setattr(trivia_engine, "ROUND_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, _ = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    assert await _wait_for(lambda: _party_states(host_ws)[-1]["round_index"] == 1, timeout=2.0)


async def test_cancelling_an_active_game_stops_its_pending_timer(client, app, monkeypatch):
    monkeypatch.setattr(trivia_engine, "ROUND_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, _ = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    await ws_dispatch(app, room_id, host_id, "cancel_party_game", {"party_game_id": party_game_id})
    cancelled_count = len([e for e in host_ws.sent if e.get("type") == "party_cancelled"])
    assert cancelled_count == 1

    await asyncio.sleep(0.3)  # well past the shortened round duration
    # No reveal should ever have arrived - only the cancellation event.
    assert all(e.get("phase") != "reveal" for e in _party_states(host_ws))


async def test_skip_round_is_host_only(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, _, _ = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    try:
        await ws_dispatch(app, room_id, p2["member_id"], "skip_party_round", {"party_game_id": party_game_id})
        assert False, "a non-host skipping should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"


async def test_host_skip_round_ends_it_immediately(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, _ = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    await ws_dispatch(app, room_id, host_id, "skip_party_round", {"party_game_id": party_game_id})
    assert _party_states(host_ws)[-1]["phase"] == "reveal"


async def test_lobby_disconnect_removes_member_from_roster(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    await register_socket(app, room_id, p2["member_id"])
    await ws_dispatch(app, room_id, p2["member_id"], "join_party_game", {"party_game_id": party_game_id})
    assert p2["member_id"] in _party_states(host_ws)[-1]["participant_ids"]

    async with app.state.db.session() as session:
        await realtime.cleanup_party_lobby_on_disconnect(session, app.state.settings, app.state.hub, room_id, p2["member_id"])

    assert p2["member_id"] not in _party_states(host_ws)[-1]["participant_ids"]


async def test_lobby_disconnect_of_the_last_participant_cancels_it(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)

    async with app.state.db.session() as session:
        await realtime.cleanup_party_lobby_on_disconnect(session, app.state.settings, app.state.hub, room_id, host_id)

    cancelled = [e for e in host_ws.sent if e.get("type") == "party_cancelled"]
    assert len(cancelled) == 1


async def test_reconnect_snapshot_resyncs_only_my_own_answer(client, app):
    from app import party_games as party_games_mod

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, _ = await _start_two_player_game(app, room_id, host_id, p2["member_id"])

    await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "choice_index": 0})

    async with app.state.db.session() as session:
        host_snapshot = await party_games_mod.connect_snapshot_event(session, room_id, host_id)
        p2_snapshot = await party_games_mod.connect_snapshot_event(session, room_id, p2["member_id"])

    assert host_snapshot["my_answer"] == {"choice_index": 0}
    assert p2_snapshot["my_answer"] is None


async def test_final_round_posts_a_winner_system_message(client, app, monkeypatch):
    monkeypatch.setattr(trivia_engine, "ROUND_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    host_ws = await register_socket(app, room_id, host_id)
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "trivia"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    p2_ws = await register_socket(app, room_id, p2["member_id"])
    await ws_dispatch(app, room_id, p2["member_id"], "join_party_game", {"party_game_id": party_game_id})
    # A short game - easier to drive to completion than the default 8 rounds.
    async with app.state.db.session() as session:
        from app.models import PartyGame
        party_game = await session.get(PartyGame, party_game_id)
        party_game.total_rounds = 1
        await session.commit()
    await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})

    assert await _wait_for(lambda: _party_states(host_ws)[-1]["status"] == "finished", timeout=2.0)

    messages = [e for e in host_ws.sent if e.get("type") == "message" and e.get("kind") == "system"]
    assert any("Trivia Night" in (m.get("text") or "") for m in messages)
