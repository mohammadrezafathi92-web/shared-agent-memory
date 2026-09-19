import asyncio
import json
import os
import subprocess
import sys

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from shared_memory.hook import Spool, make_event


def test_mcp_wire_handoff_and_auth(live_server, seed):
    async def exercise():
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {seed['claude']['token']}"}
        ) as http:
            async with streamable_http_client(live_server + "/mcp", http_client=http) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as mcp:
                    await mcp.initialize()
                    listed = await mcp.list_tools()
                    assert len(listed.tools) == 8
                    invalid = await mcp.call_tool(
                        "session_start",
                        {
                            "request": {
                                "project_id": "private-invalid-value",
                                "external_session_id": "x",
                            }
                        },
                    )
                    assert invalid.isError
                    assert "private-invalid-value" not in str(invalid.content)
                    start = await mcp.call_tool(
                        "session_start",
                        {
                            "request": {
                                "project_id": seed["project_id"],
                                "external_session_id": "wire-claude",
                                "task_key": "wire",
                            }
                        },
                    )
                    assert not start.isError, start
                    sid = start.structuredContent["session_id"]
                    result = await mcp.call_tool(
                        "decision_record",
                        {
                            "request": {
                                "session_id": sid,
                                "statement": "MCP end-to-end works",
                                "idempotency_key": "wire-decision",
                            }
                        },
                    )
                    assert not result.isError, result
                    memory_id = result.structuredContent["memory_id"]
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {seed['codex']['token']}"}
        ) as http:
            async with streamable_http_client(live_server + "/mcp", http_client=http) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as mcp:
                    await mcp.initialize()
                    result = await mcp.call_tool(
                        "context_get",
                        {"request": {"project_id": seed["project_id"], "task_key": "wire"}},
                    )
                    assert not result.isError, result
                    assert result.structuredContent["items"][0]["memory_id"] == memory_id
        async with httpx.AsyncClient() as http:
            assert (await http.post(live_server + "/mcp", json={})).status_code == 401

    asyncio.run(exercise())


def test_spool_offline_recovery_and_replay(live_server, seed, tmp_path):
    item = make_event(
        {"hook_event_name": "UserPromptSubmit", "session_id": "offline", "prompt": "private"},
        seed["project_id"],
        "offline-task",
    )
    assert "prompt" not in item["event"]["payload"]
    path = tmp_path / "spool.sqlite3"
    spool = Spool(path, "binding")
    spool.enqueue(item)

    def unavailable(request):
        raise httpx.ConnectError("offline")

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(unavailable)
    ) as client:
        with pytest.raises(httpx.ConnectError):
            spool.flush(client)
    assert spool.status()["pending"] == 1
    spool.close()
    spool = Spool(path, "binding")
    with httpx.Client(
        base_url=live_server, headers={"Authorization": f"Bearer {seed['claude']['token']}"}
    ) as client:
        assert spool.flush(client) == 1
        spool.enqueue(item)  # Simulate server commit followed by lost client acknowledgement.
        assert spool.flush(client) == 1
    assert spool.status() == {"pending": 0, "dropped": 0}
    assert path.stat().st_mode & 0o777 == 0o600
    spool.close()
    with pytest.raises(ValueError):
        Spool(path, "different-project")


def test_hook_subprocess_context_and_metadata(live_server, seed, tmp_path):
    with httpx.Client(
        base_url=live_server, headers={"Authorization": f"Bearer {seed['claude']['token']}"}
    ) as client:
        sid = client.post(
            "/api/v1/tools/session_start",
            json={
                "project_id": seed["project_id"],
                "external_session_id": "previous",
                "task_key": "demo",
            },
        ).json()["session_id"]
        client.post(
            "/api/v1/tools/session_checkpoint",
            json={
                "session_id": sid,
                "summary": "Ready for migration",
                "next_action": "Write SQL",
                "idempotency_key": "checkpoint",
            },
        ).raise_for_status()
    env = {
        **os.environ,
        "MEMORY_URL": live_server,
        "MEMORY_TOKEN": seed["codex"]["token"],
        "MEMORY_PROJECT_ID": seed["project_id"],
        "MEMORY_TASK_KEY": "demo",
        "MEMORY_SPOOL": str(tmp_path / "hook.sqlite3"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "shared_memory.hook", "--host", "codex"],
        input=json.dumps({"hook_event_name": "SessionStart", "session_id": "new-codex"}),
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0 and not result.stderr
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Write SQL" in context and "untrusted" in context


def test_hook_capture_is_bounded_and_separates_subagents():
    item = make_event(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "root",
            "agent_id": "child",
            "tool_response": {"api_key": "secret"},
        },
        "project",
        None,
        True,
    )
    assert item["session"]["external_session_id"] == "root:agent:child"
    assert item["event"]["payload"]["tool_response"]["api_key"] == "[REDACTED]"
    with pytest.raises(ValueError):
        make_event({"hook_event_name": "Unknown", "session_id": "root"}, "project", None)
