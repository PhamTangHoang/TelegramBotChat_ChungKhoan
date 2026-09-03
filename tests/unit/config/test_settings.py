from app.config.settings import Settings


def test_settings_parse_watchlist_and_allowed_chat_ids() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        watchlist_symbols=" fpt, VNM ",
        watchlist_exchanges="HOSE,HOSE",
        telegram_allowed_chat_ids="123, -456",
    )

    assert settings.watchlist_symbols == ("FPT", "VNM")
    assert settings.watchlist_exchanges == ("HOSE", "HOSE")
    assert settings.telegram_allowed_chat_ids == (123, -456)


def test_settings_accepts_missing_live_credentials_for_local_development() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:")

    assert settings.gemini_api_key is None
    assert settings.telegram_bot_token is None


def test_settings_normalizes_blank_live_credentials() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        gemini_api_key=" ",
        telegram_bot_token="",
    )

    assert settings.gemini_api_key is None
    assert settings.telegram_bot_token is None
