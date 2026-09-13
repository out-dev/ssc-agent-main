from functools import lru_cache

from pydantic import AliasChoices, Field
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
    kubernetes_shell_enabled: bool = Field(
        default=False, validation_alias="KUBERNETES_SHELL_ENABLED"
    )
    kubernetes_shell_namespace: str = Field(
        default="ssc-sandbox",
        validation_alias="KUBERNETES_SHELL_NAMESPACE",
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
    )
    kubernetes_shell_image: str = Field(
        default="mcr.microsoft.com/dotnet/sdk:8.0", validation_alias="KUBERNETES_SHELL_IMAGE"
    )
    kubernetes_shell_timeout: float = Field(
        default=30, gt=0, le=600, validation_alias="KUBERNETES_SHELL_TIMEOUT"
    )
    kubernetes_shell_startup_timeout: float = Field(
        default=120, gt=0, le=600, validation_alias="KUBERNETES_SHELL_STARTUP_TIMEOUT"
    )
    kubernetes_shell_concurrency: int = Field(
        default=4, ge=1, le=16, validation_alias="KUBERNETES_SHELL_CONCURRENCY"
    )
    workspace_dir: str = Field(
        default="/workspace",
        validation_alias=AliasChoices("WORKSPACE_DIR", "WORKSPACE_PATH"),
    )
    workspace_pvc: str = Field(
        default="workspace-storage",
        validation_alias=AliasChoices("WORKSPACE_PVC", "KUBERNETES_SHELL_WORKSPACE_PVC"),
    )
    kubernetes_shell_workspace_mount_path: str = Field(
        default="/workspace",
        validation_alias="KUBERNETES_SHELL_WORKSPACE_MOUNT_PATH",
    )
    kubernetes_shell_working_dir: str = Field(
        default="/workspace",
        validation_alias="KUBERNETES_SHELL_WORKING_DIR",
    )

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
