"""Sample files, in-memory storage and an inline processor for Document Center tests."""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

import anyio
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.storage import ObjectStream
from app.services.documents.processing import process_version

THAI_TEXT = "นโยบายการลาพักร้อน AURA ปี 2569\nพนักงานลาได้ 10 วันต่อปี"


def make_pdf(text: str = "AURA leave policy 2026") -> bytes:
    """A minimal valid one-page PDF with an ASCII text layer."""
    content = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def make_docx(paragraphs: list[str] | None = None) -> bytes:
    import docx

    document = docx.Document()
    for line in paragraphs or ["คู่มือพนักงาน", "บทที่ 1 การเข้างาน"]:
        document.add_paragraph(line)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "วันลา"
    table.rows[0].cells[1].text = "10"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_xlsx() -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "งบประมาณ"
    sheet.append(["รายการ", "จำนวน"])
    sheet.append(["คอมพิวเตอร์", 12])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def make_zip_bomb() -> bytes:
    """Looks like a DOCX, but one entry inflates ~10 MB of zeros (ratio far above the limit)."""
    return make_zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"\0" * (10 * 1024 * 1024),
        }
    )


def make_broken_docx() -> bytes:
    """Passes sniffing (right archive layout) but is not a readable Word document."""
    return make_zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"not xml"})


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False

    def iter_chunks(self, size: int) -> Iterator[bytes]:
        for i in range(0, len(self._data), size):
            yield self._data[i : i + size]

    def close(self) -> None:
        self.closed = True


@dataclass
class MemoryStorage:
    objects: dict[str, bytes] = field(default_factory=dict)
    content_types: dict[str, str] = field(default_factory=dict)
    fail_puts: bool = False

    def put_object(self, key: str, fileobj: BinaryIO, *, content_type: str, sha256: str) -> None:
        if self.fail_puts:
            raise OSError("storage down")
        fileobj.seek(0)
        self.objects[key] = fileobj.read()
        self.content_types[key] = content_type

    def open_object(self, key: str) -> ObjectStream:
        return ObjectStream(_Body(self.objects[key]))

    def download_to(self, key: str, fileobj: BinaryIO) -> None:
        fileobj.write(self.objects[key])
        fileobj.seek(0)

    def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)


@dataclass
class InlineProcessor:
    """Runs the real extraction pipeline synchronously (in a thread) against the test DB."""

    engine: Engine
    storage: MemoryStorage
    run: bool = True
    queued: list[tuple[uuid.UUID, bool]] = field(default_factory=list)

    async def enqueue(self, version_id: uuid.UUID, *, force: bool = False) -> None:
        self.queued.append((version_id, force))
        if self.run:
            await anyio.to_thread.run_sync(self.process, version_id, force)

    def process(self, version_id: uuid.UUID, force: bool = False) -> str:
        with Session(self.engine, expire_on_commit=False) as session:
            return process_version(session, self.storage, version_id, force=force)
