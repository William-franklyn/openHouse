"""All tunable knobs in one place.

Renaming the product later ("Openhouse" -> something else, "Room" -> something
else) should be a one-line env change: APP_NAME, ROOM_WORD, APP_URL.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Naming (see README naming note) ----
    APP_NAME: str = "Openhouse"
    ROOM_WORD: str = "Room"
    APP_URL: str = "http://localhost:3000"

    # ---- Infra ----
    # Real deployments point this at Postgres (e.g.
    # postgresql+asyncpg://user:pass@host/db). Tests override it to an
    # aiosqlite URL so the suite doesn't need a running Postgres server.
    DATABASE_URL: str = "postgresql+asyncpg://openhouse:openhouse@localhost:5432/openhouse"
    REDIS_URL: str = "redis://localhost:6379/0"

    S3_ENDPOINT_URL: str | None = "http://localhost:9000"
    S3_BUCKET: str = "openhouse-files"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_REGION: str = "us-east-1"

    ADMIN_TOKEN: str = "change-me"

    # ---- Room codes / invites / recovery ----
    ROOM_CODE_ALPHABET: str = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    ROOM_CODE_LENGTH: int = 5
    RECOVERY_CODE_LENGTH: int = 12
    INVITE_TTL_SECONDS: int = 15 * 60

    # ---- Content limits ----
    ROOM_NAME_MIN: int = 3
    ROOM_NAME_MAX: int = 40
    DISPLAY_NAME_MIN: int = 1
    DISPLAY_NAME_MAX: int = 24
    MESSAGE_MIN: int = 1
    MESSAGE_MAX: int = 2000
    MAX_EXTRA_CHANNELS: int = 10
    MAX_PINS: int = 3
    HISTORY_PAGE_SIZE: int = 50

    # Vercel Functions hard-cap request bodies at 4.5 MB - files between
    # that and any higher app-level limit would never even reach this
    # validation (the platform rejects the request before invoking the
    # function), so this has to stay safely under that ceiling.
    MAX_FILE_BYTES: int = 4 * 1024 * 1024
    ALLOWED_FILE_EXTENSIONS: tuple = (
        "png", "jpg", "jpeg", "gif", "webp",
        "pdf", "doc", "docx", "txt", "odt",
        "zip", "webm", "mp3", "wav", "ogg", "m4a",
    )

    # ---- Room DJ ----
    # Narrower than ALLOWED_FILE_EXTENSIONS above - stops start_music from
    # being pointed at an uploaded .pdf's file_id.
    MUSIC_EXTENSIONS: tuple = ("mp3", "wav", "ogg", "m4a", "webm")
    # Safety net: if stop_music never fires (crash, etc.), the Redis key
    # expires on its own rather than leaving "now playing" stuck forever.
    ROOM_MUSIC_TTL_SECONDS: int = 600

    # ---- Video calls ----
    # Safety net matching ROOM_MUSIC_TTL_SECONDS above - disconnect cleanup
    # handles the normal case, this just bounds how long a call's presence
    # keys can possibly survive a crash/bug in that cleanup path.
    CALL_TTL_SECONDS: int = 600
    # STUN alone only works when at least one peer is reachable directly -
    # it does nothing for two people each behind a restrictive/symmetric
    # NAT (the common "different networks" case). TURN relays the actual
    # media when no direct path exists. None disables it (falls back to
    # STUN-only) - local dev doesn't need a real Metered account.
    METERED_API_KEY: str | None = None
    METERED_SUBDOMAIN: str = "openhouse"

    # ---- Games ----
    # Safety net matching CALL_TTL_SECONDS above - bounds how long a
    # spectator's "watching" presence can survive a crash/bug in the
    # disconnect cleanup path. The game itself isn't TTL'd (it lives in
    # Postgres, not Redis) - only who's currently watching it live is.
    GAME_WATCH_TTL_SECONDS: int = 600

    # ---- Rate limits ----
    MESSAGE_RATE_LIMIT: int = 10
    MESSAGE_RATE_WINDOW_SECONDS: int = 10
    JOIN_RATE_LIMIT: int = 10
    JOIN_RATE_WINDOW_SECONDS: int = 60
    RECOVERY_RATE_LIMIT: int = 5
    RECOVERY_RATE_WINDOW_SECONDS: int = 60
    UPLOAD_RATE_LIMIT: int = 5
    UPLOAD_RATE_WINDOW_SECONDS: int = 60

    # ---- Cleanup ----
    DELETED_ROOM_CLEANUP_HOURS: int = 24
    REPORT_RETENTION_DAYS: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
