"""Run inside the app pod: python - < scripts/smoke_kind.py (via kubectl exec -i)."""

import asyncio
import os
import shlex
import socket
import sys
from pathlib import Path

import httpx

sys.path.insert(0, "/app/src")
from ssc_agent.config import Settings  # noqa: E402
from ssc_agent.kubernetes_shell import KubernetesShellTool  # noqa: E402


async def main():
    shell = KubernetesShellTool(Settings())
    created = []
    request = shell._request

    async def track(method, path, **kwargs):
        if method == "POST":
            created.append(kwargs["json"]["metadata"]["name"])
        return await request(method, path, **kwargs)

    shell._request = track
    try:
        result = await shell.run("id -u; dotnet --version; echo hello; echo error >&2; exit 7")
        assert "Exit code: 7" in result and "10001" in result and "hello" in result, result
        print("PASS: .NET sandbox, non-root execution, output and exit status")
        result = await shell.run(
            "test ! -e /var/run/secrets/kubernetes.io/serviceaccount/token && "
            "touch /tmp/invocation-only && ! touch /root-write-test && echo isolated"
        )
        assert "Exit code: 0" in result and "isolated" in result, result
        result = await shell.run("test ! -e /tmp/invocation-only && echo fresh")
        assert "Exit code: 0" in result and "fresh" in result, result
        print("PASS: no token, read-only root, disposable files")
        results = await asyncio.gather(
            shell.run("echo invocation-a"), shell.run("echo invocation-b")
        )
        assert "invocation-a" in results[0] and "invocation-b" in results[1], results
        assert len(created) == len(set(created))
        print("PASS: concurrent invocation isolation")
        shell.settings.kubernetes_shell_timeout = 1
        result = await shell.run("sleep 20")
        assert "Exit code: 137" in result or "timed out" in result, result
        print("PASS: command timeout")
        shell.settings.kubernetes_shell_timeout = 30
        task = asyncio.create_task(shell.run("sleep 25"))
        await asyncio.sleep(2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        print("PASS: cancellation")

        # Verify shared workspace communication between agent service and sandbox pod
        from ssc_agent.workspace import WorkspaceManager

        workspace = WorkspaceManager(shell.settings.workspace_dir)
        workspace.write_file("smoke-shared.txt", "agent-created-content\n")
        result = await shell.run("cat smoke-shared.txt && echo sandbox-appended >> smoke-shared.txt")
        assert "Exit code: 0" in result and "agent-created-content" in result, result
        read_back = workspace.read_file("smoke-shared.txt")
        assert "agent-created-content" in read_back and "sandbox-appended" in read_back, read_back
        workspace.delete_file("smoke-shared.txt")
        print("PASS: shared workspace read/write between agent and sandbox")

        # Use the application image's Python for precise TCP and UDP probes.
        # Its pod security and namespace policy are identical to the SDK sandbox.
        shell.settings.kubernetes_shell_image = "localhost/ssc-agent:dev"
        dns = next(
            line.split()[1]
            for line in Path("/etc/resolv.conf").read_text().splitlines()
            if line.startswith("nameserver")
        )
        targets = [(os.environ["KUBERNETES_SERVICE_HOST"], 443), (dns, 53), ("1.1.1.1", 443)]
        for host, port in targets:
            with socket.create_connection((host, port), timeout=5):
                pass
        code = f"""
import socket
for host, port in {targets!r}:
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except (TimeoutError, PermissionError):
        print('blocked', host, port)
    else:
        raise AssertionError('network access was allowed')
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    query = bytes.fromhex('123401000001000000000000')
    query += b'\\x0akubernetes\\x07default\\x03svc\\x07cluster\\x05local'
    query += bytes.fromhex('0000010001')
    s.sendto(query, ({dns!r}, 53))
    s.recvfrom(512)
except (TimeoutError, PermissionError):
    print('dns blocked')
else:
    raise AssertionError('DNS traffic was allowed')
"""
        result = await shell.run("python -c " + shlex.quote(code))
        assert "Exit code: 0" in result and result.count("blocked") == 4, result
        print("PASS: API, DNS (TCP/UDP), and internet egress denied; controls reachable")
        for name in created:
            try:
                await request("GET", f"{shell._path}/{name}")
            except httpx.HTTPStatusError as exc:
                assert exc.response.status_code == 404
            else:
                raise AssertionError(f"Sandbox pod retained: {name}")
        print("PASS: all temporary pods deleted")
    finally:
        await shell.close()


asyncio.run(main())
