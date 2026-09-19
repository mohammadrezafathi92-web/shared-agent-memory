ARG PYTHON_IMAGE=python:3.12-slim
ARG NODE_IMAGE=node:22-slim
FROM ${NODE_IMAGE} AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM ${PYTHON_IMAGE}
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv==0.12.3
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY --from=web /web/dist ./web/dist
COPY README.md LICENSE ./
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home memory
USER memory
EXPOSE 8765
CMD ["uvicorn", "shared_memory.app:app", "--host", "0.0.0.0", "--port", "8765"]
