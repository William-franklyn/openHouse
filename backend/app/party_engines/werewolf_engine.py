import copy
import random

from app.party_engines.base import IllegalAction

NIGHT_DURATION_SECONDS = 45
DAY_DURATION_SECONDS = 90
NIGHT_ROLES = ("werewolf", "doctor", "seer")


def _tally(votes: dict[str, str]) -> str | None:
    """Majority target, or None on an empty ballot or an exact tie - no
    elimination on a tie, same simplification for both the werewolves'
    night vote and the day lynch vote (verified via a standalone script
    before being written here)."""
    counts: dict[str, int] = {}
    for target in votes.values():
        if target == "abstain":
            continue
        counts[target] = counts.get(target, 0) + 1
    if not counts:
        return None
    max_count = max(counts.values())
    leaders = [t for t, c in counts.items() if c == max_count]
    return leaders[0] if len(leaders) == 1 else None


class WerewolfEngine:
    """Werewolf/Mafia: N players, secretly assigned roles (werewolf,
    doctor, seer, villager), alternating night (hidden role actions) and
    day (open lynch vote) phases until one side wins. Built as a
    PartyEngine with each night or day treated as ONE round - a
    simultaneous-but-role-scoped action set (only living werewolves +
    the living doctor + the living seer owe a night submission; everyone
    living owes a day vote), mirroring how hearts_engine.py's "passing"
    phase treats "everyone" as the required actor set while this treats
    a smaller, role-filtered subset as required. is_round_over fires once
    every REQUIRED actor (not literally everyone) has submitted.

    Hidden information is asymmetric in a new way beyond "my own hand":
    werewolves additionally see each other's identities (their team),
    and the seer accumulates private per-target inspection results
    across the whole game, visible only to them - see build_display_state.
    Villagers' night action is simply "none" - they wait.

    Deliberately out of scope for v1: no revote on a tied lynch, no
    "doctor can't save the same target twice in a row" restriction, no
    additional roles (hunter/cupid/etc), no spectating for eliminated
    players beyond what they already knew."""

    kind = "werewolf"
    MIN_PARTICIPANTS = 5
    MAX_PARTICIPANTS = 15
    DEFAULT_TOTAL_ROUNDS = 200  # loop-safety cap only, see class docstring

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "roles": {},
            "alive": {},
            "night_number": 0,
            "night_submissions": {},
            "day_votes": {},
            "seer_knowledge": {},
            "last_event": None,
            "winner": None,
            "next_phase": "night_actions",
        }

    def _assign_roles(self, state: dict) -> None:
        participant_ids = state["participant_ids"]
        n = len(participant_ids)
        num_wolves = max(1, n // 4)
        num_doctor = 1 if n >= 6 else 0
        num_seer = 1 if n >= 5 else 0
        num_villagers = n - num_wolves - num_doctor - num_seer
        pool = ["werewolf"] * num_wolves + ["doctor"] * num_doctor + ["seer"] * num_seer + ["villager"] * num_villagers
        random.shuffle(pool)
        state["roles"] = dict(zip(participant_ids, pool))
        state["alive"] = {m: True for m in participant_ids}
        state["seer_knowledge"] = {}
        state["night_submissions"] = {}
        state["day_votes"] = {}
        state["last_event"] = None
        state["winner"] = None

    def _required_night_actors(self, state: dict) -> set[str]:
        return {m for m, r in state["roles"].items() if r in NIGHT_ROLES and state["alive"].get(m, False)}

    def _check_winner(self, state: dict) -> str | None:
        living_wolves = [m for m, r in state["roles"].items() if r == "werewolf" and state["alive"].get(m, False)]
        living_others = [m for m, r in state["roles"].items() if r != "werewolf" and state["alive"].get(m, False)]
        if not living_wolves:
            return "villagers"
        if len(living_wolves) >= len(living_others):
            return "werewolves"
        return None

    def _winning_team_members(self, state: dict, winner: str) -> list[str]:
        if winner == "werewolves":
            return [m for m, r in state["roles"].items() if r == "werewolf"]
        return [m for m, r in state["roles"].items() if r != "werewolf"]

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        if state["phase"] == "lobby":
            self._assign_roles(state)
            state["night_number"] = 1
            state["phase"] = "night_actions"
            return state, NIGHT_DURATION_SECONDS

        next_phase = state["next_phase"]
        state["phase"] = next_phase
        if next_phase == "night_actions":
            state["night_number"] += 1
            state["night_submissions"] = {}
            return state, NIGHT_DURATION_SECONDS
        state["day_votes"] = {}
        return state, DAY_DURATION_SECONDS

    def parse_action(self, data: dict) -> dict:
        kind = data.get("action")
        if kind in ("wolf_vote", "doctor_save", "seer_inspect", "day_vote"):
            target_id = data.get("target_id")
            if not isinstance(target_id, str) or not target_id:
                raise ValueError("Missing or invalid target_id.")
            return {"kind": kind, "target_id": target_id}
        raise ValueError("Missing or invalid action.")

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] not in ("night_actions", "day_vote"):
            raise IllegalAction("No action is open right now.")
        if not state["alive"].get(member_id, False):
            raise IllegalAction("Eliminated players can't act.")

        if state["phase"] == "night_actions":
            role = state["roles"].get(member_id)
            if role not in NIGHT_ROLES:
                raise IllegalAction("You have no night action.")
            if member_id in state["night_submissions"]:
                raise IllegalAction("You've already acted tonight.")
            expected_kind = {"werewolf": "wolf_vote", "doctor": "doctor_save", "seer": "seer_inspect"}[role]
            if action["kind"] != expected_kind:
                raise IllegalAction("That's not your night action.")
            target_id = action["target_id"]
            if target_id not in state["participant_ids"] or not state["alive"].get(target_id, False):
                raise IllegalAction("Choose a living player.")
            state = copy.deepcopy(state)
            state["night_submissions"][member_id] = {"kind": expected_kind, "target_id": target_id}
            return state

        # day_vote
        if member_id in state["day_votes"]:
            raise IllegalAction("You've already voted today.")
        if action["kind"] != "day_vote":
            raise IllegalAction("A vote is expected right now.")
        target_id = action["target_id"]
        if target_id != "abstain" and (
            target_id not in state["participant_ids"] or not state["alive"].get(target_id, False)
        ):
            raise IllegalAction("Choose a living player or abstain.")
        state = copy.deepcopy(state)
        state["day_votes"][member_id] = target_id
        return state

    def is_round_over(self, state: dict) -> bool:
        if state["phase"] == "night_actions":
            return self._required_night_actors(state) <= set(state["night_submissions"].keys())
        if state["phase"] == "day_vote":
            living = {m for m in state["participant_ids"] if state["alive"].get(m, False)}
            return living <= set(state["day_votes"].keys())
        return False

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] not in ("night_actions", "day_vote"):  # idempotency guard
            return state, {}
        state = copy.deepcopy(state)

        if state["phase"] == "night_actions":
            wolf_votes = {
                m: a["target_id"] for m, a in state["night_submissions"].items() if a["kind"] == "wolf_vote"
            }
            doctor_save = next(
                (a["target_id"] for a in state["night_submissions"].values() if a["kind"] == "doctor_save"), None
            )
            seer_entry = next(
                ((m, a["target_id"]) for m, a in state["night_submissions"].items() if a["kind"] == "seer_inspect"),
                None,
            )

            victim = _tally(wolf_votes)
            died = victim if (victim is not None and victim != doctor_save) else None
            if died is not None:
                state["alive"][died] = False

            if seer_entry is not None:
                seer_member, target_id = seer_entry
                state["seer_knowledge"].setdefault(seer_member, {})[target_id] = state["roles"][target_id]

            state["last_event"] = {"kind": "night_result", "night_number": state["night_number"], "died_member_id": died}
            state["night_submissions"] = {}
            state["phase"] = "reveal"

            winner = self._check_winner(state)
            if winner is not None:
                state["winner"] = winner
                return state, {m: 1 for m in self._winning_team_members(state, winner)}
            state["next_phase"] = "day_vote"
            return state, {}

        # day_vote
        votes_for_event = dict(state["day_votes"])
        lynched = _tally(state["day_votes"])
        if lynched is not None:
            state["alive"][lynched] = False
        state["last_event"] = {"kind": "day_result", "lynched_member_id": lynched, "votes": votes_for_event}
        state["day_votes"] = {}
        state["phase"] = "reveal"

        winner = self._check_winner(state)
        if winner is not None:
            state["winner"] = winner
            return state, {m: 1 for m in self._winning_team_members(state, winner)}
        state["next_phase"] = "night_actions"
        return state, {}

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return state.get("winner") is not None

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        my_role = state["roles"].get(viewer_member_id) if viewer_member_id else None
        revealed_all = state["winner"] is not None

        werewolf_team = None
        if my_role == "werewolf":
            werewolf_team = [m for m, r in state["roles"].items() if r == "werewolf"]

        my_seer_knowledge = None
        if my_role == "seer" and viewer_member_id:
            my_seer_knowledge = state["seer_knowledge"].get(viewer_member_id, {})

        all_roles = dict(state["roles"]) if revealed_all else None

        need_action = False
        if viewer_member_id and state["alive"].get(viewer_member_id, False):
            if state["phase"] == "night_actions":
                need_action = (
                    viewer_member_id in self._required_night_actors(state)
                    and viewer_member_id not in state["night_submissions"]
                )
            elif state["phase"] == "day_vote":
                need_action = viewer_member_id not in state["day_votes"]

        return {
            "phase": state["phase"],
            "night_number": state["night_number"],
            "my_role": my_role,
            "alive": dict(state["alive"]),
            "werewolf_team": werewolf_team,
            "my_seer_knowledge": my_seer_knowledge,
            "all_roles": all_roles,
            "need_action": need_action,
            "winner": state["winner"],
            "last_event": state["last_event"] if state["phase"] == "reveal" else None,
        }

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        rows = [
            {
                "member_id": m,
                "score": cumulative_scores.get(m, 0),
                "round_points": None,
                "answered": False,
            }
            for m in state["participant_ids"]
        ]
        rows.sort(key=lambda r: -r["score"])
        return rows
