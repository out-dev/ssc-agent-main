from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    foundry_project_endpoint: str = Field(
        default="https://ssc-foundery.services.ai.azure.com/api/projects/ssc-proj-default",
        validation_alias="FOUNDRY_PROJECT_ENDPOINT",
    )
    foundry_model: str = Field(default="gpt-5.3-codex", validation_alias="FOUNDRY_MODEL")
    foundry_instructions: str = Field(
        default=(
            "You are a helpful assistant for the SSC Agent application. "
            "Be concise, accurate, and clear."
        ),
        validation_alias="FOUNDRY_INSTRUCTIONS",
    )
    cognee_enabled: bool = Field(default=True, validation_alias="COGNEE_ENABLED")
    cognee_url: str = Field(default="http://localhost:8000", validation_alias="COGNEE_URL")
    cognee_api_key: str = Field(default="", validation_alias="COGNEE_API_KEY")
    cognee_dataset: str = Field(
        default="ssc_agent_memory",
        validation_alias="COGNEE_DATASET",
    )
    cognee_timeout: float = Field(default=10.0, validation_alias="COGNEE_TIMEOUT")
    cognee_top_k: int = Field(default=5, validation_alias="COGNEE_TOP_K")
    docker_shell_enabled: bool = Field(default=False, validation_alias="DOCKER_SHELL_ENABLED")
    docker_shell_image: str = Field(
        default="mcr.microsoft.com/azurelinux/base/core:3.0",
        validation_alias="DOCKER_SHELL_IMAGE",
    )
    docker_shell_mode: Literal["stateless", "persistent"] = Field(
        default="stateless",
        validation_alias="DOCKER_SHELL_MODE",
    )
    docker_shell_binary: str = Field(default="podman", validation_alias="DOCKER_SHELL_BINARY")
    docker_shell_timeout: float = Field(default=30.0, validation_alias="DOCKER_SHELL_TIMEOUT")
    docker_shell_host_workdir: str | None = Field(
        default=None,
        validation_alias="DOCKER_SHELL_HOST_WORKDIR",
    )
    docker_shell_workdir: str = Field(default="/tmp", validation_alias="DOCKER_SHELL_WORKDIR")

    @field_validator("docker_shell_host_workdir", mode="before")
    @classmethod
    def empty_host_workdir_is_unset(cls, value: str | None) -> str | None:
        """Do not turn an empty environment value into an invalid bind mount."""
        if value is None or not str(value).strip():
            return None
        return str(value)
    msal_tenant_id: str = Field(
        default="13eb42f4-a065-4aed-a3da-ae0114f35f43",
        validation_alias="MSAL_TENANT_ID",
    )
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:8080",
        validation_alias="CORS_ALLOWED_ORIGINS",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def token_issuers(self) -> tuple[str, str]:
        return (
            f"https://login.microsoftonline.com/{self.msal_tenant_id}/v2.0",
            f"https://sts.windows.net/{self.msal_tenant_id}/",
        )



@lru_cache
def get_settings() -> Settings:
    return Settings()
