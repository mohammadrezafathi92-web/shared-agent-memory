import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import uvicorn
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from shared_memory.app import create_app
from shared_memory.cli import initialize, issue_token
from shared_memory.config import Settings

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("MEMORY_TEST_DATABASE_URL")
    if not url or "test" not in url.rsplit("/", 1)[-1]:
        pytest.fail(
            "Set MEMORY_TEST_DATABASE_URL to a dedicated PostgreSQL database whose name contains 'test'."
        )
    subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "MEMORY_DATABASE_URL": url},
        check=True,
    )
    return url


@pytest.fixture
def app(database_url):
    return create_app(Settings(database_url=database_url))


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def seed(database_url):
    with psycopg.connect(database_url, row_factory=dict_row) as db:
        data = initialize(db, "test-" + str(uuid4()), "owner@example.test", "shared")
        claude = issue_token(db, data["workspace_id"], "owner@example.test", "claude-code")
        codex = issue_token(db, data["workspace_id"], "owner@example.test", "codex")
        outsider = initialize(db, "test-" + str(uuid4()), "other@example.test", "private")
        other = issue_token(db, outsider["workspace_id"], "other@example.test", "codex")
        private = uuid4()
        db.execute(
            "INSERT INTO projects VALUES(%s,%s,'owner-only')", (private, data["workspace_id"])
        )
        db.execute(
            "INSERT INTO project_members VALUES(%s,%s,%s,'owner')",
            (data["workspace_id"], private, data["user_id"]),
        )
        viewer_id = uuid4()
        db.execute(
            "INSERT INTO users VALUES(%s,%s,'viewer@example.test')",
            (viewer_id, data["workspace_id"]),
        )
        db.execute(
            "INSERT INTO project_members VALUES(%s,%s,%s,'viewer')",
            (data["workspace_id"], data["project_id"], viewer_id),
        )
        viewer = issue_token(db, data["workspace_id"], "viewer@example.test", "reader")
    return dict(
        data,
        claude=claude,
        codex=codex,
        other=other,
        viewer=viewer,
        private_project_id=str(private),
    )


def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def call(client, seed):
    def invoke(name, body, who="claude", expected=200):
        response = client.post(
            f"/api/v1/tools/{name}", json=body, headers=headers(seed[who]["token"])
        )
        assert response.status_code == expected, response.text
        return response.json()

    return invoke


@pytest.fixture
def session(call, seed):
    return call(
        "session_start",
        {
            "project_id": seed["project_id"],
            "external_session_id": "claude-session",
            "task_key": "architecture",
        },
    )["session_id"]


@pytest.fixture
def live_server(database_url):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    application = create_app(Settings(database_url=database_url))
    server = uvicorn.Server(uvicorn.Config(application, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    sock.close()
