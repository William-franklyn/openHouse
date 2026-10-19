"""Channels, messages (with gap-free per-channel seq), pins, deletion."""

from sqlalchemy import select, update

from app import metrics
from app.errors import DomainError
from app.models import Channel, Member, Message, Pin, new_id, utcnow


async def list_channels(session, room_id: str) -> list[Channel]:
    result = await session.execute(
        select(Channel).where(Channel.room_id == room_id).order_by(Channel.position)
    )
    return list(result.scalars().all())


async def create_channel(session, settings, room, actor: Member, name: str) -> Channel:
    if actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the owner or a moderator can create channels.")

    name = (name or "").strip().lower().lstrip("#")
    if not name or len(name) > 32:
        raise DomainError("bad_request", "Channel name must be 1-32 characters.")

    existing = await list_channels(session, room.id)
    if any(c.name == name for c in existing):
        raise DomainError("bad_request", "That channel already exists.")

    extra_count = sum(1 for c in existing if c.name != "general")
    if extra_count >= settings.MAX_EXTRA_CHANNELS:
        raise DomainError("bad_request", "This room already has the maximum number of channels.")

    channel = Channel(id=new_id(), room_id=room.id, name=name, position=len(existing))
    session.add(channel)
    await session.commit()
    return channel


async def _next_seq(session, channel_id: str) -> int:
    await session.execute(
        update(Channel).where(Channel.id == channel_id).values(next_seq=Channel.next_seq + 1)
    )
    result = await session.execute(select(Channel.next_seq).where(Channel.id == channel_id))
    new_next = result.scalar_one()
    return new_next - 1


async def create_message(
    session,
    settings,
    channel: Channel,
    member: Member | None,
    text: str | None = None,
    kind: str = "text",
    file_id: str | None = None,
) -> Message:
    if kind == "text":
        text = (text or "").strip()
        if not (settings.MESSAGE_MIN <= len(text) <= settings.MESSAGE_MAX):
            raise DomainError(
                "bad_request",
                f"Messages must be {settings.MESSAGE_MIN}-{settings.MESSAGE_MAX} characters.",
            )

    seq = await _next_seq(session, channel.id)
    message = Message(
        id=new_id(),
        channel_id=channel.id,
        seq=seq,
        member_id=member.id if member else None,
        kind=kind,
        text=text,
        file_id=file_id,
        created_at=utcnow(),
    )
    session.add(message)
    await session.commit()

    if kind == "text":
        await metrics.bump(session, "messages_sent")
    elif kind == "file":
        await metrics.bump(session, "files_shared")

    return message


async def history(session, channel_id: str, before_seq: int | None, limit: int) -> list[Message]:
    query = select(Message).where(Message.channel_id == channel_id, Message.deleted_at.is_(None))
    if before_seq is not None:
        query = query.where(Message.seq < before_seq)
    query = query.order_by(Message.seq.desc()).limit(limit)
    result = await session.execute(query)
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def messages_after(session, channel_id: str, after_seq: int) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(
            Message.channel_id == channel_id,
            Message.seq > after_seq,
            Message.deleted_at.is_(None),
        )
        .order_by(Message.seq.asc())
    )
    return list(result.scalars().all())


async def pin_message(session, settings, room_id: str, actor: Member, message: Message) -> Pin:
    if actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the owner or a moderator can pin messages.")

    existing = (
        await session.execute(select(Pin).where(Pin.room_id == room_id))
    ).scalars().all()
    if any(p.message_id == message.id for p in existing):
        return next(p for p in existing if p.message_id == message.id)
    if len(existing) >= settings.MAX_PINS:
        raise DomainError("bad_request", "This room already has the maximum number of pins.")

    pin = Pin(id=new_id(), room_id=room_id, message_id=message.id, position=len(existing))
    session.add(pin)
    await session.commit()
    return pin


async def unpin_message(session, room_id: str, actor: Member, message_id: str) -> None:
    if actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the owner or a moderator can unpin messages.")
    result = await session.execute(
        select(Pin).where(Pin.room_id == room_id, Pin.message_id == message_id)
    )
    pin = result.scalar_one_or_none()
    if pin is not None:
        await session.delete(pin)
        await session.commit()


async def list_pins(session, room_id: str) -> list[Pin]:
    result = await session.execute(
        select(Pin).where(Pin.room_id == room_id).order_by(Pin.position)
    )
    return list(result.scalars().all())


async def delete_message(session, actor: Member, message: Message) -> None:
    is_own = message.member_id == actor.id
    is_admin = actor.role in ("owner", "mod")
    if not (is_own or is_admin):
        raise DomainError("not_allowed", "You can't delete that message.")
    message.deleted_at = utcnow()
    await session.commit()
