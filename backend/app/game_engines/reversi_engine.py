from app.game_engines.base import IllegalMove

SIZE = 8
DIRECTIONS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0)]


def _flips_for(board: list[list[int | None]], seat: int, r: int, c: int) -> list[tuple[int, int]]:
    """Every opponent cell that placing `seat` at (r,c) would flank and
    flip, across all 8 directions - empty if (r,c) isn't a legal move."""
    if board[r][c] is not None:
        return []
    opponent = 1 - seat
    flips: list[tuple[int, int]] = []
    for dr, dc in DIRECTIONS:
        run: list[tuple[int, int]] = []
        rr, cc = r + dr, c + dc
        while 0 <= rr < SIZE and 0 <= cc < SIZE and board[rr][cc] == opponent:
            run.append((rr, cc))
            rr, cc = rr + dr, cc + dc
        if run and 0 <= rr < SIZE and 0 <= cc < SIZE and board[rr][cc] == seat:
            flips.extend(run)
    return flips


def _legal_cells(board: list[list[int | None]], seat: int) -> list[tuple[int, int]]:
    return [(r, c) for r in range(SIZE) for c in range(SIZE) if _flips_for(board, seat, r, c)]


class ReversiEngine:
    kind = "reversi"
    REPLAY_FROM_LOG = False

    def initial_state(self) -> dict:
        board: list[list[int | None]] = [[None] * SIZE for _ in range(SIZE)]
        board[3][3] = 0
        board[3][4] = 1
        board[4][3] = 1
        board[4][4] = 0
        return {"board": board, "next_seat": 0}

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
        board = [r[:] for r in state["board"]]
        flips = _flips_for(board, seat, row, col)
        if not flips:
            raise IllegalMove("That move doesn't flank any pieces.")

        board[row][col] = seat
        for fr, fc in flips:
            board[fr][fc] = seat

        # Whoever's actually able to move goes next - a player with no
        # legal move is skipped entirely rather than needing to send an
        # explicit "pass", the standard Reversi rule. If NEITHER side can
        # move, next_seat is irrelevant - check_outcome ends the game.
        opponent = 1 - seat
        if _legal_cells(board, opponent):
            next_seat = opponent
        elif _legal_cells(board, seat):
            next_seat = seat
        else:
            next_seat = opponent
        return {"board": board, "next_seat": next_seat}

    def legal_moves(self, state: dict, seat: int) -> list[dict]:
        return [{"row": r, "col": c} for r, c in _legal_cells(state["board"], seat)]

    def current_turn(self, state: dict) -> int:
        return state["next_seat"]

    def check_outcome(self, state: dict) -> tuple[str | None, str | None]:
        board = state["board"]
        if _legal_cells(board, 0) or _legal_cells(board, 1):
            return None, None
        white = sum(1 for row in board for cell in row if cell == 0)
        black = sum(1 for row in board for cell in row if cell == 1)
        if white == black:
            return "draw", "board_full"
        return ("white" if white > black else "black"), "no_legal_moves"

    def build_display_state(self, state: dict, moves: list) -> dict:
        return {"board": state["board"], "legal_moves": self.legal_moves(state, state["next_seat"])}
