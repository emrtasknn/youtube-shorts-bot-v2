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
    pexels_enabled: bool = False
    pexels_api_key: str = ""
    pexels_base_url: str = "https://api.pexels.com"
    pexels_timeout_seconds: float = 30.0
    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_seconds: float = 60.0
    fish_audio_enabled: bool = False
    fish_audio_api_key: str = ""
    fish_audio_base_url: str = "https://api.fish.audio"
    fish_audio_model: str = "s2.1-pro-free"
    fish_audio_format: str = "mp3"
    fish_audio_reference_id: str = ""
    fish_audio_timeout_seconds: float = 120.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
