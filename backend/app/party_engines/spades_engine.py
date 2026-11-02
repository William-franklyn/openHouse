import copy
import random

from app.party_engines.base import IllegalAction

SUITS = ("C", "D", "H", "S")
BID_DURATION_SECONDS = 30
TRICK_DURATION_SECONDS = 30
TARGET_SCORE = 500


def _fresh_deck() -> list[dict]:
    return [{"id": f"{s}{r}", "suit": s, "rank": r} for s in SUITS for r in range(2, 15)]


def _legal_cards(hand: list[dict], state: dict) -> list[dict]:
    """Spades-specific legality, verified against a standalone script
    before being written here: spades can't be LED until broken (someone
    has played one on an earlier trick) unless the hand is nothing but
    spades; must follow the lead suit if able; no first-trick point-card
    restriction the way Hearts has, since spades carries no penalty
    cards to protect."""
    trick = state["current_trick"]
    if not trick:  # leading this trick
        if not state["spades_broken"]:
            non_spades = [c for c in hand if c["suit"] != "S"]
            if non_spades:
                return non_spades
        return list(hand)
    same_suit = [c for c in hand if c["suit"] == state["lead_suit"]]
    if same_suit:
        return same_suit
    return list(hand)


class SpadesEngine:
    """Spades: strictly 4 players in fixed partnerships (seats 0&2 vs
    seats 1&3 - seat order is participant join order, not chosen). Built
    as a PartyEngine with two round shapes interleaved within one hand,
    directly extending hearts_engine.py's pattern: a "bidding" round is
    simultaneous (all 4 submit independently, like Hearts' passing
    phase) and a "trick" round is single-actor turn-based (like Uno's
    one-turn-per-round reinterpretation). Spades is always trump - the
    highest spade played wins a trick over any non-spade, verified
    (along with bid scoring and the bag/sandbag penalty) against a
    standalone script before being written into the engine.

    Partnership scoring, not per-member: each hand, a team's combined
    bid (both partners' bids summed) is compared against their combined
    tricks taken - 10 points per bid trick if met (plus 1 per overtrick/
    "bag"), or the full negative value if not met. Every 10 accumulated
    bags costs an extra -100 (the classic "sandbagging" penalty). Unlike
    Hearts, higher is genuinely better here, so hand scores are awarded
    to party_games.py directly, no inversion needed - both teammates
    always receive the identical per-hand delta, keeping the generic
    per-member scores_json in sync with this engine's own per-team
    team_scores (tracked internally since check_game_over needs the
    real-time cumulative total, the same reason Hearts tracks raw_scores).

    Deliberately out of scope for v1: no "nil" bid bonus/penalty (a bid
    of 0 is just the floor of the normal 0-13 range), no blind nil, no
    partner selection (fixed by seat/join order)."""

    kind = "spades"
    MIN_PARTICIPANTS = 4
    MAX_PARTICIPANTS = 4
    DEFAULT_TOTAL_ROUNDS = 3000  # loop-safety cap only, see class docstring

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "hand_number": 0,
            "hands": {},
            "bids": {},
            "current_seat": 0,
            "current_trick": [],
            "lead_suit": None,
            "spades_broken": False,
            "trick_number": 0,
            "tricks_won_count": {},
            "pending_action": None,
            "last_event": None,
            "hand_results": None,
            "team_scores": {"team_a": 0, "team_b": 0},
            "team_bags": {"team_a": 0, "team_b": 0},
            "winner": None,
            "next_phase": "bidding",
        }

    def _team_of(self, state: dict, member_id: str) -> str | None:
        participant_ids = state["participant_ids"]
        if member_id not in participant_ids:
            return None
        return "team_a" if participant_ids.index(member_id) % 2 == 0 else "team_b"

    def _teams(self, state: dict) -> dict[str, list[str]]:
        p = state["participant_ids"]
        return {"team_a": [p[0], p[2]], "team_b": [p[1], p[3]]}

    def _seat_of_two_of_clubs(self, state: dict) -> int:
        for i, member_id in enumerate(state["participant_ids"]):
            if any(c["suit"] == "C" and c["rank"] == 2 for c in state["hands"][member_id]):
                return i
        return 0  # unreachable in a real 52-card deal

    def _deal_fresh_hand(self, state: dict) -> None:
        deck = _fresh_deck()
        random.shuffle(deck)
        participant_ids = state["participant_ids"]
        hands = {m: [] for m in participant_ids}
        for i, card in enumerate(deck):
            hands[participant_ids[i % 4]].append(card)
        state["hands"] = hands
        state["hand_number"] += 1
        state["bids"] = {}
        state["current_trick"] = []
        state["lead_suit"] = None
        state["spades_broken"] = False
        state["trick_number"] = 0
        state["tricks_won_count"] = {m: 0 for m in participant_ids}
        state["pending_action"] = None
        state["last_event"] = None
        state["hand_results"] = None

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        if state["phase"] in ("lobby", "hand_over"):
            self._deal_fresh_hand(state)
            state["phase"] = "bidding"
            return state, BID_DURATION_SECONDS

        next_phase = state["next_phase"]
        state["phase"] = next_phase
        state["pending_action"] = None
        return state, TRICK_DURATION_SECONDS

    def parse_action(self, data: dict) -> dict:
        kind = data.get("action")
        if kind == "bid":
            amount = data.get("amount")
            if not isinstance(amount, int) or isinstance(amount, bool) or not (0 <= amount <= 13):
                raise ValueError("Bid must be an integer between 0 and 13.")
            return {"kind": "bid", "amount": amount}
        if kind == "play_card":
            card_id = data.get("card_id")
            if not isinstance(card_id, str) or not card_id:
                raise ValueError("Missing or invalid card_id.")
            return {"kind": "play_card", "card_id": card_id}
        raise ValueError("Missing or invalid action.")

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] == "bidding":
            if member_id not in state["participant_ids"]:
                raise IllegalAction("You're not in this game.")
            if member_id in state["bids"]:
                raise IllegalAction("You've already bid this hand.")
            if action["kind"] != "bid":
                raise IllegalAction("A bid is expected right now.")
            state = copy.deepcopy(state)
            state["bids"][member_id] = action["amount"]
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
        if state["phase"] == "bidding":
            return set(state["participant_ids"]) <= set(state["bids"].keys())
        if state["phase"] == "trick":
            return state["pending_action"] is not None
        return False

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] not in ("bidding", "trick"):  # idempotency guard
            return state, {}
        state = copy.deepcopy(state)

        if state["phase"] == "bidding":
            for m in state["participant_ids"]:
                if m not in state["bids"]:
                    state["bids"][m] = 0  # AFK default: the safest possible bid
            state["current_seat"] = self._seat_of_two_of_clubs(state)
            state["last_event"] = {"kind": "bids_in", "bids": dict(state["bids"])}
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
        if card["suit"] == "S":
            state["spades_broken"] = True
        state["pending_action"] = None

        if len(state["current_trick"]) < 4:
            state["last_event"] = {"kind": "card_played", "member_id": current_player, "card": card}
            state["current_seat"] = (state["current_seat"] + 1) % 4
            state["next_phase"] = "trick"
            state["phase"] = "reveal"
            return state, {}

        # the trick is complete - spades always trump
        spades_played = [e for e in state["current_trick"] if e["card"]["suit"] == "S"]
        pool = spades_played if spades_played else [
            e for e in state["current_trick"] if e["card"]["suit"] == state["lead_suit"]
        ]
        winner = max(pool, key=lambda e: e["card"]["rank"])["member_id"]
        won_cards = [e["card"] for e in state["current_trick"]]
        state["tricks_won_count"][winner] += 1
        state["trick_number"] += 1
        state["current_trick"] = []
        state["lead_suit"] = None
        state["current_seat"] = state["participant_ids"].index(winner)

        if state["trick_number"] < 13:
            state["last_event"] = {"kind": "trick_won", "member_id": winner, "cards": won_cards}
            state["next_phase"] = "trick"
            state["phase"] = "reveal"
            return state, {}

        # the hand is complete - score both partnerships
        results = {}
        awarded: dict[str, int] = {}
        for team_name, members in self._teams(state).items():
            combined_bid = sum(state["bids"][m] for m in members)
            tricks_taken = sum(state["tricks_won_count"][m] for m in members)
            if tricks_taken >= combined_bid:
                bags = tricks_taken - combined_bid
                hand_score = combined_bid * 10 + bags
            else:
                bags = 0
                hand_score = -(combined_bid * 10)
            total_bags = state["team_bags"][team_name] + bags
            penalty = (total_bags // 10) * 100
            state["team_bags"][team_name] = total_bags % 10
            hand_score -= penalty
            state["team_scores"][team_name] += hand_score
            results[team_name] = {
                "combined_bid": combined_bid,
                "tricks_taken": tricks_taken,
                "hand_score": hand_score,
                "bag_penalty": penalty,
                "cumulative_score": state["team_scores"][team_name],
            }
            for m in members:
                awarded[m] = hand_score

        state["last_event"] = {"kind": "trick_won", "member_id": winner, "cards": won_cards}
        state["hand_results"] = results
        state["phase"] = "hand_over"

        if max(state["team_scores"].values()) >= TARGET_SCORE:
            state["winner"] = max(state["team_scores"], key=state["team_scores"].get)

        return state, awarded

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return state.get("winner") is not None

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        teams = self._teams(state) if len(state["participant_ids"]) == 4 else None
        my_team = self._team_of(state, viewer_member_id) if viewer_member_id else None

        base = {
            "phase": state["phase"],
            "hand_number": state["hand_number"],
            "teams": teams,
            "my_team": my_team,
            "my_hand": state["hands"].get(viewer_member_id) if viewer_member_id else None,
            "hand_sizes": {m: len(h) for m, h in state["hands"].items()},
            "my_bid": state["bids"].get(viewer_member_id) if viewer_member_id else None,
            "bids_submitted": list(state["bids"].keys()),
            "bids": dict(state["bids"]) if state["phase"] != "bidding" else None,
            "current_trick": [{"member_id": e["member_id"], "card": e["card"]} for e in state["current_trick"]],
            "lead_suit": state["lead_suit"],
            "spades_broken": state["spades_broken"],
            "trick_number": state["trick_number"],
            "current_player_id": state["participant_ids"][state["current_seat"]]
            if state["phase"] == "trick"
            else None,
            "team_scores": dict(state["team_scores"]),
            "team_bags": dict(state["team_bags"]),
            "winner": state["winner"],
        }
        if state["phase"] == "hand_over":
            return {**base, "hand_results": state["hand_results"], "last_event": state["last_event"]}
        if state["phase"] == "reveal":
            return {**base, "hand_results": None, "last_event": state["last_event"]}
        return {**base, "hand_results": None, "last_event": None}

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        return [
            {
                "member_id": m,
                "score": cumulative_scores.get(m, 0),
                "round_points": None,
                "answered": m in state.get("bids", {}) if state["phase"] == "bidding" else False,
                "team": self._team_of(state, m),
            }
            for m in state["participant_ids"]
        ]
