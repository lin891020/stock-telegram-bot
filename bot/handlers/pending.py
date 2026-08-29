"""兩段式輸入：指令不帶參數時 bot 追問，下一則文字當參數執行。

Telegram 的指令按鈕一定直接送出（無法填入輸入框不送出），
所以反過來讓 bot 開口問，使用者只需輸入參數本身。

刻意不用 ForceReply：它會把輸入框鎖成「回覆某則訊息」的狀態，
使用者得先解除才能打別的字。pending 狀態存在 user_data，
下一則純文字自然會被 dispatch_pending 接走，不需要 Telegram 強制回覆。

過期時間用 time.time() 而非 monotonic：user_data 會被 PicklePersistence
存到磁碟，而 monotonic 是「行程啟動以來的秒數」，重啟後基準歸零——
舊行程存的 300 拿到新行程比對，會變成永不過期或立刻過期。
"""
import time
import logging

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
    """記下 pending action 並追問參數（一般訊息，不鎖輸入框）。"""
    context.user_data["pending"] = {
        "action": action,
        "expires": time.time() + _EXPIRY_SECONDS,
        **extra,
    }
    await message.reply_text(prompt)


def pop_pending(context):
    """取出並清除 pending；不存在或過期回 None。"""
    pending = context.user_data.pop("pending", None)
    if not pending:
        return None
    if time.time() > pending.get("expires", 0):
        return None
    return pending


def clear_pending(context) -> bool:
    """丟掉等待中的追問。回傳原本是否有東西可丟。"""
    return context.user_data.pop("pending", None) is not None


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
