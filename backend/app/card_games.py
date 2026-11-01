"""Card games (Poker, the first) - a seated table of N players with
persistent chip stacks across many hands, not a single round like a
party game and not a 2-seat alternating-turn board game. See
app/card_engines/base.py for why this is its own parallel abstraction.

One live card game per room at a time, same invariant as party games.
Business logic only, no HTTP/WebSocket awareness - realtime.py's
handlers call into this, same split as party_games.py/games.py."""

import json

from sqlalchemy import select

from app.card_engines import get_card_engine
from app.card_engines.base import IllegalAction
from app.errors import DomainError
from app.models import CardGame, Member, new_id, utcnow

DEFAULT_STARTING_CHIPS = 1000


async def get_live_card_game_for_room(session, room_id: str) -> CardGame | None:
    result = await session.execute(
        select(CardGame).where(CardGame.room_id == room_id, CardGame.status.in_(("lobby", "active")))
    )
    return result.scalars().first()


async def create_lobby(session, room, host: Member, kind: str = "poker", starting_chips: int = DEFAULT_STARTING_CHIPS) -> CardGame:
    get_card_engine(kind)  # fail fast on an unknown kind, before touching the DB
    if await get_live_card_game_for_room(session, room.id) is not None:
        raise DomainError("game_in_progress", "A card game is already happening in this room.")

    card_game = CardGame(
        id=new_id(),
        room_id=room.id,
        kind=kind,
        host_member_id=host.id,
        status="lobby",
        participants_json=json.dumps([host.id]),
        starting_chips=starting_chips,
        state_json=json.dumps({"phase": "lobby"}),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(card_game)
    await session.commit()
    return card_game


async def join_lobby(session, card_game: CardGame, member: Member) -> CardGame:
    if card_game.status != "lobby":
        raise DomainError("bad_request", "This card game has already started.")
    engine = get_card_engine(card_game.kind)
    participants = json.loads(card_game.participants_json)
    if member.id not in participants:
        if len(participants) >= engine.MAX_PARTICIPANTS:
            raise DomainError("bad_request", "This table is full.")
        participants.append(member.id)
        card_game.participants_json = json.dumps(participants)
        card_game.updated_at = utcnow()
        await session.commit()
    return card_game


async def leave_lobby(session, card_game: CardGame, member: Member) -> CardGame:
    """No-op once active - a seated player with chips simply folds every
    hand going forward if they stop playing; the seat isn't vacated
    mid-session (same "roster is locked once it's running" shape as
    PartyGame)."""
    if card_game.status != "lobby":
        return card_game
    participants = json.loads(card_game.participants_json)
    if member.id in participants:
        participants.remove(member.id)
        card_game.participants_json = json.dumps(participants)
        card_game.updated_at = utcnow()
        await session.commit()
    return card_game


async def start_game(session, card_game: CardGame, actor: Member) -> CardGame:
    """Any seated participant may call this (not host-gated - matches
    party_games.start_game's reasoning)."""
    if card_game.status != "lobby":
        raise DomainError("bad_request", "This card game has already started.")
    participants = json.loads(card_game.participants_json)
    if actor.id not in participants:
        raise DomainError("not_allowed", "You're not seated at this table.")

    engine = get_card_engine(card_game.kind)
    if len(participants) < engine.MIN_PARTICIPANTS:
        raise DomainError("bad_request", f"Need at least {engine.MIN_PARTICIPANTS} players to start.")

    state = engine.initial_state(participants, card_game.starting_chips)
    state = engine.start_hand(state)
    card_game.status = "active"
    card_game.state_json = json.dumps(state)
    card_game.updated_at = utcnow()
    await session.commit()
    return card_game


async def submit_action(session, card_game: CardGame, actor: Member, action: dict) -> tuple[CardGame, bool]:
    """Returns (card_game, hand_is_over_now) - the caller must call
    resolve_hand if True."""
    if card_game.status != "active":
        raise DomainError("bad_request", "This card game isn't active.")
    participants = json.loads(card_game.participants_json)
    if actor.id not in participants:
        raise DomainError("not_allowed", "You're not seated at this table.")

    engine = get_card_engine(card_game.kind)
    state = json.loads(card_game.state_json)
    try:
        new_state = engine.apply_action(state, actor.id, action)
    except IllegalAction as exc:
        raise DomainError("illegal_action", str(exc) or "That's not a legal action.")

    card_game.state_json = json.dumps(new_state)
    card_game.updated_at = utcnow()
    await session.commit()
    return card_game, engine.is_hand_over(new_state)


async def resolve_hand(session, card_game: CardGame) -> tuple[CardGame, bool]:
    """Awards the pot(s) - chip deltas are applied to state_json's own
    chip_stacks directly inside the engine (unlike PartyGame's separate
    scores_json column; see CardGame.state_json's docstring for why).
    Returns (card_game, game_is_over)."""
    engine = get_card_engine(card_game.kind)
    state = json.loads(card_game.state_json)
    state, _chip_deltas = engine.resolve_hand(state)
    card_game.state_json = json.dumps(state)
    game_over = engine.is_game_over(state["chip_stacks"])
    if game_over:
        card_game.status = "finished"
    card_game.updated_at = utcnow()
    await session.commit()
    return card_game, game_over


async def start_next_hand(session, card_game: CardGame, actor: Member) -> CardGame:
    """Any seated player with chips left may deal the next hand once the
    previous one is resolved - no host privilege, no auto-timer (see
    PokerEngine's own docstring for why a turn/hand clock is out of scope
    for v1)."""
    if card_game.status != "active":
        raise DomainError("bad_request", "This card game isn't active.")
    participants = json.loads(card_game.participants_json)
    if actor.id not in participants:
        raise DomainError("not_allowed", "You're not seated at this table.")

    engine = get_card_engine(card_game.kind)
    state = json.loads(card_game.state_json)
    if state["phase"] != "hand_over":
        raise DomainError("bad_request", "The current hand hasn't finished yet.")
    try:
        state = engine.start_hand(state)
    except IllegalAction as exc:
        raise DomainError("illegal_action", str(exc))
    card_game.state_json = json.dumps(state)
    card_game.updated_at = utcnow()
    await session.commit()
    return card_game


async def cancel_game(session, card_game: CardGame, actor: Member) -> CardGame:
    if card_game.status not in ("lobby", "active"):
        raise DomainError("bad_request", "This card game has already ended.")
    if actor.id != card_game.host_member_id and actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the host or a room owner/mod can cancel this.")
    card_game.status = "cancelled"
    card_game.updated_at = utcnow()
    await session.commit()
    return card_game


async def get_card_game_or_404(session, room_id: str, card_game_id: str) -> CardGame:
    card_game = await session.get(CardGame, card_game_id)
    if card_game is None or card_game.room_id != room_id:
        raise DomainError("bad_request", "Unknown card game.")
    return card_game


async def build_state_event(session, card_game: CardGame, viewer_member_id: str | None = None) -> dict:
    participants = json.loads(card_game.participants_json)

    if card_game.status == "lobby":
        display = {"phase": "lobby", "seats": []}
        rows = []
        for member_id in participants:
            member = await session.get(Member, member_id)
            rows.append({"member_id": member_id, "name": member.display_name if member else "Unknown"})
        display["seats"] = rows
    else:
        engine = get_card_engine(card_game.kind)
        state = json.loads(card_game.state_json)
        display = engine.build_display_state(state, viewer_member_id)
        for seat in display["seats"]:
            member = await session.get(Member, seat["member_id"])
            seat["name"] = member.display_name if member else "Unknown"

    return {
        "type": "card_state",
        "card_game_id": card_game.id,
        "kind": card_game.kind,
        "status": card_game.status,
        "host_member_id": card_game.host_member_id,
        "participant_ids": participants,
        "starting_chips": card_game.starting_chips,
        **display,
    }


async def connect_snapshot_event(session, room_id: str, member_id: str) -> dict | None:
    card_game = await get_live_card_game_for_room(session, room_id)
    if card_game is None:
        return None
    if card_game.status == "lobby":
        return await build_state_event(session, card_game, member_id)
    participants = json.loads(card_game.participants_json)
    if member_id not in participants:
        return None
    return await build_state_event(session, card_game, member_id)
