"""Pure unit tests against the card-game engine and the standalone hand
evaluator - no DB, no WebSocket. Mirrors test_game_engines.py/
test_party_engines.py's split from the WS-level tests in
test_card_games.py."""

import random

import pytest

from app.card_engines.base import IllegalAction
from app.card_engines.poker_cards import best_hand, evaluate_5, hand_description
from app.card_engines.poker_engine import PokerEngine, _compute_pots


# ---- Hand evaluator ----

HAND_CASES = [
    (["Ah", "Kh", "Qh", "Jh", "Th"], "Straight Flush"),
    (["5h", "5d", "5s", "5c", "Kh"], "Four of a Kind"),
    (["Kh", "Kd", "Ks", "2c", "2h"], "Full House"),
    (["2h", "7h", "9h", "Jh", "Ah"], "Flush"),
    (["5h", "6d", "7s", "8c", "9h"], "Straight"),
    (["Ah", "2d", "3s", "4c", "5h"], "Straight"),  # the wheel, ace plays low
    (["Qh", "Qd", "Qs", "7c", "2h"], "Three of a Kind"),
    (["Jh", "Jd", "4s", "4c", "2h"], "Two Pair"),
    (["9h", "9d", "4s", "7c", "2h"], "Pair"),
    (["Ah", "Kd", "9s", "7c", "2h"], "High Card"),
]


@pytest.mark.parametrize("cards,expected", HAND_CASES)
def test_evaluate_5_identifies_every_hand_category(cards, expected):
    assert hand_description(evaluate_5(cards)) == expected


def test_higher_pair_kicker_wins():
    assert evaluate_5(["Ah", "Ad", "Ks", "Kc", "Qh"]) > evaluate_5(["Ah", "Ad", "Ks", "Kc", "Jh"])


def test_higher_trips_beats_lower_full_house_pair():
    assert evaluate_5(["Kh", "Kd", "Ks", "Qc", "Qh"]) > evaluate_5(["2h", "2d", "2s", "Ac", "Ah"])


def test_flush_beats_straight():
    assert evaluate_5(["2h", "7h", "9h", "Jh", "Ah"]) > evaluate_5(["5h", "6d", "7s", "8c", "9h"])


def test_quads_kicker_matters():
    assert evaluate_5(["5h", "5d", "5s", "5c", "Kh"]) > evaluate_5(["5h", "5d", "5s", "5c", "2h"])


def test_best_hand_picks_the_best_5_of_7_and_drops_the_rest():
    hole = ["Ah", "Ad"]
    board = ["Ks", "Qd", "Jh", "2c", "9h"]
    value = best_hand(hole + board)
    assert hand_description(value) == "Pair"
    assert value[1] == [14, 13, 12, 11]  # pair of aces + K, Q, J - the 2 and 9 are dropped


def test_best_hand_finds_the_board_playing_straight_flush():
    hole = ["2c", "3d"]  # irrelevant - the board alone is a straight flush
    board = ["Th", "Jh", "Qh", "Kh", "Ah"]
    assert hand_description(best_hand(hole + board)) == "Straight Flush"


# ---- Side pots ----

def test_compute_pots_single_level_no_side_pot():
    pots = _compute_pots({"A": 100, "B": 100, "C": 100}, folded=[])
    assert pots == [(300, ["A", "B", "C"])]


def test_compute_pots_two_all_in_levels():
    pots = _compute_pots({"A": 100, "B": 300, "C": 500}, folded=[])
    assert pots == [(300, ["A", "B", "C"]), (400, ["B", "C"]), (200, ["C"])]
    assert sum(p[0] for p in pots) == 900


def test_compute_pots_excludes_folded_player_from_eligibility_not_from_paying_in():
    pots = _compute_pots({"A": 100, "B": 300, "C": 300}, folded=["A"])
    assert pots == [(300, ["B", "C"]), (400, ["B", "C"])]
    assert sum(p[0] for p in pots) == 700  # A's 100 is dead money, still counted


# ---- Full engine playthroughs ----

def _played_to_showdown(engine, players, seed, starting_chips=1000):
    random.seed(seed)
    state = engine.initial_state(players, starting_chips)
    state = engine.start_hand(state)
    safety = 0
    while state["phase"] not in ("hand_over", "showdown") and safety < 50:
        safety += 1
        actor = state["action_on"]
        legal = engine.legal_actions(state, actor)
        kind = "check" if "check" in legal["actions"] else "call"
        state = engine.apply_action(state, actor, {"kind": kind})
    return state


def test_heads_up_dealer_posts_small_blind_and_acts_first():
    random.seed(3)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B"], 1000)
    state = engine.start_hand(state)
    dealer = state["participant_ids"][state["dealer_index"]]
    assert dealer == "A"
    assert state["bets_this_street"]["A"] == state["small_blind"]
    assert state["bets_this_street"]["B"] == state["big_blind"]
    assert state["action_on"] == "A"


def test_full_hand_to_showdown_conserves_chips_and_picks_the_right_winner():
    engine = PokerEngine()
    state = _played_to_showdown(engine, ["A", "B", "C"], seed=42)
    assert state["phase"] == "showdown"
    pot_before = sum(state["total_bet_this_hand"].values())

    state, deltas = engine.resolve_hand(state)
    assert sum(state["chip_stacks"].values()) == 3000
    assert sum(deltas.values()) == pot_before
    # Exactly one winner took the whole (uncontested-side-pot) pot here.
    assert sum(1 for d in deltas.values() if d > 0) == 1


def test_fold_to_win_awards_the_pot_without_a_showdown():
    random.seed(1)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B", "C"], 1000)
    state = engine.start_hand(state)
    state = engine.apply_action(state, "A", {"kind": "raise", "to": 50})
    state = engine.apply_action(state, "B", {"kind": "fold"})
    state = engine.apply_action(state, "C", {"kind": "fold"})
    assert engine.is_hand_over(state)

    state, deltas = engine.resolve_hand(state)
    assert deltas["A"] > 0
    assert deltas["B"] == 0 and deltas["C"] == 0
    assert state["showdown"] is None  # nobody's hand is ever revealed on a fold-out
    assert sum(state["chip_stacks"].values()) == 3000


def test_side_pot_excludes_short_stack_from_the_extra_action():
    random.seed(11)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B", "C"], 1000)
    state["chip_stacks"]["A"] = 30
    state = engine.start_hand(state)

    first = state["action_on"]
    legal = engine.legal_actions(state, first)
    state = engine.apply_action(state, first, {"kind": "raise", "to": legal["max_raise_to"]})
    # Bring everyone to the all-in level, then have the two full-stacked
    # players keep betting on the flop to force a genuine side pot.
    while state["phase"] == "preflop":
        actor = state["action_on"]
        state = engine.apply_action(state, actor, {"kind": "call"})

    flop_actor = state["action_on"]
    other = next(p for p in ["B", "C"] if p != flop_actor)
    state = engine.apply_action(state, flop_actor, {"kind": "raise", "to": 100})
    state = engine.apply_action(state, other, {"kind": "call"})

    safety = 0
    while state["phase"] not in ("hand_over", "showdown") and safety < 20:
        safety += 1
        actor = state["action_on"]
        state = engine.apply_action(state, actor, {"kind": "check"})

    state, deltas = engine.resolve_hand(state)
    assert sum(state["chip_stacks"].values()) == 2030
    assert len(state["pot_summary"]) == 2
    main_pot, side_pot = state["pot_summary"]
    assert set(main_pot["eligible"]) == {"A", "B", "C"}
    assert set(side_pot["eligible"]) == {"B", "C"}
    assert "A" not in side_pot["winners"]


def test_short_all_in_call_does_not_change_the_current_bet():
    random.seed(5)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B", "C"], 1000)
    state = engine.start_hand(state)
    actor = state["action_on"]
    state = engine.apply_action(state, actor, {"kind": "raise", "to": 200})
    nxt = state["action_on"]
    state["chip_stacks"][nxt] = 50
    legal = engine.legal_actions(state, nxt)
    assert legal["actions"] == ["fold", "call"]  # too short to raise
    assert legal["call_amount"] == 50
    state = engine.apply_action(state, nxt, {"kind": "call"})
    assert nxt in state["all_in"]
    assert state["current_bet"] == 200
    assert state["chip_stacks"][nxt] == 0


def test_short_all_in_raise_reopens_action_and_caps_at_the_stack():
    random.seed(5)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B", "C"], 1000)
    state = engine.start_hand(state)
    actor = state["action_on"]
    state = engine.apply_action(state, actor, {"kind": "raise", "to": 200})
    nxt = state["action_on"]
    state["chip_stacks"][nxt] = 220
    legal = engine.legal_actions(state, nxt)
    assert legal["max_raise_to"] == legal["min_raise_to"] == 225  # can't afford a full min-raise
    state = engine.apply_action(state, nxt, {"kind": "raise", "to": 225})
    assert nxt in state["all_in"]
    assert state["current_bet"] == 225
    assert state["acted_this_street"] == [nxt]  # reopened for everyone else


def test_apply_action_rejects_acting_out_of_turn():
    random.seed(5)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B", "C"], 1000)
    state = engine.start_hand(state)
    not_on_turn = next(p for p in ["A", "B", "C"] if p != state["action_on"])
    with pytest.raises(IllegalAction):
        engine.apply_action(state, not_on_turn, {"kind": "fold"})


def test_apply_action_rejects_checking_into_a_bet():
    random.seed(5)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B", "C"], 1000)
    state = engine.start_hand(state)
    actor = state["action_on"]
    with pytest.raises(IllegalAction):
        engine.apply_action(state, actor, {"kind": "check"})  # owes the big blind


def test_is_game_over_true_only_when_at_most_one_player_has_chips():
    engine = PokerEngine()
    assert engine.is_game_over({"A": 0, "B": 2000})
    assert not engine.is_game_over({"A": 100, "B": 1900})


def test_build_display_state_never_reveals_other_players_hole_cards_mid_hand():
    random.seed(5)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B", "C"], 1000)
    state = engine.start_hand(state)
    a_view = engine.build_display_state(state, "A")
    a_seat = next(s for s in a_view["seats"] if s["member_id"] == "A")
    b_seat = next(s for s in a_view["seats"] if s["member_id"] == "B")
    assert a_seat["hole_cards"] is not None
    assert b_seat["hole_cards"] is None


def test_chip_conservation_and_dealer_rotation_across_several_hands():
    random.seed(99)
    engine = PokerEngine()
    players = ["A", "B", "C", "D"]
    state = engine.initial_state(players, 1000)
    dealer_history = []

    for _ in range(6):
        state = engine.start_hand(state)
        dealer_history.append(state["dealer_index"])
        safety = 0
        while state["phase"] not in ("hand_over", "showdown") and safety < 50:
            safety += 1
            actor = state["action_on"]
            legal = engine.legal_actions(state, actor)
            kind = "check" if "check" in legal["actions"] else "call"
            state = engine.apply_action(state, actor, {"kind": kind})
        state, _ = engine.resolve_hand(state)
        assert sum(state["chip_stacks"].values()) == 4000

    # The dealer button should move around the table, not stick on one seat.
    assert len(set(dealer_history)) > 1


def test_folded_players_hole_cards_are_never_shown_even_after_resolution():
    random.seed(1)
    engine = PokerEngine()
    state = engine.initial_state(["A", "B", "C"], 1000)
    state = engine.start_hand(state)
    state = engine.apply_action(state, "A", {"kind": "raise", "to": 50})
    state = engine.apply_action(state, "B", {"kind": "fold"})
    state = engine.apply_action(state, "C", {"kind": "call"})
    # Run to showdown by checking down every remaining street.
    safety = 0
    while state["phase"] not in ("hand_over", "showdown") and safety < 20:
        safety += 1
        actor = state["action_on"]
        state = engine.apply_action(state, actor, {"kind": "check"})
    state, _ = engine.resolve_hand(state)
    view = engine.build_display_state(state, "C")
    b_seat = next(s for s in view["seats"] if s["member_id"] == "B")
    assert b_seat["hole_cards"] is None  # B folded - never revealed, even post-hand
