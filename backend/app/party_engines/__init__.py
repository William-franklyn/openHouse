from app.errors import DomainError
from app.party_engines.base import PartyEngine
from app.party_engines.codenames_engine import CodenamesEngine
from app.party_engines.draft_engine import DraftEngine
from app.party_engines.hearts_engine import HeartsEngine
from app.party_engines.spades_engine import SpadesEngine
from app.party_engines.trivia_engine import TriviaEngine
from app.party_engines.uno_engine import UnoEngine
from app.party_engines.werewolf_engine import WerewolfEngine

PARTY_ENGINES: dict[str, PartyEngine] = {
    "trivia": TriviaEngine(),
    "draft": DraftEngine(),
    "uno": UnoEngine(),
    "codenames": CodenamesEngine(),
    "hearts": HeartsEngine(),
    "werewolf": WerewolfEngine(),
    "spades": SpadesEngine(),
}


def get_party_engine(kind: str) -> PartyEngine:
    engine = PARTY_ENGINES.get(kind)
    if engine is None:
        raise DomainError("bad_request", f"Unknown party game kind '{kind}'.")
    return engine
