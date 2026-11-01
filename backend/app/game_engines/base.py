"""Seats, not colors: every Phase A/B game is 2-player, alternating turns.
Seat 0 = white_member_id (challenger/link-creator), seat 1 = black_member_id
(invited opponent) - games.py still reports these to the wire as
"white"/"black" (SEAT_NAMES) for every kind, a deliberate chess-shaped
naming leftover, not a claim that e.g. Tic-Tac-Toe's seat 0 is "white"."""

from typing import Any, Protocol, runtime_checkable

Seat = int  # 0 or 1
SEAT_NAMES: tuple[str, str] = ("white", "black")


class IllegalMove(Exception):
    """Engines raise this for any rules violation; games.py catches it and
    turns it into DomainError("illegal_move", str(exc)). Engines never
    import DomainError or know they're running inside a WS handler."""


@runtime_checkable
class GameEngine(Protocol):
    kind: str
    # True only for chess (replay moves_json through apply_move on every
    # read). False for every new kind: state_json is the persisted,
    # authoritative snapshot, updated in place each turn.
    REPLAY_FROM_LOG: bool

    def initial_state(self) -> Any:
        """A brand-new game's state, right after both seats are filled."""
        ...

    def parse_move(self, data: dict) -> dict:
        """Normalize the raw `game_move` WS payload into this engine's own
        move-dict shape. Raise ValueError/KeyError/TypeError for malformed
        input - realtime.py turns any of those into a generic bad_request."""
        ...

    def encode_move(self, move: dict) -> Any:
        """JSON-safe value appended to moves_json. Chess MUST keep
        collapsing {"uci": "e2e4"} to the bare string "e2e4" - production
        already has chess games with moves_json as a plain UCI-string
        array, and this has to keep producing that exact shape forever."""
        ...

    def decode_move(self, raw: Any) -> dict:
        """Inverse of encode_move - only used when REPLAY_FROM_LOG=True."""
        ...

    def apply_move(self, state: Any, seat: Seat, move: dict) -> Any:
        """Validate + apply. Turn ownership is already checked by games.py
        via current_turn() before this is called - only validate the
        move's own legality. Raise IllegalMove for anything invalid."""
        ...

    def legal_moves(self, state: Any, seat: Seat) -> list[dict] | None:
        """None = don't hint at all (Tic-Tac-Toe: "any empty cell" is
        trivial enough the frontend derives it itself). [] is a real,
        distinct answer (no legal moves right now)."""
        ...

    def current_turn(self, state: Any) -> Seat:
        """Always a definite answer, even once the game's over (matches
        python-chess's board.turn) - callers gate on game status
        separately."""
        ...

    def check_outcome(self, state: Any) -> tuple[str | None, str | None]:
        """(result, termination); result is "white"/"black"/"draw" (never
        a bare seat index). (None, None) = still in progress. Resignation
        bypasses this entirely - games.resign() sets Game.status directly
        without ever calling the engine."""
        ...

    def build_display_state(self, state: Any, moves: list) -> dict:
        """Kind-specific fields merged into the outer game_state event
        alongside games.py's generic fields. Pure function of state +
        move log - no DB/session access, no game-lifecycle knowledge."""
        ...

    # Deliberately NOT part of this Protocol (every existing engine omits
    # it entirely, since every board game so far is fully public to both
    # seats and every spectator). An engine with hidden per-player
    # information - battleship's own ship positions being the first case
    # - opts in by implementing:
    #
    #   def redact_for_viewer(self, display: dict, viewer_seat: Seat | None) -> dict:
    #       """Given the full display dict build_display_state produced,
    #       return the subset `viewer_seat` is actually allowed to see.
    #       viewer_seat is 0 or 1 for an actual player, None for a
    #       spectator (or for no particular viewer at all - the safe
    #       default). Called once per recipient in build_state_event,
    #       engines without hidden information never need to implement
    #       this at all - games.py checks hasattr() and skips straight
    #       through when it's absent."""
    #
    # Kept out of the Protocol class itself (rather than given a no-op
    # default here) so hasattr() stays the one, explicit way to ask "does
    # this kind actually have anything to hide" - a required method with
    # a default body would make that question impossible to answer
    # cheaply without calling it.
