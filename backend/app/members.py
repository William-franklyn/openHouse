"""Join flow, sessions, roles, kicks and bans."""

from datetime import timedelta

from sqlalchemy import select

from app import metrics, security
from app.errors import DomainError
from app.models import Invite, Member, new_id, utcnow
from app.rooms import require_active


def _resolve_display_name(room_members: list[Member], name: str | None) -> tuple[str, bool]:
    taken = {m.display_name for m in room_members}
    if name is not None and name.strip():
        base = name.strip()[:24]
    else:
        base = None

    if base is None:
        import secrets as _secrets

        while True:
            candidate = f"Guest-{_secrets.randbelow(10000):04d}"
            if candidate not in taken:
                return candidate, True

    if base not in taken:
        return base, False
    i = 2
    while f"{base} ({i})" in taken:
        i += 1
    return f"{base} ({i})", False


async def resolve_member_by_token(session, token: str | None) -> Member | None:
    """Session tokens are high-entropy and looked up globally (the WS
    `auth` message carries only a token, no room_id) - the member's own
    row tells us which room it belongs to."""
    if not token:
        return None
    token_hash = security.hash_token(token)
    result = await session.execute(select(Member).where(Member.session_token_hash == token_hash))
    return result.scalar_one_or_none()


async def require_member(session, token: str | None, room_id: str | None = None) -> Member:
    member = await resolve_member_by_token(session, token)
    if member is None or member.status in ("left", "removed", "banned"):
        raise DomainError("bad_token", "Your session is no longer valid.")
    if room_id is not None and member.room_id != room_id:
        # A real token, just not for the room in this URL - don't leak
        # which case it is.
        raise DomainError("bad_token", "Your session is no longer valid.")
    return member


async def _is_banned_device(session, room_id: str, device_hash_raw: str | None) -> bool:
    if not device_hash_raw:
        return False
    hashed = security.hash_device_id(device_hash_raw)
    result = await session.execute(
        select(Member).where(
            Member.room_id == room_id,
            Member.device_hash == hashed,
            Member.status == "banned",
        )
    )
    return result.first() is not None


async def join_room(
    session,
    settings,
    room,
    name: str | None,
    over_18: bool,
    invite_code: str | None,
    device_hash_raw: str | None,
    ip: str | None = None,
) -> dict:
    require_active(room)

    if not over_18:
        raise DomainError("bad_request", "You must be 18 or older to join.")

    if room.local_mode_ip and ip != room.local_mode_ip:
        raise DomainError(
            "wrong_network",
            "This room is only open right now to people on the same Wi-Fi/hotspot as its host.",
        )

    if await _is_banned_device(session, room.id, device_hash_raw):
        raise DomainError("banned", "You have been banned from this room.")

    invited_by_member_id = None
    invite: Invite | None = None
    if room.join_policy == "invite_only":
        if not invite_code:
            raise DomainError("bad_invite", "An invite code is required to join this room.")
        invite = await session.get(Invite, invite_code.strip())
        if (
            invite is None
            or invite.room_id != room.id
            or invite.used_by_member_id is not None
            or invite.expires_at < utcnow()
        ):
            raise DomainError("bad_invite", "That invite code is wrong, used, or expired.")
        invited_by_member_id = invite.created_by_member_id

    existing = (
        (await session.execute(select(Member).where(Member.room_id == room.id))).scalars().all()
    )
    display_name, is_anon = _resolve_display_name(existing, name)

    status = "pending" if room.join_policy == "approval" else "active"

    session_token = security.gen_session_token()
    member = Member(
        id=new_id(),
        room_id=room.id,
        display_name=display_name,
        is_anonymous=is_anon,
        role="member",
        session_token_hash=security.hash_token(session_token),
        device_hash=security.hash_device_id(device_hash_raw) if device_hash_raw else None,
        invited_by_member_id=invited_by_member_id,
        status=status,
        last_seen_at=utcnow(),
        created_at=utcnow(),
    )
    session.add(member)

    if invite is not None:
        invite.used_by_member_id = member.id

    await session.commit()

    await metrics.bump(session, "joins_anonymous" if is_anon else "joins_named")

    return {"member": member, "session_token": session_token, "status": status}


async def create_invite(session, settings, room, creator: Member) -> Invite:
    allowed = creator.role in ("owner", "mod") or room.invite_by == "members"
    if not allowed:
        raise DomainError("not_allowed", "You can't create invites for this room.")

    code = security.gen_invite_code()
    invite = Invite(
        code=code,
        room_id=room.id,
        created_by_member_id=creator.id,
        expires_at=utcnow() + timedelta(seconds=settings.INVITE_TTL_SECONDS),
    )
    session.add(invite)
    await session.commit()
    return invite


def _can_moderate(actor: Member, target: Member) -> bool:
    if actor.role == "owner":
        return target.id != actor.id
    if actor.role == "mod":
        return target.role == "member"
    return False


async def approve_member(session, actor: Member, target: Member) -> Member:
    if actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the owner or a moderator can approve joins.")
    if target.status != "pending":
        raise DomainError("bad_request", "That join request isn't pending.")
    target.status = "active"
    await session.commit()
    return target


async def reject_member(session, actor: Member, target: Member) -> Member:
    if actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the owner or a moderator can reject joins.")
    if target.status != "pending":
        raise DomainError("bad_request", "That join request isn't pending.")
    target.status = "removed"
    target.session_token_hash = None
    await session.commit()
    return target


async def remove_member(session, actor: Member, target: Member) -> Member:
    if not _can_moderate(actor, target):
        raise DomainError("not_allowed", "You can't remove that member.")
    target.status = "removed"
    target.session_token_hash = None
    await session.commit()
    return target


async def ban_member(session, actor: Member, target: Member) -> Member:
    if not _can_moderate(actor, target):
        raise DomainError("not_allowed", "You can't ban that member.")
    target.status = "banned"
    target.session_token_hash = None
    await session.commit()
    return target


async def set_role(session, actor: Member, target: Member, role: str) -> Member:
    if actor.role != "owner":
        raise DomainError("not_allowed", "Only the owner can change roles.")
    if role not in ("mod", "member"):
        raise DomainError("bad_request", "Role must be 'mod' or 'member'.")
    if target.id == actor.id:
        raise DomainError("bad_request", "The owner's role can't be changed this way.")
    target.role = role
    await session.commit()
    return target


async def rename_member(session, member: Member, new_name: str, settings) -> Member:
    new_name = (new_name or "").strip()
    if not (settings.DISPLAY_NAME_MIN <= len(new_name) <= settings.DISPLAY_NAME_MAX):
        raise DomainError("bad_request", "Name must be 1-24 characters.")
    member.display_name = new_name
    member.is_anonymous = False
    await session.commit()
    return member


async def leave_room(session, member: Member) -> None:
    member.status = "left"
    member.session_token_hash = None
    await session.commit()
