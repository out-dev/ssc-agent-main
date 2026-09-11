import pytest
from agent_framework import AgentSession, Message, SessionContext

from ssc_agent.config import Settings
from ssc_agent.memory import (
    CogneeClient,
    CogneeMemoryProvider,
    current_user_claims,
    memory_session_id,
)


def test_memory_session_id_is_user_scoped() -> None:
    token = current_user_claims.set({"oid": "user-a"})
    try:
        first = memory_session_id("thread-1")
        second = memory_session_id("thread-1")
    finally:
        current_user_claims.reset(token)

    other_token = current_user_claims.set({"oid": "user-b"})
    try:
        other = memory_session_id("thread-1")
    finally:
        current_user_claims.reset(other_token)

    assert first == second
    assert first != other


@pytest.mark.anyio
async def test_cognee_client_uses_sdk(monkeypatch) -> None:
    import cognee
    from cognee.modules.search.types import SearchType

    calls: list[tuple[str, dict]] = []

    async def fake_serve(*, url: str, api_key: str):
        calls.append(("serve", {"url": url, "api_key": api_key}))
        return object()

    async def fake_recall(**kwargs):
        calls.append(("recall", kwargs))
        return [{"question": "Old?", "answer": "Yes."}]

    async def fake_remember(entry, **kwargs):
        calls.append(("remember", {"entry": entry, **kwargs}))

    async def fake_disconnect():
        calls.append(("disconnect", {}))

    monkeypatch.setattr(cognee, "serve", fake_serve)
    monkeypatch.setattr(cognee, "recall", fake_recall)
    monkeypatch.setattr(cognee, "remember", fake_remember)
    monkeypatch.setattr(cognee, "disconnect", fake_disconnect)

    client = CogneeClient(
        Settings(cognee_url="http://cognee:8000", cognee_api_key="test-key")
    )
    try:
        recalled = await client.recall("current?", "session-1")
        await client.remember("current?", "Correct.", "session-1")
    finally:
        await client.close()

    assert recalled == [{"question": "Old?", "answer": "Yes."}]
    assert calls[0] == ("serve", {"url": "http://cognee:8000", "api_key": "test-key"})
    assert calls[1][0] == "recall"
    assert calls[1][1] == {
        "query_text": "current?",
        "query_type": SearchType.CHUNKS,
        "session_id": "session-1",
        "scope": "session",
        "top_k": 5,
    }
    assert calls[2][0] == "remember"
    assert calls[2][1]["entry"].type == "qa"
    assert calls[2][1]["entry"].question == "current?"
    assert calls[2][1]["entry"].answer == "Correct."
    assert calls[2][1]["dataset_name"] == "ssc_agent_memory"
    assert calls[2][1]["session_id"] == "session-1"
    assert calls[3] == ("disconnect", {})


@pytest.mark.anyio
async def test_memory_provider_recalls_and_remembers() -> None:
    class FakeCognee:
        async def recall(self, query: str, session_id: str) -> list[dict[str, str]]:
            assert query == "What did I say?"
            assert session_id.startswith("ssc:")
            return [{"question": "Earlier?", "answer": "A preference."}]

        async def remember(self, question: str, answer: str, session_id: str) -> None:
            assert question == "What did I say?"
            assert answer == "You said a preference."
            assert session_id.startswith("ssc:")

    claims_token = current_user_claims.set({"sub": "user-a"})
    try:
        provider = CogneeMemoryProvider(FakeCognee(), source_id="cognee-memory")
        session = AgentSession(session_id="thread-1")
        context = SessionContext(
            session_id=session.session_id,
            input_messages=[Message("user", ["What did I say?"])],
        )
        state: dict[str, str] = {}

        await provider.before_run(agent=None, session=session, context=context, state=state)
        context._response = type("Response", (), {"text": "You said a preference."})()
        await provider.after_run(agent=None, session=session, context=context, state=state)
    finally:
        current_user_claims.reset(claims_token)

    assert "Relevant long-term conversation memory" in "\n".join(context.instructions)
