"""Run shell invocations in disposable pods using the in-cluster Kubernetes API."""

import asyncio
import logging
import math
import os
import ssl
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from agent_framework import FunctionTool, tool

from .config import Settings

logger = logging.getLogger(__name__)
SERVICE_ACCOUNT = Path("/var/run/secrets/kubernetes.io/serviceaccount")
LABEL = "app.kubernetes.io/managed-by=ssc-sandbox"


class KubernetesShellTool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: httpx.AsyncClient | None = None
        self._active: set[str] = set()
        self._slots = asyncio.Semaphore(settings.kubernetes_shell_concurrency)
        self._path = f"/api/v1/namespaces/{settings.kubernetes_shell_namespace}/pods"

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._client is None:
            host = os.environ["KUBERNETES_SERVICE_HOST"]
            port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
            self._client = httpx.AsyncClient(
                base_url=f"https://{host}:{port}",
                verify=ssl.create_default_context(cafile=str(SERVICE_ACCOUNT / "ca.crt")),
                timeout=15,
                trust_env=False,
            )
        # Projected tokens rotate; read the current token for every request.
        response = await self._client.request(
            method,
            path,
            headers={"Authorization": f"Bearer {(SERVICE_ACCOUNT / 'token').read_text().strip()}"},
            **kwargs,
        )
        response.raise_for_status()
        return response

    def pod(self, name: str, command: str) -> dict:
        settings = self.settings
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": name, "labels": {"app.kubernetes.io/managed-by": "ssc-sandbox"}},
            "spec": {
                "restartPolicy": "Never",
                "automountServiceAccountToken": False,
                "enableServiceLinks": False,
                "nodeSelector": {"ssc-agent.local/offline-sandbox": "true"},
                "terminationGracePeriodSeconds": 1,
                "activeDeadlineSeconds": math.ceil(
                    settings.kubernetes_shell_startup_timeout + settings.kubernetes_shell_timeout
                ),
                "securityContext": {
                    "runAsNonRoot": True,
                    "runAsUser": 10001,
                    "runAsGroup": 10001,
                    "fsGroup": 10001,
                    "seccompProfile": {"type": "Localhost", "localhostProfile": "ssc-offline.json"},
                },
                "containers": [
                    {
                        "name": "shell",
                        "image": settings.kubernetes_shell_image,
                        "imagePullPolicy": "IfNotPresent",
                        "workingDir": "/tmp",
                        "command": [
                            "/usr/bin/timeout",
                            "--signal=KILL",
                            str(settings.kubernetes_shell_timeout),
                            "/bin/sh",
                            "-c",
                            command,
                        ],
                        "env": [
                            {"name": "HOME", "value": "/tmp"},
                            {"name": "DOTNET_CLI_HOME", "value": "/tmp"},
                            {"name": "DOTNET_SKIP_FIRST_TIME_EXPERIENCE", "value": "1"},
                        ],
                        "securityContext": {
                            "allowPrivilegeEscalation": False,
                            "readOnlyRootFilesystem": True,
                            "capabilities": {"drop": ["ALL"]},
                        },
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "128Mi"},
                            "limits": {"cpu": "1", "memory": "512Mi", "ephemeral-storage": "256Mi"},
                        },
                        "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
                    }
                ],
                "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": "128Mi"}}],
            },
        }

    async def _delete(self, name: str) -> None:
        try:
            await self._request("DELETE", f"{self._path}/{name}", json={"gracePeriodSeconds": 0})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        self._active.discard(name)

    async def run(self, command: str) -> str:
        async with self._slots:
            name = f"shell-{uuid4().hex}"
            self._active.add(name)
            try:
                async with asyncio.timeout(
                    self.settings.kubernetes_shell_startup_timeout
                    + self.settings.kubernetes_shell_timeout
                    + 15
                ):
                    await self._request("POST", self._path, json=self.pod(name, command))
                    while True:
                        response = await self._request("GET", f"{self._path}/{name}")
                        status = response.json().get("status", {})
                        if status.get("phase") in {"Succeeded", "Failed"}:
                            containers = status.get("containerStatuses", [])
                            terminated = next(
                                (
                                    c.get("state", {}).get("terminated")
                                    for c in containers
                                    if c.get("name") == "shell"
                                ),
                                None,
                            )
                            if not terminated:
                                return f"Sandbox failed: {status.get('reason', 'Unknown')}"
                            logs = await self._request(
                                "GET",
                                f"{self._path}/{name}/log",
                                params={"container": "shell", "limitBytes": "65536"},
                            )
                            return (
                                f"Exit code: {terminated['exitCode']}\n"
                                f"Output (up to 65536 bytes):\n{logs.text}"
                            )
                        await asyncio.sleep(0.5)
            except TimeoutError:
                return "Sandbox timed out during startup or execution."
            except (httpx.HTTPError, OSError, KeyError):
                logger.exception("Kubernetes sandbox invocation failed")
                return "Kubernetes sandbox unavailable; command execution could not be confirmed."
            finally:
                # Shield cleanup from request cancellation. A scheduled reaper handles crashes.
                cleanup = asyncio.create_task(self._delete(name))
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
                    raise
                except Exception:
                    logger.exception("Sandbox deletion failed; scheduled cleanup will retry")

    def as_function(self) -> FunctionTool:
        return tool(
            func=self.run,
            name="run_shell",
            approval_mode="never_require",
            description="Run a shell command in a fresh offline Kubernetes pod. "
            "Only /tmp is writable. Files are deleted after each invocation. "
            "Combine related commands in one invocation. The image includes .NET 8.",
            kind="shell",
        )

    async def reap(self) -> None:
        response = await self._request("GET", self._path, params={"labelSelector": LABEL})
        for pod in response.json()["items"]:
            created = datetime.fromisoformat(
                pod["metadata"]["creationTimestamp"].replace("Z", "+00:00")
            )
            # Longer than the configured deadline; do not remove another replica's live work.
            age = (datetime.now(UTC) - created).total_seconds()
            deadline = pod["spec"].get("activeDeadlineSeconds", 300)
            if age > deadline + 120:
                await self._delete(pod["metadata"]["name"])

    async def close(self) -> None:
        for name in tuple(self._active):
            await self._delete(name)
        if self._client is not None:
            await self._client.aclose()
            self._client = None


async def _reap() -> None:
    shell = KubernetesShellTool(Settings())
    try:
        await shell.reap()
    finally:
        await shell.close()


if __name__ == "__main__":
    asyncio.run(_reap())
