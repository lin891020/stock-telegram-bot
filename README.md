# 📈 Stock Assistant

> 個人專屬的 AI 股票分析 Telegram 機器人，支援台股與美股深度分析、財報速覽、投資學習、個人財務教練。

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-20.7-2CA5E0?logo=telegram&logoColor=white)
![Claude](https://img.shields.io/badge/AI-Claude%20Sonnet-8B5CF6?logo=anthropic&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 功能一覽

| 指令 | 功能 |
|------|------|
| 直接傳「2330」「台積電」「NVDA」 | 報價卡片＋操作按鈕（分析/K線/財報/提醒/加自選），不用打指令 |
| `/analyze <代號>` | 深度股票分析：先回 5 行速覽，完整報告出 PDF（7 種類型） |
| `/earnings <代號>` | 最近 4 季 EPS 實際 vs 預估、beat/miss 趨勢 |
| `/chart <代號> [期間]` | 日 K 線圖（成交量 + MA20/60，期間 1m/3m/6m/1y） |
| `/market` | 大盤速覽（加權、S&P 500、NASDAQ、道瓊、費半、台幣） |
| `/watch <代號>` | 加入自選股 |
| `/unwatch <代號>` | 移除自選股 |
| `/watchlist` | 查看自選股清單 |
| `/alert <代號> <條件>` | 到價提醒：`>1100`、`<950`、`+5%`、`-5%`（盤中每 10 分鐘檢查，觸發即移除） |
| `/news` | 抓取自選股最新新聞 |
| `/settime [tw] <HH:MM>` | 設定起床報（預設 06:30，含隔夜美股收盤）／台股收盤速報時間 |
| `/learn <主題>` | 投資觀念教學（ETF、複利、資產配置…） |
| `/finance` | 個人財務教練（5 階段對話，生成客製化理財建議） |
| `/model` | 切換 AI 模型（Claude / Gemini / GPT） |
| `/help` | 使用說明 |

---

## /analyze 報告類型

輸入 `/analyze TSLA` 後，選擇以下其中一種分析：

- **完整分析** — 綜合所有面向的完整報告
- **財務健康** — 資產負債、現金流、獲利能力
- **競爭護城河** — 品牌、技術壁壘、市場地位
- **估值分析** — P/E、P/S、DCF 合理價位
- **成長潛力** — 市場空間、產品路線、催化劑
- **多空辯論** — 看多 vs 看空觀點對比
- **投資建議** — 買入 / 持有 / 賣出與理由

報告以 **PDF** 格式發送，支援繁體中文排版。

---

## 快速開始

### 1. 取得 Bot Token

前往 Telegram 搜尋 `@BotFather`，執行 `/newbot` 建立機器人，取得 Token。

### 2. 取得你的 Telegram ID

搜尋 `@userinfobot`，它會回覆你的 User ID。

### 3. 安裝依賴

```bash
git clone https://github.com/lin891020/stock-telegram-bot.git
cd stock-telegram-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python scripts/download_font.py  # 下載中文字型（約 11MB）
```

### 4. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`：

```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
ALLOWED_TELEGRAM_ID=your_telegram_user_id
ANTHROPIC_API_KEY=your_anthropic_api_key
LLM_PROVIDER=anthropic
```

### 5. 啟動

```bash
python main.py
```

---

## 環境變數說明

| 變數 | 必填 | 說明 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | ✅ | BotFather 提供的機器人 Token |
| `ALLOWED_TELEGRAM_ID` | ✅ | 允許使用的 Telegram User ID |
| `LLM_PROVIDER` | — | `anthropic`（預設）/ `gemini` / `github` |
| `ANTHROPIC_API_KEY` | — | [Anthropic Console](https://console.anthropic.com) 取得 |
| `GEMINI_API_KEY` | — | [Google AI Studio](https://aistudio.google.com) 取得（免費） |
| `OPENAI_API_KEY` | — | GitHub Models token（免費） |
| `GITHUB_TOKEN` | — | `/finance` 個人資料儲存用（可選） |
| `GITHUB_REPO` | — | 儲存用戶資料的 Repo，格式：`user/repo` |

---

## AI 模型

使用 `/model` 指令切換，或設定 `LLM_PROVIDER`：

| 模型 | 提供者 | 費用 | 說明 |
|------|--------|------|------|
| `claude-sonnet-4-6` | Anthropic | 付費 | 深度分析（預設） |
| `claude-opus-4-8` | Anthropic | 付費 | 最強推理 |
| `gemini-3.5-flash` | Google | 免費 | 快速輕量 |
| `gemini-3.1-pro-preview` | Google | 免費（限額） | 深度推理 |
| `gpt-4o-mini` | GitHub Models | 免費 | 穩定備援 |

每日晨報的新聞摘要為低難度任務：使用 Anthropic 時自動改用 Haiku 以節省成本，免費模型則照常使用。

---

## 資料來源

| 來源 | 用途 |
|------|------|
| [yfinance](https://github.com/ranaroussi/yfinance) | 美股報價、財報、新聞 |
| [TWSE API](https://www.twse.com.tw) | 台股即時報價 |
| [FinMind](https://finmindtrade.com) | 台股財務報表 |

---

## 部署

### Render.com（推薦）

1. Fork 此 repo
2. 至 [Render.com](https://render.com) 建立 **Background Worker**
3. Build Command：`pip install -r requirements.txt && python scripts/download_font.py`
4. Start Command：`python main.py`
5. 填入所有必要環境變數

### Oracle Cloud Free Tier

```bash
git clone https://github.com/lin891020/stock-telegram-bot.git
cd stock-telegram-bot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scripts/download_font.py

# 設定為系統服務（開機自啟）
sudo cp scripts/stock-bot.service /etc/systemd/system/
sudo systemctl enable stock-bot && sudo systemctl start stock-bot
```

---

## 開發

```bash
# 執行測試
pytest tests/ -v

# 查看 log（VM 上）
sudo journalctl -u stock-bot -f
```

---

## 專案結構

```
stock-telegram-bot/
├── bot/
│   ├── handlers/       # Telegram 指令處理器
│   ├── services/       # 外部 API 整合（股票、LLM、PDF）
│   ├── prompts/        # 分析師 Prompt 模板
│   └── content/        # 預寫投資教學內容
├── scripts/
│   ├── download_font.py        # 下載中文字型
│   └── stock-bot.service       # systemd 服務設定
├── tests/
├── main.py
└── .env.example
```

---

## License

MIT
