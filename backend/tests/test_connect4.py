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
    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp_id, "kind": "connect4"})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]
    await ws_dispatch(app, room_id, opp_id, "accept_game", {"game_id": game_id})
    return game_id, owner_ws, opp_ws


async def test_challenge_creates_a_connect4_game(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)

    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp["member_id"], "kind": "connect4"})

    invites = [e for e in owner_ws.sent if e.get("type") == "game_invite"]
    assert len(invites) == 1
    assert invites[0]["kind"] == "connect4"


async def test_vertical_four_in_a_row_wins(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # X (owner, seat 0) drops 4 straight into column 0; O (opp, seat 1)
    # drops into column 1 each time, never threatening a line.
    for _ in range(4):
        await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "column": 0})
        if _ < 3:
            await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "column": 1})

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    last = states[-1]
    assert last["game_over"] is True
    assert last["result"] == "white"
    assert last["termination"] == "four_in_a_row"


async def test_horizontal_four_in_a_row_wins(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # X takes columns 0-3 on the bottom row; O takes a second row above
    # column 0-2, never completing a line.
    x_cols = [0, 1, 2, 3]
    o_cols = [0, 1, 2]
    for i in range(4):
        await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "column": x_cols[i]})
        if i < 3:
            await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "column": o_cols[i]})

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    last = states[-1]
    assert last["game_over"] is True
    assert last["result"] == "white"
    assert last["termination"] == "four_in_a_row"


async def test_diagonal_four_in_a_row_wins(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # Ascending diagonal for X (owner, seat 0) through (row5,col0),
    # (row4,col1), (row3,col2), (row2,col3) - needs 1/2/3 filler pieces
    # already under columns 1/2/3 respectively before X's piece lands on
    # top. Turns strictly alternate X/O regardless of column, so X's 3
    # "extra" turns (beyond the 4 diagonal placements) go into column 6,
    # off to the side, stacking harmlessly without forming a line of
    # their own (3 high, never 4).
    moves = [
        (owner_id, 0),          # X (5,0) - diagonal 1
        (opp["member_id"], 1),  # O (5,1) - filler, col1 ready
        (owner_id, 1),          # X (4,1) - diagonal 2
        (opp["member_id"], 2),  # O (5,2) - filler, col2 x1
        (owner_id, 6),          # X (5,6) - throwaway
        (opp["member_id"], 2),  # O (4,2) - filler, col2 x2, ready
        (owner_id, 2),          # X (3,2) - diagonal 3
        (opp["member_id"], 3),  # O (5,3) - filler, col3 x1
        (owner_id, 6),          # X (4,6) - throwaway
        (opp["member_id"], 3),  # O (4,3) - filler, col3 x2
        (owner_id, 6),          # X (3,6) - throwaway
        (opp["member_id"], 3),  # O (3,3) - filler, col3 x3, ready
        (owner_id, 3),          # X (2,3) - diagonal 4 - WIN
    ]
    for member_id, column in moves:
        await ws_dispatch(app, room_id, member_id, "game_move", {"game_id": game_id, "column": column})

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    last = states[-1]
    assert last["game_over"] is True
    assert last["result"] == "white"
    assert last["termination"] == "four_in_a_row"


async def test_full_column_is_illegal(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # Fill column 0 to the top (6 rows) alternating players.
    for i in range(6):
        member_id = owner_id if i % 2 == 0 else opp["member_id"]
        await ws_dispatch(app, room_id, member_id, "game_move", {"game_id": game_id, "column": 0})

    next_member_id = owner_id if 6 % 2 == 0 else opp["member_id"]
    try:
        await ws_dispatch(app, room_id, next_member_id, "game_move", {"game_id": game_id, "column": 0})
        assert False, "dropping into a full column should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_move"


async def test_out_of_turn_move_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "column": 0})
        assert False, "O moving before X should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_your_turn"


async def test_legal_moves_reports_open_columns(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    assert states[-1]["legal_moves"] == [{"column": c} for c in range(7)]


async def test_reconnect_snapshot_round_trips_the_board(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "column": 3})

    async with app.state.db.session() as session:
        event = await games_mod.connect_snapshot_event(session, room_id, owner_id)
    assert event["type"] == "game_state"
    assert event["game_id"] == game_id
    assert event["board"][5][3] == 0
