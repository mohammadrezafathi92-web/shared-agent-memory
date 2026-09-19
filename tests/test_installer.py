import importlib.util
import json
import os
import secrets
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from shared_memory.bootstrap import provision

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def answers(**changes):
    result = dict(workspace="Test team", email="owner@example.test", project="Pilot", accept=True)
    result.update(changes)
    return result


def payload():
    return dict(
        installation_id=str(uuid4()),
        workspace="Installer test",
        email="owner@example.test",
        project="Pilot",
        token="sm_" + secrets.token_urlsafe(32),
    )


def test_transactional_bootstrap_replay_and_revocation(database_url):
    data = payload()
    with psycopg.connect(database_url, row_factory=dict_row) as db:
        first = provision(db, data)
    with psycopg.connect(database_url, row_factory=dict_row) as db:
        assert provision(db, data) == first
        assert (
            db.execute(
                "SELECT count(*) AS n FROM connections WHERE workspace_id=%s",
                (first["workspace_id"],),
            ).fetchone()["n"]
            == 1
        )
    with pytest.raises(ValueError), psycopg.connect(database_url, row_factory=dict_row) as db:
        provision(db, dict(data, token="sm_" + secrets.token_urlsafe(32)))
    with psycopg.connect(database_url, row_factory=dict_row) as db:
        db.execute("UPDATE connections SET revoked_at=now() WHERE id=%s", (first["connection_id"],))
    with pytest.raises(ValueError), psycopg.connect(database_url, row_factory=dict_row) as db:
        provision(db, data)


def test_bootstrap_cli_does_not_echo_invalid_secrets(database_url):
    secret = "private-input-do-not-echo"
    result = subprocess.run(
        [str(ROOT / ".venv/bin/shared-memory"), "bootstrap"],
        input=json.dumps({"token": secret}),
        text=True,
        capture_output=True,
        env={**os.environ, "MEMORY_DATABASE_URL": database_url},
    )
    assert result.returncode != 0
    assert secret not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_installer_config_rejects_injection_and_invalid_ports():
    for change in (
        {"domain": "example.com\n{evil}", "mode": "https"},
        {"port": "1; echo oops"},
        {"port": 80},
        {"db_image": "postgres:16\nMEMORY_PORT=4"},
        {"email": "bad"},
        {"mode": "all-interfaces"},
    ):
        with pytest.raises(installer.InstallError):
            installer.validated(answers(**change))
    assert (
        installer.validated(answers(mode="https", domain="memory.example.com"))["domain"]
        == "memory.example.com"
    )


def test_runtime_is_private_and_refuses_changed_database_password(tmp_path):
    directory = tmp_path / ".install"
    directory.mkdir(mode=0o700)
    state = dict(
        config=installer.validated(answers(mode="https", domain="memory.example.com")),
        database_password="a" * 48,
        compose_project="sam-test",
    )
    command = installer.write_runtime(tmp_path, state, ["docker"])
    assert "sam-test" in command
    assert (directory / "runtime.env").stat().st_mode & 0o777 == 0o600
    assert (directory / "manage").stat().st_mode & 0o777 == 0o700
    assert (directory / "Caddyfile").read_text().startswith("memory.example.com {\n")
    override = json.loads((directory / "https.json").read_text())
    assert override["services"]["gateway"]["ports"] == ["80:80", "443:443"]
    installer.write_runtime(tmp_path, state, ["docker"])
    (directory / "runtime.env").write_text("POSTGRES_PASSWORD=changed\n")
    with pytest.raises(installer.InstallError):
        installer.write_runtime(tmp_path, state, ["docker"])
    assert (directory / "runtime.env").read_text() == "POSTGRES_PASSWORD=changed\n"


def test_failure_resume_keeps_identity_and_no_duplicate_provision(tmp_path, monkeypatch):
    config_path = tmp_path / "answers.json"
    config_path.write_text(json.dumps(answers(language="en")))
    monkeypatch.setattr(installer, "check_ports", lambda _: None)
    monkeypatch.setattr(installer, "docker_command", lambda *args: ["docker"])
    fail_once = True
    seen = []

    def fake_run(command, **kwargs):
        nonlocal fail_once
        if "up" in command and fail_once:
            fail_once = False
            raise installer.InstallError("Simulated registry outage")
        if "bootstrap" in command:
            data = json.loads(kwargs["data"])
            seen.append(data)
            return json.dumps(
                {"connection_id": "connection", "workspace_id": data["installation_id"]}
            )
        return ""

    monkeypatch.setattr(installer, "run", fake_run)
    monkeypatch.setattr(
        installer, "verify_http", lambda *a, **kw: {"status": "ok", "connection_id": "connection"}
    )
    with pytest.raises(installer.InstallError):
        installer.install(tmp_path, config_path)
    before = (tmp_path / ".install/state.json").read_bytes()
    installer.install(tmp_path, config_path)
    installer.install(tmp_path, config_path)
    assert (tmp_path / ".install/state.json").read_bytes() == before
    assert seen[0] == seen[1]
    credential = tmp_path / ".install/credentials.json"
    assert credential.stat().st_mode & 0o777 == 0o600
    config_path.write_text(json.dumps(answers(language="en", port=8999)))
    with pytest.raises(installer.InstallError, match="differs"):
        installer.install(tmp_path, config_path)


def test_manual_deployment_is_not_overwritten(tmp_path):
    (tmp_path / ".env").write_text("POSTGRES_PASSWORD=existing\n")
    config = tmp_path / "answers.json"
    config.write_text(json.dumps(answers()))
    with pytest.raises(installer.InstallError, match="manual"):
        installer.install(tmp_path, config)
    assert (tmp_path / ".env").read_text() == "POSTGRES_PASSWORD=existing\n"
