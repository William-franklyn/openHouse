"""Daily, count-only product metrics. Never message content.

Tracks: rooms created, joins (named vs anonymous), messages sent, files
shared, ownership handovers, and (via get_room_lifetimes) how long Rooms
stay active.
"""

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models import MetricDaily, utcnow


def today() -> str:
    return utcnow().strftime("%Y-%m-%d")


def _increment_stmt(day: str, name: str, by: int):
    return (
        update(MetricDaily)
        .where(MetricDaily.day == day, MetricDaily.name == name)
        .values(value=MetricDaily.value + by)
    )


async def bump(session, name: str, by: int = 1, day: str | None = None) -> None:
    """Concurrent callers can bump the same (day, name) counter at once
    (e.g. two messages sent in parallel), so this can't be a plain
    SELECT-then-INSERT-or-UPDATE - two concurrent SELECTs can both see "no
    row yet" and both try to INSERT, and the second one hits the unique
    constraint. Try the atomic UPDATE first (single statement, safe under
    concurrency on both SQLite and Postgres); only INSERT if no row
    existed yet, and if THAT loses a race, fall back to the UPDATE."""
    day = day or today()

    result = await session.execute(_increment_stmt(day, name, by))
    if result.rowcount:
        await session.commit()
        return

    session.add(MetricDaily(day=day, name=name, value=by))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await session.execute(_increment_stmt(day, name, by))
        await session.commit()


async def list_metrics(session, days: int = 14) -> list[dict]:
    result = await session.execute(
        select(MetricDaily).order_by(MetricDaily.day.desc()).limit(days * 10)
    )
    return [{"day": r.day, "name": r.name, "value": r.value} for r in result.scalars().all()]
