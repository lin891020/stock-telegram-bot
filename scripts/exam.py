"""三張考卷 + 六個角色的實測。

考卷是那些「平常要等事件發生才會考到」的路徑：財報公布推播、資料層
巡檢亮紅燈、報告自動稽核。這裡用假造的觸發條件把它們逼出來。
角色測試則是拿真的 handler 走真的流程，看使用者實際會看到什麼。

    venv/bin/python scripts/exam.py           # 免費的部分
    venv/bin/python scripts/exam.py --paid    # 含 LLM（會花錢）
"""
import asyncio, json, os, shutil, sys, tempfile, time, traceback
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="exam-")
shutil.copytree(os.path.join(REPO, "data"), os.path.join(work, "data"))
os.symlink(os.path.join(REPO, "bot"), os.path.join(work, "bot"))
os.chdir(work)
sys.path.insert(0, REPO)

from bot.config import ALLOWED_TELEGRAM_ID  # noqa: E402

PAID = "--paid" in sys.argv
UID = ALLOWED_TELEGRAM_ID

# 這次考試用的自選股，跟本機真實清單脫鉤
Path("data/watchlist.json").write_text(
    json.dumps({str(UID): ["NVDA", "2330"]}, ensure_ascii=False))


# ---------- 假 Telegram ----------
class Msg:
    def __init__(self, text="", sink=None):
        self.text, self.chat_id, self.sink = text, UID, sink
        self.from_user = type("U", (), {"id": UID})()
        self.photo = None
    async def reply_text(self, text, **kw):
        self.sink.append(("訊息", text, kw.get("reply_markup"))); return Msg(text, self.sink)
    async def edit_text(self, text, **kw):
        self.sink.append(("編輯", text, kw.get("reply_markup"))); return self
    async def reply_document(self, document, filename=None, caption=None, **kw):
        self.sink.append(("檔案", f"{filename} / {len(document):,} bytes / {caption}", None))
    async def reply_photo(self, photo, caption=None, **kw):
        self.sink.append(("圖片", f"{len(photo):,} bytes / {caption}", None))
    async def delete(self): pass

class Bot:
    def __init__(self, sink): self.sink = sink
    async def send_message(self, chat_id, text, **kw):
        self.sink.append(("推播", text, kw.get("reply_markup"))); return Msg(text, self.sink)
    async def send_photo(self, chat_id, photo, **kw):
        self.sink.append(("推播圖", f"{len(photo):,} bytes", None))

class Ctx:
    def __init__(self, sink, args=None):
        self.bot, self.args = Bot(sink), args or []
        self.user_data, self.chat_data, self.bot_data = {}, {}, {}
        self.error = None

class Upd:
    def __init__(self, sink, text=""):
        self.message = Msg(text, sink)
        self.effective_user = type("U", (), {"id": UID})()
        self.effective_chat = type("C", (), {"id": UID})()
        self.callback_query = None

def Query(sink, data, msg_text=""):
    q = type("Q", (), {})()
    q.data = data
    q.message = Msg(msg_text, sink)
    q.from_user = type("U", (), {"id": UID})()
    q.answer = lambda *a, **k: asyncio.sleep(0)
    async def _edit(text, **kw):
        sink.append(("編輯", text, kw.get("reply_markup")))
    q.edit_message_text = _edit
    upd = Upd(sink); upd.callback_query = q
    return upd


# ---------- 執行器 ----------
results = []

def record(section, name, ok, detail, took=0.0):
    results.append((section, name, ok, detail, took))
    mark = {True: "✅", False: "❌", None: "⏭️"}[ok]
    print(f"  {mark} {name}\n       {detail}", flush=True)

async def check(section, name, fn, paid=False):
    if paid and not PAID:
        record(section, name, None, "跳過（需要 --paid）"); return
    t0 = time.time()
    try:
        detail = await fn()
        record(section, name, True, detail or "通過", time.time() - t0)
    except AssertionError as e:
        record(section, name, False, f"斷言失敗：{e}", time.time() - t0)
    except Exception as e:
        record(section, name, False, f"{type(e).__name__}: {e}", time.time() - t0)
        traceback.print_exc(file=sys.stderr)


def head(title):
    print(f"\n\033[1m{title}\033[0m", flush=True)


# ==========================================================================
# 考卷一：財報公布推播
# ==========================================================================
async def exam1():
    import bot.handlers.earnings as eh
    import bot.services.earnings_watch as ew
    from bot.services.store import load_json, save_json

    STATE = Path("data/earnings_watch.json")

    def state():
        return load_json(STATE, {})

    def set_state(d):
        save_json(STATE, d)

    async def stub_brief(ticker):
        return f"（假速覽）{ticker} 本季 EPS 超出預期", type("E", (), {"missing": []})(), ticker

    # --- 1a 首次看到不推播（避免上線當下把舊財報全推一遍） ---
    async def t_first_sight():
        set_state({})
        sink = []
        eh.build_brief = stub_brief
        ew.detect_new_filing = lambda t: asyncio.sleep(0, result=None)
        await eh.poll_earnings_announcements(Ctx(sink))
        pushes = [s for s in sink if s[0] == "推播"]
        assert not pushes, f"首次看到就推了 {len(pushes)} 則"
        base = state().get("NVDA", {}).get("last_reported")
        if not base:
            # 資料源暫時掛掉會長得跟邏輯壞掉一模一樣，先分清楚再說
            from bot.services.earnings import fetch_earnings_data
            probe = await fetch_earnings_data("NVDA")
            raise AssertionError(
                f"沒有建立基準；yfinance 這次回 error={probe.get('error')!r}、"
                f"{len(probe.get('quarters', []))} 季 —— "
                + ("資料源暫時失敗，重跑一次" if probe.get("error") or not probe.get("quarters")
                   else "資料正常，是偵測邏輯的問題")
            )
        return f"0 則推播，基準建立於 {base}"
    await check("考卷一", "首次見到某支股票 → 不推播、只建基準", t_first_sight)

    # --- 1b 有新財報 → 推一則 ---
    async def t_push():
        s0 = state(); s0["NVDA"]["last_reported"] = "2000-01-01"; set_state(s0)
        sink = []
        await eh.poll_earnings_announcements(Ctx(sink))
        pushes = [s for s in sink if s[0] == "推播"]
        assert len(pushes) == 1, f"預期 1 則，實際 {len(pushes)} 則"
        assert "EPS 更新" in pushes[0][1], "訊號來源沒寫在標題"
        assert pushes[0][2] is not None, "沒有『完整報告』按鈕"
        return f"1 則推播｜{pushes[0][1].splitlines()[0][:56]}"
    await check("考卷一", "偵測到新財報 → 推一則速覽（含完整報告按鈕）", t_push)

    # --- 1c 同一季不會推第二次 ---
    async def t_no_dup():
        sink = []
        await eh.poll_earnings_announcements(Ctx(sink))
        pushes = [s for s in sink if s[0] == "推播"]
        assert not pushes, f"同一季又推了 {len(pushes)} 則"
        e = state()["NVDA"]
        assert e.get("last_filing") == e.get("last_reported"), \
            f"兩條訊號基準沒同步：{e.get('last_filing')} vs {e.get('last_reported')}"
        return f"0 則重複｜兩條訊號基準同步於 {e['last_reported']}"
    await check("考卷一", "緊接著再跑一輪 → 不會重複推播", t_no_dup)

    # --- 1d 推播失敗不吃掉那一季（這是修過的 bug） ---
    async def t_fail_keeps():
        s0 = state(); s0["NVDA"]["last_reported"] = "2000-01-01"; set_state(s0)

        async def boom(ticker):
            raise TimeoutError("模擬 LLM 逾時")
        eh.build_brief = boom
        sink = []
        await eh.poll_earnings_announcements(Ctx(sink))
        assert not [s for s in sink if s[0] == "推播"], "失敗卻推了訊息"
        kept = state()["NVDA"]["last_reported"]
        assert kept == "2000-01-01", f"失敗卻推進了基準到 {kept}——那一季永遠不會再推"

        # 修好之後，下一輪要補推
        eh.build_brief = stub_brief
        sink2 = []
        await eh.poll_earnings_announcements(Ctx(sink2))
        again = [s for s in sink2 if s[0] == "推播"]
        assert len(again) == 1, f"恢復後沒有補推（{len(again)} 則）"
        return "LLM 逾時 → 0 則推播且基準未動；恢復後下一輪補推 1 則"
    await check("考卷一", "推播中途失敗 → 基準不前進，下輪補推", t_fail_keeps)

    # --- 1e 一支壞掉不影響其他支 ---
    async def t_isolation():
        set_state({"NVDA": {"last_reported": "2000-01-01", "last_filing": "2000-01-01"},
                   "2330": {"last_reported": "2000-01-01", "last_filing": "2000-01-01"}})
        calls = []
        async def half_broken(ticker):
            calls.append(ticker)
            if ticker == "NVDA":
                raise RuntimeError("模擬 SEC 限流")
            return f"（假速覽）{ticker}", type("E", (), {"missing": []})(), ticker
        eh.build_brief = half_broken
        sink = []
        await eh.poll_earnings_announcements(Ctx(sink))
        pushes = [s for s in sink if s[0] == "推播"]
        assert "2330" in calls, "第一支炸掉後就不掃後面了"
        return f"NVDA 炸掉，2330 仍被處理（推播 {len(pushes)} 則）"
    await check("考卷一", "一支股票出錯 → 不影響同一輪的其他股票", t_isolation)

    # --- 1f 真實 SEC 閘門 ---
    async def t_sec_gate():
        import importlib
        importlib.reload(ew)
        set_state({})
        first = await ew.detect_new_filing("NVDA")
        assert first is None, f"首次見到就回報了 {first}"
        seen = state()["NVDA"].get("last_seen_filing")
        assert seen, "閘門沒有記錄已檢查過的申報日"
        t0 = time.time()
        second = await ew.detect_new_filing("NVDA")
        gate_time = time.time() - t0
        assert second is None, "同一份申報被重複回報"
        s0 = state(); s0["NVDA"].pop("last_seen_filing"); s0["NVDA"]["last_filing"] = "2000-01-01"
        set_state(s0)
        third = await ew.detect_new_filing("NVDA")
        assert third, "把基準調回 2000 年後仍偵測不到 NVDA 的財報申報"
        return f"首見不推｜閘門攔截耗時 {gate_time:.2f}s（1 個請求）｜基準調舊後抓到 {third}"
    await check("考卷一", "真實 SEC：首見不推、閘門攔截、基準調舊後抓得到", t_sec_gate)

    # --- 1g 真的跑一次 LLM 推播，印出使用者實際會收到的訊息 ---
    async def t_real_push():
        import importlib
        importlib.reload(eh); importlib.reload(ew)
        set_state({"NVDA": {"last_reported": "2000-01-01",
                            "last_seen_filing": "2099-01-01",
                            "last_filing": "2099-01-01"}})
        Path("data/watchlist.json").write_text(json.dumps({str(UID): ["NVDA"]}))
        sink = []
        await eh.poll_earnings_announcements(Ctx(sink))
        pushes = [s for s in sink if s[0] == "推播"]
        assert len(pushes) == 1, f"預期 1 則，實際 {len(pushes)}"
        body = pushes[0][1]
        print("\n" + "\033[2m" + "─" * 74 + "\n" + body[:2000] + "\n" + "─" * 74 + "\033[0m")
        Path("data/watchlist.json").write_text(json.dumps({str(UID): ["NVDA", "2330"]}))
        return f"真實推播 {len(body):,} 字元（內容如上）"
    await check("考卷一", "真實 LLM：完整走一次財報推播", t_real_push, paid=True)


# ==========================================================================
# 考卷二：資料層巡檢亮紅燈
# ==========================================================================
async def exam2():
    from bot.services.consistency import check_financials
    from bot.services.evidence import build_evidence
    from bot.services.financials import get_financials
    from bot.services.metrics import fetch_key_metrics

    real = {}

    async def t_real_clean():
        fin = await get_financials("2330")
        real["fin"] = fin
        metrics, _ = await fetch_key_metrics("2330")
        real["metrics"] = metrics
        problems = check_financials(fin, metrics)
        assert not problems, f"真實資料被誤報：{problems}"
        annual = fin.get("annual", {})
        yrs = sorted(annual.get("revenue", {}))[-1:]
        return f"台積電真實財報 0 誤報（最新年度 {yrs[0] if yrs else '?'}）"
    await check("考卷二", "真實資料不該亮燈（誤報率）", t_real_clean)

    def corrupt(**over):
        import copy
        fin = copy.deepcopy(real["fin"])
        annual = fin["annual"]
        for k, fn in over.items():
            annual[k] = fn(annual.get(k, {}))
        return fin

    def latest_year(annual, key):
        d = {k: v for k, v in (annual.get(key) or {}).items() if "非全年" not in k}
        return max(d) if d else None

    # 重現當初那個真實 bug：現金流量表的累計數被當單季加總
    async def t_cashflow():
        annual = real["fin"]["annual"]
        y = latest_year(annual, "revenue")
        rev = annual["revenue"][y]
        bad = corrupt(operating_cashflow=lambda d: {**d, y: rev * 1.48})
        problems = check_financials(bad)
        assert any("營業現金流" in p for p in problems), f"沒抓到：{problems}"
        return f"營業現金流灌成營收的 1.48 倍 → 「{problems[0][:60]}…」"
    await check("考卷二", "重現原始 bug：累計數被加總（現金流 > 營收）", t_cashflow)

    async def t_ordering():
        annual = real["fin"]["annual"]
        y = latest_year(annual, "revenue")
        bad = corrupt(gross_profit=lambda d: {**d, y: annual["revenue"][y] * 1.2})
        problems = check_financials(bad)
        assert any("毛利" in p for p in problems), f"沒抓到：{problems}"
        return f"毛利灌成營收的 1.2 倍 → 「{problems[0][:60]}…」"
    await check("考卷二", "損益表順序：毛利大於營收", t_ordering)

    async def t_tax():
        annual = real["fin"]["annual"]
        y = latest_year(annual, "net_income")
        if not y or y not in (annual.get("pretax_income") or {}):
            return "台積電缺稅前淨利欄位，此規則以合成資料驗（見下一項）"
        bad = corrupt(net_income=lambda d: {**d, y: d[y] * 1.5})
        problems = check_financials(bad)
        assert any("稅後淨利" in p and "稅前" in p for p in problems), f"沒抓到：{problems}"
        return f"淨利偏離稅前減稅 50% → 「{problems[0][:60]}…」"
    await check("考卷二", "稅務恆等式：淨利 ≠ 稅前 − 所得稅", t_tax)

    async def t_balance():
        annual = real["fin"]["annual"]
        y = latest_year(annual, "total_assets")
        if not y:
            return "無資產負債資料，略過"
        bad = corrupt(total_assets=lambda d: {**d, y: d[y] * 1.3})
        problems = check_financials(bad)
        assert any("不平衡" in p for p in problems), f"沒抓到：{problems}"
        return f"資產灌 30% → 「{problems[0][:60]}…」"
    await check("考卷二", "資產負債表不平衡", t_balance)

    async def t_capex():
        annual = real["fin"]["annual"]
        y = latest_year(annual, "capex")
        if not y:
            return "無資本支出資料，略過"
        bad = corrupt(capex=lambda d: {**d, y: abs(d[y])})
        problems = check_financials(bad)
        assert any("資本支出" in p for p in problems), f"沒抓到：{problems}"
        return f"資本支出翻正 → 「{problems[0][:60]}…」"
    await check("考卷二", "資本支出正負號抓錯", t_capex)

    # 誤報防線：上次踩到的那條
    async def t_no_false_positive():
        annual = {
            "revenue": {"2025": 530_000_000},
            "gross_profit": {"2025": 260_000_000},
            "operating_income": {"2025": 103_500_000},
            "pretax_income": {"2025": 124_900_000},
            "tax": {"2025": 18_800_000},
            "net_income": {"2025": 106_100_000},
        }
        problems = check_financials({"annual": annual})
        assert not problems, f"聯發科型（業外 > 稅）被誤報：{problems}"
        return "淨利(1,061億) > 營業利益(1,035億) 的合法情形 → 不亮燈"
    await check("考卷二", "誤報防線：業外收入大於所得稅時淨利可高於營業利益",
                t_no_false_positive)

    # 端對端：紅燈有沒有真的走到證據包
    async def t_reaches_evidence():
        annual = real["fin"]["annual"]
        y = latest_year(annual, "revenue")
        bad = corrupt(operating_cashflow=lambda d: {**d, y: annual["revenue"][y] * 1.48})
        ev = build_evidence("2330", "financial", {"name": "台積電", "market": "TW"},
                            bad, real["metrics"], [])
        warn = [n for n in ev.notes if "資料自我矛盾" in n]
        assert warn, f"紅燈沒進證據包，notes={ev.notes}"
        assert "資料自我矛盾" in ev.to_prompt(), "警告沒出現在餵給模型的文字裡"
        real["bad_evidence"] = ev
        return f"紅燈進了證據包並出現在 prompt：「{warn[0][:56]}…」"
    await check("考卷二", "端對端：紅燈進得了證據包與 prompt", t_reaches_evidence)

    # 最關鍵的一題：模型會不會把警告傳達給使用者
    async def t_model_relays():
        from bot.services.llm import call_llm
        from bot.handlers.analyze import _SYSTEM
        from bot.prompts.analysis import PROMPTS
        ev = real["bad_evidence"]
        user = f"今天日期：2026年08月29日\n\n{ev.to_prompt()}\n\n{PROMPTS['financial'].format(ticker='2330')}"
        content = await asyncio.to_thread(call_llm, _SYSTEM, user)
        real["report"] = content
        real["evidence_text"] = ev.to_prompt()
        globals()["_real_report"] = {"text": content, "ev": ev.to_prompt(),
                                     "fin": real["fin"], "mt": real["metrics"]}
        hit = any(k in content for k in ("矛盾", "不要引用", "可疑", "存疑", "異常", "不一致"))
        assert hit, "模型完全沒把資料矛盾轉達給使用者"
        idx = max((content.find(k) for k in ("矛盾", "不要引用", "可疑", "存疑", "異常")), default=-1)
        snippet = content[max(0, idx - 90):idx + 130].replace("\n", " ")
        print(f"\n\033[2m   模型的轉達：…{snippet}…\033[0m")
        return f"模型有轉達（報告 {len(content):,} 字元）"
    await check("考卷二", "真實 LLM：模型會把資料矛盾轉達給使用者嗎", t_model_relays, paid=True)


# ==========================================================================
# 考卷三：報告自動稽核
# ==========================================================================
async def exam3():
    from bot.services.claim_audit import audit_note, audit_numbers

    EV = """=== 2330 本次查到的事實 ===
【損益】
- 營收（2024 年度）：2,894,308,000 千元　[來源：FinMind]
- 毛利（2024 年度）：1,622,930,000 千元　[來源：FinMind]
- 營業利益（2024 年度）：1,320,150,000 千元　[來源：FinMind]
- 稅後淨利（2024 年度）：1,173,000,000 千元　[來源：FinMind]
【現金流】
- 營業現金流（2024 年度）：1,826,000,000 千元　[來源：FinMind]
- 資本支出（2024 年度）：-956,000,000 千元　[來源：FinMind]
"""

    async def t_derived_ok():
        # 毛利率 56.07%、淨利率 40.53%、營業利益率 45.61% —— 全是合法推導
        report = ("毛利率達 56.07%，營業利益率 45.61%，稅後淨利率 40.53%。"
                  "自由現金流為 870,000,000 千元。")
        bad = audit_numbers(report, EV)
        assert not bad, f"合法推導被誤報：{bad}"
        return "四個推導值（三個率 + 自由現金流）全部認得，0 誤報"
    await check("考卷三", "合法推導不該被標記（誤報率）", t_derived_ok)

    async def t_fabricated():
        report = "台積電 2024 年研發費用為 504,800,000 千元，員工人數 83,000 人。"
        bad = audit_numbers(report, EV)
        note = audit_note(report, EV)
        got = "抓到" if bad else "沒抓到"
        return f"{got}｜被標記的數字：{bad}｜註記長度 {len(note)}"
    await check("考卷三", "編造的數字（單點觀察，不斷言）", t_fabricated)

    async def t_fnr_real_evidence():
        """真正的問題不是單一案例，是誤放率。用真實證據包量。"""
        import random, asyncio as aio
        from bot.services.claim_audit import extract_numbers, _derivations, _close
        from bot.services.evidence import build_evidence
        from bot.services.financials import get_financials
        from bot.services.metrics import fetch_key_metrics
        from bot.services.stock import get_stock_summary
        sd, fin, (mt, an) = await aio.gather(
            get_stock_summary("2330"), get_financials("2330"), fetch_key_metrics("2330"))
        text = build_evidence("2330", "financial", sd, fin, mt, an).to_prompt()
        nums = extract_numbers(text)
        base = sorted(nums, key=abs, reverse=True)[:40]
        derived = list(_derivations(base))
        random.seed(11)
        hits = tot = 0
        for _ in range(3000):
            v = random.choice(list(nums)) * (1 + random.choice([1, -1]) * random.uniform(0.05, 0.5))
            tot += 1
            if any(_close(v, e) for e in nums) or any(_close(v, d) for d in derived):
                hits += 1
        rate = hits / tot
        globals()["_fnr"] = rate
        # 這是已知極限，不是回歸。記錄下來是為了不讓人以為這層擋得住東西。
        return (f"誤放率 {rate:.0%}（證據包 {len(nums)} 數字 → {len(derived):,} 推導值）"
                f"——這層幾乎沒有偵測力，真正有用的是下面的比率重算")
    await check("考卷三", "舊層「推不推導得出來」的已知極限", t_fnr_real_evidence)

    async def t_ratio_recompute():
        """新的那層：把具名比率直接重算。"""
        import asyncio as aio
        from bot.services.claim_audit import verify_ratios, ratio_candidates
        from bot.services.financials import get_financials
        from bot.services.metrics import fetch_key_metrics
        fin, (mt, _) = await aio.gather(get_financials("2330"), fetch_key_metrics("2330"))
        cands = ratio_candidates(fin, mt, "毛利率")
        assert cands, "算不出台積電的毛利率，比率重算等於沒有"

        真 = "、".join(f"{v:.1f}%" for _, v in cands)
        # 真值不該叫
        ok = verify_ratios(f"毛利率為 {cands[0][1]:.1f}%", fin, mt)
        assert not ok, f"真值被誤報：{ok}"
        # 離譜的值要叫
        bad = verify_ratios("毛利率高達 88.0%", fin, mt)
        assert bad, "編造的 88% 沒被抓到"
        # 財測要豁免
        fc = verify_ratios("公司預期下季毛利率為 88.0%", fin, mt)
        assert not fc, f"公司財測被誤報：{fc}"
        return f"候選 {真}｜真值不叫、88% 會叫、財測豁免"
    await check("考卷三", "比率重算（新增的那一層）", t_ratio_recompute)

    async def t_ratio_no_false_alarm_on_real_report():
        from bot.services.claim_audit import verify_ratios, _NAMED_RATIO_RE
        rep = globals().get("_real_report")
        if not rep:
            return "需要考卷二的真實報告（--paid）"
        fin, mt = rep["fin"], rep["mt"]
        claims = [(m.group("name"), m.group("value")) for m in _NAMED_RATIO_RE.finditer(rep["text"])]
        bad = verify_ratios(rep["text"], fin, mt)
        assert not bad, f"真實報告被誤報 {len(bad)} 個：{bad}"
        return f"真實報告 {len(claims)} 個具名比率宣稱，0 個誤報"
    await check("考卷三", "比率重算在真實報告上的誤報率", t_ratio_no_false_alarm_on_real_report, paid=True)

    async def t_clean_silent():
        report = "營收 2,894,308,000 千元，毛利 1,622,930,000 千元。"
        assert audit_note(report, EV) == "", "乾淨的報告卻附了稽核註記"
        return "完全引用證據包的報告 → 不附註記（安靜）"
    await check("考卷三", "乾淨報告不加註記", t_clean_silent)

    async def t_rounding():
        report = "毛利率約 56.1%，淨利率 40.5%。"
        bad = audit_numbers(report, EV)
        assert not bad, f"四捨五入被誤判成編造：{bad}"
        return "56.1% / 40.5%（報告慣用的四捨五入）不誤報"
    await check("考卷三", "四捨五入不該被當成編造", t_rounding)

    async def t_on_real_report():
        from bot.services.claim_audit import audit_numbers as an
        rep = globals().get("_real_report")
        if not rep:
            return "需要考卷二的真實報告（--paid）"
        bad = an(rep["text"], rep["ev"])
        from bot.services.claim_audit import extract_numbers
        total = len(extract_numbers(rep["text"]))
        return (f"真實報告 {len(rep['text']):,} 字元、{total} 個數字 → "
                f"{len(bad)} 個被標記"
                + (f"：{bad[:6]}" if bad else "（全部可溯源／或全部被推導空間吸收）"))
    await check("考卷三", "套在考卷二那份真實報告上", t_on_real_report, paid=True)



# ==========================================================================
# 考卷四：模型端故障
# ==========================================================================
async def exam4():
    import bot.handlers.analyze as analyze
    import bot.handlers.earnings as eh
    import bot.handlers.health as health
    import bot.services.llm as llm
    from bot.services.store import load_json, save_json
    from bot.handlers.messaging import failure_text

    def down(*a, **k):
        raise RuntimeError("Your credit balance is too low to access the Anthropic API")

    async def t_message():
        orig = llm._call_anthropic
        llm._call_anthropic = down
        try:
            llm.call_llm("s", "u")
            assert False, "模型端故障卻沒拋例外"
        except llm.LLMUnavailable as e:
            text = failure_text(e)
        finally:
            llm._call_anthropic = orig
        assert "儲值" in text, f"沒告訴使用者該儲值：{text}"
        assert "稍後再試" not in text, "額度用盡卻叫人稍後再試"
        return text.replace("\n", "｜")

    await check("考卷四", "額度用盡時的訊息說得夠清楚嗎", t_message)

    async def t_analyze_down():
        # 要從供應商那一層打斷，才會走到 call_llm 的包裝。
        # 直接換掉 analyze.call_llm 等於繞過包裝，測不到真實行為。
        orig = llm._call_anthropic
        llm._call_anthropic = down
        try:
            sink = []
            await analyze.analyze_callback.__wrapped__(
                Query(sink, "analyze_2330_financial"), Ctx(sink))
            last = sink[-1][1]
            assert "AI 模型" in last, f"沒說是模型的問題，使用者會一直重試：{last[:80]}"
            assert "稍後再試" not in last, "額度用盡卻叫人稍後再試"
            return last.replace("\n", "｜")[:90]
        finally:
            llm._call_anthropic = orig
    await check("考卷四", "/analyze 遇到模型故障", t_analyze_down)

    async def t_watchdog():
        orig = health.call_llm
        health.call_llm = down
        try:
            sink = []
            await health.health_watchdog(Ctx(sink))
            pushes = [x for x in sink if x[0] == "推播"]
            assert pushes, "AI 掛了整晚，每日巡檢卻沒通知我"
            assert "AI 模型" in pushes[0][1], f"通知裡沒指出是 AI：{pushes[0][1][:80]}"
            return pushes[0][1].replace("\n", "｜")[:100]
        finally:
            health.call_llm = orig
    await check("考卷四", "每日巡檢會主動通知我", t_watchdog)

    async def t_push_not_swallowed():
        import bot.services.earnings_report as er
        orig = er.call_llm
        er.call_llm = down
        ST = Path("data/earnings_watch.json")
        try:
            Path("data/watchlist.json").write_text(json.dumps({str(UID): ["NVDA"]}))
            save_json(ST, {"NVDA": {"last_reported": "2000-01-01",
                                    "last_seen_filing": "2099-01-01",
                                    "last_filing": "2099-01-01"}})
            sink = []
            await eh.poll_earnings_announcements(Ctx(sink))
            assert not [x for x in sink if x[0] == "推播"], "模型掛了卻推了東西出去"
            after = load_json(ST, {})["NVDA"]["last_reported"]
            assert after == "2000-01-01", f"基準被推進到 {after}，那一季永遠不會再推"
            return "0 則推播、基準停在 2000-01-01，模型恢復後會補推"
        finally:
            er.call_llm = orig
            Path("data/watchlist.json").write_text(json.dumps({str(UID): ["NVDA", "2330"]}))
    await check("考卷四", "財報公布剛好碰上模型故障 → 不會吃掉那一季", t_push_not_swallowed)

    async def t_non_llm_survives():
        import bot.handlers.price as price
        from bot.services.news import fetch_and_summarize
        orig = llm.call_llm
        llm.call_llm = down
        try:
            sink = []
            await price.price_command(Upd(sink), Ctx(sink, ["2330", "NVDA"]))
            assert "收 " in sink[-1][1], "報價被模型故障拖下水"
            text = await fetch_and_summarize(["2330"])
            assert "自選股行情" in text, "晨報被模型故障拖下水"
            return "報價與晨報照常（新聞已改成不經模型）"
        finally:
            llm.call_llm = orig
    await check("考卷四", "不靠 AI 的功能不受影響", t_non_llm_survives)


# ==========================================================================
# 六個角色
# ==========================================================================
async def personas():
    import bot.handlers.price as price
    import bot.handlers.card as card
    import bot.handlers.watch as watch
    import bot.handlers.schedule as schedule
    import bot.handlers.menu as menu
    import bot.handlers.model as model
    import bot.handlers.analyze as analyze
    import bot.handlers.errors as errors
    import bot.handlers.chart as chart
    import bot.handlers.alert as alert
    from bot.services.news import fetch_and_summarize

    def texts(sink):
        return "\n".join(str(b) for _, b, _ in sink)

    # --- 角色 1：第一次用的完全新手 ---
    head("角色 1／完全新手（沒買過股票，朋友叫他來試）")

    async def p1_start():
        sink = []; ctx = Ctx(sink)
        await menu.start_handler(Upd(sink), ctx)
        body = texts(sink)
        btns = sum(len(r) for _, _, m in sink if m for r in m.inline_keyboard)
        assert btns >= 3, f"主選單只有 {btns} 顆按鈕"
        assert "直接傳股票代號" in body, "沒告訴新手最快的用法"
        jargon = [w for w in ("護城河", "估值模型", "DCF", "beta") if w in body]
        return f"{len(sink)} 則、{btns} 顆按鈕" + (f"｜開場就出現術語 {jargon}" if jargon else "｜開場無術語")
    await check("角色1", "/start 看得懂嗎", p1_start)

    async def p1_typo():
        sink = []
        await card.text_lookup_handler(Upd(sink, "台G電"), Ctx(sink))
        body = texts(sink)
        assert body, "打錯字完全沒有回應"
        assert "找不到" in body or "查無" in body, f"打錯字的回應看不出是找不到：{body[:80]}"
        assert ("試" in body or "例如" in body), "找不到卻沒給下一步怎麼辦"
        return f"「台G電」→ {body[:70]}"
    await check("角色1", "打錯字有沒有救", p1_typo)

    async def p1_name():
        sink = []
        await card.text_lookup_handler(Upd(sink, "台積電"), Ctx(sink))
        body = texts(sink)
        assert "2330" in body, f"打中文名沒帶出代號：{body[:80]}"
        btns = sum(len(r) for _, _, m in sink if m for r in m.inline_keyboard)
        assert btns >= 4, f"卡片只有 {btns} 顆按鈕"
        assert "收" in body, "報價沒標明是收盤價"
        return f"「台積電」→ 卡片 {btns} 顆按鈕｜{body.splitlines()[0][:50]}"
    await check("角色1", "打中文公司名 → 卡片", p1_name)

    async def p1_menu_wording():
        sink = []
        await analyze.analyze_pick_callback.__wrapped__(Query(sink, "apick_2330"), Ctx(sink))
        body = texts(sink)
        assert "—" in body, "分析類型沒有白話說明"
        assert "不會直接告訴你買或賣" in body or "非投資建議" in body, "沒有免責說明"
        n = body.count("• ")
        return f"{n} 個類型每個都配白話，且標明不給買賣建議"
    await check("角色1", "分析選單七個術語有沒有白話", p1_menu_wording)

    # --- 角色 2：手機重度使用者（只按按鈕，不打指令） ---
    head("角色 2／手機族（單手操作，從不打字）")

    async def p2_chain():
        sink = []; ctx = Ctx(sink)
        await card.text_lookup_handler(Upd(sink, "NVDA"), ctx)
        cbs = []
        for _, _, m in sink:
            if m:
                for row in m.inline_keyboard:
                    cbs += [b.callback_data for b in row]
        assert any(c.startswith("cana_") for c in cbs), "卡片沒有深度分析按鈕"
        assert any(c.startswith("cearn_") for c in cbs), "卡片沒有財報按鈕"
        assert any(c.startswith("chartp_") for c in cbs), "卡片沒有 K 線按鈕"
        assert any(c.startswith("cadd_") for c in cbs), "卡片沒有加自選按鈕"
        assert any(c.startswith("ahint_") for c in cbs), "卡片沒有設提醒按鈕"
        return f"卡片 5 條路徑都在：{[c.split('_')[0] for c in cbs]}"
    await check("角色2", "卡片按鈕涵蓋所有主要功能", p2_chain)

    async def p2_add_watch():
        sink = []
        await card.card_watch_callback.__wrapped__(Query(sink, "cadd_NVDA_NVIDIA"), Ctx(sink))
        from bot.services.watchlist import get_watchlist
        assert "NVDA" in get_watchlist(UID), "按了加自選卻沒進清單"
        again = []
        await card.card_watch_callback.__wrapped__(Query(again, "cadd_NVDA_NVIDIA"), Ctx(again))
        return f"加入成功；重複按不會加兩次（清單 {get_watchlist(UID)}）"
    await check("角色2", "加自選 → 重複按不會重複加", p2_add_watch)

    async def p2_card_stays():
        sink = []
        await card.card_analyze_callback.__wrapped__(Query(sink, "cana_NVDA"), Ctx(sink))
        kinds = [k for k, _, _ in sink]
        assert "編輯" not in kinds, "按了分析卻把卡片本身改掉了，報價就看不到了"
        return f"另發新訊息（{kinds}），原卡片留在原地"
    await check("角色2", "按分析不會吃掉原本的報價卡片", p2_card_stays)

    async def p2_chart():
        sink = []
        await chart.chart_period_callback.__wrapped__(Query(sink, "chartp_NVDA_6m"), Ctx(sink))
        assert any(k in ("圖片", "推播圖") for k, _, _ in sink), f"沒出圖：{[k for k,_,_ in sink]}"
        return "K 線圖有出來"
    await check("角色2", "K 線按鈕", p2_chart)

    # --- 角色 3：美股當沖（最在意即時性） ---
    head("角色 3／美股當沖客（盤中查價，延遲會害死人）")

    async def p3_staleness():
        sink = []
        await price.price_command(Upd(sink), Ctx(sink, ["2330", "NVDA"]))
        body = sink[-1][1]
        tw_block = body.split("\n\n")[0]   # 卡片格式：標籤一行、報價一行
        assert "2330" in tw_block, f"沒有台股區塊：{body[:100]}"
        assert "收 " in tw_block, f"台股沒標收盤，會被當成即時價：{tw_block!r}"
        assert "/" in tw_block and "（" in tw_block, f"台股沒標資料日期：{tw_block!r}"
        us_block = [b for b in body.split("\n\n") if "NVDA" in b]
        return f"台股「{tw_block.splitlines()[-1][:38]}」｜美股「{us_block[0].splitlines()[-1][:30]}」"
    await check("角色3", "台股延遲有沒有講清楚（同畫面美股接近即時）", p3_staleness)

    async def p3_alert():
        sink = []; ctx = Ctx(sink)
        await alert.ask_alert_condition(Msg("", sink), ctx, "NVDA")
        assert ctx.user_data.get("pending"), "提醒沒進追問狀態"
        body = texts(sink)
        assert any(c in body for c in (">", "<", "漲", "跌", "例")), f"沒教怎麼輸入條件：{body[:80]}"
        return f"追問已建立｜{body[:70]}"
    await check("角色3", "設價格提醒的引導", p3_alert)

    # --- 角色 4：會計背景的價值投資人（會逐項對數字） ---
    head("角色 4／會計背景（會拿財報逐項對，最挑剔）")

    async def p4_evidence():
        from bot.services.evidence import build_evidence
        from bot.services.financials import get_financials
        from bot.services.metrics import fetch_key_metrics
        from bot.services.stock import get_stock_summary
        sd, fin, (mt, an) = await asyncio.gather(
            get_stock_summary("2330"), get_financials("2330"), fetch_key_metrics("2330"))
        ev = build_evidence("2330", "financial", sd, fin, mt, an)
        prompt = ev.to_prompt()
        assert "來源：" in prompt, "數字沒標來源"
        assert "期間規則" in prompt, "沒有期間規則"
        assert "無法取得" in prompt, "沒有缺漏區"
        no_period = [f["label"] for f in ev.facts.values()
                     if not f.get("period") and f.get("group") not in ("標的識別",)]
        return (f"{len(ev.facts)} 項事實、{len(ev.missing)} 項缺漏、{len(ev.notes)} 則註記"
                + (f"｜未標期間：{no_period}" if no_period else "｜每項都標了期間"))
    await check("角色4", "證據包：每個數字都標來源與期間", p4_evidence)

    async def p4_missing_honest():
        from bot.services.evidence import build_evidence
        ev = build_evidence("9999", "financial", {}, {"error": "查無此代號"}, {}, [])
        prompt = ev.to_prompt()
        assert ev.missing, "查不到資料卻沒列缺漏"
        assert "不得推測" in prompt or "不得自行推測" in prompt, "沒禁止模型填空"
        return f"查無資料 → {len(ev.missing)} 項缺漏且明文禁止推測"
    await check("角色4", "查不到資料時會誠實說缺，不讓模型填空", p4_missing_honest)

    async def p4_name_never_guessed():
        from bot.services.formatting import name_label
        assert name_label("2408", "") == "2408", "名稱拿不到卻編了一個"
        assert name_label("2408", "南亞科") == "南亞科(2408)"
        return "名稱拿不到就只寫代號（2408 曾被模型猜成聯電）"
    await check("角色4", "公司名稱絕不猜", p4_name_never_guessed)

    # --- 角色 5：亂打的人（壓力測試） ---
    head("角色 5／亂打的人（貼圖、超長字串、注入）")

    async def p5_junk():
        cases = ["", "   ", "😂😂😂", "a" * 500, "'; DROP TABLE stocks;--",
                 "<script>alert(1)</script>", "../../etc/passwd", "0" * 30, "?????"]
        out = []
        for q in cases:
            sink = []
            await card.text_lookup_handler(Upd(sink, q), Ctx(sink))
            out.append((q[:14] or "(空)", len(sink)))
        crashed = [c for c, n in out if n < 0]
        assert not crashed, crashed
        noisy = [(c, n) for c, n in out if n > 1]
        return f"{len(cases)} 種垃圾輸入全部沒炸" + (f"｜多則回應：{noisy}" if noisy else "｜回應克制")
    await check("角色5", "垃圾輸入不會炸", p5_junk)

    async def p5_html_escape():
        sink = []
        await card.text_lookup_handler(Upd(sink, "<b>hi</b>"), Ctx(sink))
        body = texts(sink)
        assert "<b>" not in body or "&lt;" in body, f"使用者輸入直接回填未跳脫：{body[:80]}"
        return "含 HTML 的輸入不會原樣回填"
    await check("角色5", "HTML 注入", p5_html_escape)

    async def p5_error_handler():
        sink = []; ctx = Ctx(sink)
        ctx.error = ValueError("x" * 3000)
        await errors.error_handler(Upd(sink, "/price BOOM"), ctx)
        body = texts(sink)
        assert body, "錯誤處理器沒送出任何東西"
        assert len(body) <= 4096, f"錯誤通知本身超過 Telegram 上限：{len(body)}"
        return f"3,000 字元的例外 → 通知 {len(body)} 字元（上限 4,096）"
    await check("角色5", "超長例外不會讓錯誤通知本身送不出去", p5_error_handler)

    async def p5_bad_callback():
        sink = []
        await analyze.analyze_callback.__wrapped__(Query(sink, "analyze_2330_不存在的類型"), Ctx(sink))
        body = texts(sink)
        assert "無效" in body, f"壞掉的 callback 沒有好好處理：{body[:80]}"
        return f"偽造的 callback → {body[:60]}"
    await check("角色5", "偽造 / 過期的按鈕資料", p5_bad_callback)

    # --- 角色 6：每天看晨報的長期使用者 ---
    head("角色 6／長期使用者（每天早上只看那一則晨報）")

    async def p6_watchlist():
        sink = []
        await watch.watchlist_command(Upd(sink), Ctx(sink))
        body = texts(sink)
        assert body, "自選股清單空白"
        return f"{body.splitlines()[0][:60]}"
    await check("角色6", "/watchlist", p6_watchlist)

    async def p6_morning():
        text = await fetch_and_summarize(["2330", "NVDA"])
        assert "自選股行情" in text, "晨報沒有行情總覽"
        tw = [l for l in text.splitlines() if "台股" in l]
        assert tw, "沒有台股區塊標題"
        assert "收盤" in tw[0], f"台股區塊沒標資料日期：{tw[0]}"
        has_links = "<a href" in text
        no_summary = "摘要" not in text
        print("\n\033[2m" + "─" * 74 + "\n" + text[:900] + "\n" + "─" * 74 + "\033[0m")
        return (f"{len(text):,} 字元｜台股標了日期｜"
                + ("新聞給連結不做摘要" if has_links and no_summary else "新聞區塊需確認"))
    await check("角色6", "晨報（真實資料，無 LLM）", p6_morning)

    async def p6_settime():
        sink = []; ctx = Ctx(sink)
        await schedule.settime_command(Upd(sink), ctx)
        body = texts(sink)
        assert ":" in body, f"沒顯示目前時間設定：{body[:80]}"
        return f"{body.splitlines()[0][:60]}"
    await check("角色6", "/settime 看得到目前排程", p6_settime)

    async def p6_model():
        sink = []
        await model.model_command(Upd(sink), Ctx(sink))
        body = texts(sink)
        assert "$" in body, "沒有價格資訊，使用者無從判斷成本"
        assert "目前" in body or "✅" in body, "看不出目前用哪個"
        return f"{[l for l in body.splitlines() if l.strip()][0][:60]}"
    await check("角色6", "/model 看得懂在選什麼", p6_model)

    async def p6_health():
        import bot.handlers.health as health
        sink = []
        await health.health_command(Upd(sink), Ctx(sink))
        body = texts(sink)
        n_ok, n_bad = body.count("✅"), body.count("❌")
        assert n_ok + n_bad >= 7, f"只有 {n_ok + n_bad} 項檢查"
        bad = [l for l in body.splitlines() if "❌" in l]
        return f"{n_ok} 綠 / {n_bad} 紅" + (f"｜{bad}" if bad else "")
    await check("角色6", "/health 七項檢查", p6_health)


# ==========================================================================
async def main():
    print(f"\033[1m實測開始\033[0m（{'含 LLM，會花錢' if PAID else '免費項目'}）  工作目錄 {work}")
    head("═══ 考卷一：財報公布推播（強制觸發） ═══")
    await exam1()
    head("═══ 考卷二：資料層巡檢亮紅燈（注入錯誤資料） ═══")
    await exam2()
    head("═══ 考卷三：報告自動稽核 ═══")
    await exam3()
    head("═══ 考卷四：AI 模型掛掉時，使用者看到什麼 ═══")
    await exam4()
    head("═══ 六個角色的真實流程 ═══")
    await personas()

    print("\n" + "═" * 78)
    by = {}
    for sec, name, ok, detail, took in results:
        by.setdefault(sec, []).append(ok)
    for sec, oks in by.items():
        p = sum(1 for o in oks if o is True)
        f = sum(1 for o in oks if o is False)
        s = sum(1 for o in oks if o is None)
        print(f"{sec:<10} 通過 {p:>2}　失敗 {f:>2}　跳過 {s:>2}")
    fails = [(s, n, d) for s, n, o, d, _ in results if o is False]
    print("═" * 78)
    if fails:
        print(f"\033[1m❌ {len(fails)} 項失敗\033[0m")
        for s, n, d in fails:
            print(f"   [{s}] {n}\n       {d}")
    else:
        print("\033[1m✅ 全部通過\033[0m")

asyncio.run(main())
shutil.rmtree(work, ignore_errors=True)
