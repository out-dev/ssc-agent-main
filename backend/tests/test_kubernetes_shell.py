import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from ssc_agent.config import Settings
from ssc_agent.kubernetes_shell import KubernetesShellTool


def settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def response(data=None, text=None):
    return httpx.Response(200, json=data) if text is None else httpx.Response(200, text=text)


@pytest.mark.parametrize("exit_code", [0, 7, 137])
def test_output_exit_status_and_pod_removal(exit_code):
    async def scenario():
        shell = KubernetesShellTool(settings())
        calls = []

        async def request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path.endswith("/log"):
                assert kwargs["params"]["limitBytes"] == "65536"
                return response(text="output\nerror output")
            return response(
                {
                    "status": {
                        "phase": "Succeeded" if exit_code == 0 else "Failed",
                        "containerStatuses": [
                            {"name": "shell", "state": {"terminated": {"exitCode": exit_code}}}
                        ],
                    }
                }
            )

        shell._request = request
        result = await shell.run("echo output; echo 'error output' >&2")
        assert f"Exit code: {exit_code}" in result
        assert "output\nerror output" in result
        assert calls[0][0] == "POST"
        assert calls[-1][0] == "DELETE"
        assert not shell._active
        pod = calls[0][2]["json"]["spec"]
        assert pod["automountServiceAccountToken"] is False
        assert pod["restartPolicy"] == "Never"
        assert pod["securityContext"]["runAsNonRoot"]
        assert pod["securityContext"]["seccompProfile"] == {
            "type": "Localhost",
            "localhostProfile": "ssc-offline.json",
        }
        assert pod["nodeSelector"] == {"ssc-agent.local/offline-sandbox": "true"}
        container = pod["containers"][0]
        assert container["securityContext"]["readOnlyRootFilesystem"]
        assert container["command"][-1] == "echo output; echo 'error output' >&2"
        assert container["command"][0] == "/usr/bin/timeout"
        assert container["workingDir"] == "/workspace"
        assert container["volumeMounts"] == [
            {"name": "tmp", "mountPath": "/tmp"},
            {"name": "workspace", "mountPath": "/workspace"},
        ]
        assert pod["volumes"] == [
            {"name": "tmp", "emptyDir": {"sizeLimit": "128Mi"}},
            {"name": "workspace", "persistentVolumeClaim": {"claimName": "workspace-storage"}},
        ]

    asyncio.run(scenario())


def test_pod_without_workspace_pvc():
    shell = KubernetesShellTool(settings(workspace_pvc=""))
    pod = shell.pod("test-pod", "echo hello")["spec"]
    assert pod["volumes"] == [{"name": "tmp", "emptyDir": {"sizeLimit": "128Mi"}}]
    assert pod["containers"][0]["volumeMounts"] == [{"name": "tmp", "mountPath": "/tmp"}]
    assert pod["containers"][0]["workingDir"] == "/tmp"


def test_pod_with_custom_workspace_settings():
    shell = KubernetesShellTool(
        settings(
            workspace_pvc="custom-pvc",
            kubernetes_shell_workspace_mount_path="/custom-space",
            kubernetes_shell_working_dir="/custom-space/app",
        )
    )
    pod = shell.pod("test-pod", "dotnet build")["spec"]
    assert pod["volumes"] == [
        {"name": "tmp", "emptyDir": {"sizeLimit": "128Mi"}},
        {"name": "workspace", "persistentVolumeClaim": {"claimName": "custom-pvc"}},
    ]
    assert pod["containers"][0]["volumeMounts"] == [
        {"name": "tmp", "mountPath": "/tmp"},
        {"name": "workspace", "mountPath": "/custom-space"},
    ]
    assert pod["containers"][0]["workingDir"] == "/custom-space/app"


def test_cancellation_removes_pod():
    async def scenario():
        shell = KubernetesShellTool(settings())
        waiting = asyncio.Event()
        deleted = []

        async def request(method, path, **kwargs):
            if method == "GET":
                waiting.set()
                await asyncio.Event().wait()
            if method == "DELETE":
                deleted.append(path)
            return response({})

        shell._request = request
        task = asyncio.create_task(shell.run("sleep 100"))
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(deleted) == 1
        assert not shell._active

    asyncio.run(scenario())


def test_timeout_and_uncertain_create_both_attempt_cleanup():
    async def scenario(error):
        shell = KubernetesShellTool(settings())
        deleted = []

        async def request(method, path, **kwargs):
            if method == "POST":
                raise error
            if method == "DELETE":
                deleted.append(path)
            return response({})

        shell._request = request
        result = await shell.run("echo hello")
        assert "timed out" in result or "unavailable" in result
        assert len(deleted) == 1

    for error in [TimeoutError(), httpx.ReadTimeout("lost API response")]:
        asyncio.run(scenario(error))


def test_concurrent_invocations_have_distinct_pods():
    async def scenario():
        shell = KubernetesShellTool(settings())
        names = []

        async def request(method, path, **kwargs):
            if method == "POST":
                names.append(kwargs["json"]["metadata"]["name"])
            return response({"status": {"phase": "Failed", "reason": "DeadlineExceeded"}})

        shell._request = request
        await asyncio.gather(shell.run("echo a"), shell.run("echo b"))
        assert len(set(names)) == 2
        assert not shell._active

    asyncio.run(scenario())


def test_reaper_leaves_live_pods_alone():
    async def scenario():
        shell = KubernetesShellTool(settings())
        deleted = []
        now = datetime.now(UTC)
        pods = [
            {
                "metadata": {
                    "name": name,
                    "creationTimestamp": (now - timedelta(seconds=age)).isoformat(),
                },
                "spec": {"activeDeadlineSeconds": 150},
            }
            for name, age in [("live", 200), ("orphan", 400)]
        ]

        async def request(method, path, **kwargs):
            if method == "DELETE":
                deleted.append(path.rsplit("/", 1)[1])
            else:
                assert (
                    kwargs["params"]["labelSelector"] == "app.kubernetes.io/managed-by=ssc-sandbox"
                )
            return response({"items": pods})

        shell._request = request
        await shell.reap()
        assert deleted == ["orphan"]

    asyncio.run(scenario())
