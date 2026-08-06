from functools import lru_cache

from pydantic import EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Velocity CRM API"
    app_version: str = "0.1.0"
    database_url: str = Field(
        default="postgresql+asyncpg://velocity_app:velocity_dev@localhost:5432/velocity"
    )
    admin_email: EmailStr = "admin@velocitycrm.com"
    admin_password: str = Field(default="VelocityAdmin@2026", min_length=12)
    jwt_secret: str = Field(default="velocity-local-development-secret", min_length=24)
    access_token_minutes: int = Field(default=480, gt=0)
    frontend_url: str = "http://localhost:3000"
    embedding_provider: str = "local"
    google_api_key: str | None = None
    google_embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = Field(default=768, gt=0)
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    gemini_temperature: float = Field(default=0.2, ge=0, le=2)
    gemini_timeout_seconds: float = Field(default=30, gt=0)
    proactive_monitoring_enabled: bool = True
    proactive_monitoring_interval_seconds: int = Field(default=60, gt=0)
    crm_adapter: str = "local"
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_accounts_url: str = "https://accounts.zoho.in"
    zoho_redirect_uri: str = "http://localhost:8000/api/integrations/zoho/callback"
    zoho_scopes: str = (
        "ZohoCRM.modules.deals.READ,ZohoCRM.modules.deals.UPDATE,"
        "ZohoCRM.modules.tasks.CREATE,ZohoCRM.users.READ"
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def use_async_postgres_driver(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()