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
| `/earnings <代號>` | 財報速覽：本季營收/獲利/管理層說法/官方財測＋近幾季 beat/miss，可按鈕出完整 PDF |
| `/chart <代號> [期間]` | 日 K 線圖（成交量 + MA20/60，期間 1m/3m/6m/1y） |
| `/market` | 大盤速覽（加權、S&P 500、NASDAQ、道瓊、費半、台幣） |
| `/watch <代號>` | 加入自選股 |
| `/unwatch <代號>` | 移除自選股 |
| `/watchlist` | 查看自選股清單 |
| `/alert <代號> <條件>` | 到價提醒：`>1100`、`<950`、`+5%`、`-5%`（盤中每 10 分鐘檢查，觸發即移除） |
| `/news` | 抓取自選股最新新聞 |
| `/settime [tw] <HH:MM>` | 設定起床報（預設 06:30，含隔夜美股收盤）／台股收盤速報時間（見下方「自動推播」） |
| `/learn <主題>` | 投資觀念教學（ETF、複利、資產配置…） |
| `/finance` | 個人財務教練（5 階段對話，生成客製化理財建議） |
| `/model` | 切換 AI 模型（Claude / Gemini / GPT） |
| `/health` | 檢查各資料源是否正常（yfinance / TWSE / FinMind / SEC） |
| `/help` | 使用說明 |

指令不帶參數時 bot 會直接開口追問（例如 `/watch` → 「輸入要加入追蹤的代號或名稱：」），下一則訊息就是參數，不會鎖住輸入框。

---

## 自動推播

加入自選股後不用另外設定，以下都會自動送到 Telegram：

| 時機 | 內容 |
|------|------|
| 每天 06:30（台北，週末不推） | 起床報：大盤（含隔夜美股收盤）＋今日財報日提醒＋自選股新聞摘要 |
| 每天 14:00 | 台股收盤速報（遇休市自動略過） |
| 盤中每 10 分鐘 | **自選台股漲停／跌停**、**自選美股單日漲跌超過 10%**（同一天同方向只推一次） |
| 盤中每 10 分鐘 | `/alert` 設定的到價提醒（觸發後自動移除） |
| 每小時 | **所有自選股**的財報公布偵測：公布後自動推一份 5 行速覽，附 `📄 完整報告` 按鈕 |

漲跌停判定是照台股檔位算出實際限價（例如前收 1090 → 漲停 1195，只有 +9.63%），不是用「漲超過 9.5%」近似。

財報偵測不需事前登記；新加入的股票第一次掃到時只記基準、不會把舊財報推一遍。
訊號以 **SEC EDGAR 官方申報為主**（8-K Item 2.02／外國發行人 6-K），yfinance 的 EPS 更新為輔——
EDGAR 是第一手、公司送件當下就有，而且觸發的同時就把報告要用的新聞稿原文一起抓下來了。
完整報告不自動生成：財報季擠在兩三週內，每份都跑主力模型太貴，想看深的再按按鈕。

---

## /analyze 報告類型

輸入 `/analyze TSLA` 後，選擇以下其中一種分析：

- **完整分析** — 綜合所有面向的完整報告
- **財務健康** — 資產負債、現金流、獲利能力
- **競爭護城河** — 品牌、技術壁壘、市場地位
- **估值分析** — P/E、P/S、DCF 合理價位
- **成長潛力** — 市場空間、產品路線、催化劑
- **多空辯論** — 看多 vs 看空觀點對比
- **判斷條件** — 在什麼條件成立時該買／該賣，以及怎麼驗證

報告以 **PDF** 格式發送，支援繁體中文排版。

`/analyze` 的定位是**分析框架示範**，不是投資建議：它示範專業分析師會看哪些面向、
用什麼標準判斷，並列出「要成立需要哪些條件」讓你自己去驗證，不會替你下結論或給評分。
真正拿來做決策的是 `/earnings` ——那份的原料是公司自己寫的財報新聞稿，
幾乎每一句都能溯源到原文。

---

## 資料紀律

原則是一句話：**寧可說查不到，不可用舊資料假裝現況。**

報告不是把股票代號丟給模型讓它自由發揮。程式會先把能查到的數字組成一份「證據包」，
每個數字都帶三樣東西：**期間**（TTM？最近一季？最新一期資產負債表？）、
**定義**（`totalDebt` 是有息負債，不是總負債）、**來源**。
查不到的項目由程式列成明確的缺漏清單，強制寫進報告最後一節，不准模型自行增減。

還有幾道程式端的檢查，攔的是實際踩過的坑：

| 檢查 | 攔到的問題 |
|------|-----------|
| 會計恆等式 | 營益率不可能大於毛利率——出現就把三個利潤率全部丟掉，不進報告 |
| 幣別一致性 | 報價是 USD、財報是 KRW 時不得混寫或相比 |
| 流量 vs 存量 | 年度營收要同年各季加總，總資產只能取最新一期；季數不足會標「僅 N 季合計，非全年」 |
| 財季標示 | 只標公布日，不猜財季代號——財年結束月各家不同，NVDA 五月公布的是 FY2027 Q1 |

資料全缺時，錯誤訊息會明講「嚴禁使用你訓練資料中的財務數字」，
而不是「以下分析基於模型訓練資料」——後者等於發許可證讓它編。

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
| `SEC_USER_AGENT` | — | SEC 要求的聯絡方式，格式：`專案名 you@example.com`。不設會用預設值，但 SEC 可能限流 |

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
| [yfinance](https://github.com/ranaroussi/yfinance) | 美股報價、財報、新聞、分析師預估 |
| [SEC EDGAR](https://www.sec.gov/edgar) | 美股財報新聞稿原文（管理層說法、官方財測）與公布偵測 |
| [TWSE API](https://www.twse.com.tw) | 台股即時報價 |
| [FinMind](https://finmindtrade.com) | 台股財務報表 |

台股沒有等同 EDGAR 的結構化來源，法說會內容目前抓不到——報告會直接寫明缺這一段，
不會拿別的東西充數。

---

## 部署

### Oracle Cloud Free Tier（本專案實際使用）

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

> ⚠️ **VM 上沒有自動部署。** push 到 GitHub 不等於上線，要自己 ssh 上去：
>
> ```bash
> cd stock-telegram-bot && git pull --ff-only
> venv/bin/pip install -r requirements.txt   # requirements 有變才需要
> sudo systemctl restart stock-bot
> ```
>
> 忘記這步會出現「程式明明改好了，行為卻沒變」——實際發生過，兩個月的 commit 都沒上線。
> 用 `/health` 或 `git log --oneline -1` 確認 VM 上跑的是哪個版本。
>
> `data/` 是 gitignored 的（自選股、提醒、財報基準都在裡面），`git pull` 不會動到它。

### Render.com

1. Fork 此 repo
2. 至 [Render.com](https://render.com) 建立 **Background Worker**
3. Build Command：`pip install -r requirements.txt && python scripts/download_font.py`
4. Start Command：`python main.py`
5. 填入所有必要環境變數

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
├── data/               # 自選股、提醒、財報基準（gitignored，不進版控）
├── tests/
├── main.py
└── .env.example
```

---

## License

MIT
