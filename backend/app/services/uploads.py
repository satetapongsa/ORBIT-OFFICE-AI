"""Shared upload handling for documents and task attachments (docs/SECURITY.md §4).

Size is measured while hashing, the type is sniffed from the content, objects are written
under server-generated keys and removed again when the database transaction fails.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import BinaryIO, Protocol

import anyio
from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger
from app.core.storage import ObjectStream
from app.services.documents.files import FileTooLargeError, InspectedFile, inspect_upload

logger = get_logger(__name__)

_READ_CHUNK = 1024 * 1024


class FileStorage(Protocol):
    def put_object(
        self, key: str, fileobj: BinaryIO, *, content_type: str, sha256: str
    ) -> None: ...
    def open_object(self, key: str) -> ObjectStream: ...
    def delete_object(self, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class StoredUpload:
    inspected: InspectedFile
    size_bytes: int
    sha256: str


async def receive_upload(upload: UploadFile, settings: Settings) -> StoredUpload:
    """Hash and size-check the (already spooled) upload, then sniff its type."""
    await upload.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := await upload.read(_READ_CHUNK):
        size += len(chunk)
        if size > settings.upload_max_bytes:
            raise FileTooLargeError(
                f"ไฟล์มีขนาดใหญ่เกิน {settings.upload_max_bytes // (1024 * 1024)} MB"
            )
        digest.update(chunk)
    await upload.seek(0)
    inspected = await anyio.to_thread.run_sync(inspect_upload, upload.file, upload.filename)
    return StoredUpload(inspected=inspected, size_bytes=size, sha256=digest.hexdigest())


async def store_upload(
    storage: FileStorage, key: str, upload: UploadFile, stored: StoredUpload
) -> None:
    try:
        await anyio.to_thread.run_sync(
            lambda: storage.put_object(
                key, upload.file, content_type=stored.inspected.mime_type, sha256=stored.sha256
            )
        )
    except Exception:
        logger.error("storage_put_failed", key=key, exc_info=True)
        raise ServiceUnavailableError("ไม่สามารถบันทึกไฟล์ได้ในขณะนี้ กรุณาลองใหม่ภายหลัง") from None


async def discard_object(storage: FileStorage, key: str) -> None:
    try:
        await anyio.to_thread.run_sync(storage.delete_object, key)
    except Exception:
        logger.warning("storage_cleanup_failed", key=key, exc_info=True)


async def open_object(storage: FileStorage, key: str) -> ObjectStream:
    try:
        return await anyio.to_thread.run_sync(storage.open_object, key)
    except Exception:
        logger.error("storage_get_failed", key=key, exc_info=True)
        raise ServiceUnavailableError("ไม่สามารถดาวน์โหลดไฟล์ได้ในขณะนี้ กรุณาลองใหม่ภายหลัง") from None
