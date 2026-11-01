from conftest import register_socket, ws_dispatch


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
    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp_id, "kind": "checkers"})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]
    await ws_dispatch(app, room_id, opp_id, "accept_game", {"game_id": game_id})
    return game_id, owner_ws, opp_ws


async def test_challenge_creates_a_checkers_game(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)

    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp["member_id"], "kind": "checkers"})

    invites = [e for e in owner_ws.sent if e.get("type") == "game_invite"]
    assert len(invites) == 1
    assert invites[0]["kind"] == "checkers"


async def test_initial_board_has_24_pieces(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    _, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    board = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]["board"]
    occupied = [cell for row in board for cell in row if cell is not None]
    assert len(occupied) == 24


async def test_capture_removes_the_opponent_piece(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # Set up a capture the same way the unit test does: owner (white)
    # advances, opponent (black) advances into a capturable spot.
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": [2, 3], "to": [3, 4]})
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "from": [5, 2], "to": [4, 3]})
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": [3, 4], "to": [5, 2]})

    board = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]["board"]
    assert board[5][2] == "w"
    assert board[4][3] is None  # captured


async def test_non_capture_move_is_illegal_when_a_capture_is_available(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": [2, 3], "to": [3, 4]})
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "from": [5, 2], "to": [4, 3]})

    try:
        # Owner has a mandatory capture available (3,4)->(5,2) but tries
        # an unrelated simple move instead.
        await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": [2, 1], "to": [3, 0]})
        assert False, "a non-capture move should be rejected when a capture is available"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_move"


async def test_out_of_turn_move_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "from": [5, 0], "to": [4, 1]})
        assert False, "opponent moving before owner should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_your_turn"


async def test_reconnect_snapshot_round_trips_the_board(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": [2, 3], "to": [3, 4]})

    async with app.state.db.session() as session:
        event = await games_mod.connect_snapshot_event(session, room_id, owner_id)
    assert event["type"] == "game_state"
    assert event["game_id"] == game_id
    assert event["board"][3][4] == "w"
