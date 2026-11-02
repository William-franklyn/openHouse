import copy
import random

from app.party_engines.base import IllegalAction

COLORS = ["Red", "Blue", "Green", "Yellow", "Purple"]
VALUES = [1, 2, 3]
COPIES_PER_VALUE = 10  # 5 colors * 3 values * 10 copies = 150 cards per scoring round - comfortably more than any supported table (8 players * 7-card hands = 56) will ever draw

HAND_SIZE = 7
NUM_SCORING_ROUNDS = 3
PICK_DURATION_SECONDS = 20
SET_BONUS_THRESHOLD = 3
SET_BONUS_POINTS = 2
RAINBOW_BONUS_POINTS = 5


def _fresh_deck() -> list[dict]:
    deck = []
    card_id = 0
    for color in COLORS:
        for value in VALUES:
            for _ in range(COPIES_PER_VALUE):
                deck.append({"id": f"c{card_id}", "color": color, "value": value})
                card_id += 1
    random.shuffle(deck)
    return deck


def _score_collection(cards: list[dict]) -> tuple[int, dict[str, int]]:
    base = sum(c["value"] for c in cards)
    counts: dict[str, int] = {}
    for c in cards:
        counts[c["color"]] = counts.get(c["color"], 0) + 1
    set_bonus = SET_BONUS_POINTS * sum(1 for v in counts.values() if v >= SET_BONUS_THRESHOLD)
    rainbow_bonus = RAINBOW_BONUS_POINTS if len(counts) == len(COLORS) else 0
    return base + set_bonus + rainbow_bonus, counts


class DraftEngine:
    """Card draft: every pick, each player secretly chooses one card from
    their current hand; once everyone's picked, hands are passed to the
    next seat and the cycle repeats until hands run out (one "scoring
    round" = exactly HAND_SIZE picks), then collected cards score via
    simple set-collection rules. NUM_SCORING_ROUNDS fresh hands are dealt
    in sequence; cumulative score across all of them decides the winner.

    Deliberately out of scope for v1: no draft-direction alternation
    (hands always pass to the same next-seat neighbor every scoring
    round, where some real booster-draft formats alternate direction
    each round), no card abilities/wilds - just color+value, kept simple
    enough to verify by hand before writing a single test.

    Built as a PartyEngine, not a CardEngine (see card_engines/base.py) -
    despite being about "cards," this has N participants acting in
    lockstep rounds with no persistent per-player chip stack and nothing
    resembling a betting turn, which is exactly PartyEngine's shape, not
    poker's."""

    kind = "draft"
    MIN_PARTICIPANTS = 2
    MAX_PARTICIPANTS = 8
    DEFAULT_TOTAL_ROUNDS = HAND_SIZE * NUM_SCORING_ROUNDS

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "scoring_round": 0,
            "pick_in_round": 0,
            "hands": {},
            "collected": {m: [] for m in participant_ids},
            "current_picks": {},
            "last_round_summary": None,
        }

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        starting_new_scoring_round = round_index % HAND_SIZE == 0
        if starting_new_scoring_round:
            deck = _fresh_deck()
            state["hands"] = {m: [deck.pop() for _ in range(HAND_SIZE)] for m in state["participant_ids"]}
            state["collected"] = {m: [] for m in state["participant_ids"]}
            state["scoring_round"] = round_index // HAND_SIZE
            state["pick_in_round"] = 0
        else:
            state["pick_in_round"] += 1
        state["current_picks"] = {}
        state["last_round_summary"] = None
        state["phase"] = "picking"
        return state, PICK_DURATION_SECONDS

    def parse_action(self, data: dict) -> dict:
        card_id = data.get("card_id")
        if not isinstance(card_id, str) or not card_id:
            raise ValueError("Missing or invalid card_id.")
        return {"card_id": card_id}

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] != "picking":
            raise IllegalAction("Picking isn't open right now.")
        if member_id in state["current_picks"]:
            raise IllegalAction("You've already picked this round.")
        card_id = action["card_id"]
        hand = state["hands"].get(member_id, [])
        card = next((c for c in hand if c["id"] == card_id), None)
        if card is None:
            raise IllegalAction("That card isn't in your hand.")
        state = copy.deepcopy(state)
        state["current_picks"][member_id] = card
        return state

    def is_round_over(self, state: dict) -> bool:
        return state["phase"] == "picking" and len(state["current_picks"]) >= len(state["participant_ids"])

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] != "picking":  # idempotency guard - timer/early-finish race
            return state, {}
        state = copy.deepcopy(state)

        # Auto-pick the first remaining card for anyone who hasn't chosen -
        # drafting can't proceed with a missing pick the way trivia
        # tolerates a missing answer, since the hand has to keep moving.
        for member_id in state["participant_ids"]:
            if member_id not in state["current_picks"]:
                hand = state["hands"][member_id]
                if hand:
                    state["current_picks"][member_id] = hand[0]

        for member_id, card in state["current_picks"].items():
            state["collected"][member_id].append(card)
            state["hands"][member_id] = [c for c in state["hands"][member_id] if c["id"] != card["id"]]

        scoring_round_finished = state["pick_in_round"] == HAND_SIZE - 1
        if not scoring_round_finished:
            # Pass each player's remaining hand to the next seat.
            n = len(state["participant_ids"])
            old_hands = state["hands"]
            new_hands = {}
            for i, member_id in enumerate(state["participant_ids"]):
                giver = state["participant_ids"][(i - 1) % n]
                new_hands[member_id] = old_hands[giver]
            state["hands"] = new_hands
            state["phase"] = "reveal"
            return state, {}

        points_awarded = {}
        summary = {}
        for member_id in state["participant_ids"]:
            score, counts = _score_collection(state["collected"][member_id])
            points_awarded[member_id] = score
            summary[member_id] = {"collected": state["collected"][member_id], "score": score, "colors": counts}
        state["last_round_summary"] = summary
        state["phase"] = "scoring_round_over"
        return state, points_awarded

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return round_index >= total_rounds - 1

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        base = {
            "phase": state["phase"],
            "scoring_round": state["scoring_round"],
            "num_scoring_rounds": NUM_SCORING_ROUNDS,
            "pick_in_round": state["pick_in_round"],
            "hand_size": HAND_SIZE,
        }
        if state["phase"] == "scoring_round_over":
            return {**base, "round_results": state["last_round_summary"]}

        display = {
            **base,
            "my_hand": state["hands"].get(viewer_member_id) if viewer_member_id else None,
            "my_pick": state["current_picks"].get(viewer_member_id) if viewer_member_id else None,
            "my_collected": state["collected"].get(viewer_member_id) if viewer_member_id else None,
            "picked_member_ids": list(state["current_picks"].keys()),
            "collected_counts": {m: len(state["collected"].get(m, [])) for m in state["participant_ids"]},
        }
        if state["phase"] == "reveal":
            display["revealed_picks"] = state["current_picks"]
        return display

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        awarded = (state.get("last_round_summary") or {})
        rows = [
            {
                "member_id": m,
                "score": cumulative_scores.get(m, 0),
                "round_points": awarded.get(m, {}).get("score") if m in awarded else None,
                "answered": m in state["current_picks"],
            }
            for m in state["participant_ids"]
        ]
        rows.sort(key=lambda r: -r["score"])
        return rows
