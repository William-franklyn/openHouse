from app.errors import DomainError
from app.game_engines.base import GameEngine
from app.game_engines.chess_engine import ChessEngine
from app.game_engines.connect4_engine import Connect4Engine
from app.game_engines.tictactoe_engine import TicTacToeEngine

ENGINES: dict[str, GameEngine] = {
    "chess": ChessEngine(),
    "tictactoe": TicTacToeEngine(),
    "connect4": Connect4Engine(),
}


def get_engine(kind: str) -> GameEngine:
    engine = ENGINES.get(kind)
    if engine is None:
        raise DomainError("bad_request", f"Unknown game kind '{kind}'.")
    return engine
