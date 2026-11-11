"""Upload inspection and text extraction (no database needed)."""

from __future__ import annotations

import io

import pytest

from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.document import AccessLevel, FileType
from app.services.documents.extraction import ExtractionError, clean_text, extract_text
from app.services.documents.files import (
    UnsafeFileError,
    UnsupportedFileError,
    check_zip,
    decode_text,
    inspect_upload,
    sanitize_filename,
)
from app.services.documents.service import capabilities_for
from tests.document_support import (
    THAI_TEXT,
    make_broken_docx,
    make_docx,
    make_pdf,
    make_xlsx,
    make_zip,
    make_zip_bomb,
)


@pytest.mark.parametrize(
    ("raw", "file_type", "expected"),
    [
        ("รายงาน ประจำปี.pdf", FileType.PDF, "รายงาน ประจำปี.pdf"),
        ("../../etc/passwd.txt", FileType.TXT, "passwd.txt"),
        ("C:\\Users\\me\\Desktop\\งบ.xlsx", FileType.XLSX, "งบ.xlsx"),
        ('bad<>:"|?*name.docx', FileType.DOCX, "bad_______name.docx"),
        ("evil\x00\x1b[31m.txt", FileType.TXT, "evil[31m.txt"),
        ("noext", FileType.PDF, "noext.pdf"),
        ("report.PDF.exe", FileType.PDF, "report.PDF.pdf"),  # extension follows the content
        ("", FileType.TXT, "document.txt"),
        (None, FileType.TXT, "document.txt"),
        ("ก" * 400 + ".txt", FileType.TXT, "ก" * 194 + ".txt"),
    ],
)
def test_sanitize_filename(raw: str | None, file_type: FileType, expected: str) -> None:
    assert sanitize_filename(raw, file_type) == expected


def test_decode_text_encodings() -> None:
    assert decode_text(THAI_TEXT.encode()) == THAI_TEXT
    assert decode_text(b"\xef\xbb\xbf" + THAI_TEXT.encode()) == THAI_TEXT  # UTF-8 BOM
    assert decode_text(THAI_TEXT.encode("utf-16")) == THAI_TEXT
    assert decode_text(THAI_TEXT.encode("cp874")) == THAI_TEXT  # TIS-620 / Windows-874
    assert decode_text(b"MZ\x90\x00\x03") is None
    assert decode_text(bytes(range(1, 32)) * 10) is None  # control characters


@pytest.mark.parametrize(
    ("name", "data", "expected"),
    [
        ("a.pdf", make_pdf(), FileType.PDF),
        ("a.docx", make_docx(), FileType.DOCX),
        ("a.xlsx", make_xlsx(), FileType.XLSX),
        ("a.TXT", THAI_TEXT.encode(), FileType.TXT),
    ],
)
def test_inspect_upload_accepts_matching_content(
    name: str, data: bytes, expected: FileType
) -> None:
    result = inspect_upload(io.BytesIO(data), name)
    assert result.file_type is expected
    assert result.filename.endswith(f".{expected.value.lower()}")


def test_text_cut_inside_a_thai_character_still_sniffs_as_text() -> None:
    data = ("ก" * 3000).encode()  # 3 bytes per character; the 8 KiB sniff cuts one in half
    assert inspect_upload(io.BytesIO(data), "a.txt").file_type is FileType.TXT


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("a.zip", make_docx()),
        ("a.docx", make_zip({"hello.txt": b"hi"})),  # zip but not OOXML
        ("a.pdf", b"not a pdf"),
        ("a.txt", b"\x00\x01binary"),
    ],
)
def test_inspect_upload_rejects_mismatches(name: str, data: bytes) -> None:
    with pytest.raises(UnsupportedFileError):
        inspect_upload(io.BytesIO(data), name)


def test_zip_guards() -> None:
    with pytest.raises(UnsafeFileError):
        check_zip(io.BytesIO(make_zip_bomb()))
    with pytest.raises(UnsafeFileError):
        check_zip(io.BytesIO(make_zip({"../escape.xml": b"x"})))
    with pytest.raises(UnsafeFileError):
        check_zip(io.BytesIO(b"PK\x03\x04 truncated"))


def test_extraction_and_cleaning() -> None:
    assert clean_text("a\r\n\r\n\r\n\r\nb  \n\x00c") == "a\n\nb\nc"
    pdf = extract_text(io.BytesIO(make_pdf("Hello")), FileType.PDF)
    assert pdf.text == "Hello"
    assert pdf.page_count == 1
    xlsx = extract_text(io.BytesIO(make_xlsx()), FileType.XLSX)
    assert xlsx.text.splitlines()[0] == "## งบประมาณ"
    with pytest.raises(ExtractionError, match="DOCX"):
        extract_text(io.BytesIO(make_broken_docx()), FileType.DOCX)
    with pytest.raises(ExtractionError, match="PDF"):
        extract_text(io.BytesIO(b"%PDF-1.4 garbage"), FileType.PDF)


def _user(*perms: str) -> CurrentUser:
    import uuid

    return CurrentUser(
        id=uuid.uuid4(),
        email="u@example.com",
        display_name="u",
        department_id=None,
        role_ids=frozenset(),
        role_codes=frozenset(),
        permissions=frozenset(perms),
    )


def test_capabilities() -> None:
    employee = _user(P.DOCUMENTS_READ, P.DOCUMENTS_UPLOAD)
    view = capabilities_for(employee, AccessLevel.VIEW)
    assert not any(view.model_dump().values())
    edit = capabilities_for(employee, AccessLevel.EDIT)
    assert (edit.can_edit, edit.can_upload_version, edit.can_manage) == (True, True, False)
    owner = capabilities_for(employee, AccessLevel.MANAGE)
    assert owner.can_manage_access and owner.can_view_history and not owner.can_delete
    records_officer = capabilities_for(
        _user(P.DOCUMENTS_READ, P.DOCUMENTS_MANAGE_ACCESS), AccessLevel.VIEW
    )
    assert records_officer.can_manage_access and not records_officer.can_edit
    auditor = capabilities_for(_user(P.DOCUMENTS_READ, P.AUDIT_READ), AccessLevel.VIEW)
    assert auditor.can_view_history and not auditor.can_manage_access
    admin = capabilities_for(_user(*[p.value for p in P]), AccessLevel.MANAGE)
    assert all(admin.model_dump().values())
