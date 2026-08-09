from bot.services.formatting import label, name_label, safe_filename


def test_name_label_combines_name_and_ticker():
    assert name_label("2408", "南亞科") == "南亞科(2408)"
    assert name_label("NVDA", "NVIDIA") == "NVIDIA(NVDA)"


def test_falls_back_to_ticker_when_name_unknown():
    """名稱查不到就只寫代號——報告曾把 2408 寫成聯電，就是因為有人替它猜。"""
    assert name_label("2408", "") == "2408"
    assert name_label("2408", None or "") == "2408"
    assert name_label("2408", "2408") == "2408"


def test_label_reads_name_from_quote_dict():
    assert label("2330", {"name": "台積電"}) == "台積電(2330)"
    assert label("2330", {}) == "2330"
    assert label("2330", "not a dict") == "2330"


def test_safe_filename_strips_path_separators():
    assert "/" not in safe_filename("a/b")
    assert "\\" not in safe_filename("a\\b")
    assert safe_filename("台積電 公司") == "台積電_公司"


def test_safe_filename_keeps_cjk():
    assert safe_filename("南亞科(2408)") == "南亞科(2408)"
