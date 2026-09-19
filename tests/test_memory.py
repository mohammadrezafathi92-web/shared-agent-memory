from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg

from shared_memory.service import DomainError


def event_body(session, key="event-1"):
    return {
        "session_id": session,
        "source_event_id": key,
        "event_type": "message",
        "occurred_at": "2026-09-19T10:00:00+00:00",
        "payload": {"text": "Choose PostgreSQL"},
    }


def test_handoff_with_sources(call, session, seed, client):
    event = call("event_append", event_body(session))
    decision = call(
        "decision_record",
        {
            "session_id": session,
            "statement": "Use PostgreSQL",
            "rationale": "Keep transactions and memory together",
            "idempotency_key": "d1",
            "source_ids": [event["event_id"]],
        },
    )
    call(
        "session_checkpoint",
        {
            "session_id": session,
            "summary": "Database selected",
            "next_action": "Implement migration",
            "idempotency_key": "cp1",
            "last_event_id": event["event_id"],
        },
    )
    continuation = call(
        "session_start",
        {
            "project_id": seed["project_id"],
            "task_key": "architecture",
            "external_session_id": "codex-session",
            "parent_session_id": session,
        },
        who="codex",
    )
    assert continuation["session_id"] != session
    context = call(
        "context_get", {"project_id": seed["project_id"], "task_key": "architecture"}, who="codex"
    )
    assert {i["kind"] for i in context["items"]} == {"decision", "checkpoint"}
    found = next(i for i in context["items"] if i["memory_id"] == decision["memory_id"])
    assert found["source_event_ids"] == [event["event_id"]]
    assert found["provenance_type"] == "agent_assertion"
    assert context["semantic_index"] == "not_enabled"
    source = client.get(
        f"/api/v1/events/{event['event_id']}",
        headers={"Authorization": f"Bearer {seed['codex']['token']}"},
    )
    assert source.status_code == 200


def test_replay_and_collision(call, session, seed):
    body = event_body(session)
    first = call("event_append", body)
    assert call("event_append", body)["event_id"] == first["event_id"]
    assert call("event_append", body)["duplicate"]
    call("event_append", dict(body, payload={"text": "different"}), expected=409)
    call(
        "session_start",
        {
            "project_id": seed["project_id"],
            "external_session_id": "claude-session",
            "task_key": "different",
        },
        expected=409,
    )


def test_concurrent_event_replay(call, app, seed, session):
    body = event_body(session, "concurrent")

    def invoke(_):
        return app.state.store.call("event_append", body, seed["claude"]["token"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(invoke, range(12)))
    assert len({r["event_id"] for r in results}) == 1
    assert sum(not r["duplicate"] for r in results) == 1


def test_isolation_scopes_and_revocation(call, client, seed, session, database_url):
    body = {"session_id": session, "statement": "Internal", "idempotency_key": "private"}
    memory = call("decision_record", body)
    call("memory_get", {"memory_id": memory["memory_id"]}, who="other", expected=404)
    call("memory_search", {"project_id": seed["project_id"]}, who="other", expected=404)
    call("memory_search", {"project_id": seed["private_project_id"]}, who="viewer", expected=404)
    call(
        "session_start",
        {"project_id": seed["project_id"], "external_session_id": "viewer"},
        who="viewer",
        expected=403,
    )
    call("event_append", event_body(session), who="codex", expected=404)
    assert (
        client.post(
            "/api/v1/tools/memory_search", json={"project_id": seed["project_id"]}
        ).status_code
        == 401
    )
    with psycopg.connect(database_url) as db:
        db.execute(
            "UPDATE connections SET revoked_at=now() WHERE id=%s",
            (seed["claude"]["connection_id"],),
        )
    call("memory_search", {"project_id": seed["project_id"]}, expected=401)


def test_explicit_revision_and_history(call, session, seed):
    first = call(
        "decision_record",
        {"session_id": session, "statement": "Use SQLite", "idempotency_key": "d1"},
    )
    revision = {
        "session_id": session,
        "statement": "Use PostgreSQL",
        "idempotency_key": "d2",
        "supersedes_id": first["memory_id"],
        "expected_version": 1,
    }
    second = call("decision_record", revision)
    assert second["version"] == 2
    assert call("decision_record", revision)["duplicate"]
    call("decision_record", dict(revision, idempotency_key="d3"), expected=409)
    rows = call("memory_search", {"project_id": seed["project_id"]})["items"]
    assert [r["memory_id"] for r in rows] == [second["memory_id"]]
    history = call("memory_search", {"project_id": seed["project_id"], "include_history": True})[
        "items"
    ]
    assert len(history) == 2 and history[1]["valid_to"]


def test_concurrent_revision_one_wins(call, app, seed, session):
    first = call(
        "decision_record",
        {"session_id": session, "statement": "Before", "idempotency_key": "before"},
    )

    def revise(n):
        try:
            app.state.store.call(
                "decision_record",
                {
                    "session_id": session,
                    "statement": f"After {n}",
                    "supersedes_id": first["memory_id"],
                    "expected_version": 1,
                    "idempotency_key": f"after-{n}",
                },
                seed["claude"]["token"],
            )
            return "ok"
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(revise, range(2)))
    assert sorted(results) == ["VERSION_CONFLICT", "ok"]


def test_foreign_source_and_cycle_rejected(call, session, seed):
    call(
        "decision_record",
        {
            "session_id": session,
            "statement": "No source",
            "source_ids": [str(uuid4())],
            "idempotency_key": "bad",
        },
        expected=404,
    )
    second = call(
        "session_start",
        {
            "project_id": seed["project_id"],
            "external_session_id": "child",
            "parent_session_id": session,
        },
    )["session_id"]
    call(
        "session_link",
        {"source_session_id": session, "target_session_id": second, "relation_type": "continues"},
        expected=409,
    )
    link = {"source_session_id": second, "target_session_id": session, "relation_type": "continues"}
    assert call("session_link", link)["linked"]
    assert call("session_link", link)["duplicate"]


def test_persian_search_task_filter_and_budget(call, session, seed):
    call(
        "decision_record",
        {"session_id": session, "statement": "يادگيري در شركت", "idempotency_key": "fa"},
    )
    result = call("memory_search", {"project_id": seed["project_id"], "query": "یادگیری شرکت"})
    assert len(result["items"]) == 1
    assert (
        call("context_get", {"project_id": seed["project_id"], "task_key": "other"})["items"] == []
    )
    small = call("context_get", {"project_id": seed["project_id"], "token_budget": 256})
    assert small["budget_used"] <= 256 and small["truncated"]
    assert call("memory_search", {"project_id": seed["project_id"], "query": "%"})["items"] == []


def test_validation_redaction_and_limits(call, client, session, seed):
    call("event_append", dict(event_body(session), occurred_at="2026-09-19T10:00:00"), expected=422)
    call("event_append", dict(event_body(session), payload={"x": "a" * 70000}), expected=422)
    body = dict(
        event_body(session),
        payload={"api_key": "secret", "text": "Bearer abcdefghijklmnopqrstuvwxyz"},
    )
    event = call("event_append", body)
    source = client.get(
        f"/api/v1/events/{event['event_id']}",
        headers={"Authorization": f"Bearer {seed['claude']['token']}"},
    ).json()
    assert source["payload"] == {"api_key": "[REDACTED]", "text": "[REDACTED]"}
    response = client.post(
        "/api/v1/tools/event_append",
        content=b"x" * 1_048_577,
        headers={"Authorization": f"Bearer {seed['claude']['token']}"},
    )
    assert response.status_code == 413


def test_data_survives_app_restart(database_url, seed):
    from fastapi.testclient import TestClient

    from shared_memory.app import create_app
    from shared_memory.config import Settings

    auth = {"Authorization": f"Bearer {seed['claude']['token']}"}
    with TestClient(create_app(Settings(database_url=database_url))) as first:
        sid = first.post(
            "/api/v1/tools/session_start",
            headers=auth,
            json={"project_id": seed["project_id"], "external_session_id": "persistent"},
        ).json()["session_id"]
        first.post(
            "/api/v1/tools/session_checkpoint",
            headers=auth,
            json={"session_id": sid, "summary": "Continue tomorrow", "idempotency_key": "persist"},
        ).raise_for_status()
    with TestClient(create_app(Settings(database_url=database_url))) as second:
        result = second.post(
            "/api/v1/tools/context_get", headers=auth, json={"project_id": seed["project_id"]}
        ).json()
        assert result["items"][0]["body"]["summary"] == "Continue tomorrow"
