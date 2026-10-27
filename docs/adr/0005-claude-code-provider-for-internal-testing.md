---
status: accepted
date: 2026-10-27
---

# 0005 Claude Code CLI provider for internal testing on a personal subscription

## Context

The team tests internally on a personal Claude subscription before buying API credit. A
`claude setup-token` token (`sk-ant-oat01-...`) is issued for Claude Code: sent directly to the
Messages API as an OAuth bearer it is refused (instant 429 with no rate-limit headers, on every
model). The same token works when the official Claude Code CLI uses it.

## Decision

- Add a `claude_code` provider (`app/llm/claude_code_adapter.py`) that runs the official `claude`
  binary in print mode, modelled on the EM-AI-FACTORY implementation: prompt on stdin, token in
  `CLAUDE_CODE_OAUTH_TOKEN`, an allowlisted environment, a private temp HOME/config per call, no
  setting sources, MCP servers or tools, and `--json-schema` for the same `AnswerDraft` contract.
- On Windows the npm `claude.cmd` shim is bypassed for the native `claude.exe` the package ships,
  because cmd.exe re-parses arguments and would corrupt the JSON schema.
- CLI failures map onto the gateway's error types (usage limit is transient and falls back to Groq;
  a refused credential is permanent and surfaced). CLI output is never echoed into messages.
- It is opt-in (`LLM_PRIMARY_PROVIDER=claude_code`) and not shipped in the Docker image. Production
  uses `ANTHROPIC_API_KEY` with the regular Anthropic adapter. The app never impersonates Claude
  Code: the requests come from the real CLI.

## Consequences

Internal testing uses Claude without API credit. Each call carries the CLI's own overhead (about
7 to 10 s per answer). Usage counts against the person's subscription limits.
