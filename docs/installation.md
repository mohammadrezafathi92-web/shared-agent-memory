# Interactive installation

Run on the machine that will host Shared Agent Memory:

```sh
curl -fsSL https://raw.githubusercontent.com/mohammadrezafathi92-web/shared-agent-memory/main/install.sh | bash
```

Requires an interactive terminal, Bash and curl. The bootstrap can install missing Git/Python on Ubuntu after asking. Docker Engine/Compose are installed from Docker's official apt repository on Ubuntu 22.04/24.04/26.04 when needed, with an explicit prompt and sudo/root access. On other systems install Docker (for example Docker Desktop) first. Existing container runtimes are never removed; conflicting Ubuntu packages require operator migration. GPU, a model API key, local Node and a local Python virtual environment are not needed.

The downloaded script clones the public repository, or resumes a matching existing checkout. It never runs `git reset`, upgrades your checkout, deletes a database volume or silently changes an existing manual `.env`. For reviewing the bootstrap first, download `install.sh`, inspect it, then run `bash install.sh`; from a cloned repository the same command starts the local installer.

## Questions

1. Installation directory (remote bootstrap only).
2. Language (`fa` / `en`).
3. Workspace, administrator email, initial project.
4. Application port (default `8765`).
5. Access mode: `local` or `https`.
6. Container registry: `dockerhub` or `ecr`.
7. Public domain, if HTTPS is selected.
8. Confirm settings; install Docker/use sudo only if necessary.
9. Optionally display the dashboard token after verified installation.

`dockerhub` uses the normal pgvector/PostgreSQL 17 image. `ecr` uses public ECR mirrors for Python, Node, Caddy and **stock PostgreSQL 17**. This works for the current keyword search; it does not supply the vector extension. Never change the database image's major version on an existing volume.

The email identifies the first owner; no email is sent. The installer creates the workspace, owner membership and one dashboard token. Use separate CLI-issued tokens for your agents. It builds the web/API images, applies migrations, waits for health, verifies authenticated identity, and saves credentials in `.install/credentials.json` with mode `0600` inside a `0700` directory. Secrets never enter command arguments or build contexts. Terminal token display is opt-in.

## Access

**Local:** the API binds only to loopback. On a remote Ubuntu server, the installer prints an SSH tunnel command. From your own machine use the server login, for example:

```sh
ssh -L 8765:127.0.0.1:8765 user@server
```

Then open `http://127.0.0.1:8765/` and enter the dashboard token.

**HTTPS:** Caddy is added to the same isolated Compose project. It publishes ports 80 and 443, obtains/renews a certificate, and proxies to the internal API. Configure the domain's DNS to reach this server and permit inbound 80/443 at your network firewall before installation. Docker-published ports can bypass host UFW rules. The installer does not edit DNS/firewalls or replace an existing reverse proxy. It checks public HTTPS before reporting success; certificate/DNS failures leave state intact so the same command can resume. Internet access to certificate authorities is required. This does not add OAuth or certify ChatGPT cloud integration.

## Resume and manage

Run the same installer in the **same directory** after a download/build/interruption failure. Saved identifiers and the same token are replayed transactionally, preventing duplicate initial accounts. Existing sessions/memory remain in the named database volume. Another invocation is blocked while installation is in progress. A revoked installer token is never silently reactivated.

Use the generated wrapper (not plain `docker compose`, which targets the manual default stack):

```sh
/path/to/shared-agent-memory/.install/manage ps
/path/to/shared-agent-memory/.install/manage logs --tail 100 api
/path/to/shared-agent-memory/.install/manage stop
/path/to/shared-agent-memory/.install/manage start
/path/to/shared-agent-memory/.install/manage exec api shared-memory issue-token --workspace-id WORKSPACE_UUID --email owner@example.com --host codex
```

Every installation uses its own Compose project name and volumes. `.install/state.json` stores stable setup identifiers and secrets; keep the directory private and include it in protected backups along with PostgreSQL backups. Do not delete it to reset the service. Editing `runtime.env` is detected and never silently overwritten. This installer is for fresh installs/resume, not an upgrade or existing-deployment adoption tool. To change deployment settings or upgrade database versions, plan a separate migration/backup first.

## Unattended installation

After cloning the repository, write an answers JSON file (no secrets needed):

```json
{
  "language": "en",
  "workspace": "My team",
  "email": "owner@example.com",
  "project": "Pilot",
  "port": 8765,
  "mode": "local",
  "accept": true
}
```

```sh
python3 scripts/install.py --config /path/to/answers.json
```

`install_docker: true` explicitly permits Ubuntu package installation; `use_sudo: true` permits elevated Docker commands. Neither defaults to true. A fresh unattended install requires `accept: true`. Optional image fields are `db_image`, `python_image`, `node_image` and `caddy_image`; `domain` is required for `mode: "https"`. Resuming with an answers file requires the same saved settings. Automatic updates are not enabled.

## Verification scope

`uv run pytest -q` includes installer validation, private file modes, interrupted-install replay, immutable runtime credentials, bootstrap idempotency and revocation. `uv run python scripts/smoke_install.py --interactive` drives the actual terminal prompts in an isolated checkout, installs real containers, writes a memory, reruns installation, and verifies that identity and memory survived without duplicate accounts. Only this test's generated stack/volumes are removed afterward.

The Ubuntu CI runner already has Docker; it exercises application installation, not apt installation on a blank VM. Public-domain certificate issuance requires real DNS and was not exercised by the local-only smoke test.

References: [Docker's Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/) and [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
