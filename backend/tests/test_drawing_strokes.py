"""Tests for the draw_stroke/draw_clear relay handlers in realtime.py -
a pure ephemeral broadcast with no DB persistence and no DrawingEngine
involvement at all (see the handlers' own docstring for why)."""

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


def _party_states(ws):
    return [e for e in ws.sent if e.get("type") == "party_state"]


def _strokes(ws):
    return [e for e in ws.sent if e.get("type") == "draw_stroke"]


def _clears(ws):
    return [e for e in ws.sent if e.get("type") == "draw_clear"]


async def _start_three_player_game(client, app, seed=1):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    p2 = await join(client, data["room"]["code"], "P2")
    p3 = await join(client, data["room"]["code"], "P3")
    member_ids = [host_id, p2["member_id"], p3["member_id"]]

    host_ws = await register_socket(app, room_id, host_id)
    await ws_dispatch(app, room_id, host_id, "start_party_game", {"kind": "drawing"})
    party_game_id = _party_states(host_ws)[-1]["party_game_id"]
    sockets = {host_id: host_ws}
    for member_id in member_ids[1:]:
        ws = await register_socket(app, room_id, member_id)
        await ws_dispatch(app, room_id, member_id, "join_party_game", {"party_game_id": party_game_id})
        sockets[member_id] = ws

    random.seed(seed)
    await ws_dispatch(app, room_id, host_id, "begin_party_game", {"party_game_id": party_game_id})
    drawer_id = _party_states(sockets[host_id])[-1]["current_drawer_id"]
    return room_id, member_ids, sockets, drawer_id


async def test_a_stroke_from_the_drawer_reaches_every_other_participant(client, app):
    room_id, member_ids, sockets, drawer_id = await _start_three_player_game(client, app)
    others = [m for m in member_ids if m != drawer_id]

    stroke = {
        "points": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
        "color": "#ff0000",
        "width": 4,
        "stroke_id": "s1",
    }
    await ws_dispatch(app, room_id, drawer_id, "draw_stroke", stroke)

    for other in others:
        received = _strokes(sockets[other])
        assert len(received) == 1
        assert received[0]["stroke_id"] == "s1"
        assert received[0]["points"] == stroke["points"]
        assert received[0]["color"] == "#ff0000"

    # The drawer should not receive an echo of their own stroke.
    assert _strokes(sockets[drawer_id]) == []


async def test_a_non_drawer_cannot_send_a_stroke(client, app):
    room_id, member_ids, sockets, drawer_id = await _start_three_player_game(client, app)
    not_drawer = next(m for m in member_ids if m != drawer_id)

    try:
        await ws_dispatch(
            app, room_id, not_drawer, "draw_stroke",
            {"points": [{"x": 0, "y": 0}], "color": "#000", "width": 2, "stroke_id": "s2"},
        )
        assert False, "a non-drawer should not be able to send a stroke"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"


async def test_a_malformed_stroke_payload_is_rejected(client, app):
    room_id, member_ids, sockets, drawer_id = await _start_three_player_game(client, app)
    try:
        await ws_dispatch(
            app, room_id, drawer_id, "draw_stroke",
            {"points": [], "color": "#000", "width": 2, "stroke_id": "s3"},
        )
        assert False, "an empty points list should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"


async def test_draw_clear_reaches_every_other_participant_but_not_the_drawer(client, app):
    room_id, member_ids, sockets, drawer_id = await _start_three_player_game(client, app)
    others = [m for m in member_ids if m != drawer_id]

    await ws_dispatch(app, room_id, drawer_id, "draw_clear", {})

    for other in others:
        assert len(_clears(sockets[other])) == 1
    assert _clears(sockets[drawer_id]) == []


async def test_a_non_drawer_cannot_clear_the_canvas(client, app):
    room_id, member_ids, sockets, drawer_id = await _start_three_player_game(client, app)
    not_drawer = next(m for m in member_ids if m != drawer_id)
    try:
        await ws_dispatch(app, room_id, not_drawer, "draw_clear", {})
        assert False, "a non-drawer should not be able to clear the canvas"
    except Exception as exc:
        assert getattr(exc, "code", None) == "not_allowed"


async def test_a_stroke_is_rejected_when_there_is_no_active_drawing_game(client, app):
    data = await create_room(client)
    room_id, host_id = data["room"]["id"], data["member"]["member_id"]
    await register_socket(app, room_id, host_id)
    try:
        await ws_dispatch(
            app, room_id, host_id, "draw_stroke",
            {"points": [{"x": 0, "y": 0}], "color": "#000", "width": 2, "stroke_id": "s4"},
        )
        assert False, "a stroke with no live drawing game should be rejected"
    except Exception as exc:
        assert getattr(exc, "code", None) == "bad_request"
