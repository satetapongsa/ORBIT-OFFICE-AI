"""Quick Q&A for the round "ถาม AI" button (ADR-066).

One question, one answer, nothing remembered: no session, no database rows, no audit entry
with the text, nothing logged. The answer streams as server-sent events from the same chat
model as the rest of the application, without tools and without company data.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.logging import get_logger
from app.services.ai.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderError,
    TextDelta,
)

logger = get_logger(__name__)

QUICK_QUESTION_MAX_CHARS = 2000

_THAI_MONTHS = (
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
)


def system_prompt(timezone: str, now: datetime | None = None) -> str:
    today = (now or datetime.now(ZoneInfo(timezone))).astimezone(ZoneInfo(timezone))
    date_th = f"{today.day} {_THAI_MONTHS[today.month - 1]} {today.year + 543}"
    return (
        "You are a friendly, knowledgeable general assistant inside an office web app. "
        "Answer any everyday question: general knowledge, language and writing, maths, "
        "science, technology, health and lifestyle basics, ideas and advice.\n"
        "Style rules:\n"
        "- Reply in the language of the question (usually Thai), natural and polite.\n"
        "- Answer the question directly in the first sentence, then add only what helps.\n"
        "- Write short plain paragraphs (usually 1-3) separated by one blank line.\n"
        "- Plain text only: no Markdown, no '#', no '**', no tables, no code fences. "
        "If steps or a list really help, write lines starting with 1. 2. 3.\n"
        "- Be accurate. If you are not sure or the answer may have changed recently, say so "
        "briefly instead of guessing.\n"
        "- You cannot see the company's documents, tasks or people. For questions about work "
        "data, suggest the 'ผู้ช่วย AI' page in the menu.\n"
        "- Each question stands alone; there is no earlier conversation.\n"
        f"Today is {date_th} ({today:%Y-%m-%d}, {timezone})."
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_answer(
    provider: ChatProvider, question: str, *, timezone: str
) -> AsyncIterator[str]:
    """Yields `delta` events with text, then `done` (or one `error` event)."""
    sent_any = False
    try:
        async for event in provider.stream(
            system=system_prompt(timezone),
            messages=[Message(role="user", content=question)],
            tools=[],
        ):
            if isinstance(event, TextDelta) and event.text:
                sent_any = True
                yield _sse("delta", {"text": event.text})
            elif isinstance(event, Completion):
                if event.refused:
                    yield _sse(
                        "error",
                        {"code": "ai_refused", "message": "ขออภัย คำถามนี้ตอบให้ไม่ได้"},
                    )
                    return
                if not sent_any and event.text:
                    yield _sse("delta", {"text": event.text})
                    sent_any = True
        if not sent_any:
            yield _sse(
                "error",
                {"code": "ai_empty", "message": "ผู้ช่วย AI ไม่ได้ให้คำตอบ กรุณาลองถามใหม่"},
            )
            return
        yield _sse("done", {})
    except ProviderError as exc:
        yield _sse("error", {"code": exc.code, "message": exc.message})
    except Exception as exc:  # never leak details into the stream
        logger.warning("quick_answer_failed", error_type=type(exc).__name__)
        yield _sse(
            "error",
            {"code": "ai_provider_error", "message": "ไม่ได้รับคำตอบจากผู้ช่วย AI กรุณาลองใหม่"},
        )
