# 7 Wall Street analyst prompts. Each accepts {ticker} via .format().

_FORMAT_RULES = """
輸出規則（必須嚴格遵守）：
1. 使用以下固定章節標題，格式為「## 一、xxx」，不可更改章節名稱或順序
2. 使用 Markdown 表格（| 欄 | 欄 |）呈現比較數據
3. 使用 **粗體** 標示重要數字或關鍵詞
4. 使用 - 或 • 開頭的列點
5. 不要使用 emoji
6. 不要使用程式碼區塊（```），改用縮排或列點表示
"""

_FIXED_SECTIONS = """
章節格式（依序輸出，不可省略）：
## 一、公司概況與商業模式
## 二、競爭優勢（護城河分析）
## 三、產業趨勢分析
## 四、財務健康狀況
## 五、關鍵風險評估
## 六、估值比較分析
## 七、情境分析
## 八、未來 12-24 個月展望
## 九、投資結論與建議
"""

PROMPTS: dict[str, str] = {
    "full": """以華爾街資深股票分析師的角度，對股票 {ticker} 進行完整深度分析。
{format_rules}
{fixed_sections}
每個章節請包含：具體數據、與同業比較、以及對投資人的實際意義。
最後的「九、投資結論與建議」必須包含：評級（買入/持有/賣出）、目標股價、主要風險提示。""",

    "financial": """以華爾街財務分析師角色，分析 {ticker} 的財務健康狀況。
{format_rules}
{fixed_sections}
重點分析：
- 一、說明公司主要收入來源
- 四、深入拆解過去5年營收成長、淨利趨勢、自由現金流、利潤率、負債水準、ROE
- 九、判斷財務體質是變強還是走弱，給出結論""",

    "moat": """以華爾街分析師角色，評估 {ticker} 的競爭護城河。
{format_rules}
{fixed_sections}
重點分析：
- 二、深入評估品牌影響力、網路效應、轉換成本、成本優勢、專利技術，並打分（1-10分）
- 六、與主要競爭對手比較護城河強度""",

    "valuation": """以投資銀行分析師角色，對 {ticker} 進行估值分析。
{format_rules}
{fixed_sections}
重點分析：
- 六、包含P/E與同業比較、DCF估值、產業平均估值水準
- 九、明確結論：被低估或高估，合理價格區間""",

    "growth": """以成長股分析師角色，分析 {ticker} 的成長潛力。
{format_rules}
{fixed_sections}
重點分析：
- 三、產業規模、成長率、擴張機會
- 八、未來5-10年潛在成長空間""",

    "debate": """以兩位分析師對話方式，針對 {ticker} 進行多空辯論。
{format_rules}
{fixed_sections}
- 七、用「多頭觀點」vs「空頭觀點」呈現辯論，雙方需有數據支持
- 九、給出相對中性的最終結論""",

    "recommendation": """以資深投資顧問角色，評估是否應該投資 {ticker}。
{format_rules}
{fixed_sections}
- 八、分短期（1年內）和長期（5年以上）展望
- 九、明確給出：買入、持有或避免，以及關鍵催化因素與主要風險""",
}

# Pre-format the prompts with the fixed rules
for _key in PROMPTS:
    PROMPTS[_key] = PROMPTS[_key].format(
        ticker="{ticker}",
        format_rules=_FORMAT_RULES,
        fixed_sections=_FIXED_SECTIONS,
    )

ANALYSIS_BUTTONS = [
    ("完整分析", "full"),
    ("財務健康", "financial"),
    ("競爭護城河", "moat"),
    ("估值分析", "valuation"),
    ("成長潛力", "growth"),
    ("多空辯論", "debate"),
    ("投資建議", "recommendation"),
]
