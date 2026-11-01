from app.game_engines.base import IllegalMove

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


class TicTacToeEngine:
    kind = "tictactoe"
    REPLAY_FROM_LOG = False

    def initial_state(self) -> dict:
        return {"board": [None] * 9, "next_seat": 0}

    def parse_move(self, data: dict) -> dict:
        cell = data.get("cell")
        if not isinstance(cell, int) or isinstance(cell, bool) or not (0 <= cell <= 8):
            raise ValueError("Missing or invalid cell.")
        return {"cell": cell}

    def encode_move(self, move: dict) -> dict:
        return move

    def decode_move(self, raw) -> dict:
        return raw

    def apply_move(self, state: dict, seat: int, move: dict) -> dict:
        cell = move["cell"]
        if not (0 <= cell <= 8):
            raise IllegalMove("That cell doesn't exist.")
        if state["board"][cell] is not None:
            raise IllegalMove("That cell is already taken.")
        board = list(state["board"])
        board[cell] = seat
        return {"board": board, "next_seat": 1 - seat}

    def legal_moves(self, state: dict, seat: int) -> list[dict] | None:
        return None  # trivial - "any empty cell" - no hint needed

    def current_turn(self, state: dict) -> int:
        return state["next_seat"]

    def check_outcome(self, state: dict) -> tuple[str | None, str | None]:
        board = state["board"]
        for a, b, c in WIN_LINES:
            if board[a] is not None and board[a] == board[b] == board[c]:
                return ("white" if board[a] == 0 else "black"), "three_in_a_row"
        if all(c is not None for c in board):
            return "draw", "board_full"
        return None, None

    def build_display_state(self, state: dict, moves: list) -> dict:
        return {"board": state["board"]}
