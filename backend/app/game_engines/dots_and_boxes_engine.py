from app.game_engines.base import IllegalMove

ROWS = 4  # box rows
COLS = 4  # box cols


class DotsAndBoxesEngine:
    kind = "dots_and_boxes"
    REPLAY_FROM_LOG = False

    def initial_state(self) -> dict:
        return {
            # h_edges[r][c]: the horizontal edge above box (r,c) - (ROWS+1) rows.
            "h_edges": [[False] * COLS for _ in range(ROWS + 1)],
            # v_edges[r][c]: the vertical edge left of box (r,c) - ROWS rows, (COLS+1) cols.
            "v_edges": [[False] * (COLS + 1) for _ in range(ROWS)],
            "boxes": [[None] * COLS for _ in range(ROWS)],
            "next_seat": 0,
        }

    def parse_move(self, data: dict) -> dict:
        edge_type = data.get("edge_type")
        row = data.get("row")
        col = data.get("col")
        if edge_type not in ("h", "v") or not isinstance(row, int) or not isinstance(col, int):
            raise ValueError("Missing or invalid edge.")
        return {"edge_type": edge_type, "row": row, "col": col}

    def encode_move(self, move: dict) -> dict:
        return move

    def decode_move(self, raw) -> dict:
        return raw

    def _box_complete(self, state: dict, r: int, c: int) -> bool:
        if not (0 <= r < ROWS and 0 <= c < COLS):
            return False
        return (
            state["h_edges"][r][c]
            and state["h_edges"][r + 1][c]
            and state["v_edges"][r][c]
            and state["v_edges"][r][c + 1]
        )

    def apply_move(self, state: dict, seat: int, move: dict) -> dict:
        edge_type, row, col = move["edge_type"], move["row"], move["col"]
        h_edges = [r[:] for r in state["h_edges"]]
        v_edges = [r[:] for r in state["v_edges"]]
        boxes = [r[:] for r in state["boxes"]]

        if edge_type == "h":
            if not (0 <= row <= ROWS and 0 <= col < COLS):
                raise IllegalMove("That edge doesn't exist.")
            if h_edges[row][col]:
                raise IllegalMove("That line is already drawn.")
            h_edges[row][col] = True
            adjacent_boxes = [(row - 1, col), (row, col)]
        else:
            if not (0 <= row < ROWS and 0 <= col <= COLS):
                raise IllegalMove("That edge doesn't exist.")
            if v_edges[row][col]:
                raise IllegalMove("That line is already drawn.")
            v_edges[row][col] = True
            adjacent_boxes = [(row, col - 1), (row, col)]

        next_state = {"h_edges": h_edges, "v_edges": v_edges, "boxes": boxes, "next_seat": state["next_seat"]}

        completed_any = False
        for br, bc in adjacent_boxes:
            if 0 <= br < ROWS and 0 <= bc < COLS and boxes[br][bc] is None and self._box_complete(next_state, br, bc):
                boxes[br][bc] = seat
                completed_any = True

        # Completing a box earns another turn - same rule whether it's one
        # box or two at once (an interior line can finish a box on both
        # sides simultaneously).
        next_state["next_seat"] = seat if completed_any else 1 - seat
        return next_state

    def legal_moves(self, state: dict, seat: int) -> list[dict] | None:
        return None  # trivial - any undrawn line - no hint needed

    def current_turn(self, state: dict) -> int:
        return state["next_seat"]

    def check_outcome(self, state: dict) -> tuple[str | None, str | None]:
        if any(not e for row in state["h_edges"] for e in row):
            return None, None
        if any(not e for row in state["v_edges"] for e in row):
            return None, None
        # Every line is drawn - every box has an owner. Tally and compare.
        white = sum(1 for row in state["boxes"] for b in row if b == 0)
        black = sum(1 for row in state["boxes"] for b in row if b == 1)
        if white == black:
            return "draw", "board_full"
        return ("white" if white > black else "black"), "board_full"

    def build_display_state(self, state: dict, moves: list) -> dict:
        return {"h_edges": state["h_edges"], "v_edges": state["v_edges"], "boxes": state["boxes"]}
