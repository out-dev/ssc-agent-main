# SSC Agent

Monorepo for a Python API built with FastAPI and Microsoft Agent Framework, a React frontend, and project documentation.

## Repository layout

```text
backend/
  pyproject.toml          Python dependencies and project configuration
  src/ssc_agent           FastAPI API and Microsoft Agent Framework agent
  tests                   Pytest API tests
frontend/                 React + TypeScript app managed with pnpm
docs/                     Architecture and operational notes
Containerfile             Image build for the API and frontend
cognee/                   Cognee image and runtime files
compose.yaml              Podman-compatible local container definition
```

## Local development

Prerequisites: Python 3.11+, uv, Node.js 24+, pnpm 10+, and Podman.

1. Authenticate for local Foundry calls with `az login` or another `DefaultAzureCredential` supported provider.
2. Start the API with `uv run --directory backend uvicorn ssc_agent.main:app --reload --port 5080`.
3. In a second terminal, generate the typed frontend client with `pnpm api:generate`.
4. Start the frontend with `pnpm dev` and open the Vite URL.

The frontend requires Microsoft Entra ID sign-in through MSAL. The supplied tenant and SPA client IDs are configured by default; they can be overridden with `VITE_MSAL_TENANT_ID` and `VITE_MSAL_CLIENT_ID` in the root `.env`. Register each frontend origin (`http://localhost:5173` for Vite and `http://localhost:8080` for the container) as a SPA redirect URI in the Entra app registration. No custom API scope is required in temporary tenant-only mode.

The API publishes its OpenAPI document at `/openapi/v1.json`. Orval generates the client under `frontend/src/api` from that document. The Vite proxy forwards `/api` and `/openapi` to port 5080. `/api/chat` requires a bearer token from the configured tenant. After login, use **Test backend connection** to run the protected `/api/test-agent` smoke check through Microsoft Agent Framework.

The chat workspace uses authenticated AG-UI streaming endpoints:

- `POST /api/ag-ui/ssc-agent` for the general SSC agent
- `POST /api/ag-ui/coding` for the coding-focused agent

Both endpoints require the same Entra bearer token as `/api/chat`. The legacy
`/api/chat` endpoint remains available for compatibility while clients migrate.

## Clean development build

Use this when local dependencies or generated output may be stale. Run it from the repository root:

```bash
rm -rf backend/.venv frontend/node_modules node_modules frontend/dist
uv sync --directory backend --frozen
pnpm install --force
```

Start the freshly installed backend in one terminal:

```bash
uv run --directory backend uvicorn ssc_agent.main:app --reload --port 5080
```

Then, from the repository root in a second terminal, regenerate the client, build the frontend, and start Vite:

```bash
pnpm api:generate
pnpm build
pnpm dev
```

Verify the backend before opening the frontend:

```bash
curl http://localhost:5080/health
curl http://localhost:5080/openapi/v1.json
```

The first command should return `{"status":"ok","version":"1.0.0"}`. Chat requests still require signing in through the frontend; no custom Entra API scope is needed in temporary tenant-only mode.

## End-to-end UI tests

Playwright runs the frontend end-to-end tests against a Vite dev server. Install its Chromium browser once with `pnpm --dir frontend exec playwright install chromium`, then run:

```bash
pnpm e2e
```

Use `pnpm e2e:ui` to run Playwright in its interactive UI mode. The initial smoke test covers the unauthenticated sign-in screen; authenticated scenarios should use a dedicated test account or Playwright storage state rather than real user credentials in the repository.

## Podman

Copy `.env.example` to `.env`, choose a PostgreSQL password, provide the Azure resource key in `LLM_API_KEY` and `EMBEDDING_API_KEY`, and provide a non-secret local credential mechanism or the Azure service principal variables. Then run:

```bash
podman compose up --build
```

### Clean Podman build

`--no-cache` forces both the React and Python backend stages to rebuild. `--pull=always` also refreshes the base images:

```bash
podman compose down
podman compose build --no-cache --pull=always
podman compose up -d
podman compose ps
```

Verify the running application and backend image:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/openapi/v1.json
podman compose logs ssc-agent
```

The clean build removes containers but keeps PostgreSQL and Cognee data volumes. To also reset all local application data, use the following instead of `podman compose down`; this deletes the named volumes and therefore removes the local PostgreSQL database and Cognee storage:

```bash
podman compose down -v
podman compose build --no-cache --pull=always
podman compose up -d
```

Use `podman compose ps` and `podman compose logs -f ssc-agent` when the backend is still starting. A stale server response with the old API metadata means an older container is serving the port; stop that container and rerun the clean build above.

Open `http://localhost:8080` for the application, `http://localhost:3000` for the Cognee Local UI, or `http://localhost:8000/docs` for the Cognee REST API. Compose builds the `ssc-agent` image containing the compiled React application and Python API, the `ssc-agent-cognee` server image, and the Cognee Local UI image from the `cognee-ui` submodule; PostgreSQL runs from `pgvector/pgvector:pg17`. PostgreSQL is used for Cognee's relational database and session cache. Cognee's default vector and graph stores remain in the named `cognee_data` and `cognee_system` volumes. Podman Desktop or Podman UI can build and start the services from `compose.yaml`.

The `cognee` service waits for PostgreSQL to become healthy and receives its connection settings through `DB_PROVIDER=postgres`, `DB_HOST=postgres`, and the `DB_*` credentials. Cognee uses Azure Foundry by default through `LLM_PROVIDER=azure`, the `azure/gpt-4.1-mini` deployment, and the resource-level endpoint in `LLM_ENDPOINT`. Cognee authenticates with the Azure resource keys in `LLM_API_KEY` and `EMBEDDING_API_KEY`; its managed-identity option is not configured. The Python agent uses `DefaultAzureCredential` and the `AZURE_CLIENT_*` variables when needed. These Cognee settings are independent of the `FOUNDRY_*` settings used by the Python agent.

The two Agent Framework profiles use the Cognee Python SDK in remote mode for durable, user-scoped conversation memory. They recall matching session memory before each model call and persist typed question/answer turns afterward. `COGNEE_URL` points to `http://cognee:8000` inside Compose; local non-container runs should use `http://localhost:8000`. Local Compose runs Cognee in single-user mode by default (`COGNEE_ENABLE_BACKEND_ACCESS_CONTROL=false`); enable access control and provide `COGNEE_API_KEY` for authenticated multi-tenant deployments.

Cognee uses the Azure `text-embedding-3-small` deployment for embeddings and passes `EMBEDDING_API_KEY` to that client. The deployment returns 1536-dimensional vectors, which Cognee stores alongside the PostgreSQL metadata. The project endpoint does not route embeddings, so `EMBEDDING_ENDPOINT` uses the resource-level deployment route shown in the Cognee configuration.

Set `SSC_AGENT_PORT`, `COGNEE_PORT`, or `POSTGRES_PORT` in `.env` when one of the default host ports is already in use.

## Validation

```bash
uv run --directory backend pytest
uv run --directory backend ruff check .
pnpm build
pnpm lint
pnpm e2e
```

The model deployment name defaults to `gpt-5.3-codex` and can be overridden with `FOUNDRY_MODEL`.

### DockerShellTool

The backend includes a Podman-backed DockerShellTool integration for running model-requested shell commands in isolated OCI containers. The Compose setup installs the Podman client in `ssc-agent` and connects it to the rootless Podman API socket from the local Podman machine. The default `stateless` mode creates a fresh container for each command, which is appropriate for this multi-user API. Use `DOCKER_SHELL_MODE=persistent` only when the agent service is dedicated to one conversation.

The tool uses the framework defaults: network disabled, non-root execution, a read-only root filesystem, a 512 MB memory limit, and a 256-process limit. The Compose setup uses `/tmp` as the command working directory because it exists in the .NET SDK image; `DOCKER_SHELL_HOST_WORKDIR` is optional and is mounted read-only at `DOCKER_SHELL_WORKDIR`.

On macOS, start the Podman machine and set `PODMAN_SOCKET_PATH` to its Linux-side socket path before starting Compose:

```bash
podman machine start
PODMAN_MACHINE_UID="$(podman machine ssh podman-machine-default 'id -u')"
PODMAN_MACHINE_GID="$(podman machine ssh podman-machine-default 'id -g')"
export PODMAN_SOCKET_PATH="/run/user/${PODMAN_MACHINE_UID}/podman/podman.sock"
export PODMAN_MACHINE_GID
podman compose up --build -d
```

The same socket path is also recorded in `.env.example`; update its numeric user ID if your Podman machine reports a different value. `PODMAN_CONTAINER_HOST` points the in-container CLI at the mounted socket. Do not set `DOCKER_SHELL_HOST_WORKDIR` unless the directory is available to the Podman machine, because mounts are resolved by that host engine.

This is suitable for a controlled local development environment. Possession of the Podman API socket grants broad control over the host Podman engine; the DockerShellTool container limits remain useful defense-in-depth, but the socket must not be exposed to an untrusted or publicly reachable backend.

AG-UI streams backend tool-call events, so the frontend can observe tool
activity as it happens. The current DockerShellTool remains server-side and
is not directly callable by the browser.
