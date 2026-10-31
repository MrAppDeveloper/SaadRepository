from __future__ import annotations

import json
import os
from typing import Any

import httpx

from nebula_agent.providers.base import (
    Message,
    NotConfiguredError,
    ProviderError,
    ProviderResponse,
    ToolCall,
    ToolSpec,
)


def to_openai_messages(messages: list[Message], system: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": m.role, "content": m.content})
    return out


class OpenAICompatProvider:
    """Any server exposing POST {base_url}/chat/completions in the OpenAI format."""

    name = "openai_compat"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OPENAI_COMPAT_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise NotConfiguredError("OPENAI_COMPAT_BASE_URL is not set (see .env.example).")
        self.api_key = api_key or os.environ.get("OPENAI_COMPAT_API_KEY", "")
        self._client = client or httpx.Client(timeout=60)

    def chat(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": to_openai_messages(messages, system),
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            url = f"{self.base_url}/chat/completions"
            r = self._client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            choice = r.json()["choices"][0]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"OpenAI-compatible request failed: {e}") from e
        msg = choice["message"]
        try:
            calls = [
                ToolCall(
                    id=c["id"],
                    name=c["function"]["name"],
                    arguments=json.loads(c["function"]["arguments"] or "{}"),
                )
                for c in msg.get("tool_calls") or []
            ]
        except (KeyError, ValueError) as e:
            raise ProviderError(f"Malformed tool call in response: {e}") from e
        return ProviderResponse(
            text=msg.get("content") or "",
            tool_calls=calls,
            stop_reason=choice.get("finish_reason") or "",
        )
