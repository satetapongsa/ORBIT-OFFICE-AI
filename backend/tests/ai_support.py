"""A scripted chat provider and SSE helpers for AI tests (no network, no real model)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.services.ai.providers.base import (
    Completion,
    Message,
    ProviderError,
    ProviderEvent,
    TextDelta,
    ToolCall,
    ToolSpec,
)


def say(text: str, **extra: Any) -> list[ProviderEvent]:
    """A turn that streams ``text`` in two pieces and ends."""
    middle = len(text) // 2
    return [TextDelta(text[:middle]), TextDelta(text[middle:]), Completion(text=text, **extra)]


def call(
    name: str, arguments: dict[str, Any] | None, call_id: str = "call_1"
) -> list[ProviderEvent]:
    return [
        Completion(text="", tool_calls=[ToolCall(call_id, name, arguments)], stop_reason="tool_use")
    ]


@dataclass
class ScriptedProvider:
    """Plays back one scripted turn per ``stream`` call and records what it was sent."""

    turns: list[list[ProviderEvent]] = field(default_factory=list)
    error: ProviderError | None = None
    name: str = "scripted"
    model: str = "test-model"
    requests: list[dict[str, Any]] = field(default_factory=list)

    @property
    def source(self) -> str:
        return f"{self.name}:{self.model}"

    async def stream(
        self, *, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> AsyncIterator[ProviderEvent]:
        self.requests.append(
            {"system": system, "messages": list(messages), "tools": [t.name for t in tools]}
        )
        if self.error is not None:
            raise self.error
        for event in self.turns.pop(0):
            yield event

    def tool_results(self, request: int = -1) -> list[dict[str, Any]]:
        """Parsed tool results the model received in a given request."""
        return [
            json.loads(m.content) for m in self.requests[request]["messages"] if m.role == "tool"
        ]


def events(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse a server-sent-events body into (event, data) pairs."""
    out: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        name, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if data:
            out.append((name, json.loads(data)))
    return out
