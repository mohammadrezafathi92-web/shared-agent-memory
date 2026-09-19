# Verification report — 2026-09-19

This report distinguishes implemented behavior, local checks, and unverified deployment claims.

## Passed locally

| Check | Result |
|---|---|
| `uv sync --frozen` / dependency lock | Resolved and installed; registry is public PyPI |
| Ruff lint and formatting | Passed |
| PostgreSQL integration suite | **14 tests passed** |
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

Docker Hub authentication requests timed out for both `pgvector/pgvector:pg17` and `python:3.12-slim`. The Python mirror allowed application image builds and runtime tests. **The default pgvector image and extension were not tested locally**, and vector retrieval is not implemented. The CI workflow specifies pgvector/PostgreSQL 17 but has not been run on GitHub.

No live Claude Code or Codex conversation was launched; adapters were tested using realistic synthetic lifecycle inputs and the official SDK. Do not advertise an installed host version as certified. ChatGPT, Claude Desktop, OpenCode and Hermes integrations remain planned. No model API credentials were used and no LLM-generated extraction was tested.

The Ubuntu-native install, x86_64 image, OAuth, GUI, load targets, restore-from-backup, deletion/retention and public-internet hardening are not certified by these checks. The source is ready for the next development milestone, not a complete general release.

## Local artifacts and state

The source repository is initialized locally on branch `main`, with no commit or remote. No GitHub repository was created or pushed. No existing agent settings were modified.

The downloadable ZIP excludes `.env`, credentials, SQLite spools, virtual environments, git metadata, caches and test data. The local checkout's private `.env` retains the PostgreSQL 16 override used for testing; a new install generated from the ZIP defaults to the documented pgvector image. Verification services are stopped after testing; the local database volume is retained.
