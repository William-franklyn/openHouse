"""SQLAlchemy models for the data model in SPEC.md section 6.

Deliberately avoids Postgres-only column types (no ARRAY/JSONB, no native
DB enums) so the exact same models work against SQLite in tests and
against real PostgreSQL in production via DATABASE_URL.
"""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return uuid.uuid4().hex


def new_video_room_token() -> str:
    # Vestigial: originally a Jitsi Meet room name (now removed in favor
    # of self-hosted WebRTC calls, which don't need this). Left as-is
    # rather than migrating it away - it's inert, and dropping a column
    # isn't worth a production migration for something unused.
    return secrets.token_hex(16)


def utcnow() -> datetime:
    """Naive UTC on purpose: SQLite (used in tests) silently drops tzinfo
    on datetime round-trips, so comparing a tz-aware "now" against a value
    just read back from SQLite raises TypeError. Postgres (production)
    handles aware datetimes fine, but there's no upside to being aware in
    one dialect and naive in the other - so everything in this app is
    naive UTC, consistently. See to_naive_utc() for normalizing input that
    arrives with an explicit offset (e.g. from a browser's toISOString())."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class Base(DeclarativeBase):
    pass


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    join_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    invite_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    owner_member_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_recovery_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    video_room_token: Mapped[str] = mapped_column(String(32), nullable=False, default=new_video_room_token)
    # Set when the owner turns on Local mode: the public IP their own
    # request arrived from at that moment (see client_ip() in main.py -
    # read from X-Forwarded-For behind a proxy). Null = off. Deliberately
    # IP-only, not GPS - this never asks anyone for their location, which
    # would be a real identifying signal in an app built around staying
    # anonymous (see SPEC.md Decisions).
    local_mode_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    members: Mapped[list["Member"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    channels: Mapped[list["Channel"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )

    def is_active(self) -> bool:
        if self.deleted_at is not None:
            return False
        if self.ends_at is not None and self.ends_at <= utcnow():
            return False
        return True


class Member(Base):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(24), nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    session_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    device_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    invited_by_member_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)

    room: Mapped["Room"] = relationship(back_populates="members")


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    next_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)

    room: Mapped["Room"] = relationship(back_populates="channels")

    __table_args__ = (UniqueConstraint("room_id", "name", name="uq_channel_room_name"),)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    member_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)

    __table_args__ = (UniqueConstraint("channel_id", "seq", name="uq_message_channel_seq"),)


class Pin(Base):
    __tablename__ = "pins"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("room_id", "message_id", name="uq_pin_room_message"),)


class FileAsset(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(128), nullable=False)
    filename: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class Invite(Base):
    __tablename__ = "invites"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    created_by_member_id: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    used_by_member_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    reporter_member_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_member_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="chess")
    white_member_id: Mapped[str] = mapped_column(String(32), nullable=False)
    black_member_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Append-only log of UCI moves ("e2e4", "e7e5", ...), same spirit as
    # the messages table's seq'd log - the board is always a replay of
    # this list from the standard starting position, never a separately
    # stored snapshot that could drift from it.
    moves_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)
    termination: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class MetricDaily(Base):
    __tablename__ = "metrics_daily"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # "YYYY-MM-DD"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
