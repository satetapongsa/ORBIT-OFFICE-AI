"""S3-compatible object storage client (MinIO in development, any S3 API in production).

boto3 is synchronous; async callers must use ``anyio.to_thread.run_sync``.
Document upload/download operations are added in Phase 4 on top of this client.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


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

    def ensure_bucket(self) -> bool:
        """Create the bucket in development if it does not exist. Returns True if it exists."""
        try:
            self.check_bucket()
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NoSuchBucket", "NotFound"} or not self._auto_create:
                raise
        self._client.create_bucket(Bucket=self.bucket)
        logger.info("storage_bucket_created", bucket=self.bucket)
        return True


@lru_cache
def get_storage() -> ObjectStorage:
    return ObjectStorage(get_settings())
