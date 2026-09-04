from app.config.settings import Settings


def test_settings_parse_watchlist_and_allowed_chat_ids() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        _env_file=None,
        watchlist_symbols=" fpt, VNM ",
        watchlist_exchanges="HOSE,HOSE",
        telegram_allowed_chat_ids="123, -456",
    )

    assert settings.watchlist_symbols == ("FPT", "VNM")
    assert settings.watchlist_exchanges == ("HOSE", "HOSE")
    assert settings.telegram_allowed_chat_ids == (123, -456)


def test_settings_accepts_missing_live_credentials_for_local_development(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", _env_file=None)

    assert settings.gemini_api_key is None
    assert settings.telegram_bot_token is None


def test_settings_normalizes_blank_live_credentials() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        _env_file=None,
        gemini_api_key=" ",
        telegram_bot_token="",
    )

    assert settings.gemini_api_key is None
    assert settings.telegram_bot_token is None


def test_settings_supports_public_telegram_access() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        _env_file=None,
        telegram_public_access=True,
    )

    assert settings.telegram_public_access is True


def test_settings_exposes_pp10_version() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", _env_file=None)

    assert settings.pp10_version == "2.0.0"


def test_settings_defaults_to_supported_low_latency_gemini_model() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", _env_file=None)

    assert settings.gemini_model == "gemini-3.1-flash-lite"
    assert settings.gemini_timeout_seconds == 20.0


def test_settings_parse_openrouter_debate_configuration() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        _env_file=None,
        llm_provider="openrouter",
        openrouter_api_key="test-key",
        openrouter_analyst_models="technical:free, pattern:free, risk:free",
        openrouter_judge_model="judge:free",
        openrouter_fallback_models="fallback-a:free, fallback-b:free",
        openrouter_max_parallel=2,
    )

    assert settings.llm_provider == "openrouter"
    assert settings.openrouter_analyst_models == (
        "technical:free",
        "pattern:free",
        "risk:free",
    )
    assert settings.openrouter_judge_model == "judge:free"
    assert settings.openrouter_fallback_models == ("fallback-a:free", "fallback-b:free")
    assert settings.openrouter_max_parallel == 2
