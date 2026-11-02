"""Pure unit tests directly against the Buzzer Race engine - no DB, no
WebSocket. Mirrors test_hearts_engine.py's split from the WS-level
tests in test_buzzer_games.py."""

import random

from app.party_engines.base import IllegalAction
from app.party_engines.buzzer_engine import BuzzerEngine, NUM_QUESTIONS, POINTS_PER_CORRECT, _QUESTIONS


def _fresh_game(players=("A", "B", "C"), seed=1):
    random.seed(seed)
    engine = BuzzerEngine()
    state = engine.initial_state(list(players))
    state, duration = engine.start_round(state, 0)
    return engine, state, duration


def test_question_bank_is_non_empty_and_every_question_has_a_valid_correct_index():
    assert len(_QUESTIONS) > 0
    for q in _QUESTIONS:
        assert 0 <= q["correct_index"] < len(q["choices"])


def test_fresh_game_opens_on_the_first_question_in_buzzing_phase():
    engine, state, duration = _fresh_game()
    assert state["phase"] == "buzzing"
    assert state["questions_asked"] == 1
    assert state["current_question"] is not None
    assert duration > 0


def test_the_first_buzz_locks_out_every_other_buzz():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "A", {"kind": "buzz"})
    try:
        engine.apply_action(state, "B", {"kind": "buzz"})
        assert False, "a second buzz should be rejected"
    except IllegalAction:
        pass
    try:
        engine.apply_action(state, "C", {"kind": "buzz"})
        assert False, "a third buzz should be rejected"
    except IllegalAction:
        pass
    assert state["pending_action"] == {"kind": "buzz", "member_id": "A"}


def test_only_the_buzzer_may_answer():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "A", {"kind": "buzz"})
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    assert state["phase"] == "answering"
    try:
        engine.apply_action(state, "B", {"kind": "answer", "choice_index": 0})
        assert False, "a non-buzzer should not be able to answer"
    except IllegalAction:
        pass
    # the real buzzer can.
    state2 = engine.apply_action(state, "A", {"kind": "answer", "choice_index": 0})
    assert state2["pending_action"]["kind"] == "answer"


def test_a_correct_answer_scores_a_flat_amount_and_moves_to_the_next_question():
    engine, state, _ = _fresh_game(seed=3)
    correct = state["current_question"]["correct_index"]
    state = engine.apply_action(state, "A", {"kind": "buzz"})
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    state = engine.apply_action(state, "A", {"kind": "answer", "choice_index": correct})
    state, points = engine.time_up(state)
    assert points == {"A": POINTS_PER_CORRECT}
    assert state["last_event"]["kind"] == "correct"
    assert state["next_phase"] == "next_question"


def test_a_wrong_answer_locks_the_buzzer_out_and_reopens_buzzing_for_the_question():
    engine, state, _ = _fresh_game(players=("A", "B", "C"), seed=4)
    correct = state["current_question"]["correct_index"]
    wrong = (correct + 1) % len(state["current_question"]["choices"])

    state = engine.apply_action(state, "A", {"kind": "buzz"})
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    state = engine.apply_action(state, "A", {"kind": "answer", "choice_index": wrong})
    state, points = engine.time_up(state)
    assert points == {}
    assert state["last_event"]["kind"] == "wrong"
    assert state["locked_out"] == ["A"]
    assert state["next_phase"] == "buzzing"

    state, _ = engine.start_round(state, 2)
    assert state["phase"] == "buzzing"
    try:
        engine.apply_action(state, "A", {"kind": "buzz"})
        assert False, "a locked-out player should not be able to buzz again this question"
    except IllegalAction:
        pass
    # B can still buzz on the SAME question.
    state2 = engine.apply_action(state, "B", {"kind": "buzz"})
    assert state2["pending_action"]["member_id"] == "B"


def test_once_everyone_is_locked_out_the_question_is_revealed_unsolved():
    engine, state, _ = _fresh_game(players=("A", "B"), seed=5)
    correct = state["current_question"]["correct_index"]
    wrong = (correct + 1) % len(state["current_question"]["choices"])

    for actor in ("A", "B"):
        state = engine.apply_action(state, actor, {"kind": "buzz"})
        state, _ = engine.time_up(state)
        state, _ = engine.start_round(state, 1)
        state = engine.apply_action(state, actor, {"kind": "answer", "choice_index": wrong})
        state, points = engine.time_up(state)
        assert points == {}
        if actor == "A":
            state, _ = engine.start_round(state, 2)

    assert state["last_event"]["kind"] == "unsolved"
    assert state["last_event"]["correct_index"] == correct
    assert set(state["locked_out"]) == {"A", "B"}
    assert state["next_phase"] == "next_question"


def test_no_buzz_within_the_time_limit_reveals_unsolved_and_moves_on():
    engine, state, _ = _fresh_game()
    correct = state["current_question"]["correct_index"]
    # Nobody ever buzzes - time_up must still resolve via the AFK path.
    state, points = engine.time_up(state)
    assert points == {}
    assert state["last_event"] == {"kind": "unsolved", "correct_index": correct}
    assert state["next_phase"] == "next_question"


def test_an_afk_buzzer_who_never_answers_is_treated_as_wrong():
    engine, state, _ = _fresh_game(players=("A", "B"), seed=6)
    state = engine.apply_action(state, "A", {"kind": "buzz"})
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    assert state["phase"] == "answering"
    # A never answers - the real server timer must still resolve it.
    state, points = engine.time_up(state)
    assert points == {}
    assert state["locked_out"] == ["A"]
    assert state["last_event"]["kind"] == "wrong"


def test_check_game_over_true_only_after_num_questions_have_been_asked():
    engine = BuzzerEngine()
    assert not engine.check_game_over({"next_phase": "next_question", "phase": "reveal"}, 0, engine.DEFAULT_TOTAL_ROUNDS)
    assert not engine.check_game_over({"next_phase": "buzzing", "phase": "buzzing"}, 0, engine.DEFAULT_TOTAL_ROUNDS)
    assert engine.check_game_over({"next_phase": "game_over", "phase": "reveal"}, 0, engine.DEFAULT_TOTAL_ROUNDS)


def test_time_up_is_idempotent_against_a_second_call():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "A", {"kind": "buzz"})
    state, first_points = engine.time_up(state)
    state_again, second_points = engine.time_up(state)
    assert second_points == {}
    assert state_again == state


def test_build_display_state_hides_the_correct_answer_until_reveal():
    engine, state, _ = _fresh_game()
    live_view = engine.build_display_state(state, "A")
    assert "correct_index" not in live_view["question"]

    state = engine.apply_action(state, "A", {"kind": "buzz"})
    state, _ = engine.time_up(state)  # -> reveal(buzzed)
    assert state["last_event"] == {"kind": "buzzed", "member_id": "A"}

    state, _ = engine.start_round(state, 1)  # -> answering, same as the real server flow
    assert state["phase"] == "answering"
    buzzed_view = engine.build_display_state(state, "B")
    assert buzzed_view["buzzed_member_id"] == "A"


def test_num_questions_is_ten():
    assert NUM_QUESTIONS == 10
