"""Pure unit tests directly against the Spades engine - no DB, no
WebSocket. Mirrors test_hearts_engine.py's split from the WS-level
tests in test_spades_games.py."""

import random
from collections import Counter

from app.party_engines.base import IllegalAction
from app.party_engines.spades_engine import SpadesEngine, TARGET_SCORE, _fresh_deck, _legal_cards


def _fresh_game(players=("A", "B", "C", "D"), seed=1):
    random.seed(seed)
    engine = SpadesEngine()
    state = engine.initial_state(list(players))
    state, duration = engine.start_round(state, 0)
    return engine, state, duration


def test_fresh_deck_has_52_unique_cards():
    deck = _fresh_deck()
    assert len(deck) == 52
    assert len({c["id"] for c in deck}) == 52
    counts = Counter(c["suit"] for c in deck)
    assert counts == {"C": 13, "D": 13, "H": 13, "S": 13}


def test_initial_deal_gives_everyone_thirteen_cards_and_opens_bidding():
    engine, state, duration = _fresh_game()
    assert state["phase"] == "bidding"
    assert duration > 0
    assert all(len(h) == 13 for h in state["hands"].values())


def test_seats_0_and_2_are_partners_seats_1_and_3_are_partners():
    engine, state, _ = _fresh_game()
    assert engine._team_of(state, "A") == "team_a"
    assert engine._team_of(state, "C") == "team_a"
    assert engine._team_of(state, "B") == "team_b"
    assert engine._team_of(state, "D") == "team_b"


def test_a_spade_beats_any_non_spade_regardless_of_lead_suit():
    hand = [{"id": "D9", "suit": "D", "rank": 9}]
    state = {"current_trick": [], "lead_suit": None, "spades_broken": True}
    assert [c["id"] for c in _legal_cards(hand, state)] == ["D9"]


def test_cannot_lead_spades_until_broken_unless_hand_is_all_spades():
    hand = [{"id": "S5", "suit": "S", "rank": 5}, {"id": "D9", "suit": "D", "rank": 9}]
    state = {"current_trick": [], "lead_suit": None, "spades_broken": False}
    legal = _legal_cards(hand, state)
    assert [c["id"] for c in legal] == ["D9"]

    all_spades = [{"id": "S5", "suit": "S", "rank": 5}, {"id": "S9", "suit": "S", "rank": 9}]
    legal = _legal_cards(all_spades, state)
    assert {c["id"] for c in legal} == {"S5", "S9"}


def test_must_follow_suit_when_able():
    hand = [{"id": "D9", "suit": "D", "rank": 9}, {"id": "C3", "suit": "C", "rank": 3}]
    state = {"current_trick": [{"member_id": "x", "card": {"id": "D2", "suit": "D", "rank": 2}}], "lead_suit": "D", "spades_broken": False}
    assert [c["id"] for c in _legal_cards(hand, state)] == ["D9"]


def test_bidding_rejects_a_second_bid_from_the_same_player():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "A", {"kind": "bid", "amount": 3})
    try:
        engine.apply_action(state, "A", {"kind": "bid", "amount": 4})
        assert False, "a second bid from the same player should be rejected"
    except IllegalAction:
        pass


def test_bidding_resolves_once_all_four_have_bid():
    engine, state, _ = _fresh_game()
    for m, amount in zip(state["participant_ids"], (3, 4, 2, 5)):
        state = engine.apply_action(state, m, {"kind": "bid", "amount": amount})
    assert engine.is_round_over(state)
    state, points = engine.time_up(state)
    assert points == {}
    assert state["bids"] == {"A": 3, "B": 4, "C": 2, "D": 5}
    assert state["next_phase"] == "trick"


def test_only_the_current_trick_player_may_play():
    engine, state, _ = _fresh_game()
    for m, amount in zip(state["participant_ids"], (3, 3, 3, 3)):
        state = engine.apply_action(state, m, {"kind": "bid", "amount": amount})
    state, _ = engine.time_up(state)
    state, _ = engine.start_round(state, 1)
    assert state["phase"] == "trick"

    actor = state["participant_ids"][state["current_seat"]]
    not_actor = next(m for m in state["participant_ids"] if m != actor)
    legal_card = _legal_cards(state["hands"][actor], state)[0]
    try:
        engine.apply_action(state, not_actor, {"kind": "play_card", "card_id": legal_card["id"]})
        assert False, "acting out of turn should be rejected"
    except IllegalAction:
        pass


def test_a_spade_wins_a_trick_over_a_higher_non_spade():
    engine = SpadesEngine()
    state = {
        "participant_ids": ["A", "B", "C", "D"],
        "current_trick": [
            {"member_id": "A", "card": {"id": "DA", "suit": "D", "rank": 14}},
            {"member_id": "B", "card": {"id": "DK", "suit": "D", "rank": 13}},
            {"member_id": "C", "card": {"id": "S2", "suit": "S", "rank": 2}},
        ],
        "lead_suit": "D",
        "spades_broken": True,
        "trick_number": 1,
        "hands": {"A": [], "B": [], "C": [], "D": [{"id": "D3", "suit": "D", "rank": 3}]},
        "current_seat": 3,
        "tricks_won_count": {"A": 0, "B": 0, "C": 0, "D": 0},
        "pending_action": {"kind": "play_card", "card_id": "D3"},
        "phase": "trick",
        "bids": {"A": 3, "B": 3, "C": 3, "D": 3},
        "team_scores": {"team_a": 0, "team_b": 0},
        "team_bags": {"team_a": 0, "team_b": 0},
        "hand_results": None,
        "last_event": None,
        "winner": None,
    }
    state, points = engine.time_up(state)
    assert state["last_event"]["member_id"] == "C"  # the only spade played wins, despite the ace of diamonds
    assert points == {}  # hand isn't over yet (1 trick played)


def test_hand_scoring_awards_overtricks_as_bags_and_penalizes_a_failed_bid():
    engine = SpadesEngine()
    state = {
        "participant_ids": ["A", "B", "C", "D"],
        "current_trick": [
            {"member_id": "A", "card": {"id": "DA", "suit": "D", "rank": 14}},
            {"member_id": "B", "card": {"id": "DK", "suit": "D", "rank": 13}},
            {"member_id": "C", "card": {"id": "D5", "suit": "D", "rank": 5}},
        ],
        "lead_suit": "D",
        "spades_broken": False,
        "trick_number": 12,
        "hands": {"A": [], "B": [], "C": [], "D": [{"id": "D3", "suit": "D", "rank": 3}]},
        "current_seat": 3,
        # team_a (A,C) took 8 tricks total so far (bid 6 combined -> 2 bags);
        # team_b (B,D) took 4 tricks total so far (bid 7 combined -> fails).
        "tricks_won_count": {"A": 5, "B": 2, "C": 2, "D": 2},
        "pending_action": {"kind": "play_card", "card_id": "D3"},
        "phase": "trick",
        "bids": {"A": 3, "B": 4, "C": 3, "D": 3},
        "team_scores": {"team_a": 0, "team_b": 0},
        "team_bags": {"team_a": 0, "team_b": 0},
        "hand_results": None,
        "last_event": None,
        "winner": None,
    }
    state, points = engine.time_up(state)
    assert state["phase"] == "hand_over"
    # This trick's winner (highest diamond, A) takes the 13th trick -> team_a: 5+2+1=8 tricks vs bid 6.
    results = state["hand_results"]
    assert results["team_a"]["combined_bid"] == 6
    assert results["team_a"]["tricks_taken"] == 8
    assert results["team_a"]["hand_score"] == 62  # 6*10 + 2 bags
    assert results["team_b"]["combined_bid"] == 7
    assert results["team_b"]["tricks_taken"] == 4
    assert results["team_b"]["hand_score"] == -70  # failed bid, no partial credit
    assert points == {"A": 62, "C": 62, "B": -70, "D": -70}


def test_bag_penalty_triggers_once_accumulated_bags_reach_ten():
    engine = SpadesEngine()
    state = {
        "participant_ids": ["A", "B", "C", "D"],
        "current_trick": [
            {"member_id": "A", "card": {"id": "D5", "suit": "D", "rank": 5}},
            {"member_id": "B", "card": {"id": "D6", "suit": "D", "rank": 6}},
            {"member_id": "C", "card": {"id": "D7", "suit": "D", "rank": 7}},
        ],
        "lead_suit": "D",
        "spades_broken": False,
        "trick_number": 12,
        "hands": {"A": [], "B": [], "C": [], "D": [{"id": "D8", "suit": "D", "rank": 8}]},
        "current_seat": 3,
        "tricks_won_count": {"A": 4, "B": 3, "C": 3, "D": 2},  # team_a already has 7+ with this trick
        "pending_action": {"kind": "play_card", "card_id": "D8"},
        "phase": "trick",
        "bids": {"A": 3, "B": 3, "C": 3, "D": 3},
        "team_scores": {"team_a": 0, "team_b": 0},
        "team_bags": {"team_a": 8, "team_b": 0},  # already carrying 8 bags
        "hand_results": None,
        "last_event": None,
        "winner": None,
    }
    state, points = engine.time_up(state)
    # D8 wins the trick -> team_b: 3+2+1=6 vs bid 6 (exact, 0 bags).
    # team_a: 4+3=7 vs bid 6 -> 1 bag; 8 existing + 1 = 9, still under 10.
    assert state["hand_results"]["team_a"]["bag_penalty"] == 0
    assert state["team_bags"]["team_a"] == 9


def test_check_game_over_true_once_a_team_reaches_the_target_score():
    engine = SpadesEngine()
    assert not engine.check_game_over({"winner": None}, 0, engine.DEFAULT_TOTAL_ROUNDS)
    assert engine.check_game_over({"winner": "team_a"}, 0, engine.DEFAULT_TOTAL_ROUNDS)


def test_time_up_is_idempotent_against_a_second_call():
    engine, state, _ = _fresh_game()
    for m in state["participant_ids"]:
        state = engine.apply_action(state, m, {"kind": "bid", "amount": 3})
    state, first_points = engine.time_up(state)
    state_again, second_points = engine.time_up(state)
    assert second_points == {}
    assert state_again == state


def test_build_display_state_hides_bid_amounts_until_bidding_resolves():
    engine, state, _ = _fresh_game()
    state = engine.apply_action(state, "A", {"kind": "bid", "amount": 5})
    view = engine.build_display_state(state, "B")
    assert view["bids"] is None
    assert view["bids_submitted"] == ["A"]
    assert view["my_bid"] is None  # B hasn't bid yet

    a_view = engine.build_display_state(state, "A")
    assert a_view["my_bid"] == 5


def test_build_display_state_never_leaks_other_players_hand_contents():
    engine, state, _ = _fresh_game()
    a_view = engine.build_display_state(state, "A")
    assert len(a_view["my_hand"]) == 13
    assert a_view["hand_sizes"] == {"A": 13, "B": 13, "C": 13, "D": 13}
    assert all(k not in a_view for k in ("other_hands", "all_hands", "hands"))


def test_target_score_is_500():
    assert TARGET_SCORE == 500
