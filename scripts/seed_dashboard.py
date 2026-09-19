"""Create isolated synthetic dashboard data; write credentials to a private file."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from shared_memory.cli import initialize, issue_token
from shared_memory.config import Settings
from shared_memory.service import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Refuse overwrite and reserve a private output before mutating the database.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    url = Settings().database_url
    with os.fdopen(fd, "w") as file:
        with psycopg.connect(url, row_factory=dict_row) as db:
            ids = initialize(
                db, "UI demo " + str(uuid4())[:8], "demo@example.test", "Agent Memory Platform"
            )
            hosts = [
                issue_token(db, ids["workspace_id"], "demo@example.test", host)
                for host in ("Claude Code", "Codex", "Dashboard")
            ]
        # Only the dashboard credential is exported; sample host credentials are revoked below.
        json.dump(dict(ids, **hosts[2]), file)
        store = Store(url)
        store.open()
        try:
            for task, names, statement in [
                (
                    "architecture",
                    ["Architecture review", "MCP implementation"],
                    "PostgreSQL stores shared memory.",
                ),
                (
                    "reliability",
                    ["Offline capture", "Session handoff"],
                    "Keep provenance with every decision.",
                ),
                (
                    "dashboard",
                    ["Dashboard planning", "Dashboard verification"],
                    "پنل فارسی و انگلیسی از یک API استفاده می‌کند.",
                ),
            ]:
                parent = None
                for index, name in enumerate(names):
                    token = hosts[index]["token"]
                    sid = store.call(
                        "session_start",
                        {
                            "project_id": ids["project_id"],
                            "external_session_id": name,
                            "task_key": task,
                            "parent_session_id": parent,
                        },
                        token,
                    )["session_id"]
                    event = store.call(
                        "event_append",
                        {
                            "session_id": sid,
                            "source_event_id": "demo-" + sid,
                            "event_type": "message",
                            "occurred_at": datetime.now(timezone.utc).isoformat(),
                            "payload": {"text": statement, "synthetic_demo": True},
                        },
                        token,
                    )
                    store.call(
                        "decision_record",
                        {
                            "session_id": sid,
                            "statement": statement,
                            "idempotency_key": "decision-" + sid,
                            "source_ids": [event["event_id"]],
                        },
                        token,
                    )
                    store.call(
                        "session_checkpoint",
                        {
                            "session_id": sid,
                            "summary": name + " complete",
                            "next_action": "Continue implementation",
                            "idempotency_key": "checkpoint-" + sid,
                        },
                        token,
                    )
                    parent = sid
        finally:
            store.close()
            with psycopg.connect(url) as db:
                db.execute(
                    "UPDATE connections SET revoked_at=now() WHERE id=ANY(%s::uuid[])",
                    ([host["connection_id"] for host in hosts[:2]],),
                )
    print(
        "Synthetic demo created. Credentials written privately; revoke the dashboard connection after use."
    )


if __name__ == "__main__":
    main()
