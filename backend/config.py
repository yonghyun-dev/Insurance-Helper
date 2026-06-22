from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    lg_api_key: str | None = None
    lg_endpoint_id: str | None = None
    lg_chat_completions_url: str | None = None

    upstage_api_key: str | None = None
    upstage_base_url: str | None = None
    upstage_model: str | None = None


settings = Settings()


def require_env(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} must be configured in .env.")
    return value
