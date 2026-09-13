"""Apply allowlisted .env settings to Kubernetes without writing secrets to disk."""

import argparse
import json
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = (
    "AZURE_CLIENT_ID",
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_SECRET",
    "COGNEE_API_KEY",
    "LLM_API_KEY",
    "EMBEDDING_API_KEY",
    "POSTGRES_PASSWORD",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kubectl", required=True)
    parser.add_argument("--context", required=True)
    args = parser.parse_args()
    values = dotenv_values(ROOT / ".env")
    if not values.get("POSTGRES_PASSWORD"):
        raise SystemExit("Set POSTGRES_PASSWORD in .env before deploying.")
    base = [args.kubectl, "--context", args.context, "-n", "ssc-agent"]
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {"name": "ssc-agent-secrets", "namespace": "ssc-agent"},
        "stringData": {key: values.get(key) or "" for key in SECRET_KEYS},
    }
    # Server-side apply avoids a second secret copy in the last-applied annotation.
    result = subprocess.run(
        base + ["apply", "--server-side", "--field-manager=ssc-kind-config", "-f", "-"],
        input=json.dumps(secret),
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit("Secret configuration failed; check cluster access and permissions.")
    for name in ("ssc-agent", "cognee", "postgres"):
        result = subprocess.run(
            base + ["get", "configmap", name + "-config", "-o", "json"],
            text=True,
            capture_output=True,
            check=True,
        )
        config = json.loads(result.stdout)
        for key in config["data"]:
            source = {
                "DB_USERNAME": "POSTGRES_USER",
                "DB_NAME": "POSTGRES_DB",
                "ENABLE_BACKEND_ACCESS_CONTROL": "COGNEE_ENABLE_BACKEND_ACCESS_CONTROL",
            }.get(key, key)
            # Internal service addresses and the namespace are deployment-owned.
            if key in {"COGNEE_URL", "DB_HOST", "DB_PORT", "KUBERNETES_SHELL_NAMESPACE"}:
                continue
            if values.get(source) is not None:
                config["data"][key] = values[source]
        result = subprocess.run(
            base + ["replace", "-f", "-"], input=json.dumps(config), text=True, capture_output=True
        )
        if result.returncode:
            raise SystemExit(f"Configuration failed for {name}.")
    print("Applied application configuration and secrets (values hidden).")


if __name__ == "__main__":
    main()
