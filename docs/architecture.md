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
Kubernetes. Recall and persistence are fail-open and only log a warning when Cognee is
unavailable.

## Sandboxed shell tool

`KubernetesShellTool` exposes a local shell function through
`FoundryChatClient.get_shell_tool`. Each invocation creates a fresh pod in
`ssc-sandbox`, polls its status, reads bounded combined stdout/stderr, and returns
the exit code. GNU timeout limits command execution independently of scheduling;
a pod deadline and a client deadline also bound startup and execution. The API
deletes pods on success, failure, and cancellation. A CronJob reaps labeled pods
older than their deadline plus two minutes, including pods orphaned by API crashes.

Sandbox pods have no service-account token, host mounts, or application secrets.
They run as a non-root user with dropped capabilities, a read-only root filesystem,
limited CPU/memory/storage, and writable temporary storage. A namespace-wide policy
denies ingress and egress, enforced by the supplied kube-network-policies controller.
A node-local seccomp profile additionally disallows IP sockets from process startup,
closing the observed network-policy enforcement race for newly started pods.
The backend service account can create/get/delete pods and read logs only in the
sandbox namespace. The separate reaper account can list/delete pods there.

See [Kubernetes deployment](kubernetes.md) for operational details and limitations.

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

`scripts/deploy-kind.ps1` builds the app and Cognee images with Podman, loads image
archives into the selected kind cluster, applies Kustomize manifests, imports
allowlisted `.env` settings, and waits for rollouts. Credentials are sent directly
to a Kubernetes Secret and are not written to generated manifest files. The app
serves the frontend and API through one origin. PostgreSQL uses pgvector/pgvector:pg17.

PVCs retain PostgreSQL and Cognee system/data files across redeployments. This
migration starts with fresh storage; former Compose volumes are not imported or
deleted. Cognee retains its Azure API-key authentication for LLMs and embeddings;
the app independently uses DefaultAzureCredential. The Cognee UI is no longer
part of the repository or deployment.
