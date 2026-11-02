"""Pure unit tests directly against the Werewolf engine - no DB, no
WebSocket. Mirrors test_hearts_engine.py's split from the WS-level
tests in test_werewolf_games.py."""

import random
from collections import Counter

from app.party_engines.base import IllegalAction
from app.party_engines.werewolf_engine import WerewolfEngine, _tally


def _fresh_game(players, seed=1):
    random.seed(seed)
    engine = WerewolfEngine()
    state = engine.initial_state(list(players))
    state, duration = engine.start_round(state, 0)
    return engine, state, duration


def test_role_counts_scale_with_player_count():
    for n in range(5, 13):
        engine, state, _ = _fresh_game([f"p{i}" for i in range(n)], seed=n)
        counts = Counter(state["roles"].values())
        assert counts["werewolf"] >= 1
        assert sum(counts.values()) == n
        if n >= 5:
            assert counts["seer"] == 1
        if n >= 6:
            assert counts["doctor"] == 1


def test_fresh_game_opens_on_night_one():
    engine, state, duration = _fresh_game([f"p{i}" for i in range(7)])
    assert state["phase"] == "night_actions"
    assert state["night_number"] == 1
    assert duration > 0
    assert all(state["alive"].values())


def test_tally_majority_tie_and_empty():
    assert _tally({"a": "x", "b": "x", "c": "y"}) == "x"
    assert _tally({"a": "x", "b": "y"}) is None  # tie -> no elimination
    assert _tally({"a": "abstain", "b": "abstain"}) is None
    assert _tally({}) is None


def test_villagers_have_no_night_action():
    engine, state, _ = _fresh_game([f"p{i}" for i in range(7)])
    villager = next(m for m, r in state["roles"].items() if r == "villager")
    try:
        engine.apply_action(state, villager, {"kind": "wolf_vote", "target_id": "p0"})
        assert False, "a villager should have no night action"
    except IllegalAction:
        pass


def test_a_player_cannot_submit_the_wrong_role_kind():
    engine, state, _ = _fresh_game([f"p{i}" for i in range(7)])
    seer = next(m for m, r in state["roles"].items() if r == "seer")
    try:
        engine.apply_action(state, seer, {"kind": "wolf_vote", "target_id": "p0"})
        assert False, "the seer should not be able to submit a wolf_vote"
    except IllegalAction:
        pass


def test_doctor_save_cancels_the_wolves_kill():
    engine, state, _ = _fresh_game(["w", "d", "s", "v1", "v2", "v3"], seed=1)
    roles = state["roles"]
    wolf = next(m for m, r in roles.items() if r == "werewolf")
    doctor = next(m for m, r in roles.items() if r == "doctor")
    seer = next(m for m, r in roles.items() if r == "seer")
    victim = next(m for m in state["participant_ids"] if m != wolf)

    state = engine.apply_action(state, wolf, {"kind": "wolf_vote", "target_id": victim})
    state = engine.apply_action(state, doctor, {"kind": "doctor_save", "target_id": victim})
    other_target = next(m for m in state["participant_ids"] if m != seer)
    state = engine.apply_action(state, seer, {"kind": "seer_inspect", "target_id": other_target})
    assert engine.is_round_over(state)

    state, points = engine.time_up(state)
    assert state["last_event"] == {"kind": "night_result", "night_number": 1, "died_member_id": None}
    assert points == {}
    assert state["seer_knowledge"][seer][other_target] == roles[other_target]


def test_an_undefended_victim_dies_at_night():
    engine, state, _ = _fresh_game(["w", "d", "s", "v1", "v2", "v3"], seed=2)
    roles = state["roles"]
    wolf = next(m for m, r in roles.items() if r == "werewolf")
    doctor = next(m for m, r in roles.items() if r == "doctor")
    seer = next(m for m, r in roles.items() if r == "seer")
    victim = next(m for m in state["participant_ids"] if m not in (wolf, doctor))

    state = engine.apply_action(state, wolf, {"kind": "wolf_vote", "target_id": victim})
    other_target = next(m for m in state["participant_ids"] if m != doctor and m != victim)
    state = engine.apply_action(state, doctor, {"kind": "doctor_save", "target_id": other_target})
    state = engine.apply_action(state, seer, {"kind": "seer_inspect", "target_id": wolf})

    state, _points = engine.time_up(state)
    assert state["last_event"]["died_member_id"] == victim
    assert state["alive"][victim] is False
    assert state["seer_knowledge"][seer][wolf] == "werewolf"


def test_day_vote_lynches_the_majority_target_and_reveals_the_tally():
    engine, state, _ = _fresh_game(["a", "b", "c", "d", "e"], seed=3)
    state["phase"] = "day_vote"
    state["day_votes"] = {}
    for m in state["participant_ids"]:
        target = "a" if m != "a" else "b"
        state = engine.apply_action(state, m, {"kind": "day_vote", "target_id": target})
    assert engine.is_round_over(state)
    state, _points = engine.time_up(state)
    assert state["last_event"]["lynched_member_id"] == "a"
    assert state["alive"]["a"] is False
    assert state["last_event"]["votes"]["a"] == "b"


def test_dead_players_cannot_act():
    engine, state, _ = _fresh_game([f"p{i}" for i in range(7)], seed=4)
    victim = next(m for m, r in state["roles"].items() if r == "villager")
    state["alive"][victim] = False
    try:
        engine.apply_action(state, victim, {"kind": "day_vote", "target_id": "p0"})
        assert False, "a dead player should not be able to act"
    except IllegalAction:
        pass


def test_villagers_win_once_every_werewolf_is_dead():
    engine, state, _ = _fresh_game([f"p{i}" for i in range(5)], seed=5)
    wolf = next(m for m, r in state["roles"].items() if r == "werewolf")
    state["alive"][wolf] = False
    assert engine._check_winner(state) == "villagers"


def test_werewolves_win_once_they_equal_or_outnumber_the_rest():
    engine = WerewolfEngine()
    state = engine.initial_state(["w1", "w2", "s", "v1"])
    state["roles"] = {"w1": "werewolf", "w2": "werewolf", "s": "seer", "v1": "villager"}
    state["alive"] = {"w1": True, "w2": True, "s": True, "v1": False}  # 2 wolves vs 1 other
    assert engine._check_winner(state) == "werewolves"
    state["alive"] = {"w1": True, "w2": True, "s": True, "v1": True}  # 2 wolves vs 2 others - tie goes to wolves
    assert engine._check_winner(state) == "werewolves"
    state["alive"] = {"w1": True, "w2": False, "s": True, "v1": True}  # 1 wolf vs 2 others
    assert engine._check_winner(state) is None


def test_winning_team_gets_credit_including_dead_teammates():
    engine = WerewolfEngine()
    state = engine.initial_state(["w1", "w2", "s", "v1"])
    state["roles"] = {"w1": "werewolf", "w2": "werewolf", "s": "seer", "v1": "villager"}
    assert set(engine._winning_team_members(state, "werewolves")) == {"w1", "w2"}
    assert set(engine._winning_team_members(state, "villagers")) == {"s", "v1"}


def test_check_game_over_true_only_once_a_winner_is_set():
    engine = WerewolfEngine()
    assert not engine.check_game_over({"winner": None}, 0, engine.DEFAULT_TOTAL_ROUNDS)
    assert engine.check_game_over({"winner": "villagers"}, 0, engine.DEFAULT_TOTAL_ROUNDS)


def test_time_up_is_idempotent_against_a_second_call():
    engine, state, _ = _fresh_game(["a", "b", "c", "d", "e"], seed=6)
    # Nobody ever submits - time_up must still resolve via the AFK path.
    state, first_points = engine.time_up(state)
    state_again, second_points = engine.time_up(state)
    assert second_points == {}
    assert state_again == state


def test_build_display_state_hides_roles_from_everyone_but_werewolves_see_their_team():
    engine, state, _ = _fresh_game([f"p{i}" for i in range(7)], seed=7)
    wolf = next(m for m, r in state["roles"].items() if r == "werewolf")
    villager = next(m for m, r in state["roles"].items() if r == "villager")

    wolf_view = engine.build_display_state(state, wolf)
    assert wolf_view["my_role"] == "werewolf"
    assert wolf_view["werewolf_team"] == [m for m, r in state["roles"].items() if r == "werewolf"]
    assert wolf_view["all_roles"] is None  # game not over - no full reveal yet

    villager_view = engine.build_display_state(state, villager)
    assert villager_view["my_role"] == "villager"
    assert villager_view["werewolf_team"] is None
    assert villager_view["all_roles"] is None


def test_build_display_state_reveals_every_role_once_the_game_ends():
    engine, state, _ = _fresh_game([f"p{i}" for i in range(7)], seed=8)
    state["winner"] = "villagers"
    villager = next(m for m, r in state["roles"].items() if r == "villager")
    view = engine.build_display_state(state, villager)
    assert view["all_roles"] == state["roles"]


def test_seer_only_sees_their_own_inspection_history():
    engine, state, _ = _fresh_game(["w", "d", "s", "v1", "v2", "v3"], seed=9)
    seer = next(m for m, r in state["roles"].items() if r == "seer")
    other_target = next(m for m in state["participant_ids"] if m != seer)
    state["seer_knowledge"] = {seer: {other_target: state["roles"][other_target]}}

    seer_view = engine.build_display_state(state, seer)
    assert seer_view["my_seer_knowledge"] == {other_target: state["roles"][other_target]}

    villager = next(m for m, r in state["roles"].items() if r == "villager" and m != seer)
    villager_view = engine.build_display_state(state, villager)
    assert villager_view["my_seer_knowledge"] is None
