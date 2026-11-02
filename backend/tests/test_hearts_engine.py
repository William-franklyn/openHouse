"""Pure unit tests directly against the Hearts engine - no DB, no
WebSocket. Mirrors test_uno_engine.py/test_codenames_engine.py's split
from the WS-level tests in test_hearts_games.py."""

import random
from collections import Counter

from app.party_engines.base import IllegalAction
from app.party_engines.hearts_engine import HeartsEngine, PASS_DIRECTIONS, _card_points, _fresh_deck, _legal_cards


def _fresh_game(players=("A", "B", "C", "D"), seed=1):
    random.seed(seed)
    engine = HeartsEngine()
    state = engine.initial_state(list(players))
    state, duration = engine.start_round(state, 0)
    return engine, state, duration


def test_fresh_deck_has_52_unique_cards():
    deck = _fresh_deck()
    assert len(deck) == 52
    assert len({c["id"] for c in deck}) == 52
    counts = Counter(c["suit"] for c in deck)
    assert counts == {"C": 13, "D": 13, "H": 13, "S": 13}


def test_card_points_match_standard_hearts_scoring():
    assert _card_points({"suit": "H", "rank": 5}) == 1
    assert _card_points({"suit": "S", "rank": 12}) == 13
    assert _card_points({"suit": "S", "rank": 13}) == 0
    assert _card_points({"suit": "C", "rank": 14}) == 0


def test_initial_deal_gives_everyone_thirteen_cards():
    engine, state, _ = _fresh_game()
    assert all(len(h) == 13 for h in state["hands"].values())
    total = sum(len(h) for h in state["hands"].values())
    assert total == 52


def test_first_hand_pass_direction_is_left_and_cycles_thereafter():
    engine, state, _ = _fresh_game()
    assert state["pass_direction"] == "left"
    assert state["phase"] == "passing"


def test_must_lead_the_two_of_clubs_on_the_first_trick():
    hand = [{"id": "C2", "suit": "C", "rank": 2}, {"id": "H5", "suit": "H", "rank": 5}]
    state = {"current_trick": [], "trick_number": 0, "hearts_broken": False, "lead_suit": None}
    legal = _legal_cards(hand, state)
    assert [c["id"] for c in legal] == ["C2"]


def test_cannot_lead_hearts_until_broken_unless_hand_is_all_hearts():
    hand = [{"id": "H5", "suit": "H", "rank": 5}, {"id": "D9", "suit": "D", "rank": 9}]
    state = {"current_trick": [], "trick_number": 1, "hearts_broken": False, "lead_suit": None}
    legal = _legal_cards(hand, state)
    assert [c["id"] for c in legal] == ["D9"]

    all_hearts = [{"id": "H5", "suit": "H", "rank": 5}, {"id": "H9", "suit": "H", "rank": 9}]
    legal = _legal_cards(all_hearts, state)
    assert {c["id"] for c in legal} == {"H5", "H9"}


def test_must_follow_suit_when_able():
    hand = [{"id": "D9", "suit": "D", "rank": 9}, {"id": "C3", "suit": "C", "rank": 3}]
    state = {
        "current_trick": [{"member_id": "X", "card": {"id": "D2", "suit": "D", "rank": 2}}],
        "trick_number": 1,
        "hearts_broken": False,
        "lead_suit": "D",
    }
    legal = _legal_cards(hand, state)
    assert [c["id"] for c in legal] == ["D9"]


def test_cannot_play_a_point_card_on_the_first_trick_unless_forced():
    hand = [
        {"id": "H5", "suit": "H", "rank": 5},
        {"id": "SQ", "suit": "S", "rank": 12},
        {"id": "C3", "suit": "C", "rank": 3},
    ]
    state = {
        "current_trick": [{"member_id": "X", "card": {"id": "D2", "suit": "D", "rank": 2}}],
        "trick_number": 0,
        "hearts_broken": False,
        "lead_suit": "D",
    }
    legal = _legal_cards(hand, state)
    assert [c["id"] for c in legal] == ["C3"]

    only_points = [{"id": "H5", "suit": "H", "rank": 5}, {"id": "SQ", "suit": "S", "rank": 12}]
    legal = _legal_cards(only_points, state)
    assert {c["id"] for c in legal} == {"H5", "SQ"}


def test_passing_phase_rejects_wrong_count_or_cards_not_in_hand():
    engine, state, _ = _fresh_game()
    actor = state["participant_ids"][0]
    hand_ids = [c["id"] for c in state["hands"][actor]]
    try:
        engine.apply_action(state, actor, {"kind": "pass", "card_ids": hand_ids[:2]})
        assert False, "passing only 2 cards should be rejected"
    except IllegalAction:
        pass
    try:
        engine.apply_action(state, actor, {"kind": "pass", "card_ids": ["not-real-1", "not-real-2", "not-real-3"]})
        assert False, "passing cards not in hand should be rejected"
    except IllegalAction:
        pass


def test_passing_moves_cards_to_the_correct_neighbor():
    engine, state, _ = _fresh_game(seed=5)
    assert state["pass_direction"] == "left"
    for member_id in state["participant_ids"]:
        cards = state["hands"][member_id][:3]
        state = engine.apply_action(state, member_id, {"kind": "pass", "card_ids": [c["id"] for c in cards]})
    assert engine.is_round_over(state)

    passed_cards = {m: [c["id"] for c in state["hands"][m][:3]] for m in state["participant_ids"]}
    state, _ = engine.time_up(state)
    assert state["phase"] == "reveal"
    assert state["last_event"] == {"kind": "cards_passed", "direction": "left"}

    n = len(state["participant_ids"])
    for i, member_id in enumerate(state["participant_ids"]):
        left_neighbor = state["participant_ids"][(i + 1) % n]
        for card_id in passed_cards[member_id]:
            assert card_id in [c["id"] for c in state["hands"][left_neighbor]]
            assert card_id not in [c["id"] for c in state["hands"][member_id]]


def test_only_the_current_trick_player_may_play():
    engine, state, _ = _fresh_game()
    for member_id in state["participant_ids"]:
        cards = state["hands"][member_id][:3]
        state = engine.apply_action(state, member_id, {"kind": "pass", "card_ids": [c["id"] for c in cards]})
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


def test_trick_is_won_by_the_highest_card_of_the_lead_suit():
    engine = HeartsEngine()
    state = {
        "participant_ids": ["A", "B", "C", "D"],
        "current_trick": [
            {"member_id": "A", "card": {"id": "D9", "suit": "D", "rank": 9}},
            {"member_id": "B", "card": {"id": "DK", "suit": "D", "rank": 13}},
            {"member_id": "C", "card": {"id": "H2", "suit": "H", "rank": 2}},
        ],
        "lead_suit": "D",
        "trick_number": 1,
        "hearts_broken": True,
        "pending_action": {"kind": "play_card", "card_id": "D3"},
        "hands": {"A": [], "B": [], "C": [], "D": [{"id": "D3", "suit": "D", "rank": 3}]},
        "current_seat": 3,
        "tricks_won": {"A": [], "B": [], "C": [], "D": []},
        "phase": "trick",
        "pending_passes": {},
        "raw_scores": {"A": 0, "B": 0, "C": 0, "D": 0},
        "hand_points": None,
        "winner": None,
        "hands_completed": 0,
    }
    state, points = engine.time_up(state)
    assert state["last_event"]["kind"] == "trick_won"
    assert state["last_event"]["member_id"] == "B"
    assert state["current_seat"] == state["participant_ids"].index("B")
    assert points == {}  # hand isn't over yet (only 1 trick played)


def test_shooting_the_moon_flips_the_hand_score():
    engine = HeartsEngine()
    all_hearts_and_queen = [{"suit": "H", "rank": r} for r in range(2, 15)] + [{"suit": "S", "rank": 12}]
    assert sum(_card_points(c) for c in all_hearts_and_queen) == 26
    state = {
        "participant_ids": ["A", "B", "C", "D"],
        "current_trick": [
            {"member_id": "B", "card": {"id": "C9", "suit": "C", "rank": 9}},
            {"member_id": "C", "card": {"id": "C5", "suit": "C", "rank": 5}},
            {"member_id": "D", "card": {"id": "C3", "suit": "C", "rank": 3}},
        ],
        "lead_suit": "C",
        "trick_number": 12,
        "hearts_broken": True,
        "pending_action": {"kind": "play_card", "card_id": "CK"},
        "hands": {"A": [{"id": "CK", "suit": "C", "rank": 13}], "B": [], "C": [], "D": []},
        "current_seat": 0,
        "tricks_won": {
            "A": all_hearts_and_queen + [{"suit": "C", "rank": 2}],
            "B": [],
            "C": [],
            "D": [],
        },
        "phase": "trick",
        "pending_passes": {},
        "raw_scores": {"A": 0, "B": 0, "C": 0, "D": 0},
        "hand_points": None,
        "winner": None,
        "hands_completed": 0,
    }
    state, points = engine.time_up(state)
    assert state["phase"] == "hand_over"
    assert state["hand_points"] == {"A": 0, "B": 26, "C": 26, "D": 26}
    assert points == {"A": 26, "B": 0, "C": 0, "D": 0}  # inverted: A shot the moon, scores best


def test_check_game_over_true_once_someone_reaches_the_target():
    engine = HeartsEngine()
    assert not engine.check_game_over({"winner": None}, 0, engine.DEFAULT_TOTAL_ROUNDS)
    assert engine.check_game_over({"winner": "A"}, 0, engine.DEFAULT_TOTAL_ROUNDS)


def test_time_up_is_idempotent_against_a_second_call():
    engine, state, _ = _fresh_game()
    # Everyone passes so the round is genuinely over.
    for member_id in state["participant_ids"]:
        cards = state["hands"][member_id][:3]
        state = engine.apply_action(state, member_id, {"kind": "pass", "card_ids": [c["id"] for c in cards]})
    state, _first_points = engine.time_up(state)
    state_again, second_points = engine.time_up(state)
    assert second_points == {}
    assert state_again == state


def test_build_display_state_never_leaks_other_players_hand_contents():
    engine, state, _ = _fresh_game()
    a_view = engine.build_display_state(state, "A")
    assert len(a_view["my_hand"]) == 13
    assert a_view["hand_sizes"] == {"A": 13, "B": 13, "C": 13, "D": 13}
    assert all(k not in a_view for k in ("other_hands", "all_hands", "hands"))


def test_pass_direction_cycle_matches_the_real_four_hand_rotation():
    assert PASS_DIRECTIONS == ("left", "right", "across", "hold")
