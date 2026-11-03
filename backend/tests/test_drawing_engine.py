"""Pure unit tests directly against the Drawing & Guess engine - no DB,
no WebSocket. Mirrors test_hearts_engine.py's split from the WS-level
tests in test_drawing_games.py. Stroke-relay handlers live in
realtime.py directly (no engine involvement) and are tested separately
in test_drawing_strokes.py."""

import random

from app.party_engines.base import IllegalAction
from app.party_engines.drawing_engine import (
    DrawingEngine,
    DRAWER_POINTS_PER_GUESSER,
    ROUNDS_PER_PLAYER,
    _WORDS,
    _mask_word,
)


def _fresh_game(players=("A", "B", "C"), seed=1):
    random.seed(seed)
    engine = DrawingEngine()
    state = engine.initial_state(list(players))
    state, duration = engine.start_round(state, 0)
    return engine, state, duration


def test_word_bank_is_non_empty_and_every_word_is_unique():
    assert len(_WORDS) > 0
    assert len(set(_WORDS)) == len(_WORDS)


def test_mask_word_hides_letters_but_preserves_word_boundaries():
    assert _mask_word("PIZZA") == "_ _ _ _ _"
    assert _mask_word("ICE CREAM") == "_ _ _   _ _ _ _ _"


def test_fresh_game_builds_a_full_rotation_where_everyone_draws_equally():
    engine, state, duration = _fresh_game(players=("A", "B", "C", "D"))
    assert len(state["drawer_sequence"]) == 4 * ROUNDS_PER_PLAYER
    from collections import Counter
    counts = Counter(state["drawer_sequence"])
    assert all(c == ROUNDS_PER_PLAYER for c in counts.values())
    assert state["phase"] == "drawing"
    assert duration > 0


def test_the_drawer_sees_the_real_word_everyone_else_sees_it_masked():
    engine, state, _ = _fresh_game()
    drawer = state["current_drawer"]
    guesser = next(p for p in state["participant_ids"] if p != drawer)

    drawer_view = engine.build_display_state(state, drawer)
    guesser_view = engine.build_display_state(state, guesser)
    assert drawer_view["word"] == state["secret_word"]
    assert guesser_view["word"] == _mask_word(state["secret_word"])
    assert "secret_word" not in guesser_view


def test_the_drawer_cannot_submit_a_guess():
    engine, state, _ = _fresh_game()
    drawer = state["current_drawer"]
    try:
        engine.apply_action(state, drawer, {"kind": "guess", "text": "anything"})
        assert False, "the drawer should not be able to guess"
    except IllegalAction:
        pass


def test_a_wrong_guess_does_not_end_the_round_and_stays_visible_verbatim():
    engine, state, _ = _fresh_game()
    drawer = state["current_drawer"]
    guesser = next(p for p in state["participant_ids"] if p != drawer)
    state = engine.apply_action(state, guesser, {"kind": "guess", "text": "definitely wrong"})
    assert not engine.is_round_over(state)
    view = engine.build_display_state(state, drawer)
    assert view["guess_log"][0] == {"member_id": guesser, "text": "definitely wrong", "correct": False}


def test_a_correct_guess_is_redacted_in_the_shared_feed():
    engine, state, _ = _fresh_game(players=("A", "B", "C"))
    drawer = state["current_drawer"]
    guessers = [p for p in state["participant_ids"] if p != drawer]
    state = engine.apply_action(state, guessers[0], {"kind": "guess", "text": state["secret_word"]})
    view = engine.build_display_state(state, guessers[1])
    entry = view["guess_log"][0]
    assert entry["correct"] is True
    assert entry["text"] == "Guessed the word!"
    assert state["secret_word"] not in entry["text"]


def test_guessing_is_case_and_whitespace_insensitive():
    engine, state, _ = _fresh_game()
    drawer = state["current_drawer"]
    guesser = next(p for p in state["participant_ids"] if p != drawer)
    state = engine.apply_action(state, guesser, {"kind": "guess", "text": f"  {state['secret_word'].lower()}  "})
    assert guesser in state["correct_guessers"]


def test_a_correct_guesser_cannot_guess_again():
    engine, state, _ = _fresh_game()
    drawer = state["current_drawer"]
    guesser = next(p for p in state["participant_ids"] if p != drawer)
    state = engine.apply_action(state, guesser, {"kind": "guess", "text": state["secret_word"]})
    try:
        engine.apply_action(state, guesser, {"kind": "guess", "text": "something else"})
        assert False, "a player who already guessed correctly should not be able to guess again"
    except IllegalAction:
        pass


def test_is_round_over_once_every_non_drawer_has_guessed_correctly():
    engine, state, _ = _fresh_game(players=("A", "B", "C"))
    drawer = state["current_drawer"]
    guessers = [p for p in state["participant_ids"] if p != drawer]
    state = engine.apply_action(state, guessers[0], {"kind": "guess", "text": state["secret_word"]})
    assert not engine.is_round_over(state)
    state = engine.apply_action(state, guessers[1], {"kind": "guess", "text": state["secret_word"]})
    assert engine.is_round_over(state)


def test_scoring_awards_the_drawer_a_flat_amount_per_correct_guesser():
    engine, state, _ = _fresh_game(players=("A", "B", "C"))
    drawer = state["current_drawer"]
    guessers = [p for p in state["participant_ids"] if p != drawer]
    for g in guessers:
        state = engine.apply_action(state, g, {"kind": "guess", "text": state["secret_word"]})
    state, points = engine.time_up(state)
    assert points[drawer] == DRAWER_POINTS_PER_GUESSER * len(guessers)
    assert all(points[g] > 0 for g in guessers)


def test_nobody_guessing_awards_the_drawer_nothing():
    engine, state, _ = _fresh_game()
    state, points = engine.time_up(state)
    drawer = state["last_event"]["drawer_member_id"]
    assert drawer not in points
    assert points == {}


def test_time_up_reveals_the_real_word_to_everyone():
    engine, state, _ = _fresh_game()
    drawer = state["current_drawer"]
    guesser = next(p for p in state["participant_ids"] if p != drawer)
    secret = state["secret_word"]
    state, _ = engine.time_up(state)
    assert state["phase"] == "reveal"
    guesser_view = engine.build_display_state(state, guesser)
    assert guesser_view["word"] == secret
    assert state["last_event"]["word"] == secret


def test_time_up_is_idempotent_against_a_second_call():
    engine, state, _ = _fresh_game()
    state, first_points = engine.time_up(state)
    state_again, second_points = engine.time_up(state)
    assert second_points == {}
    assert state_again == state


def test_the_game_ends_once_every_scheduled_turn_has_been_played():
    engine, state, _ = _fresh_game(players=("A", "B", "C"))
    round_index = 1
    turns = 0
    while not engine.check_game_over(state, 0, engine.DEFAULT_TOTAL_ROUNDS):
        turns += 1
        assert turns < 100, "safety abort"
        drawer = state["current_drawer"]
        for g in [p for p in state["participant_ids"] if p != drawer]:
            state = engine.apply_action(state, g, {"kind": "guess", "text": state["secret_word"]})
        state, _ = engine.time_up(state)
        if engine.check_game_over(state, 0, engine.DEFAULT_TOTAL_ROUNDS):
            break
        state, _ = engine.start_round(state, round_index)
        round_index += 1
    assert state["turns_completed"] == len(state["drawer_sequence"]) == 3 * ROUNDS_PER_PLAYER


def test_scoreboard_marks_correct_guessers_as_answered():
    engine, state, _ = _fresh_game(players=("A", "B", "C"))
    drawer = state["current_drawer"]
    guesser = next(p for p in state["participant_ids"] if p != drawer)
    state = engine.apply_action(state, guesser, {"kind": "guess", "text": state["secret_word"]})
    rows = engine.scoreboard(state, {})
    row = next(r for r in rows if r["member_id"] == guesser)
    assert row["answered"] is True
