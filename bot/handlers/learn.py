import asyncio
import json
import logging
import os
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from bot.services.llm import call_llm, ANTHROPIC_CHAT_MODEL

logger = logging.getLogger(__name__)

_LESSONS_PATH = os.path.join(os.path.dirname(__file__), "..", "content", "lessons.json")
_SYSTEM = (
    "你是一位投資理財教育專家，用繁體中文為台灣完全新手解釋投資概念。"
    "語氣親切、易懂，避免行話，多舉台灣的實際例子。"
)


def _load_lessons() -> dict:
    with open(_LESSONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _find_lesson(topic: str, lessons: dict) -> Optional[str]:
    """Case-insensitive partial match against lesson keys."""
    topic_lower = topic.lower()
    for key, content in lessons.items():
        if key.lower() in topic_lower or topic_lower in key.lower():
            return content
    return None


async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        lessons = _load_lessons()
        topic_list = "、".join(lessons.keys())
        await update.message.reply_text(
            f"📚 輸入你想學的主題，例如：\n"
            f"/learn ETF\n/learn 緊急備用金\n/learn 本益比\n\n"
            f"已有內容：{topic_list}\n\n"
            f"找不到的主題會由 AI 即時回答。"
        )
        return

    topic = " ".join(context.args)

    lessons = _load_lessons()
    lesson = _find_lesson(topic, lessons)

    if lesson:
        await update.message.reply_text(lesson)
        return

    # Fall back to Claude
    await update.message.reply_text(f"查詢「{topic}」中...")
    user_msg = (
        f"請用白話文解釋「{topic}」，包含：\n"
        f"1. 定義（一句話）\n2. 為什麼新手需要了解這個\n"
        f"3. 台灣實際例子\n4. 新手最需要知道的 1-2 件事\n\n長度約 300-400 字。"
    )

    try:
        response = await asyncio.to_thread(call_llm, _SYSTEM, user_msg, ANTHROPIC_CHAT_MODEL)
        await update.message.reply_text(response)
    except Exception as exc:
        logger.error("learn_command failed for topic '%s': %s", topic, exc)
        await update.message.reply_text(f"查詢失敗：{exc}")


def build_learn_handler(auth_filter):
    return CommandHandler("learn", learn_command, filters=auth_filter)
