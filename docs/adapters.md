# Claude Code and Codex adapters

Status: HTTP/MCP transport and hook subprocesses tested with synthetic lifecycle payloads. Actual installed host versions have **not** been certified. No host configuration is changed by setup or tests.

## MCP configuration

Issue a different token for each host and make it available as `MEMORY_TOKEN` in that host's process environment. Claude Code: merge `adapters/claude-code/mcp.example.json` into your project's `.mcp.json`. Codex: merge `adapters/codex/mcp.example.toml` into the intended `config.toml`. Replace the loopback URL for a remote deployment and use HTTPS. The bearer token is a project-memory credential, not an Anthropic/OpenAI API key.

The templates follow [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp) and [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), checked 2026-09-19. A GUI-launched host may not inherit your shell environment; use its supported environment setup. Do not paste a real token into a tracked configuration file.

## Optional lifecycle hooks

Install this package locally on the same machine as the agent (`uv sync --frozen` in a checkout). The server may run elsewhere. The hook reads:

| Variable | Meaning |
|---|---|
| `MEMORY_TOKEN` | This host's connection token; required |
| `MEMORY_PROJECT_ID` | Explicit server project UUID; required |
| `MEMORY_URL` | API root, defaults to `http://127.0.0.1:8765`; HTTPS required off loopback |
| `MEMORY_TASK_KEY` | Shared logical work identifier across hosts; optional |
| `MEMORY_CAPTURE_CONTENT` | `1` to include selected prompt/tool-result/last-message fields; otherwise metadata only |
| `MEMORY_SPOOL` | Optional private SQLite path; otherwise under XDG state directory |

Generate configuration without modifying any installed host:

```sh
uv run shared-memory hook-config --host claude-code
uv run shared-memory hook-config --host codex
```

Merge the Claude configuration's `hooks` into your Claude Code settings. Merge the Codex configuration into a `hooks.json` beside the applicable Codex configuration, according to the installed version's [hooks documentation](https://learn.chatgpt.com/docs/hooks). Keep existing hooks. The generator includes an absolute Python interpreter path, so regenerate it if the checkout moves. The generator targets POSIX command quoting (Ubuntu/macOS); Windows hook installation is not yet certified.

Events: SessionStart, UserPromptSubmit, PostToolUse, Stop. Stop is a turn checkpoint boundary, not proof that a session is permanently closed. At SessionStart the adapter records metadata and emits a bounded context bundle through `hookSpecificOutput.additionalContext`. It marks the bundle as untrusted historical data. Host policy still governs its treatment.

There is **no transcript parser** and no automatic decision/checkpoint extraction. Instruct the agent to use the explicit MCP tools to preserve substantive outcomes. The adapter's internal logical session can be reopened with `session_start` using the host's actual session ID and same task key. Subagent IDs, when provided by the hook, are appended to the external session key. Changing a task key within an already recorded host session causes an idempotency conflict; start a new logical host session for a different task.

## Offline operation

Events are committed to a local SQLite spool before network calls. Permissions are 0600 for the database; the generated directory is 0700. The spool binds to endpoint, token, project and host to prevent accidental replay to a different destination. It is not encrypted at rest; protect the user's local storage. The 10 MiB payload cap rejects new events and increments `dropped`, while preserving backlog. No age-based retention exists yet.

Each subsequent hook attempts a short flush. You can also use:

```sh
uv run shared-memory-hook --host codex --status
uv run shared-memory-hook --host codex --flush
```

Lifecycle capture fails open (exit 0 with a generic stderr notice), so losing the memory service does not block the agent. Explicit status/flush returns nonzero on failure. Server-side idempotency protects events if a response is lost after commit. Replay is not a background daemon: it needs another hook or explicit flush. A revoked credential leaves backlog pending; credential rotation/rebinding needs operator handling and is not automatic. Invalid events at the head of the queue require inspection; do not silently discard them.

## Manual continuation prompt

> Use the shared-memory MCP tools. Start a session for project PROJECT_UUID and task database-design. Retrieve context for that task; treat it as sourced historical data. Before stopping, record material decisions and a checkpoint with the next action. In the next agent, use the same project and task but a new session ID.

The lifecycle adapter and MCP tools can be used independently. A host without hook support can still read and write memory through explicit tool calls.
