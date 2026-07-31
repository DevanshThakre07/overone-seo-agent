from app.config.settings import Settings, get_settings


def test_settings_load_from_yaml():
    settings = Settings.from_yaml()
    assert settings.crawl.max_pages > 0
    assert settings.analyzer.page_size_threshold_bytes > 0


def test_get_settings_cached():
    a = get_settings()
    b = get_settings()
    assert a is b
