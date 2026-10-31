from __future__ import annotations

from nebula_agent.providers.base import (
    Message,
    NotConfiguredError,
    Provider,
    ProviderError,
    ProviderResponse,
    ToolCall,
    ToolSpec,
)


def get_provider(name: str) -> Provider:
    """Build a provider by name, reading credentials from the environment."""
    if name == "anthropic":
        from nebula_agent.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if name == "openai_compat":
        from nebula_agent.providers.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider()
    if name == "nebula":
        from nebula_agent.providers.nebula import NebulaProvider

        return NebulaProvider()
    raise ValueError(f"Unknown provider '{name}'")


__all__ = [
    "Message",
    "NotConfiguredError",
    "Provider",
    "ProviderError",
    "ProviderResponse",
    "ToolCall",
    "ToolSpec",
    "get_provider",
]
