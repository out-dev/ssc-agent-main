"""Cognee-backed conversational memory for Agent Framework agents."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

from agent_framework import AgentSession, ContextProvider, Message, SessionContext
from cognee.modules.search.types import SearchType

from .config import Settings

logger = logging.getLogger(__name__)

current_user_claims: ContextVar[Mapping[str, Any] | None] = ContextVar(
    "current_user_claims",
    default=None,
)


def _principal_key() -> str | None:
    """Return a stable, non-identifying key for the authenticated user."""
    claims = current_user_claims.get()
    if not claims:
        return None

    principal = claims.get("oid") or claims.get("sub")
    if not principal:
        return None
    return hashlib.sha256(str(principal).encode("utf-8")).hexdigest()[:24]


def memory_session_id(session_id: str, *, namespace: str | None = None) -> str | None:
    """Build a user-scoped Cognee session identifier."""
    principal_key = _principal_key()
    if not principal_key or not session_id:
        return None
    agent_namespace = namespace or "shared"
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    return f"ssc:{principal_key}:{agent_namespace}:{session_key}"


class CogneeClient:
    """Cognee Python SDK client connected to the configured remote service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sdk: Any | None = None
        self._connection_lock = asyncio.Lock()

    async def _get_sdk(self) -> Any:
        if self._sdk is None:
            async with self._connection_lock:
                if self._sdk is None:
                    import cognee

                    self._sdk = await cognee.serve(
                        url=self._settings.cognee_url,
                        api_key=self._settings.cognee_api_key,
                    )
        return self._sdk

    async def recall(self, query: str, session_id: str) -> list[dict[str, Any]]:
        import cognee

        await self._get_sdk()
        payload = await cognee.recall(
            query_text=query,
            query_type=SearchType.CHUNKS,
            session_id=session_id,
            scope="session",
            top_k=self._settings.cognee_top_k,
        )
        return payload if isinstance(payload, list) else []

    async def remember(self, question: str, answer: str, session_id: str) -> None:
        import cognee

        await self._get_sdk()
        await cognee.remember(
            cognee.QAEntry(question=question, answer=answer),
            dataset_name=self._settings.cognee_dataset,
            session_id=session_id,
        )

    async def close(self) -> None:
        if self._sdk is not None:
            import cognee

            await cognee.disconnect()
            self._sdk = None


def _format_recall(results: list[dict[str, Any]]) -> str:
    """Turn Cognee's response entries into bounded model context."""
    entries: list[str] = []
    for result in results:
        if not isinstance(result, Mapping):
            entries.append(str(result))
            continue
        question = result.get("question")
        answer = result.get("answer")
        if question or answer:
            entries.append(f"User: {question or '(previous request)'}\nAssistant: {answer or ''}")
        elif result.get("text"):
            entries.append(str(result["text"]))
        else:
            entries.append(json.dumps(result, ensure_ascii=False, default=str))

    return "\n\n".join(entries)[:12_000]


class CogneeMemoryProvider(ContextProvider):
    """Load and persist durable conversational memory for one agent profile."""

    def __init__(self, client: CogneeClient, *, source_id: str) -> None:
        super().__init__(source_id)
        self._client = client

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        if not session.session_id:
            return

        query = "\n".join(
            message.text
            for message in context.input_messages
            if isinstance(message, Message) and message.role == "user" and message.text
        ).strip()
        cognee_session_id = memory_session_id(session.session_id)
        if not query or cognee_session_id is None:
            return

        state["session_id"] = cognee_session_id
        state["question"] = query
        try:
            results = await self._client.recall(query, cognee_session_id)
        except Exception as error:
            logger.warning("Cognee recall failed; continuing without memory: %s", error)
            return

        memory_context = _format_recall(results)
        if memory_context:
            context.extend_instructions(
                self.source_id,
                "Relevant long-term conversation memory from Cognee. "
                "Use it when it helps, but do not mention this memory system unless asked:\n"
                f"{memory_context}",
            )

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        cognee_session_id = state.get("session_id")
        question = state.get("question")
        answer = context.response.text.strip() if context.response else ""
        if not cognee_session_id or not question or not answer:
            return

        try:
            await self._client.remember(question, answer, cognee_session_id)
        except Exception as error:
            logger.warning("Cognee remember failed; agent response was still returned: %s", error)
