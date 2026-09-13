# SSC Agent backend

The backend is a FastAPI application managed with `uv`. It uses the Python
Microsoft Agent Framework Foundry integration for agent calls.

See [How SSC Agent works](../docs/system-guide.md) for request flow, identity,
memory/session behavior, sandbox execution, and a source map. Operational commands
are in the [kind deployment runbook](../docs/kubernetes.md).

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

The optional `KubernetesShellTool` runs each shell invocation in a fresh offline
pod and deletes it afterward. Enable it with `KUBERNETES_SHELL_ENABLED=true`
inside the cluster; the deployment supplies namespace-scoped service-account
permissions. Configure `KUBERNETES_SHELL_IMAGE`, `KUBERNETES_SHELL_TIMEOUT`,
`KUBERNETES_SHELL_STARTUP_TIMEOUT`, and `KUBERNETES_SHELL_CONCURRENCY` as needed.
The image must include `/bin/sh` and GNU `/usr/bin/timeout`. The default is the
.NET 8 SDK. Only `/tmp` is writable, and files do not survive an invocation.
The host development API leaves the shell disabled by default. Enabling it
requires the installed node-local offline seccomp profile as well as RBAC;
namespace-wide network policy alone does not provide the required startup isolation.

`/api/chat` requires a Microsoft Entra bearer token. Temporary development mode
accepts any valid signed token issued by `MSAL_TENANT_ID`; it checks the signing
key, issuer, tenant ID, and expiry but does not require a registered API
resource, audience, or scope. The frontend sends the signed Entra ID token from
the normal `openid profile email` login.

Both agent profiles use Cognee's remote Python SDK for durable conversation memory.
They recall user-scoped memory before a run and store completed question/answer
turns afterward. Keys use the framework session ID; AG-UI uses its thread ID, while
the legacy endpoint maps `sessionId` to a process-local framework session object.
That legacy cache is not qualified by user and is lost on restart. Both profiles
currently use the same `shared` durable-memory namespace.

Configure memory with `COGNEE_ENABLED`, `COGNEE_URL`, optional `COGNEE_API_KEY`,
`COGNEE_DATASET`, and `COGNEE_TOP_K`. `COGNEE_TIMEOUT` is declared in settings but
is not currently enforced by the SDK wrapper. See the detailed guide for the
distinction between durable recall and restored conversation history.
The kind deployment disables Cognee access control by default through
`COGNEE_ENABLE_BACKEND_ACCESS_CONTROL=false`. Enabling it requires corresponding
Cognee user/key provisioning; setting a key alone does not complete that setup.
Memory failures are logged and ignored so Cognee availability does not take down chat.

After signing in, use the **Test backend connection** button. It calls the
protected `/api/test-agent` endpoint, which runs a small dedicated MAF agent
and displays its response.
