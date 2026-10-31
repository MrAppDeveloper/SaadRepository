from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any

from nebula_agent.providers.base import (
    Message,
    NotConfiguredError,
    ProviderAuthError,
    ProviderError,
    ProviderLimitError,
    ProviderResponse,
    ToolSpec,
)

# Environment removed from the child process so `claude` cannot be pushed onto metered billing
# (Claude Code authentication precedence puts these above the subscription login).
SCRUBBED_PREFIXES = ("ANTHROPIC_",)  # API key, auth token, base URL, profile, federation, ...
SCRUBBED_EXACT = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")

# `claude auth status` authMethod values accepted as a subscription login. Anything else is
# refused (fail closed). "oauth_token" was observed; "claude.ai" is expected but unverified.
SUBSCRIPTION_AUTH_METHODS = ("oauth_token", "claude.ai")

LIMIT_HINTS = ("usage limit", "limit reached", "rate limit", "rate_limit", "quota")
LOGIN_HINTS = ("/login", "not logged in", "invalid api key", "authentication", "expired")


def scrubbed_env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(SCRUBBED_PREFIXES) and k not in SCRUBBED_EXACT
    }


def build_prompt(messages: list[Message]) -> str:
    """Flatten a text-only conversation into one prompt (sent on stdin)."""
    if any(m.role == "tool" or m.tool_calls for m in messages):
        raise ProviderError("claude_cli is text-only: tool calls and results are not supported.")
    if len(messages) == 1 and messages[0].role == "user":
        return messages[0].content
    return "\n\n".join(f"{m.role.capitalize()}: {m.content}" for m in messages)


def parse_output(stdout: str) -> ProviderResponse:
    try:
        data = json.loads(stdout)
        result = data["result"]
        if not isinstance(result, str):
            raise TypeError("result is not a string")
        is_error = bool(data.get("is_error"))
        stop = str(data.get("subtype") or "")
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise ProviderError(f"Malformed claude CLI output: {e}") from e
    if is_error:
        lowered = result.lower()
        if any(h in lowered for h in LIMIT_HINTS):
            raise ProviderLimitError(f"Claude usage limit reached: {result[:200]}")
        if any(h in lowered for h in LOGIN_HINTS):
            raise ProviderAuthError("claude CLI is not logged in. Run `claude auth login`.")
        raise ProviderError(f"claude CLI reported an error: {result[:200]}")
    return ProviderResponse(text=result, stop_reason=stop)


def parse_auth_status(stdout: str) -> None:
    """Raise unless the CLI reports a first-party subscription-style login."""
    try:
        data = json.loads(stdout)
        logged_in, method, api = (
            data.get("loggedIn"),
            data.get("authMethod"),
            data.get("apiProvider"),
        )
    except (ValueError, AttributeError) as e:
        raise ProviderError(f"Malformed `claude auth status` output: {e}") from e
    if logged_in is not True:
        raise ProviderAuthError("claude CLI is not logged in. Run `claude auth login`.")
    if api != "firstParty":
        raise ProviderAuthError(
            f"claude CLI routes through provider '{api}', not a subscription login; refusing."
        )
    if method not in SUBSCRIPTION_AUTH_METHODS:
        raise ProviderAuthError(
            f"claude CLI auth method '{method}' is not a recognized subscription login; "
            "refusing to avoid metered billing."
        )


class ClaudeCliProvider:
    """Text-only provider that runs `claude -p`, so usage draws from the user's Claude Code login
    (subscription limits) rather than API billing.

    Safeguards:
    - Before the first request, `claude auth status` must show a first-party subscription-style
      login; otherwise nothing is sent (fail closed).
    - Every ANTHROPIC_* variable and cloud-routing flag is removed from the child's environment.
    - All built-in Claude Code tools are disabled (`--tools ""`), MCP servers and slash commands
      are skipped, and only project-level settings are read from an empty temp directory, so the
      CLI cannot run commands, edit files or delegate to other agents.
    - The only things executed are the two fixed `claude` argv lists below (no shell); model
      output is never executed.
    - Failures raise; this class never falls back to another provider.
    """

    name = "claude_cli"

    def __init__(
        self,
        binary: str | None = None,
        runner: Callable[..., Any] | None = None,
        timeout: float = 120,
    ) -> None:
        self._binary = binary or os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude")
        if not self._binary:
            raise NotConfiguredError("`claude` CLI not found on PATH (set CLAUDE_CLI_PATH).")
        self._runner = runner
        self._timeout = timeout
        self._verified = False

    def _run(self, args: list[str], stdin: str | None, timeout: float) -> Any:
        run = self._runner or subprocess.run  # resolved per call so tests can block it
        try:
            with tempfile.TemporaryDirectory() as cwd:  # no project files or settings in scope
                return run(
                    [self._binary, *args],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=scrubbed_env(),
                    cwd=cwd,
                    check=False,
                )
        except subprocess.TimeoutExpired as e:
            raise ProviderError(f"claude CLI timed out after {timeout}s.") from e
        except OSError as e:
            raise ProviderError(f"Could not run claude CLI: {e}") from e

    def check_auth(self) -> None:
        """Verify login and eligibility without making a model request."""
        proc = self._run(["auth", "status", "--json"], None, 30)
        parse_auth_status(proc.stdout)
        self._verified = True

    def chat(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        if tools:
            raise ProviderError("claude_cli is text-only: tools are not supported.")
        prompt = build_prompt(messages)
        if not self._verified:
            self.check_auth()
        args = ["-p", "--output-format", "json", "--model", model]
        args += ["--tools", "", "--strict-mcp-config", "--disable-slash-commands"]
        args += ["--setting-sources", "project", "--no-session-persistence"]
        if system:
            args += ["--system-prompt", system]
        proc = self._run(args, prompt, self._timeout)
        if proc.returncode != 0 and not proc.stdout.strip():
            raise ProviderError(f"claude CLI exited with code {proc.returncode}.")
        return parse_output(proc.stdout)
