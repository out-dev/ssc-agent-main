import asyncio
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from ssc_agent.auth import require_current_user, token_validator
from ssc_agent.main import agent_service, app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


def test_chat_requires_bearer_token() -> None:
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_test_agent_requires_bearer_token() -> None:
    with TestClient(app) as client:
        response = client.post("/api/test-agent")

    assert response.status_code == 401


@pytest.mark.parametrize("endpoint", ["/api/ag-ui/ssc-agent", "/api/ag-ui/coding"])
def test_ag_ui_endpoints_require_bearer_token(endpoint: str) -> None:
    with TestClient(app) as client:
        response = client.post(endpoint, json={})

    assert response.status_code == 401


def test_test_agent_returns_maf_smoke_result(monkeypatch) -> None:
    async def fake_run_test() -> str:
        return "SSC Agent test connection is working."

    app.dependency_overrides[require_current_user] = lambda: {"sub": "test-user"}
    monkeypatch.setattr(agent_service, "run_test", fake_run_test)
    try:
        with TestClient(app) as client:
            response = client.post("/api/test-agent")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "The authenticated MAF test agent responded successfully.",
        "agentResponse": "SSC Agent test connection is working.",
    }


def test_empty_chat_message_is_rejected_after_authentication() -> None:
    app.dependency_overrides[require_current_user] = lambda: {"sub": "test-user"}
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat", json={"message": "  "})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"title": "Message is required.", "status": 400}


def test_chat_returns_agent_answer_after_authentication(monkeypatch) -> None:
    async def fake_run(message: str, session_id: str | None = None) -> str:
        assert message == "Say hello"
        return "Hello from the SSC Agent."

    app.dependency_overrides[require_current_user] = lambda: {"sub": "test-user"}
    monkeypatch.setattr(agent_service, "run", fake_run)
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat", json={"message": "Say hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"message": "Hello from the SSC Agent.", "sessionId": None}


def test_token_from_configured_tenant_is_accepted_without_api_scope(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))

    async def fake_get_jwks():
        return {"keys": [{**public_jwk, "kid": "test-key"}]}

    monkeypatch.setattr(token_validator, "_get_jwks", fake_get_jwks)
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": token_validator._settings.token_issuers[0],
            "aud": "https://unregistered-resource.example",
            "tid": token_validator._settings.msal_tenant_id,
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    claims = asyncio.run(token_validator.validate(token))

    assert claims["tid"] == token_validator._settings.msal_tenant_id

    invalid_tenant_token = jwt.encode(
        {
            "iss": token_validator._settings.token_issuers[0],
            "aud": "https://unregistered-resource.example",
            "tid": "another-tenant-id",
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(token_validator.validate(invalid_tenant_token))

    assert error.value.status_code == 401
