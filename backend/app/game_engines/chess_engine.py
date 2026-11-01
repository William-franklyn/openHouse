import chess

from app.game_engines.base import IllegalMove


def _was_last_move_a_capture(board_before_last: chess.Board, last_uci: str) -> bool:
    """Whether the most recent move captured a piece - used purely for the
    frontend's sound effect, so it's derived fresh rather than stored
    (same "replay the log" philosophy as the board itself)."""
    return board_before_last.is_capture(chess.Move.from_uci(last_uci))


class ChessEngine:
    kind = "chess"
    REPLAY_FROM_LOG = True

    def initial_state(self) -> chess.Board:
        return chess.Board()

    def parse_move(self, data: dict) -> dict:
        from_sq, to_sq, promotion = data.get("from"), data.get("to"), data.get("promotion")
        if not from_sq or not to_sq:
            raise ValueError("Missing from/to.")
        return {"uci": f"{from_sq}{to_sq}{promotion or ''}"}

    def encode_move(self, move: dict) -> str:
        return move["uci"]

    def decode_move(self, raw) -> dict:
        return {"uci": raw}

    def apply_move(self, board: chess.Board, seat: int, move: dict) -> chess.Board:
        try:
            chess_move = chess.Move.from_uci(move["uci"])
        except ValueError:
            raise IllegalMove("That's not a legal move.")
        if chess_move not in board.legal_moves:
            raise IllegalMove("That's not a legal move.")
        board.push(chess_move)
        return board

    def legal_moves(self, board: chess.Board, seat: int) -> list[dict]:
        return [{"uci": m.uci()} for m in board.legal_moves]

    def current_turn(self, board: chess.Board) -> int:
        return 0 if board.turn == chess.WHITE else 1

    def check_outcome(self, board: chess.Board) -> tuple[str | None, str | None]:
        if not board.is_game_over():
            return None, None
        outcome = board.outcome()
        if outcome is None:
            return None, None
        result = "draw" if outcome.winner is None else ("white" if outcome.winner == chess.WHITE else "black")
        return result, outcome.termination.name.lower()

    def build_display_state(self, board: chess.Board, moves: list) -> dict:
        if moves:
            board_before_last = chess.Board()
            for uci in moves[:-1]:
                board_before_last.push_uci(uci)
            last_move_was_capture = _was_last_move_a_capture(board_before_last, moves[-1])
        else:
            last_move_was_capture = False
        return {
            "board_fen": board.board_fen(),
            "legal_moves": [m.uci() for m in board.legal_moves],
            "in_check": board.is_check(),
            "last_move_was_capture": last_move_was_capture,
        }
