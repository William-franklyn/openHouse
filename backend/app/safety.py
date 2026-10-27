"""Rate limiting and reports.

Rate limiting is a plain fixed-window counter in Redis (INCR + EXPIRE on
first hit). It's not as smooth as a sliding window, but it's simple,
correct for SPEC.md's "N per M seconds" limits, and works identically
against real Redis or fakeredis in tests.
"""

from app.errors import DomainError
from app.models import Report, new_id, utcnow


async def check_rate_limit(redis, key: str, limit: int, window_seconds: int) -> None:
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
    if current > limit:
        raise DomainError("rate_limited", "Too many requests - slow down and try again.")


async def check_message_rate(redis, settings, member_id: str) -> None:
    await check_rate_limit(
        redis,
        f"rl:msg:{member_id}",
        settings.MESSAGE_RATE_LIMIT,
        settings.MESSAGE_RATE_WINDOW_SECONDS,
    )


async def check_join_rate(redis, settings, ip: str) -> None:
    await check_rate_limit(
        redis, f"rl:join:{ip}", settings.JOIN_RATE_LIMIT, settings.JOIN_RATE_WINDOW_SECONDS
    )


async def check_upload_rate(redis, settings, member_id: str) -> None:
    await check_rate_limit(
        redis,
        f"rl:upload:{member_id}",
        settings.UPLOAD_RATE_LIMIT,
        settings.UPLOAD_RATE_WINDOW_SECONDS,
    )


async def check_recovery_rate(redis, settings, ip: str) -> None:
    await check_rate_limit(
        redis,
        f"rl:recover:{ip}",
        settings.RECOVERY_RATE_LIMIT,
        settings.RECOVERY_RATE_WINDOW_SECONDS,
    )


async def create_report(
    session,
    room_id: str,
    reporter_member_id: str,
    reason: str,
    target_member_id: str | None = None,
    message_id: str | None = None,
) -> Report:
    if not reason or not reason.strip():
        raise DomainError("bad_request", "A report needs a reason.")
    report = Report(
        id=new_id(),
        room_id=room_id,
        reporter_member_id=reporter_member_id,
        target_member_id=target_member_id,
        message_id=message_id,
        reason=reason.strip()[:1000],
        status="open",
        created_at=utcnow(),
    )
    session.add(report)
    await session.commit()
    return report
