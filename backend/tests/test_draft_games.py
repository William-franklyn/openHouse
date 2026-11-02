import asyncio
import random

from conftest import register_socket, ws_dispatch

from app import realtime
from app.party_engines import draft_engine


async def _wait_for(predicate, timeout=1.0, interval=0.02):
    """Same polling pattern as test_party_games.py - two room-wide
    broadcasts issued back-to-back can race fakeredis's pubsub delivery."""
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
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "draft"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    return party_game_id, host_ws


async def _start_two_player_draft(app, room_id, host_id, p2_id):
    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    p2_ws = await register_socket(app, room_id, p2_id)
    await ws_dispatch(app, room_id, p2_id, "join_party_game", {"party_game_id": party_game_id})
    random.seed(42)
    await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})
    return party_game_id, host_ws, p2_ws


async def test_starting_draft_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "draft"})

    assert _party_states(host_ws)[-1]["status"] == "lobby"
    assert _party_states(bystander_ws)[-1]["status"] == "lobby"


async def test_default_total_rounds_is_21_for_a_fresh_draft_game(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_draft(app, room_id, host_id, p2["member_id"])

    state = _party_states(host_ws)[-1]
    assert state["total_rounds"] == 21
    assert state["phase"] == "picking"


async def test_each_player_sees_only_their_own_hand(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_draft(app, room_id, host_id, p2["member_id"])

    host_state = _party_states(host_ws)[-1]
    p2_state = _party_states(p2_ws)[-1]
    assert len(host_state["my_hand"]) == 7
    assert len(p2_state["my_hand"]) == 7
    # Neither payload carries the other player's hand under any key.
    assert all("hand" not in str(k).lower() or k == "my_hand" or k == "hand_size" for k in host_state.keys())


async def test_picks_stay_hidden_until_reveal_then_become_public(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_draft(app, room_id, host_id, p2["member_id"])

    host_state = _party_states(host_ws)[-1]
    host_card_id = host_state["my_hand"][0]["id"]
    await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "card_id": host_card_id})

    p2_state_after_host_picked = _party_states(p2_ws)[-1]
    assert host_id in p2_state_after_host_picked["picked_member_ids"]
    assert "revealed_picks" not in p2_state_after_host_picked

    p2_state = _party_states(p2_ws)[-1]
    p2_card_id = p2_state["my_hand"][0]["id"]
    await ws_dispatch(app, room_id, p2["member_id"], "party_action", {"party_game_id": party_game_id, "card_id": p2_card_id})

    final_p2_state = _party_states(p2_ws)[-1]
    assert final_p2_state["phase"] == "reveal"
    assert set(final_p2_state["revealed_picks"].keys()) == {host_id, p2["member_id"]}


async def test_picking_a_card_not_in_hand_is_rejected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_draft(app, room_id, host_id, p2["member_id"])

    try:
        await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "card_id": "bogus"})
        assert False, "picking a card not in hand should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_a_full_scoring_round_completes_and_awards_points(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_draft(app, room_id, host_id, p2["member_id"])

    for _ in range(7):
        assert await _wait_for(lambda: _party_states(host_ws)[-1]["phase"] == "picking", timeout=2.0)
        state = _party_states(host_ws)[-1]
        host_card = state["my_hand"][0]["id"]
        p2_card = _party_states(p2_ws)[-1]["my_hand"][0]["id"]
        await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "card_id": host_card})
        await ws_dispatch(app, room_id, p2["member_id"], "party_action", {"party_game_id": party_game_id, "card_id": p2_card})

    final = _party_states(host_ws)[-1]
    assert final["phase"] == "scoring_round_over"
    assert set(final["round_results"].keys()) == {host_id, p2["member_id"]}
    assert len(final["round_results"][host_id]["collected"]) == 7
    assert all(row["score"] > 0 for row in final["scoreboard"])


async def test_real_timer_auto_picks_for_a_straggler_and_advances(client, app, monkeypatch):
    monkeypatch.setattr(draft_engine, "PICK_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_draft(app, room_id, host_id, p2["member_id"])

    # Host picks, P2 never does - only the real timer can resolve this pick.
    state = _party_states(host_ws)[-1]
    host_card = state["my_hand"][0]["id"]
    await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "card_id": host_card})

    assert await _wait_for(lambda: _party_states(host_ws)[-1]["pick_in_round"] == 1, timeout=2.0)


async def test_skip_round_resolves_the_pick_immediately(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_draft(app, room_id, host_id, p2["member_id"])

    await ws_dispatch(app, room_id, host_id, "skip_party_round", {"party_game_id": party_game_id})
    state = _party_states(host_ws)[-1]
    assert state["phase"] == "reveal"
    assert state["pick_in_round"] == 0  # the just-finished pick, not yet advanced


async def test_full_game_finishes_after_three_scoring_rounds(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)

    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    party_game_id, host_ws, p2_ws = await _start_two_player_draft(app, room_id, host_id, p2["member_id"])

    safety = 0
    while _party_states(host_ws)[-1]["status"] != "finished" and safety < 21:
        safety += 1
        assert await _wait_for(
            lambda: _party_states(host_ws)[-1]["phase"] == "picking"
            or _party_states(host_ws)[-1]["status"] == "finished",
            timeout=2.0,
        )
        state = _party_states(host_ws)[-1]
        if state["status"] == "finished":
            break
        host_card = state["my_hand"][0]["id"]
        # fakeredis pubsub delivery to each socket's listener task is not
        # instantaneous - p2_ws may still be rendering the previous round,
        # so wait for ITS OWN view to agree it's "picking" before trusting
        # its my_hand (same race documented in test_uno_games.py).
        assert await _wait_for(lambda: _party_states(p2_ws)[-1].get("phase") == "picking", timeout=2.0)
        p2_card = _party_states(p2_ws)[-1]["my_hand"][0]["id"]
        await ws_dispatch(app, room_id, host_id, "party_action", {"party_game_id": party_game_id, "card_id": host_card})
        await ws_dispatch(app, room_id, p2["member_id"], "party_action", {"party_game_id": party_game_id, "card_id": p2_card})

    final = _party_states(host_ws)[-1]
    assert final["status"] == "finished"
    assert final["round_index"] == 20

    messages = [e for e in host_ws.sent if e.get("type") == "message" and e.get("kind") == "system"]
    assert any("Draft" in (m.get("text") or "") for m in messages)
