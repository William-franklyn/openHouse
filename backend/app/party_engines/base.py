"""N-participant party games (Trivia, then later Werewolf/Codenames/
Drawing&Guessing/Buzzer-Race) - a parallel abstraction to
game_engines/base.py's GameEngine, not a reuse of it:

- GameEngine is exactly 2 seats (Seat = 0 or 1) alternating turns
  (current_turn), ending via check_outcome's white/black/draw.
  PartyEngine is N participants (a list of member_ids fixed at round 0),
  nobody "takes a turn" - everyone acts within the same open window (a
  round), and a round ends on a server-driven deadline, not because the
  acting side changed.
- GameEngine.REPLAY_FROM_LOG lets chess rebuild state by replaying a move
  log. No PartyEngine ever does this - state_json is always the single
  authoritative, directly-persisted snapshot.
- GameEngine.apply_move takes a resolved Seat because turn order already
  answers "whose move is this" (games.py checks it before calling in).
  PartyEngine.apply_action takes the raw member_id - any participant can
  act at any moment the round allows, so "is this even your turn" isn't
  a precondition the caller can prove in advance the way seat-ownership is.
- GameEngine.redact_for_viewer is optional (hasattr-gated) because most
  board games have nothing to hide. Every PartyEngine implements
  build_display_state's redaction directly and unconditionally - hiding
  other participants' in-progress answers isn't an edge case here, it's
  the whole mechanic, and the same will be true of Werewolf's night
  actions or Codenames' hidden key card, so there's no safe seatless
  default worth factoring out.
"""

from typing import Any, Protocol, runtime_checkable


class IllegalAction(Exception):
    """Engines raise this for any invalid action (wrong phase, round
    already decided, duplicate submission, bad payload shape);
    party_games.py catches it and turns it into
    DomainError("illegal_action", str(exc)) - the PartyEngine analogue of
    IllegalMove/DomainError("illegal_move", ...)."""


@runtime_checkable
class PartyEngine(Protocol):
    kind: str
    # Below this many participants in the lobby, start_game refuses to
    # lock the roster - the N-participant analogue of handle_start_call's
    # "pick at least one invitee" floor. No GameEngine equivalent exists
    # (2-seat games always have exactly 2 by construction).
    MIN_PARTICIPANTS: int
    # Optional - above this many participants, join_lobby refuses to let
    # anyone else in ("This lobby is full."). Not part of the structural
    # Protocol (checked via getattr, defaulting to "no limit") since most
    # engines genuinely have none; Hearts needs exactly 4 (a 52-card deck
    # dealt evenly, hardcoded trick/pass logic), so MIN_PARTICIPANTS ==
    # MAX_PARTICIPANTS == 4 for it specifically.
    # MAX_PARTICIPANTS: int
    # How many "rounds" (in whatever unit this engine calls a round - for
    # Trivia that's literally one question each; for Draft, see
    # draft_engine.py, it's one pick) a fresh game runs for by default.
    # Not a free lobby-time choice the way Trivia's total_rounds param
    # could theoretically be, since some engines' round count is locked
    # to their own fixed structure (Draft's is hand_size * num_scoring_
    # rounds - cutting it short mid-structure would leave an un-scored
    # partial round) - party_games.create_lobby falls back to this
    # whenever the caller doesn't pass an explicit override.
    DEFAULT_TOTAL_ROUNDS: int

    def initial_state(self, participant_ids: list[str]) -> Any:
        """Fresh pre-round-0 state the instant the roster locks. Takes
        the roster explicitly (GameEngine.initial_state() never needs
        seats passed in, since there are always exactly 2 and games.py
        already knows which column each came from)."""
        ...

    def start_round(self, state: Any, round_index: int) -> tuple[Any, int]:
        """Begin round `round_index` (0-based). Returns
        (new_state, round_duration_seconds) - the duration is read back
        by realtime.py to size the Hub timer it arms. No GameEngine
        equivalent exists: board-game turns have no clock."""
        ...

    def parse_action(self, data: dict) -> dict:
        """Normalize the raw party_action WS payload into this engine's
        own action-dict shape, mirroring GameEngine.parse_move exactly.
        Raise ValueError/KeyError/TypeError for malformed input -
        realtime.py turns any of those into a generic bad_request before
        apply_action ever sees it."""
        ...

    def apply_action(self, state: Any, member_id: str, action: dict) -> Any:
        """Validate + apply one participant's action against the current
        round. Raise IllegalAction for anything invalid. Unlike
        GameEngine.apply_move, there is no prior turn-ownership check to
        lean on - whether `member_id` may act *at all* right now (right
        phase? haven't already acted this round?) is this method's job."""
        ...

    def is_round_over(self, state: Any) -> bool:
        """True once the round's own completion condition is met before
        its timer would naturally expire (trivia: everyone's answered).
        party_games.submit_answer checks this after every apply_action
        and, if true, the caller cancels the pending timer and calls
        time_up() itself immediately - same transition, just triggered
        early instead of by the clock."""
        ...

    def time_up(self, state: Any) -> tuple[Any, dict[str, int]]:
        """THE one authoritative "this round is over" transition - fired
        by the Hub's server timer expiring, by is_round_over()==True
        right after an action, or by the host's skip action. Every
        caller funnels through this exact function so there is never a
        second, divergent "end the round" code path. Returns
        (new_state, points_awarded_this_round) - party_games.py folds
        the points straight into its own scores_json column without ever
        reaching into engine-internal state, keeping it kind-agnostic.
        Must be idempotent against being called again on an
        already-revealed round (see realtime.py's note on the
        timer/early-finish race): a second call must return the SAME
        new_state unchanged and an EMPTY points dict, so a race never
        double-awards. No GameEngine equivalent - board games only end a
        turn via a legal move."""
        ...

    def check_game_over(self, state: Any, round_index: int, total_rounds: int) -> bool:
        """True if the game should finish now rather than start another
        round. Parallels GameEngine.check_outcome, but returns a plain
        bool - a party game has no win/loss/draw result; final standings
        come from scoreboard() instead."""
        ...

    def build_display_state(self, state: Any, viewer_member_id: str | None) -> dict:
        """The full per-viewer display dict for the outer party_state
        event. Combines what GameEngine splits into
        build_display_state()+optional redact_for_viewer() into one
        REQUIRED call, since a party game's redaction depends on more
        than a fixed seat index (e.g. "has THIS viewer answered THIS
        round") - there's no safe seatless default worth factoring out
        the way board games have. Must always include a top-level
        "phase" string in the returned dict - every generic frontend
        countdown/reveal UI switches on it. viewer_member_id is None for
        a no-viewer-in-particular build (e.g. system-message text)."""
        ...

    def scoreboard(self, state: Any, cumulative_scores: dict[str, int]) -> list[dict]:
        """Live or final standings rows (member_id, score, any
        kind-specific flag like "answered this round") - reused as-is by
        the lobby roster, the live in-round scoreboard, the reveal
        screen, and the final leaderboard. Kept as its own method
        (rather than folded into build_display_state) because the
        N-player scoreboard shape is identical across every future party
        game kind, whereas the rest of build_display_state is wildly
        different per kind."""
        ...
