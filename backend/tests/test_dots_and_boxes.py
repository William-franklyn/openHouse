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
    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp_id, "kind": "dots_and_boxes"})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]
    await ws_dispatch(app, room_id, opp_id, "accept_game", {"game_id": game_id})
    return game_id, owner_ws, opp_ws


async def test_challenge_creates_a_dots_and_boxes_game(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)

    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp["member_id"], "kind": "dots_and_boxes"})

    invites = [e for e in owner_ws.sent if e.get("type") == "game_invite"]
    assert len(invites) == 1
    assert invites[0]["kind"] == "dots_and_boxes"


async def test_completing_a_box_lets_the_same_player_move_again(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # Owner (seat0) draws 3 sides of box (0,0) on their own turns, with
    # opponent's turns spent on unrelated, far-away edges that don't
    # complete anything - turns still strictly alternate since none of
    # these moves claim a box yet.
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "edge_type": "h", "row": 0, "col": 0})
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "edge_type": "h", "row": 4, "col": 3})
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "edge_type": "v", "row": 0, "col": 0})
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "edge_type": "h", "row": 4, "col": 2})
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "edge_type": "h", "row": 1, "col": 0})
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "edge_type": "v", "row": 3, "col": 4})
    # Owner draws the 4th side - should complete the box and go again.
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "edge_type": "v", "row": 0, "col": 1})

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    last = states[-1]
    assert last["boxes"][0][0] == 0
    assert last["turn"] == "white"  # still the owner's turn after claiming


async def test_redrawing_a_line_is_illegal(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "edge_type": "h", "row": 0, "col": 0})
    try:
        await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "edge_type": "h", "row": 0, "col": 0})
        assert False, "redrawing an existing line should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_move"


async def test_out_of_turn_move_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "edge_type": "h", "row": 0, "col": 0})
        assert False, "opponent moving before owner should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_your_turn"


async def test_reconnect_snapshot_round_trips_the_board(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "edge_type": "h", "row": 0, "col": 0})

    async with app.state.db.session() as session:
        event = await games_mod.connect_snapshot_event(session, room_id, owner_id)
    assert event["type"] == "game_state"
    assert event["game_id"] == game_id
    assert event["h_edges"][0][0] is True
