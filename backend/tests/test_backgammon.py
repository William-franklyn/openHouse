from conftest import register_socket, ws_dispatch

from app import game_engines


def _fixed_rolls(*rolls):
    """Monkeypatch target: app.game_engines.backgammon_engine._roll.
    Returns each given roll in order, then repeats the last one forever -
    tests only need the first one or two turns to be deterministic."""
    rolls = list(rolls)

    def _next():
        if len(rolls) > 1:
            return rolls.pop(0)
        return rolls[0]

    return _next


async def create_room(client, name="Test Room", owner_name="Owner"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def join(client, code, name):
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": name, "over_18": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _start_game(app, room_id, owner_id, opp_id):
    owner_ws = await register_socket(app, room_id, owner_id)
    opp_ws = await register_socket(app, room_id, opp_id)
    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp_id, "kind": "backgammon"})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]
    await ws_dispatch(app, room_id, opp_id, "accept_game", {"game_id": game_id})
    return game_id, owner_ws, opp_ws


async def test_challenge_creates_a_backgammon_game(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)

    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp["member_id"], "kind": "backgammon"})

    invites = [e for e in owner_ws.sent if e.get("type") == "game_invite"]
    assert len(invites) == 1
    assert invites[0]["kind"] == "backgammon"


async def test_initial_board_has_15_checkers_each(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    _, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    state = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    points = state["points"]
    assert sum(p for p in points if p > 0) == 15
    assert sum(-p for p in points if p < 0) == 15
    assert len(state["dice"]) in (2, 4)
    assert "legal_moves" in state


async def test_a_legal_move_is_applied_and_consumes_one_die(client, app, monkeypatch):
    monkeypatch.setattr(game_engines.backgammon_engine, "_roll", _fixed_rolls([6, 4]))

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    state = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    assert state["remaining_dice"] == [6, 4]

    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": 23, "to": 17})

    new_state = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    assert new_state["points"][17] == 1
    assert new_state["points"][23] == 1
    assert new_state["remaining_dice"] == [4]
    assert new_state["turn"] == "white"  # one die left, still the owner's turn


async def test_illegal_distance_is_rejected(client, app, monkeypatch):
    monkeypatch.setattr(game_engines.backgammon_engine, "_roll", _fixed_rolls([6, 4]))

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": 23, "to": 20})  # distance 3
        assert False, "a move not matching either die should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_move"


async def test_out_of_turn_move_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "from": 0, "to": 4})
        assert False, "opponent moving before owner should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_your_turn"


async def test_both_dice_used_passes_turn_to_the_opponent(client, app, monkeypatch):
    monkeypatch.setattr(game_engines.backgammon_engine, "_roll", _fixed_rolls([6, 4], [5, 2]))

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": 23, "to": 17})
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": 12, "to": 8})

    state = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    assert state["turn"] == "black"
    assert state["remaining_dice"] == [5, 2]


async def test_reconnect_snapshot_round_trips_the_board(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    async with app.state.db.session() as session:
        event = await games_mod.connect_snapshot_event(session, room_id, owner_id)
    assert event["type"] == "game_state"
    assert event["game_id"] == game_id
    assert sum(p for p in event["points"] if p > 0) == 15
