"""Pure unit tests directly against the Codenames engine - no DB, no
WebSocket. Mirrors test_uno_engine.py's split from the WS-level tests in
test_codenames_games.py."""

import random
from collections import Counter

from app.party_engines.base import IllegalAction
from app.party_engines.codenames_engine import CodenamesEngine


def _fresh_game(players=("red_sm", "blue_sm", "red_op", "blue_op"), seed=1):
    random.seed(seed)
    engine = CodenamesEngine()
    state = engine.initial_state(list(players))
    state, duration = engine.start_round(state, 0)
    return engine, state, duration


def test_board_has_the_real_codenames_word_distribution():
    engine, state, _ = _fresh_game()
    assert len(state["board"]) == 25
    counts = Counter(c["owner"] for c in state["board"])
    assert counts["red"] == 9
    assert counts["blue"] == 8
    assert counts["neutral"] == 7
    assert counts["assassin"] == 1
    assert len({c["word"] for c in state["board"]}) == 25  # no duplicate words


def test_teams_split_by_alternating_join_order_first_member_is_spymaster():
    engine, state, _ = _fresh_game(players=("a", "b", "c", "d", "e"))
    assert state["teams"]["red"]["spymaster"] == "a"
    assert state["teams"]["red"]["operatives"] == ["c", "e"]
    assert state["teams"]["blue"]["spymaster"] == "b"
    assert state["teams"]["blue"]["operatives"] == ["d"]


def test_red_is_always_the_starting_team_with_nine_words():
    engine, state, duration = _fresh_game()
    assert state["active_team"] == "red"
    assert state["phase"] == "clue"
    assert duration > 0


def test_parse_action_rejects_bad_clue_payloads():
    engine = CodenamesEngine()
    try:
        engine.parse_action({"action": "clue", "word": "", "number": 2})
        assert False
    except ValueError:
        pass
    try:
        engine.parse_action({"action": "clue", "word": "FRUIT", "number": 10})
        assert False
    except ValueError:
        pass
    try:
        engine.parse_action({"action": "clue", "word": "FRUIT", "number": "two"})
        assert False
    except ValueError:
        pass
    parsed = engine.parse_action({"action": "clue", "word": " FRUIT ", "number": 2})
    assert parsed == {"kind": "clue", "word": "FRUIT", "number": 2}


def test_only_the_active_spymaster_may_give_a_clue():
    engine, state, _ = _fresh_game()
    action = engine.parse_action({"action": "clue", "word": "FRUIT", "number": 2})
    for not_spymaster in ("blue_sm", "red_op", "blue_op"):
        try:
            engine.apply_action(state, not_spymaster, action)
            assert False, f"{not_spymaster} should not be able to give the clue"
        except IllegalAction:
            pass
    state2 = engine.apply_action(state, "red_sm", action)
    assert state2["pending_action"] == {"kind": "clue", "word": "FRUIT", "number": 2}


def test_only_an_active_operative_may_guess_not_their_own_spymaster():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 1}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    assert state["phase"] == "guessing"
    word_id = state["board"][0]["id"]
    guess = engine.parse_action({"action": "guess", "word_id": word_id})
    for not_operative in ("red_sm", "blue_sm", "blue_op"):
        try:
            engine.apply_action(state, not_operative, guess)
            assert False, f"{not_operative} should not be able to guess"
        except IllegalAction:
            pass
    state2 = engine.apply_action(state, "red_op", guess)
    assert state2["pending_action"] == {"kind": "guess", "word_id": word_id}


def test_guessing_your_own_word_continues_the_same_teams_turn():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 2}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    assert state["guesses_remaining"] == 3

    red_word = next(c for c in state["board"] if c["owner"] == "red")
    state = engine.apply_action(state, "red_op", engine.parse_action({"action": "guess", "word_id": red_word["id"]}))
    state, points = engine.time_up(state)
    assert points == {}
    assert state["next_phase"] == "guessing"
    assert state["guesses_remaining"] == 2
    assert state["active_team"] == "red"


def test_guessing_a_neutral_word_ends_the_turn_immediately():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 2}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)

    neutral_word = next(c for c in state["board"] if c["owner"] == "neutral")
    state = engine.apply_action(state, "red_op", engine.parse_action({"action": "guess", "word_id": neutral_word["id"]}))
    state, points = engine.time_up(state)
    assert points == {}
    assert state["next_phase"] == "clue"
    assert state["active_team"] == "blue"
    assert state["guesses_remaining"] is None


def test_guessing_the_enemy_teams_word_ends_the_turn_and_reveals_it():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 2}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)

    blue_word = next(c for c in state["board"] if c["owner"] == "blue")
    state = engine.apply_action(state, "red_op", engine.parse_action({"action": "guess", "word_id": blue_word["id"]}))
    state, points = engine.time_up(state)
    assert points == {}
    assert state["active_team"] == "blue"
    revealed = next(c for c in state["board"] if c["id"] == blue_word["id"])
    assert revealed["revealed"] is True


def test_guessing_the_assassin_ends_the_game_for_the_other_team():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 2}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)

    assassin = next(c for c in state["board"] if c["owner"] == "assassin")
    state = engine.apply_action(state, "red_op", engine.parse_action({"action": "guess", "word_id": assassin["id"]}))
    state, points = engine.time_up(state)
    assert state["winner"] == "blue"
    assert state["win_reason"] == "assassin_hit"
    assert points == {"blue_sm": 1, "blue_op": 1}
    assert engine.check_game_over(state, 0, engine.DEFAULT_TOTAL_ROUNDS)


def test_revealing_a_teams_last_word_wins_them_the_game():
    engine, state, _ = _fresh_game()
    # Reveal all but one of red's words directly (hand-crafted board state).
    red_words = [c for c in state["board"] if c["owner"] == "red"]
    for c in red_words[:-1]:
        c["revealed"] = True
    last_red_word = red_words[-1]

    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 1}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    state = engine.apply_action(
        state, "red_op", engine.parse_action({"action": "guess", "word_id": last_red_word["id"]})
    )
    state, points = engine.time_up(state)
    assert state["winner"] == "red"
    assert state["win_reason"] == "all_words_found"
    assert points == {"red_sm": 1, "red_op": 1}


def test_a_spymaster_who_never_gives_a_clue_passes_the_turn():
    engine, state, _ = _fresh_game()
    # Nobody ever calls apply_action - time_up must still resolve the round.
    state, points = engine.time_up(state)
    assert points == {}
    assert state["last_event"] == {"kind": "clue_timeout", "team": "red"}
    assert state["next_phase"] == "clue"
    assert state["active_team"] == "blue"


def test_an_operative_who_never_guesses_passes_the_turn():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 2}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    # Nobody ever guesses or passes - time_up must still resolve the round.
    state, points = engine.time_up(state)
    assert points == {}
    assert state["last_event"] == {"kind": "guess_timeout", "team": "red"}
    assert state["active_team"] == "blue"


def test_an_operative_may_voluntarily_pass_to_end_the_turn_early():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 2}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    state = engine.apply_action(state, "red_op", engine.parse_action({"action": "pass"}))
    state, points = engine.time_up(state)
    assert points == {}
    assert state["last_event"] == {"kind": "guess_pass", "team": "red"}
    assert state["active_team"] == "blue"


def test_time_up_is_idempotent_against_a_second_call():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 2}))
    state, first_points = engine.time_up(state)
    state_again, second_points = engine.time_up(state)
    assert second_points == {}
    assert state_again == state


def test_spymaster_sees_every_owner_operative_only_sees_revealed_owners():
    engine, state, _ = _fresh_game()
    sm_view = engine.build_display_state(state, "red_sm")
    op_view = engine.build_display_state(state, "red_op")
    assert all(c["owner"] is not None for c in sm_view["board"])
    assert all(c["owner"] is None for c in op_view["board"])
    assert sm_view["my_role"] == "spymaster"
    assert op_view["my_role"] == "operative"
    assert sm_view["my_team"] == op_view["my_team"] == "red"


def test_the_whole_board_is_revealed_to_everyone_once_the_game_ends():
    engine, state, _ = _fresh_game()
    red_words = [c for c in state["board"] if c["owner"] == "red"]
    for c in red_words[:-1]:
        c["revealed"] = True
    last_red_word = red_words[-1]

    state = engine.apply_action(state, "red_sm", engine.parse_action({"action": "clue", "word": "X", "number": 1}))
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    state = engine.apply_action(
        state, "red_op", engine.parse_action({"action": "guess", "word_id": last_red_word["id"]})
    )
    state, _ = engine.time_up(state)
    assert state["winner"] == "red"

    op_view = engine.build_display_state(state, "blue_op")
    assert all(c["owner"] is not None for c in op_view["board"])


def test_scoreboard_groups_rows_by_team_and_flags_the_spymaster():
    engine, state, _ = _fresh_game()
    rows = engine.scoreboard(state, {})
    by_member = {r["member_id"]: r for r in rows}
    assert by_member["red_sm"]["team"] == "red"
    assert by_member["red_sm"]["is_spymaster"] is True
    assert by_member["red_op"]["is_spymaster"] is False
    assert by_member["blue_sm"]["team"] == "blue"
