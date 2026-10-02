from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_name: str = "youtube-shorts-bot-v2"
    environment: str = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://shorts:shorts@localhost:5432/shorts"
    telegram_bot_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
