"""AI provider adapters behind one neutral interface (ADR-007)."""

from __future__ import annotations

from app.core.config import AIProvider, Settings
from app.services.ai.config import chat_config
from app.services.ai.providers.base import ChatProvider


def build_chat_provider(settings: Settings) -> ChatProvider | None:
    """The configured chat provider, or ``None`` when AI chat is disabled or misconfigured."""
    config = chat_config(settings)
    if not config.valid or config.model is None:
        return None
    if settings.ai_chat_provider is AIProvider.ANTHROPIC:
        from app.services.ai.providers.anthropic_provider import AnthropicProvider

        assert settings.ai_chat_api_key is not None  # noqa: S101 - checked by chat_config
        return AnthropicProvider(
            api_key=settings.ai_chat_api_key.get_secret_value(),
            model=config.model,
            max_tokens=settings.ai_chat_max_tokens,
            timeout_seconds=settings.ai_request_timeout_seconds,
            refusal_fallback=settings.ai_chat_refusal_fallback,
            base_url=settings.ai_chat_base_url,
        )
    from app.services.ai.providers.openai_compatible import OpenAICompatibleProvider

    assert settings.ai_chat_base_url is not None  # noqa: S101 - checked by chat_config
    return OpenAICompatibleProvider(
        base_url=settings.ai_chat_base_url,
        model=config.model,
        max_tokens=settings.ai_chat_max_tokens,
        temperature=settings.ai_chat_temperature,
        timeout_seconds=settings.ai_request_timeout_seconds,
        api_key=(settings.ai_chat_api_key.get_secret_value() if settings.ai_chat_api_key else None),
    )
