"""定時推播的**時間**：排程與 /settime。

跟 digest.py 的分工：那裡決定「推什麼」，這裡決定「幾點推」。
時間一律以台北時間存放與顯示，換算成 UTC 只在 clock.utc_time_for 一處。

要新增一個定時推播，改三個地方：
  1. settings.TIME_KEYS  —— 設定檔欄位與預設時間
  2. 這裡的 _JOBS        —— job 名稱、設定鍵、要跑的 callback
  3. main.py             —— 啟動時呼叫 schedule_all(job_queue)
_SETTIME_TARGETS 與 /settime 的按鈕都是從 _JOBS 推導出來的，不用另外改。
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot.auth import restrict_callback
from bot.handlers.digest import (
    send_daily_news, send_noon_snapshot, send_tw_closing, send_us_closing,
)
from bot.services import clock
from bot.services.settings import get_time, parse_hhmm, set_time

logger = logging.getLogger(__name__)


class Job:
    """一個定時推播：job 名稱、settings 的鍵、要跑什麼、/settime 怎麼叫它。"""

    def __init__(self, name: str, time_key: str, callback, label: str, presets: tuple[str, ...]):
        self.name, self.time_key = name, time_key
        self.callback, self.label, self.presets = callback, label, presets


# /settime 的參數名 → 這個 job。新增排程只要在這裡加一筆。
_JOBS: dict[str, Job] = {
    "news": Job("daily_news", "news", send_daily_news, "起床報",
                ("06:00", "06:30", "07:00", "07:30")),
    "us": Job("us_closing", "us_close", send_us_closing, "美股收盤速報",
              ("05:00", "05:30", "06:00", "22:00")),
    "noon": Job("noon_snapshot", "noon", send_noon_snapshot, "台股盤中速報",
                ("11:00", "12:00", "13:00")),
    "tw": Job("tw_closing", "tw_close", send_tw_closing, "台股收盤速報",
              ("14:00", "14:30", "15:00")),
}


def _reschedule(job_queue, job: Job) -> None:
    """依設定檔裡的台北時間重新掛上；舊的先移除，避免同名 job 疊加。"""
    for existing in job_queue.get_jobs_by_name(job.name):
        existing.schedule_removal()
    hour, minute = parse_hhmm(get_time(job.time_key))
    job_queue.run_daily(job.callback, time=clock.utc_time_for(hour, minute), name=job.name)
    logger.info("Job %s scheduled at %s Taipei", job.name, get_time(job.time_key))


def schedule_all(job_queue) -> None:
    """啟動時掛上所有定時推播。"""
    for job in _JOBS.values():
        _reschedule(job_queue, job)


# ── /settime ──────────────────────────────────────────────────────────

def _current_times() -> str:
    return "\n".join(f"• {job.label}：{get_time(job.time_key)}" for job in _JOBS.values())


def _settime_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t, callback_data=f"stime_{key}_{t}") for t in job.presets]
        for key, job in _JOBS.items()
    ])


async def _apply(job_queue, key: str, raw: str) -> str:
    job = _JOBS[key]
    normalized = set_time(job.time_key, raw)
    _reschedule(job_queue, job)
    return f"✅ {job.label}時間已改為每天 {normalized}（台北時間，週末不推送）"


async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/settime 06:30（起床報）｜/settime tw 14:30（台股收盤速報）"""
    if not context.args:
        await update.message.reply_text(
            f"目前推送時間（台北時間，週末不推送）：\n{_current_times()}\n\n"
            "點按鈕直接改（由上而下依序對應上面四項），\n"
            "或輸入自訂時間：/settime 06:45、/settime tw 14:10、\n"
            "/settime us 05:00、/settime noon 11:30",
            reply_markup=_settime_keyboard(),
        )
        return

    if len(context.args) >= 2 and context.args[0].lower() in _JOBS:
        key, raw = context.args[0].lower(), context.args[1]
    else:
        key, raw = "news", context.args[0]

    if parse_hhmm(raw) is None:
        await update.message.reply_text(
            "時間格式錯誤，請用 24 小時制 HH:MM，例如：\n/settime 08:30\n/settime tw 14:30"
        )
        return

    await update.message.reply_text(await _apply(context.job_queue, key, raw))


@restrict_callback
async def settime_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/settime 的預設時間按鈕：stime_{key}_{HH:MM}"""
    query = update.callback_query
    await query.answer()

    _, key, raw = query.data.split("_", 2)
    if key not in _JOBS or parse_hhmm(raw) is None:
        await query.edit_message_text("❌ 無效的時間選項，請重新使用 /settime")
        return

    await query.edit_message_text(await _apply(context.job_queue, key, raw))


def build_schedule_handler(auth_filter):
    return [
        CommandHandler("settime", settime_command, filters=auth_filter),
        CallbackQueryHandler(settime_pick_callback, pattern="^stime_"),
    ]
