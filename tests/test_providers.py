import json
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner

from nebula_agent.cli import app
from nebula_agent.providers import (
    Message,
    NotConfiguredError,
    ProviderError,
    ToolCall,
    ToolSpec,
    get_provider,
)
from nebula_agent.providers.anthropic import AnthropicProvider, to_anthropic_messages
from nebula_agent.providers.nebula import NebulaProvider
from nebula_agent.providers.openai_compat import OpenAICompatProvider, to_openai_messages

TOOL = ToolSpec("run_sql", "Run SQL", {"type": "object", "properties": {"q": {"type": "string"}}})
HISTORY = [
    Message("user", "hi"),
    Message("assistant", "ok", [ToolCall("t1", "run_sql", {"q": "select 1"})]),
    Message("tool", "1", tool_call_id="t1"),
    Message("tool", "2", tool_call_id="t2"),
]


def test_anthropic_message_conversion_merges_tool_results():
    out = to_anthropic_messages(HISTORY)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[1]["content"][1] == {
        "type": "tool_use",
        "id": "t1",
        "name": "run_sql",
        "input": {"q": "select 1"},
    }
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["t1", "t2"]


def test_anthropic_chat_parses_response():
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[
                SimpleNamespace(type="text", text="thinking"),
                SimpleNamespace(type="tool_use", id="t9", name="run_sql", input={"q": "x"}),
            ],
        )

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    resp = AnthropicProvider(client=client).chat("m", [Message("user", "hi")], [TOOL], "sys")
    assert resp.text == "thinking" and resp.stop_reason == "tool_use"
    assert resp.tool_calls == [ToolCall("t9", "run_sql", {"q": "x"})]
    assert seen["system"] == "sys" and seen["tools"][0]["input_schema"] == TOOL.parameters


def test_anthropic_wraps_errors():
    def boom(**kw):
        raise RuntimeError("down")

    client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    with pytest.raises(ProviderError, match="down"):
        AnthropicProvider(client=client).chat("m", [Message("user", "hi")])


def test_anthropic_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(NotConfiguredError):
        AnthropicProvider()


def test_openai_message_conversion():
    out = to_openai_messages(HISTORY, "sys")
    assert out[0] == {"role": "system", "content": "sys"}
    assert json.loads(out[2]["tool_calls"][0]["function"]["arguments"]) == {"q": "select 1"}
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": "1"}


def test_openai_compat_chat_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer k"
        body = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {"name": "run_sql", "arguments": '{"q": "y"}'},
                            }
                        ],
                    },
                }
            ]
        }
        return httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatProvider("http://x/v1/", "k", client)
    resp = p.chat("m", [Message("user", "hi")], [TOOL])
    assert resp.text == "" and resp.tool_calls == [ToolCall("c1", "run_sql", {"q": "y"})]


def test_openai_compat_http_error_wrapped():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(ProviderError):
        OpenAICompatProvider("http://x/v1", client=client).chat("m", [Message("user", "hi")])


def test_openai_compat_requires_base_url(monkeypatch):
    monkeypatch.delenv("OPENAI_COMPAT_BASE_URL", raising=False)
    with pytest.raises(NotConfiguredError):
        OpenAICompatProvider()


def test_nebula_is_unconfigured_stub():
    with pytest.raises(NotConfiguredError, match="not been verified"):
        NebulaProvider().chat("m", [Message("user", "hi")])


def test_get_provider_unknown():
    with pytest.raises(ValueError):
        get_provider("bogus")


def test_cli_providers_test_nebula_reports_not_configured():
    result = CliRunner().invoke(app, ["providers", "test", "nebula", "-m", "x"])
    assert result.exit_code == 3
