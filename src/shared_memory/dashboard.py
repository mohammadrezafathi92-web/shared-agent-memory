"""Project-scoped dashboard reads and explicit project creation."""

from contextlib import contextmanager
from uuid import UUID, uuid4

from fastapi import APIRouter, Query
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field

from .service import DomainError


class NewProject(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)


def dashboard_router(store, token_getter):
    router = APIRouter(prefix="/api/v1")

    @contextmanager
    def actor_db(write=False):
        with store.pool.connection() as db:
            actor = store.authenticate(db, token_getter())
            scope = "memory:write" if write else "memory:read"
            if scope not in actor["scopes"]:
                raise DomainError("FORBIDDEN", 403)
            yield db, actor

    @router.get("/me")
    def me():
        with actor_db() as (db, actor):
            user = db.execute("SELECT email FROM users WHERE id=%s", (actor["user_id"],)).fetchone()
            owner = db.execute(
                """SELECT 1 FROM project_members WHERE workspace_id=%s
                   AND user_id=%s AND role='owner' LIMIT 1""",
                (actor["workspace_id"], actor["user_id"]),
            ).fetchone()
            return {
                "email": user["email"],
                "connection_id": actor["id"],
                "host": actor["host"],
                "scopes": actor["scopes"],
                "can_create_project": bool(owner) and "memory:write" in actor["scopes"],
            }

    @router.post("/projects", status_code=201)
    def create_project(body: NewProject):
        try:
            with actor_db(write=True) as (db, actor):
                owner = db.execute(
                    """SELECT 1 FROM project_members WHERE workspace_id=%s
                       AND user_id=%s AND role='owner' LIMIT 1""",
                    (actor["workspace_id"], actor["user_id"]),
                ).fetchone()
                if not owner:
                    raise DomainError("FORBIDDEN", 403)
                pid = uuid4()
                db.execute(
                    "INSERT INTO projects(id,workspace_id,name) VALUES(%s,%s,%s)",
                    (pid, actor["workspace_id"], body.name),
                )
                db.execute(
                    "INSERT INTO project_members VALUES(%s,%s,%s,'owner')",
                    (actor["workspace_id"], pid, actor["user_id"]),
                )
                store.audit(db, actor, "project_create", pid)
            return {"id": pid, "name": body.name, "role": "owner"}
        except UniqueViolation:
            raise DomainError("PROJECT_NAME_EXISTS", 409) from None

    def sessions_query(db, project_id, limit=50, offset=0):
        return db.execute(
            """SELECT s.id,s.external_session_id,s.task_key,s.parent_session_id,s.created_at,
            c.host,s.connection_id,
            (SELECT count(*) FROM events e WHERE e.session_id=s.id) AS event_count,
            (SELECT count(*) FROM memories m WHERE m.session_id=s.id) AS memory_count,
            (SELECT body->>'summary' FROM memories m WHERE m.session_id=s.id AND kind='checkpoint'
                ORDER BY created_at DESC,id DESC LIMIT 1) AS summary
            FROM sessions s JOIN connections c ON c.id=s.connection_id WHERE s.project_id=%s
            ORDER BY s.created_at DESC,s.id DESC LIMIT %s OFFSET %s""",
            (project_id, limit, offset),
        ).fetchall()

    @router.get("/projects/{project_id}/overview")
    def overview(project_id: UUID):
        with actor_db() as (db, actor):
            store.authorize(db, actor, project_id)
            stats = db.execute(
                """SELECT
                (SELECT count(*) FROM sessions WHERE project_id=%s) AS sessions,
                (SELECT count(*) FROM memories WHERE project_id=%s AND valid_to IS NULL) AS memories,
                (SELECT count(*) FROM events WHERE project_id=%s) AS events,
                (SELECT count(DISTINCT connection_id) FROM sessions WHERE project_id=%s) AS connections""",
                (project_id, project_id, project_id, project_id),
            ).fetchone()
            memories = db.execute(
                """SELECT m.*,s.task_key FROM memories m JOIN sessions s ON s.id=m.session_id
                WHERE m.project_id=%s AND m.valid_to IS NULL ORDER BY m.created_at DESC,m.id DESC LIMIT 6""",
                (project_id,),
            ).fetchall()
            return {
                "stats": stats,
                "sessions": sessions_query(db, project_id, 5),
                "memories": [store.serialize_memory(db, m) for m in memories],
                "search_mode": "keyword",
            }

    @router.get("/projects/{project_id}/sessions")
    def sessions(
        project_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        with actor_db() as (db, actor):
            store.authorize(db, actor, project_id)
            total = db.execute(
                "SELECT count(*) AS n FROM sessions WHERE project_id=%s", (project_id,)
            ).fetchone()["n"]
            return {
                "items": sessions_query(db, project_id, limit, offset),
                "total": total,
                "next_offset": offset + limit if offset + limit < total else None,
            }

    @router.get("/sessions/{session_id}")
    def session_detail(
        session_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        with actor_db() as (db, actor):
            session = store.session(db, actor, session_id)
            host = db.execute(
                "SELECT host FROM connections WHERE id=%s", (session["connection_id"],)
            ).fetchone()["host"]
            total = db.execute(
                "SELECT count(*) AS n FROM events WHERE session_id=%s", (session_id,)
            ).fetchone()["n"]
            events = db.execute(
                """SELECT id,event_type,occurred_at,received_at,payload FROM events
                WHERE session_id=%s ORDER BY received_at DESC,id DESC LIMIT %s OFFSET %s""",
                (session_id, limit, offset),
            ).fetchall()
            memories = db.execute(
                """SELECT m.*,s.task_key FROM memories m JOIN sessions s ON s.id=m.session_id
                WHERE m.session_id=%s ORDER BY m.created_at DESC,m.id DESC LIMIT 100""",
                (session_id,),
            ).fetchall()
            role = db.execute(
                "SELECT role FROM project_members WHERE project_id=%s AND user_id=%s",
                (session["project_id"], actor["user_id"]),
            ).fetchone()["role"]
            return {
                "session": dict(session, host=host),
                "events": events,
                "events_total": total,
                "next_offset": offset + limit if offset + limit < total else None,
                "memories": [store.serialize_memory(db, m) for m in memories],
                "can_write": session["connection_id"] == actor["id"] and role != "viewer",
            }

    @router.get("/projects/{project_id}/graph")
    def graph(project_id: UUID):
        with actor_db() as (db, actor):
            store.authorize(db, actor, project_id)
            nodes = sessions_query(db, project_id, 100)
            ids = [node["id"] for node in nodes]
            edges = db.execute(
                """SELECT source_id,target_id,relation_type FROM session_links
                 WHERE project_id=%s AND source_id=ANY(%s) AND target_id=ANY(%s)""",
                (project_id, ids, ids),
            ).fetchall()
            pairs = {(e["source_id"], e["target_id"], e["relation_type"]) for e in edges}
            for node in nodes:
                pair = (node["id"], node["parent_session_id"], "continues")
                if node["parent_session_id"] in ids and pair not in pairs:
                    edges.append(
                        {"source_id": pair[0], "target_id": pair[1], "relation_type": pair[2]}
                    )
            total = db.execute(
                "SELECT count(*) AS n FROM sessions WHERE project_id=%s", (project_id,)
            ).fetchone()["n"]
            return {"nodes": nodes, "edges": edges, "truncated": total > len(nodes)}

    @router.get("/connections")
    def connections():
        with actor_db() as (db, actor):
            return db.execute(
                """SELECT c.id,c.host,c.scopes,c.created_at,c.revoked_at,
                (SELECT max(s.created_at) FROM sessions s JOIN project_members p ON p.project_id=s.project_id
                   WHERE s.connection_id=c.id AND p.user_id=%s) AS last_session_at
                FROM connections c WHERE c.user_id=%s AND c.workspace_id=%s ORDER BY c.created_at DESC""",
                (actor["user_id"], actor["user_id"], actor["workspace_id"]),
            ).fetchall()

    return router
