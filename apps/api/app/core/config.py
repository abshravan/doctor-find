"""Centralized, typed application settings (12-factor via env)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_env: str = "local"
    app_name: str = "DoctorFind"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Infra
    database_url: str = "postgresql+asyncpg://doctorfind:doctorfind@localhost:5432/doctorfind"
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Feature flags
    enable_ai_triage: bool = True
    enable_voice: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
