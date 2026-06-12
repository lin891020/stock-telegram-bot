"""長訊息切分：Telegram 單則上限 4096 字，超過會直接發送失敗。"""

# 預留餘裕（HTML 實體展開等）
MAX_MSG_LEN = 3500


def split_message(text: str, limit: int = MAX_MSG_LEN) -> list[str]:
    """切成多段：優先在空行邊界切，單一段落仍超長就硬切。"""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        # 單一段落本身超長 → 硬切
        while len(para) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:limit])
            para = para[limit:]
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > limit:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def send_long(bot, chat_id: int, text: str, parse_mode: str = None) -> None:
    for chunk in split_message(text):
        await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=parse_mode)


async def reply_long(message, text: str, parse_mode: str = None) -> None:
    for chunk in split_message(text):
        await message.reply_text(chunk, parse_mode=parse_mode)
