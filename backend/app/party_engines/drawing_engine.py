import copy
import json
import random
import time
from pathlib import Path

from app.party_engines.base import IllegalAction

DRAW_DURATION_SECONDS = 75
ROUNDS_PER_PLAYER = 2
BASE_POINTS = 500
MIN_SCORE_FRACTION = 0.3
DRAWER_POINTS_PER_GUESSER = 50

_WORDS_PATH = Path(__file__).parent / "drawing_words.json"
_WORDS: list[str] = json.loads(_WORDS_PATH.read_text(encoding="utf-8"))


def _pick_word(already_used: list[str]) -> str:
    used = set(already_used)
    pool = [w for w in _WORDS if w not in used]
    if not pool:
        pool = _WORDS  # exhausted the bank - allow repeats rather than erroring
    return random.choice(pool)


def _mask_word(word: str) -> str:
    return " ".join("_" if c != " " else " " for c in word)


def _points_for(guessed_at_ms: int, started_at_ms: int, deadline_ms: int) -> int:
    duration = max(1, deadline_ms - started_at_ms)
    elapsed = max(0, min(duration, guessed_at_ms - started_at_ms))
    fraction_remaining = 1 - (elapsed / duration)
    scaled = MIN_SCORE_FRACTION + (1 - MIN_SCORE_FRACTION) * fraction_remaining
    return round(BASE_POINTS * scaled)


class DrawingEngine:
    """Drawing & Guess: one player draws each turn (on a shared canvas -
    the actual pen strokes are NOT part of this engine or PartyGame
    state at all; they're relayed live by realtime.py's draw_stroke/
    draw_clear handlers directly between clients, the same "ephemeral,
    no persistence" shape already used for WebRTC call signaling,
    because a continuous stream of pointer coordinates has nothing in
    common with a discrete per-round action and would be wildly
    inefficient to route through the generic party_state rebuild-and-
    broadcast machinery). This engine only owns the turn-based *game*
    around that canvas: whose turn it is, the secret word, the live
    guess feed, and scoring - built as a single round-type PartyEngine
    (unlike Werewolf/Spades/Hearts, there's no second phase to
    interleave, so start_round never needs a next_phase field at all).

    Guessing is simultaneous-but-open-ended, closer to Trivia's
    "everyone acts independently" shape than Uno's turn order: any
    non-drawer may guess repeatedly until they get it right (unlike
    Trivia's one-shot answer) or the clock runs out. is_round_over
    fires once every non-drawer has guessed correctly. The drawer
    scores a flat amount per correct guesser; guessers score on speed,
    reusing Trivia's bonus curve, verified against a standalone script
    before being written here.

    Deliberately out of scope for v1: no fuzzy/typo-tolerant guess
    matching (exact, case/whitespace-insensitive only), no word-choice
    menu for the drawer (one word is assigned automatically), no replay
    of strokes drawn before a guesser reconnects mid-turn."""

    kind = "drawing"
    MIN_PARTICIPANTS = 3
    DEFAULT_TOTAL_ROUNDS = 500  # loop-safety cap only, see class docstring

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "drawer_sequence": [],
            "turn_index": 0,
            "turns_completed": 0,
            "used_words": [],
            "current_drawer": None,
            "secret_word": None,
            "round_started_at_ms": None,
            "round_deadline_ms": None,
            "guess_log": [],
            "correct_guessers": {},
            "last_event": None,
        }

    def _begin_drawing_turn(self, state: dict) -> None:
        drawer = state["drawer_sequence"][state["turn_index"]]
        word = _pick_word(state["used_words"])
        state["used_words"].append(word)
        state["current_drawer"] = drawer
        state["secret_word"] = word
        now_ms = int(time.time() * 1000)
        state["round_started_at_ms"] = now_ms
        state["round_deadline_ms"] = now_ms + DRAW_DURATION_SECONDS * 1000
        state["guess_log"] = []
        state["correct_guessers"] = {}
        state["last_event"] = None

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        if state["phase"] == "lobby":
            n = len(state["participant_ids"])
            state["drawer_sequence"] = [
                state["participant_ids"][i % n] for i in range(n * ROUNDS_PER_PLAYER)
            ]
            state["turn_index"] = 0
        else:
            state["turn_index"] += 1
        self._begin_drawing_turn(state)
        state["phase"] = "drawing"
        return state, DRAW_DURATION_SECONDS

    def parse_action(self, data: dict) -> dict:
        kind = data.get("action")
        if kind == "guess":
            text = data.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Missing or invalid guess text.")
            return {"kind": "guess", "text": text.strip()[:60]}
        raise ValueError("Missing or invalid action.")

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] != "drawing":
            raise IllegalAction("No guessing is open right now.")
        if member_id not in state["participant_ids"]:
            raise IllegalAction("You're not in this game.")
        if member_id == state["current_drawer"]:
            raise IllegalAction("The drawer can't guess.")
        if member_id in state["correct_guessers"]:
            raise IllegalAction("You've already guessed it.")
        if action["kind"] != "guess":
            raise IllegalAction("A guess is expected right now.")

        state = copy.deepcopy(state)
        text = action["text"]
        is_correct = text.strip().lower() == state["secret_word"].strip().lower()
        if is_correct:
            state["correct_guessers"][member_id] = int(time.time() * 1000)
        state["guess_log"].append({"member_id": member_id, "text": text, "correct": is_correct})
        return state

    def is_round_over(self, state: dict) -> bool:
        if state["phase"] != "drawing":
            return False
        non_drawers = [m for m in state["participant_ids"] if m != state["current_drawer"]]
        return all(m in state["correct_guessers"] for m in non_drawers)

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] != "drawing":  # idempotency guard
            return state, {}
        state = copy.deepcopy(state)
        drawer = state["current_drawer"]

        awarded: dict[str, int] = {}
        for member_id, guessed_at_ms in state["correct_guessers"].items():
            awarded[member_id] = _points_for(guessed_at_ms, state["round_started_at_ms"], state["round_deadline_ms"])
        if state["correct_guessers"]:
            awarded[drawer] = DRAWER_POINTS_PER_GUESSER * len(state["correct_guessers"])

        state["last_event"] = {
            "kind": "turn_over",
            "drawer_member_id": drawer,
            "word": state["secret_word"],
            "correct_guesser_ids": list(state["correct_guessers"].keys()),
        }
        state["turns_completed"] += 1
        state["phase"] = "reveal"
        return state, awarded

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return state["turns_completed"] >= len(state["drawer_sequence"])

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        drawer = state.get("current_drawer")
        is_drawer = viewer_member_id is not None and viewer_member_id == drawer
        is_reveal = state["phase"] == "reveal"
        word = state.get("secret_word")

        if word is None:
            word_display, word_length = None, None
        elif is_drawer or is_reveal:
            word_display, word_length = word, len(word)
        else:
            word_display, word_length = _mask_word(word), len(word.replace(" ", ""))

        guess_log = [
            {
                "member_id": g["member_id"],
                "text": "Guessed the word!" if g["correct"] else g["text"],
                "correct": g["correct"],
            }
            for g in state.get("guess_log", [])
        ]

        return {
            "phase": state["phase"],
            "turn_number": state["turn_index"] + 1,
            "total_turns": len(state.get("drawer_sequence", [])),
            "current_drawer_id": drawer,
            "am_drawer": is_drawer,
            "word": word_display,
            "word_length": word_length,
            "round_started_at_ms": state.get("round_started_at_ms"),
            "round_deadline_ms": state.get("round_deadline_ms"),
            "guess_log": guess_log,
            "have_guessed_correctly": viewer_member_id in state.get("correct_guessers", {}) if viewer_member_id else False,
            "correct_guesser_ids": list(state.get("correct_guessers", {}).keys()),
            "last_event": state["last_event"] if is_reveal else None,
        }

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        rows = [
            {
                "member_id": m,
                "score": cumulative_scores.get(m, 0),
                "round_points": None,
                "answered": m in state.get("correct_guessers", {}),
            }
            for m in state["participant_ids"]
        ]
        rows.sort(key=lambda r: -r["score"])
        return rows
