"""Anthropic (Claude) chat adapter using the official ``anthropic`` SDK.

* Streams with ``messages.stream`` and returns the final message.
* Assistant content blocks (including thinking blocks) are kept as ``raw`` and replayed
  unchanged on later requests to the same model — never edited.
* Sampling parameters are not sent (current Claude models reject them); thinking is left at
  the model default (adaptive on current models).
* Tools stream their input eagerly; inputs are validated by the chat service before use.
* On models that support it, refusals fall back server-side to another model
  (``AI_CHAT_REFUSAL_FALLBACK``); a remaining refusal is reported to the user.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

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
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept server-side refusal fallbacks (`fallbacks: "default"`).
FALLBACK_MODELS = frozenset(
    {
        "claude-fable-5-2",
        "claude-fable-5-1",
        "claude-mythos-5-2",
        "claude-mythos-5-1",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
    }
)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout_seconds: float,
        refusal_fallback: bool = True,
        base_url: str | None = None,
        http_client: Any | None = None,
        max_retries: int = 2,
    ) -> None:
        self.model = model
        self._max_tokens = max_tokens
        self._fallback = refusal_fallback and model in FALLBACK_MODELS
        self._client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=http_client,
        )

    @property
    def source(self) -> str:
        return f"{self.name}:{self.model}"

    # --- Conversion -----------------------------------------------------------------

    def _messages(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": [{"type": "text", "text": m.content}]})
            elif m.role == "system":
                text = SYSTEM_NOTE_PREFIX + m.content
                out.append({"role": "user", "content": [{"type": "text", "text": text}]})
            elif m.role == "assistant":
                if m.raw is not None and m.raw_source == self.source:
                    out.append({"role": "assistant", "content": m.raw})
                    continue
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for call in m.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments or {},
                        }
                    )
                if blocks:
                    out.append({"role": "assistant", "content": blocks})
            else:  # tool result: all results of one turn go into one user message
                block = {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id,
                    "content": m.content,
                    "is_error": m.is_error,
                }
                previous = out[-1] if out else None
                if (
                    previous is not None
                    and previous["role"] == "user"
                    and all(b.get("type") == "tool_result" for b in previous["content"])
                ):
                    previous["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    @staticmethod
    def _tools(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "eager_input_streaming": True,
            }
            for t in tools
        ]

    # --- Streaming ------------------------------------------------------------------

    async def stream(
        self, *, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> AsyncIterator[ProviderEvent]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": self._messages(messages),
            # Caches the stable prefix (tools + system + earlier turns) automatically.
            "cache_control": {"type": "ephemeral"},
        }
        if tools:
            params["tools"] = self._tools(tools)
        try:
            if self._fallback:
                manager: Any = self._client.beta.messages.stream(
                    betas=[FALLBACK_BETA], fallbacks="default", **params
                )
            else:
                manager = self._client.messages.stream(**params)
            async with manager as stream:
                async for event in stream:
                    if event.type == "text" and event.text:
                        yield TextDelta(event.text)
                final = await stream.get_final_message()
        except ValueError:
            # Tool input the SDK could not parse at all (eager input streaming).
            logger.warning("anthropic_invalid_tool_json", model=self.model)
            raise ProviderError(MSG_BAD_REQUEST, retryable=True) from None
        except anthropic.APIStatusError as exc:
            raise _status_error(exc) from None
        except anthropic.APIConnectionError as exc:
            logger.warning("anthropic_connection_error", error_type=type(exc).__name__)
            raise ProviderError(MSG_UNAVAILABLE, retryable=True) from None

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in final.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else None
                calls.append(ToolCall(id=block.id, name=block.name, arguments=args))
        usage = final.usage
        yield Completion(
            text="".join(text_parts),
            tool_calls=calls,
            stop_reason=final.stop_reason,
            raw=[block.to_dict() for block in final.content],
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            refused=final.stop_reason == "refusal",
            truncated=final.stop_reason == "max_tokens",
        )


def _status_error(exc: anthropic.APIStatusError) -> ProviderError:
    # Log status and request id only — never the response body or the API key.
    logger.warning(
        "anthropic_api_error",
        status_code=exc.status_code,
        error_type=type(exc).__name__,
        request_id=exc.request_id,
    )
    if isinstance(
        exc,
        anthropic.AuthenticationError | anthropic.PermissionDeniedError | anthropic.NotFoundError,
    ):
        return ProviderError(MSG_AUTH, code="ai_provider_misconfigured")
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderError(MSG_RATE_LIMITED, code="ai_rate_limited", retryable=True)
    if isinstance(exc, anthropic.BadRequestError):
        return ProviderError(MSG_BAD_REQUEST)
    return ProviderError(MSG_UNAVAILABLE, retryable=exc.status_code >= 500)
