import asyncio

from conftest import register_socket, ws_dispatch


async def _wait_for(predicate, timeout=1.0, interval=0.02):
    """Two room-wide broadcasts issued back-to-back can race fakeredis's
    pubsub delivery (see test_realtime.py/test_video_call.py for the same
    pattern) - poll instead of asserting on the very next tick."""
    elapsed = 0.0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return predicate()


async def create_room(client, name="Test Room", owner_name="Owner"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def join(client, code, name):
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": name, "over_18": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def last_system_message(client, room_id, channel_id, token):
    resp = await client.get(f"/api/rooms/{room_id}/channels/{channel_id}/messages", headers=auth(token))
    assert resp.status_code == 200, resp.text
    messages = [m for m in resp.json()["messages"] if m["kind"] == "system"]
    return messages[-1]["text"] if messages else None


async def _get_general_channel_id(client, room_id, token):
    resp = await client.get(f"/api/rooms/{room_id}", headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["channels"][0]["id"]


# 1. Challenging ---------------------------------------------------------

async def test_challenge_invites_both_players_with_the_same_game_id(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")

    owner_ws = await register_socket(app, room_id, owner_id)
    opp_ws = await register_socket(app, room_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp["member_id"]})

    owner_invites = [e for e in owner_ws.sent if e.get("type") == "game_invite"]
    opp_invites = [e for e in opp_ws.sent if e.get("type") == "game_invite"]
    assert len(owner_invites) == 1 and len(opp_invites) == 1
    assert owner_invites[0]["game_id"] == opp_invites[0]["game_id"]
    assert owner_invites[0]["challenger_name"] == "Owner"
    assert owner_invites[0]["opponent_name"] == "Opponent"


async def test_cannot_challenge_yourself(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    await register_socket(app, room_id, owner_id)

    try:
        await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": owner_id})
        assert False, "challenging yourself should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_cannot_challenge_someone_outside_the_room(client, app):
    data_a = await create_room(client, name="Room A")
    data_b = await create_room(client, name="Room B")
    room_a_id, owner_a_id = data_a["room"]["id"], data_a["member"]["member_id"]
    outsider_id = data_b["member"]["member_id"]
    await register_socket(app, room_a_id, owner_a_id)

    try:
        await ws_dispatch(app, room_a_id, owner_a_id, "challenge_to_chess", {"opponent_id": outsider_id})
        assert False, "challenging someone outside the room should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_cannot_start_a_second_game_while_one_is_pending(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp1 = await join(client, data["room"]["code"], "Opp1")
    opp2 = await join(client, data["room"]["code"], "Opp2")
    await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, opp1["member_id"])
    await register_socket(app, room_id, opp2["member_id"])

    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp1["member_id"]})
    try:
        await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp2["member_id"]})
        assert False, "a second simultaneous challenge should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "game_in_progress"


# 2. Accept / decline / cancel -------------------------------------------

async def test_accept_starts_the_game_and_posts_a_system_message(client, app):
    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)
    opp_ws = await register_socket(app, room_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp["member_id"]})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]

    await ws_dispatch(app, room_id, opp["member_id"], "accept_game", {"game_id": game_id})

    owner_states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    opp_states = [e for e in opp_ws.sent if e.get("type") == "game_state"]
    assert len(owner_states) == 1 and len(opp_states) == 1
    state = owner_states[0]
    assert state["status"] == "active"
    assert state["white_member_id"] == owner_id
    assert state["black_member_id"] == opp["member_id"]
    assert state["turn"] == "white"
    assert len(state["legal_moves"]) == 20  # every legal opening move for white

    channel_id = await _get_general_channel_id(client, room_id, owner_token)
    text = await last_system_message(client, room_id, channel_id, owner_token)
    assert "Owner" in text and "Opponent" in text and "chess" in text.lower()


async def test_only_the_invited_opponent_can_accept(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    owner_ws = await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, opp["member_id"])
    await register_socket(app, room_id, bystander["member_id"])

    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp["member_id"]})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]

    try:
        await ws_dispatch(app, room_id, bystander["member_id"], "accept_game", {"game_id": game_id})
        assert False, "a non-opponent accepting should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"


async def test_decline_notifies_the_challenger_and_frees_both_players(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    opp2 = await join(client, data["room"]["code"], "Opponent2")
    owner_ws = await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, opp["member_id"])
    await register_socket(app, room_id, opp2["member_id"])

    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp["member_id"]})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]

    await ws_dispatch(app, room_id, opp["member_id"], "decline_game", {"game_id": game_id})

    declines = [e for e in owner_ws.sent if e.get("type") == "game_declined"]
    assert len(declines) == 1 and declines[0]["game_id"] == game_id

    # Declined frees the challenger up to start a new one.
    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp2["member_id"]})
    assert len([e for e in owner_ws.sent if e.get("type") == "game_invite"]) == 2


async def test_cancel_notifies_the_opponent(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)
    opp_ws = await register_socket(app, room_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp["member_id"]})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]

    await ws_dispatch(app, room_id, owner_id, "cancel_game", {"game_id": game_id})

    cancels = [e for e in opp_ws.sent if e.get("type") == "game_cancelled"]
    assert len(cancels) == 1 and cancels[0]["game_id"] == game_id


# 3. Moves and turn enforcement -------------------------------------------

async def _start_game(app, room_id, owner_id, opp_id):
    owner_ws = await register_socket(app, room_id, owner_id)
    opp_ws = await register_socket(app, room_id, opp_id)
    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp_id})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]
    await ws_dispatch(app, room_id, opp_id, "accept_game", {"game_id": game_id})
    return game_id, owner_ws, opp_ws


async def test_black_cannot_move_before_white(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(
            app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "from": "e7", "to": "e5"}
        )
        assert False, "black moving before white should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_your_turn"


async def test_illegal_move_is_rejected(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    try:
        await ws_dispatch(
            app, room_id, owner_id, "game_move", {"game_id": game_id, "from": "e2", "to": "e5"}
        )
        assert False, "a pawn jumping to e5 should be illegal"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_move"


async def test_legal_move_flips_turn_and_updates_legal_moves(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, opp_ws = await _start_game(app, room_id, owner_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": "e2", "to": "e4"})

    states = [e for e in owner_ws.sent if e.get("type") == "game_state"]
    latest = states[-1]
    assert latest["turn"] == "black"
    assert latest["moves"] == ["e2e4"]
    assert latest["last_move"] == "e2e4"
    assert len(latest["legal_moves"]) == 20  # every legal reply for black
    assert latest["board_fen"] == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"

    # Both players see the same state.
    opp_latest = [e for e in opp_ws.sent if e.get("type") == "game_state"][-1]
    assert opp_latest["moves"] == ["e2e4"]


async def test_cannot_move_a_piece_that_isnt_yours(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await register_socket(app, room_id, bystander["member_id"])

    try:
        await ws_dispatch(
            app, room_id, bystander["member_id"], "game_move", {"game_id": game_id, "from": "e2", "to": "e4"}
        )
        assert False, "a non-player moving should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"


# 4. Game-over detection ---------------------------------------------------

async def test_checkmate_ends_the_game_and_announces_the_winner(client, app):
    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # Fool's Mate: fastest checkmate in chess - black wins on move 2.
    moves = [(owner_id, "f2", "f3"), (opp["member_id"], "e7", "e5"), (owner_id, "g2", "g4")]
    for member_id, frm, to in moves:
        await ws_dispatch(app, room_id, member_id, "game_move", {"game_id": game_id, "from": frm, "to": to})
    await ws_dispatch(
        app, room_id, opp["member_id"], "game_move",
        {"game_id": game_id, "from": "d8", "to": "h4"},
    )

    final = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    assert final["game_over"] is True
    assert final["status"] == "finished"
    assert final["result"] == "black"
    assert final["termination"] == "checkmate"

    channel_id = await _get_general_channel_id(client, room_id, owner_token)
    text = await last_system_message(client, room_id, channel_id, owner_token)
    assert "checkmate" in text.lower() and "Opponent" in text


async def test_resign_ends_the_game_in_the_opponents_favor(client, app):
    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "resign_game", {"game_id": game_id})

    final = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    assert final["game_over"] is True
    assert final["result"] == "black"
    assert final["termination"] == "resignation"

    channel_id = await _get_general_channel_id(client, room_id, owner_token)
    text = await last_system_message(client, room_id, channel_id, owner_token)
    assert "resigned" in text.lower()


async def test_finished_game_frees_both_players_to_start_a_new_one(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    opp2 = await join(client, data["room"]["code"], "Opponent2")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await register_socket(app, room_id, opp2["member_id"])

    await ws_dispatch(app, room_id, owner_id, "resign_game", {"game_id": game_id})
    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp2["member_id"]})

    # One invite from _start_game's initial challenge, one from this new one.
    assert len([e for e in owner_ws.sent if e.get("type") == "game_invite"]) == 2


# 5. Reconnect snapshot -----------------------------------------------------

async def test_connect_snapshot_resends_a_pending_invite(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    owner_ws = await register_socket(app, room_id, owner_id)
    await register_socket(app, room_id, opp["member_id"])

    await ws_dispatch(app, room_id, owner_id, "challenge_to_chess", {"opponent_id": opp["member_id"]})
    game_id = [e for e in owner_ws.sent if e.get("type") == "game_invite"][0]["game_id"]

    async with app.state.db.session() as session:
        event = await games_mod.connect_snapshot_event(session, room_id, opp["member_id"])
    assert event["type"] == "game_invite"
    assert event["game_id"] == game_id


async def test_connect_snapshot_resends_an_active_games_state(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    async with app.state.db.session() as session:
        event = await games_mod.connect_snapshot_event(session, room_id, owner_id)
    assert event["type"] == "game_state"
    assert event["game_id"] == game_id
    assert event["status"] == "active"


async def test_connect_snapshot_is_none_with_no_games(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]

    async with app.state.db.session() as session:
        event = await games_mod.connect_snapshot_event(session, room_id, owner_id)
    assert event is None


# 6. Room deletion cleans up games -------------------------------------------

async def test_deleting_a_room_removes_its_games(client, app):
    from sqlalchemy import select

    from app.models import Game

    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    opp = await join(client, data["room"]["code"], "Opponent")
    await _start_game(app, room_id, owner_id, opp["member_id"])

    resp = await client.delete(f"/api/rooms/{room_id}", headers=auth(owner_token))
    assert resp.status_code == 200, resp.text

    async with app.state.db.session() as session:
        result = await session.execute(select(Game).where(Game.room_id == room_id))
        assert result.scalars().first() is None


# 7. Room-wide "live now" broadcasts -----------------------------------------

async def test_accept_broadcasts_game_live_to_a_bystander_not_just_the_players(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])

    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    live = [e for e in bystander_ws.sent if e.get("type") == "game_live"]
    assert len(live) == 1
    assert live[0]["game_id"] == game_id
    assert live[0]["white_name"] == "Owner"
    assert live[0]["black_name"] == "Opponent"


async def test_live_games_for_room_excludes_the_players_own_game(client, app):
    from app import games as games_mod

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    await _start_game(app, room_id, owner_id, opp["member_id"])

    async with app.state.db.session() as session:
        for_owner = await games_mod.live_games_for_room(session, room_id, exclude_member_id=owner_id)
        for_bystander = await games_mod.live_games_for_room(session, room_id, exclude_member_id="nobody")
    assert for_owner == []
    assert len(for_bystander) == 1


async def test_checkmate_and_resign_broadcast_game_live_ended(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])

    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, owner_id, "resign_game", {"game_id": game_id})

    ended = [e for e in bystander_ws.sent if e.get("type") == "game_live_ended"]
    assert len(ended) == 1 and ended[0]["game_id"] == game_id


# 8. Spectating ---------------------------------------------------------------

async def test_watching_sends_current_state_immediately(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])

    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": "e2", "to": "e4"})

    await ws_dispatch(app, room_id, bystander["member_id"], "watch_game", {"game_id": game_id})

    states = [e for e in bystander_ws.sent if e.get("type") == "game_state"]
    assert len(states) == 1
    assert states[0]["moves"] == ["e2e4"]


async def test_watcher_receives_subsequent_moves_but_cannot_play(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])

    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, bystander["member_id"], "watch_game", {"game_id": game_id})

    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": "e2", "to": "e4"})

    states = [e for e in bystander_ws.sent if e.get("type") == "game_state"]
    assert states[-1]["moves"] == ["e2e4"]

    try:
        await ws_dispatch(
            app, room_id, bystander["member_id"], "game_move",
            {"game_id": game_id, "from": "e7", "to": "e5"},
        )
        assert False, "a spectator playing a move should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"


async def test_unwatch_stops_future_state_updates(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])

    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, bystander["member_id"], "watch_game", {"game_id": game_id})
    await ws_dispatch(app, room_id, bystander["member_id"], "unwatch_game", {"game_id": game_id})

    before = len([e for e in bystander_ws.sent if e.get("type") == "game_state"])
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": "e2", "to": "e4"})
    after = len([e for e in bystander_ws.sent if e.get("type") == "game_state"])
    assert after == before


async def test_watcher_count_broadcasts_on_watch_and_unwatch(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    await register_socket(app, room_id, bystander["member_id"])

    # _start_game registers its own fresh socket for owner_id internally -
    # any register_socket() called beforehand for the same member would be
    # silently overwritten (Hub.register replaces, not appends), so the
    # socket to assert on has to be the one _start_game actually returns.
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, bystander["member_id"], "watch_game", {"game_id": game_id})

    def counts():
        return [e for e in owner_ws.sent if e.get("type") == "game_watchers"]

    assert await _wait_for(lambda: counts() and counts()[-1]["count"] == 1)

    await ws_dispatch(app, room_id, bystander["member_id"], "unwatch_game", {"game_id": game_id})
    assert await _wait_for(lambda: counts()[-1]["count"] == 0)


async def test_cleanup_watchers_on_disconnect_clears_count(client, app):
    from app import realtime

    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    bystander = await join(client, data["room"]["code"], "Bystander")
    await register_socket(app, room_id, bystander["member_id"])

    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, bystander["member_id"], "watch_game", {"game_id": game_id})

    await realtime.cleanup_watchers_on_disconnect(app.state.redis, app.state.hub, room_id, bystander["member_id"])

    def counts():
        return [e for e in owner_ws.sent if e.get("type") == "game_watchers"]

    assert await _wait_for(lambda: counts() and counts()[-1]["count"] == 0)


# 9. Capture flag (for the frontend's sound effect) --------------------------

async def test_last_move_was_capture_flag(client, app):
    data = await create_room(client)
    room_id, owner_id = data["room"]["id"], data["member"]["member_id"]
    opp = await join(client, data["room"]["code"], "Opponent")
    game_id, owner_ws, _ = await _start_game(app, room_id, owner_id, opp["member_id"])

    # Non-capturing opening move.
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": "e2", "to": "e4"})
    state = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    assert state["last_move_was_capture"] is False

    # d7-d5, then e4xd5 - a real capture.
    await ws_dispatch(app, room_id, opp["member_id"], "game_move", {"game_id": game_id, "from": "d7", "to": "d5"})
    await ws_dispatch(app, room_id, owner_id, "game_move", {"game_id": game_id, "from": "e4", "to": "d5"})
    state = [e for e in owner_ws.sent if e.get("type") == "game_state"][-1]
    assert state["last_move_was_capture"] is True


# 10. Leaderboard --------------------------------------------------------------

async def test_leaderboard_aggregates_wins_losses_and_draws(client, app):
    data = await create_room(client)
    room_id, owner_id, owner_token = data["room"]["id"], data["member"]["member_id"], data["session_token"]
    opp = await join(client, data["room"]["code"], "Opponent")

    # Game 1: owner (white) resigns - opponent (black) wins.
    game_id, _, _ = await _start_game(app, room_id, owner_id, opp["member_id"])
    await ws_dispatch(app, room_id, owner_id, "resign_game", {"game_id": game_id})

    # Game 2: opponent (white this time) resigns - owner (black) wins.
    game_id2, _, _ = await _start_game(app, room_id, opp["member_id"], owner_id)
    await ws_dispatch(app, room_id, opp["member_id"], "resign_game", {"game_id": game_id2})

    resp = await client.get(f"/api/rooms/{room_id}/games/leaderboard", headers=auth(owner_token))
    assert resp.status_code == 200, resp.text
    rows = {r["member_id"]: r for r in resp.json()["rows"]}

    assert rows[owner_id]["wins"] == 1
    assert rows[owner_id]["losses"] == 1
    assert rows[opp["member_id"]]["wins"] == 1
    assert rows[opp["member_id"]]["losses"] == 1
    assert rows[owner_id]["games_played"] == 2
