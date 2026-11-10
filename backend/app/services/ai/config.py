"""AI provider configuration inspection.

Phase 1 only validates configuration; provider adapters (and real connectivity checks)
are implemented in Phase 6. Nothing here contacts an AI provider.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import AIProvider, Settings


@dataclass(frozen=True, slots=True)
class AIComponentConfig:
    name: str  # "ai_chat" | "ai_embedding"
    provider: AIProvider
    model: str | None
    problems: tuple[str, ...]

    @property
    def enabled(self) -> bool:
        return self.provider is not AIProvider.DISABLED

    @property
    def valid(self) -> bool:
        return self.enabled and not self.problems


def _problems(
    prefix: str,
    provider: AIProvider,
    model: str | None,
    base_url: str | None,
    has_api_key: bool,
) -> tuple[str, ...]:
    if provider is AIProvider.DISABLED:
        return ()
    problems: list[str] = []
    if not model:
        problems.append(f"{prefix}_MODEL is required")
    if provider is AIProvider.OPENAI_COMPATIBLE and not base_url:
        problems.append(f"{prefix}_BASE_URL is required for openai_compatible")
    if provider is AIProvider.ANTHROPIC and not has_api_key:
        problems.append(f"{prefix}_API_KEY is required for anthropic")
    return tuple(problems)


def chat_config(settings: Settings) -> AIComponentConfig:
    return AIComponentConfig(
        name="ai_chat",
        provider=settings.ai_chat_provider,
        model=settings.ai_chat_model,
        problems=_problems(
            "AI_CHAT",
            settings.ai_chat_provider,
            settings.ai_chat_model,
            settings.ai_chat_base_url,
            settings.ai_chat_api_key is not None,
        ),
    )


def embedding_config(settings: Settings) -> AIComponentConfig:
    return AIComponentConfig(
        name="ai_embedding",
        provider=settings.ai_embedding_provider,
        model=settings.ai_embedding_model,
        problems=_problems(
            "AI_EMBEDDING",
            settings.ai_embedding_provider,
            settings.ai_embedding_model,
            settings.ai_embedding_base_url,
            settings.ai_embedding_api_key is not None,
        ),
    )
