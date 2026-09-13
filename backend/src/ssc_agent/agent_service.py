import asyncio
import logging

from agent_framework import Agent, AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential

from .config import Settings
from .kubernetes_shell import KubernetesShellTool
from .memory import CogneeClient, CogneeMemoryProvider
from .workspace import WorkspaceManager

logger = logging.getLogger(__name__)

TEST_AGENT_INSTRUCTIONS = (
    "You are a connectivity test agent. Reply with a short confirmation that "
    "the Microsoft Agent Framework and model connection are working."
)

AGENT_PROFILES = {
    "ssc-agent": {
        "name": "ssc-agent",
        "suffix": "",
    },
    "coding": {
        "name": "ssc-coding-agent",
        "suffix": (
            " Focus on software engineering tasks, explain implementation trade-offs, "
            "and prefer practical, verifiable solutions. You have access to a shared workspace "
            "and an isolated sandbox shell. You can create, read, and edit project files, "
            "and run shell commands in the sandbox to build, run, test (.NET 8 CLI), "
            "and debug projects."
        ),
    },
}


class AgentService:
    """Runs user messages through a Microsoft Agent Framework agent."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._workspace = WorkspaceManager(settings.workspace_dir)
        self._memory = CogneeClient(settings) if settings.cognee_enabled else None
        self._credential: DefaultAzureCredential | None = None
        self._client: FoundryChatClient | None = None
        self._agent: Agent | None = None
        self._agents: dict[str, Agent] = {}
        self._shell: KubernetesShellTool | None = None
        self._sessions: dict[str, AgentSession] = {}
        self._initialization_lock = asyncio.Lock()
        self._session_lock = asyncio.Lock()

    @property
    def workspace(self) -> WorkspaceManager:
        return self._workspace

    def _create_agent(self, agent_id: str) -> Agent:
        profile = AGENT_PROFILES.get(agent_id)
        if profile is None:
            raise ValueError(f"Unknown agent profile: {agent_id}")

        if self._client is None:
            self._credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=True,
            )
            self._client = FoundryChatClient(
                project_endpoint=self._settings.foundry_project_endpoint,
                model=self._settings.foundry_model,
                credential=self._credential,
            )

        tools = list(self._workspace.get_tools())
        if self._settings.kubernetes_shell_enabled:
            if self._shell is None:
                try:
                    self._shell = KubernetesShellTool(
                        self._settings,
                    )
                except Exception:
                    logger.warning(
                        "KubernetesShellTool initialization failed; continuing without shell tool.",
                        exc_info=True,
                    )
                    self._shell = None
            if self._shell is not None:
                tools.append(self._client.get_shell_tool(func=self._shell.as_function()))

        agent = Agent(
            client=self._client,
            name=profile["name"],
            instructions=self._settings.foundry_instructions + profile["suffix"],
            tools=tools if tools else None,
            context_providers=(
                [CogneeMemoryProvider(self._memory, source_id=f"cognee-memory-{agent_id}")]
                if self._memory is not None
                else None
            ),
        )
        self._agents[agent_id] = agent
        if agent_id == "ssc-agent":
            self._agent = agent
        logger.info("Microsoft Agent Framework agent initialized: %s", agent_id)
        return agent

    def get_agent(self, agent_id: str = "ssc-agent") -> Agent:
        """Return an agent profile for AG-UI endpoint registration."""
        return self._agents.get(agent_id) or self._create_agent(agent_id)

    async def _get_agent(self, agent_id: str = "ssc-agent") -> Agent:
        existing_agent = self._agents.get(agent_id)
        if existing_agent is not None:
            return existing_agent

        async with self._initialization_lock:
            return self._agents.get(agent_id) or self._create_agent(agent_id)

    async def _get_session(self, session_id: str | None) -> AgentSession:
        if not session_id:
            return AgentSession()

        async with self._session_lock:
            return self._sessions.setdefault(session_id, AgentSession())

    async def run(self, message: str, session_id: str | None = None) -> str:
        agent = await self._get_agent()
        session = await self._get_session(session_id)
        logger.info("Running agent request with message length %d", len(message))
        response = await agent.run(message, session=session)
        return response.text

    async def run_test(self) -> str:
        """Run a deterministic smoke request through a dedicated MAF test agent."""
        await self._get_agent("ssc-agent")
        if self._client is None:
            raise RuntimeError("The Microsoft Agent Framework client is not initialized")

        test_agent = Agent(
            client=self._client,
            name="ssc-agent-test",
            instructions=TEST_AGENT_INSTRUCTIONS,
        )
        response = await test_agent.run(
            "Confirm that the SSC Agent test connection is working in one short sentence."
        )
        return response.text

    async def close(self) -> None:
        if self._shell is not None:
            await self._shell.close()
        if self._client is not None:
            await self._client.client.close()
            await self._client.project_client.close()
        if self._credential is not None:
            await self._credential.close()
        if self._memory is not None:
            await self._memory.close()
