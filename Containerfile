FROM node:24-alpine AS frontend-build

WORKDIR /workspace
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/package.json
RUN pnpm install --frozen-lockfile

COPY frontend ./frontend
RUN pnpm --filter frontend build

FROM ghcr.io/astral-sh/uv:0.12.4 AS uv

FROM python:3.14-slim AS backend-build

COPY --from=uv /uv /uvx /bin/

WORKDIR /workspace
WORKDIR /workspace/backend
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/src ./src
RUN uv sync --frozen --no-dev

FROM python:3.14-slim AS runtime

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    FRONTEND_DIST=/app/frontend-dist \
    PYTHONUNBUFFERED=1
EXPOSE 8080

COPY --from=backend-build /workspace/backend/.venv /app/.venv
COPY --from=backend-build /workspace/backend/src /app/src
COPY --from=frontend-build /workspace/frontend/dist /app/frontend-dist

# DockerShellTool uses the Podman client to submit isolated command containers
# to the host Podman API socket mounted by Compose.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes ca-certificates podman \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
CMD ["python", "-m", "uvicorn", "ssc_agent.main:app", "--app-dir", "/app/src", "--host", "0.0.0.0", "--port", "8080"]
