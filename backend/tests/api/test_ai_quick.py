"""One-off "ถาม AI" questions (ADR-066): streamed, stateless, nothing stored."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.ai.providers.base import ProviderError
from app.services.ai.quick import system_prompt
from tests.ai_support import ScriptedProvider, events, say
from tests.conftest import Factory

AsUser = Callable[..., TestClient]
QUICK = "/api/v1/ai/quick"
TABLES = ("chat_sessions", "chat_messages", "ai_action_requests", "audit_logs")


def _counts(db: Factory) -> dict[str, int]:
    return {t: int(db.scalar(f"SELECT count(*) FROM {t}")) for t in TABLES}


def test_answer_streams_and_nothing_is_stored(
    as_user: AsUser, api_app: FastAPI, db: Factory
) -> None:
    provider = ScriptedProvider()
    api_app.state.chat_provider = provider
    client = as_user(["EMPLOYEE"])
    before = _counts(db)

    provider.turns.append(say("กรุงเทพมหานครเป็นเมืองหลวงของประเทศไทย"))
    response = client.post(QUICK, json={"question": "  เมืองหลวงของไทยคืออะไร  "})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    stream = events(response.text)
    assert [name for name, _ in stream] == ["delta", "delta", "done"]
    assert "".join(d["text"] for n, d in stream if n == "delta") == (
        "กรุงเทพมหานครเป็นเมืองหลวงของประเทศไทย"
    )

    sent = provider.requests[-1]
    assert sent["tools"] == []  # no tools, no company data
    assert [(m.role, m.content) for m in sent["messages"]] == [("user", "เมืองหลวงของไทยคืออะไร")]
    assert "no Markdown" in sent["system"] and "paragraphs" in sent["system"]

    # A second question starts from nothing: no earlier turns are sent.
    provider.turns.append(say("2"))
    client.post(QUICK, json={"question": "1+1 เท่ากับเท่าไร"})
    assert len(provider.requests[-1]["messages"]) == 1
    assert _counts(db) == before  # no sessions, messages or audit rows


def test_errors_and_limits(as_user: AsUser, api_app: FastAPI) -> None:
    client = as_user(["EMPLOYEE"])
    api_app.state.chat_provider = None
    assert client.post(QUICK, json={"question": "สวัสดี"}).status_code == 503

    provider = ScriptedProvider(error=ProviderError("ผู้ให้บริการ AI ไม่ตอบสนองในขณะนี้"))
    api_app.state.chat_provider = provider
    failed = events(client.post(QUICK, json={"question": "สวัสดี"}).text)
    assert failed == [
        ("error", {"code": "ai_provider_error", "message": "ผู้ให้บริการ AI ไม่ตอบสนองในขณะนี้"})
    ]

    provider.error = None
    provider.turns.append(say("", refused=True))
    assert events(client.post(QUICK, json={"question": "x"}).text)[0][0] == "error"

    assert client.post(QUICK, json={"question": "   "}).status_code == 422
    assert client.post(QUICK, json={"question": "ก" * 2001}).status_code == 422
    assert as_user([]).post(QUICK, json={"question": "สวัสดี"}).status_code == 403


def test_system_prompt_states_the_local_date() -> None:
    prompt = system_prompt("Asia/Bangkok", datetime(2026, 11, 22, 18, 0, tzinfo=UTC))
    assert "23 พฤศจิกายน 2569" in prompt  # already the next day in Bangkok
    assert "2026-11-23" in prompt


def test_quick_questions_can_use_a_cheaper_model(as_user: AsUser, api_app: FastAPI) -> None:
    main, cheap = ScriptedProvider(model="main-model"), ScriptedProvider(model="cheap-model")
    api_app.state.chat_provider = main
    api_app.state.quick_provider = cheap
    client = as_user(["EMPLOYEE"])
    cheap.turns.append(say("ตอบสั้นๆ"))
    stream = events(client.post(QUICK, json={"question": "สวัสดี"}).text)
    assert stream[-1][0] == "done"
    assert len(cheap.requests) == 1 and main.requests == []  # main assistant model untouched


def test_quick_provider_settings() -> None:
    from app.services.ai.providers import build_quick_provider
    from tests.conftest import make_settings

    groq = {
        "ai_chat_provider": "openai_compatible",
        "ai_chat_base_url": "https://api.groq.com/openai/v1",
        "ai_chat_model": "openai/gpt-oss-120b",
    }
    assert build_quick_provider(make_settings(**groq)) is None  # not set: main model is used
    quick = build_quick_provider(make_settings(**groq, ai_quick_model="llama-3.1-8b-instant"))
    assert quick is not None and quick.model == "llama-3.1-8b-instant"
    assert quick._max_tokens == 1024  # type: ignore[attr-defined]
    disabled = make_settings(ai_quick_model="llama-3.1-8b-instant")
    assert build_quick_provider(disabled) is None  # no AI provider configured at all


def test_main_model_answers_when_the_quick_model_is_refused(
    as_user: AsUser, api_app: FastAPI
) -> None:
    refused = ProviderError("การตั้งค่าผู้ให้บริการ AI ไม่ถูกต้อง", code="ai_provider_misconfigured")
    cheap = ScriptedProvider(model="retired-model", error=refused)
    main = ScriptedProvider(model="main-model")
    api_app.state.quick_provider = cheap
    api_app.state.chat_provider = main
    client = as_user(["EMPLOYEE"])

    main.turns.append(say("ตอบจากโมเดลหลัก"))
    stream = events(client.post(QUICK, json={"question": "สวัสดี"}).text)
    assert [n for n, _ in stream][-1] == "done"
    assert "".join(d["text"] for n, d in stream if n == "delta") == "ตอบจากโมเดลหลัก"
    assert len(cheap.requests) == 1 and len(main.requests) == 1

    # Without a separate quick model there is nothing to fall back to.
    api_app.state.quick_provider = None
    main.error = refused
    stream = events(client.post(QUICK, json={"question": "สวัสดี"}).text)
    assert stream == [
        (
            "error",
            {
                "code": "ai_provider_misconfigured",
                "message": "การตั้งค่าผู้ให้บริการ AI ไม่ถูกต้อง กรุณาติดต่อผู้ดูแลระบบ",
            },
        )
    ]
