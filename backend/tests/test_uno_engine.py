"""Pure unit tests directly against the Uno engine - no DB, no
WebSocket. Mirrors test_draft_engine.py's split from the WS-level tests
in test_uno_games.py."""

import random
from collections import Counter

from app.party_engines.base import IllegalAction
from app.party_engines.uno_engine import UnoEngine, NUM_HANDS, _can_play, _card_points, _fresh_deck


def _total_cards(state) -> int:
    return (
        sum(len(h) for h in state["hands"].values())
        + len(state["draw_pile"])
        + len(state["discard_pile"])
    )


def test_fresh_deck_has_108_cards_in_the_real_uno_distribution():
    deck = _fresh_deck()
    assert len(deck) == 108
    counts = Counter((c["color"], c["kind"]) for c in deck)
    for color in ("Red", "Blue", "Green", "Yellow"):
        assert counts[(color, "number")] == 19  # one 0 + two each of 1-9
        assert counts[(color, "skip")] == 2
        assert counts[(color, "reverse")] == 2
        assert counts[(color, "draw2")] == 2
    assert counts[("Wild", "wild")] == 4
    assert counts[("Wild", "wild_draw4")] == 4


def test_can_play_matches_color_number_or_is_always_legal_for_wild():
    top = {"color": "Red", "kind": "number", "value": 7}
    assert _can_play({"color": "Red", "kind": "number", "value": 3}, "Red", top)  # same color
    assert _can_play({"color": "Blue", "kind": "number", "value": 7}, "Red", top)  # same number
    assert not _can_play({"color": "Blue", "kind": "number", "value": 3}, "Red", top)  # neither
    assert _can_play({"color": "Wild", "kind": "wild", "value": None}, "Red", top)  # always legal


def test_card_points_match_standard_uno_scoring():
    assert _card_points({"kind": "number", "value": 7}) == 7
    assert _card_points({"kind": "skip"}) == 20
    assert _card_points({"kind": "reverse"}) == 20
    assert _card_points({"kind": "draw2"}) == 20
    assert _card_points({"kind": "wild"}) == 50
    assert _card_points({"kind": "wild_draw4"}) == 50


def test_initial_deal_gives_everyone_seven_cards_and_a_non_wild_starter():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B", "C"])
    state, duration = engine.start_round(state, 0)
    assert all(len(state["hands"][p]) == 7 for p in ["A", "B", "C"])
    assert state["discard_pile"][-1]["color"] != "Wild"
    assert state["active_color"] == state["discard_pile"][-1]["color"]
    assert _total_cards(state) == 108


def test_apply_action_rejects_acting_out_of_turn():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    not_on_turn = next(p for p in ["A", "B"] if p != state["participant_ids"][state["current_seat"]])
    try:
        engine.apply_action(state, not_on_turn, {"kind": "draw"})
        assert False, "acting out of turn should be rejected"
    except IllegalAction:
        pass


def test_apply_action_rejects_a_card_not_in_hand():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    try:
        engine.apply_action(state, actor, {"kind": "play", "card_id": "not-real", "chosen_color": None})
        assert False, "playing a card not in hand should be rejected"
    except IllegalAction:
        pass


def test_apply_action_rejects_an_illegal_color_and_number_mismatch():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    top = state["discard_pile"][-1]
    illegal = next(
        (c for c in state["hands"][actor] if not _can_play(c, state["active_color"], top)), None
    )
    if illegal is None:
        return  # rare shuffle where every card in hand happens to be legal - nothing to assert
    try:
        engine.apply_action(state, actor, {"kind": "play", "card_id": illegal["id"], "chosen_color": None})
        assert False, "an illegal card should be rejected"
    except IllegalAction:
        pass


def test_apply_action_rejects_a_wild_without_a_chosen_color():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    state["hands"][actor].append({"id": "wild-test", "color": "Wild", "kind": "wild", "value": None})
    try:
        engine.apply_action(state, actor, {"kind": "play", "card_id": "wild-test", "chosen_color": None})
        assert False, "a wild card without a chosen color should be rejected"
    except IllegalAction:
        pass


def test_draw_action_adds_one_card_and_passes_the_turn():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B", "C"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    state = engine.apply_action(state, actor, {"kind": "draw"})
    assert engine.is_round_over(state)
    state, points = engine.time_up(state)
    assert points == {}
    assert len(state["hands"][actor]) == 8
    assert state["participant_ids"][state["current_seat"]] != actor


def test_skip_card_skips_exactly_one_player():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B", "C"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    skip_card = {"id": "skip-test", "color": state["active_color"], "kind": "skip", "value": None}
    state["hands"][actor].append(skip_card)
    state = engine.apply_action(state, actor, {"kind": "play", "card_id": "skip-test", "chosen_color": None})
    state, _ = engine.time_up(state)
    actor_seat = state["participant_ids"].index(actor)
    expected_next = state["participant_ids"][(actor_seat + 2) % 3]
    assert state["participant_ids"][state["current_seat"]] == expected_next


def test_reverse_acts_as_a_skip_with_exactly_two_players():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    reverse_card = {"id": "rev-test", "color": state["active_color"], "kind": "reverse", "value": None}
    state["hands"][actor].append(reverse_card)
    state = engine.apply_action(state, actor, {"kind": "play", "card_id": "rev-test", "chosen_color": None})
    state, _ = engine.time_up(state)
    # The SAME player goes again - the opponent's turn was skipped entirely.
    assert state["participant_ids"][state["current_seat"]] == actor


def test_reverse_flips_direction_with_more_than_two_players():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B", "C", "D"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    reverse_card = {"id": "rev-test", "color": state["active_color"], "kind": "reverse", "value": None}
    state["hands"][actor].append(reverse_card)
    state = engine.apply_action(state, actor, {"kind": "play", "card_id": "rev-test", "chosen_color": None})
    state, _ = engine.time_up(state)
    assert state["direction"] == -1
    actor_seat = state["participant_ids"].index(actor)
    expected_next = state["participant_ids"][(actor_seat - 1) % 4]
    assert state["participant_ids"][state["current_seat"]] == expected_next


def test_draw_two_forces_the_next_player_to_draw_and_lose_their_turn():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B", "C"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    victim = state["participant_ids"][(state["current_seat"] + 1) % 3]
    victim_hand_before = len(state["hands"][victim])
    draw2_card = {"id": "d2-test", "color": state["active_color"], "kind": "draw2", "value": None}
    state["hands"][actor].append(draw2_card)
    state = engine.apply_action(state, actor, {"kind": "play", "card_id": "d2-test", "chosen_color": None})
    state, _ = engine.time_up(state)
    assert len(state["hands"][victim]) == victim_hand_before + 2
    assert state["participant_ids"][state["current_seat"]] not in (actor, victim) or len(state["participant_ids"]) == 2


def test_wild_draw_four_forces_four_cards_and_sets_the_chosen_color():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    victim = state["participant_ids"][(state["current_seat"] + 1) % 2]
    victim_hand_before = len(state["hands"][victim])
    wd4 = {"id": "wd4-test", "color": "Wild", "kind": "wild_draw4", "value": None}
    state["hands"][actor].append(wd4)
    state = engine.apply_action(state, actor, {"kind": "play", "card_id": "wd4-test", "chosen_color": "Green"})
    state, _ = engine.time_up(state)
    assert len(state["hands"][victim]) == victim_hand_before + 4
    assert state["active_color"] == "Green"


def test_card_count_is_conserved_through_a_full_hand():
    random.seed(3)
    engine = UnoEngine()
    players = ["A", "B", "C"]
    state = engine.initial_state(players)
    state, _ = engine.start_round(state, 0)
    assert _total_cards(state) == 108

    safety = 0
    round_index = 1  # start_round(0) already consumed by the initial deal above
    while state["hands_completed"] < 1 and safety < 500:
        safety += 1
        actor = state["participant_ids"][state["current_seat"]]
        hand, top = state["hands"][actor], state["discard_pile"][-1]
        legal = [c for c in hand if _can_play(c, state["active_color"], top)]
        if legal:
            card = legal[0]
            extra = {"chosen_color": "Red"} if card["color"] == "Wild" else {"chosen_color": None}
            state = engine.apply_action(state, actor, {"kind": "play", "card_id": card["id"], **extra})
        else:
            state = engine.apply_action(state, actor, {"kind": "draw"})
        state, _points = engine.time_up(state)
        assert _total_cards(state) == 108, f"card leak at turn {safety}"
        if state["phase"] == "reveal":
            state, _duration = engine.start_round(state, round_index)
            round_index += 1

    assert state["phase"] == "hand_over"
    assert state["last_hand_summary"]["winner_member_id"] in players


def test_hand_winner_scores_the_sum_of_opponents_remaining_card_points():
    random.seed(3)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    other = next(p for p in ["A", "B"] if p != actor)
    # Hand-craft the winning move: actor has exactly one card left, which is legal.
    winning_card = {"id": "last-card", "color": state["active_color"], "kind": "number", "value": 5}
    state["hands"][actor] = [winning_card]
    state["hands"][other] = [
        {"id": "o1", "color": "Red", "kind": "number", "value": 7},
        {"id": "o2", "color": "Blue", "kind": "skip", "value": None},
    ]
    state = engine.apply_action(state, actor, {"kind": "play", "card_id": "last-card", "chosen_color": None})
    state, points = engine.time_up(state)
    assert state["phase"] == "hand_over"
    assert points == {actor: 27}  # 7 + 20
    assert state["last_hand_summary"]["winner_member_id"] == actor


def test_time_up_is_idempotent_against_a_second_call():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    state = engine.apply_action(state, actor, {"kind": "draw"})
    state, first_points = engine.time_up(state)
    state_again, second_points = engine.time_up(state)
    assert second_points == {}
    assert state_again == state


def test_afk_player_auto_draws_and_passes():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    actor = state["participant_ids"][state["current_seat"]]
    hand_before = len(state["hands"][actor])
    # Nobody ever calls apply_action - time_up must still resolve the turn.
    state, points = engine.time_up(state)
    assert len(state["hands"][actor]) == hand_before + 1
    assert points == {}


def test_draw_pile_reshuffles_from_discard_when_exhausted():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B"])
    state, _ = engine.start_round(state, 0)
    # Drain the draw pile down to nothing and pad the discard pile so a
    # reshuffle is forced on the next draw.
    state["draw_pile"] = []
    state["discard_pile"] = state["discard_pile"] + [
        {"id": f"pad{i}", "color": "Red", "kind": "number", "value": 1} for i in range(10)
    ]
    actor = state["participant_ids"][state["current_seat"]]
    hand_before = len(state["hands"][actor])
    state = engine.apply_action(state, actor, {"kind": "draw"})
    state, _ = engine.time_up(state)
    assert len(state["hands"][actor]) == hand_before + 1
    assert len(state["discard_pile"]) == 1  # only the (preserved) top card remains


def test_check_game_over_true_only_after_num_hands_completed():
    engine = UnoEngine()
    for completed in range(NUM_HANDS):
        assert not engine.check_game_over({"hands_completed": completed}, 0, engine.DEFAULT_TOTAL_ROUNDS)
    assert engine.check_game_over({"hands_completed": NUM_HANDS}, 0, engine.DEFAULT_TOTAL_ROUNDS)


def test_build_display_state_never_leaks_other_players_hand_contents():
    random.seed(1)
    engine = UnoEngine()
    state = engine.initial_state(["A", "B", "C"])
    state, _ = engine.start_round(state, 0)

    a_view = engine.build_display_state(state, "A")
    assert len(a_view["my_hand"]) == 7
    assert a_view["hand_sizes"] == {"A": 7, "B": 7, "C": 7}
    assert all(k not in a_view for k in ("other_hands", "all_hands", "hands"))
