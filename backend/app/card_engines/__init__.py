from app.errors import DomainError
from app.card_engines.base import CardEngine
from app.card_engines.poker_engine import PokerEngine

CARD_ENGINES: dict[str, CardEngine] = {
    "poker": PokerEngine(),
}


def get_card_engine(kind: str) -> CardEngine:
    engine = CARD_ENGINES.get(kind)
    if engine is None:
        raise DomainError("bad_request", f"Unknown card game kind '{kind}'.")
    return engine
