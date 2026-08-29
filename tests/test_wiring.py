"""main.py 的接線測試。

BUG 3 的修法是「把清除追問的 handler 註冊在 group −1」。
drop_stale_pending 自己有測，但「它真的被掛在比指令更早的 group」
一直沒有任何東西擋著——接線錯了，函式再正確也不會被呼叫到。
"""
import pytest

import main

# 接線測試要真的把 Application 組起來，所以環境必須跟 requirements.txt 一致。
# 本機若還停在舊版 PTB（缺 rate-limiter extra）就跳過，並在訊息裡說清楚
# ——測試全綠但 bot 其實跑不起來，是最容易誤導人的狀態。
aiolimiter = pytest.importorskip(
    "aiolimiter",
    reason="環境與 requirements.txt 不符：跑 pip install -r requirements.txt",
)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(main, "TELEGRAM_BOT_TOKEN", "123:FAKE")
    built = {}


    # run_polling 會阻塞，換掉它才能跑到組裝結束
    import telegram.ext
    monkeypatch.setattr(telegram.ext.Application, "run_polling", lambda self, *a, **k: built.setdefault("app", self))
    main.main()
    return built["app"]


def test_pending_cleaner_runs_before_commands(app):
    """清除追問必須在比指令更早的 group，否則清了也沒用。"""
    from bot.handlers.pending import drop_stale_pending

    groups = {
        g: [getattr(h, "callback", None) for h in handlers]
        for g, handlers in app.handlers.items()
    }
    assert -1 in groups, "沒有 group −1，清除追問的 handler 不會比指令先跑"
    assert drop_stale_pending in groups[-1]

    command_groups = [g for g in groups if g > -1]
    assert command_groups, "指令應該註冊在 group −1 之後"
    assert min(command_groups) > -1


def test_error_handler_is_registered(app):
    from bot.handlers.errors import error_handler
    assert error_handler in app.error_handlers


def test_all_scheduled_jobs_are_present(app):
    names = {job.name for job in app.job_queue.jobs()}
    expected = {
        "daily_news", "tw_closing", "alert_check",
        "big_move_check", "earnings_poll", "health_watchdog",
    }
    assert expected <= names, f"少了排程：{expected - names}"


def _cron_minutes(job) -> int:
    """從 APScheduler 的 cron trigger 取出 UTC 的「當日第幾分鐘」。

    不用 job.next_t——排程器沒啟動時它是 None，測試裡不會啟動。
    """
    import re
    text = str(job.job.trigger)
    hour = int(re.search(r"hour='(\d+)'", text).group(1))
    minute = int(re.search(r"minute='(\d+)'", text).group(1))
    return hour * 60 + minute


def test_watchdog_runs_before_the_morning_report(app):
    """巡檢排在晨報之前，壞掉的話你讀報告的同時就知道。"""
    jobs = {job.name: job for job in app.job_queue.jobs()}
    watchdog = _cron_minutes(jobs["health_watchdog"])
    news = _cron_minutes(jobs["daily_news"])
    assert watchdog < news, f"巡檢 {watchdog} 應該早於晨報 {news}（UTC 分鐘）"


def test_persistence_and_concurrency_are_on(app):
    assert app.persistence is not None, "沒開持久化，重啟就掉對話狀態"
    assert app.concurrent_updates, "沒開並行，/analyze 會擋住所有其他指令"
