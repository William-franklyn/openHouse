import sys
from pathlib import Path

import fakeredis
import pytest
from httpx import ASGITransport, AsyncClient
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import realtime  # noqa: E402
from app.config import Settings  # noqa: E402
from app.files import Storage  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Member, Room  # noqa: E402


class FakeWebSocket:
    """Stand-in for a starlette WebSocket, used to exercise realtime.py's
    dispatch/Hub logic directly without a live ASGI WebSocket connection."""

    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True


@pytest.fixture
def settings(tmp_path) -> Settings:
    db_path = tmp_path / "test.db"
    return Settings(
        DATABASE_URL=f"sqlite+aiosqlite:///{db_path}",
        S3_ENDPOINT_URL=None,
        ADMIN_TOKEN="test-admin-token",
        MESSAGE_RATE_LIMIT=10,
        MESSAGE_RATE_WINDOW_SECONDS=10,
        JOIN_RATE_LIMIT=10,
        JOIN_RATE_WINDOW_SECONDS=60,
        UPLOAD_RATE_LIMIT=5,
        UPLOAD_RATE_WINDOW_SECONDS=60,
        RECOVERY_RATE_LIMIT=5,
        RECOVERY_RATE_WINDOW_SECONDS=60,
    )


@pytest.fixture
def fake_redis_server():
    return fakeredis.FakeServer()


@pytest.fixture
def redis_client(fake_redis_server):
    return fakeredis.FakeAsyncRedis(server=fake_redis_server)


def make_redis_client(fake_redis_server):
    """Lets a test build a second, independent client against the SAME
    in-memory fake server - i.e. a second 'server instance' sharing Redis."""
    return fakeredis.FakeAsyncRedis(server=fake_redis_server)


@pytest.fixture
def storage(settings):
    with mock_aws():
        s = Storage(settings)
        s.ensure_bucket()
        yield s


@pytest.fixture
async def app(settings, redis_client, storage):
    application = create_app(settings=settings, redis_client=redis_client, storage=storage)
    await application.state.db.create_all()
    await application.state.hub.start()
    yield application
    await application.state.hub.stop()
    await application.state.db.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def register_socket(app, room_id: str, member_id: str) -> FakeWebSocket:
    """Simulates a member's WS connection being open on this Hub instance,
    without a live ASGI WebSocket - see FakeWebSocket's docstring."""
    ws = FakeWebSocket()
    app.state.hub.register(room_id, member_id, ws)
    await app.state.hub.presence_add(room_id, member_id)
    return ws


async def ws_dispatch(app, room_id: str, member_id: str, msg_type: str, data: dict | None = None):
    """Exercises realtime.dispatch (the same function the real /ws route
    calls) for one message, against a freshly-loaded room/actor. Mirrors
    what main.py's websocket endpoint does per incoming message, just
    without a live socket driving it."""
    async with app.state.db.session() as session:
        room = await session.get(Room, room_id)
        actor = await session.get(Member, member_id)
        await realtime.dispatch(
            session, app.state.settings, app.state.redis, app.state.hub, room, actor, msg_type, data or {}
        )
