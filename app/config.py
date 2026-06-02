from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://waymark:waymark@127.0.0.1:5432/waymark"
    firebase_project_id: str | None = None
    api_cors_origins: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_cors_origins(settings: Settings) -> list[str]:
    return [
        origin.strip()
        for origin in settings.api_cors_origins.split(",")
        if origin.strip()
    ]
