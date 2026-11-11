"""Excel and PDF exports of the analytics overview (Phase 8).

The data comes from :mod:`app.services.analytics`, so an export never contains more than the
caller may analyse. Text from users (titles, names) is escaped for HTML and forced to plain text
in spreadsheets (no formula injection). PDFs are rendered with WeasyPrint (HarfBuzz shaping,
TLWG Thai fonts in the image).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.principal import CurrentUser
from app.models.task import TaskStatus
from app.repositories import analytics as repo
from app.repositories.task_access import visible_tasks_condition
from app.repositories.tickets import visible_tickets_condition
from app.schemas.analytics import AnalyticsOverview, AnalyticsScope
from app.services import analytics
from app.services.tasks.service import STATUS_LABELS as TASK_STATUS
from app.services.tickets.service import CATEGORY_LABELS
from app.services.tickets.service import STATUS_LABELS as TICKET_STATUS

MAX_ROWS = 2000  # rows per list in one export
PDF_LIST_ROWS = 100

PRIORITY = {"LOW": "ต่ำ", "MEDIUM": "ปานกลาง", "HIGH": "สูง", "URGENT": "ด่วนที่สุด"}
DOC_CATEGORY = {
    "POLICY": "นโยบาย",
    "PROCEDURE": "ขั้นตอนการปฏิบัติงาน",
    "FORM": "แบบฟอร์ม",
    "REPORT": "รายงาน",
    "CONTRACT": "สัญญา",
    "MANUAL": "คู่มือ",
    "OTHER": "อื่นๆ",
}


@dataclass(frozen=True, slots=True)
class ReportData:
    overview: AnalyticsOverview
    tasks: list[dict[str, Any]]
    tickets: list[dict[str, Any]]


def _local(value: datetime | None, tz: str) -> str:
    return value.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M") if value else ""


def _task_status(key: str) -> str:
    try:
        return TASK_STATUS[TaskStatus(key)]
    except ValueError:
        return key


def _ticket_status(key: str) -> str:
    from app.models.ticket import TicketStatus

    try:
        return TICKET_STATUS[TicketStatus(key)]
    except ValueError:
        return key


def _ticket_category(key: str) -> str:
    from app.models.ticket import TicketCategory

    try:
        return CATEGORY_LABELS[TicketCategory(key)]
    except ValueError:
        return key


async def collect(
    session: AsyncSession,
    settings: Settings,
    user: CurrentUser,
    scope: AnalyticsScope,
    date_from: Any,
    date_to: Any,
) -> ReportData:
    data = await analytics.overview(session, settings, user, scope, date_from, date_to)
    flt = analytics.resolve_scope(user, scope)
    period = analytics.resolve_period(settings, date_from, date_to)
    tz = settings.app_timezone
    tasks = [
        {
            "title": task.title,
            "status": _task_status(task.status),
            "priority": PRIORITY.get(task.priority, task.priority),
            "assignees": names or "",
            "due": _local(task.due_at, tz),
            "created": _local(task.created_at, tz),
            "completed": _local(task.completed_at, tz),
        }
        for task, names in await repo.task_rows(
            session, flt, visible_tasks_condition(user), period.start, period.end, limit=MAX_ROWS
        )
    ]
    tickets = [
        {
            "number": ticket.ticket_number,
            "title": ticket.title,
            "category": _ticket_category(ticket.category),
            "priority": PRIORITY.get(ticket.priority, ticket.priority),
            "status": _ticket_status(ticket.status),
            "requester": requester or "",
            "assignee": assignee or "",
            "created": _local(ticket.created_at, tz),
            "resolved": _local(ticket.resolved_at, tz),
        }
        for ticket, requester, assignee in await repo.ticket_rows(
            session, flt, visible_tickets_condition(user), period.start, period.end, limit=MAX_ROWS
        )
    ]
    return ReportData(overview=data, tasks=tasks, tickets=tickets)


def _kpis(o: AnalyticsOverview) -> list[tuple[str, Any]]:
    rate = f"{o.tasks.completion_rate * 100:.0f}%" if o.tasks.completion_rate is not None else "—"
    return [
        ("งานที่ยังไม่เสร็จ", o.tasks.open),
        ("งานเลยกำหนด", o.tasks.overdue),
        ("งานที่สร้างในช่วงนี้", o.tasks.created),
        ("งานที่เสร็จในช่วงนี้", o.tasks.completed),
        ("อัตราการปิดงาน", rate),
        (
            "เวลาเฉลี่ยจนงานเสร็จ (ชั่วโมง)",
            o.tasks.avg_completion_hours if o.tasks.avg_completion_hours is not None else "—",
        ),
        ("แจ้งปัญหาไอทีที่ยังเปิดอยู่", o.tickets.open),
        ("แจ้งปัญหาใหม่ในช่วงนี้", o.tickets.opened),
        ("แก้ไขแล้วในช่วงนี้", o.tickets.resolved),
        (
            "เวลาเฉลี่ยในการแก้ไข (ชั่วโมง)",
            o.tickets.avg_resolution_hours if o.tickets.avg_resolution_hours is not None else "—",
        ),
        ("เอกสารทั้งหมด", o.documents.total),
        ("เอกสารที่อัปโหลดในช่วงนี้", o.documents.uploaded),
    ]


def _title(o: AnalyticsOverview) -> str:
    where = analytics.SCOPE_LABELS[o.scope]
    if o.department is not None:
        where += f" ({o.department.name})"
    return f"รายงานภาพรวม AURA OFFICE AI — {where}"


def filename(o: AnalyticsOverview, ext: str) -> str:
    return f"aura-report-{o.scope}-{o.date_from.isoformat()}-{o.date_to.isoformat()}.{ext}"


# --- Excel --------------------------------------------------------------------------------


def to_xlsx(report: ReportData) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    o = report.overview
    book = Workbook()

    def sheet(title: str, header: list[str], rows: list[list[Any]], first: bool = False) -> None:
        ws = book.active if first else book.create_sheet()
        assert ws is not None  # noqa: S101
        ws.title = title
        ws.append(header)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append(row)
        for row_cells in ws.iter_rows(min_row=2):
            for cell in row_cells:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.data_type = "s"  # never a formula
        for column in ws.columns:
            width = max((len(str(c.value or "")) for c in column), default=8)
            ws.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 60)

    summary_rows: list[list[Any]] = [
        ["รายงาน", _title(o)],
        ["ช่วงเวลา", f"{o.date_from.isoformat()} ถึง {o.date_to.isoformat()} ({o.timezone})"],
        [],
        *[[k, v] for k, v in _kpis(o)],
    ]
    sheet("สรุป", ["หัวข้อ", "ค่า"], summary_rows, first=True)
    sheet(
        "งาน",
        ["ชื่องาน", "สถานะ", "ความสำคัญ", "ผู้รับผิดชอบ", "กำหนดส่ง", "สร้างเมื่อ", "เสร็จเมื่อ"],
        [
            [
                t["title"],
                t["status"],
                t["priority"],
                t["assignees"],
                t["due"],
                t["created"],
                t["completed"],
            ]
            for t in report.tasks
        ],
    )
    sheet(
        "แจ้งปัญหาไอที",
        ["เลขที่", "เรื่อง", "หมวด", "ความสำคัญ", "สถานะ", "ผู้แจ้ง", "ผู้รับผิดชอบ", "แจ้งเมื่อ", "แก้ไขเมื่อ"],
        [
            [
                t["number"],
                t["title"],
                t["category"],
                t["priority"],
                t["status"],
                t["requester"],
                t["assignee"],
                t["created"],
                t["resolved"],
            ]
            for t in report.tickets
        ],
    )
    if o.tasks.workload:
        sheet(
            "ภาระงาน",
            ["พนักงาน", "งานค้าง", "เลยกำหนด", "เสร็จในช่วงนี้"],
            [[w.user.display_name, w.open, w.overdue, w.completed] for w in o.tasks.workload],
        )
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# --- PDF ----------------------------------------------------------------------------------

_CSS = """
@page {
  size: A4; margin: 16mm 14mm;
  @bottom-right { content: counter(page) " / " counter(pages); font-size: 8pt; color: #666; }
}
body { font-family: "Loma", "Garuda", "Sawasdee", sans-serif; font-size: 10pt; color: #1f2937; }
h1 { font-size: 16pt; margin: 0 0 2mm; }
h2 { font-size: 12pt; margin: 6mm 0 2mm; border-bottom: 1px solid #ddd; padding-bottom: 1mm; }
.muted { color: #6b7280; font-size: 9pt; }
table { width: 100%; border-collapse: collapse; margin-top: 2mm; }
th, td { border: 1px solid #e5e7eb; padding: 1.5mm 2mm; text-align: left; vertical-align: top; }
th { background: #f3f4f6; }
td.num { text-align: right; }
.kpis td { width: 25%; }
.bar { background: #2563eb; height: 3mm; }
"""


def _table(header: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in header)
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="num">{escape(str(c))}</td>'
            if isinstance(c, int | float)
            else f"<td>{escape(str(c))}</td>"
            for c in row
        )
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _bars(rows: list[tuple[str, int]]) -> str:
    peak = max((n for _, n in rows), default=0) or 1
    items = "".join(
        f"<tr><td>{escape(label)}</td><td class='num'>{n}</td>"
        f"<td style='width:50%'><div class='bar' style='width:{n / peak * 100:.0f}%'></div>"
        "</td></tr>"
        for label, n in rows
    )
    return f"<table>{items}</table>"


def to_html(report: ReportData) -> str:
    o = report.overview
    kpi_cells = _kpis(o)
    kpi_rows = "".join(
        "<tr>"
        + "".join(
            f"<td><span class='muted'>{escape(k)}</span><br><b>{escape(str(v))}</b></td>"
            for k, v in kpi_cells[i : i + 4]
        )
        + "</tr>"
        for i in range(0, len(kpi_cells), 4)
    )
    parts = [
        f"<h1>{escape(_title(o))}</h1>",
        f"<p class='muted'>ช่วงเวลา {o.date_from.isoformat()} ถึง {o.date_to.isoformat()} "
        f"({escape(o.timezone)}) · "
        f"สร้างเมื่อ {_local(o.generated_at, o.timezone)}</p>",
        f"<table class='kpis'>{kpi_rows}</table>",
        "<h2>สถานะงาน</h2>",
        _bars([(_task_status(c.key), c.count) for c in o.tasks.by_status]),
        "<h2>แจ้งปัญหาไอทีตามหมวด (ในช่วงนี้)</h2>",
        _bars([(_ticket_category(c.key), c.count) for c in o.tickets.by_category])
        if o.tickets.by_category
        else "<p class='muted'>ไม่มีรายการ</p>",
    ]
    if o.tasks.workload:
        parts += [
            "<h2>ภาระงานรายบุคคล</h2>",
            _table(
                ["พนักงาน", "งานค้าง", "เลยกำหนด", "เสร็จในช่วงนี้"],
                [[w.user.display_name, w.open, w.overdue, w.completed] for w in o.tasks.workload],
            ),
        ]
    shown = report.tasks[:PDF_LIST_ROWS]
    parts += [
        f"<h2>รายการงาน ({len(shown)} จาก {len(report.tasks)})</h2>",
        _table(
            ["ชื่องาน", "สถานะ", "ความสำคัญ", "ผู้รับผิดชอบ", "กำหนดส่ง"],
            [[t["title"], t["status"], t["priority"], t["assignees"], t["due"]] for t in shown],
        )
        if shown
        else "<p class='muted'>ไม่มีรายการ</p>",
    ]
    shown_t = report.tickets[:PDF_LIST_ROWS]
    parts += [
        f"<h2>แจ้งปัญหาไอที ({len(shown_t)} จาก {len(report.tickets)})</h2>",
        _table(
            ["เลขที่", "เรื่อง", "สถานะ", "ผู้แจ้ง", "ผู้รับผิดชอบ"],
            [
                [t["number"], t["title"], t["status"], t["requester"], t["assignee"]]
                for t in shown_t
            ],
        )
        if shown_t
        else "<p class='muted'>ไม่มีรายการ</p>",
        "<p class='muted'>ไฟล์ Excel มีรายการครบทุกแถว</p>",
    ]
    body = "".join(parts)
    head = f"<head><meta charset='utf-8'><style>{_CSS}</style></head>"
    return f"<!DOCTYPE html><html lang='th'>{head}<body>{body}</body></html>"


def to_pdf(report: ReportData) -> bytes:
    from weasyprint import HTML

    pdf: bytes = HTML(string=to_html(report)).write_pdf()
    return pdf
