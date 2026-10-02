from app.config.settings import get_settings


def test_settings_load() -> None:
    settings = get_settings()
    assert settings.app_name == "youtube-shorts-bot-v2"
    assert settings.database_url.startswith("postgresql+psycopg://")
