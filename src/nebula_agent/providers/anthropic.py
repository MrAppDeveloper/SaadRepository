from __future__ import annotations

import os
from typing import Any

from nebula_agent.providers.base import (
    AUTH_STATUS_CODES,
    Message,
    NotConfiguredError,
    ProviderAuthError,
    ProviderError,
    ProviderResponse,
    ToolCall,
    ToolSpec,
    validate_tool_calls,
)


def to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert neutral messages; consecutive tool results merge into one user turn."""
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        elif m.role == "assistant" and m.tool_calls:
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                for c in m.tool_calls
            ]
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def parse_response(resp: Any) -> ProviderResponse:
    try:
        texts: list[str] = []
        calls: list[ToolCall] = []
        for b in list(resp.content):
            if b.type == "text":
                texts.append(b.text)
            elif b.type == "tool_use":
                if not isinstance(b.input, dict):
                    raise TypeError("tool input is not an object")
                calls.append(ToolCall(id=b.id, name=b.name, arguments=dict(b.input)))
        return ProviderResponse("".join(texts), calls, resp.stop_reason or "")
    except (AttributeError, TypeError, ValueError) as e:
        raise ProviderError(f"Malformed Anthropic response: {e}") from e


class AnthropicProvider:
    """Calls the Anthropic API with an API key. This is metered API billing,
    separate from a Claude Code subscription."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None, client: Any = None) -> None:
        if client is None:
            api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise NotConfiguredError("ANTHROPIC_API_KEY is not set (see .env.example).")
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self._client = client

    def chat(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": to_anthropic_messages(messages),
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as e:  # SDK raises many distinct types; surface one
            status = getattr(e, "status_code", None)
            if status in AUTH_STATUS_CODES:
                raise ProviderAuthError(
                    f"Anthropic rejected the credentials (HTTP {status}). Check ANTHROPIC_API_KEY."
                ) from e
            raise ProviderError(f"Anthropic request failed: {e}") from e
        parsed = parse_response(resp)
        validate_tool_calls(parsed.tool_calls, tools)
        return parsed
