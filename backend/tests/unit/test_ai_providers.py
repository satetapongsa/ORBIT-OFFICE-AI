"""Provider adapters: request shape, streaming parsing and error mapping (no network)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from app.core.config import AIProvider
from app.services.ai.providers import build_chat_provider
from app.services.ai.providers.anthropic_provider import AnthropicProvider
from app.services.ai.providers.base import (
    Completion,
    Message,
    ProviderError,
    ProviderEvent,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from app.services.ai.providers.openai_compatible import OpenAICompatibleProvider
from tests.conftest import make_settings, run

TOOLS = [ToolSpec("get_my_tasks", "List tasks", {"type": "object", "properties": {}})]
HISTORY = [
    Message(role="user", content="งานของฉันมีอะไรบ้าง"),
    Message(
        role="assistant",
        content="",
        tool_calls=(ToolCall("call_1", "get_my_tasks", {"scope": "assigned"}),),
    ),
    Message(role="tool", content='{"ok": true}', tool_call_id="call_1"),
    Message(role="system", content="ผู้ใช้ยืนยันแล้ว"),
    Message(role="user", content="ขอบคุณ"),
]


def collect(provider: Any, messages: list[Message] = HISTORY) -> list[ProviderEvent]:
    async def _go() -> list[ProviderEvent]:
        return [e async for e in provider.stream(system="SYS", messages=messages, tools=TOOLS)]

    return run(_go())  # type: ignore[no-any-return]


def sse(*events: dict[str, Any], named: bool = False) -> bytes:
    parts = []
    for e in events:
        prefix = f"event: {e['type']}\n" if named else ""
        parts.append(f"{prefix}data: {json.dumps(e, ensure_ascii=False)}\n\n")
    return "".join(parts).encode()


# --- OpenAI-compatible ----------------------------------------------------------------------


def openai(handler: Callable[[httpx2.Request], httpx2.Response]) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="http://llm.test/v1/",
        model="qwen3:8b",
        max_tokens=1000,
        temperature=0.2,
        timeout_seconds=5,
        api_key="local-key",
        transport=httpx2.MockTransport(handler),
    )


def test_openai_compatible_request_and_streamed_tool_call() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        chunks = [
            {"choices": [{"delta": {"content": "กำลัง"}}]},
            {"choices": [{"delta": {"content": "ค้นหา"}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_9",
                                    "function": {"name": "get_my_tasks", "arguments": '{"sco'},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [{"index": 0, "function": {"arguments": 'pe": "all"}'}}]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 7}},
        ]
        body = sse(*chunks) + b"data: [DONE]\n\n"
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    events = collect(openai(handler))
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer local-key"
    body = seen["body"]
    assert body["stream"] is True and body["temperature"] == 0.2
    assert body["tools"][0] == {
        "type": "function",
        "function": {
            "name": "get_my_tasks",
            "description": "List tasks",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "user", "user"]
    assert body["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"scope": "assigned"}'
    assert body["messages"][3] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"ok": true}',
    }
    assert body["messages"][4]["content"].startswith("[แจ้งจากระบบ]")

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["กำลัง", "ค้นหา"]
    done = events[-1]
    assert isinstance(done, Completion)
    assert done.text == "กำลังค้นหา"
    assert done.tool_calls == [ToolCall("call_9", "get_my_tasks", {"scope": "all"})]
    assert (done.input_tokens, done.output_tokens) == (50, 7)


def test_openai_compatible_bad_tool_json_and_truncation() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        chunk = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"name": "get_my_tasks", "arguments": "{oops"}}
                        ]
                    },
                    "finish_reason": "length",
                }
            ]
        }
        return httpx2.Response(200, content=sse(chunk) + b"data: [DONE]\n\n")

    done = collect(openai(handler))[-1]
    assert isinstance(done, Completion)
    assert done.truncated is True
    assert done.tool_calls[0].arguments is None
    assert done.tool_calls[0].id.startswith("call_0_")


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, "ai_provider_misconfigured", False),
        (404, "ai_provider_misconfigured", False),
        (429, "ai_rate_limited", True),
        (400, "ai_provider_error", False),
        (503, "ai_provider_error", True),
    ],
)
def test_openai_compatible_error_mapping(status: int, code: str, retryable: bool) -> None:
    secret_body = "provider internal detail sk-should-not-leak"

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, text=secret_body)

    with pytest.raises(ProviderError) as info:
        collect(openai(handler))
    assert info.value.code == code
    assert info.value.retryable is retryable
    assert "sk-should-not-leak" not in info.value.message


def test_openai_compatible_connection_failure() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(ProviderError) as info:
        collect(openai(handler))
    assert info.value.retryable is True


# --- Anthropic ----------------------------------------------------------------------------


def anthropic_provider(
    handler: Callable[[httpx2.Request], httpx2.Response], model: str = "claude-opus-5-5"
) -> AnthropicProvider:
    return AnthropicProvider(
        api_key="test-key",
        model=model,
        max_tokens=16000,
        timeout_seconds=5,
        refusal_fallback=True,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        max_retries=0,
    )


def anthropic_stream(stop_reason: str = "tool_use") -> bytes:
    return sse(
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 120, "output_tokens": 1},
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "ขอดูงานก่อน"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "get_my_tasks",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"scope": "assigned"}'},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 30},
        },
        {"type": "message_stop"},
        named=True,
    )


def test_anthropic_request_stream_and_raw_content() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(
            200, content=anthropic_stream(), headers={"content-type": "text/event-stream"}
        )

    raw_turn = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "ก่อนหน้า"},
    ]
    history = [
        Message(role="user", content="สวัสดี"),
        Message(
            role="assistant", content="ก่อนหน้า", raw=raw_turn, raw_source="anthropic:claude-opus-5-5"
        ),
        Message(
            role="assistant",
            content="",
            tool_calls=(
                ToolCall("toolu_a", "get_my_tasks", {}),
                ToolCall("toolu_b", "get_my_tasks", {}),
            ),
        ),
        Message(role="tool", content="A", tool_call_id="toolu_a"),
        Message(role="tool", content="B", tool_call_id="toolu_b", is_error=True),
        Message(role="user", content="ต่อเลย"),
    ]
    events = collect(anthropic_provider(handler), history)

    assert seen["path"] == "/v1/messages"
    headers = seen["headers"]
    # The SDK sends the key itself (as x-api-key or an Authorization header, by version).
    assert headers.get("x-api-key") == "test-key" or "test-key" in headers.get("authorization", "")
    assert "server-side-fallback-2026-07-01" in seen["headers"]["anthropic-beta"]
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert body["stream"] is True
    assert body["system"] == "SYS"
    assert body["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in body and "thinking" not in body
    assert body["tools"][0]["eager_input_streaming"] is True
    assert body["tools"][0]["input_schema"] == {"type": "object", "properties": {}}
    messages = body["messages"]
    # The earlier Claude turn is replayed exactly as received (thinking block included).
    assert messages[1] == {"role": "assistant", "content": raw_turn}
    # Parallel tool results go back together in one user message.
    assert messages[3]["role"] == "user"
    assert [b["tool_use_id"] for b in messages[3]["content"]] == ["toolu_a", "toolu_b"]
    assert messages[3]["content"][1]["is_error"] is True

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["ขอดูงานก่อน"]
    done = events[-1]
    assert isinstance(done, Completion)
    assert done.tool_calls == [ToolCall("toolu_1", "get_my_tasks", {"scope": "assigned"})]
    assert done.stop_reason == "tool_use"
    assert done.raw is not None and done.raw[1]["type"] == "tool_use"
    assert (done.input_tokens, done.output_tokens) == (120, 30)


def test_anthropic_without_fallback_support_uses_plain_endpoint() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, content=anthropic_stream("end_turn"))

    collect(
        anthropic_provider(handler, model="claude-haiku-4-5"), [Message(role="user", content="hi")]
    )
    assert "fallbacks" not in seen["body"]
    assert "server-side-fallback" not in seen["headers"].get("anthropic-beta", "")


def test_anthropic_refusal_is_flagged() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=anthropic_stream("refusal"))

    done = collect(anthropic_provider(handler), [Message(role="user", content="hi")])[-1]
    assert isinstance(done, Completion) and done.refused is True


@pytest.mark.parametrize(
    ("status", "error_type", "code"),
    [
        (401, "authentication_error", "ai_provider_misconfigured"),
        (429, "rate_limit_error", "ai_rate_limited"),
        (400, "invalid_request_error", "ai_provider_error"),
        (529, "overloaded_error", "ai_provider_error"),
    ],
)
def test_anthropic_error_mapping(status: int, error_type: str, code: str) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            json={"type": "error", "error": {"type": error_type, "message": "secret detail"}},
        )

    with pytest.raises(ProviderError) as info:
        collect(anthropic_provider(handler), [Message(role="user", content="hi")])
    assert info.value.code == code
    assert "secret detail" not in info.value.message


# --- Factory ------------------------------------------------------------------------------


def test_build_chat_provider() -> None:
    assert build_chat_provider(make_settings()) is None
    # Misconfigured (no model) also yields no provider rather than a broken one.
    assert build_chat_provider(make_settings(ai_chat_provider=AIProvider.ANTHROPIC)) is None
    claude = build_chat_provider(
        make_settings(
            ai_chat_provider=AIProvider.ANTHROPIC,
            ai_chat_model="claude-opus-5-5",
            ai_chat_api_key="k",
        )
    )
    assert isinstance(claude, AnthropicProvider) and claude.source == "anthropic:claude-opus-5-5"
    local = build_chat_provider(
        make_settings(
            ai_chat_provider=AIProvider.OPENAI_COMPATIBLE,
            ai_chat_model="qwen3:8b",
            ai_chat_base_url="http://127.0.0.1:11434/v1",
        )
    )
    assert isinstance(local, OpenAICompatibleProvider)
