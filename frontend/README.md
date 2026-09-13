# SSC Agent frontend

The React/TypeScript frontend provides Entra sign-in, a backend connection test,
and streamed conversations with the general and coding agent profiles.

Read [How SSC Agent works](../docs/system-guide.md) for the full request flow and
[the deployment runbook](../docs/kubernetes.md) for kind operations.

## Development

Run these commands from the repository root. Start the API on port 5080 first;
Vite proxies `/api` and `/openapi` to it.

```powershell
pnpm install --frozen-lockfile
pnpm api:generate
pnpm dev
```

The API generator reads `http://localhost:5080/openapi/v1.json`. It writes ordinary
HTTP client modules under `src/api`; AG-UI streaming uses its own `HttpAgent`.
For a host frontend with cluster services, follow the local-development section
in the [runbook](../docs/kubernetes.md).

## How the UI is assembled

| File | Responsibility |
| --- | --- |
| [src/main.tsx](src/main.tsx) | Initialize MSAL and mount authentication, query, and router providers |
| [src/router.tsx](src/router.tsx) | TanStack Router route tree |
| [src/features/auth/AuthGate.tsx](src/features/auth/AuthGate.tsx) | Login, connection-test screen, and workspace access |
| [src/features/auth/authConfig.ts](src/features/auth/authConfig.ts) | Tenant/client defaults, redirect origin, login scopes |
| [src/api-mutator.ts](src/api-mutator.ts) | Attach bearer tokens for ordinary HTTP and streaming requests |
| [src/App.tsx](src/App.tsx) | assistant-ui runtime, AG-UI profile selection, workspace layout |
| [orval.config.ts](orval.config.ts) | Generate typed clients from FastAPI OpenAPI |

TanStack Query handles ordinary server queries such as health; assistant-ui's
AG-UI adapter handles conversation streaming. Zustand stores the workspace's
chat/activity selection. Radix components provide dialogs, and Lucide provides
icons. The backend owns command execution; the browser does not call Kubernetes.

The agent selector remounts the conversation runtime. New conversation reloads
the page. There is no saved-thread list or restoration feature. The Activity log
screen is a placeholder. The model name shown in the UI is a source string;
changing backend `FOUNDRY_MODEL` does not automatically change that label.

## Authentication and configuration

MSAL requests `openid profile email` and uses `window.location.origin` for redirects.
Register the Vite origin and `http://localhost:8080` as SPA redirect URIs in Entra.
The current API accepts tenant-validated bearer tokens without enforcing audience
or delegated API scopes; see the system guide for its exact behavior.

| Variable | Meaning |
| --- | --- |
| `VITE_MSAL_TENANT_ID` | Browser sign-in tenant |
| `VITE_MSAL_CLIENT_ID` | SPA application client ID |
| `VITE_API_BASE_URL` | Optional API base URL; empty uses the current origin |

Local Vite reads the root `.env` through `envDir: '..'`. These variables are
build-time inputs. The Containerfile excludes `.env*` and provides no `VITE_*`
build arguments, so the container-built frontend uses source defaults unless
build wiring is changed. Runtime Kubernetes ConfigMaps do not rewrite JavaScript.
Never put server-side credentials in `VITE_*` variables.

## Build and verify

From the repository root:

```powershell
pnpm build
pnpm lint
pnpm --dir frontend exec playwright install chromium
pnpm e2e
```

The build runs TypeScript and Vite; lint uses Oxlint. Playwright's current smoke
test covers the unauthenticated screen. Authenticated scenarios require a test
account/session and are not established by a successful frontend build.

In kind, FastAPI serves the built assets from the combined application image.
There is no separate Vite or frontend Deployment.
