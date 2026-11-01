import copy

from app.card_engines.base import IllegalAction
from app.card_engines.poker_cards import best_hand, hand_description, shuffled_deck

STREET_AFTER = {"preflop": "flop", "flop": "turn", "turn": "river", "river": "showdown"}
CARDS_DEALT_ON_STREET = {"flop": 3, "turn": 1, "river": 1}


def _compute_pots(total_bet_this_hand: dict[str, int], folded: list[str]) -> list[tuple[int, list[str]]]:
    """Returns [(pot_amount, eligible_winner_ids), ...], main pot first, one
    entry per distinct all-in stack depth. See the module docstring in
    PokerEngine for why this can't just be a single pot."""
    folded_set = set(folded)
    contributors = {m: b for m, b in total_bet_this_hand.items() if b > 0}
    if not contributors:
        return []
    levels = sorted(set(contributors.values()))
    pots = []
    prev_level = 0
    for level in levels:
        tier = level - prev_level
        prev_level = level
        if tier <= 0:
            continue
        payers = [m for m, b in contributors.items() if b >= level]
        amount = tier * len(payers)
        eligible = [m for m in payers if m not in folded_set]
        if amount > 0:
            pots.append((amount, eligible))
    return pots


def _next_active_seat(participant_ids: list[str], from_index: int, skip: set[str]) -> int | None:
    n = len(participant_ids)
    for offset in range(1, n + 1):
        idx = (from_index + offset) % n
        if participant_ids[idx] not in skip:
            return idx
    return None


class PokerEngine:
    """Texas Hold'em. Chips are play money, not real currency - there is no
    buy-in/cash-out, only a starting stack configured at table creation;
    a player who hits 0 chips is simply out for the rest of this sitting.

    Deliberately out of scope for v1 (documented here, not silently
    missing): no turn clock/auto-fold-on-timeout (every other engine's
    timer need was a FIXED round; a poker decision has no natural fixed
    length, so this would need its own design pass), no tournament
    structure (blinds never increase), no run-it-twice. The one real
    betting-rules simplification: a short all-in (less than a full raise)
    still reopens action for every other player, where strict casino
    rules would NOT reopen it for players who already called the
    previous bet - slightly more generous to the table, never unfair to
    any individual player, and much simpler to implement correctly."""

    kind = "poker"
    MIN_PARTICIPANTS = 2
    MAX_PARTICIPANTS = 8

    def initial_state(self, participant_ids: list[str], starting_chips: int) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "dealer_index": -1,  # start_hand's rotation makes seat 0 the first dealer
            "hand_number": 0,
            "small_blind": max(1, starting_chips // 200),
            "big_blind": max(2, starting_chips // 100),
            "chip_stacks": {m: starting_chips for m in participant_ids},
            "deck": [],
            "hole_cards": {},
            "community_cards": [],
            "folded": [],
            "all_in": [],
            "sitting_out": [],
            "total_bet_this_hand": {},
            "bets_this_street": {},
            "acted_this_street": [],
            "current_bet": 0,
            "min_raise": 0,
            "action_on": None,
            "last_aggressor": None,
            "showdown": None,
            "pot_summary": None,
        }

    def start_hand(self, state: dict) -> dict:
        state = copy.deepcopy(state)
        active = [m for m in state["participant_ids"] if state["chip_stacks"][m] > 0]
        if len(active) < 2:
            raise IllegalAction("Not enough players with chips to start a hand.")

        state["sitting_out"] = [m for m in state["participant_ids"] if state["chip_stacks"][m] <= 0]
        state["dealer_index"] = _next_active_seat(
            state["participant_ids"], state["dealer_index"], set(state["sitting_out"])
        )
        state["hand_number"] += 1
        state["deck"] = shuffled_deck()
        state["hole_cards"] = {m: [state["deck"].pop(), state["deck"].pop()] for m in active}
        state["community_cards"] = []
        state["folded"] = []
        state["all_in"] = []
        state["total_bet_this_hand"] = {m: 0 for m in active}
        state["bets_this_street"] = {}
        state["acted_this_street"] = []
        state["showdown"] = None
        state["pot_summary"] = None

        sb, bb = state["small_blind"], state["big_blind"]
        skip = set(state["sitting_out"])
        if len(active) == 2:
            # Heads-up: the dealer posts small blind and acts first preflop
            # (and last on every later street) - the one seating exception
            # in the whole game.
            sb_seat, bb_seat = state["dealer_index"], _next_active_seat(state["participant_ids"], state["dealer_index"], skip)
        else:
            sb_seat = _next_active_seat(state["participant_ids"], state["dealer_index"], skip)
            bb_seat = _next_active_seat(state["participant_ids"], sb_seat, skip)
        sb_id, bb_id = state["participant_ids"][sb_seat], state["participant_ids"][bb_seat]

        self._post_blind(state, sb_id, sb)
        self._post_blind(state, bb_id, bb)
        state["current_bet"] = state["bets_this_street"].get(bb_id, 0)
        state["min_raise"] = bb
        state["last_aggressor"] = bb_id

        if len(active) == 2:
            first_to_act_seat = state["dealer_index"]
        else:
            first_to_act_seat = _next_active_seat(state["participant_ids"], bb_seat, skip)
        state["action_on"] = state["participant_ids"][first_to_act_seat]
        state["phase"] = "preflop"
        self._skip_to_next_actionable_player(state)
        return state

    def _post_blind(self, state: dict, member_id: str, amount: int) -> None:
        pay = min(amount, state["chip_stacks"][member_id])
        state["bets_this_street"][member_id] = state["bets_this_street"].get(member_id, 0) + pay
        state["total_bet_this_hand"][member_id] += pay
        state["chip_stacks"][member_id] -= pay
        if state["chip_stacks"][member_id] == 0:
            state["all_in"].append(member_id)

    def parse_action(self, data: dict) -> dict:
        kind = data.get("action")
        if kind not in ("fold", "check", "call", "raise"):
            raise ValueError("Missing or invalid action.")
        if kind == "raise":
            to = data.get("to")
            if not isinstance(to, int) or isinstance(to, bool) or to < 0:
                raise ValueError("Missing or invalid raise amount.")
            return {"kind": "raise", "to": to}
        return {"kind": kind}

    def _active_in_hand(self, state: dict) -> list[str]:
        excluded = set(state["folded"]) | set(state["sitting_out"])
        return [m for m in state["participant_ids"] if m not in excluded]

    def legal_actions(self, state: dict, member_id: str) -> dict:
        if state["action_on"] != member_id:
            return {"actions": [], "call_amount": 0, "min_raise_to": None, "max_raise_to": None}
        owed = state["current_bet"] - state["bets_this_street"].get(member_id, 0)
        stack = state["chip_stacks"][member_id]
        actions = ["fold"]
        actions.append("check" if owed <= 0 else "call")
        if stack > max(0, owed):
            actions.append("raise")
        min_raise_to = state["current_bet"] + state["min_raise"]
        max_raise_to = state["bets_this_street"].get(member_id, 0) + stack
        return {
            "actions": actions,
            "call_amount": max(0, min(owed, stack)),
            "min_raise_to": min(min_raise_to, max_raise_to) if "raise" in actions else None,
            "max_raise_to": max_raise_to if "raise" in actions else None,
        }

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] not in ("preflop", "flop", "turn", "river"):
            raise IllegalAction("No betting is open right now.")
        if state["action_on"] != member_id:
            raise IllegalAction("It's not your turn.")
        state = copy.deepcopy(state)
        kind = action["kind"]
        owed = state["current_bet"] - state["bets_this_street"].get(member_id, 0)
        stack = state["chip_stacks"][member_id]

        if kind == "fold":
            state["folded"].append(member_id)
        elif kind == "check":
            if owed > 0:
                raise IllegalAction("You can't check - there's a bet to call.")
        elif kind == "call":
            pay = min(max(owed, 0), stack)
            self._put_in_pot(state, member_id, pay)
        elif kind == "raise":
            to = action["to"]
            max_to = state["bets_this_street"].get(member_id, 0) + stack
            min_to = state["current_bet"] + state["min_raise"]
            if to > max_to:
                raise IllegalAction("You don't have enough chips for that raise.")
            if to < state["current_bet"] + 1:
                raise IllegalAction("A raise has to increase the bet.")
            if to < min_to and to < max_to:
                raise IllegalAction(f"The minimum raise is to {min_to}.")
            pay = to - state["bets_this_street"].get(member_id, 0)
            self._put_in_pot(state, member_id, pay)
            if to > state["current_bet"]:
                state["min_raise"] = max(state["min_raise"], to - state["current_bet"])
                state["current_bet"] = to
                state["last_aggressor"] = member_id
                state["acted_this_street"] = []

        if member_id not in state["acted_this_street"]:
            state["acted_this_street"].append(member_id)

        active = self._active_in_hand(state)
        if len(active) <= 1:
            state["phase"] = "hand_over"
            state["action_on"] = None
            return state

        self._advance(state)
        return state

    def _put_in_pot(self, state: dict, member_id: str, pay: int) -> None:
        state["bets_this_street"][member_id] = state["bets_this_street"].get(member_id, 0) + pay
        state["total_bet_this_hand"][member_id] += pay
        state["chip_stacks"][member_id] -= pay
        if state["chip_stacks"][member_id] == 0 and member_id not in state["all_in"]:
            state["all_in"].append(member_id)

    def _street_complete(self, state: dict) -> bool:
        active = self._active_in_hand(state)
        contestants = [m for m in active if m not in state["all_in"]]
        for m in contestants:
            if m not in state["acted_this_street"]:
                return False
            if state["bets_this_street"].get(m, 0) != state["current_bet"]:
                return False
        return True

    def _advance(self, state: dict) -> None:
        if not self._street_complete(state):
            self._move_action_to_next_player(state)
            return

        active = self._active_in_hand(state)
        contestants = [m for m in active if m not in state["all_in"]]
        if len(contestants) <= 1:
            # Nobody left who can still be bet into - deal out the rest of
            # the board with no further betting ("running it out").
            while state["phase"] != "river":
                self._deal_next_street(state)
            state["phase"] = "showdown"
            state["action_on"] = None
            return

        if state["phase"] == "river":
            state["phase"] = "showdown"
            state["action_on"] = None
            return

        self._deal_next_street(state)
        state["bets_this_street"] = {}
        state["acted_this_street"] = []
        state["current_bet"] = 0
        state["min_raise"] = state["big_blind"]
        state["action_on"] = None
        skip = set(state["folded"]) | set(state["sitting_out"]) | set(state["all_in"])
        first_seat = _next_active_seat(state["participant_ids"], state["dealer_index"], skip)
        if first_seat is not None:
            state["action_on"] = state["participant_ids"][first_seat]

    def _deal_next_street(self, state: dict) -> None:
        state["phase"] = STREET_AFTER[state["phase"]]
        for _ in range(CARDS_DEALT_ON_STREET.get(state["phase"], 0)):
            state["community_cards"].append(state["deck"].pop())

    def _move_action_to_next_player(self, state: dict) -> None:
        skip = set(state["folded"]) | set(state["sitting_out"]) | set(state["all_in"])
        current_seat = state["participant_ids"].index(state["action_on"])
        next_seat = _next_active_seat(state["participant_ids"], current_seat, skip)
        state["action_on"] = state["participant_ids"][next_seat] if next_seat is not None else None

    def _skip_to_next_actionable_player(self, state: dict) -> None:
        """After posting blinds, action_on might land on an all-in-from-the-
        blind player - walk forward until it's someone who can actually act,
        same traversal apply_action uses mid-street."""
        skip = set(state["folded"]) | set(state["sitting_out"]) | set(state["all_in"])
        if state["action_on"] in skip:
            seat = state["participant_ids"].index(state["action_on"])
            next_seat = _next_active_seat(state["participant_ids"], seat, skip)
            state["action_on"] = state["participant_ids"][next_seat] if next_seat is not None else None

    def is_hand_over(self, state: dict) -> bool:
        return state["phase"] in ("hand_over", "showdown")

    def resolve_hand(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] not in ("hand_over", "showdown"):
            return state, {}
        state = copy.deepcopy(state)
        pots = _compute_pots(state["total_bet_this_hand"], state["folded"])
        deltas = {m: 0 for m in state["participant_ids"]}
        showdown = {}
        active = self._active_in_hand(state)

        if len(active) == 1:
            winner = active[0]
            for amount, _eligible in pots:
                deltas[winner] += amount
        else:
            hand_values = {m: best_hand(state["hole_cards"][m] + state["community_cards"]) for m in active}
            for m, value in hand_values.items():
                showdown[m] = {
                    "hole_cards": state["hole_cards"][m],
                    "description": hand_description(value),
                }
            pot_summary = []
            for amount, eligible in pots:
                if not eligible:
                    continue
                best_value = max(hand_values[m] for m in eligible)
                winners = [m for m in eligible if hand_values[m] == best_value]
                share, remainder = divmod(amount, len(winners))
                for i, w in enumerate(winners):
                    deltas[w] += share + (1 if i < remainder else 0)
                pot_summary.append({"amount": amount, "winners": winners, "eligible": eligible})
            state["pot_summary"] = pot_summary

        for m, delta in deltas.items():
            state["chip_stacks"][m] += delta
        state["showdown"] = showdown or None
        state["phase"] = "hand_over"
        state["action_on"] = None
        return state, deltas

    def is_game_over(self, chip_stacks: dict[str, int]) -> bool:
        return sum(1 for v in chip_stacks.values() if v > 0) <= 1

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        def seat_view(m: str) -> dict:
            hole = None
            if m == viewer_member_id and m in state["hole_cards"]:
                hole = state["hole_cards"][m]
            elif state["phase"] == "hand_over" and state.get("showdown") and m in state["showdown"]:
                hole = state["showdown"][m]["hole_cards"]
            return {
                "member_id": m,
                "chips": state["chip_stacks"][m],
                "bet_this_street": state["bets_this_street"].get(m, 0),
                "folded": m in state["folded"],
                "all_in": m in state["all_in"],
                "sitting_out": m in state["sitting_out"],
                "hole_cards": hole,
                "hand_description": (state.get("showdown") or {}).get(m, {}).get("description"),
            }

        pot = sum(state["total_bet_this_hand"].values())
        legal = self.legal_actions(state, viewer_member_id) if viewer_member_id else {"actions": []}
        return {
            "phase": state["phase"],
            "hand_number": state["hand_number"],
            "dealer_index": state["dealer_index"],
            "small_blind": state["small_blind"],
            "big_blind": state["big_blind"],
            "community_cards": state["community_cards"],
            "pot": pot,
            "current_bet": state["current_bet"],
            "action_on": state["action_on"],
            "seats": [seat_view(m) for m in state["participant_ids"]],
            "my_legal_actions": legal,
            "pot_summary": state["pot_summary"],
        }
