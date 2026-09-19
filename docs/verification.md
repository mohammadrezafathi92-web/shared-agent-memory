# Verification report — 2026-09-19

This report distinguishes implemented behavior, local checks, and unverified deployment claims.

## Passed locally

| Check | Result |
|---|---|
| `uv sync --frozen` / dependency lock | Resolved and installed; registry is public PyPI |
| Ruff lint and formatting | Passed |
| PostgreSQL integration suite | **18 tests passed** |
| Alembic on a fresh dedicated test database | Revision 0001 applied successfully |
| Contract schemas | `docs/contracts.json` equals implementation schemas |
| Python source/wheel packaging | Build completed |
| Official MCP protocol over HTTP | Initialization, tool listing, writes and cross-connection retrieval passed |
| Hook adapter subprocess | SessionStart returned previous context; synthetic Codex payload |
| Offline spool | Failed connection preserved backlog; later replay succeeded without duplicate event |
| Docker application images | Built using the public ECR mirror of the Python Docker Official Image |
| Compose services | Database healthy, migration exited successfully, API healthy |
| Containerized MCP handoff demo | Two synthetic host identities shared a decision and checkpoint |
| Database + API restart | Same two memory IDs retrieved after restart |
| React production build | TypeScript and Vite build passed |
| Chromium browser flows | **4 passed**, both against local API and container on port 8766 |
| Container user | Application runs as UID 10001, not root |

Integration tests also exercise viewer restrictions, project/workspace isolation, credential revocation, idempotency collisions, concurrent writes, decision supersession races, source lookup, graph cycle rejection, Persian normalization, input size limits and secret-pattern redaction. This is meaningful regression coverage, not a full security audit or load benchmark.

## Tested environment

- Host: macOS ARM64; Docker's Linux containers.
- Local Python: 3.13.15. Container Python: 3.12.14.
- PostgreSQL: 16.14, existing stock `postgres:16` image.
- MCP SDK: 1.30.0, pinned in `uv.lock`.
- Application image base: `public.ecr.aws/docker/library/python:3.12-slim`.
- Compose database override: `MEMORY_DB_IMAGE=postgres:16`.
- Local API demo port: 8765; container smoke-test port: 8766.

Two dependency deprecation warnings were emitted by Starlette/AnyIO's test-client compatibility layer. They did not fail the tests. Production MCP transport was also tested through a real socket, independently of TestClient.

## Not yet verified or implemented

Docker Hub authentication requests timed out for both `pgvector/pgvector:pg17` and `python:3.12-slim`. The Python mirror allowed application image builds and runtime tests. **The default pgvector image and extension were not tested locally**, and vector retrieval is not implemented. The initial GitHub CI run passed on Ubuntu with pgvector/PostgreSQL 17, including the default Docker build and Compose smoke check.

No live Claude Code or Codex conversation was launched; adapters were tested using realistic synthetic lifecycle inputs and the official SDK. Do not advertise an installed host version as certified. ChatGPT, Claude Desktop, OpenCode and Hermes integrations remain planned. No model API credentials were used and no LLM-generated extraction was tested.

The Ubuntu-native install, x86_64 image, OAuth, load targets, restore-from-backup, deletion/retention and public-internet hardening are not certified by these checks. The source is ready for the next development milestone, not a complete general release.

## Local artifacts and state

The source is published on `main` at https://github.com/mohammadrezafathi92-web/shared-agent-memory. No existing agent settings were modified.

The downloadable ZIP excludes `.env`, credentials, SQLite spools, virtual environments, git metadata, caches and test data. The local checkout's private `.env` retains the PostgreSQL 16 override used for testing; a new install generated from the ZIP defaults to the documented pgvector image. The local database volume is retained.

## Dashboard milestone (0.2)

React/TypeScript static build, Persian/English layout, project-scoped reads, owner project creation, session/event pagination, source inspection, explicit session links, context preview and own-connection listing are implemented. Backend regression tests include workspace/project isolation and sanitized validation errors. Four Playwright Chromium flows cover real-data reads and source inspection, language switching, context, logout, session/decision/continuation writes, mobile project creation, reload credential clearing and invalid credentials. Screenshots use synthetic data only.

The interface is a same-origin static React app rather than the earlier proposed Next.js service. This removes a separate web runtime from the install. It is a developer preview: no full accessibility audit, high-concurrency load benchmark, real host certification or production deployment is implied.

## Interactive installer

Added a Bash bootstrap and standard-library Python wizard, isolated Compose project/volumes, optional Caddy HTTPS, private saved configuration, transactional initial provisioning and non-destructive resume. The regression suite now contains **24 passing tests**. An actual local container installation and replay verifies dashboard access, owner identity, no duplicate accounts, retained memory and private credential files. CI also drives interactive terminal prompts on Ubuntu with its existing Docker installation. Blank-VM apt installation and real public DNS/certificate issuance are not covered by this smoke test.

## Host/Origin allowlist now covers the whole app

`MEMORY_ALLOWED_HOSTS` previously only protected the `/mcp` endpoint: the official MCP SDK's
DNS-rebinding check runs inside its own mounted sub-app and never saw requests to `/api/v1/*`,
`/health`, `/` or `/assets/*`. `BoundaryMiddleware` now validates the `Host` header (and `Origin`,
when a browser sends one) against the same allowlist for every request before anything else runs,
mirroring the SDK's own exact-string/`"host:*"` matching. Verified locally: a pure unit test for
the matching function (`test_host_allowed_matching`), plus an integration test against a running
app confirming an unrecognized `Host` gets `421` and an unrecognized `Origin` gets `403` on both
the dashboard shell and the REST API (`test_boundary_rejects_unknown_host_and_origin`) — the
latter needs the project's PostgreSQL test database and was not run in this environment; it runs
under the same `uv run pytest -q` CI already exercises.

## LAN access mode

Added a third installer access mode, `lan`, alongside `local` and `https`: the API additionally
binds to an operator-supplied LAN IP address (validated as private, non-loopback) over plain HTTP,
and that address is added to `MEMORY_ALLOWED_HOSTS`. Config validation and the generated Compose
override (`.install/lan.json`) are covered by local unit tests
(`test_installer_lan_mode_requires_private_non_loopback_bind_host`,
`test_installer_lan_mode_publishes_on_the_lan_address`); an actual container install in `lan` mode,
reached from a second device, was **not** re-run through `scripts/smoke_install.py` in this change
— only exercised manually once against a real server during development.
