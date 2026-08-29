from bot.handlers.messaging import _paginate, split_message


def test_single_chunk_has_no_page_marker():
    assert _paginate(["只有一段"]) == ["只有一段"]


def test_multiple_chunks_get_numbered():
    out = _paginate(["a", "b", "c"])
    assert out[0].endswith("— 1/3 —")
    assert out[2].endswith("— 3/3 —")


def test_split_then_paginate_marks_every_part():
    text = "\n\n".join("段落" * 400 for _ in range(6))
    parts = _paginate(split_message(text))
    assert len(parts) > 1
    assert all(f"/{len(parts)} —" in p for p in parts)
