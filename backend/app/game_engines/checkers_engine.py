from app.game_engines.base import IllegalMove

SIZE = 8
# Piece codes: "w"/"b" = man, "wk"/"bk" = king. None = empty.
SEAT_COLOR = {0: "w", 1: "b"}


def _seat_of_piece(piece: str | None) -> int | None:
    if piece is None:
        return None
    return 0 if piece[0] == "w" else 1


def _is_king(piece: str | None) -> bool:
    return piece is not None and piece.endswith("k")


def _forward_dirs(seat: int, piece: str) -> list[int]:
    """Row deltas a piece may move in. Kings go either way; men only
    toward the opponent's back row (standard rule - no backward captures
    or moves for a man)."""
    if _is_king(piece):
        return [-1, 1]
    return [1] if seat == 0 else [-1]


def _simple_moves_from(board, seat: int, r: int, c: int) -> list[tuple[int, int]]:
    piece = board[r][c]
    moves = []
    for dr in _forward_dirs(seat, piece):
        for dc in (-1, 1):
            rr, cc = r + dr, c + dc
            if 0 <= rr < SIZE and 0 <= cc < SIZE and board[rr][cc] is None:
                moves.append((rr, cc))
    return moves


def _captures_from(board, seat: int, r: int, c: int) -> list[tuple[int, int, int, int]]:
    """(to_r, to_c, captured_r, captured_c) for every jump available to
    the piece at (r,c) right now."""
    piece = board[r][c]
    opponent = 1 - seat
    jumps = []
    for dr in _forward_dirs(seat, piece):
        for dc in (-1, 1):
            mid_r, mid_c = r + dr, c + dc
            land_r, land_c = r + 2 * dr, c + 2 * dc
            if not (0 <= land_r < SIZE and 0 <= land_c < SIZE):
                continue
            mid_piece = board[mid_r][mid_c]
            if mid_piece is not None and _seat_of_piece(mid_piece) == opponent and board[land_r][land_c] is None:
                jumps.append((land_r, land_c, mid_r, mid_c))
    return jumps


def _all_captures(board, seat: int) -> list[tuple[int, int, int, int, int, int]]:
    out = []
    for r in range(SIZE):
        for c in range(SIZE):
            if _seat_of_piece(board[r][c]) == seat:
                for land_r, land_c, cap_r, cap_c in _captures_from(board, seat, r, c):
                    out.append((r, c, land_r, land_c, cap_r, cap_c))
    return out


def _all_simple_moves(board, seat: int) -> list[tuple[int, int, int, int]]:
    out = []
    for r in range(SIZE):
        for c in range(SIZE):
            if _seat_of_piece(board[r][c]) == seat:
                for land_r, land_c in _simple_moves_from(board, seat, r, c):
                    out.append((r, c, land_r, land_c))
    return out


def _has_any_move(board, seat: int) -> bool:
    return bool(_all_captures(board, seat)) or bool(_all_simple_moves(board, seat))


class CheckersEngine:
    kind = "checkers"
    REPLAY_FROM_LOG = False

    def initial_state(self) -> dict:
        board: list[list[str | None]] = [[None] * SIZE for _ in range(SIZE)]
        for r in range(3):
            for c in range(SIZE):
                if (r + c) % 2 == 1:
                    board[r][c] = "w"
        for r in range(5, SIZE):
            for c in range(SIZE):
                if (r + c) % 2 == 1:
                    board[r][c] = "b"
        return {"board": board, "next_seat": 0, "must_continue_from": None}

    def parse_move(self, data: dict) -> dict:
        frm, to = data.get("from"), data.get("to")
        if (
            not isinstance(frm, list) or not isinstance(to, list)
            or len(frm) != 2 or len(to) != 2
            or not all(isinstance(x, int) for x in (*frm, *to))
        ):
            raise ValueError("Missing or invalid from/to.")
        return {"from": [frm[0], frm[1]], "to": [to[0], to[1]]}

    def encode_move(self, move: dict) -> dict:
        return move

    def decode_move(self, raw) -> dict:
        return raw

    def apply_move(self, state: dict, seat: int, move: dict) -> dict:
        fr, fc = move["from"]
        tr, tc = move["to"]
        board = [row[:] for row in state["board"]]

        if not (0 <= fr < SIZE and 0 <= fc < SIZE and 0 <= tr < SIZE and 0 <= tc < SIZE):
            raise IllegalMove("That's off the board.")
        piece = board[fr][fc]
        if piece is None or _seat_of_piece(piece) != seat:
            raise IllegalMove("You don't have a piece there.")

        must_continue_from = state.get("must_continue_from")
        if must_continue_from is not None and [fr, fc] != list(must_continue_from):
            raise IllegalMove("You must continue jumping with the same piece.")

        mandatory = must_continue_from is not None or bool(_all_captures(board, seat))

        captures_here = _captures_from(board, seat, fr, fc)
        capture_match = next(((lr, lc, cr, cc) for lr, lc, cr, cc in captures_here if (lr, lc) == (tr, tc)), None)

        if capture_match is not None:
            land_r, land_c, cap_r, cap_c = capture_match
            board[cap_r][cap_c] = None
            board[tr][tc] = piece
            board[fr][fc] = None
            kinged = self._maybe_king(board, seat, tr, tc)
            further = [] if kinged else _captures_from(board, seat, tr, tc)
            if further:
                return {"board": board, "next_seat": seat, "must_continue_from": [tr, tc]}
            return {"board": board, "next_seat": 1 - seat, "must_continue_from": None}

        if mandatory:
            raise IllegalMove("A capture is available - you must take it.")

        if (tr, tc) not in _simple_moves_from(board, seat, fr, fc):
            raise IllegalMove("That's not a legal move.")

        board[tr][tc] = piece
        board[fr][fc] = None
        self._maybe_king(board, seat, tr, tc)
        return {"board": board, "next_seat": 1 - seat, "must_continue_from": None}

    def _maybe_king(self, board, seat: int, r: int, c: int) -> bool:
        back_row = SIZE - 1 if seat == 0 else 0
        if r == back_row and not _is_king(board[r][c]):
            board[r][c] = SEAT_COLOR[seat] + "k"
            return True
        return False

    def legal_moves(self, state: dict, seat: int) -> list[dict]:
        board = state["board"]
        must_continue_from = state.get("must_continue_from")
        if must_continue_from is not None:
            r, c = must_continue_from
            return [{"from": [r, c], "to": [lr, lc]} for lr, lc, _, _ in _captures_from(board, seat, r, c)]

        captures = _all_captures(board, seat)
        if captures:
            return [{"from": [fr, fc], "to": [lr, lc]} for fr, fc, lr, lc, _, _ in captures]
        return [{"from": [fr, fc], "to": [tr, tc]} for fr, fc, tr, tc in _all_simple_moves(board, seat)]

    def current_turn(self, state: dict) -> int:
        return state["next_seat"]

    def check_outcome(self, state: dict) -> tuple[str | None, str | None]:
        board = state["board"]
        turn = state["next_seat"]
        if not any(_seat_of_piece(cell) == turn for row in board for cell in row):
            return self._other(turn), "no_pieces_left"
        if not _has_any_move(board, turn):
            return self._other(turn), "no_legal_moves"
        return None, None

    def _other(self, seat: int) -> str:
        return "white" if seat == 1 else "black"

    def build_display_state(self, state: dict, moves: list) -> dict:
        return {
            "board": state["board"],
            "must_continue_from": state.get("must_continue_from"),
            "legal_moves": self.legal_moves(state, state["next_seat"]),
        }
