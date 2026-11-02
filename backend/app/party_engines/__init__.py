from app.errors import DomainError
from app.party_engines.base import PartyEngine
from app.party_engines.codenames_engine import CodenamesEngine
from app.party_engines.draft_engine import DraftEngine
from app.party_engines.trivia_engine import TriviaEngine
from app.party_engines.uno_engine import UnoEngine

PARTY_ENGINES: dict[str, PartyEngine] = {
    "trivia": TriviaEngine(),
    "draft": DraftEngine(),
    "uno": UnoEngine(),
    "codenames": CodenamesEngine(),
}


def get_party_engine(kind: str) -> PartyEngine:
    engine = PARTY_ENGINES.get(kind)
    if engine is None:
        raise DomainError("bad_request", f"Unknown party game kind '{kind}'.")
    return engine
