# 📈 Stock Assistant

> 個人專屬的 AI 股票分析 Telegram 機器人，支援台股與美股深度分析、財報速覽、投資學習、個人財務教練。

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-22.8-2CA5E0?logo=telegram&logoColor=white)
![Claude](https://img.shields.io/badge/AI-Claude%20Sonnet%205-8B5CF6?logo=anthropic&logoColor=white)
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
| `/cancel` | 取消目前等待中的操作 |
| `/health` | 七項健康檢查：yfinance / TWSE / SEC EDGAR / FinMind / lxml / PDF 字型 / AI 模型 |
| `/help` | 使用說明 |

指令不帶參數時 bot 會直接開口追問（例如 `/watch` → 「輸入要加入追蹤的代號或名稱：」），下一則訊息就是參數，不會鎖住輸入框。

---

## 自動推播

加入自選股後不用另外設定，以下都會自動送到 Telegram：

| 時機 | 內容 |
|------|------|
| 每天 06:30（台北，週末不推） | 起床報：大盤（含隔夜美股收盤）＋今日財報日提醒＋自選股新聞標題 |
| 每天 14:00 | 台股收盤速報（遇休市自動略過） |
| 盤中每 10 分鐘 | **自選台股漲停／跌停**、**自選美股單日漲跌超過 10%**（同一天同方向只推一次） |
| 盤中每 10 分鐘 | `/alert` 設定的到價提醒（觸發後自動移除） |
| 每小時 | **所有自選股**的財報公布偵測：公布後自動推一份 5 行速覽，附 `📄 完整報告` 按鈕 |
| 每天 06:00 | **系統巡檢**：七項檢查有紅燈才推播，全綠時安靜 |

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

報告以 **PDF** 格式發送，封面與檔名都帶公司名稱（`南亞科(2408) — 財報解讀`）。
名稱查不到時只寫代號，不猜——報告曾把 2408 寫成聯電，就是因為有人替它補了一個看似合理的答案。

⚠️ 繁體中文排版需要 `scripts/download_font.py` 下載的字型（約 11MB，不在版控內）。
少了它 PDF 仍會正常產出、正常送達，只是中文全部空白——所以 `/health` 會明確檢查這一項。

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

### 三層防線

證據包只解決了三件事裡的一件。實際踩過之後補上另外兩層：

| 層 | 擋什麼 | 怎麼做 |
|---|---|---|
| **證據包** | 模型憑空編數字 | 每個數字帶期間／定義／來源；缺的由程式列清單，不准模型增減 |
| **資料層檢查** | **我們自己餵錯數字** | 五項純程式規則，見下 |
| **產出後稽核** | 模型算錯或寫出查不到出處的數字 | 把報告裡的具名比率用結構化財報**重算一次** |

中間那層是後來才發現非補不可的。證據包擋得住模型亂編，卻擋不住我們自己
把錯的數字餵進去——那種錯對模型是**隱形的**，它只會忠實地引用一個假數字。

實際案例：FinMind 的損益表是單季數（要加總）、現金流量表是年初至今累計數
（不能加總），同一個 API 兩種語意且沒有欄位標明。程式對兩者都加總，台積電
2024 營業現金流被算成 4.28 兆，真實是 1.83 兆——**虛報 2.3 倍，而且每份台股
分析都吃到這個數字**。三層裡只有資料層檢查抓得到它：

```
營業現金流 4.28兆 > 全年營收 2.89兆 → 製造業不可能
```

`bot/services/consistency.py` 的六項規則：營業現金流不得大於營收、
營收 ≥ 毛利 ≥ 營業利益、稅後淨利 = 稅前淨利 − 所得稅、資產 = 負債 + 權益、
資本支出應為負數、兩個來源差三倍以上即量級錯誤。原則跟證據包一致：
**只標記，不猜哪個對**。

> 「營業利益 ≥ 淨利」曾經也在這張表上，但它**不是**恆等式——業外收入大於
> 所得稅時淨利本來就會超過營業利益（實測聯發科 2025 完全正確卻被判紅燈）。
> 它對九支自選股誤報了兩支。會亂叫的檢查只會訓練人忽略它，所以拿掉了。

`bot/services/claim_audit.py` 有兩層，偵測力差很多：

| | 問法 | 實測 |
|---|---|---|
| `audit_numbers` | 「這個數字推不推導得出來」 | **幾乎沒有偵測力**。46 個證據數字兩兩排列產生 4,428 個推導值，把 0–100 這段數線鋪滿；把真數字擾動 5–50%（幻覺的典型樣貌）後仍有 94% 被判為「算得出來」，一份 4,830 字元的真實報告標記 0 個 |
| `verify_ratios` | 「報告說毛利率 56.1%，那用本次資料算出來是多少」 | 點對點比對，候選只有幾個期間。三份真實報告 22 個具名比率宣稱、**0 個誤報**；編造值會被抓出來 |

差別在提問方式：候選集夠大時，「有沒有可能算出來」的答案永遠是「有」。
公司財測的比率（「預期下季毛利率 74.0%」）本來就算不出來，會自動豁免。
兩層都只標記、不改寫報告——改寫要用模型驗模型，會引入新的錯誤。

### 靜默失敗是這個專案的主要敵人

會大聲壞掉的東西不可怕，可怕的是照常運作、只是答案是錯的。實際踩過的三種：

- **缺套件** — yfinance 少了 `lxml` 就抓不到任何財報日，不報錯，靜靜死了兩個月
- **缺字型** — PDF 照樣產出、照樣送達，打開來中文全是空白
- **用錯欄位名** — FinMind 拿錯型別名稱只會回空陣列，不報錯。同一個坑踩了三次：
  `NetIncome`（正確是 `IncomeAfterTaxes`，台股年度淨利一直缺）、
  `PropertyAndPlantAndEquipment`（資本支出）、
  `TotalLiabilities` / `StockholdersEquity`（正確是 `Liabilities` / `Equity`——
  那是 yfinance 的講法，用在台股上讓總負債與股東權益整組是空的，
  負債比與 ROE 全部算不出來，而「資產 = 負債 + 權益」這條檢查因為永遠
  拿不到資料，對台股形同不存在）

第三次之後不再靠人發現：`FINMIND_TYPES` 把依賴的 14 個科目名稱列成一張表，
`/health` 拿它去對 FinMind 真正回傳的科目，對方改名就亮紅燈；
另外任何年度科目變空都會寫進 log。

所以 `/health` 檢查的不只是「網路通不通」，而是每一條真正會靜默斷掉的線，
而且**每天早上 06:00 自動跑一次**——有紅燈才推播，全綠時安靜。
只靠「想到才去打 /health」是沒用的，沒人會沒事去打它。

另外掛了 PTB 的全域 error handler：任何 handler 沒接住的例外都會回一則訊息給你，
而不是讓「訊息就是沒來」跟「bot 掛了」長得一模一樣。

狀態檔（自選股、提醒、財報基準）走 `bot/services/store.py` 的原子寫入：
先寫暫存檔、`fsync`、再 `os.replace`。以前是「先清空再寫」，
中途斷電就留下半截檔案——而自選股幾乎每個指令都要讀，壞了等於整隻 bot 不能用。

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
| `FINMIND_TOKEN` | — | [FinMind](https://finmindtrade.com) 台股財報，免費註冊可提高額度 |
| `SEC_USER_AGENT` | — | SEC 要求的聯絡方式，格式：`專案名 you@example.com`。不設會用預設值，但 SEC 可能限流 |

---

## AI 模型

使用 `/model` 指令切換，或設定 `LLM_PROVIDER`：

| 模型 | 提供者 | 每百萬 token | 說明 |
|------|--------|------|------|
| `claude-sonnet-5` | Anthropic | $2 / $10 | 深度分析（預設） |
| `claude-opus-5` | Anthropic | $5 / $25 | 最強推理 |
| `claude-haiku-4-5` | Anthropic | $1 / $5 | 最便宜最快 |
| `gemini-3.5-flash` | Google | 免費 | 快速輕量 |
| `gemini-3.1-pro-preview` | Google | 免費（限額） | 深度推理 |
| `gpt-4o-mini` | GitHub Models | 免費 | 穩定備援 |

`/model` 選的是**分析與財報報告**用的模型。`/finance` 與 `/learn` 固定用 Haiku 省成本；
晨報則完全不經過模型（只列新聞標題），兩者都不受這裡影響。

模型代號用官方完整字串，不要自己加日期後綴（`claude-haiku-4-5`，
不是 `claude-haiku-4-5-20251001`）——加了會變成無效代號。

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
# 單元測試（233 項，全部 mock，不打網路）
pytest tests/ -v

# 端對端煙霧測試（真實資料源，--paid 才呼叫 LLM）
venv/bin/python scripts/smoke_test.py

# 情境考卷：強制觸發平常要等事件才會走到的路徑，再讓六個角色走一遍
venv/bin/python scripts/exam.py --paid

# 查看 log（VM 上）
sudo journalctl -u stock-bot -f
```

測試偏重「算錯了會靜靜產出錯誤答案」的地方：漲跌停檔位、年度數字加總、
財季標示、證據包缺漏、財報偵測基準、狀態檔原子寫入、FinMind 科目名稱。
外部 API 一律 mock，跑測試不會真的打網路。

`scripts/exam.py` 補的是另一半：**要等事件發生才考得到的路徑**。它用假造的
觸發條件把它們逼出來——財報公布推播（含推播失敗不吃掉那一季）、資料層巡檢
亮紅燈（注入錯誤資料）、報告自動稽核、AI 模型掛掉時使用者看到什麼——再讓
六個角色（新手／手機族／當沖／會計背景／亂打的人／每天看晨報的人）走真實
handler。兩個真實 bug 是它找出來的：FinMind 的總負債與股東權益一直是空的，
以及產出後稽核幾乎沒有偵測力。

---

## 我要改 X，去哪裡改

| 想改的東西 | 去哪裡 |
|---|---|
| **報價怎麼顯示**（「收 2,420.00 元（8/28 收盤）」） | `services/formatting.py` — 全部指令共用這一份 |
| **「名稱(代號)」的寫法** | `services/formatting.py` 的 `name_label`。曾經散在七處且**內容不一致**，別再自己寫一份 |
| **晨報／收盤速報的內容** | `handlers/digest.py` |
| **晨報／收盤速報的時間** | `handlers/schedule.py` 的 `_JOBS`，加一筆就多一個排程 |
| **時區、週末判斷** | `services/clock.py` — 整個專案唯一換算時區的地方 |
| **自選股增刪查** | `handlers/watch.py` |
| **股票卡片上的按鈕** | `handlers/card.py` 的 `_card_keyboard` |
| **分析報告的章節與語氣** | `prompts/analysis.py`（`/analyze`）、`prompts/earnings_report.py`（財報） |
| **餵給模型的資料有哪些** | `services/evidence.py` — 事實、缺漏、註記都在這裡組 |
| **資料對不對的檢查規則** | `services/consistency.py` |
| **報告產出後的稽核** | `services/claim_audit.py` |
| **台股財報的科目名稱** | `services/financials.py` 的 `FINMIND_TYPES` |
| **財報公布怎麼偵測** | `services/earnings_watch.py` — 動之前先讀模組說明 |
| **新增一個指令** | 寫 handler → `build_*_handler` → `main.py` 註冊 → `_post_init` 的指令清單。漏掉任一步有測試會擋（`test_wiring.py`） |
| **AI 模型與價格** | `services/llm.py` 的 `AVAILABLE_MODELS` |

## 專案結構

```
stock-telegram-bot/
├── bot/
│   ├── handlers/       # 一個檔案一種職責，見上表
│   │   ├── watch.py        # 自選股增刪查
│   │   ├── digest.py       # 定時推播「推什麼」
│   │   ├── schedule.py     # 定時推播「幾點推」
│   │   ├── card.py         # 股票卡片（純文字查詢的入口）
│   │   ├── messaging.py    # 長訊息分段、失敗訊息、callback 截斷
│   │   ├── pending.py      # 指令不帶參數時的追問
│   │   └── errors.py       # 全域錯誤處理
│   ├── services/       # 外部 API、證據包、資料層檢查、產出稽核、狀態存取
│   │   ├── evidence.py     # 餵給模型的事實與缺漏
│   │   ├── consistency.py  # 資料對不對
│   │   ├── claim_audit.py  # 報告寫出來的數字對不對
│   │   ├── clock.py        # 台北時間（唯一換算時區處）
│   │   ├── formatting.py   # 顯示格式（唯一組標籤處）
│   │   └── store.py        # 狀態檔的原子寫入
│   ├── prompts/        # 分析師 Prompt 模板
│   └── content/        # 預寫投資教學內容
├── scripts/
│   ├── smoke_test.py           # 端對端煙霧測試（真實資料源）
│   ├── exam.py                 # 情境考卷 + 六個角色的端對端實測
│   ├── download_font.py        # 下載中文字型
│   └── stock-bot.service       # systemd 服務設定
├── data/               # 自選股、提醒、財報基準、對話狀態（gitignored）
├── tests/
├── main.py             # 接線：handler 註冊、排程、全域錯誤處理
└── .env.example
```

**一個原則:同一件事只有一個地方。** 這份 README 之前列過四種重複
（標籤、callback 截斷、時區、週末判斷），其中兩種的實作**內容還不一樣**
——那不只是難找，是會產生不一致行為的 bug。

---

## License

MIT
