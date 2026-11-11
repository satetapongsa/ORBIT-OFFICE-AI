"""OpenAI-compatible chat adapter (Ollama, vLLM, LM Studio, OpenAI, gateways).

Plain HTTP (``httpx2``) against ``{base_url}/chat/completions`` with server-sent events.
Tool calls arrive as fragments per ``index`` and are assembled here; arguments that are not
a JSON object are reported as ``None`` so the chat service can return an error to the model.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx2

from app.core.logging import get_logger
from app.services.ai.providers.base import (
    MSG_AUTH,
    MSG_BAD_REQUEST,
    MSG_RATE_LIMITED,
    MSG_UNAVAILABLE,
    Completion,
    Message,
    ProviderError,
    ProviderEvent,
    TextDelta,
    ToolCall,
    ToolSpec,
)

logger = get_logger(__name__)

SYSTEM_NOTE_PREFIX = "[แจ้งจากระบบ] "


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        max_tokens: int,
        temperature: float,
        timeout_seconds: float,
        api_key: str | None = None,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout_seconds
        self._headers = {"Accept": "text/event-stream"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._transport = transport

    @property
    def source(self) -> str:
        return f"{self.name}:{self.model}"

    @staticmethod
    def _messages(system: str, messages: Sequence[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
            elif m.role == "system":
                out.append({"role": "user", "content": SYSTEM_NOTE_PREFIX + m.content})
            elif m.role == "assistant":
                entry: dict[str, Any] = {"role": "assistant", "content": m.content or None}
                if m.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments or {}, ensure_ascii=False),
                            },
                        }
                        for c in m.tool_calls
                    ]
                if entry["content"] is None and "tool_calls" not in entry:
                    continue
                out.append(entry)
            else:
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        return out

    async def stream(
        self, *, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> AsyncIterator[ProviderEvent]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages(system, messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]

        text: list[str] = []
        fragments: dict[int, dict[str, str]] = {}
        finish: str | None = None
        usage: dict[str, Any] = {}
        try:
            async with (
                httpx2.AsyncClient(timeout=self._timeout, transport=self._transport) as client,
                client.stream("POST", self._url, json=payload, headers=self._headers) as resp,
            ):
                if resp.status_code != 200:
                    await resp.aread()  # drain; the body is never logged or shown
                    raise _status_error(resp.status_code)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(chunk.get("usage"), dict):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text.append(delta["content"])
                            yield TextDelta(delta["content"])
                        for part in delta.get("tool_calls") or []:
                            entry = fragments.setdefault(
                                int(part.get("index", 0)), {"id": "", "name": "", "args": ""}
                            )
                            if part.get("id"):
                                entry["id"] = part["id"]
                            function = part.get("function") or {}
                            if function.get("name") and not entry["name"]:
                                entry["name"] = function["name"]
                            entry["args"] += function.get("arguments") or ""
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
        except ProviderError:
            raise
        except httpx2.TimeoutException:
            logger.warning("openai_compatible_timeout", model=self.model)
            raise ProviderError(MSG_UNAVAILABLE, retryable=True) from None
        except httpx2.HTTPError as exc:
            logger.warning("openai_compatible_transport_error", error_type=type(exc).__name__)
            raise ProviderError(MSG_UNAVAILABLE, retryable=True) from None

        calls: list[ToolCall] = []
        for index in sorted(fragments):
            entry = fragments[index]
            if not entry["name"]:
                continue
            try:
                parsed = json.loads(entry["args"] or "{}")
            except json.JSONDecodeError:
                parsed = None
            calls.append(
                ToolCall(
                    id=entry["id"] or f"call_{index}_{uuid.uuid4().hex[:8]}",
                    name=entry["name"],
                    arguments=parsed if isinstance(parsed, dict) else None,
                )
            )
        yield Completion(
            text="".join(text),
            tool_calls=calls,
            stop_reason=finish,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            refused=finish == "content_filter",
            truncated=finish == "length",
        )


def _status_error(status: int) -> ProviderError:
    logger.warning("openai_compatible_api_error", status_code=status)
    if status in (401, 403, 404):
        return ProviderError(MSG_AUTH, code="ai_provider_misconfigured")
    if status == 429:
        return ProviderError(MSG_RATE_LIMITED, code="ai_rate_limited", retryable=True)
    if status in (400, 413, 422):
        return ProviderError(MSG_BAD_REQUEST)
    return ProviderError(MSG_UNAVAILABLE, retryable=status >= 500)
