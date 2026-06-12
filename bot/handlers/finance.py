import asyncio
import logging
from datetime import date
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters,
)

from bot.handlers.messaging import reply_long
from bot.services.github_store import read_profile, write_profile
from bot.services.llm import call_llm, ANTHROPIC_CHAT_MODEL

logger = logging.getLogger(__name__)

INCOME, EXPENSES, SAVINGS, DEBT, GOAL = range(5)

_GOALS = [
    ("🏦 緊急備用金", "emergency_fund"),
    ("📈 開始投資ETF", "start_etf"),
    ("💰 存第一桶金", "first_million"),
    ("🏠 買房計畫", "buy_house"),
    ("🌅 退休規劃", "retirement"),
]

_GOAL_LABELS = {k: l for l, k in _GOALS}

_SYSTEM = (
    "你是一位專業的個人理財教練，專門幫助台灣的投資新手規劃財務。"
    "請用繁體中文給出具體可執行的建議，語氣鼓勵且實際。"
    "提供具體的金額、時間和行動步驟，讓完全沒有理財經驗的人也能照著做。"
)


async def finance_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    existing = await asyncio.to_thread(read_profile)

    if existing and existing.get("monthly_income"):
        keyboard = [
            [InlineKeyboardButton("✅ 使用現有資料繼續", callback_data="finance_use_existing")],
            [InlineKeyboardButton("🔄 重新設定", callback_data="finance_reset")],
        ]
        await update.message.reply_text(
            f"找到你上次的資料（{existing.get('updated_at', '')}）：\n"
            f"月收入：NT${existing.get('monthly_income', 0):,}\n"
            f"目標：{existing.get('goal', '未設定')}\n\n要繼續還是重新設定？",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        context.user_data["existing_profile"] = existing
        return GOAL

    await update.message.reply_text(
        "歡迎使用個人理財教練！💪\n\n"
        "我會問你幾個問題，然後給你專屬的薪水分配建議。\n\n"
        "第一步：請輸入你每月**稅後**收入（新台幣，只要數字）："
    )
    return INCOME


async def _handle_existing_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "finance_reset":
        await query.edit_message_text("好的，重新開始！\n\n請輸入你每月稅後收入（新台幣）：")
        context.user_data.pop("existing_profile", None)
        return INCOME

    # Use existing — go straight to goal selection
    existing = context.user_data.get("existing_profile", {})
    context.user_data.update({
        "income": existing.get("monthly_income", 0),
        "expenses": existing.get("monthly_expenses", 0),
        "savings": existing.get("savings", 0),
        "debt": existing.get("debt", 0),
    })
    keyboard = [[InlineKeyboardButton(l, callback_data=f"goal_{k}")] for l, k in _GOALS]
    await query.edit_message_text(
        "你想更新理財目標嗎？選一個：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return GOAL


def _parse_number(text: str) -> Optional[int]:
    try:
        return int(text.replace(",", "").replace("，", "").replace(" ", ""))
    except ValueError:
        return None


async def got_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    n = _parse_number(update.message.text)
    if n is None:
        await update.message.reply_text("請輸入數字，例如：50000")
        return INCOME
    context.user_data["income"] = n
    await update.message.reply_text("每月固定支出大約多少？（房租、水電、交通、伙食，新台幣）：")
    return EXPENSES


async def got_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    n = _parse_number(update.message.text)
    if n is None:
        await update.message.reply_text("請輸入數字，例如：20000")
        return EXPENSES
    context.user_data["expenses"] = n
    await update.message.reply_text("目前有多少存款？（新台幣，沒有請輸入 0）：")
    return SAVINGS


async def got_savings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    n = _parse_number(update.message.text)
    if n is None:
        await update.message.reply_text("請輸入數字，沒有存款請輸入 0")
        return SAVINGS
    context.user_data["savings"] = n
    await update.message.reply_text("有任何貸款或負債嗎？（沒有請輸入 0，新台幣）：")
    return DEBT


async def got_debt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    n = _parse_number(update.message.text)
    if n is None:
        await update.message.reply_text("請輸入數字，沒有負債請輸入 0")
        return DEBT
    context.user_data["debt"] = n
    keyboard = [[InlineKeyboardButton(l, callback_data=f"goal_{k}")] for l, k in _GOALS]
    await update.message.reply_text(
        "最後一步！你最想達成哪個理財目標？",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return GOAL


async def got_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    goal_key = query.data.replace("goal_", "")
    goal_label = _GOAL_LABELS.get(goal_key, goal_key)

    profile = {
        "monthly_income": context.user_data.get("income", 0),
        "monthly_expenses": context.user_data.get("expenses", 0),
        "savings": context.user_data.get("savings", 0),
        "debt": context.user_data.get("debt", 0),
        "goal": goal_label,
        "updated_at": str(date.today()),
    }

    await asyncio.to_thread(write_profile, profile)
    await query.edit_message_text(f"目標：{goal_label} ✅\n\n正在為你生成個人化理財建議...")

    disposable = profile["monthly_income"] - profile["monthly_expenses"]
    user_msg = (
        f"根據以下財務狀況，請給出個人化的薪水分配建議和理財計畫：\n\n"
        f"每月稅後收入：NT${profile['monthly_income']:,}\n"
        f"每月固定支出：NT${profile['monthly_expenses']:,}\n"
        f"每月可支配餘額：NT${disposable:,}\n"
        f"目前存款：NT${profile['savings']:,}\n"
        f"負債：NT${profile['debt']:,}\n"
        f"理財目標：{profile['goal']}\n\n"
        f"請提供：\n"
        f"1. 建議的薪水分配比例（根據他的實際數字客製化，附具體金額）\n"
        f"2. 針對「{profile['goal']}」的第一步具體行動（本週就能做到的事）\n"
        f"3. 預估達成目標的時間\n"
        f"4. 給完全新手最重要的 2 個提醒"
    )

    try:
        advice = await asyncio.to_thread(call_llm, _SYSTEM, user_msg, ANTHROPIC_CHAT_MODEL)
        await reply_long(query.message, advice)
    except Exception as exc:
        logger.error("Finance advice generation failed: %s", exc)
        await query.message.reply_text(f"建議生成失敗：{exc}")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("已取消。輸入 /finance 可以重新開始。")
    return ConversationHandler.END


def build_finance_handler(auth_filter):
    return ConversationHandler(
        entry_points=[CommandHandler("finance", finance_start, filters=auth_filter)],
        states={
            INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_income)],
            EXPENSES: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_expenses)],
            SAVINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_savings)],
            DEBT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_debt)],
            GOAL: [
                CallbackQueryHandler(got_goal, pattern="^goal_"),
                CallbackQueryHandler(_handle_existing_choice, pattern="^finance_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
