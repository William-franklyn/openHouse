import asyncio
import random

from conftest import register_socket, ws_dispatch

from app import realtime
from app.party_engines import spades_engine


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
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "spades"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    return party_game_id, host_ws


async def _start_four_player_game(app, room_id, member_ids, seed=1):
    host_id = member_ids[0]
    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    sockets = {host_id: host_ws}
    for member_id in member_ids[1:]:
        ws = await register_socket(app, room_id, member_id)
        await ws_dispatch(app, room_id, member_id, "join_party_game", {"party_game_id": party_game_id})
        sockets[member_id] = ws
    random.seed(seed)
    await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})
    return party_game_id, sockets


async def _setup_room_with_four(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    p3 = await join(client, data["room"]["code"], "P3")
    p4 = await join(client, data["room"]["code"], "P4")
    member_ids = [host_id, p2["member_id"], p3["member_id"], p4["member_id"]]
    return room_id, member_ids


async def test_starting_spades_room_broadcasts_a_lobby_to_everyone_connected(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    bystander = await join(client, data["room"]["code"], "Bystander")
    bystander_ws = await register_socket(app, room_id, bystander["member_id"])
    host_ws = await register_socket(app, room_id, host_id)

    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "spades"})

    assert _party_states(host_ws)[-1]["status"] == "lobby"
    assert _party_states(bystander_ws)[-1]["status"] == "lobby"


async def test_a_fifth_player_cannot_join_the_lobby(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    members = [host_id]
    for name in ("P2", "P3", "P4"):
        joined = await join(client, data["room"]["code"], name)
        members.append(joined["member_id"])
    p5 = await join(client, data["room"]["code"], "P5")

    party_game_id, host_ws = await _start_lobby(app, room_id, host_id)
    for member_id in members[1:]:
        await register_socket(app, room_id, member_id)
        await ws_dispatch(app, room_id, member_id, "join_party_game", {"party_game_id": party_game_id})

    await register_socket(app, room_id, p5["member_id"])
    try:
        await ws_dispatch(app, room_id, p5["member_id"], "join_party_game", {"party_game_id": party_game_id})
        assert False, "a 5th player joining a Spades lobby should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_each_player_sees_only_their_own_hand(client, app):
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)

    for member_id in member_ids:
        state = _party_states(sockets[member_id])[-1]
        assert len(state["my_hand"]) == 13
    host_state = _party_states(sockets[member_ids[0]])[-1]
    assert host_state["hand_sizes"] == {m: 13 for m in member_ids}


async def test_bid_amounts_stay_hidden_until_everyone_has_bid(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)

    await ws_dispatch(
        app, room_id, member_ids[0], "party_action",
        {"party_game_id": party_game_id, "action": "bid", "amount": 4},
    )
    other_view = _party_states(sockets[member_ids[1]])[-1]
    assert other_view["bids"] is None
    assert member_ids[0] in other_view["bids_submitted"]

    my_view = _party_states(sockets[member_ids[0]])[-1]
    assert my_view["my_bid"] == 4


async def test_only_the_current_trick_player_may_act(client, app, monkeypatch):
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)

    for member_id in member_ids:
        await ws_dispatch(
            app, room_id, member_id, "party_action",
            {"party_game_id": party_game_id, "action": "bid", "amount": 3},
        )
    assert await _wait_for(lambda: _party_states(sockets[member_ids[0]])[-1]["phase"] == "trick", timeout=2.0)

    state = _party_states(sockets[member_ids[0]])[-1]
    current = state["current_player_id"]
    not_current = next(m for m in member_ids if m != current)
    legal_card_id = _party_states(sockets[current])[-1]["my_hand"][0]["id"]
    try:
        await ws_dispatch(
            app, room_id, not_current, "party_action",
            {"party_game_id": party_game_id, "action": "play_card", "card_id": legal_card_id},
        )
        assert False, "acting out of turn should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "illegal_action"


async def test_skip_round_resolves_the_current_phase_immediately(client, app):
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)
    host_id = member_ids[0]

    await ws_dispatch(app, room_id, host_id, "skip_party_round", {"party_game_id": party_game_id})
    state = _party_states(sockets[host_id])[-1]
    assert state["phase"] == "reveal"


async def test_real_timer_resolves_bidding_with_no_submissions(client, app, monkeypatch):
    monkeypatch.setattr(spades_engine, "BID_DURATION_SECONDS", 0.05)
    monkeypatch.setattr(realtime, "PARTY_REVEAL_PAUSE_SECONDS", 0.05)
    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)

    # Nobody ever bids - only the real server timer can resolve this.
    assert await _wait_for(lambda: _party_states(sockets[member_ids[0]])[-1]["phase"] == "trick", timeout=2.0)


async def test_reconnect_snapshot_resyncs_only_my_own_hand(client, app):
    from app import party_games as party_games_mod

    room_id, member_ids = await _setup_room_with_four(client, app)
    party_game_id, sockets = await _start_four_player_game(app, room_id, member_ids)

    async with app.state.db.session() as session:
        snapshot_a = await party_games_mod.connect_snapshot_event(session, room_id, member_ids[0])
        snapshot_b = await party_games_mod.connect_snapshot_event(session, room_id, member_ids[1])

    assert len(snapshot_a["my_hand"]) == 13
    assert len(snapshot_b["my_hand"]) == 13
    assert {c["id"] for c in snapshot_a["my_hand"]}.isdisjoint({c["id"] for c in snapshot_b["my_hand"]})
