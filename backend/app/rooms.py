"""Room lifecycle: creation, codes, settings, deletion, owner recovery."""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select

from app import metrics, security
from app.errors import DomainError
from app.models import (
    CardGame,
    Channel,
    FileAsset,
    Game,
    Invite,
    Member,
    Message,
    MessageReaction,
    PartyGame,
    Pin,
    Room,
    new_id,
    to_naive_utc,
    utcnow,
)


async def _unique_code(session, settings) -> str:
    for _ in range(50):
        candidate = security.gen_room_code(settings.ROOM_CODE_ALPHABET, settings.ROOM_CODE_LENGTH)
        result = await session.execute(select(Room).where(Room.code == candidate))
        existing = [r for r in result.scalars().all() if r.is_active()]
        if not existing:
            return candidate
    raise RuntimeError("could not generate a unique room code")


def _resolve_display_name(name: str | None) -> tuple[str, bool]:
    if name is None:
        return _anon_name(), True
    trimmed = name.strip()
    if not trimmed:
        return _anon_name(), True
    return trimmed[:24], False


def _anon_name() -> str:
    import secrets as _secrets

    return f"Guest-{_secrets.randbelow(10000):04d}"


async def create_room(
    session,
    settings,
    name: str,
    ends_at: datetime | None,
    owner_name: str | None,
    device_hash: str | None,
) -> dict:
    name = (name or "").strip()
    if not (settings.ROOM_NAME_MIN <= len(name) <= settings.ROOM_NAME_MAX):
        raise DomainError(
            "bad_request",
            f"Room name must be {settings.ROOM_NAME_MIN}-{settings.ROOM_NAME_MAX} characters.",
        )

    code = await _unique_code(session, settings)
    recovery_code = security.gen_recovery_code(settings.RECOVERY_CODE_LENGTH)

    room = Room(
        id=new_id(),
        name=name,
        code=code,
        join_policy="open",
        invite_by=None,
        owner_member_id=None,
        owner_recovery_hash=security.hash_recovery_code(recovery_code),
        ends_at=to_naive_utc(ends_at),
        created_at=utcnow(),
    )
    session.add(room)

    display_name, is_anon = _resolve_display_name(owner_name)
    session_token = security.gen_session_token()
    owner = Member(
        id=new_id(),
        room_id=room.id,
        display_name=display_name,
        is_anonymous=is_anon,
        role="owner",
        session_token_hash=security.hash_token(session_token),
        device_hash=security.hash_device_id(device_hash) if device_hash else None,
        status="active",
        last_seen_at=utcnow(),
        created_at=utcnow(),
    )
    session.add(owner)
    await session.flush()

    room.owner_member_id = owner.id
    general = Channel(id=new_id(), room_id=room.id, name="general", position=0)
    session.add(general)
    await session.commit()

    await metrics.bump(session, "rooms_created")

    return {
        "room": room,
        "owner": owner,
        "session_token": session_token,
        "recovery_code": recovery_code,
        "general_channel": general,
    }


async def get_room_by_code(session, code: str) -> Room:
    result = await session.execute(select(Room).where(Room.code == code.strip().upper()))
    room = result.scalar_one_or_none()
    if room is None or room.deleted_at is not None:
        raise DomainError("bad_code", "That room code doesn't exist.")
    return room


async def get_room_or_404(session, room_id: str) -> Room:
    room = await session.get(Room, room_id)
    if room is None or room.deleted_at is not None:
        raise DomainError("bad_code", "That room doesn't exist.")
    return room


def require_active(room: Room) -> None:
    if not room.is_active():
        raise DomainError("room_ended", "This room has ended.")


async def update_room_settings(
    session,
    room: Room,
    join_policy: str | None = None,
    invite_by: str | None = None,
    ends_at: datetime | None = ...,  # sentinel: ... means "leave unchanged"
    name: str | None = None,
) -> Room:
    if join_policy is not None:
        if join_policy not in ("open", "approval", "invite_only"):
            raise DomainError("bad_request", "Unknown join policy.")
        room.join_policy = join_policy
    if invite_by is not None:
        if invite_by not in ("admins", "members"):
            raise DomainError("bad_request", "Unknown invite_by setting.")
        room.invite_by = invite_by
    if ends_at is not ...:
        room.ends_at = to_naive_utc(ends_at)
    if name is not None:
        name = name.strip()
        if not name:
            raise DomainError("bad_request", "Room name can't be empty.")
        room.name = name[:40]
    await session.commit()
    return room


async def set_local_mode(session, room: Room, enabled: bool, ip: str | None) -> Room:
    """IP-only, not GPS - see models.Room.local_mode_ip. The owner must
    enable this *from the network they want to allow* (their own hotspot,
    or the venue/dorm's shared Wi-Fi); whoever's request IP matches at
    join time gets in. Nothing here ever asks a joiner for their location."""
    if not enabled:
        room.local_mode_ip = None
        await session.commit()
        return room

    if not ip or ip == "unknown":
        raise DomainError("bad_request", "Couldn't read your network address to turn on Local mode.")
    room.local_mode_ip = ip
    await session.commit()
    return room


async def rotate_code(session, settings, room: Room) -> str:
    room.code = await _unique_code(session, settings)
    await session.commit()
    return room.code


async def delete_room(session, storage, room: Room) -> None:
    """Hard-deletes everything the room owns right now (see SPEC.md
    Decisions: the spec's 24h grace window needs a background scheduler,
    which felt disproportionate for an MVP pass, so cleanup is immediate
    instead). The Room row itself is soft-deleted (deleted_at set, row
    kept) rather than hard-deleted, so it still exists for metrics/
    history and so its code can't collide with a brand new room.

    Deletion order matters - children before the parents they reference,
    so this never trips a foreign key constraint on a real Postgres
    database (sqlite in tests is lax about this and wouldn't have caught
    it, which is exactly how Pin/MessageReaction cleanup went missing
    here for a while): MessageReaction and Pin both reference Message,
    so both must go before the bulk Message delete; Channel references
    Room, so it goes after everything that references *it* (Message).
    Reports are deliberately left alone - they're a moderation audit
    trail (who reported whom, and why), and that needs to survive the
    room it was filed against being deleted, not disappear the moment
    someone deletes the evidence."""
    room.deleted_at = utcnow()

    channel_ids = [
        c.id for c in (await session.execute(select(Channel).where(Channel.room_id == room.id))).scalars()
    ]
    if channel_ids:
        message_ids = list(
            (await session.execute(select(Message.id).where(Message.channel_id.in_(channel_ids)))).scalars()
        )
        if message_ids:
            await session.execute(
                MessageReaction.__table__.delete().where(MessageReaction.message_id.in_(message_ids))
            )
            await session.execute(Pin.__table__.delete().where(Pin.message_id.in_(message_ids)))
        await session.execute(
            Message.__table__.delete().where(Message.channel_id.in_(channel_ids))
        )
        await session.execute(Channel.__table__.delete().where(Channel.id.in_(channel_ids)))

    files_result = await session.execute(select(FileAsset).where(FileAsset.room_id == room.id))
    for f in files_result.scalars().all():
        storage.delete(f.storage_key)
        await session.delete(f)

    await session.execute(Invite.__table__.delete().where(Invite.room_id == room.id))
    await session.execute(Game.__table__.delete().where(Game.room_id == room.id))
    await session.execute(PartyGame.__table__.delete().where(PartyGame.room_id == room.id))
    await session.execute(CardGame.__table__.delete().where(CardGame.room_id == room.id))
    await session.execute(Member.__table__.delete().where(Member.room_id == room.id))

    await session.commit()


async def find_dormant_room_ids(session, threshold_days: int) -> list[str]:
    """Rooms with no message activity and nobody seen for threshold_days -
    a room is dormant once ALL of: it was created more than threshold_days
    ago (so a brand new empty room gets a grace period), its most recent
    message (if any) is older than that, and its most recently active
    member (if any, by last_seen_at falling back to their own created_at
    for a member who's never reconnected since joining) is also older
    than that. Any one of those being recent keeps the room alive."""
    cutoff = utcnow() - timedelta(days=threshold_days)

    last_message_at = (
        select(Channel.room_id.label("room_id"), func.max(Message.created_at).label("at"))
        .join(Message, Message.channel_id == Channel.id)
        .group_by(Channel.room_id)
        .subquery()
    )
    last_member_at = (
        select(
            Member.room_id.label("room_id"),
            func.max(func.coalesce(Member.last_seen_at, Member.created_at)).label("at"),
        )
        .group_by(Member.room_id)
        .subquery()
    )

    query = (
        select(Room.id)
        .outerjoin(last_message_at, last_message_at.c.room_id == Room.id)
        .outerjoin(last_member_at, last_member_at.c.room_id == Room.id)
        .where(
            Room.deleted_at.is_(None),
            Room.created_at < cutoff,
            or_(last_message_at.c.at.is_(None), last_message_at.c.at < cutoff),
            or_(last_member_at.c.at.is_(None), last_member_at.c.at < cutoff),
        )
    )
    result = await session.execute(query)
    return [row[0] for row in result.all()]


async def run_dormant_sweep_loop(db, storage, settings) -> None:
    """Runs for the lifetime of the process (started from main.py's
    lifespan, alongside the Hub): every DORMANT_SWEEP_INTERVAL_SECONDS,
    finds rooms dormant for DORMANT_ROOM_DAYS and deletes each one
    through the exact same delete_room() an admin's explicit delete
    uses - one cleanup path, not two that could drift apart. Sleeps
    first so a slow test suite or a rapid restart loop never fires it
    immediately on every boot."""
    while True:
        await asyncio.sleep(settings.DORMANT_SWEEP_INTERVAL_SECONDS)
        try:
            async with db.session() as session:
                dormant_ids = await find_dormant_room_ids(session, settings.DORMANT_ROOM_DAYS)
                for room_id in dormant_ids:
                    room = await session.get(Room, room_id)
                    if room is not None and room.deleted_at is None:
                        await delete_room(session, storage, room)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # must never let one bad tick kill the sweep loop for good


async def transfer_ownership(session, room: Room, old_owner: Member, new_owner: Member) -> None:
    old_owner.role = "member"
    new_owner.role = "owner"
    room.owner_member_id = new_owner.id
    await session.commit()
    await metrics.bump(session, "ownership_handovers")


async def recover_owner(
    session, settings, redis, room_id: str, recovery_code: str, ip: str, device_hash: str | None
) -> dict:
    from app import safety

    await safety.check_recovery_rate(redis, settings, ip)

    room = await get_room_or_404(session, room_id)

    if not security.verify_recovery_code(recovery_code, room.owner_recovery_hash):
        raise DomainError("not_allowed", "That recovery code is wrong.")

    owner = await session.get(Member, room.owner_member_id) if room.owner_member_id else None
    if owner is None:
        raise DomainError("bad_request", "This room has no owner to recover.")

    session_token = security.gen_session_token()
    owner.session_token_hash = security.hash_token(session_token)
    owner.device_hash = security.hash_device_id(device_hash) if device_hash else owner.device_hash
    owner.status = "active"
    owner.last_seen_at = utcnow()
    await session.commit()

    return {"member": owner, "session_token": session_token, "room": room}
