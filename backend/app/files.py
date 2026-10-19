"""File uploads/downloads against S3-compatible storage.

README section 8 describes a client-direct-to-S3 presigned-upload flow
(`POST /rooms/{id}/files` returns a signed PUT URL, then `POST
/files/{fid}/complete`). We simplify to a single multipart upload
through our own server instead (same pattern as our other project,
Hotspot Hangout) — see README Decisions for why: it's one request
instead of two, and it's what we can actually exercise in tests without
a frontend driving a real presigned PUT. Downloads still go through a
genuine short-lived presigned GET URL, which is the part that actually
benefits from bypassing our server.
"""

import asyncio
import re

import boto3
from botocore.client import Config

from app.errors import DomainError
from app.models import FileAsset, Member, new_id, utcnow


def sanitize_filename(name: str) -> str:
    name = str(name or "file")
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r'[\x00-\x1f\x7f"]', "", name).strip()
    if not name:
        name = "file"
    return name[:100]


class Storage:
    def __init__(self, settings):
        self.bucket = settings.S3_BUCKET
        kwargs = dict(
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4"),
        )
        # Omit endpoint_url entirely when unset: moto's mock_aws() only
        # intercepts calls to the default AWS endpoints, so passing a
        # custom one (even in tests, where nothing is listening on it)
        # makes boto3 attempt a real, slowly-timing-out connection.
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        self.client = boto3.client("s3", **kwargs)
        # Deliberately no network call here - constructing a Storage must
        # stay cheap and side-effect-free, since app/main.py builds one at
        # import time for ASGI auto-discovery (e.g. Vercel/uvicorn looking
        # for a top-level `app`). The real bucket-exists check runs once,
        # asynchronously, from the app's lifespan startup instead - see
        # ensure_bucket() and its caller in main.py.

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except Exception:
                pass

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get_bytes(self, key: str) -> bytes:
        def _get():
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()

        return await asyncio.to_thread(_get)

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            pass

    def presigned_get_url(self, key: str, filename: str, expires_seconds: int = 300) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires_seconds,
        )


def file_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


async def upload_file(
    session,
    settings,
    storage: Storage,
    room,
    member: Member,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> FileAsset:
    size = len(data)
    if size > settings.MAX_FILE_BYTES:
        raise DomainError("file_too_large", "File is too large.")

    ext = file_extension(filename)
    if ext not in settings.ALLOWED_FILE_EXTENSIONS:
        raise DomainError("file_type", "That file type isn't allowed.")

    display_name = sanitize_filename(filename)
    file_id = new_id()
    storage_key = f"{room.id}/{file_id}-{display_name}"
    await storage.put(storage_key, data, content_type or "application/octet-stream")

    asset = FileAsset(
        id=file_id,
        room_id=room.id,
        member_id=member.id,
        storage_key=storage_key,
        filename=display_name,
        size=size,
        mime=content_type or "application/octet-stream",
        created_at=utcnow(),
    )
    session.add(asset)
    await session.commit()
    return asset


async def get_file_or_404(session, room_id: str, file_id: str) -> FileAsset:
    asset = await session.get(FileAsset, file_id)
    if asset is None or asset.room_id != room_id:
        raise DomainError("bad_request", "File not found.")
    return asset


def download_url(storage: Storage, asset: FileAsset, expires_seconds: int = 300) -> str:
    return storage.presigned_get_url(asset.storage_key, asset.filename, expires_seconds)
