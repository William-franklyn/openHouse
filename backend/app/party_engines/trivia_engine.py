import copy
import json
import random
import time
from pathlib import Path

from app.party_engines.base import IllegalAction

ROUND_DURATION_SECONDS = 20
BASE_POINTS = 1000
# A correct answer at the very last instant before the deadline still
# scores this fraction of BASE_POINTS - answering correctly always beats
# answering wrong or not at all, regardless of speed.
MIN_SCORE_FRACTION = 0.3

_QUESTIONS_PATH = Path(__file__).parent / "trivia_questions.json"
_QUESTIONS: list[dict] = json.loads(_QUESTIONS_PATH.read_text(encoding="utf-8"))


def _pick_question(already_used_ids: list[str]) -> dict:
    used = set(already_used_ids)
    pool = [q for q in _QUESTIONS if q["id"] not in used]
    if not pool:
        pool = _QUESTIONS  # exhausted the bank - allow repeats rather than erroring
    return random.choice(pool)


def _points_for(answered_at_ms: int, started_at_ms: int, deadline_ms: int) -> int:
    duration = max(1, deadline_ms - started_at_ms)
    elapsed = max(0, min(duration, answered_at_ms - started_at_ms))
    fraction_remaining = 1 - (elapsed / duration)
    scaled = MIN_SCORE_FRACTION + (1 - MIN_SCORE_FRACTION) * fraction_remaining
    return round(BASE_POINTS * scaled)


class TriviaEngine:
    kind = "trivia"
    MIN_PARTICIPANTS = 2

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "question_ids_used": [],
            "current_question": None,
            "round_started_at_ms": None,
            "round_deadline_ms": None,
            "answers": {},
            "round_points_awarded": None,
        }

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        question = _pick_question(state["question_ids_used"])
        state["question_ids_used"].append(question["id"])
        now_ms = int(time.time() * 1000)
        state.update(
            current_question=question,
            round_started_at_ms=now_ms,
            round_deadline_ms=now_ms + ROUND_DURATION_SECONDS * 1000,
            answers={},
            round_points_awarded=None,
            phase="question",
        )
        return state, ROUND_DURATION_SECONDS

    def parse_action(self, data: dict) -> dict:
        choice_index = data.get("choice_index")
        if not isinstance(choice_index, int) or isinstance(choice_index, bool):
            raise ValueError("Missing or invalid choice_index.")
        return {"choice_index": choice_index}

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] != "question":
            raise IllegalAction("This round isn't open for answers right now.")
        if member_id in state["answers"]:
            raise IllegalAction("You've already answered this round.")
        choice_index = action["choice_index"]
        if not (0 <= choice_index < len(state["current_question"]["choices"])):
            raise IllegalAction("That's not a valid choice.")
        state = copy.deepcopy(state)
        state["answers"][member_id] = {
            "choice_index": choice_index,
            "answered_at_ms": int(time.time() * 1000),
        }
        return state

    def is_round_over(self, state: dict) -> bool:
        return state["phase"] == "question" and len(state["answers"]) >= len(state["participant_ids"])

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] != "question":  # idempotency guard - timer/early-finish race
            return state, {}
        state = copy.deepcopy(state)
        correct = state["current_question"]["correct_index"]
        awarded = {}
        for member_id in state["participant_ids"]:
            answer = state["answers"].get(member_id)
            if answer is not None and answer["choice_index"] == correct:
                awarded[member_id] = _points_for(
                    answer["answered_at_ms"], state["round_started_at_ms"], state["round_deadline_ms"]
                )
            else:
                awarded[member_id] = 0
        state["round_points_awarded"] = awarded
        state["phase"] = "reveal"
        return state, awarded

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return round_index >= total_rounds - 1

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        question, phase = state["current_question"], state["phase"]
        if question is None:
            return {"phase": phase, "question": None}
        if phase == "question":
            my_answer = state["answers"].get(viewer_member_id) if viewer_member_id else None
            return {
                "phase": "question",
                "question": {k: question[k] for k in ("id", "category", "question", "choices")},
                "round_started_at_ms": state["round_started_at_ms"],
                "round_deadline_ms": state["round_deadline_ms"],
                "answered_member_ids": list(state["answers"].keys()),
                "my_answer": {"choice_index": my_answer["choice_index"]} if my_answer else None,
            }
        return {
            "phase": "reveal",
            "question": dict(question),
            "answers": state["answers"],
            "round_points_awarded": state["round_points_awarded"],
        }

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        awarded = state.get("round_points_awarded") or {}
        rows = [
            {
                "member_id": m,
                "score": cumulative_scores.get(m, 0),
                "round_points": awarded.get(m),
                "answered": m in state["answers"],
            }
            for m in state["participant_ids"]
        ]
        rows.sort(key=lambda r: -r["score"])
        return rows
