"""Upload inspection: content sniffing, archive safety checks and filename sanitising.

The client's filename and ``Content-Type`` are never trusted to decide the file type: the
type comes from the bytes (magic numbers, archive structure, text decoding) and must agree
with the extension on the allow-list (docs/SECURITY.md §4).
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import BinaryIO

from app.core.errors import AppError
from app.models.document import FileType, ImageType

MIME_TYPES: dict[FileType, str] = {
    FileType.PDF: "application/pdf",
    FileType.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileType.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileType.TXT: "text/plain; charset=utf-8",
}

EXTENSIONS: dict[str, FileType] = {
    ".pdf": FileType.PDF,
    ".docx": FileType.DOCX,
    ".xlsx": FileType.XLSX,
    ".txt": FileType.TXT,
}

# Attachments only (ticket screenshots): never parsed, only stored and downloaded.
IMAGE_MIME_TYPES: dict[ImageType, str] = {
    ImageType.PNG: "image/png",
    ImageType.JPEG: "image/jpeg",
}
IMAGE_EXTENSIONS: dict[str, ImageType] = {
    ".png": ImageType.PNG,
    ".jpg": ImageType.JPEG,
    ".jpeg": ImageType.JPEG,
}
_IMAGE_MAGIC: dict[ImageType, bytes] = {
    ImageType.PNG: b"\x89PNG\r\n\x1a\n",
    ImageType.JPEG: b"\xff\xd8\xff",
}
ATTACHMENT_TYPES_MESSAGE = "รองรับเฉพาะไฟล์ PDF, DOCX, XLSX, TXT, PNG และ JPG"

# Archive (DOCX/XLSX) limits — protect the API and the worker from zip bombs.
MAX_ZIP_ENTRIES = 5_000
MAX_ZIP_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_ZIP_RATIO = 200  # uncompressed / compressed for any single entry

_SNIFF_BYTES = 8192
_MAX_FILENAME_CHARS = 200


class UnsupportedFileError(AppError):
    status_code = 415
    code = "unsupported_file_type"
    message = "รองรับเฉพาะไฟล์ PDF, DOCX, XLSX และ TXT"


class UnsafeFileError(AppError):
    status_code = 422
    code = "unsafe_file"
    message = "ไฟล์นี้มีโครงสร้างที่ไม่ปลอดภัยหรือเสียหาย จึงไม่สามารถรับได้"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"
    message = "ไฟล์มีขนาดใหญ่เกินกำหนด"


class EmptyFileError(AppError):
    status_code = 422
    code = "empty_file"
    message = "ไฟล์ว่างเปล่า"


@dataclass(frozen=True, slots=True)
class InspectedFile:
    file_type: FileType | ImageType
    mime_type: str
    filename: str


def sanitize_filename(raw: str | None, file_type: StrEnum) -> str:
    """A display-safe base name ending in the sniffed type's extension.

    Directory parts, control characters and reserved characters are removed; the result is
    only ever stored as metadata (storage keys are server-generated).
    """
    name = raw or ""
    # Strip any directory part (both separators: browsers on Windows may send full paths).
    name = PureWindowsPath(PurePosixPath(name).name).name
    name = unicodedata.normalize("NFC", name)
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip(" .")
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = stem.strip(" .")[: _MAX_FILENAME_CHARS - 6] or "document"
    return f"{stem}.{file_type.value.lower()}"


def check_zip(fileobj: BinaryIO) -> zipfile.ZipFile:
    """Open an OOXML archive and reject zip bombs and path tricks before any parsing."""
    try:
        archive = zipfile.ZipFile(fileobj)
    except (zipfile.BadZipFile, OSError, ValueError):
        raise UnsafeFileError() from None
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise UnsafeFileError()
    total = 0
    for info in infos:
        if info.flag_bits & 0x1:  # encrypted entry
            raise UnsafeFileError("ไฟล์ถูกเข้ารหัสด้วยรหัสผ่าน กรุณาปลดล็อกก่อนอัปโหลด")
        if info.filename.startswith(("/", "\\")) or ".." in PurePosixPath(info.filename).parts:
            raise UnsafeFileError()
        total += info.file_size
        compressed = max(info.compress_size, 1)
        if info.file_size > 1024 * 1024 and info.file_size / compressed > MAX_ZIP_RATIO:
            raise UnsafeFileError()
    if total > MAX_ZIP_UNCOMPRESSED_BYTES:
        raise UnsafeFileError()
    return archive


def _ooxml_type(fileobj: BinaryIO) -> FileType | None:
    archive = check_zip(fileobj)
    names = set(archive.namelist())
    if "[Content_Types].xml" not in names:
        return None
    if "word/document.xml" in names:
        return FileType.DOCX
    if "xl/workbook.xml" in names:
        return FileType.XLSX
    return None


def decode_text(data: bytes) -> str | None:
    """Decode text: UTF-8 (± BOM), UTF-16 with BOM, then Thai Windows-874.

    Returns ``None`` for binary data.
    """
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if b"\x00" in data:
        return None
    for encoding in ("utf-8-sig", "cp874"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        # Reject data that decodes but is mostly control characters (likely binary).
        controls = sum(
            1 for ch in text if unicodedata.category(ch) == "Cc" and ch not in "\r\n\t\f"
        )
        if text and controls / len(text) > 0.01:
            return None
        return text
    return None


def _looks_like_text(head: bytes) -> bool:
    # A multi-byte UTF-8 character may be cut at the sniff boundary: trim up to 3 bytes.
    for cut in range(4):
        sample = head[: len(head) - cut] if cut else head
        if decode_text(sample) is not None:
            return True
    return False


def inspect_upload(fileobj: BinaryIO, filename: str | None) -> InspectedFile:
    """Decide the file type from content and check it against the extension allow-list."""
    suffix = PurePosixPath(PureWindowsPath(filename or "").name).suffix.lower()
    declared = EXTENSIONS.get(suffix)
    if declared is None:
        raise UnsupportedFileError()

    fileobj.seek(0)
    head = fileobj.read(_SNIFF_BYTES)
    fileobj.seek(0)
    if not head:
        raise EmptyFileError()

    sniffed: FileType | None
    if head.startswith(b"%PDF-"):
        sniffed = FileType.PDF
    elif head.startswith(b"PK\x03\x04"):
        sniffed = _ooxml_type(fileobj)
        fileobj.seek(0)
    elif _looks_like_text(head):
        sniffed = FileType.TXT
    else:
        sniffed = None

    if sniffed is None or sniffed is not declared:
        raise UnsupportedFileError("เนื้อหาไฟล์ไม่ตรงกับนามสกุลไฟล์ หรือไม่ใช่ไฟล์ PDF, DOCX, XLSX หรือ TXT")
    return InspectedFile(
        file_type=sniffed,
        mime_type=MIME_TYPES[sniffed],
        filename=sanitize_filename(filename, sniffed),
    )


def inspect_attachment(fileobj: BinaryIO, filename: str | None) -> InspectedFile:
    """Ticket attachments: the document formats (same checks as :func:`inspect_upload`) or a
    PNG/JPEG image identified by its signature and matching its extension."""
    suffix = PurePosixPath(PureWindowsPath(filename or "").name).suffix.lower()
    image = IMAGE_EXTENSIONS.get(suffix)
    if image is None:
        if suffix not in EXTENSIONS:
            raise UnsupportedFileError(ATTACHMENT_TYPES_MESSAGE)
        return inspect_upload(fileobj, filename)
    fileobj.seek(0)
    head = fileobj.read(16)
    fileobj.seek(0)
    if not head:
        raise EmptyFileError()
    if not head.startswith(_IMAGE_MAGIC[image]):
        raise UnsupportedFileError("เนื้อหาไฟล์ไม่ตรงกับนามสกุลไฟล์ (" + ATTACHMENT_TYPES_MESSAGE + ")")
    return InspectedFile(
        file_type=image,
        mime_type=IMAGE_MIME_TYPES[image],
        filename=sanitize_filename(filename, image),
    )
