import copy
import json
import random
from pathlib import Path

from app.party_engines.base import IllegalAction

BUZZ_DURATION_SECONDS = 15
ANSWER_DURATION_SECONDS = 10
POINTS_PER_CORRECT = 100
NUM_QUESTIONS = 10

# Same bank trivia_engine.py reads - genuinely the same content type (a
# multiple-choice question), just a different interaction mechanic
# wrapped around it. The data file is shared; the engine code is not
# (no cross-imports between sibling engines, same as every other kind).
_QUESTIONS_PATH = Path(__file__).parent / "trivia_questions.json"
_QUESTIONS: list[dict] = json.loads(_QUESTIONS_PATH.read_text(encoding="utf-8"))


def _pick_question(already_used_ids: list[str]) -> dict:
    used = set(already_used_ids)
    pool = [q for q in _QUESTIONS if q["id"] not in used]
    if not pool:
        pool = _QUESTIONS  # exhausted the bank - allow repeats rather than erroring
    return random.choice(pool)


class BuzzerEngine:
    """Buzzer Race: first valid action wins, not "everyone acts" (Trivia)
    or "one designated actor acts" (Uno) - a genuinely different round
    shape. Each question alternates between two round types: "buzzing"
    (any not-yet-locked-out participant may buzz; apply_action rejects
    every submission after the first - dispatch order alone decides the
    winner, verified against a standalone script before being written
    here) and "answering" (only the player who won the buzz may submit a
    multiple-choice answer). A wrong (or un-answered) buzz locks that
    player out of the CURRENT question and reopens buzzing for whoever's
    left; once everyone's locked out, the question is revealed unsolved.
    A correct answer scores a flat POINTS_PER_CORRECT and moves to a
    fresh question - speed is already rewarded by winning the buzz race
    itself, so no separate speed-bonus scoring curve is needed the way
    Trivia's is.

    check_game_over ignores the generic round_index/total_rounds (a
    question can span several buzzing/answering rounds via the lockout
    cycle) and instead tracks its own questions_asked counter against
    NUM_QUESTIONS, the same pattern every other multi-round-per-unit
    engine in this codebase uses."""

    kind = "buzzer"
    MIN_PARTICIPANTS = 2
    DEFAULT_TOTAL_ROUNDS = 500  # loop-safety cap only, see class docstring

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "question_ids_used": [],
            "current_question": None,
            "questions_asked": 0,
            "locked_out": [],
            "pending_action": None,
            "last_event": None,
            "next_phase": "buzzing",
        }

    def _deal_fresh_question(self, state: dict) -> None:
        question = _pick_question(state["question_ids_used"])
        state["question_ids_used"].append(question["id"])
        state["current_question"] = question
        state["questions_asked"] += 1
        state["locked_out"] = []
        state["pending_action"] = None
        state["last_event"] = None

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        if state["phase"] == "lobby":
            self._deal_fresh_question(state)
            state["phase"] = "buzzing"
            return state, BUZZ_DURATION_SECONDS

        next_phase = state["next_phase"]
        if next_phase == "buzzing" and state["current_question"] is None:
            # shouldn't happen, but guard defensively against a bad transition
            self._deal_fresh_question(state)
        elif next_phase == "next_question":
            self._deal_fresh_question(state)
            next_phase = "buzzing"
        state["phase"] = next_phase
        state["pending_action"] = None
        duration = BUZZ_DURATION_SECONDS if next_phase == "buzzing" else ANSWER_DURATION_SECONDS
        return state, duration

    def parse_action(self, data: dict) -> dict:
        kind = data.get("action")
        if kind == "buzz":
            return {"kind": "buzz"}
        if kind == "answer":
            choice_index = data.get("choice_index")
            if not isinstance(choice_index, int) or isinstance(choice_index, bool):
                raise ValueError("Missing or invalid choice_index.")
            return {"kind": "answer", "choice_index": choice_index}
        raise ValueError("Missing or invalid action.")

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] == "buzzing":
            if action["kind"] != "buzz":
                raise IllegalAction("Only buzzing in is allowed right now.")
            if member_id not in state["participant_ids"]:
                raise IllegalAction("You're not in this game.")
            if member_id in state["locked_out"]:
                raise IllegalAction("You're locked out for this question.")
            if state["pending_action"] is not None:
                raise IllegalAction("Someone already buzzed in.")
            state = copy.deepcopy(state)
            state["pending_action"] = {"kind": "buzz", "member_id": member_id}
            return state

        if state["phase"] == "answering":
            # start_round always clears pending_action when opening a fresh
            # phase - the buzzer's identity survives in last_event (set by
            # the buzzing phase's own time_up), not in pending_action.
            buzzer = (
                state["last_event"]["member_id"]
                if state["last_event"] and state["last_event"].get("kind") == "buzzed"
                else None
            )
            if member_id != buzzer:
                raise IllegalAction("It's not your turn to answer.")
            if state["pending_action"] is not None:
                raise IllegalAction("You've already answered.")
            if action["kind"] != "answer":
                raise IllegalAction("An answer is expected right now.")
            choice_index = action["choice_index"]
            if not (0 <= choice_index < len(state["current_question"]["choices"])):
                raise IllegalAction("That's not a valid choice.")
            state = copy.deepcopy(state)
            state["pending_action"] = {"kind": "answer", "member_id": member_id, "choice_index": choice_index}
            return state

        raise IllegalAction("No action is open right now.")

    def is_round_over(self, state: dict) -> bool:
        if state["phase"] == "buzzing":
            return state["pending_action"] is not None and state["pending_action"]["kind"] == "buzz"
        if state["phase"] == "answering":
            return state["pending_action"] is not None and state["pending_action"]["kind"] == "answer"
        return False

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] not in ("buzzing", "answering"):  # idempotency guard
            return state, {}
        state = copy.deepcopy(state)

        if state["phase"] == "buzzing":
            action = state["pending_action"]
            if action is None:
                # Nobody buzzed in time - reveal unsolved, move to a fresh question.
                state["last_event"] = {"kind": "unsolved", "correct_index": state["current_question"]["correct_index"]}
                state["pending_action"] = None
                if state["questions_asked"] >= NUM_QUESTIONS:
                    state["phase"] = "reveal"
                    state["next_phase"] = "game_over"
                else:
                    state["next_phase"] = "next_question"
                    state["phase"] = "reveal"
                return state, {}

            # Someone buzzed - open the answering window for them.
            state["last_event"] = {"kind": "buzzed", "member_id": action["member_id"]}
            state["pending_action"] = None
            state["next_phase"] = "answering"
            state["phase"] = "reveal"
            return state, {}

        # answering phase - AFK (no answer submitted) treated the same as a wrong answer
        return self._resolve_answer(state, state["pending_action"])

    def _resolve_answer(self, state: dict, action: dict | None) -> tuple[dict, dict[str, int]]:
        # Figure out who was answering from the last reveal event (set when
        # buzzing resolved into this answering window).
        buzzer = state["last_event"]["member_id"] if state["last_event"] and state["last_event"].get("kind") == "buzzed" else None
        correct_index = state["current_question"]["correct_index"]
        choice_index = action["choice_index"] if action is not None else None
        is_correct = choice_index == correct_index

        if is_correct:
            state["last_event"] = {
                "kind": "correct", "member_id": buzzer, "choice_index": choice_index, "correct_index": correct_index,
            }
            state["pending_action"] = None
            awarded = {buzzer: POINTS_PER_CORRECT}
            if state["questions_asked"] >= NUM_QUESTIONS:
                state["phase"] = "reveal"
                state["next_phase"] = "game_over"
            else:
                state["next_phase"] = "next_question"
                state["phase"] = "reveal"
            return state, awarded

        # wrong (or no) answer - lock the buzzer out of this question
        state["locked_out"].append(buzzer)
        state["pending_action"] = None
        remaining = [p for p in state["participant_ids"] if p not in state["locked_out"]]
        if remaining:
            state["last_event"] = {
                "kind": "wrong", "member_id": buzzer, "choice_index": choice_index, "correct_index": None,
            }
            state["next_phase"] = "buzzing"
            state["phase"] = "reveal"
            return state, {}

        state["last_event"] = {"kind": "unsolved", "correct_index": correct_index}
        if state["questions_asked"] >= NUM_QUESTIONS:
            state["phase"] = "reveal"
            state["next_phase"] = "game_over"
        else:
            state["next_phase"] = "next_question"
            state["phase"] = "reveal"
        return state, {}

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return state.get("next_phase") == "game_over" and state["phase"] == "reveal"

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        question = state["current_question"]
        base = {
            "phase": state["phase"],
            "question_number": state["questions_asked"],
            "num_questions": NUM_QUESTIONS,
            "locked_out": list(state["locked_out"]),
            "buzzed_member_id": None,
        }
        if question is None:
            return {**base, "question": None, "last_event": None}

        is_reveal = state["phase"] == "reveal"
        reveal_answered = is_reveal and state["last_event"] and state["last_event"]["kind"] in ("correct", "wrong", "unsolved")
        show_correct = reveal_answered and state["last_event"]["kind"] in ("correct", "unsolved")

        buzzed_member_id = None
        if state["phase"] == "answering" and state["last_event"] and state["last_event"].get("kind") == "buzzed":
            buzzed_member_id = state["last_event"]["member_id"]

        question_payload = {k: question[k] for k in ("id", "category", "question", "choices")}
        if show_correct:
            question_payload = dict(question)  # includes correct_index

        return {
            **base,
            "question": question_payload,
            "buzzed_member_id": buzzed_member_id,
            "last_event": state["last_event"] if is_reveal else None,
        }

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        rows = [
            {
                "member_id": m,
                "score": cumulative_scores.get(m, 0),
                "round_points": None,
                "answered": m in state["locked_out"],
            }
            for m in state["participant_ids"]
        ]
        rows.sort(key=lambda r: -r["score"])
        return rows
