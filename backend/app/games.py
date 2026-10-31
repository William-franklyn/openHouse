"""Games inside a room - chess is the first. A game is an append-only log
of UCI moves (moves_json), replayed from the standard starting position on
every read via python-chess - same spirit as messages.py's seq'd log, never
a separately stored board snapshot that could drift from it.

Business logic only, no HTTP/WebSocket awareness - realtime.py's handlers
call into this, same split as rooms.py/members.py."""

import json

import chess
from sqlalchemy import or_, select

from app.errors import DomainError
from app.models import Game, Member, new_id, utcnow

COLOR_NAMES = {chess.WHITE: "white", chess.BLACK: "black"}


def _board(game: Game) -> chess.Board:
    board = chess.Board()
    for uci in json.loads(game.moves_json):
        board.push_uci(uci)
    return board


def _color_of(game: Game, member_id: str) -> bool | None:
    if member_id == game.white_member_id:
        return chess.WHITE
    if member_id == game.black_member_id:
        return chess.BLACK
    return None


async def get_live_game_for_member(session, room_id: str, member_id: str) -> Game | None:
    """The one pending-or-active game this member is currently part of in
    this room, if any. Used both to block starting a second one (keeps the
    "one game at a time" invariant the frontend's single myGameId slot
    relies on) and to build the connect-time snapshot for reconnects."""
    result = await session.execute(
        select(Game).where(
            Game.room_id == room_id,
            Game.status.in_(("pending", "active")),
            or_(Game.white_member_id == member_id, Game.black_member_id == member_id),
        )
    )
    return result.scalars().first()


async def create_challenge(session, room, challenger: Member, opponent: Member) -> Game:
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
        kind="chess",
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
    if game.status != "pending":
        raise DomainError("bad_request", "That challenge is no longer open.")
    if actor.id != game.white_member_id:
        raise DomainError("not_allowed", "Only the person who sent it can cancel it.")
    game.status = "cancelled"
    game.updated_at = utcnow()
    await session.commit()
    return game


def _outcome(board: chess.Board) -> tuple[str | None, str | None]:
    """(result, termination). result is "white"/"black"/"draw", or None if
    the game is still going."""
    if not board.is_game_over():
        return None, None
    outcome = board.outcome()
    if outcome is None:
        return None, None
    result = "draw" if outcome.winner is None else COLOR_NAMES[outcome.winner]
    return result, outcome.termination.name.lower()


async def apply_move(session, game: Game, actor: Member, uci: str) -> Game:
    if game.status != "active":
        raise DomainError("bad_request", "This game isn't active.")
    color = _color_of(game, actor.id)
    if color is None:
        raise DomainError("not_allowed", "You're not a player in this game.")

    board = _board(game)
    if board.turn != color:
        raise DomainError("not_your_turn", "It's not your turn.")

    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        raise DomainError("illegal_move", "That's not a legal move.")
    if move not in board.legal_moves:
        raise DomainError("illegal_move", "That's not a legal move.")

    board.push(move)
    moves = json.loads(game.moves_json)
    moves.append(move.uci())
    game.moves_json = json.dumps(moves)
    game.updated_at = utcnow()

    result, termination = _outcome(board)
    if result is not None:
        game.status = "finished"
        game.result = result
        game.termination = termination

    await session.commit()
    return game


async def resign(session, game: Game, actor: Member) -> Game:
    if game.status != "active":
        raise DomainError("bad_request", "This game isn't active.")
    color = _color_of(game, actor.id)
    if color is None:
        raise DomainError("not_allowed", "You're not a player in this game.")

    game.status = "finished"
    game.result = COLOR_NAMES[not color]
    game.termination = "resignation"
    game.updated_at = utcnow()
    await session.commit()
    return game


def _was_last_move_a_capture(moves: list[str]) -> bool:
    """Whether the most recent move captured a piece - used purely for the
    frontend's sound effect, so it's derived fresh rather than stored
    (same "replay the log" philosophy as the board itself)."""
    if not moves:
        return False
    board = chess.Board()
    for uci in moves[:-1]:
        board.push_uci(uci)
    return board.is_capture(chess.Move.from_uci(moves[-1]))


async def build_state_event(session, game: Game) -> dict:
    board = _board(game)
    white = await session.get(Member, game.white_member_id)
    black = await session.get(Member, game.black_member_id)
    moves = json.loads(game.moves_json)
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
        # The piece placement field of FEN ("rnbqkbnr/pppppppp/8/.../RNBQKBNR")
        # - lets the client render the board from pure serialization, with
        # no chess rules of its own (it never needs to know how a knight
        # moves, just where the pieces currently are).
        "board_fen": board.board_fen(),
        "turn": "white" if board.turn == chess.WHITE else "black",
        "legal_moves": [m.uci() for m in board.legal_moves] if game.status == "active" else [],
        "in_check": board.is_check(),
        "last_move_was_capture": _was_last_move_a_capture(moves),
        "game_over": game.status == "finished",
        "result": game.result,
        "termination": game.termination,
        "last_move": moves[-1] if moves else None,
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


async def connect_snapshot_event(session, room_id: str, member_id: str) -> dict | None:
    """Replayed right after `ready` on every (re)connect - same role as
    music_snapshot/active_calls_for_member: don't lose track of a pending
    challenge or an in-progress game across a reload."""
    game = await get_live_game_for_member(session, room_id, member_id)
    if game is None:
        return None
    if game.status == "pending":
        white = await session.get(Member, game.white_member_id)
        black = await session.get(Member, game.black_member_id)
        if white is None or black is None:
            return None
        return invite_event(game, white, black)
    return await build_state_event(session, game)
