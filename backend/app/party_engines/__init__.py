from app.errors import DomainError
from app.party_engines.base import PartyEngine
from app.party_engines.trivia_engine import TriviaEngine

PARTY_ENGINES: dict[str, PartyEngine] = {
    "trivia": TriviaEngine(),
}


def get_party_engine(kind: str) -> PartyEngine:
    engine = PARTY_ENGINES.get(kind)
    if engine is None:
        raise DomainError("bad_request", f"Unknown party game kind '{kind}'.")
    return engine
