from __future__ import annotations

import os

from nebula_agent.providers.base import (
    Message,
    NotConfiguredError,
    Provider,
    ProviderAuthError,
    ProviderDisabledError,
    ProviderError,
    ProviderLimitError,
    ProviderResponse,
    ToolCall,
    ToolSpec,
)

ENABLE_ENV = "NEBULA_AGENT_ENABLE"
OPT_IN_PROVIDERS = ("anthropic", "openai_compat", "claude_cli")


def enabled_providers() -> set[str]:
    """Providers the user has explicitly enabled, e.g. NEBULA_AGENT_ENABLE=anthropic."""
    raw = os.environ.get(ENABLE_ENV, "")
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def get_provider(name: str) -> Provider:
    """Build exactly the named provider. Never substitutes another one on failure."""
    if name == "nebula":
        from nebula_agent.providers.nebula import NebulaProvider

        return NebulaProvider()
    if name not in OPT_IN_PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'")
    if name not in enabled_providers():
        raise ProviderDisabledError(
            f"Provider '{name}' is disabled. Set {ENABLE_ENV}={name} in .env to enable it; "
            "this can use your quota or incur charges with that provider."
        )
    if name == "anthropic":
        from nebula_agent.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if name == "claude_cli":
        from nebula_agent.providers.claude_cli import ClaudeCliProvider

        return ClaudeCliProvider()
    from nebula_agent.providers.openai_compat import OpenAICompatProvider

    return OpenAICompatProvider()


__all__ = [
    "Message",
    "NotConfiguredError",
    "Provider",
    "ProviderAuthError",
    "ProviderDisabledError",
    "ProviderError",
    "ProviderLimitError",
    "ProviderResponse",
    "ToolCall",
    "ToolSpec",
    "enabled_providers",
    "get_provider",
]
