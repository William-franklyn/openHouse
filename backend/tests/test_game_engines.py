"""Pure unit tests directly against the game engines - no DB, no WebSocket,
no fakeredis. Fast, isolated coverage of the actual board logic, separate
from the realtime-plumbing tests in test_tictactoe.py/test_connect4.py."""

import pytest

from app.game_engines.base import IllegalMove
from app.game_engines.connect4_engine import COLS, ROWS, Connect4Engine
from app.game_engines.backgammon_engine import BackgammonEngine, BAR, OFF
from app.game_engines.backgammon_engine import _roll as bg_roll
from app.game_engines.checkers_engine import CheckersEngine
from app.game_engines.dots_and_boxes_engine import ROWS as DAB_ROWS, COLS as DAB_COLS, DotsAndBoxesEngine
from app.game_engines.reversi_engine import ReversiEngine
from app.game_engines.tictactoe_engine import WIN_LINES, TicTacToeEngine


# ---- Tic-Tac-Toe: all 8 win lines ----

@pytest.mark.parametrize("line", WIN_LINES)
def test_tictactoe_every_win_line_is_detected(line):
    engine = TicTacToeEngine()
    state = engine.initial_state()
    a, b, c = line
    other_cells = [i for i in range(9) if i not in line]

    # X takes the line, O takes two unrelated cells in between - X should
    # not win until the 3rd (last) cell of the line is placed.
    state = engine.apply_move(state, 0, {"cell": a})
    assert engine.check_outcome(state) == (None, None)
    state = engine.apply_move(state, 1, {"cell": other_cells[0]})
    state = engine.apply_move(state, 0, {"cell": b})
    assert engine.check_outcome(state) == (None, None)
    state = engine.apply_move(state, 1, {"cell": other_cells[1]})
    state = engine.apply_move(state, 0, {"cell": c})

    assert engine.check_outcome(state) == ("white", "three_in_a_row")


def test_tictactoe_occupied_cell_raises_illegal_move():
    engine = TicTacToeEngine()
    state = engine.apply_move(engine.initial_state(), 0, {"cell": 4})
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 1, {"cell": 4})


def test_tictactoe_full_board_no_winner_is_a_draw():
    engine = TicTacToeEngine()
    state = engine.initial_state()
    # X O X / X O O / O X X - no line for either side.
    seats_and_cells = [(0, 0), (1, 1), (0, 2), (1, 4), (0, 3), (1, 5), (0, 7), (1, 6), (0, 8)]
    for seat, cell in seats_and_cells:
        state = engine.apply_move(state, seat, {"cell": cell})
    assert engine.check_outcome(state) == ("draw", "board_full")


def test_tictactoe_legal_moves_is_none():
    engine = TicTacToeEngine()
    assert engine.legal_moves(engine.initial_state(), 0) is None


def test_tictactoe_current_turn_alternates():
    engine = TicTacToeEngine()
    state = engine.initial_state()
    assert engine.current_turn(state) == 0
    state = engine.apply_move(state, 0, {"cell": 0})
    assert engine.current_turn(state) == 1


# ---- Connect Four: all 4 directions + column-full boundary ----

def _drop_sequence(engine, moves):
    state = engine.initial_state()
    for seat, column in moves:
        state = engine.apply_move(state, seat, {"column": column})
    return state


def test_connect4_vertical_win():
    engine = Connect4Engine()
    moves = [(0, 0), (1, 1), (0, 0), (1, 1), (0, 0), (1, 1), (0, 0)]
    state = _drop_sequence(engine, moves)
    assert engine.check_outcome(state) == ("white", "four_in_a_row")


def test_connect4_horizontal_win():
    engine = Connect4Engine()
    moves = [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2), (0, 3)]
    state = _drop_sequence(engine, moves)
    assert engine.check_outcome(state) == ("white", "four_in_a_row")


def test_connect4_diagonal_up_right_win():
    engine = Connect4Engine()
    moves = [
        (0, 0),
        (1, 1),
        (0, 1),
        (1, 2),
        (0, 6),
        (1, 2),
        (0, 2),
        (1, 3),
        (0, 6),
        (1, 3),
        (0, 6),
        (1, 3),
        (0, 3),
    ]
    state = _drop_sequence(engine, moves)
    assert engine.check_outcome(state) == ("white", "four_in_a_row")


def test_connect4_diagonal_up_left_win():
    """Mirror image of the up-right diagonal - descending from col3 to col0."""
    engine = Connect4Engine()
    moves = [
        (0, 3),
        (1, 2),
        (0, 2),
        (1, 1),
        (0, 6),
        (1, 1),
        (0, 1),
        (1, 0),
        (0, 6),
        (1, 0),
        (0, 6),
        (1, 0),
        (0, 0),
    ]
    state = _drop_sequence(engine, moves)
    assert engine.check_outcome(state) == ("white", "four_in_a_row")


def test_connect4_full_column_raises_illegal_move():
    engine = Connect4Engine()
    state = engine.initial_state()
    for i in range(ROWS):
        state = engine.apply_move(state, i % 2, {"column": 0})
    with pytest.raises(IllegalMove):
        engine.apply_move(state, (ROWS) % 2, {"column": 0})


def test_connect4_legal_moves_excludes_full_columns():
    engine = Connect4Engine()
    state = engine.initial_state()
    for i in range(ROWS):
        state = engine.apply_move(state, i % 2, {"column": 0})
    legal = engine.legal_moves(state, 0)
    assert {"column": 0} not in legal
    assert len(legal) == COLS - 1


def test_connect4_full_board_no_winner_is_a_draw():
    """check_outcome is a pure function of state, not of how that state
    was reached - this board was generated by random search and verified
    (via this engine's own _winner()) to contain zero 4-in-a-rows in any
    direction before being hardcoded here, rather than hand-traced, which
    is error-prone across a 6x7 grid x 4 directions."""
    engine = Connect4Engine()
    board = [
        [0, 0, 1, 1, 0, 1, 1],
        [0, 0, 0, 1, 0, 0, 1],
        [0, 1, 0, 0, 1, 1, 1],
        [1, 1, 0, 1, 1, 0, 0],
        [0, 1, 1, 0, 1, 1, 1],
        [0, 0, 0, 1, 0, 1, 0],
    ]
    assert len(board) == ROWS and all(len(row) == COLS for row in board)
    state = {"board": board, "next_seat": 0}
    result, termination = engine.check_outcome(state)
    assert result == "draw"
    assert termination == "board_full"


# ---- Dots and Boxes: completing boxes, extra turns, scoring ----

def test_dab_completing_a_box_claims_it_and_grants_another_turn():
    engine = DotsAndBoxesEngine()
    state = engine.initial_state()
    # Seat 1 draws 3 of box (0,0)'s 4 sides.
    for edge_type, row, col in [("h", 0, 0), ("v", 0, 0), ("h", 1, 0)]:
        state = engine.apply_move(state, 1, {"edge_type": edge_type, "row": row, "col": col})
    assert state["boxes"][0][0] is None
    # Seat 0 draws the last side - claims the box and goes again.
    state = engine.apply_move(state, 0, {"edge_type": "v", "row": 0, "col": 1})
    assert state["boxes"][0][0] == 0
    assert state["next_seat"] == 0


def test_dab_one_line_can_complete_two_boxes_at_once():
    engine = DotsAndBoxesEngine()
    state = engine.initial_state()
    # 3 sides each of adjacent boxes (0,0) and (0,1), missing only the
    # vertical line between them (v_edges[0][1], shared by both).
    setup = [("h", 0, 0), ("h", 1, 0), ("v", 0, 0), ("h", 0, 1), ("h", 1, 1), ("v", 0, 2)]
    for edge_type, row, col in setup:
        state = engine.apply_move(state, 1, {"edge_type": edge_type, "row": row, "col": col})
    assert state["boxes"][0][0] is None and state["boxes"][0][1] is None

    state = engine.apply_move(state, 0, {"edge_type": "v", "row": 0, "col": 1})
    assert state["boxes"][0][0] == 0
    assert state["boxes"][0][1] == 0
    assert state["next_seat"] == 0  # still just one extra turn, not two


def test_dab_redrawing_a_line_is_illegal():
    engine = DotsAndBoxesEngine()
    state = engine.apply_move(engine.initial_state(), 0, {"edge_type": "h", "row": 0, "col": 0})
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 1, {"edge_type": "h", "row": 0, "col": 0})


def test_dab_full_board_scores_more_boxes_as_winner():
    engine = DotsAndBoxesEngine()
    state = engine.initial_state()
    state["h_edges"] = [[True] * DAB_COLS for _ in range(DAB_ROWS + 1)]
    state["v_edges"] = [[True] * (DAB_COLS + 1) for _ in range(DAB_ROWS)]
    boxes = [[0] * DAB_COLS for _ in range(DAB_ROWS)]
    for r, c in [(3, 0), (3, 1), (3, 2), (3, 3), (2, 2), (2, 3)]:
        boxes[r][c] = 1
    state["boxes"] = boxes  # 10 white boxes, 6 black boxes
    result, termination = engine.check_outcome(state)
    assert result == "white"
    assert termination == "board_full"


def test_dab_not_over_until_every_line_is_drawn():
    engine = DotsAndBoxesEngine()
    state = engine.initial_state()
    state["h_edges"] = [[True] * DAB_COLS for _ in range(DAB_ROWS + 1)]
    state["v_edges"] = [[True] * (DAB_COLS + 1) for _ in range(DAB_ROWS)]
    state["v_edges"][0][0] = False  # one line still missing
    assert engine.check_outcome(state) == (None, None)


# ---- Reversi: standard start, flips, forced pass, scoring ----

def test_reversi_initial_state_matches_standard_setup():
    engine = ReversiEngine()
    state = engine.initial_state()
    assert state["board"][3][3] == 0
    assert state["board"][3][4] == 1
    assert state["board"][4][3] == 1
    assert state["board"][4][4] == 0
    assert sorted((m["row"], m["col"]) for m in engine.legal_moves(state, 0)) == [(2, 4), (3, 5), (4, 2), (5, 3)]


def test_reversi_move_flips_flanked_pieces():
    engine = ReversiEngine()
    state = engine.initial_state()
    new_state = engine.apply_move(state, 0, {"row": 2, "col": 4})
    assert new_state["board"][2][4] == 0
    assert new_state["board"][3][4] == 0  # flipped from black to white
    assert new_state["board"][4][4] == 0  # untouched, already white
    assert new_state["next_seat"] == 1


def test_reversi_move_that_flanks_nothing_is_illegal():
    engine = ReversiEngine()
    state = engine.initial_state()
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 0, {"row": 0, "col": 0})


def test_reversi_occupied_cell_is_illegal():
    engine = ReversiEngine()
    state = engine.initial_state()
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 0, {"row": 3, "col": 3})


def test_reversi_stuck_player_is_skipped_automatically():
    """If the opponent has no legal move anywhere on the board after my
    move, it's my turn again - no explicit 'pass' needed from them."""
    engine = ReversiEngine()
    board = [[None] * 8 for _ in range(8)]
    board[0][0] = 0
    board[0][1] = 1
    board[0][2] = 1
    board[7][0] = 0
    board[7][1] = 1
    state = {"board": board, "next_seat": 0}
    assert engine.legal_moves(state, 1) == []  # black already has nothing else to do here

    new_state = engine.apply_move(state, 0, {"row": 0, "col": 3})
    assert engine.legal_moves(new_state, 1) == []
    assert new_state["next_seat"] == 0  # black skipped, white goes again


def test_reversi_more_pieces_wins_when_both_sides_are_stuck():
    engine = ReversiEngine()
    board = [[None] * 8 for _ in range(8)]
    for r in range(4):
        for c in range(8):
            board[r][c] = 0
    for r in range(4, 8):
        for c in range(8):
            board[r][c] = 1
    state = {"board": board, "next_seat": 0}
    assert engine.check_outcome(state) == ("draw", "board_full")

    board[7][7] = 0  # tip the balance - 33 white, 31 black
    result, termination = engine.check_outcome({"board": board, "next_seat": 0})
    assert result == "white"
    assert termination == "no_legal_moves"


# ---- Checkers: setup, mandatory capture, multi-jump, kinging, loss conditions ----

def _empty_checkers_state(next_seat=0):
    return {"board": [[None] * 8 for _ in range(8)], "next_seat": next_seat, "must_continue_from": None}


def test_checkers_initial_setup_has_12_pieces_each_on_dark_squares():
    engine = CheckersEngine()
    state = engine.initial_state()
    board = state["board"]
    white = [(r, c) for r in range(8) for c in range(8) if board[r][c] == "w"]
    black = [(r, c) for r in range(8) for c in range(8) if board[r][c] == "b"]
    assert len(white) == 12 and len(black) == 12
    assert all((r + c) % 2 == 1 for r, c in white + black)
    assert all(r <= 2 for r, c in white)
    assert all(r >= 5 for r, c in black)


def test_checkers_simple_move_count_from_opening():
    engine = CheckersEngine()
    state = engine.initial_state()
    # Only the front row (closest to the middle) has anywhere to go.
    assert len(engine.legal_moves(state, 0)) == 7


def test_checkers_capture_removes_the_jumped_piece():
    engine = CheckersEngine()
    state = _empty_checkers_state()
    state["board"][2][2] = "w"
    state["board"][3][3] = "b"
    new_state = engine.apply_move(state, 0, {"from": [2, 2], "to": [4, 4]})
    assert new_state["board"][4][4] == "w"
    assert new_state["board"][3][3] is None
    assert new_state["board"][2][2] is None


def test_checkers_capture_is_mandatory_when_available():
    engine = CheckersEngine()
    state = _empty_checkers_state()
    state["board"][2][2] = "w"
    state["board"][3][3] = "b"
    state["board"][5][5] = "w"  # a second white piece with an ordinary move available
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 0, {"from": [5, 5], "to": [6, 4]})


def test_checkers_multi_jump_must_continue_with_the_same_piece():
    engine = CheckersEngine()
    state = _empty_checkers_state()
    state["board"][2][2] = "w"
    state["board"][3][3] = "b"
    state["board"][5][5] = "b"

    after_first = engine.apply_move(state, 0, {"from": [2, 2], "to": [4, 4]})
    assert after_first["must_continue_from"] == [4, 4]
    assert after_first["next_seat"] == 0  # same player, must keep jumping

    # Trying to move a different piece mid-chain is illegal.
    after_first["board"][0][1] = "w"
    with pytest.raises(IllegalMove):
        engine.apply_move(after_first, 0, {"from": [0, 1], "to": [1, 0]})

    after_second = engine.apply_move(after_first, 0, {"from": [4, 4], "to": [6, 6]})
    assert after_second["board"][6][6] == "w"
    assert after_second["board"][3][3] is None and after_second["board"][5][5] is None
    assert after_second["must_continue_from"] is None
    assert after_second["next_seat"] == 1


def test_checkers_reaching_the_back_row_kings_and_ends_the_turn():
    engine = CheckersEngine()
    state = _empty_checkers_state()
    state["board"][5][3] = "w"
    state["board"][6][4] = "b"
    new_state = engine.apply_move(state, 0, {"from": [5, 3], "to": [7, 5]})
    assert new_state["board"][7][5] == "wk"
    assert new_state["must_continue_from"] is None
    assert new_state["next_seat"] == 1


def test_checkers_king_can_move_backward():
    engine = CheckersEngine()
    state = _empty_checkers_state()
    state["board"][4][4] = "wk"
    destinations = sorted(tuple(m["to"]) for m in engine.legal_moves(state, 0))
    assert destinations == [(3, 3), (3, 5), (5, 3), (5, 5)]


def test_checkers_man_cannot_move_backward():
    engine = CheckersEngine()
    state = _empty_checkers_state()
    state["board"][4][4] = "w"
    destinations = sorted(tuple(m["to"]) for m in engine.legal_moves(state, 0))
    assert destinations == [(5, 3), (5, 5)]


def test_checkers_losing_all_pieces_loses_the_game():
    engine = CheckersEngine()
    state = _empty_checkers_state()
    state["board"][4][4] = "b"
    assert engine.check_outcome(state) == ("black", "no_pieces_left")


def test_checkers_no_legal_moves_loses_the_game():
    engine = CheckersEngine()
    state = _empty_checkers_state()
    state["board"][0][1] = "w"
    state["board"][1][0] = "b"
    state["board"][1][2] = "b"
    state["board"][2][3] = "b"  # blocks the only capture landing too
    assert engine.legal_moves(state, 0) == []
    assert engine.check_outcome(state) == ("black", "no_legal_moves")


# ---- Backgammon: setup, movement, hitting, bar entry, bearing off, dice ----

def _bg_state(points=None, bar=None, borne_off=None, dice=(6, 4), next_seat=0):
    return {
        "points": points if points is not None else [0] * 24,
        "bar": list(bar) if bar is not None else [0, 0],
        "borne_off": list(borne_off) if borne_off is not None else [0, 0],
        "dice": list(dice),
        "remaining_dice": list(dice),
        "next_seat": next_seat,
    }


def test_backgammon_initial_setup_has_15_checkers_each_in_standard_spots():
    engine = BackgammonEngine()
    state = engine.initial_state()
    points = state["points"]
    assert sum(p for p in points if p > 0) == 15
    assert sum(-p for p in points if p < 0) == 15
    assert points[23] == 2 and points[12] == 5 and points[7] == 3 and points[5] == 5
    assert points[0] == -2 and points[11] == -5 and points[16] == -3 and points[18] == -5
    assert len(state["dice"]) in (2, 4)


def test_backgammon_move_distance_must_match_a_remaining_die():
    engine = BackgammonEngine()
    points = [0] * 24
    points[10] = 1
    state = _bg_state(points, dice=(6, 4))
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 0, {"from": 10, "to": 3})  # distance 7 - not one of the dice


def test_backgammon_landing_on_a_blot_hits_it():
    engine = BackgammonEngine()
    points = [0] * 24
    points[10] = 1
    points[7] = -1  # lone black checker
    state = _bg_state(points, dice=(3, 5))
    new_state = engine.apply_move(state, 0, {"from": 10, "to": 7})
    assert new_state["points"][7] == 1
    assert new_state["bar"][1] == 1


def test_backgammon_landing_on_two_or_more_is_blocked():
    engine = BackgammonEngine()
    points = [0] * 24
    points[10] = 1
    points[7] = -2  # a real wall, not a blot
    state = _bg_state(points, dice=(3, 5))
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 0, {"from": 10, "to": 7})


def test_backgammon_must_enter_from_the_bar_before_any_other_move():
    engine = BackgammonEngine()
    points = [0] * 24
    points[10] = 1
    state = _bg_state(points, bar=[1, 0], dice=(3, 5))
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 0, {"from": 10, "to": 7})


def test_backgammon_bar_entry_uses_die_minus_one_style_mapping_and_can_hit():
    engine = BackgammonEngine()
    points = [0] * 24
    points[2] = 1  # white blot sitting on black's entry point for die 3
    state = _bg_state(points, bar=[0, 1], dice=(3, 5), next_seat=1)
    new_state = engine.apply_move(state, 1, {"from": BAR, "to": 2})
    assert new_state["points"][2] == -1
    assert new_state["bar"][0] == 1  # white's hit checker goes to the bar
    assert new_state["bar"][1] == 0


def test_backgammon_bearing_off_requires_all_checkers_home():
    engine = BackgammonEngine()
    points = [0] * 24
    points[5] = 1
    points[10] = 14  # one checker still outside the home board
    state = _bg_state(points, dice=(6, 4))
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 0, {"from": 5, "to": OFF})


def test_backgammon_bearing_off_with_an_exact_die():
    engine = BackgammonEngine()
    points = [0] * 24
    points[5] = 2
    points[0] = 13
    state = _bg_state(points, dice=(6, 2))
    new_state = engine.apply_move(state, 0, {"from": 5, "to": OFF})
    assert new_state["borne_off"][0] == 1
    assert new_state["points"][5] == 1


def test_backgammon_bearing_off_the_furthest_checker_with_an_overage_die():
    engine = BackgammonEngine()
    points = [0] * 24
    points[3] = 1  # needs exactly 4, but no 4 was rolled
    points[0] = 14
    state = _bg_state(points, dice=(6, 2))
    new_state = engine.apply_move(state, 0, {"from": 3, "to": OFF})
    assert new_state["borne_off"][0] == 1


def test_backgammon_overage_bear_off_rejected_if_a_further_checker_exists():
    engine = BackgammonEngine()
    points = [0] * 24
    points[3] = 1
    points[5] = 1  # this one is further back - must be borne off (or moved) first
    points[0] = 13
    state = _bg_state(points, dice=(6, 2))
    with pytest.raises(IllegalMove):
        engine.apply_move(state, 0, {"from": 3, "to": OFF})


def test_backgammon_doubles_give_four_moves_of_the_same_value():
    # Roll enough times to observe a double and confirm it expands to 4.
    saw_double = False
    for _ in range(200):
        rolled = bg_roll()
        if len(rolled) == 4:
            saw_double = True
            assert rolled[0] == rolled[1] == rolled[2] == rolled[3]
            break
    assert saw_double


def test_backgammon_stuck_mid_turn_forfeits_the_remaining_die():
    engine = BackgammonEngine()
    points = [0] * 24
    points[10] = 1
    points[0] = -2  # blocks the only destination for the second die (4)
    state = _bg_state(points, dice=(6, 4))
    new_state = engine.apply_move(state, 0, {"from": 10, "to": 4})
    assert new_state["next_seat"] == 1
    assert len(new_state["remaining_dice"]) in (2, 4)  # a fresh roll for the other player


def test_backgammon_bearing_off_all_15_wins():
    engine = BackgammonEngine()
    assert engine.check_outcome(_bg_state(borne_off=[15, 0])) == ("white", "all_checkers_home")
    assert engine.check_outcome(_bg_state(borne_off=[0, 15])) == ("black", "all_checkers_home")
    assert engine.check_outcome(_bg_state(borne_off=[14, 10])) == (None, None)
