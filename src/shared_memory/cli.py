import argparse
import hashlib
import json
import secrets
import shlex
import sys
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from .config import Settings

SCOPES = ["memory:read", "memory:write", "session:write"]


def initialize(db, workspace, email, project):
    wid, uid, pid = uuid4(), uuid4(), uuid4()
    db.execute("INSERT INTO workspaces(id,name) VALUES(%s,%s)", (wid, workspace))
    db.execute("INSERT INTO users(id,workspace_id,email) VALUES(%s,%s,%s)", (uid, wid, email))
    db.execute("INSERT INTO projects(id,workspace_id,name) VALUES(%s,%s,%s)", (pid, wid, project))
    db.execute(
        "INSERT INTO project_members(workspace_id,project_id,user_id,role) VALUES(%s,%s,%s,'owner')",
        (wid, pid, uid),
    )
    return {"workspace_id": str(wid), "user_id": str(uid), "project_id": str(pid)}


def issue_token(db, workspace_id, email, host, scopes=None):
    user = db.execute(
        "SELECT id FROM users WHERE workspace_id=%s AND email=%s", (workspace_id, email)
    ).fetchone()
    if not user:
        raise ValueError("User does not exist in this workspace; grant project access first.")
    token, cid = "sm_" + secrets.token_urlsafe(32), uuid4()
    db.execute(
        "INSERT INTO connections(id,workspace_id,user_id,host,token_hash,scopes) VALUES(%s,%s,%s,%s,%s,%s)",
        (
            cid,
            workspace_id,
            user["id"],
            host,
            hashlib.sha256(token.encode()).hexdigest(),
            scopes if scopes is not None else SCOPES,
        ),
    )
    return {"connection_id": str(cid), "token": token}


def main():
    parser = argparse.ArgumentParser(
        description="Shared memory administration (requires database access)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="Installer provisioning; JSON on stdin, no secrets on stdout")
    init = sub.add_parser("init")
    init.add_argument("--workspace", required=True)
    init.add_argument("--email", required=True)
    init.add_argument("--project", required=True)
    project = sub.add_parser("create-project")
    project.add_argument("--workspace-id", required=True)
    project.add_argument("--email", required=True)
    project.add_argument("--name", required=True)
    grant = sub.add_parser("grant")
    grant.add_argument("--project-id", required=True)
    grant.add_argument("--email", required=True)
    grant.add_argument("--role", choices=["owner", "editor", "viewer"], default="editor")
    issue = sub.add_parser("issue-token")
    issue.add_argument("--workspace-id", required=True)
    issue.add_argument("--email", required=True)
    issue.add_argument("--host", required=True)
    issue.add_argument("--read-only", action="store_true")
    revoke = sub.add_parser("revoke")
    revoke.add_argument("--connection-id", required=True)
    hook = sub.add_parser("hook-config")
    hook.add_argument("--host", choices=["claude-code", "codex"], required=True)
    args = parser.parse_args()
    if args.command == "hook-config":
        cmd = shlex.join([sys.executable, "-m", "shared_memory.hook", "--host", args.host])
        print(
            json.dumps(
                {
                    "hooks": {
                        event: [{"hooks": [{"type": "command", "command": cmd, "timeout": 8}]}]
                        for event in ["SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"]
                    }
                },
                indent=2,
            )
        )
        return
    with psycopg.connect(Settings().database_url, row_factory=dict_row) as db:
        if args.command == "bootstrap":
            from .bootstrap import provision

            try:
                result = provision(db, json.loads(sys.stdin.read(16384)))
            except (ValueError, TypeError):
                raise SystemExit(
                    "Bootstrap input or existing installation identity is invalid; no changes committed."
                ) from None
        elif args.command == "init":
            result = initialize(db, args.workspace, args.email, args.project)
        elif args.command == "create-project":
            user = db.execute(
                "SELECT id FROM users WHERE workspace_id=%s AND email=%s",
                (args.workspace_id, args.email),
            ).fetchone()
            if not user:
                parser.error("Unknown user")
            pid = uuid4()
            db.execute(
                "INSERT INTO projects(id,workspace_id,name) VALUES(%s,%s,%s)",
                (pid, args.workspace_id, args.name),
            )
            db.execute(
                "INSERT INTO project_members VALUES(%s,%s,%s,'owner')",
                (args.workspace_id, pid, user["id"]),
            )
            result = {"project_id": str(pid)}
        elif args.command == "grant":
            project = db.execute(
                "SELECT workspace_id FROM projects WHERE id=%s", (args.project_id,)
            ).fetchone()
            if not project:
                parser.error("Unknown project")
            wid = project["workspace_id"]
            user = db.execute(
                """INSERT INTO users(id,workspace_id,email) VALUES(%s,%s,%s)
                       ON CONFLICT(workspace_id,email) DO UPDATE SET email=EXCLUDED.email RETURNING id""",
                (uuid4(), wid, args.email),
            ).fetchone()
            db.execute(
                """INSERT INTO project_members VALUES(%s,%s,%s,%s)
                       ON CONFLICT(project_id,user_id) DO UPDATE SET role=EXCLUDED.role""",
                (wid, args.project_id, user["id"], args.role),
            )
            result = {"user_id": str(user["id"]), "role": args.role}
        elif args.command == "issue-token":
            result = issue_token(
                db,
                args.workspace_id,
                args.email,
                args.host,
                ["memory:read"] if args.read_only else None,
            )
        else:
            row = db.execute(
                "UPDATE connections SET revoked_at=now() WHERE id=%s RETURNING id",
                (args.connection_id,),
            ).fetchone()
            result = {"revoked": bool(row)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
