import json

from shared_memory.connect_agents import (
    SUPPORTED_HOSTS,
    claude_code_entry,
    connect,
    detect_hosts,
    merge_codex_toml,
    merge_mcp_json,
    private_write,
)


def always(_prompt):
    return True


def never(_prompt):
    return False


def test_detect_hosts_reports_only_binaries_on_path():
    which = {"claude": "/usr/bin/claude"}.get
    assert detect_hosts(which=which) == ["claude-code"]
    assert detect_hosts(which=lambda name: None) == []


def test_claude_code_entry_references_env_var_not_a_raw_token():
    entry = claude_code_entry("http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CLAUDE_CODE")
    assert entry["url"] == "http://127.0.0.1:8765/mcp"
    assert entry["headers"]["Authorization"] == "Bearer ${MEMORY_TOKEN_CLAUDE_CODE}"


def test_merge_mcp_json_creates_file_when_absent(tmp_path):
    path = tmp_path / ".mcp.json"
    entry = claude_code_entry("http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CLAUDE_CODE")
    result = merge_mcp_json(path, "shared-memory", entry, always)
    assert result["status"] == "written"
    data = json.loads(path.read_text())
    assert data["mcpServers"]["shared-memory"] == entry


def test_merge_mcp_json_preserves_existing_unrelated_servers(tmp_path):
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps({"mcpServers": {"other": {"type": "stdio"}}}))
    entry = claude_code_entry("http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CLAUDE_CODE")
    result = merge_mcp_json(path, "shared-memory", entry, always)
    assert result["status"] == "written"
    data = json.loads(path.read_text())
    assert data["mcpServers"]["other"] == {"type": "stdio"}
    assert data["mcpServers"]["shared-memory"] == entry


def test_merge_mcp_json_is_a_noop_when_entry_already_matches(tmp_path):
    path = tmp_path / ".mcp.json"
    entry = claude_code_entry("http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CLAUDE_CODE")
    path.write_text(json.dumps({"mcpServers": {"shared-memory": entry}}))
    before = path.read_text()
    result = merge_mcp_json(path, "shared-memory", entry, never)
    assert result["status"] == "unchanged"
    assert path.read_text() == before


def test_merge_mcp_json_never_overwrites_a_differing_entry(tmp_path):
    path = tmp_path / ".mcp.json"
    existing = {"type": "http", "url": "http://elsewhere:9999/mcp", "headers": {}}
    path.write_text(json.dumps({"mcpServers": {"shared-memory": existing}}))
    entry = claude_code_entry("http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CLAUDE_CODE")
    result = merge_mcp_json(path, "shared-memory", entry, always)
    assert result["status"] == "skipped"
    data = json.loads(path.read_text())
    assert data["mcpServers"]["shared-memory"] == existing


def test_merge_mcp_json_declines_without_confirmation(tmp_path):
    path = tmp_path / ".mcp.json"
    entry = claude_code_entry("http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CLAUDE_CODE")
    result = merge_mcp_json(path, "shared-memory", entry, never)
    assert result["status"] == "declined"
    assert not path.exists()


def test_merge_mcp_json_errors_on_invalid_json_without_modifying_it(tmp_path):
    path = tmp_path / ".mcp.json"
    path.write_text("{not json")
    entry = claude_code_entry("http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CLAUDE_CODE")
    result = merge_mcp_json(path, "shared-memory", entry, always)
    assert result["status"] == "error"
    assert path.read_text() == "{not json"


def test_merge_codex_toml_appends_when_absent(tmp_path):
    path = tmp_path / "config.toml"
    result = merge_codex_toml(
        path, "shared_memory", "http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CODEX", always
    )
    assert result["status"] == "written"
    text = path.read_text()
    assert "[mcp_servers.shared_memory]" in text
    assert 'bearer_token_env_var = "MEMORY_TOKEN_CODEX"' in text


def test_merge_codex_toml_preserves_existing_content_and_appends(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[mcp_servers.other]\nurl = "http://other/mcp"\nbearer_token_env_var = "X"\n')
    result = merge_codex_toml(
        path, "shared_memory", "http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CODEX", always
    )
    assert result["status"] == "written"
    text = path.read_text()
    assert "[mcp_servers.other]" in text
    assert "[mcp_servers.shared_memory]" in text


def test_merge_codex_toml_is_a_noop_when_table_already_matches(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[mcp_servers.shared_memory]\nurl = "http://127.0.0.1:8765/mcp"\n'
        'bearer_token_env_var = "MEMORY_TOKEN_CODEX"\n'
    )
    before = path.read_text()
    result = merge_codex_toml(
        path, "shared_memory", "http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CODEX", never
    )
    assert result["status"] == "unchanged"
    assert path.read_text() == before


def test_merge_codex_toml_never_rewrites_a_differing_table(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[mcp_servers.shared_memory]\nurl = "http://elsewhere/mcp"\nbearer_token_env_var = "OTHER"\n'
    )
    before = path.read_text()
    result = merge_codex_toml(
        path, "shared_memory", "http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CODEX", always
    )
    assert result["status"] == "skipped"
    assert path.read_text() == before


def test_merge_codex_toml_errors_on_invalid_toml_without_modifying_it(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("not = [valid toml")
    result = merge_codex_toml(
        path, "shared_memory", "http://127.0.0.1:8765/mcp", "MEMORY_TOKEN_CODEX", always
    )
    assert result["status"] == "error"
    assert path.read_text() == "not = [valid toml"


def test_connect_writes_both_hosts_and_never_embeds_a_raw_token_in_config(tmp_path):
    mcp_json = tmp_path / ".mcp.json"
    codex_toml = tmp_path / "config.toml"
    env_vars = {"claude-code": "MEMORY_TOKEN_CLAUDE_CODE", "codex": "MEMORY_TOKEN_CODEX"}

    def token_provider(host):
        return f"sm_secret_for_{host}", env_vars[host]

    outcome = connect(
        list(SUPPORTED_HOSTS),
        "http://127.0.0.1:8765/mcp",
        token_provider,
        always,
        mcp_json_path=mcp_json,
        codex_toml_path=codex_toml,
    )
    assert {r["host"]: r["status"] for r in outcome["results"]} == {
        "claude-code": "written",
        "codex": "written",
    }
    assert outcome["exports"] == [
        "export MEMORY_TOKEN_CLAUDE_CODE=sm_secret_for_claude-code",
        "export MEMORY_TOKEN_CODEX=sm_secret_for_codex",
    ]
    assert "sm_secret_for_claude-code" not in mcp_json.read_text()
    assert "sm_secret_for_codex" not in codex_toml.read_text()


def test_connect_rejects_unsupported_host():
    outcome = connect(["carrier-pigeon"], "http://x/mcp", lambda h: ("t", "V"), always)
    assert outcome["results"] == [
        {"host": "carrier-pigeon", "status": "error", "detail": "unsupported host"}
    ]


def test_private_write_is_atomic_and_restrictive(tmp_path):
    path = tmp_path / "nested" / "secrets.env"
    private_write(path, "export X=1\n")
    assert path.read_text() == "export X=1\n"
    mode = path.stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"expected no group/other permissions, got {oct(mode)}"


def test_cli_connect_agents_token_mode_needs_no_database(tmp_path):
    import json as _json
    import subprocess
    import sys

    mcp_json = tmp_path / ".mcp.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "shared_memory.cli",
            "connect-agents",
            "--token",
            "sm_test_token_value",
            "--host",
            "claude-code",
            "--url",
            "http://127.0.0.1:8765/mcp",
            "--mcp-json",
            str(mcp_json),
            "--yes",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    outcome = _json.loads(result.stdout)
    assert outcome["results"] == [
        {
            "host": "claude-code",
            "env_var": "MEMORY_TOKEN_CLAUDE_CODE",
            "status": "written",
            "path": str(mcp_json),
        }
    ]
    assert "sm_test_token_value" not in mcp_json.read_text()
    data = _json.loads(mcp_json.read_text())
    assert (
        data["mcpServers"]["shared-memory"]["headers"]["Authorization"]
        == "Bearer ${MEMORY_TOKEN_CLAUDE_CODE}"
    )


def test_cli_connect_agents_requires_token_or_workspace(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "shared_memory.cli",
            "connect-agents",
            "--host",
            "claude-code",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Provide --token" in result.stderr
