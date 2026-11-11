"""Plain-text extraction for PDF, DOCX, XLSX and TXT (runs in the Celery worker).

Each parser works within limits (pages, archive size, output length) and raises
:class:`ExtractionError` with a Thai, user-presentable message. Extracted text is untrusted
data: it is stored as-is (cleaned) and never interpreted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import BinaryIO

from app.models.document import FileType
from app.services.documents.files import UnsafeFileError, check_zip, decode_text

MAX_TEXT_CHARS = 2_000_000
MAX_PDF_PAGES = 2_000
MAX_XLSX_CELLS = 2_000_000


class ExtractionError(Exception):
    """Expected failure; ``message`` is shown to users."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    text: str
    page_count: int | None
    truncated: bool


_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\x00", ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_SPACE.sub("\n", text)
    return _BLANK_LINES.sub("\n\n", text).strip()


def _pdf(stream: BinaryIO) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(stream, strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("ไฟล์ PDF ถูกป้องกันด้วยรหัสผ่าน จึงอ่านข้อความไม่ได้")
        pages = len(reader.pages)
        if pages > MAX_PDF_PAGES:
            raise ExtractionError(f"ไฟล์ PDF มีมากกว่า {MAX_PDF_PAGES:,} หน้า")
        parts: list[str] = []
        size = 0
        for page in reader.pages:
            chunk = page.extract_text() or ""
            parts.append(chunk)
            size += len(chunk)
            if size > MAX_TEXT_CHARS:
                break
        # Form feeds mark page boundaries (page numbers in citations, Phase 7).
        return "\f".join(parts), pages
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError):
        raise ExtractionError("ไฟล์ PDF เสียหายหรืออ่านไม่ได้") from None


def _docx(stream: BinaryIO) -> str:
    import docx

    check_zip(stream)
    stream.seek(0)
    try:
        document = docx.Document(stream)
    except Exception:
        raise ExtractionError("ไฟล์ DOCX เสียหายหรืออ่านไม่ได้") from None
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _xlsx(stream: BinaryIO) -> str:
    import openpyxl

    check_zip(stream)
    stream.seek(0)
    try:
        workbook = openpyxl.load_workbook(stream, read_only=True, data_only=True)
    except Exception:
        raise ExtractionError("ไฟล์ XLSX เสียหายหรืออ่านไม่ได้") from None
    parts: list[str] = []
    cells = 0
    size = 0
    try:
        for sheet in workbook.worksheets:
            parts.append(f"## {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                values = ["" if v is None else str(v) for v in row]
                cells += len(values)
                if cells > MAX_XLSX_CELLS:
                    raise ExtractionError("ไฟล์ XLSX มีข้อมูลมากเกินกว่าที่ระบบรองรับ")
                line = "\t".join(values).rstrip("\t")
                if line:
                    parts.append(line)
                    size += len(line)
                if size > MAX_TEXT_CHARS:
                    return "\n".join(parts)
    finally:
        workbook.close()
    return "\n".join(parts)


def _txt(stream: BinaryIO) -> str:
    text = decode_text(stream.read())
    if text is None:
        raise ExtractionError("ไม่สามารถอ่านไฟล์ข้อความได้ (รองรับ UTF-8, UTF-16 และ TIS-620)")
    return text


def extract_text(stream: BinaryIO, file_type: FileType) -> ExtractionResult:
    stream.seek(0)
    page_count: int | None = None
    try:
        if file_type is FileType.PDF:
            raw, page_count = _pdf(stream)
        elif file_type is FileType.DOCX:
            raw = _docx(stream)
        elif file_type is FileType.XLSX:
            raw = _xlsx(stream)
        else:
            raw = _txt(stream)
    except UnsafeFileError as exc:
        raise ExtractionError(exc.message) from None
    text = clean_text(raw)
    truncated = len(text) > MAX_TEXT_CHARS
    return ExtractionResult(text=text[:MAX_TEXT_CHARS], page_count=page_count, truncated=truncated)
