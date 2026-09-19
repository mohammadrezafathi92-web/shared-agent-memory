#!/usr/bin/env python3
"""Interactive, resumable installer. Host Python uses only its standard library."""

import argparse
import errno
import fcntl
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


class InstallError(Exception):
    pass


LANG = "en"
MANAGED_ENV = (
    "POSTGRES_PASSWORD",
    "MEMORY_PORT",
    "MEMORY_ALLOWED_HOSTS",
    "MEMORY_DB_IMAGE",
    "MEMORY_PYTHON_IMAGE",
    "MEMORY_NODE_IMAGE",
    "COMPOSE_FILE",
    "COMPOSE_PROJECT_NAME",
    "COMPOSE_PROFILES",
)


def say(en, fa):
    return fa if LANG == "fa" else en


def ask(en, fa, default=""):
    suffix = f" [{default}]" if default else ""
    return input(say(en, fa) + suffix + ": ").strip() or default


def confirm(en, fa, default=False):
    while True:
        value = ask(en, fa, "Y/n" if default else "y/N").lower()
        if value in ("y", "yes", "بله"):
            return True
        if value in ("n", "no", "خیر"):
            return False
        if value in ("y/n",):
            return default


def run(args, *, capture=False, data=None, cwd=None):
    env = os.environ.copy()
    if "compose" in args:
        for key in MANAGED_ENV:
            env.pop(key, None)
    result = subprocess.run(args, input=data, text=True, capture_output=capture, cwd=cwd, env=env)
    if result.returncode:
        # Do not echo stdin, environment, or captured provisioning output.
        raise InstallError(say("Command failed: ", "اجرای دستور ناموفق بود: ") + shlex.join(args))
    return result.stdout if capture else ""


def works(args):
    return (
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    )


def private_write(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validated(raw):
    allowed = {
        "language",
        "workspace",
        "email",
        "project",
        "port",
        "mode",
        "domain",
        "install_docker",
        "use_sudo",
        "accept",
        "show_token",
        "db_image",
        "python_image",
        "node_image",
        "caddy_image",
    }
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise InstallError("Unknown installer configuration fields.")
    config = dict(
        language="fa",
        port=8765,
        mode="local",
        domain="",
        install_docker=False,
        use_sudo=False,
        accept=False,
        show_token=False,
        db_image="pgvector/pgvector:pg17",
        python_image="python:3.12-slim",
        node_image="node:22-slim",
        caddy_image="caddy:2-alpine",
    )
    config.update(raw)
    for key in ("workspace", "project"):
        value = config.get(key)
        if (
            not isinstance(value, str)
            or not 1 <= len(value.strip()) <= 100
            or any(ord(c) < 32 for c in value)
        ):
            raise InstallError(
                "Workspace and project names must contain 1–100 printable characters."
            )
        config[key] = value.strip()
    email = config.get("email", "")
    if (
        not isinstance(email, str)
        or len(email) > 254
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
    ):
        raise InstallError("Enter a valid administrator email.")
    if config["language"] not in ("en", "fa") or config["mode"] not in ("local", "https"):
        raise InstallError("Language must be fa/en and access mode local/https.")
    try:
        config["port"] = int(config["port"])
    except (TypeError, ValueError):
        raise InstallError("Port must be an integer.") from None
    if not 1024 <= config["port"] <= 65535:
        raise InstallError("Application port must be between 1024 and 65535.")
    for key in ("install_docker", "use_sudo", "accept", "show_token"):
        if not isinstance(config[key], bool):
            raise InstallError(key + " must be true or false.")
    if config["mode"] == "https":
        if not isinstance(config["domain"], str):
            raise InstallError("Domain must be text.")
        domain = config["domain"].lower()
        if (
            len(domain) > 253
            or "." not in domain
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                for part in domain.split(".")
            )
            or domain.replace(".", "").isdigit()
        ):
            raise InstallError(
                "Enter a public DNS name without scheme, path or port (e.g. memory.example.com)."
            )
        config["domain"] = domain
    for key in ("db_image", "python_image", "node_image", "caddy_image"):
        if not isinstance(config[key], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._/@:-]{1,240}", config[key]
        ):
            raise InstallError("Invalid container image reference.")
    return config


def collect():
    while True:
        raw = {
            "language": LANG,
            "workspace": ask("Workspace name", "نام مجموعه", "My team"),
            "email": ask("Administrator email", "ایمیل مدیر"),
            "project": ask("First project name", "نام پروژه اولیه", "Main project"),
            "port": ask("Local application port", "پورت محلی برنامه", "8765"),
            "mode": ask("Access: local or https", "دسترسی: local یا https", "local"),
        }
        registry = ask(
            "Image registry: dockerhub or ecr", "مخزن ایمیج: dockerhub یا ecr", "dockerhub"
        )
        if registry == "ecr":
            raw.update(
                db_image="public.ecr.aws/docker/library/postgres:17",
                python_image="public.ecr.aws/docker/library/python:3.12-slim",
                node_image="public.ecr.aws/docker/library/node:22-slim",
                caddy_image="public.ecr.aws/docker/library/caddy:2-alpine",
            )
        elif registry != "dockerhub":
            print("Choose dockerhub or ecr.")
            continue
        if raw["mode"] == "https":
            print(
                say(
                    "HTTPS publishes ports 80/443. Point a public DNS name at this server and allow these ports in your network firewall.",
                    "HTTPS پورت‌های ۸۰ و ۴۴۳ را منتشر می‌کند. دامنه را به این سرور متصل و این پورت‌ها را در فایروال شبکه باز کنید.",
                )
            )
            raw["domain"] = ask("Public domain", "دامنه عمومی")
        try:
            return validated(raw)
        except InstallError as exc:
            print(exc)


def docker_command(root, config, interactive):
    if not shutil.which("docker") or not works(["docker", "compose", "version"]):
        consent = (
            config["install_docker"]
            if not interactive
            else confirm(
                "Install Docker Engine + Compose from the official Ubuntu apt repository?",
                "Docker و Compose از مخزن رسمی روی اوبونتو نصب شوند؟",
            )
        )
        if not consent:
            raise InstallError(
                "Docker Engine and Compose are required; install/start them and rerun."
            )
        release = Path("/etc/os-release")
        if not release.exists() or not re.search(
            r'^ID=["\']?ubuntu["\']?$', release.read_text(), re.M
        ):
            raise InstallError(
                "Automatic dependency installation supports Ubuntu only; install Docker manually here."
            )
        prefix = [] if os.geteuid() == 0 else ["sudo"]
        run(prefix + ["bash", str(root / "scripts/install-docker.sh")])
    if works(["docker", "info"]):
        return ["docker"]
    if os.geteuid() == 0 or not shutil.which("sudo"):
        raise InstallError("Docker daemon is unavailable. Start Docker and rerun.")
    consent = (
        config["use_sudo"]
        if not interactive
        else confirm(
            "Docker needs elevated access. Use sudo for Docker commands?",
            "اجرای Docker دسترسی مدیریتی می‌خواهد. از sudo استفاده شود؟",
            True,
        )
    )
    if consent:
        run(["sudo", "-v"])
        if works(["sudo", "docker", "info"]):
            return ["sudo", "docker"]
    raise InstallError("Docker is not accessible. Fix access/start the daemon, then rerun.")


def env_content(state):
    c = state["config"]
    hosts = ["127.0.0.1:*", "localhost:*"]
    if c["mode"] == "https":
        hosts += [c["domain"], c["domain"] + ":443"]
    return (
        f"POSTGRES_PASSWORD={state['database_password']}\nMEMORY_PORT={c['port']}\n"
        f"MEMORY_ALLOWED_HOSTS='{json.dumps(hosts)}'\nMEMORY_DB_IMAGE={c['db_image']}\n"
        f"MEMORY_PYTHON_IMAGE={c['python_image']}\nMEMORY_NODE_IMAGE={c['node_image']}\n"
    )


def compose_command(root, state, docker):
    command = docker + [
        "compose",
        "--project-name",
        state["compose_project"],
        "--project-directory",
        str(root),
        "--env-file",
        str(root / ".install/runtime.env"),
        "-f",
        str(root / "compose.yaml"),
    ]
    if state["config"]["mode"] == "https":
        command += ["-f", str(root / ".install/https.json")]
    return command


def write_runtime(root, state, docker):
    directory = root / ".install"
    expected = env_content(state)
    env = directory / "runtime.env"
    if env.exists() and env.read_text() != expected:
        raise InstallError(
            "Managed runtime.env was changed. Restore it from state before resuming; it was not overwritten."
        )
    private_write(env, expected)
    if state["config"]["mode"] == "https":
        domain = state["config"]["domain"]
        private_write(directory / "Caddyfile", domain + " {\n    reverse_proxy api:8765\n}\n")
        override = {
            "services": {
                "gateway": {
                    "image": state["config"]["caddy_image"],
                    "restart": "unless-stopped",
                    "ports": ["80:80", "443:443"],
                    "volumes": [
                        {
                            "type": "bind",
                            "source": str(directory / "Caddyfile"),
                            "target": "/etc/caddy/Caddyfile",
                            "read_only": True,
                        },
                        "caddy-data:/data",
                        "caddy-config:/config",
                    ],
                    "depends_on": {"api": {"condition": "service_healthy"}},
                }
            },
            "volumes": {"caddy-data": {}, "caddy-config": {}},
        }
        private_write(directory / "https.json", json.dumps(override, indent=2))
    command = compose_command(root, state, docker)
    private_write(
        directory / "manage",
        "#!/usr/bin/env bash\nset -euo pipefail\nunset "
        + " ".join(MANAGED_ENV)
        + "\nexec "
        + shlex.join(command)
        + ' "$@"\n',
    )
    os.chmod(directory / "manage", 0o700)
    return command


def check_ports(config):
    ports = [("127.0.0.1", config["port"])]
    if config["mode"] == "https":
        ports += [("0.0.0.0", 80), ("0.0.0.0", 443)]
    for host, port in ports:
        with socket.socket() as sock:
            try:
                sock.bind((host, port))
            except OSError as exc:
                if exc.errno == errno.EACCES and port < 1024:
                    continue  # Docker binds these privileged HTTPS ports after elevation.
                raise InstallError(
                    f"Port {port} is unavailable; choose another application port or free the HTTPS port."
                ) from None


def verify_http(url, token=None, attempts=30):
    headers = {"Authorization": "Bearer " + token} if token else {}
    # Local verification must not send credentials through environment HTTP proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(attempts):
        try:
            with opener.open(urllib.request.Request(url, headers=headers), timeout=5) as response:
                return json.load(response)
        except (OSError, ValueError, urllib.error.URLError):
            if attempt + 1 < attempts:
                time.sleep(2)
    raise InstallError("HTTP verification failed: " + url)


def install(root, config_file=None):
    global LANG
    interactive = config_file is None
    if interactive:
        if not sys.stdin.isatty():
            raise InstallError("Use an interactive terminal or --config FILE.")
        LANG = ask("Language / زبان: fa or en", "Language / زبان: fa or en", "fa")
        if LANG not in ("fa", "en"):
            raise InstallError("Choose fa or en.")
    directory = root / ".install"
    if directory.is_symlink():
        raise InstallError("Installer state directory must not be a symlink.")
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    with (directory / "lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallError("Another installer is running for this directory.") from None
        path = directory / "state.json"
        fresh = not path.exists()
        if not fresh:
            state = json.loads(path.read_text())
            if state.get("schema") != 1:
                raise InstallError("Unsupported installer state version.")
            config = validated(state["config"])
            LANG = config["language"]
            if config_file and validated(json.loads(config_file.read_text())) != config:
                raise InstallError(
                    "Configuration differs from saved installation. Resume with the original settings."
                )
            print(
                say(
                    "Resuming saved installation; keeping database password and account identity.",
                    "ادامه نصب ذخیره‌شده؛ رمز دیتابیس و هویت حساب حفظ می‌شوند.",
                )
            )
        else:
            if (root / ".env").exists():
                raise InstallError(
                    "Existing manual .env detected. Use a fresh checkout; installer will not adopt/overwrite an existing deployment."
                )
            config = validated(json.loads(config_file.read_text())) if config_file else collect()
            LANG = config["language"]
            print(say("Installation settings", "تنظیمات نصب"))
            print(
                json.dumps(
                    {
                        key: config[key]
                        for key in ("workspace", "email", "project", "port", "mode", "domain")
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            accepted = (
                config["accept"]
                if not interactive
                else confirm("Start installation?", "نصب آغاز شود؟", True)
            )
            if not accepted:
                raise InstallError("Installation cancelled.")
            check_ports(config)
            installation_id = str(uuid4())
            state = {
                "schema": 1,
                "config": config,
                "installation_id": installation_id,
                "compose_project": "sam-" + installation_id[:12],
                "database_password": secrets.token_hex(24),
                "token": "sm_" + secrets.token_urlsafe(32),
            }
            # Save identity BEFORE starting containers; retries cannot create duplicate accounts.
            private_write(path, json.dumps(state, ensure_ascii=False, indent=2))
        docker = docker_command(root, config, interactive)
        command = write_runtime(root, state, docker)
        print(
            say(
                "Building and starting services; the first download can take several minutes…",
                "ساخت و راه‌اندازی سرویس‌ها؛ دانلود اولیه ممکن است چند دقیقه طول بکشد…",
            )
        )
        run(command + ["config", "--quiet"], capture=True)
        run(command + ["up", "--build", "-d", "--wait", "--wait-timeout", "180"])
        base = "http://127.0.0.1:" + str(config["port"])
        health = verify_http(base + "/health")
        if health.get("status") != "ok":
            raise InstallError("Service health check did not succeed.")
        payload = {key: config[key] for key in ("workspace", "email", "project")}
        payload.update(installation_id=state["installation_id"], token=state["token"])
        result = json.loads(
            run(
                command + ["exec", "-T", "api", "shared-memory", "bootstrap"],
                capture=True,
                data=json.dumps(payload),
            )
        )
        identity = verify_http(base + "/api/v1/me", state["token"], attempts=1)
        if identity.get("connection_id") != result["connection_id"]:
            raise InstallError("HTTP identity does not match this installation.")
        url = "https://" + config["domain"] if config["mode"] == "https" else base
        credentials = dict(
            result,
            email=config["email"],
            token=state["token"],
            dashboard_url=url,
            mcp_url=url + "/mcp",
        )
        private_write(
            directory / "credentials.json", json.dumps(credentials, ensure_ascii=False, indent=2)
        )
        if config["mode"] == "https":
            print(
                say(
                    "Waiting for public HTTPS and certificate verification…",
                    "در انتظار تأیید HTTPS و گواهی دامنه…",
                )
            )
            if verify_http(url + "/health", attempts=12).get("status") != "ok":
                raise InstallError("Public HTTPS health check failed; check DNS and ports 80/443.")
        print(say("Installation verified.", "نصب با موفقیت تأیید شد."))
        print("Dashboard: " + url + "/\nMCP: " + url + "/mcp")
        print(
            say("Private credentials: ", "اطلاعات ورود خصوصی: ")
            + str(directory / "credentials.json")
        )
        print(
            say("Manage services: ", "مدیریت سرویس‌ها: ")
            + shlex.quote(str(directory / "manage"))
            + " ps"
        )
        if config["mode"] == "local":
            print(
                say(
                    "For a remote server use an SSH tunnel, then open the local dashboard:",
                    "برای سرور راه دور، تونل SSH بسازید و سپس پنل محلی را باز کنید:",
                )
            )
            print(f"ssh -L {config['port']}:127.0.0.1:{config['port']} USER@SERVER")
        show = (
            config["show_token"]
            if not interactive
            else confirm(
                "Show dashboard token in this terminal?", "توکن پنل در این ترمینال نمایش داده شود؟"
            )
        )
        if show:
            print("Dashboard token: " + state["token"])
        return credentials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        help="JSON answers for unattended installation (accept=true required)",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        install(root, args.config)
    except (InstallError, OSError, ValueError, KeyboardInterrupt, EOFError) as exc:
        # OSError paths are useful; state and input payloads are never dumped.
        print(say("Installation stopped: ", "نصب متوقف شد: ") + str(exc), file=sys.stderr)
        print(
            say(
                "Fix the issue and run the same installer again. Existing state and volumes are preserved.",
                "مشکل را برطرف و همین نصب‌کننده را دوباره اجرا کنید. وضعیت نصب و داده‌ها حفظ شده‌اند.",
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
