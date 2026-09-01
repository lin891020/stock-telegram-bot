"""全域錯誤處理：沒被 handler 自己接住的例外，最後由這裡兜底。

沒有這層的話，未捕捉的例外只會在 journalctl 留下 traceback，
使用者端「訊息就是沒來」——跟 bot 掛掉分不出來。/price 整支
沒有 try/except，get_stock_summary 一炸你就什麼都收不到，
而這正是這個專案最怕的那種靜默失敗，只是換了個位置。
"""
import html
import logging
import traceback

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import ContextTypes

from bot.config import ALLOWED_TELEGRAM_ID

logger = logging.getLogger(__name__)

# Telegram 單則上限 4096。留餘裕給標題與錯誤訊息，剩下的才給 traceback。
# Telegram 算的是 UTF-16 單位而不是 Python 字元數，貼著上限送很脆弱，留餘裕。
_TELEGRAM_LIMIT = 4096
_MARGIN = 96
_HEAD_BUDGET = 900


def _describe(update: object) -> str:
    """出錯時使用者在做什麼——只取指令/按鈕本身，不記訊息全文。"""
    if not isinstance(update, Update):
        return ""
    if update.callback_query and update.callback_query.data:
        return f"按鈕 {update.callback_query.data}"
    if update.message and update.message.text:
        return f"訊息 {update.message.text[:60]}"
    return ""


def _is_transient_polling_blip(update: object, error: BaseException) -> bool:
    """長輪詢的連線瞬斷——會自己好，不該拿去吵使用者。

    VM 上跟 Telegram 之間的 TCP 連線閒置久了會被中間設備收掉，
    get_updates 就拋 NetworkError。PTB 的 network_retry_loop 本來就會重連，
    但它同時把例外丟進這裡，於是使用者收到一則有 traceback 的紅色錯誤，
    看起來像 bot 掛了——實際上下一秒就恢復了。實測一個晚上收到兩則。

    只在「沒有 update」時當成瞬斷。使用者正在操作時發生的網路錯誤代表
    他那個指令真的失敗了，那必須說。
    """
    return isinstance(error, NetworkError) and not isinstance(update, Update)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    context_desc = _describe(update)

    if _is_transient_polling_blip(update, context.error):
        logger.warning("長輪詢連線瞬斷（會自動重連）：%s", context.error)
        return

    logger.error("未捕捉的例外（%s）", context_desc or "無 update", exc_info=context.error)

    chat_id = None
    if isinstance(update, Update) and update.effective_chat:
        chat_id = update.effective_chat.id
    elif ALLOWED_TELEGRAM_ID:
        # JobQueue 的例外沒有 update，仍要讓你知道排程壞了
        chat_id = ALLOWED_TELEGRAM_ID
    if chat_id is None:
        return

    where = f"（{html.escape(context_desc)}）" if context_desc else ""
    head = (
        f"❌ 出了未預期的錯誤{where}\n"
        f"<code>{html.escape(type(context.error).__name__)}: "
        f"{html.escape(str(context.error)[:200])}</code>\n\n"
        "細節已寫入 log。可用 /health 檢查資料源是否正常。\n\n"
    )[:_HEAD_BUDGET]

    # 先跳脫再截斷。反過來的話長度會失準——traceback 裡滿是 <module>、
    # <lambda>，跳脫後每個 < 變成 4 個字元，實測 2500 字元會膨脹到 3660，
    # 整則因此超過上限、送不出去。那等於錯誤通知在最需要的時候消失。
    raw = "".join(
        traceback.format_exception(type(context.error), context.error, context.error.__traceback__)
    )
    budget = _TELEGRAM_LIMIT - _MARGIN - len(head) - len("<pre></pre>")
    trace = html.escape(raw)[-budget:] if budget > 0 else ""

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{head}<pre>{trace}</pre>" if trace else head,
            parse_mode="HTML",
        )
    except Exception as e:
        # 連錯誤通知都送不出去就只能記 log，不要再往上拋（會變成無窮迴圈）
        logger.error("錯誤通知傳送失敗：%s", e)
