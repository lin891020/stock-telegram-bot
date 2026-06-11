import pytest

import bot.services.alerts as alerts
from bot.services.alerts import parse_condition, describe_condition, condition_text, is_triggered


@pytest.fixture(autouse=True)
def tmp_alerts_file(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "_FILE", tmp_path / "alerts.json")


def test_parse_price_conditions():
    assert parse_condition(">1100") == {"kind": "price", "op": ">", "value": 1100.0}
    assert parse_condition("< 950.5") == {"kind": "price", "op": "<", "value": 950.5}


def test_parse_pct_conditions():
    assert parse_condition("+5%") == {"kind": "pct", "op": "+", "value": 5.0}
    assert parse_condition("-3.5 %") == {"kind": "pct", "op": "-", "value": 3.5}


def test_parse_invalid_conditions():
    assert parse_condition("1100") is None
    assert parse_condition(">abc") is None
    assert parse_condition("+5") is None
    assert parse_condition("") is None


def test_price_trigger():
    above = parse_condition(">1100")
    below = parse_condition("<950")
    assert is_triggered(above, 1101.0, None) is True
    assert is_triggered(above, 1100.0, None) is False
    assert is_triggered(below, 949.0, None) is True
    assert is_triggered(below, 950.0, None) is False


def test_pct_trigger():
    up = parse_condition("+5%")
    down = parse_condition("-5%")
    assert is_triggered(up, 105.0, 100.0) is True
    assert is_triggered(up, 104.0, 100.0) is False
    assert is_triggered(down, 95.0, 100.0) is True
    assert is_triggered(down, 96.0, 100.0) is False
    # 漲跌幅條件沒有前收盤價時不觸發
    assert is_triggered(up, 105.0, None) is False


def test_describe_condition():
    assert "漲破" in describe_condition(parse_condition(">1100"))
    assert "跌破" in describe_condition(parse_condition("<950"))
    assert "漲幅" in describe_condition(parse_condition("+5%"))
    assert "跌幅" in describe_condition(parse_condition("-5%"))


def test_condition_text_roundtrip():
    # 「再設一次」按鈕靠 condition_text 還原條件，必須可被 parse_condition 解析回原值
    for raw in (">1100", "<950.5", "+5%", "-3.5%"):
        cond = parse_condition(raw)
        assert parse_condition(condition_text(cond)) == cond


def test_add_get_remove_alert():
    cond = parse_condition(">1100")
    alert = alerts.add_alert(123, "2330", cond)
    assert alert["ticker"] == "2330"
    assert alerts.get_alerts(123) == [alert]

    assert alerts.remove_alert(123, alert["id"]) is True
    assert alerts.get_alerts(123) == []
    assert alerts.remove_alert(123, alert["id"]) is False
