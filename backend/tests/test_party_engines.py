"""Pure unit tests directly against the party-game engines - no DB, no
WebSocket, no fakeredis. Separate from the realtime-plumbing tests in
test_party_games.py, same split as test_game_engines.py vs
test_battleship.py."""

from app.party_engines.base import IllegalAction
from app.party_engines.trivia_engine import TriviaEngine, _points_for


def _started_question_state():
    engine = TriviaEngine()
    state = engine.initial_state(["m1", "m2", "m3"])
    state, duration = engine.start_round(state, 0)
    return engine, state, duration


def test_round_duration_is_returned_from_start_round():
    _, _, duration = _started_question_state()
    assert duration == 20


def test_faster_correct_answer_scores_more_than_slower_correct_answer():
    started_at = 1_000_000
    deadline = started_at + 20_000
    fast = _points_for(started_at + 1_000, started_at, deadline)
    slow = _points_for(started_at + 18_000, started_at, deadline)
    assert fast > slow > 0


def test_correct_answer_at_the_very_last_instant_still_scores_the_floor():
    started_at = 1_000_000
    deadline = started_at + 20_000
    last_instant = _points_for(deadline, started_at, deadline)
    assert last_instant == 300  # MIN_SCORE_FRACTION (0.3) * BASE_POINTS (1000)


def test_wrong_answer_scores_zero():
    engine, state, _ = _started_question_state()
    correct = state["current_question"]["correct_index"]
    wrong = next(i for i in range(len(state["current_question"]["choices"])) if i != correct)
    state = engine.apply_action(state, "m1", {"choice_index": wrong})
    state, awarded = engine.time_up(state)
    assert awarded["m1"] == 0


def test_missing_answer_scores_zero():
    engine, state, _ = _started_question_state()
    state, awarded = engine.time_up(state)  # nobody answered
    assert awarded == {"m1": 0, "m2": 0, "m3": 0}


def test_correct_answer_scores_above_zero():
    engine, state, _ = _started_question_state()
    correct = state["current_question"]["correct_index"]
    state = engine.apply_action(state, "m1", {"choice_index": correct})
    state, awarded = engine.time_up(state)
    assert awarded["m1"] > 0


def test_apply_action_rejects_a_second_answer_from_the_same_member():
    engine, state, _ = _started_question_state()
    state = engine.apply_action(state, "m1", {"choice_index": 0})
    try:
        engine.apply_action(state, "m1", {"choice_index": 1})
        assert False, "answering twice should be rejected"
    except IllegalAction:
        pass


def test_apply_action_rejects_an_out_of_range_choice():
    engine, state, _ = _started_question_state()
    n_choices = len(state["current_question"]["choices"])
    try:
        engine.apply_action(state, "m1", {"choice_index": n_choices})
        assert False, "out-of-range choice should be rejected"
    except IllegalAction:
        pass


def test_apply_action_rejects_answers_once_revealed():
    engine, state, _ = _started_question_state()
    state, _ = engine.time_up(state)
    assert state["phase"] == "reveal"
    try:
        engine.apply_action(state, "m1", {"choice_index": 0})
        assert False, "answering after reveal should be rejected"
    except IllegalAction:
        pass


def test_is_round_over_true_only_once_everyone_has_answered():
    engine, state, _ = _started_question_state()
    assert not engine.is_round_over(state)
    state = engine.apply_action(state, "m1", {"choice_index": 0})
    assert not engine.is_round_over(state)
    state = engine.apply_action(state, "m2", {"choice_index": 0})
    assert not engine.is_round_over(state)
    state = engine.apply_action(state, "m3", {"choice_index": 0})
    assert engine.is_round_over(state)


def test_time_up_is_idempotent_against_a_second_call():
    engine, state, _ = _started_question_state()
    state, awarded_first = engine.time_up(state)
    assert awarded_first  # real points were computed the first time
    state_again, awarded_second = engine.time_up(state)
    assert awarded_second == {}  # a second call awards nothing further
    assert state_again == state  # and leaves the already-revealed state untouched


def test_check_game_over_true_only_at_the_final_round_index():
    engine = TriviaEngine()
    total_rounds = 8
    for round_index in range(total_rounds - 1):
        assert not engine.check_game_over({}, round_index, total_rounds)
    assert engine.check_game_over({}, total_rounds - 1, total_rounds)


def test_question_phase_display_never_reveals_the_correct_index():
    engine, state, _ = _started_question_state()
    for viewer in ("m1", "m2", "m3", None):
        display = engine.build_display_state(state, viewer)
        assert "correct_index" not in display["question"]
        assert "correct_index" not in str(display["question"].keys())


def test_question_phase_display_hides_other_participants_choices():
    engine, state, _ = _started_question_state()
    correct = state["current_question"]["correct_index"]
    state = engine.apply_action(state, "m1", {"choice_index": correct})

    viewer_m1 = engine.build_display_state(state, "m1")
    assert viewer_m1["my_answer"] == {"choice_index": correct}
    assert viewer_m1["answered_member_ids"] == ["m1"]
    assert "answers" not in viewer_m1  # the raw per-member choice map never appears pre-reveal

    viewer_m2 = engine.build_display_state(state, "m2")
    assert viewer_m2["my_answer"] is None
    assert viewer_m2["answered_member_ids"] == ["m1"]  # progress visible...
    assert "answers" not in viewer_m2  # ...but m1's actual pick is not


def test_reveal_phase_display_includes_the_correct_index_and_all_answers():
    engine, state, _ = _started_question_state()
    correct = state["current_question"]["correct_index"]
    state = engine.apply_action(state, "m1", {"choice_index": correct})
    state, _ = engine.time_up(state)

    display = engine.build_display_state(state, "m2")
    assert display["question"]["correct_index"] == correct
    assert display["answers"]["m1"]["choice_index"] == correct
    assert display["round_points_awarded"]["m1"] > 0
    assert display["round_points_awarded"]["m2"] == 0


def test_scoreboard_is_sorted_descending_by_cumulative_score():
    engine, state, _ = _started_question_state()
    rows = engine.scoreboard(state, {"m1": 500, "m2": 1500, "m3": 0})
    assert [r["member_id"] for r in rows] == ["m2", "m1", "m3"]


def test_scoreboard_reflects_answered_flag_before_reveal():
    engine, state, _ = _started_question_state()
    state = engine.apply_action(state, "m2", {"choice_index": 0})
    rows = {r["member_id"]: r for r in engine.scoreboard(state, {})}
    assert rows["m2"]["answered"] is True
    assert rows["m1"]["answered"] is False
