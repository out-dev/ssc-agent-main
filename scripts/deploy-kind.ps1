param(
    [string]$Cluster = "kind-cluster",
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$kubectlCommand = Get-Command kubectl -ErrorAction SilentlyContinue
$kubectlPath = if ($kubectlCommand) { $kubectlCommand.Source } else { Join-Path $repoRoot ".tools/kubectl.exe" }
if (-not (Test-Path -LiteralPath $kubectlPath)) { throw "Install kubectl or place it at .tools/kubectl.exe." }
$targetContext = "kind-$Cluster"
function Invoke-Checked {
    param([string]$File, [string[]]$Arguments)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit code $LASTEXITCODE" }
}
Invoke-Checked $kubectlPath @("--context", $targetContext, "get", "nodes")
New-Item -ItemType Directory -Force .tools | Out-Null
if (-not $SkipBuild) {
    Invoke-Checked podman @("build", "-f", "Containerfile", "-t", "localhost/ssc-agent:dev", ".")
    Invoke-Checked podman @("build", "-f", "cognee/Containerfile", "-t", "localhost/ssc-agent-cognee:dev", "cognee")
}
$env:KIND_EXPERIMENTAL_PROVIDER = "podman"
$clusterNodes = & kind get nodes --name $Cluster
if ($LASTEXITCODE -ne 0) { throw "Unable to list kind nodes." }
foreach ($nodeName in $clusterNodes) {
    $nodeArch = & $kubectlPath --context $targetContext get node $nodeName -o 'jsonpath={.status.nodeInfo.architecture}'
    if ($LASTEXITCODE -ne 0 -or $nodeArch -ne "amd64") { throw "The offline seccomp profile currently supports amd64 nodes." }
    Invoke-Checked podman @("exec", $nodeName, "mkdir", "-p", "/var/lib/kubelet/seccomp")
    Get-Content -Raw deploy/kind/seccomp-offline.json | & podman exec -i $nodeName sh -c 'cat > /var/lib/kubelet/seccomp/ssc-offline.json'
    if ($LASTEXITCODE -ne 0) { throw "Could not install the offline seccomp profile on $nodeName." }
    Invoke-Checked $kubectlPath @("--context", $targetContext, "label", "node", $nodeName, "ssc-agent.local/offline-sandbox=true", "--overwrite")
}
foreach ($imageName in @("localhost/ssc-agent:dev", "localhost/ssc-agent-cognee:dev")) {
    $archive = Join-Path $repoRoot ".tools/image.tar"
    Invoke-Checked podman @("save", "--format", "docker-archive", "-o", $archive, $imageName)
    Invoke-Checked kind @("load", "image-archive", $archive, "--name", $Cluster)
    Remove-Item -LiteralPath $archive
}
Invoke-Checked $kubectlPath @("--context", $targetContext, "apply", "-f", "deploy/kind/network-policy-controller.yaml")
Invoke-Checked $kubectlPath @("--context", $targetContext, "-n", "kube-system", "rollout", "status", "daemonset/kube-network-policies", "--timeout=120s")
Invoke-Checked $kubectlPath @("--context", $targetContext, "apply", "-f", "deploy/kind/namespaces-rbac.yaml")
Invoke-Checked $kubectlPath @("--context", $targetContext, "apply", "-f", "deploy/kind/configmaps.yaml")
Invoke-Checked uv @("run", "--directory", "backend", "python", "../scripts/configure_kind.py", "--kubectl", $kubectlPath, "--context", $targetContext)
Invoke-Checked $kubectlPath @("--context", $targetContext, "apply", "-f", "deploy/kind/workloads.yaml")
Invoke-Checked $kubectlPath @("--context", $targetContext, "-n", "ssc-agent", "rollout", "restart", "deployment/ssc-agent", "deployment/cognee")
foreach ($workload in @("statefulset/postgres", "deployment/cognee", "deployment/ssc-agent")) {
    Invoke-Checked $kubectlPath @("--context", $targetContext, "-n", "ssc-agent", "rollout", "status", $workload, "--timeout=300s")
}
Get-Content -Raw scripts/smoke_kind.py | & $kubectlPath --context $targetContext -n ssc-agent exec -i deployment/ssc-agent -- python -
if ($LASTEXITCODE -ne 0) { throw "Live sandbox verification failed." }
Write-Host "Deployed. Open http://localhost:8080 after running:"
Write-Host "$kubectlPath --context $targetContext -n ssc-agent port-forward service/ssc-agent 8080:8080"
