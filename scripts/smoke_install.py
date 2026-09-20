"""Isolated Docker installer smoke test; only this test's generated stack is removed."""

import argparse
import json
import os
import pty
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wizard(root, port, registry="dockerhub"):
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [sys.executable, str(root / "scripts/install.py")],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    prompts = iter(
        [
            ("Language /", "en"),
            ("Workspace name", "Installer smoke"),
            ("Administrator email", "installer@example.test"),
            ("First project name", "Pilot"),
            ("Local application port", str(port)),
            ("Access:", "local"),
            ("Image registry: dockerhub or ecr", registry),
            ("Start installation?", "y"),
            ("Show dashboard token", "n"),
        ]
    )
    expected = next(prompts)
    log, pending = "", ""
    # A stale prompt matcher must fail quickly instead of consuming the
    # complete CI job timeout. Image pulls/builds are allowed separately by
    # the installer's own command execution.
    deadline = time.monotonic() + 600
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 1)[0]:
                try:
                    chunk = os.read(master, 65536).decode(errors="replace")
                except OSError:
                    break
                if not chunk:
                    break
                log += chunk
                pending += chunk
                if expected and expected[0] in pending:
                    os.write(master, (expected[1] + "\n").encode())
                    pending = ""
                    expected = next(prompts, None)
            elif process.poll() is not None:
                break
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
        if process.returncode or expected:
            raise RuntimeError("Wizard failed or did not complete prompts:\n" + log[-12000:])
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
        os.close(master)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--db-image", default="pgvector/pgvector:pg17")
    parser.add_argument("--python-image", default="python:3.12-slim")
    parser.add_argument("--node-image", default="node:22-slim")
    args = parser.parse_args()
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="installer-smoke-", dir=work) as temporary:
        root = Path(temporary) / "app"
        shutil.copytree(
            ROOT,
            root,
            ignore=shutil.ignore_patterns(
                ".git",
                ".env",
                ".env.*",
                ".venv",
                ".install",
                "node_modules",
                "dist",
                "work",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                "test-results",
                "playwright-report",
            ),
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = dict(
            language="en",
            workspace="Installer smoke",
            email="installer@example.test",
            project="Pilot",
            port=port,
            accept=True,
            db_image=args.db_image,
            python_image=args.python_image,
            node_image=args.node_image,
        )
        answers = root / "work/answers.json"
        answers.parent.mkdir()
        answers.write_text(json.dumps(config))
        manage = root / ".install/manage"
        try:
            if args.interactive:
                registry = "ecr" if args.db_image.startswith("public.ecr.aws/") else "dockerhub"
                wizard(root, port, registry)
                # Reuse exactly the saved answers for unattended recovery/replay.
                answers.write_text(
                    json.dumps(json.loads((root / ".install/state.json").read_text())["config"])
                )
            else:
                subprocess.run(
                    [sys.executable, str(root / "scripts/install.py"), "--config", str(answers)],
                    check=True,
                )
            credentials = json.loads((root / ".install/credentials.json").read_text())
            before = (root / ".install/state.json").read_bytes()

            def api(path, data=None):
                request = urllib.request.Request(
                    credentials["dashboard_url"] + path,
                    data=json.dumps(data).encode() if data is not None else None,
                    headers={
                        "Authorization": "Bearer " + credentials["token"],
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    return json.load(response)

            session = api(
                "/api/v1/tools/session_start",
                {
                    "project_id": credentials["project_id"],
                    "external_session_id": "installer-persistence",
                },
            )["session_id"]
            memory = api(
                "/api/v1/tools/decision_record",
                {
                    "session_id": session,
                    "statement": "Installer replay preserves this decision.",
                    "idempotency_key": "test",
                },
            )
            subprocess.run(
                [sys.executable, str(root / "scripts/install.py"), "--config", str(answers)],
                check=True,
            )
            assert (root / ".install/state.json").read_bytes() == before
            assert len(api("/api/v1/projects")) == 1
            assert len(api("/api/v1/connections")) == 1
            assert (
                api("/api/v1/tools/memory_get", {"memory_id": memory["memory_id"]})["body"][
                    "statement"
                ]
                == "Installer replay preserves this decision."
            )
            assert (root / ".install/credentials.json").stat().st_mode & 0o777 == 0o600
            with urllib.request.urlopen(credentials["dashboard_url"], timeout=10) as response:
                assert "Shared Memory" in response.read().decode()
            print(
                "INSTALLER PASSED: dashboard + account + replay without duplicates + retained memory + private credentials"
            )
        finally:
            if manage.exists():
                subprocess.run([str(manage), "down", "--volumes"], check=True)


if __name__ == "__main__":
    main()
