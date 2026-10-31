from __future__ import annotations

import json
import os
from typing import Any

import httpx

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


def parse_response(data: Any) -> ProviderResponse:
    try:
        choice = data["choices"][0]
        msg = choice["message"]
        content = msg.get("content") or ""
        if not isinstance(content, str):
            raise TypeError("content is not a string")
        calls = []
        for c in msg.get("tool_calls") or []:
            args = json.loads(c["function"]["arguments"] or "{}")
            if not isinstance(args, dict):
                raise TypeError("tool arguments are not an object")
            calls.append(ToolCall(id=c["id"], name=c["function"]["name"], arguments=args))
        return ProviderResponse(content, calls, choice.get("finish_reason") or "")
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as e:
        raise ProviderError(f"Malformed response: {e}") from e


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
            data = r.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in AUTH_STATUS_CODES:
                raise ProviderAuthError(
                    f"Server rejected the credentials (HTTP {status}). Check OPENAI_COMPAT_API_KEY."
                ) from e
            raise ProviderError(f"OpenAI-compatible request failed: HTTP {status}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"OpenAI-compatible request failed: {e}") from e
        except ValueError as e:
            raise ProviderError("OpenAI-compatible response was not valid JSON.") from e
        parsed = parse_response(data)
        validate_tool_calls(parsed.tool_calls, tools)
        return parsed
