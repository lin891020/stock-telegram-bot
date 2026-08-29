"""端對端煙霧測試：真實資料源、真實 handler，出口換成 stdout。

    venv/bin/python scripts/smoke_test.py           # 免費的部分
    venv/bin/python scripts/smoke_test.py --paid    # 含 LLM（會花錢）

單元測試把外部相依都換成假的，所以「資料源改版」「API key 過期」
「模型代號打錯」這類問題它一個都抓不到。這支相反：什麼都不 mock，
只把最後的出口從 Telegram 換掉。

刻意不碰 Telegram 的 getUpdates——那會把正在跑的 bot 的訊息領走。
data/ 先複製到暫存目錄，跑完不影響真實狀態。
"""
import asyncio, os, shutil, sys, tempfile, time, traceback

# --- 隔離狀態：複製 data/ 到暫存目錄再 chdir 過去 -----------------------
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="smoke-")
shutil.copytree(os.path.join(REPO, "data"), os.path.join(work, "data"))
os.symlink(os.path.join(REPO, "bot"), os.path.join(work, "bot"))
os.chdir(work)
sys.path.insert(0, REPO)

from bot.config import ALLOWED_TELEGRAM_ID  # noqa: E402

RUN_PAID = "--paid" in sys.argv

# --- 假的 Telegram 物件 ---------------------------------------------------
class Msg:
    def __init__(self, text="", sink=None):
        self.text, self.chat_id, self.sink = text, ALLOWED_TELEGRAM_ID, sink
    async def reply_text(self, text, **kw):
        self.sink.append(("訊息", text, kw.get("reply_markup")))
        return Msg(text, self.sink)
    async def edit_text(self, text, **kw):
        self.sink.append(("編輯", text, kw.get("reply_markup"))); return self
    async def reply_document(self, document, filename=None, caption=None, **kw):
        self.sink.append(("檔案", f"{filename} / {len(document)} bytes / {caption}", None))
    async def delete(self): pass

class Bot:
    def __init__(self, sink): self.sink = sink
    async def send_message(self, chat_id, text, **kw):
        self.sink.append(("推播", text, kw.get("reply_markup"))); return Msg(text, self.sink)

class Ctx:
    def __init__(self, sink, args=None):
        self.bot, self.args = Bot(sink), args or []
        self.user_data, self.chat_data, self.bot_data = {}, {}, {}
        self.error = None

class Upd:
    def __init__(self, sink, text=""):
        self.message = Msg(text, sink)
        self.effective_user = type("U", (), {"id": ALLOWED_TELEGRAM_ID})()
        self.effective_chat = type("C", (), {"id": ALLOWED_TELEGRAM_ID})()
        self.callback_query = None

# --- 執行器 ---------------------------------------------------------------
results = []

async def case(name, coro_fn, paid=False):
    if paid and not RUN_PAID:
        results.append((name, "跳過", "需要 --paid（會呼叫 LLM）", 0)); return
    sink = []
    t0 = time.time()
    try:
        await coro_fn(sink)
        took = time.time() - t0
        if not sink:
            results.append((name, "無輸出", "handler 沒有送出任何東西", took)); return
        kind, body, markup = sink[-1]
        preview = " / ".join(f"{k}:{str(b)[:110]}" for k, b, _ in sink[:3])
        btns = sum(len(r) for r in markup.inline_keyboard) if markup else 0
        results.append((name, "OK", f"{len(sink)} 則{f'・{btns} 顆按鈕' if btns else ''} — {preview}", took))
    except Exception as e:
        results.append((name, "失敗", f"{type(e).__name__}: {e}", time.time() - t0))
        traceback.print_exc(file=sys.stderr)

async def main():
    import bot.handlers.price as price
    import bot.handlers.card as card
    import bot.handlers.watch as watch
    import bot.handlers.digest as digest
    import bot.handlers.health as health
    import bot.handlers.model as model
    import bot.handlers.menu as menu
    import bot.handlers.market as market
    import bot.handlers.errors as errors
    import bot.handlers.earnings as earnings
    import bot.handlers.analyze as analyze
    from bot.services.charts import render_chart
    from bot.services.news import fetch_and_summarize

    await case("/price 2330 NVDA", lambda s: price.price_command(Upd(s), Ctx(s, ["2330", "NVDA"])))
    await case("純文字「台積電」出卡片", lambda s: card.text_lookup_handler(Upd(s, "台積電"), Ctx(s)))
    await case("純文字「NVDA」出卡片", lambda s: card.text_lookup_handler(Upd(s, "NVDA"), Ctx(s)))
    await case("/watchlist", lambda s: watch.watchlist_command(Upd(s), Ctx(s)))
    await case("/market 大盤", lambda s: market.market_command(Upd(s), Ctx(s)))
    await case("/health 七項檢查", lambda s: health.health_command(Upd(s), Ctx(s)))
    await case("/model 選單", lambda s: model.model_command(Upd(s), Ctx(s)))
    await case("/start 主選單", lambda s: menu.start_handler(Upd(s), Ctx(s)))
    await case("/help", lambda s: menu.help_handler(Upd(s), Ctx(s)))
    await case("/cancel（無進行中）", lambda s: menu.cancel_handler(Upd(s), Ctx(s)))

    async def _watch_then_cancel(s):
        ctx = Ctx(s)
        await watch.watch_command(Upd(s), ctx)          # 無參數 → 追問
        assert ctx.user_data.get("pending"), "追問狀態沒建立"
        await menu.cancel_handler(Upd(s), ctx)
        assert not ctx.user_data.get("pending"), "/cancel 沒清掉追問"
    await case("追問 → /cancel 清除", _watch_then_cancel)

    async def _err(s):
        ctx = Ctx(s); ctx.error = ValueError("模擬的資料源錯誤")
        await errors.error_handler(Upd(s, "/price XYZ"), ctx)
    await case("全域錯誤處理", _err)

    async def _chart(s):
        png = await asyncio.to_thread(render_chart, "2330", "6m", "台積電")
        s.append(("圖檔", f"PNG {len(png)} bytes", None))
        assert png[:4] == b"\x89PNG", "不是合法 PNG"
    await case("/chart 2330 6m 產生 K 線", _chart)

    async def _watchdog(s):
        await health.health_watchdog(Ctx(s))
        s.append(("巡檢", "全綠 → 安靜（沒有推播就是對的）" if not s else "有紅燈", None))
    await case("每日巡檢（全綠應安靜）", _watchdog)

    # --- 以下會花錢 -------------------------------------------------------
    await case("/earnings NVDA（LLM）",
               lambda s: earnings.earnings_command(Upd(s), Ctx(s, ["NVDA"])), paid=True)
    await case("晨報 fetch_and_summarize（LLM）",
               lambda s: _news(s, fetch_and_summarize), paid=True)
    await case("/analyze 2330 財務健康（LLM+PDF）",
               lambda s: _analyze(s, analyze), paid=True)

async def _news(s, fn):
    text = await fn(["2330", "NVDA"])
    s.append(("晨報", text[:400], None))

async def _analyze(s, analyze):
    q = type("Q", (), {})()
    q.data = "analyze_2330_financial"
    q.message = Msg("", s)
    q.answer = lambda *a, **k: asyncio.sleep(0)
    q.edit_message_text = lambda text, **kw: s.append(("編輯", text, None)) or asyncio.sleep(0)
    upd = Upd(s); upd.callback_query = q
    await analyze.analyze_callback.__wrapped__(upd, Ctx(s))

asyncio.run(main())

print(f"\n{'項目':<34}{'結果':<7}{'秒':>6}  細節")
print("─" * 118)
for name, status, detail, took in results:
    mark = {"OK": "✅", "失敗": "❌", "跳過": "⏭️", "無輸出": "⚠️"}[status]
    print(f"{name:<34}{mark:<6}{took:>6.1f}  {detail[:70]}")
ok = sum(1 for _, st, _, _ in results if st == "OK")
bad = [n for n, st, _, _ in results if st in ("失敗", "無輸出")]
print("─" * 118)
print(f"通過 {ok}／{len(results)}" + (f"　問題：{', '.join(bad)}" if bad else "　無失敗"))
shutil.rmtree(work, ignore_errors=True)
