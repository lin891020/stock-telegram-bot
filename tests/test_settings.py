import pytest

import bot.services.settings as settings


@pytest.fixture(autouse=True)
def tmp_settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_FILE", tmp_path / "settings.json")


def test_parse_hhmm_valid():
    assert settings.parse_hhmm("08:00") == (8, 0)
    assert settings.parse_hhmm("8:05") == (8, 5)
    assert settings.parse_hhmm("23:59") == (23, 59)
    assert settings.parse_hhmm(" 07:30 ") == (7, 30)


def test_parse_hhmm_invalid():
    assert settings.parse_hhmm("24:00") is None
    assert settings.parse_hhmm("08:60") is None
    assert settings.parse_hhmm("0800") is None
    assert settings.parse_hhmm("abc") is None
    assert settings.parse_hhmm("") is None


def test_get_news_time_default():
    assert settings.get_news_time() == settings.DEFAULT_NEWS_TIME


def test_set_and_get_news_time():
    assert settings.set_news_time("7:30") == "07:30"
    assert settings.get_news_time() == "07:30"


def test_set_news_time_invalid_raises():
    with pytest.raises(ValueError):
        settings.set_news_time("25:00")


def test_closing_time_defaults():
    assert settings.get_time("tw_close") == "14:00"
    assert settings.get_news_time() == "06:30"


def test_set_closing_times():
    assert settings.set_time("tw_close", "14:30") == "14:30"
    assert settings.get_time("tw_close") == "14:30"
    # 改台股收盤時間不影響其他設定
    assert settings.get_news_time() == settings.DEFAULT_NEWS_TIME


def test_model_persistence():
    assert settings.get_saved_model() is None
    settings.save_model("claude-sonnet-4-6")
    assert settings.get_saved_model() == "claude-sonnet-4-6"
