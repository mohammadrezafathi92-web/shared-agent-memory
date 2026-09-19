"""One authorization and transaction boundary for REST and MCP."""

import hashlib
import json
import re
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .contracts import CONTRACTS, MemorySearch


class DomainError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def fingerprint(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def normalize(value):
    return " ".join(value.lower().translate(str.maketrans("يك\u200c", "یک ")).split())


def redact(value):
    """Best effort only. Do not collect secrets; this is not a DLP guarantee."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"password|secret|token|api.?key|authorization", k, re.I)
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return re.sub(
            r"\b(?:sk-[\w-]{12,}|sm_[\w-]{20,}|Bearer\s+[\w.\-]{12,})",
            "[REDACTED]",
            value,
            flags=re.I,
        )
    return value


class Store:
    def __init__(self, database_url):
        self.pool = ConnectionPool(
            database_url, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
        )

    def open(self):
        self.pool.open(wait=True, timeout=20)

    def close(self):
        self.pool.close()

    def authenticate(self, db, token):
        if not token:
            raise DomainError("UNAUTHORIZED", 401)
        row = db.execute(
            "SELECT * FROM connections WHERE token_hash=%s AND revoked_at IS NULL",
            (hashlib.sha256(token.encode()).hexdigest(),),
        ).fetchone()
        if not row:
            raise DomainError("UNAUTHORIZED", 401)
        return row

    def authorize(self, db, actor, project_id, write=False):
        row = db.execute(
            "SELECT role FROM project_members WHERE project_id=%s AND user_id=%s AND workspace_id=%s",
            (project_id, actor["user_id"], actor["workspace_id"]),
        ).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404)
        if write and row["role"] == "viewer":
            raise DomainError("FORBIDDEN", 403)

    def session(self, db, actor, session_id, write=False):
        row = db.execute(
            "SELECT * FROM sessions WHERE id=%s AND workspace_id=%s",
            (session_id, actor["workspace_id"]),
        ).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404)
        self.authorize(db, actor, row["project_id"], write)
        if write and row["connection_id"] != actor["id"]:
            raise DomainError("NOT_FOUND", 404)
        return row

    def call(self, name, raw, token):
        if name not in CONTRACTS:
            raise DomainError("NOT_FOUND", 404)
        req = CONTRACTS[name].model_validate(raw)
        with self.pool.connection() as db:
            actor = self.authenticate(db, token)
            scope = (
                "memory:read"
                if name in ("memory_search", "memory_get", "context_get")
                else "memory:write"
                if name == "decision_record"
                else "session:write"
            )
            if scope not in actor["scopes"]:
                raise DomainError("FORBIDDEN", 403)
            result = getattr(self, name)(db, actor, req)
        return result

    def audit(self, db, actor, action, target):
        db.execute(
            "INSERT INTO audit(workspace_id,connection_id,action,target_id) VALUES(%s,%s,%s,%s)",
            (actor["workspace_id"], actor["id"], action, target),
        )

    def lock(self, db, key):
        # Transaction-scoped locks serialize idempotency checks and concurrent graph changes.
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(key),))

    def session_start(self, db, actor, req):
        self.authorize(db, actor, req.project_id, True)
        self.lock(db, f"session:{actor['id']}:{req.external_session_id}")
        old = db.execute(
            "SELECT * FROM sessions WHERE connection_id=%s AND external_session_id=%s",
            (actor["id"], req.external_session_id),
        ).fetchone()
        if old:
            if any(
                old[k] != getattr(req, k) for k in ("project_id", "task_key", "parent_session_id")
            ):
                raise DomainError("IDEMPOTENCY_CONFLICT", 409)
            return {"session_id": str(old["id"]), "duplicate": True, "capture_mode": "explicit"}
        if req.parent_session_id:
            parent = self.session(db, actor, req.parent_session_id)
            if parent["project_id"] != req.project_id:
                raise DomainError("NOT_FOUND", 404)
        sid = uuid4()
        db.execute(
            """INSERT INTO sessions(id,workspace_id,project_id,connection_id,external_session_id,
                   task_key,parent_session_id) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (
                sid,
                actor["workspace_id"],
                req.project_id,
                actor["id"],
                req.external_session_id,
                req.task_key,
                req.parent_session_id,
            ),
        )
        self.audit(db, actor, "session_start", sid)
        return {"session_id": str(sid), "duplicate": False, "capture_mode": "explicit"}

    def event_append(self, db, actor, req):
        session = self.session(db, actor, req.session_id, True)
        clean = redact(req.model_dump(mode="json"))
        digest = fingerprint(clean)
        self.lock(db, f"event:{actor['id']}:{req.source_event_id}")
        old = db.execute(
            "SELECT id,content_hash FROM events WHERE connection_id=%s AND source_event_id=%s",
            (actor["id"], req.source_event_id),
        ).fetchone()
        if old:
            if old["content_hash"] != digest:
                raise DomainError("IDEMPOTENCY_CONFLICT", 409)
            return {"event_id": str(old["id"]), "duplicate": True, "processing_status": "stored"}
        eid = uuid4()
        db.execute(
            """INSERT INTO events(id,workspace_id,project_id,session_id,connection_id,source_event_id,
                   event_type,occurred_at,payload,content_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                eid,
                actor["workspace_id"],
                session["project_id"],
                req.session_id,
                actor["id"],
                req.source_event_id,
                req.event_type,
                req.occurred_at,
                Jsonb(clean["payload"]),
                digest,
            ),
        )
        self.audit(db, actor, "event_append", eid)
        return {"event_id": str(eid), "duplicate": False, "processing_status": "stored"}

    def save_memory(self, db, actor, req, kind, body, source_ids, supersedes=None, expected=None):
        session = self.session(db, actor, req.session_id, True)
        clean = redact(req.model_dump(mode="json"))
        digest = fingerprint(clean)
        self.lock(db, f"memory:{actor['id']}:{req.idempotency_key}")
        old = db.execute(
            "SELECT * FROM memories WHERE connection_id=%s AND idempotency_key=%s",
            (actor["id"], req.idempotency_key),
        ).fetchone()
        if old:
            if old["content_hash"] != digest or old["kind"] != kind:
                raise DomainError("IDEMPOTENCY_CONFLICT", 409)
            return {"memory_id": str(old["id"]), "version": old["version"], "duplicate": True}
        for source in set(source_ids):
            found = db.execute(
                "SELECT id FROM events WHERE id=%s AND session_id=%s AND workspace_id=%s",
                (source, req.session_id, actor["workspace_id"]),
            ).fetchone()
            if not found:
                raise DomainError("NOT_FOUND", 404)
        version = 1
        if supersedes:
            previous = db.execute(
                """SELECT m.*,s.task_key FROM memories m JOIN sessions s ON s.id=m.session_id
                   WHERE m.id=%s AND m.project_id=%s AND m.workspace_id=%s FOR UPDATE OF m""",
                (supersedes, session["project_id"], actor["workspace_id"]),
            ).fetchone()
            if not previous:
                raise DomainError("NOT_FOUND", 404)
            if (
                previous["kind"] != kind
                or previous["valid_to"]
                or expected != previous["version"]
                or previous["task_key"] != session["task_key"]
            ):
                raise DomainError("VERSION_CONFLICT", 409)
            version = previous["version"] + 1
            db.execute("UPDATE memories SET valid_to=now() WHERE id=%s", (supersedes,))
        elif expected is not None:
            raise DomainError("INVALID_ARGUMENT")
        mid = uuid4()
        body = redact(body)
        db.execute(
            """INSERT INTO memories(id,workspace_id,project_id,session_id,connection_id,kind,body,
          search_text,idempotency_key,content_hash,version,supersedes_id,provenance_type)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                mid,
                actor["workspace_id"],
                session["project_id"],
                req.session_id,
                actor["id"],
                kind,
                Jsonb(body),
                normalize(json.dumps(body, ensure_ascii=False)),
                req.idempotency_key,
                digest,
                version,
                supersedes,
                "agent_assertion",
            ),
        )
        for source in set(source_ids):
            db.execute(
                "INSERT INTO memory_sources(workspace_id,project_id,memory_id,event_id) VALUES(%s,%s,%s,%s)",
                (actor["workspace_id"], session["project_id"], mid, source),
            )
        self.audit(db, actor, kind, mid)
        return {
            "memory_id": str(mid),
            "version": version,
            "duplicate": False,
            "provenance_type": "agent_assertion",
        }

    def decision_record(self, db, actor, req):
        return self.save_memory(
            db,
            actor,
            req,
            "decision",
            {"statement": req.statement, "rationale": req.rationale},
            req.source_ids,
            req.supersedes_id,
            req.expected_version,
        )

    def session_checkpoint(self, db, actor, req):
        return self.save_memory(
            db,
            actor,
            req,
            "checkpoint",
            {
                "summary": req.summary,
                "open_items": req.open_items,
                "next_action": req.next_action,
                "last_event_id": str(req.last_event_id) if req.last_event_id else None,
            },
            [req.last_event_id] if req.last_event_id else [],
        )

    def serialize_memory(self, db, row):
        sources = db.execute(
            "SELECT event_id FROM memory_sources WHERE memory_id=%s ORDER BY event_id", (row["id"],)
        ).fetchall()
        return {
            "memory_id": str(row["id"]),
            "session_id": str(row["session_id"]),
            "project_id": str(row["project_id"]),
            "task_key": row.get("task_key"),
            "kind": row["kind"],
            "body": row["body"],
            "version": row["version"],
            "valid_from": row["valid_from"].isoformat(),
            "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
            "supersedes_id": str(row["supersedes_id"]) if row["supersedes_id"] else None,
            "provenance_type": row["provenance_type"],
            "source_event_ids": [str(s["event_id"]) for s in sources],
        }

    def memory_search(self, db, actor, req):
        self.authorize(db, actor, req.project_id)
        terms = normalize(req.query).split()[:20]
        clauses = ["m.project_id=%s", "m.workspace_id=%s"]
        args = [req.project_id, actor["workspace_id"]]
        if not req.include_history:
            clauses.append("m.valid_to IS NULL")
        if req.task_key is not None:
            clauses.append("s.task_key=%s")
            args.append(req.task_key)
        for term in terms:
            clauses.append("strpos(m.search_text,%s)>0")
            args.append(term)
        args.append(req.limit + 1)
        rows = db.execute(
            "SELECT m.*,s.task_key FROM memories m JOIN sessions s ON s.id=m.session_id WHERE "
            + " AND ".join(clauses)
            + " ORDER BY m.created_at DESC,m.id LIMIT %s",
            args,
        ).fetchall()
        return {
            "items": [self.serialize_memory(db, r) for r in rows[: req.limit]],
            "truncated": len(rows) > req.limit,
            "search_mode": "keyword",
            "semantic_index": "not_enabled",
        }

    def memory_get(self, db, actor, req):
        row = db.execute(
            """SELECT m.*,s.task_key FROM memories m JOIN sessions s ON s.id=m.session_id
                          WHERE m.id=%s AND m.workspace_id=%s""",
            (req.memory_id, actor["workspace_id"]),
        ).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404)
        self.authorize(db, actor, row["project_id"])
        return self.serialize_memory(db, row)

    def context_get(self, db, actor, req):
        search = MemorySearch(
            project_id=req.project_id, task_key=req.task_key, query=req.query, limit=100
        )
        result = self.memory_search(db, actor, search)
        # UTF-8 bytes provide a deliberately conservative budget for byte-based LLM tokenizers.
        # No claim of an exact provider token count. Keep whole evidence records, never cut source IDs.
        selected, used = [], 0
        truncated = result["truncated"]
        seen_checkpoints = set()
        for item in result["items"]:
            if item["kind"] == "checkpoint":
                if item["session_id"] in seen_checkpoints:
                    continue
                seen_checkpoints.add(item["session_id"])
            size = len(json.dumps(item, ensure_ascii=False).encode())
            if used + size > req.token_budget:
                truncated = True
                continue
            selected.append(item)
            used += size
        return {
            "items": selected,
            "content_trust": "untrusted_source_data",
            "budget_method": "utf8_bytes_conservative",
            "budget_used": used,
            "truncated": truncated,
            "search_mode": "keyword",
            "semantic_index": "not_enabled",
            "conflict_detection": "explicit_supersession_only",
        }

    def session_link(self, db, actor, req):
        source = self.session(db, actor, req.source_session_id, True)
        target = self.session(db, actor, req.target_session_id)
        if (
            source["project_id"] != target["project_id"]
            or req.source_session_id == req.target_session_id
        ):
            raise DomainError("INVALID_ARGUMENT")
        self.lock(db, f"graph:{source['project_id']}")
        if req.relation_type != "references":
            cycle = db.execute(
                """WITH RECURSIVE edges AS (
                SELECT source_id,target_id FROM session_links WHERE project_id=%s AND relation_type!='references'
                UNION SELECT id,parent_session_id FROM sessions WHERE project_id=%s AND parent_session_id IS NOT NULL
              ), reach(id) AS (
                SELECT %s::uuid UNION SELECT e.target_id FROM edges e JOIN reach r ON e.source_id=r.id
              ) SELECT 1 FROM reach WHERE id=%s""",
                (
                    source["project_id"],
                    source["project_id"],
                    req.target_session_id,
                    req.source_session_id,
                ),
            ).fetchone()
            if cycle:
                raise DomainError("CYCLE_DETECTED", 409)
        inserted = db.execute(
            """INSERT INTO session_links(workspace_id,project_id,source_id,target_id,relation_type)
                      VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING source_id""",
            (
                actor["workspace_id"],
                source["project_id"],
                req.source_session_id,
                req.target_session_id,
                req.relation_type,
            ),
        ).fetchone()
        if inserted:
            self.audit(db, actor, "session_link", req.source_session_id)
        return {"linked": True, "duplicate": not bool(inserted)}
