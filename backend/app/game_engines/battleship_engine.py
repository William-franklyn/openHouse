import random

from app.game_engines.base import IllegalMove

SIZE = 10
SHIP_SIZES = [5, 4, 3, 3, 2]  # Carrier, Battleship, Cruiser, Submarine, Destroyer

# Per-cell values sent to the frontend. "ship"/"empty" only ever appear on
# a viewer's OWN board (the one thing battleship actually hides) - the
# opponent's board only ever shows "hit"/"miss"/"unknown", regardless of
# what's actually underneath an unshot cell.
SHIP, HIT, MISS, EMPTY, UNKNOWN = "ship", "hit", "miss", "empty", "unknown"


def _place_fleet() -> list[list[int | None]]:
    """Ships are placed once, automatically, when the game starts (there's
    no manual placement phase - see the engine's module docstring below)
    - retries on overlap, which converges fast on a 10x10 board with only
    17 of 100 cells occupied."""
    while True:
        grid: list[list[int | None]] = [[None] * SIZE for _ in range(SIZE)]
        ok = True
        for ship_id, length in enumerate(SHIP_SIZES):
            placed = False
            for _attempt in range(200):
                horizontal = random.random() < 0.5
                if horizontal:
                    r = random.randint(0, SIZE - 1)
                    c = random.randint(0, SIZE - length)
                    cells = [(r, c + i) for i in range(length)]
                else:
                    r = random.randint(0, SIZE - length)
                    c = random.randint(0, SIZE - 1)
                    cells = [(r + i, c) for i in range(length)]
                if all(grid[rr][cc] is None for rr, cc in cells):
                    for rr, cc in cells:
                        grid[rr][cc] = ship_id
                    placed = True
                    break
            if not placed:
                ok = False
                break
        if ok:
            return grid


class BattleshipEngine:
    """The first (and so far only) kind with hidden per-player information -
    see GameEngine.redact_for_viewer in base.py for the opt-in hook this
    relies on. Ships are auto-placed randomly for both seats at game
    start rather than offering a manual placement UI: real Battleship's
    simultaneous, non-alternating placement phase doesn't fit the
    strictly-alternating turn model every other engine here assumes, and
    building a second turn-order mode just for one game's setup step
    isn't worth it next to what's actually interesting about this game -
    the hidden state itself."""

    kind = "battleship"
    REPLAY_FROM_LOG = False

    def initial_state(self) -> dict:
        return {
            "grids": [_place_fleet(), _place_fleet()],
            "ship_hits": [[0] * len(SHIP_SIZES), [0] * len(SHIP_SIZES)],
            "shots": [[[None] * SIZE for _ in range(SIZE)], [[None] * SIZE for _ in range(SIZE)]],
            "next_seat": 0,
        }

    def parse_move(self, data: dict) -> dict:
        row, col = data.get("row"), data.get("col")
        if not isinstance(row, int) or not isinstance(col, int) or not (0 <= row < SIZE and 0 <= col < SIZE):
            raise ValueError("Missing or invalid cell.")
        return {"row": row, "col": col}

    def encode_move(self, move: dict) -> dict:
        return move

    def decode_move(self, raw) -> dict:
        return raw

    def apply_move(self, state: dict, seat: int, move: dict) -> dict:
        row, col = move["row"], move["col"]
        opponent = 1 - seat
        if state["shots"][seat][row][col] is not None:
            raise IllegalMove("You already fired at that cell.")

        shots = [[r[:] for r in state["shots"][0]], [r[:] for r in state["shots"][1]]]
        ship_hits = [list(state["ship_hits"][0]), list(state["ship_hits"][1])]

        ship_id = state["grids"][opponent][row][col]
        if ship_id is not None:
            shots[seat][row][col] = HIT
            ship_hits[opponent][ship_id] += 1
        else:
            shots[seat][row][col] = MISS

        return {
            "grids": state["grids"],  # ships never move once placed - safe to share, never mutated
            "ship_hits": ship_hits,
            "shots": shots,
            "next_seat": opponent,
        }

    def legal_moves(self, state: dict, seat: int) -> list[dict]:
        shots = state["shots"][seat]
        return [{"row": r, "col": c} for r in range(SIZE) for c in range(SIZE) if shots[r][c] is None]

    def current_turn(self, state: dict) -> int:
        return state["next_seat"]

    def check_outcome(self, state: dict) -> tuple[str | None, str | None]:
        for seat in (0, 1):
            if all(hits == size for hits, size in zip(state["ship_hits"][seat], SHIP_SIZES)):
                return ("black" if seat == 0 else "white"), "fleet_sunk"
        return None, None

    def build_display_state(self, state: dict, moves: list) -> dict:
        # The genuinely full, unredacted view - never sent as-is, always
        # passed through redact_for_viewer first. Kept as the return value
        # of this method (rather than redacting here directly) so the
        # shape matches every other engine's build_display_state contract.
        return {
            "grids": state["grids"],
            "shots": state["shots"],
            "ship_hits": state["ship_hits"],
            "ship_sizes": SHIP_SIZES,
        }

    def _own_board_view(self, grid: list[list[int | None]], incoming_shots: list[list[str | None]]) -> list[list[str]]:
        return [
            [
                HIT if incoming_shots[r][c] == HIT else MISS if incoming_shots[r][c] == MISS else (SHIP if grid[r][c] is not None else EMPTY)
                for c in range(SIZE)
            ]
            for r in range(SIZE)
        ]

    def _revealed_only_view(self, incoming_shots: list[list[str | None]]) -> list[list[str]]:
        return [[incoming_shots[r][c] or UNKNOWN for c in range(SIZE)] for r in range(SIZE)]

    def redact_for_viewer(self, display: dict, viewer_seat: int | None) -> dict:
        grids = display["grids"]
        shots = display["shots"]

        def grid_for(owner_seat: int) -> list[list[str]]:
            # Shots fired AT owner_seat's board are the OTHER seat's shots,
            # not owner_seat's own (those are aimed at the opposite board).
            incoming_shots = shots[1 - owner_seat]
            if owner_seat == viewer_seat:
                return self._own_board_view(grids[owner_seat], incoming_shots)
            return self._revealed_only_view(incoming_shots)

        return {
            "white_grid": grid_for(0),
            "black_grid": grid_for(1),
            "ship_hits": display["ship_hits"],
            "ship_sizes": display["ship_sizes"],
            "my_seat": viewer_seat,
        }
