import random

from conftest import register_socket, ws_dispatch


async def create_room(client, name="Test Room", owner_name="Host"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def join(client, code, name):
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": name, "over_18": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _card_states(ws):
    return [e for e in ws.sent if e.get("type") == "card_state"]


async def _start_lobby(app, room_id, host_id, starting_chips=1000):
    host_ws = await register_socket(app, room_id, host_id)
    await ws_dispatch(app, room_id, host_id, "start_card_game", {"kind": "poker", "starting_chips": starting_chips})
    card_game_id = _card_states(host_ws)[-1]["card_game_id"]
    return card_game_id, host_ws


async def _start_two_player_table(app, room_id, host_id, p2_id, starting_chips=1000):
    card_game_id, host_ws = await _start_lobby(app, room_id, host_id, starting_chips)
    p2_ws = await register_socket(app, room_id, p2_id)
    await ws_dispatch(app, room_id, p2_id, "join_card_game", {"card_game_id": card_game_id})
    random.seed(42)
    await ws_dispatch(app, room_id, host_id, "begin_card_game", {"card_game_id": card_game_id})
    return card_game_id, host_ws, p2_ws


async def test_starting_poker_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_card_game", {"kind": "poker"})

    assert _card_states(host_ws)[-1]["status"] == "lobby"
    assert _card_states(bystander_ws)[-1]["status"] == "lobby"


async def test_joining_after_begin_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    late = await join(client, data["room"]["code"], "Late")
    await register_socket(app, room_id, late["member_id"])

    card_game_id, _, _ = await _start_two_player_table(app, room_id, host_id, p2["member_id"])

    try:
        await ws_dispatch(app, room_id, late["member_id"], "join_card_game", {"card_game_id": card_game_id})
        assert False, "joining a locked table should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_starting_below_min_participants_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    card_game_id, _ = await _start_lobby(app, room_id, host_id)

    try:
        await ws_dispatch(app, room_id, host_id, "begin_card_game", {"card_game_id": card_game_id})
        assert False, "starting with only the host should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_each_player_sees_only_their_own_hole_cards(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    card_game_id, host_ws, p2_ws = await _start_two_player_table(app, room_id, host_id, p2["member_id"])

    host_state = _card_states(host_ws)[-1]
    p2_state = _card_states(p2_ws)[-1]

    host_seat = next(s for s in host_state["seats"] if s["member_id"] == host_id)
    host_other_seat = next(s for s in host_state["seats"] if s["member_id"] == p2["member_id"])
    assert host_seat["hole_cards"] is not None
    assert host_other_seat["hole_cards"] is None

    p2_seat = next(s for s in p2_state["seats"] if s["member_id"] == p2["member_id"])
    p2_other_seat = next(s for s in p2_state["seats"] if s["member_id"] == host_id)
    assert p2_seat["hole_cards"] is not None
    assert p2_other_seat["hole_cards"] is None


async def test_acting_out_of_turn_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    card_game_id, host_ws, p2_ws = await _start_two_player_table(app, room_id, host_id, p2["member_id"])

    state = _card_states(host_ws)[-1]
    acting_player = state["action_on"]
    other_player = p2["member_id"] if acting_player == host_id else host_id

    try:
        await ws_dispatch(app, room_id, other_player, "card_action", {"card_game_id": card_game_id, "action": "fold"})
        assert False, "acting out of turn should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_fold_to_win_ends_the_hand_without_a_showdown(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    card_game_id, host_ws, p2_ws = await _start_two_player_table(app, room_id, host_id, p2["member_id"])

    state = _card_states(host_ws)[-1]
    acting_player = state["action_on"]
    await ws_dispatch(app, room_id, acting_player, "card_action", {"card_game_id": card_game_id, "action": "fold"})

    final = _card_states(host_ws)[-1]
    assert final["phase"] == "hand_over"
    chips_before = 1000
    total_after = sum(s["chips"] for s in final["seats"])
    assert total_after == chips_before * 2  # chips conserved, nothing vanished


async def test_full_hand_to_showdown_posts_a_winner_message_and_conserves_chips(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    card_game_id, host_ws, p2_ws = await _start_two_player_table(app, room_id, host_id, p2["member_id"])

    safety = 0
    while _card_states(host_ws)[-1]["phase"] not in ("hand_over", "showdown") and safety < 40:
        safety += 1
        state = _card_states(host_ws)[-1]
        actor = state["action_on"]
        legal = state["my_legal_actions"] if actor == host_id else _card_states(p2_ws)[-1]["my_legal_actions"]
        kind = "check" if "check" in legal["actions"] else "call"
        await ws_dispatch(app, room_id, actor, "card_action", {"card_game_id": card_game_id, "action": kind})

    final = _card_states(host_ws)[-1]
    total_chips = sum(s["chips"] for s in final["seats"])
    assert total_chips == 2000

    messages = [e for e in host_ws.sent if e.get("type") == "message" and e.get("kind") == "system"]
    assert any("Poker" in (m.get("text") or "") for m in messages)


async def test_start_next_hand_requires_the_current_hand_to_be_over(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    card_game_id, host_ws, p2_ws = await _start_two_player_table(app, room_id, host_id, p2["member_id"])

    try:
        await ws_dispatch(app, room_id, host_id, "start_next_hand", {"card_game_id": card_game_id})
        assert False, "starting the next hand mid-hand should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"

    state = _card_states(host_ws)[-1]
    acting_player = state["action_on"]
    await ws_dispatch(app, room_id, acting_player, "card_action", {"card_game_id": card_game_id, "action": "fold"})
    assert _card_states(host_ws)[-1]["phase"] == "hand_over"

    other = p2["member_id"] if acting_player == host_id else host_id
    await ws_dispatch(app, room_id, other, "start_next_hand", {"card_game_id": card_game_id})
    assert _card_states(host_ws)[-1]["hand_number"] == 2


async def test_elimination_ends_the_whole_table_when_one_player_busts(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    card_game_id, host_ws, p2_ws = await _start_two_player_table(
        app, room_id, host_id, p2["member_id"], starting_chips=100
    )

    # Both players shove all-in preflop so one hand decides the whole table.
    state = _card_states(host_ws)[-1]
    first = state["action_on"]
    legal = state["my_legal_actions"]
    await ws_dispatch(
        app, room_id, first, "card_action", {"card_game_id": card_game_id, "action": "raise", "to": legal["max_raise_to"]}
    )
    second = p2["member_id"] if first == host_id else host_id
    await ws_dispatch(app, room_id, second, "card_action", {"card_game_id": card_game_id, "action": "call"})

    final = _card_states(host_ws)[-1]
    assert final["status"] == "finished"
    total_chips = sum(s["chips"] for s in final["seats"])
    assert total_chips == 200
    assert sorted(s["chips"] for s in final["seats"]) == [0, 200]

    messages = [e for e in host_ws.sent if e.get("type") == "message" and e.get("kind") == "system"]
    assert any("won the whole table" in (m.get("text") or "") for m in messages)


async def test_lobby_disconnect_removes_member_from_the_table(client, app):
    from app import realtime

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    card_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    await register_socket(app, room_id, p2["member_id"])
    await ws_dispatch(app, room_id, p2["member_id"], "join_card_game", {"card_game_id": card_game_id})
    assert p2["member_id"] in _card_states(host_ws)[-1]["participant_ids"]

    async with app.state.db.session() as session:
        await realtime.cleanup_card_lobby_on_disconnect(session, app.state.settings, app.state.hub, room_id, p2["member_id"])

    assert p2["member_id"] not in _card_states(host_ws)[-1]["participant_ids"]


async def test_reconnect_snapshot_resyncs_only_my_own_hole_cards(client, app):
    from app import card_games as card_games_mod

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    card_game_id, host_ws, p2_ws = await _start_two_player_table(app, room_id, host_id, p2["member_id"])

    async with app.state.db.session() as session:
        host_snapshot = await card_games_mod.connect_snapshot_event(session, room_id, host_id)
        p2_snapshot = await card_games_mod.connect_snapshot_event(session, room_id, p2["member_id"])

    host_own = next(s for s in host_snapshot["seats"] if s["member_id"] == host_id)
    host_other = next(s for s in host_snapshot["seats"] if s["member_id"] == p2["member_id"])
    assert host_own["hole_cards"] is not None
    assert host_other["hole_cards"] is None
    p2_own = next(s for s in p2_snapshot["seats"] if s["member_id"] == p2["member_id"])
    assert p2_own["hole_cards"] is not None
