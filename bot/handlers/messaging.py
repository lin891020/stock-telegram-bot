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


def _paginate(chunks: list[str]) -> list[str]:
    """兩段以上就標頁碼。長報告分批到達時，看不到頁碼就分不出
    「這樣就完了」還是「後面還沒到／掉了」。"""
    if len(chunks) < 2:
        return chunks
    total = len(chunks)
    return [f"{chunk}\n\n— {i}/{total} —" for i, chunk in enumerate(chunks, 1)]


async def send_long(bot, chat_id: int, text: str, parse_mode: str = None,
                    reply_markup=None) -> None:
    """訊息過長時自動切分。按鈕只掛在最後一段，否則會出現在半截訊息下面。"""
    chunks = _paginate(split_message(text))
    for index, chunk in enumerate(chunks):
        await bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=parse_mode,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


async def reply_long(message, text: str, parse_mode: str = None) -> None:
    for chunk in _paginate(split_message(text)):
        await message.reply_text(chunk, parse_mode=parse_mode)
