import copy
import random

from app.party_engines.base import IllegalAction

COLORS = ["Red", "Blue", "Green", "Yellow"]
NUM_HANDS = 3
TURN_DURATION_SECONDS = 20
SPECIAL_CARD_POINTS = 20
WILD_CARD_POINTS = 50


def _fresh_deck() -> list[dict]:
    deck = []
    card_id = 0

    def add(color, kind, value=None):
        nonlocal card_id
        deck.append({"id": f"c{card_id}", "color": color, "kind": kind, "value": value})
        card_id += 1

    for color in COLORS:
        add(color, "number", 0)
        for value in range(1, 10):
            add(color, "number", value)
            add(color, "number", value)
        for kind in ("skip", "reverse", "draw2"):
            add(color, kind)
            add(color, kind)
    for _ in range(4):
        add("Wild", "wild")
    for _ in range(4):
        add("Wild", "wild_draw4")

    random.shuffle(deck)
    return deck


def _card_points(card: dict) -> int:
    if card["kind"] == "number":
        return card["value"]
    if card["kind"] in ("skip", "reverse", "draw2"):
        return SPECIAL_CARD_POINTS
    return WILD_CARD_POINTS


def _draw_one(state: dict) -> dict:
    """Pops one card off the draw pile, reshuffling the discard pile
    (everything except its current top card) back into a fresh draw pile
    first if it's empty - verified against a real draw/discard drain
    before being written here."""
    if not state["draw_pile"]:
        top = state["discard_pile"][-1]
        rest = state["discard_pile"][:-1]
        random.shuffle(rest)
        state["draw_pile"] = rest
        state["discard_pile"] = [top]
    return state["draw_pile"].pop()


def _can_play(card: dict, active_color: str, top: dict) -> bool:
    if card["color"] == "Wild":
        return True
    if card["color"] == active_color:
        return True
    if card["kind"] != "number" and card["kind"] == top["kind"]:
        return True
    if card["kind"] == "number" and top["kind"] == "number" and card["value"] == top["value"]:
        return True
    return False


def _next_seat(current_seat: int, direction: int, n: int, steps: int = 1) -> int:
    return (current_seat + direction * steps) % n


class UnoEngine:
    """Uno: N players, strict turn rotation (not simultaneous like Trivia/
    Draft), a shared hand each, playing toward an empty hand. Built as a
    PartyEngine anyway - "round" here means "one player's turn", not "one
    synchronized action from everyone": is_round_over fires the moment
    the SINGLE player whose turn it is has acted (apply_action rejects
    anyone else, mirroring how PokerEngine enforces its own turn order
    despite CardEngine's protocol not requiring it either). This also
    means check_game_over ignores the generic round_index/total_rounds
    counter entirely (a hand's length varies - it isn't bounded the way
    Draft's fixed-size picks are) and checks its own hands_completed
    counter instead; DEFAULT_TOTAL_ROUNDS is just a generous loop-safety
    cap, not a meaningful gameplay parameter.

    Deliberately out of scope for v1: no "UNO!" call-out penalty, no
    stacking draw cards, no jump-in rule, no legality restriction on
    playing a Wild Draw Four, no race-to-500 scoring - a fixed
    NUM_HANDS=3 instead, same predictable shape as Draft's three rounds."""

    kind = "uno"
    MIN_PARTICIPANTS = 2
    MAX_PARTICIPANTS = 8
    DEFAULT_TOTAL_ROUNDS = 2000  # loop-safety cap only, see class docstring

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "hand_number": 0,
            "hands_completed": 0,
            "hands": {},
            "draw_pile": [],
            "discard_pile": [],
            "active_color": None,
            "direction": 1,
            "current_seat": 0,
            "pending_action": None,
            "last_hand_summary": None,
            # What the last-acting player did, shown during the "reveal"
            # pause between turns - also the idempotency signal: time_up
            # always moves OUT of "turn" (into "reveal" or "hand_over"),
            # so a second call sees phase != "turn" and no-ops correctly,
            # unlike leaving phase as "turn" for the next player's turn,
            # which would make a genuine new turn indistinguishable from
            # an already-resolved one.
            "last_action": None,
        }

    def _deal_fresh_hand(self, state: dict) -> None:
        deck = _fresh_deck()
        state["hands"] = {m: [deck.pop() for _ in range(7)] for m in state["participant_ids"]}
        # Find the first non-wild card to open the discard pile with - never
        # start a hand with an active Draw Four/Wild forcing an effect
        # before anyone's had a turn.
        starter_index = next(i for i, c in enumerate(deck) if c["color"] != "Wild")
        starter = deck.pop(starter_index)
        state["draw_pile"] = deck
        state["discard_pile"] = [starter]
        state["active_color"] = starter["color"]
        state["direction"] = 1
        state["current_seat"] = state["hand_number"] % len(state["participant_ids"])
        state["hand_number"] += 1
        state["pending_action"] = None
        state["last_hand_summary"] = None

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        if state["phase"] in ("lobby", "hand_over"):
            self._deal_fresh_hand(state)
        state["pending_action"] = None
        state["phase"] = "turn"
        return state, TURN_DURATION_SECONDS

    def parse_action(self, data: dict) -> dict:
        kind = data.get("action")
        if kind == "draw":
            return {"kind": "draw"}
        if kind == "play":
            card_id = data.get("card_id")
            if not isinstance(card_id, str) or not card_id:
                raise ValueError("Missing or invalid card_id.")
            chosen_color = data.get("chosen_color")
            if chosen_color is not None and chosen_color not in COLORS:
                raise ValueError("Invalid chosen_color.")
            return {"kind": "play", "card_id": card_id, "chosen_color": chosen_color}
        raise ValueError("Missing or invalid action.")

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] != "turn":
            raise IllegalAction("No turn is open right now.")
        current_player = state["participant_ids"][state["current_seat"]]
        if member_id != current_player:
            raise IllegalAction("It's not your turn.")
        if state["pending_action"] is not None:
            raise IllegalAction("You've already acted this turn.")

        state = copy.deepcopy(state)
        if action["kind"] == "draw":
            state["pending_action"] = {"kind": "draw"}
            return state

        hand = state["hands"][member_id]
        card = next((c for c in hand if c["id"] == action["card_id"]), None)
        if card is None:
            raise IllegalAction("That card isn't in your hand.")
        top = state["discard_pile"][-1]
        if not _can_play(card, state["active_color"], top):
            raise IllegalAction("That card doesn't match the active color or the top of the pile.")
        if card["color"] == "Wild" and action.get("chosen_color") is None:
            raise IllegalAction("Choose a color to play a wild card.")

        state["pending_action"] = {"kind": "play", "card": card, "chosen_color": action.get("chosen_color")}
        return state

    def is_round_over(self, state: dict) -> bool:
        return state["phase"] == "turn" and state["pending_action"] is not None

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] != "turn":  # idempotency guard - timer/early-finish race
            return state, {}
        state = copy.deepcopy(state)
        n = len(state["participant_ids"])
        current_player = state["participant_ids"][state["current_seat"]]

        action = state["pending_action"] or {"kind": "draw"}  # AFK default: draw and pass
        if action["kind"] == "draw":
            state["hands"][current_player].append(_draw_one(state))
            state["current_seat"] = _next_seat(state["current_seat"], state["direction"], n)
            state["pending_action"] = None
            state["last_action"] = {"member_id": current_player, "kind": "draw", "card": None}
            state["phase"] = "reveal"
            return state, {}

        card = action["card"]
        state["hands"][current_player] = [c for c in state["hands"][current_player] if c["id"] != card["id"]]
        state["discard_pile"].append(card)
        state["active_color"] = action["chosen_color"] or card["color"]
        state["last_action"] = {"member_id": current_player, "kind": "play", "card": card}

        if not state["hands"][current_player]:
            opponents_points = sum(
                _card_points(c)
                for m, hand in state["hands"].items()
                if m != current_player
                for c in hand
            )
            hand_sizes = {m: len(h) for m, h in state["hands"].items()}
            state["last_hand_summary"] = {
                "winner_member_id": current_player,
                "points": opponents_points,
                "hand_sizes": hand_sizes,
            }
            state["hands_completed"] += 1
            state["phase"] = "hand_over"
            state["pending_action"] = None
            return state, {current_player: opponents_points}

        if card["kind"] == "reverse" and n == 2:
            next_seat = state["current_seat"]  # acts as a skip with exactly 2 players
        elif card["kind"] == "reverse":
            state["direction"] *= -1
            next_seat = _next_seat(state["current_seat"], state["direction"], n)
        elif card["kind"] == "skip":
            next_seat = _next_seat(state["current_seat"], state["direction"], n, steps=2)
        elif card["kind"] == "draw2":
            victim = state["participant_ids"][_next_seat(state["current_seat"], state["direction"], n)]
            state["hands"][victim].extend(_draw_one(state) for _ in range(2))
            next_seat = _next_seat(state["current_seat"], state["direction"], n, steps=2)
        elif card["kind"] == "wild_draw4":
            victim = state["participant_ids"][_next_seat(state["current_seat"], state["direction"], n)]
            state["hands"][victim].extend(_draw_one(state) for _ in range(4))
            next_seat = _next_seat(state["current_seat"], state["direction"], n, steps=2)
        else:
            next_seat = _next_seat(state["current_seat"], state["direction"], n)

        state["current_seat"] = next_seat
        state["pending_action"] = None
        state["phase"] = "reveal"
        return state, {}

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return state["hands_completed"] >= NUM_HANDS

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        base = {
            "phase": state["phase"],
            "hand_number": state["hand_number"],
            "num_hands": NUM_HANDS,
        }
        if state["phase"] == "hand_over":
            return {**base, "hand_result": state["last_hand_summary"]}

        return {
            **base,
            "my_hand": state["hands"].get(viewer_member_id) if viewer_member_id else None,
            "hand_sizes": {m: len(h) for m, h in state["hands"].items()},
            "discard_top": state["discard_pile"][-1] if state["discard_pile"] else None,
            "active_color": state["active_color"],
            "direction": state["direction"],
            "current_player_id": state["participant_ids"][state["current_seat"]],
            "draw_pile_size": len(state["draw_pile"]),
            "last_action": state["last_action"] if state["phase"] == "reveal" else None,
        }

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        summary = state.get("last_hand_summary")
        winner = summary["winner_member_id"] if summary else None
        current_player = state["participant_ids"][state["current_seat"]] if state["phase"] == "turn" else None
        rows = [
            {
                "member_id": m,
                "score": cumulative_scores.get(m, 0),
                "round_points": summary["points"] if (summary and m == winner) else (0 if summary else None),
                "answered": m == current_player and state.get("pending_action") is not None,
            }
            for m in state["participant_ids"]
        ]
        rows.sort(key=lambda r: -r["score"])
        return rows
