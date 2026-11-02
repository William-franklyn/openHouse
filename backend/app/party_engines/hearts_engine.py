import copy
import random

from app.party_engines.base import IllegalAction

SUITS = ("C", "D", "H", "S")
PASS_DURATION_SECONDS = 45
TRICK_DURATION_SECONDS = 30
TARGET_SCORE = 100
PASS_DIRECTIONS = ("left", "right", "across", "hold")
PASS_OFFSETS = {"left": 1, "right": -1, "across": 2}


def _fresh_deck() -> list[dict]:
    return [{"id": f"{s}{r}", "suit": s, "rank": r} for s in SUITS for r in range(2, 15)]


def _is_point_card(card: dict) -> bool:
    return card["suit"] == "H" or (card["suit"] == "S" and card["rank"] == 12)


def _card_points(card: dict) -> int:
    if card["suit"] == "H":
        return 1
    if card["suit"] == "S" and card["rank"] == 12:
        return 13
    return 0


def _legal_cards(hand: list[dict], state: dict) -> list[dict]:
    """The full real-Hearts legality rules, verified against a standalone
    script before being written here: must lead the 2 of clubs on the
    very first trick; hearts can't be led until broken (a heart has been
    played on an earlier trick) unless the hand is nothing but hearts;
    must follow the lead suit if able; no point card (heart or queen of
    spades) may be played on the first trick unless it's the only
    option."""
    trick = state["current_trick"]
    is_first_trick = state["trick_number"] == 0

    if not trick:  # leading this trick
        if is_first_trick:
            two_clubs = next((c for c in hand if c["suit"] == "C" and c["rank"] == 2), None)
            return [two_clubs] if two_clubs else list(hand)
        if not state["hearts_broken"]:
            non_hearts = [c for c in hand if c["suit"] != "H"]
            if non_hearts:
                return non_hearts
        return list(hand)

    lead_suit = state["lead_suit"]
    same_suit = [c for c in hand if c["suit"] == lead_suit]
    if same_suit:
        return same_suit
    if is_first_trick:
        safe = [c for c in hand if not _is_point_card(c)]
        if safe:
            return safe
    return list(hand)


class HeartsEngine:
    """Hearts: strictly 4 players, 13 cards each from a standard deck.
    Built as a PartyEngine with TWO round shapes interleaved within one
    hand: a "passing" round is simultaneous (all 4 submit independently,
    like Trivia's everyone-answers shape) while a "trick" round is
    single-actor turn-based (like uno_engine.py's one-player-per-round
    reinterpretation) - is_round_over/apply_action branch on state["phase"]
    to use whichever shape applies. check_game_over ignores the generic
    round_index/total_rounds and ends the game once any player's RAW
    (uncapped, lower-is-better) point total reaches 100 after a complete
    hand; the per-hand points awarded back through time_up are inverted
    (26 - raw) so the shared scoreboard/FinalView's "higher score wins"
    convention still picks the real winner with zero special-casing.

    Deliberately out of scope for v1: no mid-passing card preview of what
    you're about to receive, no "blind" nullification variants, no
    configurable deck size - this is the standard 4-player game only."""

    kind = "hearts"
    MIN_PARTICIPANTS = 4
    MAX_PARTICIPANTS = 4
    DEFAULT_TOTAL_ROUNDS = 5000  # loop-safety cap only, see class docstring

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "hand_number": 0,
            "hands_completed": 0,
            "hands": {},
            "pass_direction": None,
            "pending_passes": {},
            "current_seat": 0,
            "current_trick": [],
            "lead_suit": None,
            "hearts_broken": False,
            "trick_number": 0,
            "tricks_won": {},
            "pending_action": None,
            "last_event": None,
            "hand_points": None,
            "raw_scores": {m: 0 for m in participant_ids},
            "winner": None,
            "next_phase": "passing",
        }

    def _deal_fresh_hand(self, state: dict) -> None:
        deck = _fresh_deck()
        random.shuffle(deck)
        participant_ids = state["participant_ids"]
        hands = {m: [] for m in participant_ids}
        for i, card in enumerate(deck):
            hands[participant_ids[i % 4]].append(card)
        state["hands"] = hands
        state["hand_number"] += 1
        state["pass_direction"] = PASS_DIRECTIONS[(state["hand_number"] - 1) % 4]
        state["pending_passes"] = {}
        state["current_trick"] = []
        state["lead_suit"] = None
        state["hearts_broken"] = False
        state["trick_number"] = 0
        state["tricks_won"] = {m: [] for m in participant_ids}
        state["pending_action"] = None
        state["hand_points"] = None

    def _seat_of_two_of_clubs(self, state: dict) -> int:
        for i, member_id in enumerate(state["participant_ids"]):
            if any(c["suit"] == "C" and c["rank"] == 2 for c in state["hands"][member_id]):
                return i
        return 0  # unreachable in a real 52-card deal

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        if state["phase"] in ("lobby", "hand_over"):
            self._deal_fresh_hand(state)
            if state["pass_direction"] == "hold":
                state["phase"] = "trick"
                state["current_seat"] = self._seat_of_two_of_clubs(state)
                return state, TRICK_DURATION_SECONDS
            state["phase"] = "passing"
            return state, PASS_DURATION_SECONDS

        next_phase = state["next_phase"]
        state["phase"] = next_phase
        state["pending_action"] = None
        return state, (PASS_DURATION_SECONDS if next_phase == "passing" else TRICK_DURATION_SECONDS)

    def parse_action(self, data: dict) -> dict:
        kind = data.get("action")
        if kind == "pass":
            card_ids = data.get("card_ids")
            if not isinstance(card_ids, list) or not all(isinstance(c, str) for c in card_ids):
                raise ValueError("Missing or invalid card_ids.")
            return {"kind": "pass", "card_ids": card_ids}
        if kind == "play_card":
            card_id = data.get("card_id")
            if not isinstance(card_id, str) or not card_id:
                raise ValueError("Missing or invalid card_id.")
            return {"kind": "play_card", "card_id": card_id}
        raise ValueError("Missing or invalid action.")

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] == "passing":
            if member_id not in state["participant_ids"]:
                raise IllegalAction("You're not in this game.")
            if member_id in state["pending_passes"]:
                raise IllegalAction("You've already chosen your cards to pass.")
            if action["kind"] != "pass":
                raise IllegalAction("A pass selection is expected right now.")
            card_ids = action["card_ids"]
            hand_ids = {c["id"] for c in state["hands"][member_id]}
            if len(card_ids) != 3 or len(set(card_ids)) != 3 or not set(card_ids) <= hand_ids:
                raise IllegalAction("Choose exactly 3 distinct cards from your own hand.")
            state = copy.deepcopy(state)
            state["pending_passes"][member_id] = card_ids
            return state

        if state["phase"] == "trick":
            current_player = state["participant_ids"][state["current_seat"]]
            if member_id != current_player:
                raise IllegalAction("It's not your turn.")
            if state["pending_action"] is not None:
                raise IllegalAction("You've already played a card this trick.")
            if action["kind"] != "play_card":
                raise IllegalAction("A card play is expected right now.")
            card = next((c for c in state["hands"][member_id] if c["id"] == action["card_id"]), None)
            if card is None:
                raise IllegalAction("That card isn't in your hand.")
            legal_ids = {c["id"] for c in _legal_cards(state["hands"][member_id], state)}
            if card["id"] not in legal_ids:
                raise IllegalAction("That card isn't legal to play right now.")
            state = copy.deepcopy(state)
            state["pending_action"] = {"kind": "play_card", "card_id": action["card_id"]}
            return state

        raise IllegalAction("No action is open right now.")

    def is_round_over(self, state: dict) -> bool:
        if state["phase"] == "passing":
            return len(state["pending_passes"]) >= 4
        if state["phase"] == "trick":
            return state["pending_action"] is not None
        return False

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] not in ("passing", "trick"):  # idempotency guard
            return state, {}
        state = copy.deepcopy(state)

        if state["phase"] == "passing":
            for member_id in state["participant_ids"]:
                if member_id not in state["pending_passes"]:
                    state["pending_passes"][member_id] = [c["id"] for c in state["hands"][member_id][:3]]

            direction = state["pass_direction"]
            offset = PASS_OFFSETS[direction]
            n = len(state["participant_ids"])
            outgoing: dict[str, list[dict]] = {}
            for i, member_id in enumerate(state["participant_ids"]):
                card_ids = state["pending_passes"][member_id]
                moving = [c for c in state["hands"][member_id] if c["id"] in card_ids]
                state["hands"][member_id] = [c for c in state["hands"][member_id] if c["id"] not in card_ids]
                recipient = state["participant_ids"][(i + offset) % n]
                outgoing.setdefault(recipient, []).extend(moving)
            for member_id, cards in outgoing.items():
                state["hands"][member_id].extend(cards)

            state["pending_passes"] = {}
            state["current_seat"] = self._seat_of_two_of_clubs(state)
            state["last_event"] = {"kind": "cards_passed", "direction": direction}
            state["next_phase"] = "trick"
            state["phase"] = "reveal"
            return state, {}

        # trick phase
        action = state["pending_action"]
        current_player = state["participant_ids"][state["current_seat"]]
        if action is None:
            card = _legal_cards(state["hands"][current_player], state)[0]
        else:
            card = next(c for c in state["hands"][current_player] if c["id"] == action["card_id"])

        state["hands"][current_player] = [c for c in state["hands"][current_player] if c["id"] != card["id"]]
        if not state["current_trick"]:
            state["lead_suit"] = card["suit"]
        state["current_trick"].append({"member_id": current_player, "card": card})
        if card["suit"] == "H":
            state["hearts_broken"] = True
        state["pending_action"] = None

        if len(state["current_trick"]) < 4:
            state["last_event"] = {"kind": "card_played", "member_id": current_player, "card": card}
            state["current_seat"] = (state["current_seat"] + 1) % 4
            state["next_phase"] = "trick"
            state["phase"] = "reveal"
            return state, {}

        # the trick is complete
        winning_entry = max(
            (e for e in state["current_trick"] if e["card"]["suit"] == state["lead_suit"]),
            key=lambda e: e["card"]["rank"],
        )
        winner = winning_entry["member_id"]
        won_cards = [e["card"] for e in state["current_trick"]]
        state["tricks_won"][winner].extend(won_cards)
        state["trick_number"] += 1
        state["current_trick"] = []
        state["lead_suit"] = None
        state["current_seat"] = state["participant_ids"].index(winner)

        if state["trick_number"] < 13:
            state["last_event"] = {"kind": "trick_won", "member_id": winner, "cards": won_cards}
            state["next_phase"] = "trick"
            state["phase"] = "reveal"
            return state, {}

        # the hand is complete - score it
        raw_points = {m: 0 for m in state["participant_ids"]}
        for m, cards in state["tricks_won"].items():
            raw_points[m] = sum(_card_points(c) for c in cards)
        moon_shooter = next((m for m, p in raw_points.items() if p == 26), None)
        if moon_shooter is not None:
            raw_points = {m: (0 if m == moon_shooter else 26) for m in state["participant_ids"]}

        state["raw_scores"] = {m: state["raw_scores"][m] + raw_points[m] for m in state["participant_ids"]}
        state["hand_points"] = raw_points
        state["hands_completed"] += 1
        state["last_event"] = {"kind": "trick_won", "member_id": winner, "cards": won_cards}
        state["phase"] = "hand_over"

        if max(state["raw_scores"].values()) >= TARGET_SCORE:
            state["winner"] = min(state["raw_scores"], key=state["raw_scores"].get)

        awarded = {m: 26 - raw_points[m] for m in state["participant_ids"]}
        return state, awarded

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return state.get("winner") is not None

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        n = len(state["participant_ids"])
        pass_to = None
        if state["phase"] == "passing" and viewer_member_id in state["participant_ids"] and state["pass_direction"] != "hold":
            seat = state["participant_ids"].index(viewer_member_id)
            offset = PASS_OFFSETS.get(state["pass_direction"])
            if offset is not None:
                pass_to = state["participant_ids"][(seat + offset) % n]

        base = {
            "phase": state["phase"],
            "hand_number": state["hand_number"],
            "pass_direction": state["pass_direction"],
            "pass_to_member_id": pass_to,
            "my_hand": state["hands"].get(viewer_member_id) if viewer_member_id else None,
            "hand_sizes": {m: len(h) for m, h in state["hands"].items()},
            "have_passed": viewer_member_id in state["pending_passes"] if viewer_member_id else False,
            "current_trick": [
                {"member_id": e["member_id"], "card": e["card"]} for e in state["current_trick"]
            ],
            "lead_suit": state["lead_suit"],
            "hearts_broken": state["hearts_broken"],
            "trick_number": state["trick_number"],
            "current_player_id": state["participant_ids"][state["current_seat"]]
            if state["phase"] == "trick"
            else None,
            "raw_scores": state["raw_scores"],
            "winner": state["winner"],
        }
        if state["phase"] == "hand_over":
            return {**base, "hand_points": state["hand_points"], "last_event": state["last_event"]}
        if state["phase"] == "reveal":
            return {**base, "hand_points": None, "last_event": state["last_event"]}
        return {**base, "hand_points": None, "last_event": None}

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        hand_points = state.get("hand_points") or {}
        rows = [
            {
                "member_id": m,
                "score": cumulative_scores.get(m, 0),
                "round_points": (26 - hand_points[m]) if m in hand_points else None,
                "answered": m in state.get("pending_passes", {}),
            }
            for m in state["participant_ids"]
        ]
        rows.sort(key=lambda r: -r["score"])
        return rows
