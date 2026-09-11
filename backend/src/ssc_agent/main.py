import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .agent_service import AgentService
from .auth import require_current_user
from .config import get_settings
from .models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ProblemDetails,
    TestAgentResponse,
)

settings = get_settings()
agent_service = AgentService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await agent_service.close()


app = FastAPI(
    title="Ssc.Agent.Api",
    version="1.0.0",
    openapi_url="/openapi/v1.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


for agent_id, endpoint in {
    "ssc-agent": "/api/ag-ui/ssc-agent",
    "coding": "/api/ag-ui/coding",
}.items():
    add_agent_framework_fastapi_endpoint(
        app,
        agent_service.get_agent(agent_id),
        endpoint,
        dependencies=[Depends(require_current_user)],
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    name="GetHealth",
    operation_id="getHealth",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="1.0.0")


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    responses={400: {"model": ProblemDetails}},
    tags=["Chat"],
    name="SendChatMessage",
    operation_id="sendChatMessage",
)
async def chat(
    request: ChatRequest,
    _: dict[str, object] = Depends(require_current_user),
) -> ChatResponse | JSONResponse:
    if not request.message.strip():
        return JSONResponse(
            status_code=400,
            content={"title": "Message is required.", "status": 400},
        )

    response = await agent_service.run(request.message, request.session_id)
    return ChatResponse(message=response, session_id=request.session_id)


@app.post(
    "/api/test-agent",
    response_model=TestAgentResponse,
    tags=["Diagnostics"],
    name="RunTestAgent",
    operation_id="runTestAgent",
)
async def test_agent(_: dict[str, object] = Depends(require_current_user)) -> TestAgentResponse:
    response = await agent_service.run_test()
    return TestAgentResponse(
        status="ok",
        message="The authenticated MAF test agent responded successfully.",
        agent_response=response,
    )


frontend_dist = Path(
    os.environ.get(
        "FRONTEND_DIST",
        str(Path(__file__).resolve().parents[3] / "frontend" / "dist"),
    )
)
if frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        requested_file = frontend_dist / path
        if path and requested_file.is_file() and frontend_dist in requested_file.parents:
            return FileResponse(requested_file)
        return FileResponse(frontend_dist / "index.html")
