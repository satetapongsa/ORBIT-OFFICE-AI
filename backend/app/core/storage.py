"""S3-compatible object storage client (MinIO in development, any S3 API in production).

boto3 is synchronous; async callers must use ``anyio.to_thread.run_sync``.
The bucket is private: objects are only reachable through the API after an ACL check.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any, BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ObjectStream:
    """Chunk iterator over an S3 response body; always closes the connection."""

    def __init__(self, body: Any, chunk_size: int = 64 * 1024) -> None:
        self._body = body
        self._chunk_size = chunk_size

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._body.iter_chunks(self._chunk_size)
        finally:
            self._body.close()

    def close(self) -> None:
        self._body.close()


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    last_modified: datetime


class ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.storage_bucket
        self._auto_create = settings.storage_auto_create_bucket and not settings.is_production
        timeout = settings.health_check_timeout_seconds
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint_url,
            region_name=settings.storage_region,
            aws_access_key_id=settings.storage_access_key.get_secret_value(),
            aws_secret_access_key=settings.storage_secret_key.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=timeout,
                read_timeout=max(timeout, 30),
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    def check_bucket(self) -> None:
        """Raise if the bucket is unreachable or missing."""
        self._client.head_bucket(Bucket=self.bucket)

    def ensure_bucket(self, *, create: bool | None = None) -> bool:
        """Create the bucket if it does not exist. Returns True if it exists.

        By default only development creates it automatically; ``create=True`` is the explicit
        deploy step (``python -m app.cli ensure-bucket``) for production."""
        allowed = self._auto_create if create is None else create
        try:
            self.check_bucket()
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NoSuchBucket", "NotFound"} or not allowed:
                raise
        self._client.create_bucket(Bucket=self.bucket)
        logger.info("storage_bucket_created", bucket=self.bucket)
        return True

    # --- Objects ---------------------------------------------------------------------

    def put_object(self, key: str, fileobj: BinaryIO, *, content_type: str, sha256: str) -> None:
        fileobj.seek(0)
        self._client.upload_fileobj(
            fileobj,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type, "Metadata": {"sha256": sha256}},
        )

    def download_to(self, key: str, fileobj: BinaryIO) -> None:
        self._client.download_fileobj(self.bucket, key, fileobj)
        fileobj.seek(0)

    def open_object(self, key: str) -> ObjectStream:
        """Open an object for streaming. Errors (missing object, storage down) raise here,
        before any response bytes are sent."""
        return ObjectStream(self._client.get_object(Bucket=self.bucket, Key=key)["Body"])

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def iter_objects(self, prefix: str = "") -> Iterator[StoredObject]:
        """Every object in the bucket (paginated), for clean-up jobs and backups."""
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                yield StoredObject(
                    key=item["Key"], size=int(item["Size"]), last_modified=item["LastModified"]
                )

    def put_bytes(self, key: str, fileobj: BinaryIO, *, content_type: str) -> None:
        """Restore an object as-is (backups); uploads use :meth:`put_object`."""
        self._client.upload_fileobj(
            fileobj, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )


@lru_cache
def get_storage() -> ObjectStorage:
    return ObjectStorage(get_settings())
