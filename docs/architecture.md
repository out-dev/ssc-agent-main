# Architecture overview

SSC Agent runs a React interface and FastAPI backend in one application image.
The backend coordinates a Foundry model, durable Cognee memory, and disposable
Kubernetes shell pods. PostgreSQL supports Cognee. Podman builds the images and
hosts the kind nodes; Kubernetes manages the application and sandbox workloads.

For the complete walkthrough, read [How SSC Agent works](system-guide.md).
For deployment and troubleshooting commands, use [the kind runbook](kubernetes.md).

## Runtime boundaries

| Boundary | Components | Connection |
| --- | --- | --- |
| Browser | React, MSAL, assistant-ui, AG-UI client | Same-origin HTTP through port forwarding |
| Application namespace (`ssc-agent`) | FastAPI, Cognee, PostgreSQL, cleanup CronJob | Internal Kubernetes Services |
| Sandbox namespace (`ssc-sandbox`) | One temporary pod per shell invocation | Created and observed through the Kubernetes API |
| Azure | Entra ID, Foundry chat model, Cognee LLM/embedding deployments | Separate browser, backend, and Cognee credentials |
| kind nodes | Kubelet, containerd, network-policy controller, seccomp file | Run and isolate workload containers |

The app exposes port 8080 and serves the compiled frontend itself. Cognee listens
on 8000 and PostgreSQL on 5432 behind internal Services. The deployment does not
create an Ingress. The Cognee UI and Compose configuration have been removed.

## A chat request

The browser authenticates with Entra and posts an AG-UI request to the selected
profile. FastAPI validates the bearer token and establishes the request identity.
Agent Framework invokes the memory provider, calls Foundry, executes requested
tools, and returns streamed response/tool events. Eligible completed turns are
stored in Cognee afterward.

`ssc-agent` and `coding` share one Foundry client, shell adapter, and memory client
per process. The coding profile adds engineering instructions. Both use the
configured `FOUNDRY_MODEL`; switching profiles does not select another deployment.

Ordinary HTTP routes remain available: `/health`, `/openapi/v1.json`,
`/api/test-agent`, and the legacy `/api/chat`. The primary chat routes are
`/api/ag-ui/ssc-agent` and `/api/ag-ui/coding`.

## Identity and state

The browser normally sends an Entra ID token. Current backend validation checks
RS256 signing, issuer, time claims, and tenant; audience and API scopes are not
validated in the current development implementation. The backend independently
uses `DefaultAzureCredential` for Foundry. Cognee independently uses Azure resource
keys for its LLM and embedding clients.

Cognee keys combine a hashed user principal and framework session ID. AG-UI uses
its thread ID for that framework session. Both profiles currently use the same
`shared` memory namespace. Recall and storage errors are logged while the agent
continues. `COGNEE_TIMEOUT` is declared but not enforced by the current wrapper.

Durable recall is separate from visible conversation history. The frontend has
no saved-conversation restoration feature. The legacy `/api/chat` session cache
is process-local, keyed only by supplied `sessionId`, and creates framework session
IDs separately; it is not a durable, user-qualified session registry. These
behaviors are detailed in the [state and memory walkthrough](system-guide.md).

## Shell execution and workspace

`KubernetesShellTool` submits a plain Pod for each invocation, polls status, reads
up to 64 KiB of combined logs, and returns the exit code. The pod uses the .NET 8
SDK, a writable `/tmp`, resource limits, non-root execution, dropped capabilities,
and a read-only root filesystem with the shared workspace mounted at the configured path
(default `/workspace`). It receives no application secrets or service-account token.

The agent service and sandbox pods share access to a configurable workspace:
- `WorkspaceManager` provides file tools (`write_file`, `read_file`, `list_files`, `delete_file`) for creating and modifying project files.
- The sandbox pod executes in the shared workspace, enabling the coding agent to create, build, test, and debug code (e.g. `dotnet new`, `dotnet build`, `dotnet test`, `dotnet run`).

A deny-all NetworkPolicy and a node-local seccomp profile keep pods offline.
The profile blocks IP socket creation from process startup, including loopback,
closing an observed policy-enforcement timing gap. Only Unix-domain sockets remain
available. The supplied profile and installer target amd64 kind nodes.

The backend can create/get/delete sandbox pods and read logs. It does not need
Podman, kubectl, or `pods/exec`. Cancellation and normal completion attempt deletion.
Pod/client/command deadlines bound execution; a separate CronJob reaps orphaned
pods. User approval is not requested for each shell command in this application.

## Deployment and persistence

The PowerShell deployment helper builds with Podman, installs the offline profile,
loads images into kind, configures network enforcement, imports allowlisted `.env`
values into ConfigMaps/Secrets, and applies workloads. It waits for readiness and
runs live sandbox smoke checks. Port forwarding is a separate host process.

The app and Cognee use single-replica Deployments with `Recreate`; PostgreSQL uses
a StatefulSet. Cognee waits for PostgreSQL readiness through an init container.
Persistent volumes and PVCs preserve the database, Cognee system/data directories,
and the shared workspace across pod replacement.
Deleting the local kind cluster is not a data-preserving operation.

`/health` verifies only the API process. The authenticated connection-test endpoint
exercises Foundry; the sandbox smoke script exercises real pods. Neither is a
complete browser-and-memory end-to-end test. See the
[validation coverage table](system-guide.md) for the distinction.
