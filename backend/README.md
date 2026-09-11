# SSC Agent backend

The backend is a FastAPI application managed with `uv`. It uses the Python
Microsoft Agent Framework Foundry integration for agent calls.

## Development

From the repository root:

```bash
uv run --directory backend uvicorn ssc_agent.main:app --reload --port 5080
```

Run the backend checks with:

```bash
uv run --directory backend pytest
uv run --directory backend ruff check .
```

For a clean local backend environment, remove the backend virtual environment
and recreate it from the locked dependencies:

```bash
rm -rf backend/.venv
uv sync --directory backend --frozen
uv run --directory backend pytest
```

The API uses `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL` for Microsoft
Foundry configuration. `DefaultAzureCredential` supplies agent authentication
using the standard Azure SDK credential chain.

The backend exposes two authenticated AG-UI SSE endpoints:

- `/api/ag-ui/ssc-agent` — the general SSC agent
- `/api/ag-ui/coding` — the coding-focused agent

They use the same Foundry client and authentication dependency, but have
separate Agent Framework agent profiles. `/api/chat` is retained as a legacy
JSON endpoint.

The `DockerShellTool` integration is enabled by the Podman Compose setup. It
runs commands in stateless, isolated containers by default. The backend image
contains the `podman` client, and Compose connects it to the rootless Podman
machine socket; see the root `.env.example` for the socket, image, timeout,
and optional work-directory settings.

`/api/chat` requires a Microsoft Entra bearer token. Temporary development mode
accepts any valid signed token issued by `MSAL_TENANT_ID`; it checks the signing
key, issuer, tenant ID, and expiry but does not require a registered API
resource, audience, or scope. The frontend sends the signed Entra ID token from
the normal `openid profile email` login.

Both agent profiles use Cognee's Python SDK as a durable conversation-memory provider. It recalls
user-scoped memory for the current AG-UI thread (or `/api/chat` `sessionId`) before the
model call and stores the completed question/answer turn afterward. Configure it with
`COGNEE_ENABLED`, `COGNEE_URL`, optional `COGNEE_API_KEY`, `COGNEE_DATASET`,
`COGNEE_TIMEOUT`, and `COGNEE_TOP_K`.
The local Compose deployment disables Cognee access control by default through
`COGNEE_ENABLE_BACKEND_ACCESS_CONTROL=false`; enable it when using an API key
and multiple Cognee users.
Memory failures are logged and ignored so Cognee availability does not take down chat.

After signing in, use the **Test backend connection** button. It calls the
protected `/api/test-agent` endpoint, which runs a small dedicated MAF agent
and displays its response.
