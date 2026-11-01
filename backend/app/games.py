"""Games inside a room - chess was the first, now one of several pluggable
kinds (see app/game_engines/). A game is either an append-only log of moves
replayed from the start on every read (chess, via python-chess), or a
directly-persisted state_json snapshot updated in place each move (every
other kind) - see GameEngine.REPLAY_FROM_LOG in app/game_engines/base.py.

Business logic only, no HTTP/WebSocket awareness - realtime.py's handlers
call into this, same split as rooms.py/members.py."""

import json
import secrets

from sqlalchemy import or_, select

from app.errors import DomainError
from app.game_engines import get_engine
from app.game_engines.base import GameEngine, IllegalMove, SEAT_NAMES
from app.models import Game, Member, new_id, utcnow


def _seat_of(game: Game, member_id: str) -> int | None:
    if member_id == game.white_member_id:
        return 0
    if member_id == game.black_member_id:
        return 1
    return None


def _load_state(game: Game, engine: GameEngine):
    if engine.REPLAY_FROM_LOG:
        state = engine.initial_state()
        for seat, raw in enumerate(json.loads(game.moves_json)):
            state = engine.apply_move(state, seat % 2, engine.decode_move(raw))
        return state
    if game.state_json is None:
        return engine.initial_state()
    return json.loads(game.state_json)


def _activate(game: Game) -> None:
    """Called exactly once, the moment a game's status flips to "active".
    For a REPLAY_FROM_LOG=False engine, initial_state() is persisted here
    rather than left to be lazily computed by the next _load_state() call
    - most engines' initial_state() is a pure function of nothing, so
    calling it twice would be harmless, but an engine whose initial_state
    has a real side effect (backgammon's opening dice roll) must only
    ever be called once, or the dice shown in that first broadcast
    silently stop matching what's actually validated on the first move."""
    engine = get_engine(game.kind)
    if not engine.REPLAY_FROM_LOG:
        game.state_json = json.dumps(engine.initial_state())


async def get_live_game_for_member(session, room_id: str, member_id: str) -> Game | None:
    """The one pending/awaiting/active game this member is currently part
    of in this room, if any. Used both to block starting a second one
    (keeps the "one game at a time" invariant the frontend's single
    myGameId slot relies on) and to build the connect-time snapshot for
    reconnects. "awaiting" games have no black_member_id yet, so this only
    ever matches them via white_member_id."""
    result = await session.execute(
        select(Game).where(
            Game.room_id == room_id,
            Game.status.in_(("pending", "awaiting", "active")),
            or_(Game.white_member_id == member_id, Game.black_member_id == member_id),
        )
    )
    return result.scalars().first()


async def create_challenge(session, room, challenger: Member, opponent: Member, kind: str = "chess") -> Game:
    get_engine(kind)  # fail fast on an unknown kind, before touching the DB
    if opponent.id == challenger.id:
        raise DomainError("bad_request", "You can't challenge yourself.")
    if opponent.room_id != room.id or opponent.status != "active":
        raise DomainError("bad_request", "That person isn't in this room.")
    if await get_live_game_for_member(session, room.id, challenger.id) is not None:
        raise DomainError("game_in_progress", "Finish or cancel your current game first.")
    if await get_live_game_for_member(session, room.id, opponent.id) is not None:
        raise DomainError("game_in_progress", f"{opponent.display_name} is already in a game.")

    game = Game(
        id=new_id(),
        room_id=room.id,
        kind=kind,
        white_member_id=challenger.id,
        black_member_id=opponent.id,
        status="pending",
        moves_json="[]",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(game)
    await session.commit()
    return game


async def create_link_challenge(session, room, challenger: Member, kind: str = "chess") -> Game:
    """An open seat, not addressed to any specific member yet - for
    inviting someone who isn't in the room (or even online anywhere) by
    sharing a link, rather than picking from who's currently present."""
    get_engine(kind)  # fail fast on an unknown kind, before touching the DB
    if await get_live_game_for_member(session, room.id, challenger.id) is not None:
        raise DomainError("game_in_progress", "Finish or cancel your current game first.")

    game = Game(
        id=new_id(),
        room_id=room.id,
        kind=kind,
        white_member_id=challenger.id,
        black_member_id=None,
        status="awaiting",
        moves_json="[]",
        link_token=secrets.token_urlsafe(8),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(game)
    await session.commit()
    return game


async def get_game_by_token(session, room_id: str, token: str) -> Game | None:
    """Not filtered to status "awaiting" - claim_link_challenge needs to
    see an already-claimed game too, to tell "someone else already took
    this" apart from "you're re-opening the same link you already used"."""
    result = await session.execute(select(Game).where(Game.room_id == room_id, Game.link_token == token))
    return result.scalars().first()


async def claim_link_challenge(session, room, game: Game, claimant: Member) -> tuple[Game, bool]:
    """Returns (game, is_fresh_claim). Claiming is idempotent for whoever
    already holds the seat: reopening the exact same share link (from
    WhatsApp's chat history, a bookmark, or a page reload that fires
    before the URL gets cleaned up) is a completely normal thing for a
    real guest to do, and should resync them into the game rather than
    show a scary "invalid link" error for something that already
    succeeded once."""
    if claimant.id == game.black_member_id and game.status in ("active", "finished"):
        return game, False
    if game.status != "awaiting":
        raise DomainError("bad_request", "That invite link isn't valid anymore.")
    if claimant.id == game.white_member_id:
        raise DomainError("bad_request", "You can't join your own invite link.")
    if await get_live_game_for_member(session, room.id, claimant.id) is not None:
        raise DomainError("game_in_progress", "Finish or cancel your current game first.")

    game.black_member_id = claimant.id
    game.status = "active"
    _activate(game)
    game.updated_at = utcnow()
    await session.commit()
    return game, True


async def get_game_or_404(session, room_id: str, game_id: str) -> Game:
    game = await session.get(Game, game_id)
    if game is None or game.room_id != room_id:
        raise DomainError("bad_request", "Unknown game.")
    return game


async def accept_challenge(session, game: Game, actor: Member) -> Game:
    if game.status != "pending":
        raise DomainError("bad_request", "That challenge is no longer open.")
    if actor.id != game.black_member_id:
        raise DomainError("not_allowed", "That challenge wasn't sent to you.")
    game.status = "active"
    _activate(game)
    game.updated_at = utcnow()
    await session.commit()
    return game


async def decline_challenge(session, game: Game, actor: Member) -> Game:
    if game.status != "pending":
        raise DomainError("bad_request", "That challenge is no longer open.")
    if actor.id != game.black_member_id:
        raise DomainError("not_allowed", "That challenge wasn't sent to you.")
    game.status = "declined"
    game.updated_at = utcnow()
    await session.commit()
    return game


async def cancel_challenge(session, game: Game, actor: Member) -> Game:
    """Covers both a targeted invite ("pending") and an open link
    ("awaiting") - cancelling either just frees the challenger up to
    start something else."""
    if game.status not in ("pending", "awaiting"):
        raise DomainError("bad_request", "That challenge is no longer open.")
    if actor.id != game.white_member_id:
        raise DomainError("not_allowed", "Only the person who sent it can cancel it.")
    game.status = "cancelled"
    game.updated_at = utcnow()
    await session.commit()
    return game


async def apply_move(session, game: Game, actor: Member, move: dict) -> Game:
    if game.status != "active":
        raise DomainError("bad_request", "This game isn't active.")
    seat = _seat_of(game, actor.id)
    if seat is None:
        raise DomainError("not_allowed", "You're not a player in this game.")

    engine = get_engine(game.kind)
    state = _load_state(game, engine)
    if engine.current_turn(state) != seat:
        raise DomainError("not_your_turn", "It's not your turn.")

    try:
        new_state = engine.apply_move(state, seat, move)
    except IllegalMove as exc:
        raise DomainError("illegal_move", str(exc) or "That's not a legal move.")

    moves = json.loads(game.moves_json)
    moves.append(engine.encode_move(move))
    game.moves_json = json.dumps(moves)
    if not engine.REPLAY_FROM_LOG:
        game.state_json = json.dumps(new_state)
    game.updated_at = utcnow()

    result, termination = engine.check_outcome(new_state)
    if result is not None:
        game.status = "finished"
        game.result = result
        game.termination = termination

    await session.commit()
    return game


async def resign(session, game: Game, actor: Member) -> Game:
    if game.status != "active":
        raise DomainError("bad_request", "This game isn't active.")
    seat = _seat_of(game, actor.id)
    if seat is None:
        raise DomainError("not_allowed", "You're not a player in this game.")

    game.status = "finished"
    game.result = SEAT_NAMES[1 - seat]
    game.termination = "resignation"
    game.updated_at = utcnow()
    await session.commit()
    return game


async def build_state_event(session, game: Game) -> dict:
    engine = get_engine(game.kind)
    state = _load_state(game, engine)
    moves = json.loads(game.moves_json)
    white = await session.get(Member, game.white_member_id)
    black = await session.get(Member, game.black_member_id)

    display = engine.build_display_state(state, moves)
    # Resignation (or any future non-engine-driven ending) finishes the
    # Game row without the engine's own state ever reflecting "over" - any
    # legal_moves hint must follow the game's actual lifecycle status, not
    # just what the board position happens to allow.
    if game.status != "active" and "legal_moves" in display:
        display["legal_moves"] = []

    return {
        "type": "game_state",
        "game_id": game.id,
        "kind": game.kind,
        "status": game.status,
        "white_member_id": game.white_member_id,
        "white_name": white.display_name if white else "Unknown",
        "black_member_id": game.black_member_id,
        "black_name": black.display_name if black else "Unknown",
        "moves": moves,
        "turn": SEAT_NAMES[engine.current_turn(state)],
        "game_over": game.status == "finished",
        "result": game.result,
        "termination": game.termination,
        "last_move": moves[-1] if moves else None,
        **display,
    }


def live_event(game: Game, white: Member, black: Member) -> dict:
    """The lightweight room-wide "X vs Y is live" announcement - no board
    state, just enough for a non-players banner. Watching (watch_game)
    is what actually fetches the full board."""
    return {
        "type": "game_live",
        "game_id": game.id,
        "kind": game.kind,
        "white_member_id": game.white_member_id,
        "white_name": white.display_name,
        "black_member_id": game.black_member_id,
        "black_name": black.display_name,
    }


async def live_games_for_room(session, room_id: str, exclude_member_id: str | None = None) -> list[dict]:
    """Every currently-active game in the room, as live_event dicts - used
    to populate a newly-connecting client's "live now" banner for games
    already in progress. Excludes the connecting member's own game(s),
    since they get the full game_state directly, not a spectator banner."""
    result = await session.execute(select(Game).where(Game.room_id == room_id, Game.status == "active"))
    games = result.scalars().all()
    events = []
    for game in games:
        if exclude_member_id in (game.white_member_id, game.black_member_id):
            continue
        white = await session.get(Member, game.white_member_id)
        black = await session.get(Member, game.black_member_id)
        if white is None or black is None:
            continue
        events.append(live_event(game, white, black))
    return events


async def leaderboard(session, room_id: str) -> list[dict]:
    """Win/loss/draw counts per member, from every finished game in this
    room - derived on read from the games table, not tracked separately,
    same "one source of truth" reasoning as the board itself."""
    result = await session.execute(
        select(Game).where(Game.room_id == room_id, Game.status == "finished")
    )
    games = result.scalars().all()

    stats: dict[str, dict] = {}

    def bump(member_id: str, key: str) -> None:
        row = stats.setdefault(member_id, {"wins": 0, "losses": 0, "draws": 0})
        row[key] += 1

    for game in games:
        if game.result == "draw":
            bump(game.white_member_id, "draws")
            bump(game.black_member_id, "draws")
        elif game.result == "white":
            bump(game.white_member_id, "wins")
            bump(game.black_member_id, "losses")
        else:
            bump(game.black_member_id, "wins")
            bump(game.white_member_id, "losses")

    rows = []
    for member_id, row in stats.items():
        member = await session.get(Member, member_id)
        rows.append(
            {
                "member_id": member_id,
                "name": member.display_name if member else "Unknown",
                **row,
                "games_played": row["wins"] + row["losses"] + row["draws"],
            }
        )
    rows.sort(key=lambda r: (-r["wins"], -r["draws"], r["losses"]))
    return rows


def invite_event(game: Game, challenger: Member, opponent: Member) -> dict:
    return {
        "type": "game_invite",
        "game_id": game.id,
        "kind": game.kind,
        "challenger_member_id": challenger.id,
        "challenger_name": challenger.display_name,
        "opponent_member_id": opponent.id,
        "opponent_name": opponent.display_name,
    }


def link_waiting_event(game: Game, white: Member) -> dict:
    return {
        "type": "game_link_waiting",
        "game_id": game.id,
        "kind": game.kind,
        "white_member_id": white.id,
        "white_name": white.display_name,
        "link_token": game.link_token,
    }


async def connect_snapshot_event(session, room_id: str, member_id: str) -> dict | None:
    """Replayed right after `ready` on every (re)connect - same role as
    music_snapshot/active_calls_for_member: don't lose track of a pending
    challenge, an open invite link, or an in-progress game across a
    reload."""
    game = await get_live_game_for_member(session, room_id, member_id)
    if game is None:
        return None
    if game.status == "pending":
        white = await session.get(Member, game.white_member_id)
        black = await session.get(Member, game.black_member_id)
        if white is None or black is None:
            return None
        return invite_event(game, white, black)
    if game.status == "awaiting":
        white = await session.get(Member, game.white_member_id)
        if white is None:
            return None
        return link_waiting_event(game, white)
    return await build_state_event(session, game)
