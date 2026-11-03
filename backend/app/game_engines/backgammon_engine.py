import random

from app.game_engines.base import IllegalMove

# Points are indexed 0-23. White (seat 0) moves from 23 toward 0 and bears
# off past 0; Black (seat 1) moves from 0 toward 23 and bears off past 23.
# points[p] > 0 = that many white checkers; points[p] < 0 = that many
# black checkers; 0 = empty. "from": -1 means entering from the bar;
# "to": 24 means bearing off - kept as plain ints (not a string/int union)
# so moves stay a uniform, JSON-safe {"from": int, "to": int} shape.
BAR = -1
OFF = 24
WHITE_HOME = range(0, 6)
BLACK_HOME = range(18, 24)


def _roll() -> list[int]:
    d1, d2 = random.randint(1, 6), random.randint(1, 6)
    return [d1, d1, d1, d1] if d1 == d2 else [d1, d2]


class BackgammonEngine:
    kind = "backgammon"
    REPLAY_FROM_LOG = False

    def initial_state(self) -> dict:
        points = [0] * 24
        points[23], points[12], points[7], points[5] = 2, 5, 3, 5
        points[0], points[11], points[16], points[18] = -2, -5, -3, -5
        dice = _roll()
        return {
            "points": points,
            "bar": [0, 0],
            "borne_off": [0, 0],
            "dice": dice,
            "remaining_dice": list(dice),
            "next_seat": 0,
        }

    def parse_move(self, data: dict) -> dict:
        frm, to = data.get("from"), data.get("to")
        if not isinstance(frm, int) or not isinstance(to, int):
            raise ValueError("Missing or invalid from/to.")
        return {"from": frm, "to": to}

    def encode_move(self, move: dict) -> dict:
        return move

    def decode_move(self, raw) -> dict:
        return raw

    # ---- internal helpers ----

    def _blocked(self, points: list[int], seat: int, to: int) -> bool:
        return points[to] <= -2 if seat == 0 else points[to] >= 2

    def _is_blot(self, points: list[int], seat: int, to: int) -> bool:
        return points[to] == -1 if seat == 0 else points[to] == 1

    def _land(self, points: list[int], bar: list[int], seat: int, to: int) -> None:
        if self._is_blot(points, seat, to):
            bar[1 - seat] += 1
            points[to] = 0
        points[to] += 1 if seat == 0 else -1

    def _entry_die(self, seat: int, to: int) -> int | None:
        if seat == 0:
            return 24 - to if 18 <= to <= 23 else None
        return to + 1 if 0 <= to <= 5 else None

    def _all_home(self, points: list[int], bar: list[int], seat: int) -> bool:
        if bar[seat] > 0:
            return False
        if seat == 0:
            return all(points[p] <= 0 for p in range(6, 24))
        return all(points[p] >= 0 for p in range(0, 18))

    def _furthest_home_point(self, points: list[int], seat: int) -> int | None:
        if seat == 0:
            occupied = [p for p in WHITE_HOME if points[p] > 0]
            return max(occupied) if occupied else None
        occupied = [p for p in BLACK_HOME if points[p] < 0]
        return min(occupied) if occupied else None

    def _bear_off_die(self, points: list[int], seat: int, frm: int, remaining: list[int]) -> int | None:
        exact = frm + 1 if seat == 0 else 24 - frm
        if exact in remaining:
            return exact
        if self._furthest_home_point(points, seat) == frm:
            larger = [d for d in remaining if d > exact]
            if larger:
                return min(larger)
        return None

    def _compute_legal_moves(self, points: list[int], bar: list[int], seat: int, remaining: list[int]) -> list[dict]:
        moves: list[dict] = []
        dice_values = sorted(set(remaining))

        if bar[seat] > 0:
            for die in dice_values:
                to = 24 - die if seat == 0 else die - 1
                if not self._blocked(points, seat, to):
                    moves.append({"from": BAR, "to": to})
            return moves

        own_points = [p for p in range(24) if (points[p] > 0 if seat == 0 else points[p] < 0)]
        can_bear_off = self._all_home(points, bar, seat)
        for frm in own_points:
            for die in dice_values:
                to = frm - die if seat == 0 else frm + die
                if 0 <= to <= 23:
                    if not self._blocked(points, seat, to):
                        moves.append({"from": frm, "to": to})
                elif can_bear_off:
                    if self._bear_off_die(points, seat, frm, remaining) == die:
                        moves.append({"from": frm, "to": OFF})
        return moves

    # ---- GameEngine interface ----

    def apply_move(self, state: dict, seat: int, move: dict) -> dict:
        frm, to = move["from"], move["to"]
        points = list(state["points"])
        bar = list(state["bar"])
        borne_off = list(state["borne_off"])
        remaining = list(state["remaining_dice"])

        if bar[seat] > 0 and frm != BAR:
            raise IllegalMove("You must enter your checker(s) from the bar first.")

        if frm == BAR:
            if bar[seat] == 0:
                raise IllegalMove("You have no checkers on the bar.")
            die = self._entry_die(seat, to)
            if die is None or die not in remaining:
                raise IllegalMove("That's not a legal entry for your dice.")
            if self._blocked(points, seat, to):
                raise IllegalMove("That point is blocked.")
            bar[seat] -= 1
            self._land(points, bar, seat, to)
            remaining.remove(die)
        elif to == OFF:
            if not (0 <= frm <= 23) or (points[frm] <= 0 if seat == 0 else points[frm] >= 0):
                raise IllegalMove("You don't have a checker there.")
            if not self._all_home(points, bar, seat):
                raise IllegalMove("All your checkers must be home before bearing off.")
            die = self._bear_off_die(points, seat, frm, remaining)
            if die is None:
                raise IllegalMove("That's not a legal bear-off for your dice.")
            points[frm] += -1 if seat == 0 else 1
            borne_off[seat] += 1
            remaining.remove(die)
        else:
            if not (0 <= frm <= 23) or (points[frm] <= 0 if seat == 0 else points[frm] >= 0):
                raise IllegalMove("You don't have a checker there.")
            if not (0 <= to <= 23):
                raise IllegalMove("That's off the board.")
            die = (frm - to) if seat == 0 else (to - frm)
            if die <= 0 or die not in remaining:
                raise IllegalMove("That's not a legal move for your dice.")
            if self._blocked(points, seat, to):
                raise IllegalMove("That point is blocked.")
            points[frm] += -1 if seat == 0 else 1
            self._land(points, bar, seat, to)
            remaining.remove(die)

        dice = state["dice"]
        next_seat = seat
        if not remaining or not self._compute_legal_moves(points, bar, seat, remaining):
            next_seat = 1 - seat
            dice = _roll()
            remaining = list(dice)
            # A fresh roll can leave the other player with no legal move
            # at all (e.g. blocked by a prime) - real backgammon forfeits
            # that whole turn outright, so keep flipping/re-rolling rather
            # than stranding the game on a turn nobody can act on. Capped
            # defensively; a real closed-out position resolves in a
            # handful of rolls, never anywhere near this bound.
            guard = 0
            while not self._compute_legal_moves(points, bar, next_seat, remaining) and guard < 50:
                next_seat = 1 - next_seat
                dice = _roll()
                remaining = list(dice)
                guard += 1

        return {
            "points": points,
            "bar": bar,
            "borne_off": borne_off,
            "dice": dice,
            "remaining_dice": remaining,
            "next_seat": next_seat,
        }

    def legal_moves(self, state: dict, seat: int) -> list[dict]:
        return self._compute_legal_moves(state["points"], state["bar"], seat, state["remaining_dice"])

    def current_turn(self, state: dict) -> int:
        return state["next_seat"]

    def check_outcome(self, state: dict) -> tuple[str | None, str | None]:
        if state["borne_off"][0] == 15:
            return "white", "all_checkers_home"
        if state["borne_off"][1] == 15:
            return "black", "all_checkers_home"
        return None, None

    def build_display_state(self, state: dict, moves: list) -> dict:
        return {
            "points": state["points"],
            "bar": state["bar"],
            "borne_off": state["borne_off"],
            "dice": state["dice"],
            "remaining_dice": state["remaining_dice"],
            "legal_moves": self.legal_moves(state, state["next_seat"]),
        }
