# Local deployment to kind

The three services run in `ssc-agent`; disposable shell pods run in `ssc-sandbox`.
The default existing cluster is `kind-cluster` (context `kind-kind-cluster`).
Podman remains the image builder and kind node provider. No engine socket is
mounted into application pods. The former Cognee UI submodule is removed.

## Deploy

Install Podman, kind, kubectl, uv, and PowerShell. Start your existing cluster.
The helper accepts kubectl on PATH or `.tools/kubectl.exe`. Copy `.env.example`
to `.env` if needed, then supply a PostgreSQL password, Azure service-principal
credentials for the app, and LLM/embedding API keys for Cognee. Host `az login`
credentials are not automatically available inside Kubernetes pods.

```powershell
./scripts/deploy-kind.ps1 -Cluster kind-cluster
kubectl --context kind-kind-cluster -n ssc-agent port-forward service/ssc-agent 8080:8080
```

Open <http://localhost:8080>. Register that SPA redirect origin in the Entra app
registration. Cognee and PostgreSQL remain internal; optionally forward
`service/cognee 8000:8000` to access the Cognee API documentation.

The script builds images from the two Containerfiles, imports image archives into
kind, installs the network-policy controller, applies `deploy/kind`, imports
allowlisted configuration from `.env`, restarts the app/Cognee, and runs the live sandbox smoke tests. Image tags are
local development tags with `IfNotPresent`; use this script to reload new builds.
`-SkipBuild` reuses images already built in Podman and still reloads them into kind.
The script always uses an explicit context. Secrets are passed over stdin rather
than command-line arguments or generated files. Do not commit `.env`.

## Storage and configuration

The initial deployment uses fresh 5 GiB PVCs for PostgreSQL and Cognee. The cluster
must have a default dynamic storage provisioner (kind's local-path provisioner is
supported). Rebuilds retain data. Deleting PVCs, the namespace, or the kind cluster
removes local data; former Podman volumes are left untouched.

ConfigMaps in `configmaps.yaml` hold defaults; `.env` can override their allowlisted
keys. Internal service addresses and the sandbox namespace are deployment-owned.
Legacy `DOCKER_SHELL_*` and `PODMAN_*` variables are ignored. The host development
API keeps its shell disabled; Kubernetes shell execution requires in-cluster
service-account credentials. The default sandbox image is the .NET 8 SDK and must
provide `/bin/sh` and GNU `/usr/bin/timeout` if replaced.

## Sandbox lifecycle and networking

Every invocation receives a new pod and a writable `/tmp` emptyDir. All files
are discarded afterward. Combine commands into one invocation when they need
shared files. Command execution defaults to 30 seconds; startup has an additional
120-second allowance. Output combines stdout/stderr and returns at most
64 KiB from the start of the log plus the exit code. Four invocations can run concurrently per backend.
Namespace quota limits the total pod count to 16.

Pods run non-root, without credentials or host mounts, with dropped capabilities,
a read-only root filesystem, and CPU/memory/storage limits. Their namespace denies
all ingress and egress, including DNS, cluster services, and internet access.
Image pulls happen on the node and remain possible. The controller manifest is
vendored from kubernetes-sigs/kube-network-policies v1.1.1, with the image pinned
to v1.1.1 and fail-open disabled: <https://github.com/kubernetes-sigs/kube-network-policies/tree/v1.1.1>.
It augments kind's networking without replacing its CNI.

Live testing found a brief policy-enforcement race on new pods. To keep commands
offline from their first instruction, `seccomp-offline.json` restricts sockets to
AF_UNIX. It derives from this cluster's containerd 2.3.4 RuntimeDefault profile,
retaining its default-deny syscall rules and disallowing socketcall and io_uring.
IPv4, IPv6, packet, and netlink sockets are unavailable, including IP loopback.
Unix-domain sockets remain available. The helper installs the profile in each
kind node's kubelet seccomp directory, then labels that node for sandbox
scheduling. A missing profile prevents container startup. The supplied profile
supports amd64 nodes; the script rejects other architectures. See the
[Kubernetes seccomp documentation](https://kubernetes.io/docs/reference/node/seccomp/).
Verify network denial after changes to the cluster or profile.

The API deletes pods in a finally block. A pod deadline stops abandoned execution,
and a reaper CronJob runs every two minutes to delete labeled pods past their
deadline plus a two-minute margin. The reaper runs outside the offline namespace
so it can reach the API. No pods/exec permission is needed by the application.
Kubernetes pods share the node kernel; they are a local development isolation
boundary. Per-pod PID limits are kubelet settings, not standard pod resources;
this migration does not claim to preserve the old 256-process container limit.

## Verify and operate

```powershell
kubectl --context kind-kind-cluster -n ssc-agent get pods,pvc
kubectl --context kind-kind-cluster -n ssc-agent logs deployment/ssc-agent
kubectl --context kind-kind-cluster -n ssc-sandbox get pods
Invoke-RestMethod http://localhost:8080/health
uv run --directory backend pytest
uv run --directory backend ruff check .
pnpm build
Get-Content -Raw scripts/smoke_kind.py | kubectl --context kind-kind-cluster -n ssc-agent exec -i deployment/ssc-agent -- python -
```

After signing in, use **Test backend connection**, then ask the agent to run a
shell command. Observe a temporary pod in `ssc-sandbox` and its subsequent removal.
For teardown that preserves PVCs, delete the Deployments, StatefulSet, and CronJob
in `ssc-agent`. Avoid deleting the namespace or using `kubectl delete -k` when
you want to retain data. PostgreSQL credentials must remain consistent with an
initialized database; changing `.env` does not change existing database passwords.
