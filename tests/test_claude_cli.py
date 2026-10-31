import json
import subprocess
from types import SimpleNamespace

import pytest

from nebula_agent.providers import (
    Message,
    NotConfiguredError,
    ProviderAuthError,
    ProviderDisabledError,
    ProviderError,
    ProviderLimitError,
    ToolSpec,
    get_provider,
)
from nebula_agent.providers.claude_cli import ClaudeCliProvider

AUTH_OK = json.dumps({"loggedIn": True, "authMethod": "oauth_token", "apiProvider": "firstParty"})


class FakeRun:
    """Stands in for subprocess.run. `auth` answers `claude auth status`; the rest answers -p."""

    def __init__(self, stdout="", returncode=0, raises=None, auth=AUTH_OK):
        self.stdout, self.returncode, self.raises, self.auth = stdout, returncode, raises, auth
        self.calls = []

    def chat_calls(self):
        return [c for c in self.calls if c[0][1] == "-p"]

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if argv[1] == "auth":
            return SimpleNamespace(stdout=self.auth, returncode=0)
        if self.raises:
            raise self.raises
        return SimpleNamespace(stdout=self.stdout, returncode=self.returncode)


def ok(text="hello", **extra):
    return json.dumps(
        {"type": "result", "subtype": "success", "is_error": False, "result": text, **extra}
    )


def provider(run):
    return ClaudeCliProvider(binary="/usr/bin/claude", runner=run)


def test_success_and_command_shape():
    run = FakeRun(ok("hi there"))
    resp = provider(run).chat("sonnet", [Message("user", "Question?")], system="be brief")
    assert (resp.text, resp.stop_reason, resp.tool_calls) == ("hi there", "success", [])
    argv, kw = run.chat_calls()[0]
    assert argv[:2] == ["/usr/bin/claude", "-p"]
    assert argv[argv.index("--tools") + 1] == ""  # every built-in tool disabled
    assert {"--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"} <= set(
        argv
    )
    assert argv[argv.index("--setting-sources") + 1] == "project"
    assert argv[argv.index("--system-prompt") + 1] == "be brief"
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert kw["input"] == "Question?"  # prompt goes on stdin, not argv
    assert "Question?" not in argv
    assert "shell" not in kw


def test_api_credentials_and_overrides_are_scrubbed_from_every_child_env(monkeypatch):
    bad = [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_PROFILE",
        "ANTHROPIC_FEDERATION_RULE_ID",
        "ANTHROPIC_SOMETHING_NEW",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ]
    for var in bad:
        monkeypatch.setenv(var, "set-in-parent")
    monkeypatch.setenv("HOME", "/keep/me")
    run = FakeRun(ok())
    provider(run).chat("m", [Message("user", "hi")])
    assert len(run.calls) == 2  # auth status + chat; both must be scrubbed
    for _, kw in run.calls:
        assert not set(bad) & set(kw["env"])
        assert kw["env"]["HOME"] == "/keep/me"


def test_runs_in_empty_temp_dir():
    run = FakeRun(ok())
    provider(run).chat("m", [Message("user", "hi")])
    assert run.calls[-1][1]["cwd"].startswith(("/tmp", "/var"))


def test_multi_turn_prompt_is_flattened():
    run = FakeRun(ok())
    provider(run).chat("m", [Message("user", "a"), Message("assistant", "b"), Message("user", "c")])
    assert run.chat_calls()[0][1]["input"] == "User: a\n\nAssistant: b\n\nUser: c"


def test_rejects_tools_and_tool_messages_without_running_anything():
    run = FakeRun(ok())
    p = provider(run)
    with pytest.raises(ProviderError, match="text-only"):
        p.chat("m", [Message("user", "hi")], [ToolSpec("t", "d", {})])
    with pytest.raises(ProviderError, match="text-only"):
        p.chat("m", [Message("user", "hi"), Message("tool", "x", tool_call_id="1")])
    assert run.calls == []  # not even the auth check ran


@pytest.mark.parametrize(
    "stdout",
    ["", "not json", "[]", json.dumps({"is_error": False}), json.dumps({"result": 5})],
)
def test_malformed_output(stdout):
    with pytest.raises(ProviderError, match="Malformed"):
        provider(FakeRun(stdout)).chat("m", [Message("user", "hi")])


def test_not_logged_in_is_auth_error():
    out = json.dumps({"is_error": True, "result": "Not logged in · Please run /login"})
    with pytest.raises(ProviderAuthError):
        provider(FakeRun(out, returncode=1)).chat("m", [Message("user", "hi")])


def test_other_cli_error_is_provider_error_not_auth():
    out = json.dumps({"is_error": True, "result": "overloaded"})
    with pytest.raises(ProviderError) as e:
        provider(FakeRun(out, returncode=1)).chat("m", [Message("user", "hi")])
    assert not isinstance(e.value, ProviderAuthError)


def test_nonzero_exit_without_output():
    with pytest.raises(ProviderError, match="code 2"):
        provider(FakeRun("", returncode=2)).chat("m", [Message("user", "hi")])


def test_timeout_and_missing_binary_at_runtime():
    with pytest.raises(ProviderError, match="timed out"):
        provider(FakeRun(raises=subprocess.TimeoutExpired("claude", 1))).chat(
            "m", [Message("user", "hi")]
        )
    with pytest.raises(ProviderError, match="Could not run"):
        provider(FakeRun(raises=FileNotFoundError("gone"))).chat("m", [Message("user", "hi")])


def test_binary_not_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    with pytest.raises(NotConfiguredError, match="not found"):
        ClaudeCliProvider()


def test_auth_is_verified_before_the_request_and_only_once():
    run = FakeRun(ok())
    p = provider(run)
    p.chat("m", [Message("user", "a")])
    p.chat("m", [Message("user", "b")])
    kinds = [c[0][1] for c in run.calls]
    assert kinds == ["auth", "-p", "-p"]


@pytest.mark.parametrize(
    "auth, match",
    [
        (json.dumps({"loggedIn": False}), "not logged in"),
        (
            json.dumps({"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"}),
            "api_key",
        ),
        (
            json.dumps({"loggedIn": True, "authMethod": "oauth_token", "apiProvider": "bedrock"}),
            "bedrock",
        ),
        (json.dumps({"loggedIn": True, "authMethod": "oauth_token"}), "provider"),
        (json.dumps({"loggedIn": True, "apiProvider": "firstParty"}), "None"),
        ("not json", "Malformed"),
        ("[]", "Malformed"),
    ],
)
def test_ineligible_auth_blocks_the_request(auth, match):
    run = FakeRun(ok(), auth=auth)
    with (
        pytest.raises(ProviderAuthError, match=f"(?i){match}")
        if match != "Malformed"
        else pytest.raises(ProviderError, match=match)
    ):
        provider(run).chat("m", [Message("user", "hi")])
    assert run.chat_calls() == []  # no model request was sent


def test_usage_limit_is_a_limit_error_not_auth():
    out = json.dumps({"is_error": True, "result": "5-hour limit reached ∙ resets 3pm"})
    with pytest.raises(ProviderLimitError):
        provider(FakeRun(out, returncode=1)).chat("m", [Message("user", "hi")])


def test_auth_check_timeout_is_a_provider_error():
    def slow(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 30)

    with pytest.raises(ProviderError, match="timed out"):
        provider(slow).chat("m", [Message("user", "hi")])


def test_disabled_by_default_and_enabled_explicitly(monkeypatch):
    with pytest.raises(ProviderDisabledError):
        get_provider("claude_cli")
    monkeypatch.setenv("NEBULA_AGENT_ENABLE", "claude_cli")
    monkeypatch.setenv("CLAUDE_CLI_PATH", "/usr/bin/claude")
    assert isinstance(get_provider("claude_cli"), ClaudeCliProvider)


def test_real_subprocess_is_blocked_in_tests():
    # No injected runner: the provider falls back to subprocess.run, which conftest blocks.
    with pytest.raises(RuntimeError, match="blocked"):
        ClaudeCliProvider(binary="/usr/bin/claude").chat("m", [Message("user", "hi")])
