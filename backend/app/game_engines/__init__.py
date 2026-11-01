from app.errors import DomainError
from app.game_engines.backgammon_engine import BackgammonEngine
from app.game_engines.base import GameEngine
from app.game_engines.battleship_engine import BattleshipEngine
from app.game_engines.checkers_engine import CheckersEngine
from app.game_engines.chess_engine import ChessEngine
from app.game_engines.connect4_engine import Connect4Engine
from app.game_engines.dots_and_boxes_engine import DotsAndBoxesEngine
from app.game_engines.reversi_engine import ReversiEngine
from app.game_engines.tictactoe_engine import TicTacToeEngine

ENGINES: dict[str, GameEngine] = {
    "chess": ChessEngine(),
    "tictactoe": TicTacToeEngine(),
    "connect4": Connect4Engine(),
    "dots_and_boxes": DotsAndBoxesEngine(),
    "reversi": ReversiEngine(),
    "checkers": CheckersEngine(),
    "backgammon": BackgammonEngine(),
    "battleship": BattleshipEngine(),
}


def get_engine(kind: str) -> GameEngine:
    engine = ENGINES.get(kind)
    if engine is None:
        raise DomainError("bad_request", f"Unknown game kind '{kind}'.")
    return engine
