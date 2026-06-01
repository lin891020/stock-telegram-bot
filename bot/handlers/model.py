from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.services.llm import AVAILABLE_MODELS, get_current_model, set_current_model


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = get_current_model()
    keyboard = [
        [InlineKeyboardButton(
            f"{'✅ ' if key == current else ''}{name}",
            callback_data=f"model_{key}",
        )]
        for key, (name, _) in AVAILABLE_MODELS.items()
    ]
    await update.message.reply_text(
        f"目前使用：{AVAILABLE_MODELS[current][0]}\n\n選擇分析模型：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    model_key = query.data.replace("model_", "", 1)
    try:
        set_current_model(model_key)
        name, _ = AVAILABLE_MODELS[model_key]
        await query.edit_message_text(f"✅ 已切換至：{name}")
    except ValueError:
        await query.edit_message_text("❌ 未知的模型")


def build_model_handler(auth_filter):
    return [
        CommandHandler("model", model_command, filters=auth_filter),
        CallbackQueryHandler(model_callback, pattern="^model_"),
    ]
