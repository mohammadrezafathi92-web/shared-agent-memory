import re
from uuid import uuid4

import pytest
from conftest import headers


def test_dashboard_isolation_and_scopes(client, seed, call, session):
    call(
        "decision_record",
        {"session_id": session, "statement": "Private decision", "idempotency_key": "dashboard"},
    )
    paths = [
        f"/api/v1/projects/{seed['project_id']}/overview",
        f"/api/v1/projects/{seed['project_id']}/sessions",
        f"/api/v1/projects/{seed['project_id']}/graph",
        f"/api/v1/sessions/{session}",
    ]
    for path in paths:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=headers(seed["other"]["token"])).status_code == 404
        assert client.get(path, headers=headers(seed["viewer"]["token"])).status_code == 200
    for endpoint in ("overview", "sessions", "graph"):
        assert (
            client.get(
                f"/api/v1/projects/{seed['private_project_id']}/{endpoint}",
                headers=headers(seed["viewer"]["token"]),
            ).status_code
            == 404
        )
    me = client.get("/api/v1/me", headers=headers(seed["claude"]["token"])).json()
    assert me["can_create_project"]
    connections = client.get("/api/v1/connections", headers=headers(seed["claude"]["token"])).json()
    assert {c["id"] for c in connections} == {
        seed["claude"]["connection_id"],
        seed["codex"]["connection_id"],
    }
    assert "token_hash" not in str(connections)
    detail = client.get(
        f"/api/v1/sessions/{session}", headers=headers(seed["codex"]["token"])
    ).json()
    assert not detail["can_write"]


def test_project_creation_and_pagination(client, seed, call, session):
    auth = headers(seed["claude"]["token"])
    name = "New project " + str(uuid4())[:8]
    created = client.post("/api/v1/projects", json={"name": name}, headers=auth)
    assert created.status_code == 201
    pid = created.json()["id"]
    assert (
        client.get(f"/api/v1/projects/{pid}/overview", headers=auth).json()["stats"]["sessions"]
        == 0
    )
    assert client.post("/api/v1/projects", json={"name": name}, headers=auth).status_code == 409
    assert (
        client.post(
            "/api/v1/projects", json={"name": "Forbidden"}, headers=headers(seed["viewer"]["token"])
        ).status_code
        == 403
    )
    assert client.post("/api/v1/projects", json={"name": "   "}, headers=auth).status_code == 422
    invalid = client.post(
        "/api/v1/projects", json={"name": "x", "private": "DO_NOT_ECHO"}, headers=auth
    )
    assert invalid.status_code == 422 and "DO_NOT_ECHO" not in invalid.text
    call("session_start", {"project_id": seed["project_id"], "external_session_id": "another"})
    page = client.get(
        f"/api/v1/projects/{seed['project_id']}/sessions?limit=1", headers=auth
    ).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["next_offset"] == 1
    next_page = client.get(
        f"/api/v1/projects/{seed['project_id']}/sessions?limit=1&offset=1", headers=auth
    ).json()
    assert next_page["items"][0]["id"] != page["items"][0]["id"]
    assert next_page["next_offset"] is None


def test_graph_parent_links(client, seed, call, session):
    child = call(
        "session_start",
        {
            "project_id": seed["project_id"],
            "external_session_id": "continued",
            "parent_session_id": session,
        },
    )["session_id"]
    graph = client.get(
        f"/api/v1/projects/{seed['project_id']}/graph", headers=headers(seed["claude"]["token"])
    ).json()
    assert graph["edges"] == [
        {"source_id": child, "target_id": session, "relation_type": "continues"}
    ]


def test_public_shell_does_not_expose_api(client):
    # Build the UI before this test to validate its public shell/assets boundary.
    root = client.get("/")
    if root.status_code != 200:
        pytest.skip("Build web/dist to check the public shell")
    assert "Shared Memory" in root.text
    asset = re.search(r'src="(/assets/[^\"]+)"', root.text)[1]
    assert client.get(asset).status_code == 200
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/me").status_code == 401
