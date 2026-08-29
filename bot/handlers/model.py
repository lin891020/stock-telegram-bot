from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.auth import restrict_callback
from bot.services.llm import (
    ANTHROPIC_CHAT_MODEL, AVAILABLE_MODELS, get_current_model, set_current_model,
)

_PROVIDER_GROUPS = [
    ("anthropic", "Claude（付費）"),
    ("gemini", "Gemini（免費）"),
    ("github", "GitHub Models（免費）"),
]


def _model_name(key: str) -> str:
    info = AVAILABLE_MODELS.get(key)
    return info.label if info else key


def _menu_text() -> str:
    current = get_current_model()
    lines = [f"🤖 目前使用：{_model_name(current)}", ""]
    for provider, heading in _PROVIDER_GROUPS:
        items = [(k, v) for k, v in AVAILABLE_MODELS.items() if v.provider == provider]
        if not items:
            continue
        lines.append(heading)
        for key, info in items:
            mark = "▸ " if key == current else "   "
            lines.append(f"{mark}{info.label} — {info.note}")
        lines.append("")
    lines.append(
        f"ℹ️ 這裡選的是**深度分析**用的模型。晨報新聞摘要固定用 "
        f"{_model_name(ANTHROPIC_CHAT_MODEL)}（每天都跑，省成本），不受這裡影響。"
    )
    return "\n".join(lines)


def _keyboard() -> InlineKeyboardMarkup:
    current = get_current_model()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'✅ ' if key == current else ''}{info.label}",
            callback_data=f"model_{key}",
        )]
        for key, info in AVAILABLE_MODELS.items()
    ])


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_menu_text(), reply_markup=_keyboard())


@restrict_callback
async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    model_key = query.data.replace("model_", "", 1)
    try:
        set_current_model(model_key)
    except ValueError:
        await query.answer("這個模型已不在清單中", show_alert=True)
        return
    # 切完仍留在選單，方便比較與再切；只更新勾選狀態，不把訊息換成一行結果
    await query.answer(f"已切換至 {_model_name(model_key)}")
    await query.edit_message_text(_menu_text(), reply_markup=_keyboard())


def build_model_handler(auth_filter):
    return [
        CommandHandler("model", model_command, filters=auth_filter),
        CallbackQueryHandler(model_callback, pattern="^model_"),
    ]
