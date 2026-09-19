"""Transactional, repeatable installer provisioning; only accessible through the operator CLI."""

import hashlib
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field


class BootstrapInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: UUID
    workspace: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    project: str = Field(min_length=1, max_length=100)
    token: str = Field(pattern=r"^sm_[A-Za-z0-9_-]{43}$")


def provision(db, raw):
    from .cli import SCOPES

    data = BootstrapInput.model_validate(raw)
    wid = data.installation_id
    uid, pid, cid = [uuid5(wid, kind) for kind in ("owner", "project", "dashboard")]
    digest = hashlib.sha256(data.token.encode()).hexdigest()
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(wid),))
    existing = db.execute("SELECT name FROM workspaces WHERE id=%s", (wid,)).fetchone()
    if existing:
        row = db.execute(
            """SELECT c.token_hash,c.revoked_at,u.email,p.name FROM connections c
               JOIN users u ON u.id=c.user_id JOIN projects p ON p.workspace_id=c.workspace_id
               WHERE c.id=%s AND u.id=%s AND p.id=%s""",
            (cid, uid, pid),
        ).fetchone()
        if not row or row["token_hash"] != digest or row["revoked_at"]:
            raise ValueError(
                "Installer identity differs or its credential was revoked; use operator CLI."
            )
        if (
            existing["name"] != data.workspace
            or row["email"] != data.email
            or row["name"] != data.project
        ):
            raise ValueError("Installer configuration differs from the existing database.")
    else:
        db.execute("INSERT INTO workspaces VALUES(%s,%s)", (wid, data.workspace))
        db.execute("INSERT INTO users VALUES(%s,%s,%s)", (uid, wid, data.email))
        db.execute("INSERT INTO projects VALUES(%s,%s,%s)", (pid, wid, data.project))
        db.execute("INSERT INTO project_members VALUES(%s,%s,%s,'owner')", (wid, pid, uid))
        db.execute(
            """INSERT INTO connections(id,workspace_id,user_id,host,token_hash,scopes)
               VALUES(%s,%s,%s,'dashboard',%s,%s)""",
            (cid, wid, uid, digest, SCOPES),
        )
    return {
        "workspace_id": str(wid),
        "user_id": str(uid),
        "project_id": str(pid),
        "connection_id": str(cid),
    }
