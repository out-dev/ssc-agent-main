#!/usr/bin/env bash
set -euo pipefail

CLUSTER="kind-cluster"
SKIP_BUILD=false
CLEAN=false

usage() {
    echo "Usage: $0 [--cluster <name>] [--skip-build] [--clean]"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cluster)
            if [[ $# -lt 2 ]]; then
                echo "Error: --cluster requires a value." >&2
                usage
            fi
            CLUSTER="$2"
            shift 2
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Error: Unknown option $1" >&2
            usage
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

KUBECTL_PATH=""
if command -v kubectl >/dev/null 2>&1; then
    KUBECTL_PATH="$(command -v kubectl)"
elif [[ -x ".tools/kubectl" ]]; then
    KUBECTL_PATH="$REPO_ROOT/.tools/kubectl"
elif [[ -x ".tools/kubectl.exe" ]]; then
    KUBECTL_PATH="$REPO_ROOT/.tools/kubectl.exe"
else
    echo "Error: Install kubectl or place it at .tools/kubectl." >&2
    exit 1
fi

TARGET_CONTEXT="kind-${CLUSTER}"

echo "Checking cluster connectivity for context '$TARGET_CONTEXT'..."
"$KUBECTL_PATH" --context "$TARGET_CONTEXT" get nodes >/dev/null
mkdir -p .tools

export KIND_EXPERIMENTAL_PROVIDER="podman"

CLUSTER_NODES="$(kind get nodes --name "$CLUSTER")"
if [[ -z "$CLUSTER_NODES" ]]; then
    echo "Error: Unable to list kind nodes for cluster '$CLUSTER'." >&2
    exit 1
fi

if [[ "$CLEAN" == "true" ]]; then
    echo "Cleaning up existing deployment, storage claims, and persistent volumes..."
    "$KUBECTL_PATH" --context "$TARGET_CONTEXT" -n ssc-sandbox delete pods --all --grace-period=1 >/dev/null 2>&1 || true
    "$KUBECTL_PATH" --context "$TARGET_CONTEXT" delete -f deploy/kind/workloads.yaml --ignore-not-found=true >/dev/null 2>&1 || true
    "$KUBECTL_PATH" --context "$TARGET_CONTEXT" -n ssc-agent delete pvc --all --ignore-not-found=true >/dev/null 2>&1 || true
    "$KUBECTL_PATH" --context "$TARGET_CONTEXT" -n ssc-sandbox delete pvc --all --ignore-not-found=true >/dev/null 2>&1 || true
    "$KUBECTL_PATH" --context "$TARGET_CONTEXT" delete pv workspace-pv-agent workspace-pv-sandbox --ignore-not-found=true >/dev/null 2>&1 || true
    for nodeName in $CLUSTER_NODES; do
        podman exec "$nodeName" rm -rf /var/lib/ssc-workspace >/dev/null 2>&1 || true
    done
    echo "Clean-up complete."
fi

if [[ "$SKIP_BUILD" == "false" ]]; then
    echo "Building container images with Podman..."
    podman build -f Containerfile -t localhost/ssc-agent:dev .
    podman build -f cognee/Containerfile -t localhost/ssc-agent-cognee:dev cognee
fi

for nodeName in $CLUSTER_NODES; do
    nodeArch="$("$KUBECTL_PATH" --context "$TARGET_CONTEXT" get node "$nodeName" -o 'jsonpath={.status.nodeInfo.architecture}')"
    if [[ "$nodeArch" != "amd64" && "$nodeArch" != "arm64" && "$nodeArch" != "aarch64" ]]; then
        echo "Error: Node architecture '$nodeArch' is not supported by the offline seccomp profile." >&2
        exit 1
    fi
    podman exec "$nodeName" mkdir -p /var/lib/kubelet/seccomp
    cat deploy/kind/seccomp-offline.json | podman exec -i "$nodeName" sh -c 'cat > /var/lib/kubelet/seccomp/ssc-offline.json'
    podman exec "$nodeName" mkdir -p /var/lib/ssc-workspace
    podman exec "$nodeName" chmod 777 /var/lib/ssc-workspace
    "$KUBECTL_PATH" --context "$TARGET_CONTEXT" label node "$nodeName" ssc-agent.local/offline-sandbox=true --overwrite
done

for imageName in "localhost/ssc-agent:dev" "localhost/ssc-agent-cognee:dev"; do
    archive="$REPO_ROOT/.tools/image.tar"
    echo "Saving image $imageName and loading into kind cluster '$CLUSTER'..."
    podman save --format docker-archive -o "$archive" "$imageName"
    kind load image-archive "$archive" --name "$CLUSTER"
    rm -f "$archive"
done

echo "Applying network policy controller..."
"$KUBECTL_PATH" --context "$TARGET_CONTEXT" apply -f deploy/kind/network-policy-controller.yaml
"$KUBECTL_PATH" --context "$TARGET_CONTEXT" -n kube-system rollout status daemonset/kube-network-policies --timeout=120s

echo "Applying namespaces, RBAC, and ConfigMaps..."
"$KUBECTL_PATH" --context "$TARGET_CONTEXT" apply -f deploy/kind/namespaces-rbac.yaml
"$KUBECTL_PATH" --context "$TARGET_CONTEXT" apply -f deploy/kind/configmaps.yaml

echo "Applying application configuration and secrets..."
uv run --directory backend python ../scripts/configure_kind.py --kubectl "$KUBECTL_PATH" --context "$TARGET_CONTEXT"

echo "Applying workloads..."
"$KUBECTL_PATH" --context "$TARGET_CONTEXT" apply -f deploy/kind/workloads.yaml
"$KUBECTL_PATH" --context "$TARGET_CONTEXT" -n ssc-agent rollout restart deployment/ssc-agent deployment/cognee

echo "Waiting for workloads to become ready..."
for workload in "statefulset/postgres" "deployment/cognee" "deployment/ssc-agent"; do
    "$KUBECTL_PATH" --context "$TARGET_CONTEXT" -n ssc-agent rollout status "$workload" --timeout=300s
done

echo "Running live sandbox verification..."
cat scripts/smoke_kind.py | "$KUBECTL_PATH" --context "$TARGET_CONTEXT" -n ssc-agent exec -i deployment/ssc-agent -- python -

echo "Deployed. Open http://localhost:8080 after running:"
echo "$KUBECTL_PATH --context $TARGET_CONTEXT -n ssc-agent port-forward service/ssc-agent 8080:8080"
