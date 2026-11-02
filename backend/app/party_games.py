"""Party games inside a room - N arbitrary room participants in a
host-started lobby, not the 2-seat board-game model in app/games.py (see
app/party_engines/base.py for why this is a parallel abstraction, not a
reuse, of GameEngine). One live party game per room at a time.

Business logic only, no HTTP/WebSocket awareness - realtime.py's handlers
call into this, same split as games.py/rooms.py/members.py."""

import json

from sqlalchemy import select

from app.errors import DomainError
from app.models import Member, PartyGame, new_id, utcnow
from app.party_engines import get_party_engine
from app.party_engines.base import IllegalAction

async def get_live_party_game_for_room(session, room_id: str) -> PartyGame | None:
    result = await session.execute(
        select(PartyGame).where(PartyGame.room_id == room_id, PartyGame.status.in_(("lobby", "active")))
    )
    return result.scalars().first()


async def create_lobby(session, room, host: Member, kind: str = "trivia", total_rounds: int | None = None) -> PartyGame:
    engine = get_party_engine(kind)  # fail fast on an unknown kind, before touching the DB
    if await get_live_party_game_for_room(session, room.id) is not None:
        raise DomainError("game_in_progress", "A party game is already happening in this room.")
    if total_rounds is None:
        total_rounds = engine.DEFAULT_TOTAL_ROUNDS

    party_game = PartyGame(
        id=new_id(),
        room_id=room.id,
        kind=kind,
        host_member_id=host.id,
        status="lobby",
        participants_json=json.dumps([host.id]),
        scores_json="{}",
        round_index=0,
        total_rounds=total_rounds,
        state_json=json.dumps({"phase": "lobby"}),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(party_game)
    await session.commit()
    return party_game


async def join_lobby(session, party_game: PartyGame, member: Member) -> PartyGame:
    if party_game.status != "lobby":
        raise DomainError("bad_request", "This party game has already started.")
    participants = json.loads(party_game.participants_json)
    engine = get_party_engine(party_game.kind)
    max_participants = getattr(engine, "MAX_PARTICIPANTS", None)
    if member.id not in participants:
        if max_participants is not None and len(participants) >= max_participants:
            raise DomainError("bad_request", "This lobby is full.")
        participants.append(member.id)
        party_game.participants_json = json.dumps(participants)
        party_game.updated_at = utcnow()
        await session.commit()
    return party_game


async def leave_lobby(session, party_game: PartyGame, member: Member) -> PartyGame:
    """No-op (never errors) once the game is active - a stray leave after
    start shouldn't need special-casing by callers; the roster is locked
    and the round timer is authoritative regardless of who's connected."""
    if party_game.status != "lobby":
        return party_game
    participants = json.loads(party_game.participants_json)
    if member.id in participants:
        participants.remove(member.id)
        party_game.participants_json = json.dumps(participants)
        party_game.updated_at = utcnow()
        await session.commit()
    return party_game


async def start_game(session, party_game: PartyGame, actor: Member) -> tuple[PartyGame, int]:
    """Any participant may call this (not host-gated - matches
    handle_start_call/handle_start_music's "normal member action, not a
    privilege" reasoning). Returns (party_game, round_duration_seconds)."""
    if party_game.status != "lobby":
        raise DomainError("bad_request", "This party game has already started.")
    participants = json.loads(party_game.participants_json)
    if actor.id not in participants:
        raise DomainError("not_allowed", "You're not in this lobby.")

    engine = get_party_engine(party_game.kind)
    if len(participants) < engine.MIN_PARTICIPANTS:
        raise DomainError("bad_request", f"Need at least {engine.MIN_PARTICIPANTS} players to start.")

    state = engine.initial_state(participants)
    state, duration = engine.start_round(state, 0)
    party_game.status = "active"
    party_game.round_index = 0
    party_game.scores_json = json.dumps({member_id: 0 for member_id in participants})
    party_game.state_json = json.dumps(state)
    party_game.updated_at = utcnow()
    await session.commit()
    return party_game, duration


async def submit_answer(session, party_game: PartyGame, actor: Member, action: dict) -> tuple[PartyGame, bool]:
    """Returns (party_game, round_is_over_now) - a caller getting True
    back must itself cancel the pending timer and call time_up."""
    if party_game.status != "active":
        raise DomainError("bad_request", "This party game isn't active.")
    participants = json.loads(party_game.participants_json)
    if actor.id not in participants:
        raise DomainError("not_allowed", "You're not a player in this game.")

    engine = get_party_engine(party_game.kind)
    state = json.loads(party_game.state_json)
    try:
        new_state = engine.apply_action(state, actor.id, action)
    except IllegalAction as exc:
        raise DomainError("illegal_action", str(exc) or "That's not a valid action.")

    party_game.state_json = json.dumps(new_state)
    party_game.updated_at = utcnow()
    await session.commit()
    return party_game, engine.is_round_over(new_state)


async def time_up(session, party_game: PartyGame) -> tuple[PartyGame, bool]:
    """THE round-over transition: scores the round, folds the awarded
    points into scores_json, flips status="finished" if the game's over.
    Idempotent (delegates to the engine's own idempotency guard - a
    second call returns an empty points dict, so this never double-
    awards). Returns (party_game, game_over)."""
    engine = get_party_engine(party_game.kind)
    state = json.loads(party_game.state_json)
    state, points_awarded = engine.time_up(state)

    scores = json.loads(party_game.scores_json)
    for member_id, awarded in points_awarded.items():
        scores[member_id] = scores.get(member_id, 0) + awarded
    party_game.scores_json = json.dumps(scores)
    party_game.state_json = json.dumps(state)

    game_over = engine.check_game_over(state, party_game.round_index, party_game.total_rounds)
    if game_over:
        party_game.status = "finished"
    party_game.updated_at = utcnow()
    await session.commit()
    return party_game, game_over


async def advance_round(session, party_game: PartyGame) -> tuple[PartyGame, int]:
    """Starts the next round after a reveal. Returns
    (party_game, round_duration_seconds)."""
    engine = get_party_engine(party_game.kind)
    state = json.loads(party_game.state_json)
    party_game.round_index += 1
    state, duration = engine.start_round(state, party_game.round_index)
    party_game.state_json = json.dumps(state)
    party_game.updated_at = utcnow()
    await session.commit()
    return party_game, duration


async def skip_round(session, party_game: PartyGame, actor: Member) -> None:
    """Permission check only - the one host-privileged action in this
    whole feature. The actual round-ending transition goes through
    time_up/advance_round via realtime.py's shared function."""
    if party_game.status != "active":
        raise DomainError("bad_request", "This party game isn't active.")
    if actor.id != party_game.host_member_id:
        raise DomainError("not_allowed", "Only the host can skip a round.")


async def cancel_game(session, party_game: PartyGame, actor: Member) -> PartyGame:
    """Ends a lobby or active game early. Host (or room owner/mod) only."""
    if party_game.status not in ("lobby", "active"):
        raise DomainError("bad_request", "This party game has already ended.")
    if actor.id != party_game.host_member_id and actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the host or a room owner/mod can cancel this.")
    party_game.status = "cancelled"
    party_game.updated_at = utcnow()
    await session.commit()
    return party_game


async def get_party_game_or_404(session, room_id: str, party_game_id: str) -> PartyGame:
    party_game = await session.get(PartyGame, party_game_id)
    if party_game is None or party_game.room_id != room_id:
        raise DomainError("bad_request", "Unknown party game.")
    return party_game


async def build_state_event(session, party_game: PartyGame, viewer_member_id: str | None = None) -> dict:
    """The per-recipient party_state payload. During "lobby" there's no
    locked roster yet for the engine to build a scoreboard from (every
    PartyEngine's scoreboard()/build_display_state() assume a fixed,
    already-locked participant list - see initial_state()'s docstring),
    so the lobby roster is built directly here instead of delegating to
    the engine; "active"/"finished" delegate fully."""
    participants = json.loads(party_game.participants_json)

    if party_game.status == "lobby":
        display = {"phase": "lobby"}
        rows = []
        for member_id in participants:
            member = await session.get(Member, member_id)
            rows.append(
                {
                    "member_id": member_id,
                    "name": member.display_name if member else "Unknown",
                    "score": 0,
                    "round_points": None,
                    "answered": False,
                }
            )
    else:
        engine = get_party_engine(party_game.kind)
        state = json.loads(party_game.state_json)
        display = engine.build_display_state(state, viewer_member_id)
        cumulative_scores = json.loads(party_game.scores_json)
        rows = []
        for row in engine.scoreboard(state, cumulative_scores):
            member = await session.get(Member, row["member_id"])
            rows.append({**row, "name": member.display_name if member else "Unknown"})

    return {
        "type": "party_state",
        "party_game_id": party_game.id,
        "kind": party_game.kind,
        "status": party_game.status,
        "host_member_id": party_game.host_member_id,
        "round_index": party_game.round_index,
        "total_rounds": party_game.total_rounds,
        "participant_ids": participants,
        "scoreboard": rows,
        **display,
    }


async def connect_snapshot_event(session, room_id: str, member_id: str) -> dict | None:
    """Replayed right after `ready` on every (re)connect, same role as
    games.connect_snapshot_event. A reconnecting non-participant still
    sees an open lobby (so they can discover and join it) but gets
    nothing for an already-active game they're not part of - no v1
    spectate."""
    party_game = await get_live_party_game_for_room(session, room_id)
    if party_game is None:
        return None
    if party_game.status == "lobby":
        return await build_state_event(session, party_game, member_id)
    participants = json.loads(party_game.participants_json)
    if member_id not in participants:
        return None
    return await build_state_event(session, party_game, member_id)
