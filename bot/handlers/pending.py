"""兩段式輸入：指令不帶參數時 bot 追問，下一則文字當參數執行。

Telegram 的指令按鈕一定直接送出（無法填入輸入框不送出），
所以反過來讓 bot 用 ForceReply 開口問，使用者只需輸入參數本身。
"""
import time
import logging

from telegram import ForceReply

logger = logging.getLogger(__name__)

_EXPIRY_SECONDS = 180

# action 名稱 → async fn(update, context, text)。各 handler 模組 import 時自行註冊。
PENDING_HANDLERS: dict = {}


def register(action: str):
    """Decorator：註冊 pending action 的執行函式。"""
    def _wrap(func):
        PENDING_HANDLERS[action] = func
        return func
    return _wrap


async def ask(message, context, action: str, prompt: str, **extra) -> None:
    """記下 pending action 並用 ForceReply 追問參數。"""
    context.user_data["pending"] = {
        "action": action,
        "expires": time.monotonic() + _EXPIRY_SECONDS,
        **extra,
    }
    await message.reply_text(prompt, reply_markup=ForceReply(selective=True))


def pop_pending(context):
    """取出並清除 pending；不存在或過期回 None。"""
    pending = context.user_data.pop("pending", None)
    if not pending:
        return None
    if time.monotonic() > pending.get("expires", 0):
        return None
    return pending


async def dispatch_pending(update, context) -> bool:
    """若有有效的 pending action 就執行。回傳是否已處理。"""
    pending = pop_pending(context)
    if not pending:
        return False
    handler = PENDING_HANDLERS.get(pending["action"])
    if handler is None:
        logger.warning("no handler for pending action %s", pending["action"])
        return False
    await handler(update, context, pending)
    return True
