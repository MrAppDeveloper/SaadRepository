from __future__ import annotations

import os
from typing import Any

from nebula_agent.providers.base import (
    Message,
    NotConfiguredError,
    ProviderError,
    ProviderResponse,
    ToolCall,
    ToolSpec,
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


class AnthropicProvider:
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
            raise ProviderError(f"Anthropic request failed: {e}") from e
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [
            ToolCall(id=b.id, name=b.name, arguments=dict(b.input))
            for b in resp.content
            if b.type == "tool_use"
        ]
        return ProviderResponse(text=text, tool_calls=calls, stop_reason=resp.stop_reason or "")
