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
deploy/kind/              Kubernetes manifests for the existing kind cluster
scripts/deploy-kind.ps1   Build, load, and deploy with Podman and kind
```

## Local development

Prerequisites: Python 3.11+, uv, Node.js 24+, pnpm 10+, Podman, kind, and kubectl.

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

## Kubernetes (kind)

The deployment runs the combined React/FastAPI app, Cognee, and PostgreSQL in
`ssc-agent`. Temporary shell pods run in `ssc-sandbox`. Podman builds images
and hosts the existing kind node; the application uses the Kubernetes API.
The former Cognee UI submodule is removed.

See [the kind deployment guide](docs/kubernetes.md) for setup, configuration,
network isolation, validation, and cleanup. From PowerShell:

```powershell
Copy-Item .env.example .env # only if you do not already have .env
# Fill in your Azure credentials, Cognee API keys, and PostgreSQL password.
./scripts/deploy-kind.ps1 -Cluster kind-cluster
kubectl --context kind-kind-cluster -n ssc-agent port-forward service/ssc-agent 8080:8080
```

Open `http://localhost:8080`. Existing Entra sign-in and AG-UI endpoints are
unchanged. Fresh persistent volumes store PostgreSQL and Cognee data; rebuilding
or redeploying retains them. Deleting the kind cluster deletes its local storage.

## Validation

```bash
uv run --directory backend pytest
uv run --directory backend ruff check .
pnpm build
pnpm lint
pnpm e2e
```

The model deployment name defaults to `gpt-5.3-codex` and can be overridden with `FOUNDRY_MODEL`.
