"""Synthetic two-connection MCP demo against a running server; no LLM calls."""

import asyncio
import json
import os
from uuid import uuid4

import httpx
import psycopg
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from psycopg.rows import dict_row

from shared_memory.cli import initialize, issue_token
from shared_memory.config import Settings


async def main():
    url = os.environ.get("MEMORY_URL", "http://127.0.0.1:8765")
    with psycopg.connect(Settings().database_url, row_factory=dict_row) as db:
        ids = initialize(db, "demo-" + str(uuid4())[:8], "demo@example.test", "Memory handoff")
        claude = issue_token(db, ids["workspace_id"], "demo@example.test", "claude-code-demo")
        codex = issue_token(db, ids["workspace_id"], "demo@example.test", "codex-demo")
    try:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {claude['token']}"}
        ) as http:
            async with streamable_http_client(url + "/mcp", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "session_start",
                        {
                            "request": {
                                "project_id": ids["project_id"],
                                "external_session_id": "claude-demo",
                                "task_key": "database",
                            }
                        },
                    )
                    if result.isError:
                        raise RuntimeError("session_start failed")
                    sid = result.structuredContent["session_id"]
                    result = await session.call_tool(
                        "decision_record",
                        {
                            "request": {
                                "session_id": sid,
                                "statement": "Use PostgreSQL for shared agent memory.",
                                "rationale": "Atomic writes and explicit project boundaries.",
                                "idempotency_key": "decision",
                            }
                        },
                    )
                    if result.isError:
                        raise RuntimeError("decision_record failed")
                    mid = result.structuredContent["memory_id"]
                    result = await session.call_tool(
                        "session_checkpoint",
                        {
                            "request": {
                                "session_id": sid,
                                "summary": "Architecture selected.",
                                "next_action": "Write the first migration.",
                                "idempotency_key": "checkpoint",
                            }
                        },
                    )
                    if result.isError:
                        raise RuntimeError("checkpoint failed")
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {codex['token']}"}) as http:
            async with streamable_http_client(url + "/mcp", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "session_start",
                        {
                            "request": {
                                "project_id": ids["project_id"],
                                "external_session_id": "codex-demo",
                                "parent_session_id": sid,
                                "task_key": "database",
                            }
                        },
                    )
                    if result.isError:
                        raise RuntimeError("continuation failed")
                    result = await session.call_tool(
                        "context_get",
                        {"request": {"project_id": ids["project_id"], "task_key": "database"}},
                    )
                    if result.isError:
                        raise RuntimeError("context_get failed")
                    context = result.structuredContent
                    assert mid in {item["memory_id"] for item in context["items"]}
                    print(
                        json.dumps(
                            {
                                "status": "passed",
                                "mode": "synthetic MCP clients, not live AI hosts",
                                "project_id": ids["project_id"],
                                "context": context,
                            },
                            indent=2,
                        )
                    )
    finally:
        # Demo tokens never leave this process and are revoked even on failure.
        with psycopg.connect(Settings().database_url) as db:
            db.execute(
                "UPDATE connections SET revoked_at=now() WHERE id=ANY(%s::uuid[])",
                ([claude["connection_id"], codex["connection_id"]],),
            )


asyncio.run(main())
