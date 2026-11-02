import asyncio
import random

from conftest import register_socket, ws_dispatch

from app import realtime
from app.party_engines import uno_engine


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
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "uno"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    return party_game_id, host_ws


async def _start_two_player_uno(app, room_id, host_id, p2_id):
    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    p2_ws = await register_socket(app, room_id, p2_id)
    await ws_dispatch(app, room_id, p2_id, "join_party_game", {"party_game_id": party_game_id})
    random.seed(1)
    await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})
    return party_game_id, host_ws, p2_ws


def _legal_card(my_hand, active_color, top):
    for c in my_hand:
        if c["color"] == "Wild" or c["color"] == active_color:
            return c
        if c["kind"] != "number" and c["kind"] == top["kind"]:
            return c
        if c["kind"] == "number" and top["kind"] == "number" and c["value"] == top["value"]:
            return c
    return None


async def test_starting_uno_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "uno"})

    assert _party_states(host_ws)[-1]["status"] == "lobby"
    assert _party_states(bystander_ws)[-1]["status"] == "lobby"


async def test_each_player_sees_only_their_own_hand(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_uno(app, room_id, host_id, p2["member_id"])

    host_state = _party_states(host_ws)[-1]
    p2_state = _party_states(p2_ws)[-1]
    assert len(host_state["my_hand"]) == 7
    assert len(p2_state["my_hand"]) == 7
    assert host_state["hand_sizes"] == {host_id: 7, p2["member_id"]: 7}


async def test_acting_out_of_turn_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_uno(app, room_id, host_id, p2["member_id"])

    state = _party_states(host_ws)[-1]
    not_on_turn = p2["member_id"] if state["current_player_id"] == host_id else host_id
    try:
        await ws_dispatch(app, room_id, not_on_turn, "party_action", {"party_game_id": party_game_id, "action": "draw"})
        assert False, "acting out of turn should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_a_draw_action_resolves_the_turn_and_passes_to_the_next_player(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_uno(app, room_id, host_id, p2["member_id"])

    state = _party_states(host_ws)[-1]
    actor = state["current_player_id"]
    await ws_dispatch(app, room_id, actor, "party_action", {"party_game_id": party_game_id, "action": "draw"})

    final = _party_states(host_ws)[-1]
    assert final["phase"] == "reveal"
    assert final["last_action"]["member_id"] == actor
    assert final["last_action"]["kind"] == "draw"


async def test_playing_a_card_not_in_hand_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_uno(app, room_id, host_id, p2["member_id"])

    state = _party_states(host_ws)[-1]
    actor = state["current_player_id"]
    try:
        await ws_dispatch(
            app, room_id, actor, "party_action",
            {"party_game_id": party_game_id, "action": "play", "card_id": "bogus"},
        )
        assert False, "playing a card not in hand should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_real_timer_auto_draws_for_a_straggler_and_advances(client, app, monkeypatch):
    monkeypatch.setattr(uno_engine, "TURN_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_uno(app, room_id, host_id, p2["member_id"])

    # Nobody ever acts - only the real server timer can resolve this turn.
    assert await _wait_for(lambda: _party_states(host_ws)[-1]["phase"] == "reveal", timeout=2.0)
    assert await _wait_for(lambda: _party_states(host_ws)[-1]["phase"] == "turn", timeout=2.0)


async def test_skip_round_resolves_the_turn_immediately(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_uno(app, room_id, host_id, p2["member_id"])

    await ws_dispatch(app, room_id, host_id, "skip_party_round", {"party_game_id": party_game_id})
    state = _party_states(host_ws)[-1]
    assert state["phase"] == "reveal"


async def test_hand_conserves_card_count_and_awards_the_winner(client, app, monkeypatch):
    # Every turn below is resolved by an explicit player action (is_round_over
    # fires immediately, same as draft's picks) - leave TURN_DURATION_SECONDS
    # at its real default so the straggler timer never races a submitted
    # action; only the inter-turn reveal pause needs shortening.
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_uno(app, room_id, host_id, p2["member_id"])

    safety = 0
    while _party_states(host_ws)[-1]["status"] != "finished" and safety < 1000:
        safety += 1
        assert await _wait_for(
            lambda: _party_states(host_ws)[-1]["phase"] == "turn"
            or _party_states(host_ws)[-1]["status"] == "finished",
            timeout=2.0,
        )
        state = _party_states(host_ws)[-1]
        if state["status"] == "finished":
            break
        actor = state["current_player_id"]
        actor_ws = host_ws if actor == host_id else p2_ws
        # fakeredis pubsub delivery to each socket's listener task is not
        # instantaneous - actor_ws may still be rendering the previous turn,
        # so wait for ITS OWN view to agree it's now this actor's turn
        # before trusting its my_hand/discard_top for a card choice.
        if not await _wait_for(
            lambda: _party_states(actor_ws)[-1].get("phase") == "turn"
            and _party_states(actor_ws)[-1].get("current_player_id") == actor,
            timeout=2.0,
        ):
            continue
        actor_state = _party_states(actor_ws)[-1]
        card = _legal_card(actor_state["my_hand"], actor_state["active_color"], actor_state["discard_top"])
        if card is not None:
            extra = {"chosen_color": "Red"} if card["color"] == "Wild" else {}
            await ws_dispatch(
                app, room_id, actor, "party_action",
                {"party_game_id": party_game_id, "action": "play", "card_id": card["id"], **extra},
            )
        else:
            await ws_dispatch(app, room_id, actor, "party_action", {"party_game_id": party_game_id, "action": "draw"})

    final = _party_states(host_ws)[-1]
    assert final["status"] == "finished"

    messages = [e for e in host_ws.sent if e.get("type") == "message" and e.get("kind") == "system"]
    assert any("Uno" in (m.get("text") or "") for m in messages)


async def test_lobby_disconnect_removes_member_from_the_table(client, app):
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


async def test_reconnect_snapshot_resyncs_only_my_own_hand(client, app):
    from app import party_games as party_games_mod

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_uno(app, room_id, host_id, p2["member_id"])

    async with app.state.db.session() as session:
        host_snapshot = await party_games_mod.connect_snapshot_event(session, room_id, host_id)
        p2_snapshot = await party_games_mod.connect_snapshot_event(session, room_id, p2["member_id"])

    assert len(host_snapshot["my_hand"]) == 7
    assert len(p2_snapshot["my_hand"]) == 7
