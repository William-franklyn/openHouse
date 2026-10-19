"""FastAPI app: REST routes, the /ws realtime endpoint, and the admin API."""

import json
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as redis_asyncio
from fastapi import Depends, FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app import files as files_mod
from app import members as members_mod
from app import messages as messages_mod
from app import metrics as metrics_mod
from app import realtime
from app import rooms as rooms_mod
from app import safety
from app.config import Settings, get_settings
from app.db import Database
from app.errors import DomainError
from app.files import Storage
from app.models import Channel, Member, Report, Room, utcnow
from app.realtime import Hub


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(
    settings: Settings | None = None,
    redis_client=None,
    storage: Storage | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.DATABASE_URL)
    redis_client = redis_client or redis_asyncio.from_url(settings.REDIS_URL)
    storage = storage or Storage(settings)
    hub = Hub(redis_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.create_all()
        await hub.start()
        yield
        await hub.stop()
        await db.dispose()

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.redis = redis_client
    app.state.storage = storage
    app.state.hub = hub

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.http_status, content={"code": exc.code, "message": exc.message})

    register_routes(app)
    return app


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request):
    db: Database = request.app.state.db
    async with db.session() as session:
        yield session


def get_redis(request: Request):
    return request.app.state.redis


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


def get_hub(request: Request) -> Hub:
    return request.app.state.hub


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:]
    return None


async def require_room_member(
    room_id: str,
    session=Depends(get_session),
    token: str | None = Depends(bearer_token),
) -> Member:
    return await members_mod.require_member(session, token, room_id)


def require_admin(x_admin_token: str | None = Header(default=None), settings: Settings = Depends(get_settings_dep)):
    if not x_admin_token or x_admin_token != settings.ADMIN_TOKEN:
        raise DomainError("not_allowed", "Admin token required.")


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateRoomBody(BaseModel):
    name: str
    ends_at: datetime | None = None
    owner_name: str | None = None
    device_id: str | None = None


class JoinBody(BaseModel):
    name: str | None = None
    over_18: bool = False
    invite_code: str | None = None
    device_id: str | None = None


class RecoverBody(BaseModel):
    recovery_code: str
    device_id: str | None = None


class PatchRoomBody(BaseModel):
    name: str | None = None
    join_policy: str | None = None
    invite_by: str | None = None
    ends_at: datetime | None = None


class ReportBody(BaseModel):
    reason: str
    target_member_id: str | None = None
    message_id: str | None = None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def room_public(room: Room, member_count: int) -> dict:
    return {
        "id": room.id,
        "name": room.name,
        "code": room.code,
        "member_count": member_count,
        "join_policy": room.join_policy,
        "is_active": room.is_active(),
    }


def member_out(member: Member) -> dict:
    return {
        "member_id": member.id,
        "name": member.display_name,
        "is_anonymous": member.is_anonymous,
        "role": member.role,
        "status": member.status,
    }


async def active_member_count(session, room_id: str) -> int:
    result = await session.execute(
        select(Member).where(Member.room_id == room_id, Member.status == "active")
    )
    return len(result.scalars().all())


def message_out(msg) -> dict:
    return {
        "id": msg.id,
        "channel_id": msg.channel_id,
        "seq": msg.seq,
        "member_id": msg.member_id,
        "kind": msg.kind,
        "text": msg.text,
        "file_id": msg.file_id,
        "created_at": msg.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register_routes(app: FastAPI) -> None:
    @app.post("/api/rooms")
    async def create_room_route(
        body: CreateRoomBody,
        session=Depends(get_session),
        settings: Settings = Depends(get_settings_dep),
    ):
        result = await rooms_mod.create_room(
            session, settings, body.name, body.ends_at, body.owner_name, body.device_id
        )
        return {
            "room": room_public(result["room"], 1),
            "member": member_out(result["owner"]),
            "session_token": result["session_token"],
            "recovery_code": result["recovery_code"],
        }

    @app.get("/api/rooms/by-code/{code}")
    async def preview_room_route(code: str, session=Depends(get_session)):
        room = await rooms_mod.get_room_by_code(session, code)
        return room_public(room, await active_member_count(session, room.id))

    @app.post("/api/rooms/{code}/join")
    async def join_room_route(
        code: str,
        body: JoinBody,
        request: Request,
        session=Depends(get_session),
        settings: Settings = Depends(get_settings_dep),
        redis_client=Depends(get_redis),
    ):
        await safety.check_join_rate(redis_client, settings, client_ip(request))
        room = await rooms_mod.get_room_by_code(session, code)
        result = await members_mod.join_room(
            session, settings, room, body.name, body.over_18, body.invite_code, body.device_id
        )
        return {
            "member_id": result["member"].id,
            "room_id": room.id,
            "session_token": result["session_token"],
            "status": result["status"],
        }

    @app.post("/api/rooms/{room_id}/recover-owner")
    async def recover_owner_route(
        room_id: str,
        body: RecoverBody,
        request: Request,
        session=Depends(get_session),
        settings: Settings = Depends(get_settings_dep),
        redis_client=Depends(get_redis),
    ):
        result = await rooms_mod.recover_owner(
            session, settings, redis_client, room_id, body.recovery_code, client_ip(request), body.device_id
        )
        return {"member": member_out(result["member"]), "session_token": result["session_token"]}

    @app.get("/api/rooms/{room_id}")
    async def get_room_route(room_id: str, actor: Member = Depends(require_room_member), session=Depends(get_session)):
        room = await rooms_mod.get_room_or_404(session, room_id)
        channels = await messages_mod.list_channels(session, room_id)
        return {
            "room": room_public(room, await active_member_count(session, room_id)),
            "my_role": actor.role,
            "my_member_id": actor.id,
            "channels": [{"id": c.id, "name": c.name} for c in channels],
        }

    @app.patch("/api/rooms/{room_id}")
    async def patch_room_route(
        room_id: str,
        body: PatchRoomBody,
        actor: Member = Depends(require_room_member),
        session=Depends(get_session),
    ):
        if actor.role != "owner":
            raise DomainError("not_allowed", "Only the owner can change room settings.")
        room = await rooms_mod.get_room_or_404(session, room_id)
        fields = body.model_dump(exclude_unset=True)
        kwargs = {}
        if "join_policy" in fields:
            kwargs["join_policy"] = fields["join_policy"]
        if "invite_by" in fields:
            kwargs["invite_by"] = fields["invite_by"]
        if "ends_at" in fields:
            kwargs["ends_at"] = fields["ends_at"]
        if "name" in fields:
            kwargs["name"] = fields["name"]
        room = await rooms_mod.update_room_settings(session, room, **kwargs)
        return room_public(room, await active_member_count(session, room_id))

    @app.post("/api/rooms/{room_id}/new-code")
    async def new_code_route(room_id: str, actor: Member = Depends(require_room_member), session=Depends(get_session), settings: Settings = Depends(get_settings_dep)):
        if actor.role != "owner":
            raise DomainError("not_allowed", "Only the owner can rotate the room code.")
        room = await rooms_mod.get_room_or_404(session, room_id)
        new_code = await rooms_mod.rotate_code(session, settings, room)
        return {"code": new_code}

    @app.delete("/api/rooms/{room_id}")
    async def delete_room_route(
        room_id: str,
        actor: Member = Depends(require_room_member),
        session=Depends(get_session),
        storage: Storage = Depends(get_storage),
        hub: Hub = Depends(get_hub),
    ):
        if actor.role != "owner":
            raise DomainError("not_allowed", "Only the owner can delete this room.")
        room = await rooms_mod.get_room_or_404(session, room_id)
        await hub.publish(room_id, {"type": "room_deleted", "message": "This room was deleted by the owner."})
        await rooms_mod.delete_room(session, storage, room)
        return {"ok": True}

    @app.post("/api/rooms/{room_id}/invites")
    async def create_invite_route(room_id: str, actor: Member = Depends(require_room_member), session=Depends(get_session), settings: Settings = Depends(get_settings_dep)):
        room = await rooms_mod.get_room_or_404(session, room_id)
        invite = await members_mod.create_invite(session, settings, room, actor)
        return {"code": invite.code, "expires_at": invite.expires_at.isoformat()}

    @app.get("/api/rooms/{room_id}/channels/{channel_id}/messages")
    async def history_route(
        room_id: str,
        channel_id: str,
        before_seq: int | None = None,
        actor: Member = Depends(require_room_member),
        session=Depends(get_session),
        settings: Settings = Depends(get_settings_dep),
    ):
        rows = await messages_mod.history(session, channel_id, before_seq, settings.HISTORY_PAGE_SIZE)
        return {"messages": [message_out(m) for m in rows]}

    @app.post("/api/rooms/{room_id}/files")
    async def upload_file_route(
        room_id: str,
        request: Request,
        actor: Member = Depends(require_room_member),
        session=Depends(get_session),
        settings: Settings = Depends(get_settings_dep),
        storage: Storage = Depends(get_storage),
        redis_client=Depends(get_redis),
        hub: Hub = Depends(get_hub),
    ):
        await safety.check_upload_rate(redis_client, settings, actor.id)
        room = await rooms_mod.get_room_or_404(session, room_id)
        rooms_mod.require_active(room)

        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise DomainError("bad_request", "No file provided.")
        channel_id = form.get("channel_id")

        data = await upload.read()
        asset = await files_mod.upload_file(
            session, settings, storage, room, actor, upload.filename, upload.content_type, data
        )

        if channel_id:
            channel = await session.get(Channel, channel_id)
            if channel is not None and channel.room_id == room_id:
                msg = await messages_mod.create_message(
                    session, settings, channel, actor, kind="file", file_id=asset.id
                )
                await hub.publish(room_id, realtime.message_event(msg, actor.display_name))

        return {"file_id": asset.id, "filename": asset.filename, "size": asset.size}

    @app.get("/api/files/{file_id}")
    async def download_file_route(
        file_id: str,
        session=Depends(get_session),
        storage: Storage = Depends(get_storage),
        token: str | None = Depends(bearer_token),
    ):
        # The README's path for this route carries no room id (unlike every
        # other member-scoped route) - the member's room comes from their
        # token, and the file has to belong to that same room.
        member = await members_mod.require_member(session, token)
        asset = await files_mod.get_file_or_404(session, member.room_id, file_id)
        url = files_mod.download_url(storage, asset)
        return {"url": url, "filename": asset.filename, "size": asset.size, "expires_in": 300}

    @app.post("/api/rooms/{room_id}/reports")
    async def create_report_route(
        room_id: str,
        body: ReportBody,
        actor: Member = Depends(require_room_member),
        session=Depends(get_session),
    ):
        report = await safety.create_report(
            session, room_id, actor.id, body.reason, body.target_member_id, body.message_id
        )
        return {"report_id": report.id, "status": report.status}

    # ---- platform admin ----

    @app.get("/api/admin/reports")
    async def admin_reports_route(session=Depends(get_session), _=Depends(require_admin)):
        result = await session.execute(select(Report).order_by(Report.created_at.desc()))
        reports = result.scalars().all()
        return {
            "reports": [
                {
                    "id": r.id,
                    "room_id": r.room_id,
                    "reporter_member_id": r.reporter_member_id,
                    "target_member_id": r.target_member_id,
                    "message_id": r.message_id,
                    "reason": r.reason,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in reports
            ]
        }

    @app.post("/api/admin/reports/{report_id}/resolve")
    async def admin_resolve_report_route(report_id: str, session=Depends(get_session), _=Depends(require_admin)):
        report = await session.get(Report, report_id)
        if report is None:
            raise DomainError("bad_request", "Unknown report.")
        report.status = "done"
        await session.commit()
        return {"ok": True}

    @app.get("/api/admin/metrics")
    async def admin_metrics_route(session=Depends(get_session), _=Depends(require_admin)):
        return {"metrics": await metrics_mod.list_metrics(session)}

    @app.delete("/api/admin/rooms/{room_id}")
    async def admin_delete_room_route(
        room_id: str,
        session=Depends(get_session),
        storage: Storage = Depends(get_storage),
        hub: Hub = Depends(get_hub),
        _=Depends(require_admin),
    ):
        room = await rooms_mod.get_room_or_404(session, room_id)
        await hub.publish(room_id, {"type": "room_deleted", "message": "This room was removed by a platform admin."})
        await rooms_mod.delete_room(session, storage, room)
        return {"ok": True}

    # ---- realtime ----

    @app.websocket("/ws")
    async def ws_route(websocket: WebSocket):
        await websocket.accept()

        db: Database = websocket.app.state.db
        redis_client = websocket.app.state.redis
        hub: Hub = websocket.app.state.hub
        settings: Settings = websocket.app.state.settings

        member_id: str | None = None
        room_id: str | None = None

        async with db.session() as session:
            try:
                raw = await _receive_json(websocket)
                if raw is None or raw.get("type") != "auth":
                    await websocket.send_json(
                        {"type": "error", "code": "bad_request", "message": "First message must be auth."}
                    )
                    await websocket.close()
                    return

                member = await members_mod.resolve_member_by_token(session, raw.get("session_token"))
                if member is None or member.status in ("left", "removed", "banned"):
                    await websocket.send_json({"type": "error", "code": "bad_token", "message": "Your session is no longer valid."})
                    await websocket.close()
                    return

                room = await session.get(Room, member.room_id)
                if room is None or not room.is_active():
                    await websocket.send_json({"type": "error", "code": "room_ended", "message": "This room has ended."})
                    await websocket.close()
                    return

                member_id, room_id = member.id, room.id
                hub.register(room_id, member_id, websocket)
                await hub.presence_add(room_id, member_id)
                member.last_seen_at = utcnow()
                await session.commit()

                await websocket.send_json({"type": "ready"})

                last_seq = raw.get("last_seq") or {}
                for channel in await messages_mod.list_channels(session, room_id):
                    after = int(last_seq.get(channel.id, 0) or 0)
                    for msg in await messages_mod.messages_after(session, channel.id, after):
                        sender = await session.get(Member, msg.member_id) if msg.member_id else None
                        await websocket.send_json(
                            realtime.message_event(msg, sender.display_name if sender else None)
                        )

                await realtime._publish_presence(session, redis_client, hub, room)

                while True:
                    raw = await _receive_json(websocket)
                    if raw is None:
                        continue
                    msg_type = raw.get("type")
                    if not isinstance(msg_type, str):
                        await websocket.send_json({"type": "error", "code": "bad_request", "message": "Missing type."})
                        continue
                    try:
                        await realtime.dispatch(session, settings, redis_client, hub, room, member, msg_type, raw)
                    except DomainError as exc:
                        await websocket.send_json({"type": "error", "code": exc.code, "message": exc.message})

            except WebSocketDisconnect:
                pass
            finally:
                if room_id and member_id:
                    hub.unregister(room_id, member_id)
                    await hub.presence_remove(room_id, member_id)
                    try:
                        room = await session.get(Room, room_id)
                        if room is not None:
                            await realtime._publish_presence(session, redis_client, hub, room)
                    except Exception:
                        pass


async def _receive_json(websocket: WebSocket) -> dict | None:
    text = await websocket.receive_text()
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        await websocket.send_json({"type": "error", "code": "bad_request", "message": "Invalid JSON."})
        return None
