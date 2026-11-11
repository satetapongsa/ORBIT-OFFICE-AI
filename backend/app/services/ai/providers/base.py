"""Provider-neutral chat types (ADR-007).

The chat service only speaks these types; each adapter converts them to its provider's wire
format. Nothing here contains SQL, permissions or tool logic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant", "tool", "system"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    # ``None`` when the model produced arguments that are not a JSON object.
    arguments: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class Message:
    """One conversation turn.

    ``system`` turns are application notes (e.g. "the user confirmed action X"); adapters send
    them as user-side text because providers differ in where system text may appear.
    ``raw`` is the provider's own assistant content, replayed unchanged when the same
    provider and model answer again (``raw_source`` = "provider:model").
    """

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    is_error: bool = False
    raw: list[dict[str, Any]] | None = None
    raw_source: str | None = None


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(slots=True)
class Completion:
    """The finished assistant turn."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    raw: list[dict[str, Any]] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    refused: bool = False
    truncated: bool = False


ProviderEvent = TextDelta | Completion


class ProviderError(Exception):
    """A provider call failed. ``message`` is safe to show to users (Thai, no provider body)."""

    def __init__(self, message: str, *, code: str = "ai_provider_error", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


class ChatProvider(Protocol):
    name: str
    model: str

    @property
    def source(self) -> str:
        """``provider:model`` — identifies whose ``raw`` content may be replayed."""
        ...

    def stream(
        self, *, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> AsyncIterator[ProviderEvent]:
        """Yield text deltas, then exactly one :class:`Completion` (or raise ProviderError)."""
        ...


# User-facing messages for common failures.
MSG_UNAVAILABLE = "ผู้ให้บริการ AI ไม่ตอบสนองในขณะนี้ กรุณาลองใหม่อีกครั้ง"
MSG_RATE_LIMITED = "ผู้ให้บริการ AI มีผู้ใช้งานหนาแน่น กรุณารอสักครู่แล้วลองใหม่"
MSG_AUTH = "การตั้งค่าผู้ให้บริการ AI ไม่ถูกต้อง กรุณาติดต่อผู้ดูแลระบบ"
MSG_BAD_REQUEST = "ผู้ให้บริการ AI ปฏิเสธคำขอนี้ กรุณาลองถามใหม่ให้สั้นลงหรือเริ่มบทสนทนาใหม่"
