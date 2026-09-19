# Contributing

Use Python 3.12+ and `uv sync --frozen`. Run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -q` against a dedicated PostgreSQL test database (see README).

All reads/writes must use the shared authorization boundary. Add regression coverage for access changes, retries, races and source provenance. Freeze migrations; add a new revision rather than editing a released migration. Keep synthetic fixtures free of real conversation data, credentials or identifying details.

Document adapter compatibility with exact host version, operating system, capture capabilities and date. An SDK test is not a live host certification. Changes to contracts must update `docs/contracts.json` and migration notes. Do not introduce model API calls, telemetry or remote data transfer without explicit configuration and documentation.

For UI work, use Node.js 22.12+ and `npm ci --prefix web`, then `npm run build --prefix web`. Run the Playwright flows described in README against synthetic local data. Check both Persian RTL and English LTR, narrow screens, keyboard focus and access restrictions.
