"""Claude via the official Claude Code CLI, on a person's own subscription (internal testing only).

A ``claude setup-token`` token (``sk-ant-oat01-...``) is issued for Claude Code, and the API
refuses it for direct calls. Running the official ``claude`` binary in print mode with the token
in ``CLAUDE_CODE_OAUTH_TOKEN`` is the documented headless use of that token. Production uses
``ANTHROPIC_API_KEY`` and the regular Anthropic adapter.

Isolation rules, adapted from the EM-AI-FACTORY ``claude_code`` provider:

- The prompt goes on stdin and the token in the environment, never on argv (argv is visible in
  process listings, and Windows caps a command line at 32,767 characters).
- The environment is an allowlist, not a copy of ``os.environ``: an inherited
  ``ANTHROPIC_API_KEY`` or a parent Claude Code session's variables must not decide what this
  call runs on.
- Every call gets a private temp directory as HOME, CLAUDE_CONFIG_DIR and cwd, with no setting
  sources, no MCP servers and no tools, so nothing on the host (CLAUDE.md, hooks, plugins)
  reaches it.
- The CLI's own text is never interpolated into error messages, because it can echo the token.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.llm.base import (
    InvalidOutputError,
    PermanentProviderError,
    Prompt,
    ProviderResult,
    RefusalError,
    TransientProviderError,
    Usage,
)
from app.llm.schemas import AnswerDraft

TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"  # noqa: S105 - an env var name, not a secret
PASSTHROUGH_ENV = (
    "PATH",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    # Without these, claude.exe on Windows exits at startup with no output.
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
)
BLOCKED_TOOLS = ("DesignSync", "PushNotification", "RemoteTrigger")
# Structured output takes a few turns inside the CLI (it refuses fewer than three).
MAX_TURNS = 6
_SCHEMA = json.dumps(AnswerDraft.model_json_schema(), separators=(",", ":"))
_SHIMS = (".cmd", ".bat", ".ps1")


class ClaudeCodeNotInstalledError(RuntimeError):
    pass


def resolve_binary(configured: str | None) -> str:
    """The native ``claude`` executable.

    On Windows an npm ``claude.cmd`` shim is not used: cmd.exe re-parses its arguments, so the
    JSON schema's quotes and the empty ``--tools ""`` would not reach the CLI intact. The npm
    package ships the native binary next to the shim, so that is found and used instead.
    """
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    for name in ("claude.exe", "claude"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for found in list(candidates):
        if found.lower().endswith(_SHIMS) or (
            sys.platform == "win32" and not found.lower().endswith(".exe")
        ):
            native = (
                Path(found).parent
                / "node_modules"
                / "@anthropic-ai"
                / "claude-code"
                / "bin"
                / "claude.exe"
            )
            if native.exists():
                candidates.insert(0, str(native))
    for path in candidates:
        lowered = path.lower()
        if Path(path).exists() and not lowered.endswith(_SHIMS):
            if sys.platform == "win32" and not lowered.endswith(".exe"):
                continue
            return path
    raise ClaudeCodeNotInstalledError(
        "the Claude Code CLI was not found; install it (https://claude.ai/install.ps1 on Windows) "
        "or set CLAUDE_CODE_BIN to the native claude executable"
    )


def build_env(token: str, home: str) -> dict[str, str]:
    env = {name: os.environ[name] for name in PASSTHROUGH_ENV if name in os.environ}
    env.update(HOME=home, USERPROFILE=home, CLAUDE_CONFIG_DIR=home)
    env[TOKEN_ENV] = token
    return env


def build_argv(binary: str, model: str, system_prompt_file: str) -> list[str]:
    return [
        binary,
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--tools",
        "",  # no filesystem, shell or network tools
        "--setting-sources",
        "",  # no user/project settings, CLAUDE.md, hooks or plugins
        "--strict-mcp-config",
        "--no-session-persistence",
        "--max-turns",
        str(MAX_TURNS),
        "--disallowedTools",
        ",".join(BLOCKED_TOOLS),
        "--system-prompt-file",
        system_prompt_file,
        "--json-schema",
        _SCHEMA,
    ]


def parse_envelope(
    stdout: str, stderr: str, exit_code: int, model: str
) -> tuple[AnswerDraft, Usage]:
    """The CLI's JSON result envelope as a draft, or the normalised error its failure deserves."""
    try:
        payload = json.loads(stdout)
        if not isinstance(payload, dict):
            raise ValueError
    except ValueError:
        # Classify from stderr only, and never echo it: it can contain the token.
        text = stderr.lower()
        if "401" in text or "403" in text or "not logged in" in text or "invalid" in text:
            raise PermanentProviderError(
                f"Claude Code refused the credential for {model}; check CLAUDE_CODE_OAUTH_TOKEN"
            ) from None
        raise TransientProviderError(f"Claude Code CLI failed (exit {exit_code})") from None

    status = payload.get("api_error_status")
    if payload.get("is_error") or payload.get("subtype") != "success" or status:
        if status == 429:
            raise TransientProviderError("Claude Code reported a usage or rate limit")
        if status in (401, 403):
            raise PermanentProviderError(
                f"Claude Code refused the credential for {model}; check CLAUDE_CODE_OAUTH_TOKEN"
            )
        if payload.get("subtype") == "error_max_turns":
            raise InvalidOutputError(
                f"Claude Code used {MAX_TURNS} turns without a structured answer"
            )
        if payload.get("stop_reason") == "refusal":
            raise RefusalError("the model declined to answer this request")
        raise TransientProviderError(f"Claude Code call failed (status {status or exit_code})")

    structured = payload.get("structured_output")
    if structured is None:
        raise InvalidOutputError("Claude Code returned no structured output")
    try:
        draft = AnswerDraft.model_validate(structured)
    except ValidationError as exc:
        raise InvalidOutputError(f"Claude Code output failed validation: {exc}") from exc
    raw = payload.get("usage") or {}
    cache_read = raw.get("cache_read_input_tokens") or 0
    usage = Usage(
        input_tokens=(raw.get("input_tokens") or 0)
        + cache_read
        + (raw.get("cache_creation_input_tokens") or 0),
        output_tokens=raw.get("output_tokens"),
        cached_tokens=cache_read,
    )
    return draft, usage


class ClaudeCodeProvider:
    name = "claude-code"

    def __init__(self, token: str, model: str, binary: str, timeout_s: float = 180.0) -> None:
        self.model = model
        self._token = token
        self._binary = binary
        self._timeout_s = timeout_s

    def _run(self, prompt: Prompt) -> tuple[str, str, int]:
        with tempfile.TemporaryDirectory(prefix="cnc-claude-code-") as home:
            system_file = Path(home) / "system-prompt.txt"
            system_file.write_text(prompt.system, encoding="utf-8")
            try:
                proc = subprocess.run(  # noqa: S603 - fixed binary, argv built here, no shell
                    build_argv(self._binary, self.model, str(system_file)),
                    input=prompt.user,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=build_env(self._token, home),
                    cwd=home,
                    timeout=self._timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise TransientProviderError(
                    f"Claude Code did not answer within {self._timeout_s:.0f}s"
                ) from None
            return proc.stdout, proc.stderr, proc.returncode

    async def answer(self, prompt: Prompt) -> ProviderResult:
        # A worker thread rather than asyncio subprocesses: those need the Proactor loop on Windows,
        # which uvicorn does not use under --reload. subprocess.run also kills the child on timeout.
        stdout, stderr, code = await asyncio.to_thread(self._run, prompt)
        draft, usage = parse_envelope(stdout, stderr, code, self.model)
        return ProviderResult(draft=draft, model=self.model, usage=usage)
