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
from telegram.ext import ContextTypes

from bot.config import ALLOWED_TELEGRAM_ID

logger = logging.getLogger(__name__)

# Telegram 單則上限 4096，traceback 只留尾端（最深的呼叫在後面，資訊量最大）
_MAX_TRACE = 2500


def _describe(update: object) -> str:
    """出錯時使用者在做什麼——只取指令/按鈕本身，不記訊息全文。"""
    if not isinstance(update, Update):
        return ""
    if update.callback_query and update.callback_query.data:
        return f"按鈕 {update.callback_query.data}"
    if update.message and update.message.text:
        return f"訊息 {update.message.text[:60]}"
    return ""


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    context_desc = _describe(update)
    logger.error("未捕捉的例外（%s）", context_desc or "無 update", exc_info=context.error)

    chat_id = None
    if isinstance(update, Update) and update.effective_chat:
        chat_id = update.effective_chat.id
    elif ALLOWED_TELEGRAM_ID:
        # JobQueue 的例外沒有 update，仍要讓你知道排程壞了
        chat_id = ALLOWED_TELEGRAM_ID
    if chat_id is None:
        return

    trace = "".join(
        traceback.format_exception(type(context.error), context.error, context.error.__traceback__)
    )[-_MAX_TRACE:]
    where = f"（{context_desc}）" if context_desc else ""

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"❌ 出了未預期的錯誤{where}\n"
                f"<code>{html.escape(type(context.error).__name__)}: "
                f"{html.escape(str(context.error)[:200])}</code>\n\n"
                "細節已寫入 log。可用 /health 檢查資料源是否正常。\n\n"
                f"<pre>{html.escape(trace)}</pre>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        # 連錯誤通知都送不出去就只能記 log，不要再往上拋（會變成無窮迴圈）
        logger.error("錯誤通知傳送失敗：%s", e)
