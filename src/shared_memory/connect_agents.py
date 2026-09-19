"""Detect installed agent CLIs on this machine and wire them to this MCP server.

This is an explicit, on-demand admin action (``shared-memory connect-agents``),
not something setup or tests run automatically. It follows the same
conservative rule as ``hook-config`` and the installer's ``runtime.env``:
create a host configuration entry if it is absent, do nothing if an
identical one already exists, and never silently overwrite a differing one.
Nothing here reads a host's transcripts or touches anything but the two
files below.

Targets:

* Claude Code: ``mcpServers`` in a project's ``.mcp.json`` (default: the
  current working directory).
* Codex: ``mcp_servers`` in ``~/.codex/config.toml``. There is no safe
  stdlib TOML writer, so an existing file is only ever appended to, never
  rewritten in place.

A raw bearer token is never written into either configuration file; both
reference the token through a per-host environment variable name instead
(``MEMORY_TOKEN_CLAUDE_CODE``, ``MEMORY_TOKEN_CODEX``), matching the model
documented in docs/adapters.md. The caller is responsible for making that
environment variable available to the host process.
"""

import json
import os
import shlex
import shutil
import tempfile
import tomllib
from pathlib import Path

SUPPORTED_HOSTS = ("claude-code", "codex")

BINARY_NAMES = {
    "claude-code": "claude",
    "codex": "codex",
}

ENV_VAR_NAMES = {
    "claude-code": "MEMORY_TOKEN_CLAUDE_CODE",
    "codex": "MEMORY_TOKEN_CODEX",
}


def detect_hosts(which=shutil.which):
    """Return the supported hosts whose CLI binary is on PATH, in a stable order."""
    return [host for host in SUPPORTED_HOSTS if which(BINARY_NAMES[host])]


def private_write(path, text):
    """Atomically write ``text`` to ``path`` with restrictive permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".connect-agents-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def claude_code_entry(url, token_env_var):
    """The ``mcpServers.<name>`` object for Claude Code's ``.mcp.json``."""
    return {
        "type": "http",
        "url": url,
        "headers": {"Authorization": f"Bearer ${{{token_env_var}}}"},
    }


def merge_mcp_json(path, server_name, entry, ask):
    """Add ``entry`` under ``mcpServers.<server_name>`` in the ``.mcp.json`` at ``path``.

    ``ask(prompt) -> bool`` gates the write when the entry is genuinely new.
    Returns a dict with at least a ``status`` in
    {"written", "unchanged", "skipped", "declined", "error"}.
    """
    path = Path(path)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {
                "status": "error",
                "path": str(path),
                "detail": f"could not read existing file: {exc}",
            }
        if not isinstance(existing, dict):
            return {
                "status": "error",
                "path": str(path),
                "detail": "existing file is not a JSON object; not modified",
            }
    else:
        existing = {}
    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        return {
            "status": "error",
            "path": str(path),
            "detail": "existing mcpServers is not an object; not modified",
        }
    current = servers.get(server_name)
    if current == entry:
        return {"status": "unchanged", "path": str(path)}
    if current is not None:
        return {
            "status": "skipped",
            "path": str(path),
            "detail": f"an mcpServers.{server_name} entry already exists and differs; leaving it as-is",
        }
    if not ask(f"Add an mcpServers.{server_name} entry to {path}?"):
        return {"status": "declined", "path": str(path)}
    servers[server_name] = entry
    private_write(path, json.dumps(existing, indent=2, ensure_ascii=False) + "\n")
    return {"status": "written", "path": str(path)}


def merge_codex_toml(path, table_name, url, token_env_var, ask):
    """Append an ``[mcp_servers.<table_name>]`` table to the Codex ``config.toml`` at ``path``.

    Only ever appends: an existing, differing table is left untouched
    (there is no safe stdlib TOML writer to edit it in place). ``ask``
    and the return shape match :func:`merge_mcp_json`.
    """
    path = Path(path)
    existing_text = ""
    tables = {}
    if path.exists():
        try:
            existing_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return {
                "status": "error",
                "path": str(path),
                "detail": f"could not read existing file: {exc}",
            }
        try:
            tables = tomllib.loads(existing_text)
        except tomllib.TOMLDecodeError as exc:
            return {
                "status": "error",
                "path": str(path),
                "detail": f"existing file is not valid TOML ({exc}); not modified",
            }
    mcp_servers = tables.get("mcp_servers", {})
    if not isinstance(mcp_servers, dict):
        return {
            "status": "error",
            "path": str(path),
            "detail": "existing mcp_servers is not a table; not modified",
        }
    desired = {"url": url, "bearer_token_env_var": token_env_var}
    current = mcp_servers.get(table_name)
    if current == desired:
        return {"status": "unchanged", "path": str(path)}
    if current is not None:
        return {
            "status": "skipped",
            "path": str(path),
            "detail": f"an [mcp_servers.{table_name}] table already exists and differs; leaving it as-is",
        }
    if not ask(f"Append an [mcp_servers.{table_name}] table to {path}?"):
        return {"status": "declined", "path": str(path)}
    block = (
        f"[mcp_servers.{table_name}]\n"
        f"url = {json.dumps(url)}\n"
        f"bearer_token_env_var = {json.dumps(token_env_var)}\n"
    )
    prefix = existing_text
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix:
        prefix += "\n"  # blank line between existing content and the new table
    private_write(path, prefix + block)
    return {"status": "written", "path": str(path)}


def connect(hosts, url, token_provider, ask, mcp_json_path=None, codex_toml_path=None):
    """Wire each of ``hosts`` to ``url`` and return what happened, host by host.

    ``token_provider(host) -> (token, env_var_name)`` supplies the bearer
    token and the environment variable name it should be exported as;
    callers decide whether that token was freshly issued or supplied by
    the operator. Nothing here ever writes a raw token into a config file.

    Returns ``{"results": [...], "exports": ["export VAR=token", ...]}``.
    """
    if mcp_json_path is None:
        mcp_json_path = Path.cwd() / ".mcp.json"
    if codex_toml_path is None:
        codex_toml_path = Path.home() / ".codex" / "config.toml"
    results = []
    exports = []
    for host in hosts:
        if host not in SUPPORTED_HOSTS:
            results.append({"host": host, "status": "error", "detail": "unsupported host"})
            continue
        token, env_var = token_provider(host)
        exports.append(f"export {env_var}={shlex.quote(token)}")
        if host == "claude-code":
            entry = claude_code_entry(url, env_var)
            outcome = merge_mcp_json(mcp_json_path, "shared-memory", entry, ask)
        else:
            outcome = merge_codex_toml(codex_toml_path, "shared_memory", url, env_var, ask)
        results.append({"host": host, "env_var": env_var, **outcome})
    return {"results": results, "exports": exports}
