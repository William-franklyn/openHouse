import copy
import json
import random
from pathlib import Path

from app.party_engines.base import IllegalAction

WORD_BANK: list[str] = json.loads((Path(__file__).parent / "codenames_words.json").read_text())

CLUE_DURATION_SECONDS = 90
GUESS_DURATION_SECONDS = 90


def _other_team(team: str) -> str:
    return "blue" if team == "red" else "red"


def _team_members(state: dict, team: str) -> list[str]:
    roster = state["teams"][team]
    return [roster["spymaster"]] + list(roster["operatives"])


def _completed_team(state: dict) -> str | None:
    for team in ("red", "blue"):
        team_words = [c for c in state["board"] if c["owner"] == team]
        if team_words and all(c["revealed"] for c in team_words):
            return team
    return None


def _viewer_role(state: dict, viewer_member_id: str | None) -> tuple[str | None, str | None]:
    if viewer_member_id is None or not state["teams"]:
        return None, None
    for team, roster in state["teams"].items():
        if viewer_member_id == roster["spymaster"]:
            return team, "spymaster"
        if viewer_member_id in roster["operatives"]:
            return team, "operative"
    return None, None


class CodenamesEngine:
    """Codenames: two teams, each with one spymaster (full board visibility)
    and N operatives (only revealed words' owners visible). Built as a
    PartyEngine by reinterpreting "round" as one atomic action - either a
    spymaster's clue or a single operative's guess/pass - mirroring how
    uno_engine.py reinterpreted it as "one player's turn". is_round_over
    fires the instant that single action is submitted; apply_action
    enforces role+team ownership internally (nobody outside the active
    team's current role may act). check_game_over ignores the generic
    round_index/total_rounds and checks state["winner"] instead, set the
    moment a team's 9/8 words are all revealed or the assassin is hit -
    DEFAULT_TOTAL_ROUNDS is purely a loop-safety cap.

    Deliberately out of scope for v1: no custom word packs, no manual
    team/spymaster picking (teams auto-split by lobby join order, first
    member of each team is spymaster), red is always the fixed starting
    team (9 words) rather than randomized, no spymaster hints/history
    panel beyond the current clue."""

    kind = "codenames"
    MIN_PARTICIPANTS = 4
    DEFAULT_TOTAL_ROUNDS = 300  # loop-safety cap only, see class docstring

    def initial_state(self, participant_ids: list[str]) -> dict:
        return {
            "phase": "lobby",
            "participant_ids": list(participant_ids),
            "teams": {},
            "board": [],
            "active_team": None,
            "current_clue": None,
            "guesses_remaining": None,
            "pending_action": None,
            "last_event": None,
            "winner": None,
            "win_reason": None,
            "next_phase": "clue",
        }

    def _deal_fresh_game(self, state: dict) -> None:
        participant_ids = state["participant_ids"]
        red_ids = participant_ids[0::2]
        blue_ids = participant_ids[1::2]
        state["teams"] = {
            "red": {"spymaster": red_ids[0], "operatives": red_ids[1:]},
            "blue": {"spymaster": blue_ids[0], "operatives": blue_ids[1:]},
        }
        words = random.sample(WORD_BANK, 25)
        owners = ["red"] * 9 + ["blue"] * 8 + ["neutral"] * 7 + ["assassin"] * 1
        random.shuffle(owners)
        state["board"] = [
            {"id": f"w{i}", "word": w, "owner": o, "revealed": False}
            for i, (w, o) in enumerate(zip(words, owners))
        ]
        state["active_team"] = "red"
        state["current_clue"] = None
        state["guesses_remaining"] = None
        state["winner"] = None
        state["win_reason"] = None
        state["last_event"] = None
        state["next_phase"] = "clue"

    def start_round(self, state: dict, round_index: int) -> tuple[dict, int]:
        state = copy.deepcopy(state)
        if state["phase"] == "lobby":
            self._deal_fresh_game(state)
        next_phase = state["next_phase"]
        state["phase"] = next_phase
        state["pending_action"] = None
        if next_phase == "clue":
            state["current_clue"] = None
            duration = CLUE_DURATION_SECONDS
        else:
            duration = GUESS_DURATION_SECONDS
        return state, duration

    def parse_action(self, data: dict) -> dict:
        kind = data.get("action")
        if kind == "clue":
            word = data.get("word")
            number = data.get("number")
            if not isinstance(word, str) or not word.strip():
                raise ValueError("Missing or invalid word.")
            if not isinstance(number, int) or isinstance(number, bool) or not (0 <= number <= 9):
                raise ValueError("Clue number must be an integer between 0 and 9.")
            return {"kind": "clue", "word": word.strip(), "number": number}
        if kind == "guess":
            word_id = data.get("word_id")
            if not isinstance(word_id, str) or not word_id:
                raise ValueError("Missing or invalid word_id.")
            return {"kind": "guess", "word_id": word_id}
        if kind == "pass":
            return {"kind": "pass"}
        raise ValueError("Missing or invalid action.")

    def apply_action(self, state: dict, member_id: str, action: dict) -> dict:
        if state["phase"] not in ("clue", "guessing"):
            raise IllegalAction("No action is open right now.")
        if state["pending_action"] is not None:
            raise IllegalAction("An action has already been submitted this round.")

        active = state["teams"][state["active_team"]]

        if state["phase"] == "clue":
            if member_id != active["spymaster"]:
                raise IllegalAction("Only the active team's spymaster can give a clue right now.")
            if action["kind"] != "clue":
                raise IllegalAction("A clue is expected right now.")
            state = copy.deepcopy(state)
            state["pending_action"] = {"kind": "clue", "word": action["word"], "number": action["number"]}
            return state

        # guessing phase
        if member_id == active["spymaster"] or member_id not in active["operatives"]:
            raise IllegalAction("Only an operative on the active team can act right now.")
        if action["kind"] == "pass":
            state = copy.deepcopy(state)
            state["pending_action"] = {"kind": "pass"}
            return state
        if action["kind"] != "guess":
            raise IllegalAction("A guess or a pass is expected right now.")
        card = next((c for c in state["board"] if c["id"] == action["word_id"]), None)
        if card is None:
            raise IllegalAction("That's not a word on the board.")
        if card["revealed"]:
            raise IllegalAction("That word has already been revealed.")
        state = copy.deepcopy(state)
        state["pending_action"] = {"kind": "guess", "word_id": action["word_id"]}
        return state

    def is_round_over(self, state: dict) -> bool:
        return state["phase"] in ("clue", "guessing") and state["pending_action"] is not None

    def time_up(self, state: dict) -> tuple[dict, dict[str, int]]:
        if state["phase"] not in ("clue", "guessing"):  # idempotency guard
            return state, {}
        state = copy.deepcopy(state)
        action = state["pending_action"]
        team = state["active_team"]

        if state["phase"] == "clue":
            if action is None:
                state["last_event"] = {"kind": "clue_timeout", "team": team}
                state["active_team"] = _other_team(team)
                state["next_phase"] = "clue"
            else:
                state["current_clue"] = {"word": action["word"], "number": action["number"]}
                state["guesses_remaining"] = action["number"] + 1
                state["last_event"] = {
                    "kind": "clue_given", "team": team, "word": action["word"], "number": action["number"],
                }
                state["next_phase"] = "guessing"
            state["pending_action"] = None
            state["phase"] = "reveal"
            return state, {}

        # guessing phase
        if action is None or action["kind"] == "pass":
            event_kind = "guess_timeout" if action is None else "guess_pass"
            state["last_event"] = {"kind": event_kind, "team": team}
            state["active_team"] = _other_team(team)
            state["next_phase"] = "clue"
            state["current_clue"] = None
            state["guesses_remaining"] = None
            state["pending_action"] = None
            state["phase"] = "reveal"
            return state, {}

        card = next(c for c in state["board"] if c["id"] == action["word_id"])
        card["revealed"] = True
        owner = card["owner"]
        state["last_event"] = {"kind": "guess_result", "team": team, "word": card["word"], "owner": owner}
        state["pending_action"] = None
        state["phase"] = "reveal"

        if owner == "assassin":
            winner = _other_team(team)
            state["winner"] = winner
            state["win_reason"] = "assassin_hit"
            return state, {m: 1 for m in _team_members(state, winner)}

        winner = _completed_team(state)
        if winner is not None:
            state["winner"] = winner
            state["win_reason"] = "all_words_found"
            return state, {m: 1 for m in _team_members(state, winner)}

        if owner == team:
            state["guesses_remaining"] -= 1
            if state["guesses_remaining"] > 0:
                state["next_phase"] = "guessing"
                return state, {}

        state["active_team"] = _other_team(team)
        state["next_phase"] = "clue"
        state["current_clue"] = None
        state["guesses_remaining"] = None
        return state, {}

    def check_game_over(self, state: dict, round_index: int, total_rounds: int) -> bool:
        return state.get("winner") is not None

    def build_display_state(self, state: dict, viewer_member_id: str | None) -> dict:
        team, role = _viewer_role(state, viewer_member_id)
        # Once the game is over the whole board is revealed to everyone,
        # same as a real Codenames table - redaction only matters mid-game.
        is_spymaster_view = role == "spymaster" or state["winner"] is not None
        board = [
            {
                "id": c["id"],
                "word": c["word"],
                "revealed": c["revealed"],
                "owner": c["owner"] if (c["revealed"] or is_spymaster_view) else None,
            }
            for c in state["board"]
        ]
        return {
            "phase": state["phase"],
            "teams": {
                t: {"spymaster": r["spymaster"], "operatives": list(r["operatives"])}
                for t, r in state["teams"].items()
            },
            "board": board,
            "active_team": state["active_team"],
            "my_team": team,
            "my_role": role,
            "current_clue": state["current_clue"],
            "guesses_remaining": state["guesses_remaining"],
            "winner": state["winner"],
            "win_reason": state["win_reason"],
            "last_event": state["last_event"] if state["phase"] == "reveal" else None,
        }

    def scoreboard(self, state: dict, cumulative_scores: dict[str, int]) -> list[dict]:
        rows = []
        for team in ("red", "blue"):
            roster = state["teams"].get(team)
            if not roster:
                continue
            for member_id in _team_members(state, team):
                rows.append(
                    {
                        "member_id": member_id,
                        "score": cumulative_scores.get(member_id, 0),
                        "round_points": None,
                        "answered": False,
                        "team": team,
                        "is_spymaster": member_id == roster["spymaster"],
                    }
                )
        return rows
