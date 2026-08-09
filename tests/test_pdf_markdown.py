from bot.services.pdf import font_status, generate_pdf


def test_numbered_list_keeps_its_number():
    """以前 '1. ' 被整段丟掉，讀者看到的是一串沒有次序的段落。

    直接比對兩份 PDF：有編號的那份一定跟沒編號的不同，
    表示編號真的有被畫進去。
    """
    with_number = generate_pdf("X", "t", "1. 資料中心營收占比")
    without = generate_pdf("X", "t", "資料中心營收占比")
    assert with_number != without


def test_renders_full_markdown_without_crashing():
    md = (
        "## 一、本季數字\n\n"
        "| 項目 | 本季 |\n|---|---|\n| 營收 | 81.6 billion |\n\n"
        "1. 第一點\n2. 第二點\n"
        "- 項目符號\n"
        "> 引述\n"
        "**整段粗體**\n"
        "---\n"
        "```\ncode\n```\n"
    )
    assert generate_pdf("NVDA", "財報解讀", md).startswith(b"%PDF")


def test_escapes_xml_special_chars():
    """未跳脫的 < & 會讓 ReportLab 解析失敗，整份報告生不出來。"""
    assert generate_pdf("X", "t", "毛利率 < 40% & 營益率 > 20%").startswith(b"%PDF")


def test_font_is_available():
    """缺字型時 PDF 照樣產出，只是中文全空白——所以要顯式檢查。"""
    ok, detail = font_status()
    assert ok, detail
