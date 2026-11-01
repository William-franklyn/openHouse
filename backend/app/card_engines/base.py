"""Card games (Poker, the first) - yet another parallel abstraction, not a
reuse of GameEngine (2 fixed seats, strict turn alternation) or PartyEngine
(a fixed-duration round every participant acts in independently, then a
synchronized reveal):

- Poker is N seated players acting in a well-defined ORDER (like
  GameEngine), but the "whose turn" pointer moves around the table
  dynamically as players fold/go all-in, and a "round" (a betting street)
  ends on a condition about who's matched the current bet, not after a
  single move or a fixed clock. No PartyEngine-style timer drives streets
  forward - action advances purely from player decisions.
- Hole cards are hidden from every other player for the ENTIRE hand, not
  just until a reveal point (contrast with Trivia, where eversyone's pick
  becomes public knowledge at a fixed reveal step) - a folded player's
  hole cards are never shown to anyone, ever.
- Chip stacks persist across many hands in one sitting (unlike a
  PartyGame's cumulative score, which only exists across rounds of ONE
  game instance) - a CardGame row covers an entire session at the table,
  not a single hand.
"""

from typing import Any, Protocol, runtime_checkable


class IllegalAction(Exception):
    """Engines raise this for any invalid action (acting out of turn,
    betting less than the minimum, raising after folding, ...);
    card_games.py catches it and turns it into
    DomainError("illegal_action", str(exc))."""


@runtime_checkable
class CardEngine(Protocol):
    kind: str
    MIN_PARTICIPANTS: int
    MAX_PARTICIPANTS: int

    def initial_state(self, participant_ids: list[str], starting_chips: int) -> Any:
        """Fresh pre-first-hand state - seats everyone with starting_chips,
        no cards dealt yet (phase="lobby" until start_hand)."""
        ...

    def start_hand(self, state: Any) -> Any:
        """Shuffles, deals hole cards, posts blinds, rotates the dealer
        button, and sets the first player to act. Players with 0 chips
        are skipped (sitting out, not removed from participant_ids - they
        keep their seat for display purposes even though they can't act).
        Raises IllegalAction if fewer than 2 players have chips."""
        ...

    def parse_action(self, data: dict) -> dict:
        """Normalize the raw card_action WS payload, mirroring
        GameEngine.parse_move/PartyEngine.parse_action. Raise
        ValueError/KeyError/TypeError for malformed input."""
        ...

    def legal_actions(self, state: Any, member_id: str) -> dict:
        """What member_id may do RIGHT NOW: {"actions": [...], "call_amount":
        int, "min_raise_to": int | None, "max_raise_to": int | None}. Purely
        informational - apply_action is the actual enforcement; the frontend
        uses this to grey out illegal buttons rather than relying on trial
        and error against apply_action."""
        ...

    def apply_action(self, state: Any, member_id: str, action: dict) -> Any:
        """Validate + apply one betting decision (fold/check/call/raise).
        Raise IllegalAction if it isn't member_id's turn or the action
        isn't legal right now. Advances action_on to the next player, or
        advances the street (dealing the flop/turn/river) once the
        current betting round is complete, or moves straight to showdown
        resolution if the round that just completed was the river - or if
        only one non-folded player remains at any point."""
        ...

    def is_hand_over(self, state: Any) -> bool:
        """True once a winner is determined (everyone else folded, or
        river betting + showdown resolved) - card_games.py checks this
        after every apply_action and calls resolve_hand if so."""
        ...

    def resolve_hand(self, state: Any) -> tuple[Any, dict[str, int]]:
        """Awards the pot (splitting into side pots for any all-ins at
        different stack depths) and returns (new_state, chip_deltas) -
        chip_deltas is folded into the caller's own persistent chip_stacks,
        the same split PartyEngine.time_up uses for scores. new_state's
        phase becomes "hand_over" with the showdown result (whose hands
        were shown, who won what) preserved for display until the next
        start_hand call."""
        ...

    def is_game_over(self, chip_stacks: dict[str, int]) -> bool:
        """True once at most one player still has chips - everyone else
        busted out. Takes chip_stacks directly (not engine state) since
        chip_stacks is the caller's persistent column, not engine-owned."""
        ...

    def build_display_state(self, state: Any, viewer_member_id: str | None) -> dict:
        """Per-viewer redacted view: the viewer's own hole cards are
        included, every other active player's hole cards are omitted
        entirely (not even a placeholder count beyond what "still in the
        hand" already implies) until showdown reveals exactly the hands
        that were shown. A folded player's hole cards are NEVER included,
        even post-showdown, even to themselves (nothing to show - the
        round's over for them)."""
        ...
