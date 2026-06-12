from bot.handlers.messaging import split_message


def test_short_text_single_chunk():
    assert split_message("hello") == ["hello"]


def test_split_at_paragraph_boundary():
    paras = [f"段落{i} " + "x" * 500 for i in range(20)]
    text = "\n\n".join(paras)
    chunks = split_message(text, limit=1500)
    assert all(len(c) <= 1500 for c in chunks)
    # 內容不遺失
    assert "".join(chunks).replace("\n\n", "") == text.replace("\n\n", "")


def test_hard_split_single_long_paragraph():
    # 單一段落（無空行）超過上限也要能切
    text = "x" * 9000
    chunks = split_message(text, limit=3500)
    assert all(len(c) <= 3500 for c in chunks)
    assert "".join(chunks) == text


def test_mixed_long_and_short_paragraphs():
    text = "short" + "\n\n" + "y" * 4000 + "\n\n" + "tail"
    chunks = split_message(text, limit=3500)
    assert all(len(c) <= 3500 for c in chunks)
    joined = "".join(chunks)
    assert "short" in joined and "tail" in joined and joined.count("y") == 4000
