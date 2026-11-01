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
    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp_id, "kind": "tictactoe"})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]
    await ws_dispatch(app, room_id, opp_id, "accept_game", {"game_id": game_id})
    return game_id, owner_ws, opp_ws


async def test_challenge_creates_a_tictactoe_game(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)

    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp["member_id"], "kind": "tictactoe"})

    invites = [e for e in owner_ws.sent if e.get("type") == "game_invite"]
    assert len(invites) == 1
    assert invites[0]["kind"] == "tictactoe"


async def test_three_in_a_row_wins(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # X (owner, seat 0) takes the top row: 0, 1, 2. O (opp, seat 1) plays
    # elsewhere and never threatens a line of its own.
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "cell": 0})
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "cell": 3})
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "cell": 1})
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "cell": 4})
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "cell": 2})

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    last = states[-1]
    assert last["game_over"] is True
    assert last["result"] == "white"
    assert last["termination"] == "three_in_a_row"
    assert last["board"] == [0, 0, 0, 1, 1, None, None, None, None]


async def test_occupied_cell_is_illegal(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "cell": 0})
    try:
        await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "cell": 0})
        assert False, "playing an already-taken cell should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_move"


async def test_out_of_turn_move_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "cell": 4})
        assert False, "O moving before X should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_your_turn"


async def test_invalid_cell_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "cell": 99})
        assert False, "an out-of-range cell should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_full_board_with_no_winner_is_a_draw(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # Final board (X=owner/seat0, O=opp/seat1), no line for either side:
    #   X O X
    #   X O O
    #   O X X
    moves = [
        (owner_id, 0), (opp["member_id"], 1), (owner_id, 2),
        (opp["member_id"], 4), (owner_id, 3), (opp["member_id"], 5),
        (owner_id, 7), (opp["member_id"], 6), (owner_id, 8),
    ]
    for member_id, cell in moves:
        await ws_dispatch(app, room_id, member_id, "game_move", {"game_id": game_id, "cell": cell})

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    last = states[-1]
    assert last["game_over"] is True
    assert last["result"] == "draw"
    assert last["termination"] == "board_full"


async def test_legal_moves_key_is_absent_not_hinted(client, app):
    """Tic-tac-toe's engine returns None from legal_moves (trivial enough
    the frontend derives "any empty cell" itself) - confirm that actually
    means no legal_moves key on the wire at all, not an empty list."""
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    assert "legal_moves" not in states[-1]


async def test_reconnect_snapshot_round_trips_the_board(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "cell": 4})

    async with app.state.db.session() as session:
        event = await games_mod.connect_snapshot_event(session, room_id, owner_id)
    assert event["type"] == "game_state"
    assert event["game_id"] == game_id
    assert event["board"][4] == 0
