# Architecture

## Runtime

The FastAPI application is the runtime boundary for the application. It owns the Microsoft Agent Framework registration, the Azure AI Projects client, and HTTP endpoints.

`DefaultAzureCredential` is used so local Azure CLI authentication, workload identity, managed identity, and service principal environments can be selected without changing application code. No credential is stored in the repository.

The Foundry project endpoint and model deployment are configuration values:

- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_MODEL`

The default project endpoint is the configured `ssc-proj-default` project, and the default deployment is `gpt-5.3-codex`.

## Conversational memory

Both Agent Framework profiles attach a Cognee `ContextProvider`. Before each model call,
it recalls matching Q&A entries from Cognee's session-memory API; after a response, it
stores the completed turn through `/api/v1/remember/entry`. The Cognee session key is
derived from a hash of the Entra subject and the AG-UI thread ID (or the legacy chat
`sessionId`), keeping memory durable while preventing users from sharing a session by
guessing a thread ID. Cognee is accessed over the internal `COGNEE_URL` service URL in
Compose. Recall and persistence are fail-open and only log a warning when Cognee is
unavailable.

## Sandboxed shell tool

`agent-framework-tools` provides the optional `DockerShellTool` integration. It
is enabled in the Compose development setup. When enabled, the agent gets a
local shell function through `FoundryChatClient.get_shell_tool`; commands run
in stateless containers by default so shell state cannot be shared between
API users. The tool's default sandbox disables networking, runs as a non-root
user, makes the root filesystem read-only, and applies memory and process
limits. The backend image contains the Podman client and Compose mounts the
rootless Podman-machine API socket at `/run/podman/podman.sock`.

The socket is a powerful host control interface. This setup is intended for
controlled local development, not as a production isolation boundary. On
macOS, the socket path in Compose is the Linux path inside the Podman machine,
not the temporary macOS proxy path returned by `podman machine inspect`.

## Authentication

In temporary development mode, the React client signs in with the standard `openid profile email` scopes and adds the resulting signed Entra ID token to API requests. The backend validates `/api/chat` tokens against the Microsoft Entra tenant signing keys, issuer, expiry, and tenant ID. It intentionally does not require an API resource, audience, client claim, or delegated scope while tenant-only mode is enabled. `MSAL_TENANT_ID` configures the accepted tenant. `/health` remains unauthenticated for liveness probes. This relaxed mode must be replaced with audience and permission validation before production use.

The authenticated post-login screen exposes `/api/test-agent`. This endpoint creates a small dedicated MAF agent over the configured Foundry client and returns its response, providing an end-to-end setup check before entering the workspace.

## API contract

FastAPI generates the OpenAPI document at `/openapi/v1.json`. `frontend/orval.config.ts` consumes that document and generates fetch-based React Query operations and models. Generated files are kept in `frontend/src/api`; application code should call those generated operations rather than duplicating request types.

The initial API surface is:

- `GET /health` for liveness and frontend status display
- `POST /api/chat` for a typed agent request
- `POST /api/test-agent` for an authenticated MAF configuration smoke test

The frontend chat uses the AG-UI protocol over authenticated server-sent
events. Two agent profiles are exposed:

- `POST /api/ag-ui/ssc-agent` for the general assistant
- `POST /api/ag-ui/coding` for software-engineering conversations

The AG-UI endpoint registration supplies `require_current_user` explicitly;
AG-UI does not authenticate endpoints by default. AG-UI thread IDs are
conversation identifiers, not authorization credentials, so authentication
and user-level authorization remain server responsibilities.

## Frontend routing and data

The frontend is a React 19 + TypeScript + Vite application. TanStack Router is
the routing framework: `frontend/src/router.tsx` owns the application route
tree, and feature routes should be defined with their feature before being
aggregated there. TanStack React Query is the frontend server-state layer and
is mounted through a shared `QueryClientProvider` in `frontend/src/main.tsx`.

Playwright is the frontend end-to-end UI testing framework. Tests live in
`frontend/e2e`, use the Vite dev server, and run in Chromium through the root
`pnpm e2e` script.

## Delivery

`Containerfile` builds the frontend and backend independently, copies the Vite output into the Python runtime, and ships the `ssc-agent` runtime image. The API serves the SPA fallback, so the browser only needs one origin in container deployments.

For a clean development build, recreate `backend/.venv`, run `uv sync --frozen`, reinstall the pnpm workspace, regenerate the OpenAPI client, and run the frontend build. For a clean Podman build, run `podman compose down`, then `podman compose build --no-cache --pull=always`, followed by `podman compose up -d`. The normal clean container rebuild preserves named data volumes; `podman compose down -v` is an explicit data-reset operation that removes the local PostgreSQL and Cognee data.

The `cognee/` directory contains the `Containerfile`, Python requirements, and entrypoint for the `ssc-agent-cognee` runtime image. `compose.yaml` builds and runs it as a separate `cognee` service alongside PostgreSQL, which uses the `pgvector/pgvector:pg17` image. Cognee uses PostgreSQL for its relational database and session cache through the `DB_*` settings. Cognee's LLM and embedding clients use the native Azure API-key settings `LLM_API_KEY` and `EMBEDDING_API_KEY`; its managed-identity option is not configured. The Python agent independently uses `DefaultAzureCredential` for its Foundry project client. Cognee's vector store uses the Azure `text-embedding-3-small` deployment. Named volumes retain PostgreSQL data and Cognee's default graph store across restarts.
