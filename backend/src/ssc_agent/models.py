from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message: str
    session_id: str | None = Field(default=None, alias="sessionId")


class ChatResponse(BaseModel):
    message: str
    session_id: str | None = Field(default=None, alias="sessionId")


class HealthResponse(BaseModel):
    status: str
    version: str


class TestAgentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    message: str
    agent_response: str = Field(alias="agentResponse")


class ProblemDetails(BaseModel):
    title: str
    status: int
