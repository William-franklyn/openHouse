"""Pure unit tests directly against the draft engine - no DB, no
WebSocket. Mirrors test_party_engines.py's split from the WS-level tests
in test_draft_games.py."""

import random

from app.party_engines.base import IllegalAction
from app.party_engines.draft_engine import DraftEngine, HAND_SIZE, NUM_SCORING_ROUNDS, _score_collection


def _play_all_picks(engine, players, total_rounds, pick_index=0):
    """Plays every pick by always taking each player's first remaining
    hand card - deterministic enough to assert on, and exercises the
    exact same code path a real auto-pick-on-timeout would."""
    random.seed(7)
    state = engine.initial_state(players)
    cumulative = {p: 0 for p in players}
    history = []
    for round_index in range(total_rounds):
        state, duration = engine.start_round(state, round_index)
        for p in players:
            card = state["hands"][p][pick_index % len(state["hands"][p])]
            state = engine.apply_action(state, p, {"card_id": card["id"]})
        state, points = engine.time_up(state)
        for p, pts in points.items():
            cumulative[p] += pts
        history.append((state["phase"], dict(points)))
    return state, cumulative, history


def test_default_total_rounds_matches_hand_size_times_scoring_rounds():
    engine = DraftEngine()
    assert engine.DEFAULT_TOTAL_ROUNDS == HAND_SIZE * NUM_SCORING_ROUNDS


def test_score_collection_base_sum_only():
    score, counts = _score_collection([{"color": "Red", "value": 1}, {"color": "Blue", "value": 2}])
    assert score == 3
    assert counts == {"Red": 1, "Blue": 1}


def test_score_collection_set_bonus_for_three_of_a_color():
    cards = [{"color": "Red", "value": 1}] * 3
    score, counts = _score_collection(cards)
    assert score == 3 * 1 + 2  # base 3, +2 set bonus
    assert counts == {"Red": 3}


def test_score_collection_rainbow_bonus_requires_all_five_colors():
    cards = [{"color": c, "value": 1} for c in ["Red", "Blue", "Green", "Yellow", "Purple"]]
    score, counts = _score_collection(cards)
    assert score == 5 * 1 + 5  # base 5, +5 rainbow bonus
    assert len(counts) == 5


def test_full_game_conserves_pick_counts_and_ends_on_schedule():
    engine = DraftEngine()
    players = ["A", "B", "C"]
    state, cumulative, history = _play_all_picks(engine, players, engine.DEFAULT_TOTAL_ROUNDS)

    assert all(len(state["hands"][p]) == 0 for p in players)
    assert all(len(state["collected"][p]) == HAND_SIZE for p in players)
    assert state["phase"] == "scoring_round_over"

    scoring_round_overs = [h for h in history if h[0] == "scoring_round_over"]
    assert len(scoring_round_overs) == NUM_SCORING_ROUNDS
    # Every other pick in between awards nothing.
    reveals = [h for h in history if h[0] == "reveal"]
    assert all(points == {} for _phase, points in reveals)
    assert len(reveals) == engine.DEFAULT_TOTAL_ROUNDS - NUM_SCORING_ROUNDS


def test_check_game_over_true_only_at_the_final_round_index():
    engine = DraftEngine()
    total = engine.DEFAULT_TOTAL_ROUNDS
    for round_index in range(total - 1):
        assert not engine.check_game_over({}, round_index, total)
    assert engine.check_game_over({}, total - 1, total)


def test_pass_mechanic_hand_sizes_shrink_by_one_each_pick():
    engine = DraftEngine()
    players = ["A", "B", "C", "D"]
    random.seed(1)
    state = engine.initial_state(players)
    for pick in range(HAND_SIZE):
        state, _ = engine.start_round(state, pick)
        expected_size = HAND_SIZE - pick
        assert all(len(state["hands"][p]) == expected_size for p in players), (pick, state["hands"])
        for p in players:
            state = engine.apply_action(state, p, {"card_id": state["hands"][p][0]["id"]})
        state, _ = engine.time_up(state)


def test_apply_action_rejects_a_second_pick_in_the_same_round():
    engine = DraftEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    card = state["hands"]["A"][0]
    state = engine.apply_action(state, "A", {"card_id": card["id"]})
    try:
        engine.apply_action(state, "A", {"card_id": state["hands"]["A"][0]["id"]})
        assert False, "picking twice in one round should be rejected"
    except IllegalAction:
        pass


def test_apply_action_rejects_a_card_not_in_hand():
    engine = DraftEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    try:
        engine.apply_action(state, "A", {"card_id": "not-a-real-card"})
        assert False, "picking a card not in hand should be rejected"
    except IllegalAction:
        pass


def test_time_up_auto_picks_for_a_straggler():
    engine = DraftEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    state = engine.apply_action(state, "A", {"card_id": state["hands"]["A"][0]["id"]})
    # B never acts - time_up must still resolve the pick for both.
    state, _points = engine.time_up(state)
    assert len(state["collected"]["A"]) == 1
    assert len(state["collected"]["B"]) == 1


def test_time_up_is_idempotent_against_a_second_call():
    engine = DraftEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    state = engine.apply_action(state, "A", {"card_id": state["hands"]["A"][0]["id"]})
    state = engine.apply_action(state, "B", {"card_id": state["hands"]["B"][0]["id"]})
    state, first_points = engine.time_up(state)
    state_again, second_points = engine.time_up(state)
    assert second_points == {}
    assert state_again == state


def test_build_display_state_never_leaks_other_players_hands_or_picks_before_reveal():
    engine = DraftEngine()
    state = engine.initial_state(["A", "B", "C"])
    state, _ = engine.start_round(state, 0)
    state = engine.apply_action(state, "A", {"card_id": state["hands"]["A"][0]["id"]})

    b_view = engine.build_display_state(state, "B")
    assert "my_hand" in b_view and b_view["my_hand"] is not None
    assert "revealed_picks" not in b_view
    assert "A" in b_view["picked_member_ids"]
    assert all(key not in b_view for key in ("other_hands", "all_hands"))


def test_build_display_state_reveals_only_the_picked_cards_not_remaining_hands():
    engine = DraftEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    for p in ["A", "B"]:
        state = engine.apply_action(state, p, {"card_id": state["hands"][p][0]["id"]})
    state, _ = engine.time_up(state)
    assert state["phase"] == "reveal"

    view = engine.build_display_state(state, "A")
    assert set(view["revealed_picks"].keys()) == {"A", "B"}
    assert "my_hand" in view  # viewer's own (now-passed) hand is still visible to them


def test_scoring_round_over_reveals_full_collections_for_everyone():
    engine = DraftEngine()
    players = ["A", "B"]
    state, _, _ = _play_all_picks(engine, players, HAND_SIZE)
    assert state["phase"] == "scoring_round_over"
    view = engine.build_display_state(state, "A")
    assert set(view["round_results"].keys()) == {"A", "B"}
    assert len(view["round_results"]["B"]["collected"]) == HAND_SIZE  # A can see B's full hand once scored
