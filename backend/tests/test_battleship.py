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
    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp_id, "kind": "battleship"})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]
    await ws_dispatch(app, room_id, opp_id, "accept_game", {"game_id": game_id})
    return game_id, owner_ws, opp_ws


def _ship_cells(grid):
    return {(r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v == "ship"}


async def test_challenge_creates_a_battleship_game(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)

    await ws_dispatch(app, room_id, owner_id, "challenge_game", {"opponent_id": opp["member_id"], "kind": "battleship"})

    invites = [e for e in owner_ws.sent if e.get("type") == "game_invite"]
    assert len(invites) == 1
    assert invites[0]["kind"] == "battleship"


async def test_each_player_sees_their_own_ships_but_not_the_opponents(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    _, owner_ws, opp_ws = await _start_game(app, room_id, owner_id, opp["member_id"])

    owner_state = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    opp_state = [e for e in opp_ws.sent if e.get("type") == "game_state"][-1]

    assert owner_state["my_seat"] == 0
    assert opp_state["my_seat"] == 1

    # Owner's own fleet (white_grid) shows real ship cells to the owner...
    owner_own_ships = _ship_cells(owner_state["white_grid"])
    assert len(owner_own_ships) == 17
    # ...but the SAME fleet is completely invisible on the opponent's copy
    # of white_grid (the critical hidden-information check).
    opp_sees_of_white = _ship_cells(opp_state["white_grid"])
    assert opp_sees_of_white == set()

    # And symmetrically for black's fleet.
    opp_own_ships = _ship_cells(opp_state["black_grid"])
    assert len(opp_own_ships) == 17
    owner_sees_of_black = _ship_cells(owner_state["black_grid"])
    assert owner_sees_of_black == set()


async def test_a_spectator_sees_neither_players_ships(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    spectator = await join(client, data["room"]["code"], "Watcher")
    game_id, owner_ws, opp_ws = await _start_game(app, room_id, owner_id, opp["member_id"])
    spec_ws = await register_socket(app, room_id, spectator["member_id"])

    await ws_dispatch(app, room_id, spectator["member_id"], "watch_game", {"game_id": game_id})

    spec_state = [e for e in spec_ws.sent if e.get("type") == "game_state"][-1]
    assert spec_state["my_seat"] is None
    assert _ship_cells(spec_state["white_grid"]) == set()
    assert _ship_cells(spec_state["black_grid"]) == set()


async def test_a_hit_is_visible_to_everyone_once_fired(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, opp_ws = await _start_game(app, room_id, owner_id, opp["member_id"])

    # Owner fires at every cell of black's board until a hit lands - the
    # fleet is randomly placed, so sweep rather than assume a coordinate.
    owner_state = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    hit_cell = None
    opp_shot_cells = iter((r, c) for r in range(10) for c in range(9, -1, -1))
    for r in range(10):
        for c in range(10):
            await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "row": r, "col": c})
            latest = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
            if latest["black_grid"][r][c] == "hit":
                hit_cell = (r, c)
                break
            # Need the opponent to move back in between (strict turn
            # alternation) - each shot must land on a cell the opponent
            # hasn't fired at yet, but the content doesn't matter here.
            orow, ocol = next(opp_shot_cells)
            await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "row": orow, "col": ocol})
        if hit_cell:
            break

    assert hit_cell is not None, "expected at least one hit while sweeping the whole board"
    r, c = hit_cell
    opp_state = [e for e in opp_ws.sent if e.get("type") == "game_state"][-1]
    # Owner (seat 0/white) fired at black's board, so the hit lands on
    # black's own fleet - opp (seat 1/black) sees it on their OWN grid.
    assert opp_state["black_grid"][r][c] == "hit"


async def test_firing_at_the_same_cell_twice_is_illegal(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "row": 3, "col": 3})
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "row": 0, "col": 0})
    try:
        await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "row": 3, "col": 3})
        assert False, "firing at an already-shot cell should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_move"


async def test_out_of_turn_move_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "row": 1, "col": 1})
        assert False, "opponent moving before owner should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_your_turn"


async def test_reconnect_snapshot_shows_my_own_ships_not_the_opponents(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    async with app.state.db.session() as session:
        owner_snapshot = await games_mod.connect_snapshot_event(session, room_id, owner_id)
        opp_snapshot = await games_mod.connect_snapshot_event(session, room_id, opp["member_id"])

    assert owner_snapshot["my_seat"] == 0
    assert len(_ship_cells(owner_snapshot["white_grid"])) == 17
    assert opp_snapshot["my_seat"] == 1
    # The reconnecting owner's snapshot must not leak black's ships either.
    assert _ship_cells(owner_snapshot["black_grid"]) == set()
