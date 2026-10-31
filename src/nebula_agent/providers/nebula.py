from __future__ import annotations

from nebula_agent.providers.base import Message, NotConfiguredError, ProviderResponse, ToolSpec


class NebulaProvider:
    """Placeholder. The Nebula API has not been verified, so no endpoint is assumed.

    Replace chat() once the official docs, base URL and auth scheme are confirmed.
    """

    name = "nebula"

    def chat(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        raise NotConfiguredError(
            "Nebula provider is not implemented: the Nebula API has not been verified yet."
        )
