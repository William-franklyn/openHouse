from app.game_engines.base import IllegalMove

ROWS, COLS = 6, 7


def _winner(board: list[list[int | None]]) -> int | None:
    for r in range(ROWS):
        for c in range(COLS):
            v = board[r][c]
            if v is None:
                continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + dr * i, c + dc * i) for i in range(4)]
                if all(0 <= rr < ROWS and 0 <= cc < COLS for rr, cc in cells):
                    if all(board[rr][cc] == v for rr, cc in cells):
                        return v
    return None


class Connect4Engine:
    kind = "connect4"
    REPLAY_FROM_LOG = False

    def initial_state(self) -> dict:
        return {"board": [[None] * COLS for _ in range(ROWS)], "next_seat": 0}

    def parse_move(self, data: dict) -> dict:
        column = data.get("column")
        if not isinstance(column, int) or isinstance(column, bool) or not (0 <= column < COLS):
            raise ValueError("Missing or invalid column.")
        return {"column": column}

    def encode_move(self, move: dict) -> dict:
        return move

    def decode_move(self, raw) -> dict:
        return raw

    def apply_move(self, state: dict, seat: int, move: dict) -> dict:
        column = move["column"]
        if not (0 <= column < COLS):
            raise IllegalMove("That column doesn't exist.")
        board = [row[:] for row in state["board"]]
        row = next((r for r in range(ROWS - 1, -1, -1) if board[r][column] is None), None)
        if row is None:
            raise IllegalMove("That column is full.")
        board[row][column] = seat
        return {"board": board, "next_seat": 1 - seat}

    def legal_moves(self, state: dict, seat: int) -> list[dict]:
        return [{"column": c} for c in range(COLS) if state["board"][0][c] is None]

    def current_turn(self, state: dict) -> int:
        return state["next_seat"]

    def check_outcome(self, state: dict) -> tuple[str | None, str | None]:
        board = state["board"]
        winner = _winner(board)
        if winner is not None:
            return ("white" if winner == 0 else "black"), "four_in_a_row"
        if all(board[0][c] is not None for c in range(COLS)):
            return "draw", "board_full"
        return None, None

    def build_display_state(self, state: dict, moves: list) -> dict:
        return {"board": state["board"], "legal_moves": self.legal_moves(state, state["next_seat"])}
