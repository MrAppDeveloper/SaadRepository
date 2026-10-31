from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(Exception):
    """A provider call failed."""


class NotConfiguredError(ProviderError):
    """The provider is missing credentials or settings."""


class ProviderDisabledError(NotConfiguredError):
    """The provider exists but has not been explicitly enabled."""


class ProviderAuthError(ProviderError):
    """The provider rejected our credentials (HTTP 401/403)."""


class ProviderLimitError(ProviderError):
    """The provider refused because a usage / rate limit was reached. Never retried elsewhere."""


AUTH_STATUS_CODES = (401, 403)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the tool's arguments


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """Provider-neutral message. role is 'user', 'assistant' or 'tool'."""

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # assistant only
    tool_call_id: str | None = None  # tool only


@dataclass
class ProviderResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""


class Provider(Protocol):
    name: str

    def chat(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> ProviderResponse: ...


def validate_tool_calls(calls: list[ToolCall], tools: list[ToolSpec] | None) -> None:
    """Treat model output as untrusted: only tools we offered may be requested.

    Parsing a ToolCall never executes anything; this just rejects malformed or
    unexpected requests at the provider boundary.
    """
    offered = {t.name for t in tools or []}
    for c in calls:
        if not isinstance(c.id, str) or not c.id:
            raise ProviderError("Malformed response: tool call without an id.")
        if c.name not in offered:
            raise ProviderError(f"Model requested tool '{c.name}', which was not offered.")
        if not isinstance(c.arguments, dict):
            raise ProviderError("Malformed response: tool arguments are not an object.")
