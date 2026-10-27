"""Claude Code provider: argv/env construction and result parsing. No CLI is spawned here."""

from __future__ import annotations

import json

import pytest

from app.llm.base import InvalidOutputError, PermanentProviderError, TransientProviderError
from app.llm.claude_code_adapter import (
    TOKEN_ENV,
    ClaudeCodeNotInstalledError,
    build_argv,
    build_env,
    parse_envelope,
    resolve_binary,
)

TOKEN = "sk-ant-oat01-test-token"
DRAFT = {
    "status": "answered",
    "answer": "SS304",
    "evidence": [{"fact_id": "mfg_record_A!Parts!C2", "quoted_value": "SS304"}],
    "computation": None,
    "general_knowledge": [],
    "missing_information": [],
    "confidence": "high",
    "reason": "stated",
}


def _envelope(**overrides) -> str:
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "api_error_status": None,
        "structured_output": DRAFT,
        "usage": {"input_tokens": 100, "cache_read_input_tokens": 50, "output_tokens": 20},
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_token_never_on_argv_and_env_is_an_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-leak")
    monkeypatch.setenv("CLAUDECODE", "1")
    argv = build_argv("claude.exe", "claude-opus-5-5", str(tmp_path / "sp.txt"))
    env = build_env(TOKEN, str(tmp_path))
    assert TOKEN not in " ".join(argv)
    assert env[TOKEN_ENV] == TOKEN
    assert "ANTHROPIC_API_KEY" not in env and "CLAUDECODE" not in env
    assert env["HOME"] == env["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
    assert json.loads(argv[argv.index("--json-schema") + 1])["type"] == "object"


def test_parses_structured_output_and_usage():
    draft, usage = parse_envelope(_envelope(), "", 0, "m")
    assert draft.status == "answered" and draft.evidence[0].fact_id == "mfg_record_A!Parts!C2"
    assert usage.input_tokens == 150 and usage.cached_tokens == 50 and usage.output_tokens == 20


def test_usage_limit_is_transient():
    with pytest.raises(TransientProviderError):
        parse_envelope(
            _envelope(subtype="success", api_error_status=429, structured_output=None), "", 0, "m"
        )


def test_bad_credential_is_permanent_and_not_echoed():
    with pytest.raises(PermanentProviderError) as exc:
        parse_envelope("", f"Failed to authenticate. API Error: 401 token {TOKEN}", 1, "m")
    assert TOKEN not in str(exc.value)


def test_missing_or_invalid_structured_output():
    with pytest.raises(InvalidOutputError):
        parse_envelope(_envelope(structured_output=None), "", 0, "m")
    with pytest.raises(InvalidOutputError):
        parse_envelope(_envelope(structured_output={"status": "nonsense"}), "", 0, "m")
    with pytest.raises(InvalidOutputError):
        parse_envelope(_envelope(subtype="error_max_turns", is_error=True), "", 1, "m")


def test_garbage_stdout_without_auth_hint_is_transient():
    with pytest.raises(TransientProviderError):
        parse_envelope("not json", "network error", 1, "m")


def test_npm_shim_resolves_to_bundled_native_binary(tmp_path, monkeypatch):
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off")
    native = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.write_text("")
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert resolve_binary(str(shim)) == str(native)


def test_missing_cli_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(ClaudeCodeNotInstalledError):
        resolve_binary(str(tmp_path / "nope.exe"))
