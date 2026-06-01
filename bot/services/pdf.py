import io
import os
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_NAME = "NotoSans"
_FONT_REGISTERED = False

# Strip common emoji Unicode ranges
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0001FA00-\U0001FAFF"
    "⌀-⏿"
    "⬀-⯿"
    "]+",
    flags=re.UNICODE,
)


def _ensure_font() -> str:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _FONT_NAME

    font_path = os.path.join(
        os.path.dirname(__file__), "..", "fonts", "NotoSansTC-Regular.ttf"
    )
    font_path = os.path.abspath(font_path)

    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont(_FONT_NAME, font_path))
        _FONT_REGISTERED = True
        return _FONT_NAME

    return "Helvetica"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _strip_emoji(s: str) -> str:
    return _EMOJI_RE.sub("", s).strip()


def _inline_bold(s: str) -> str:
    """Convert **text** to <b>text</b> for ReportLab XML."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def _is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\|[-| :]+\|$", line))


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and "|" in s[1:-1]


def _parse_table_row(line: str) -> list:
    parts = line.strip().strip("|").split("|")
    return [p.strip() for p in parts]


def _cell(text: str, font: str, size: int = 9, bold: bool = False) -> Paragraph:
    style = ParagraphStyle(
        "cell", fontName=font, fontSize=size, leading=size + 4,
        wordWrap="CJK",
    )
    safe = _inline_bold(_esc(text))
    if bold:
        safe = f"<b>{safe}</b>"
    return Paragraph(safe, style)


def _build_table(rows: list[list[str]], font: str) -> Table:
    col_count = max(len(r) for r in rows)
    padded = [r + [""] * (col_count - len(r)) for r in rows]
    data = [
        [_cell(cell, font, bold=(row_idx == 0)) for cell in row]
        for row_idx, row in enumerate(padded)
    ]

    col_width = (A4[0] - 5 * cm) / col_count
    t = Table(data, colWidths=[col_width] * col_count, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), font),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("WORDWRAP", (0, 0), (-1, -1), True),
    ]))
    return t


def generate_pdf(ticker: str, analysis_type: str, content: str) -> bytes:
    font = _ensure_font()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2.5 * cm, leftMargin=2.5 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
    )

    title_style = ParagraphStyle(
        "ReportTitle", fontName=font, fontSize=16, leading=22,
        spaceAfter=8, textColor=colors.HexColor("#1a1a2e"),
    )
    h1_style = ParagraphStyle(
        "ReportH1", fontName=font, fontSize=14, leading=20,
        spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor("#1a1a2e"),
        borderPad=4,
    )
    h2_style = ParagraphStyle(
        "ReportH2", fontName=font, fontSize=12, leading=18,
        spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#16213e"),
    )
    body_style = ParagraphStyle(
        "ReportBody", fontName=font, fontSize=10, leading=16, spaceAfter=3,
    )
    code_style = ParagraphStyle(
        "ReportCode", fontName=font, fontSize=9, leading=14, spaceAfter=2,
        leftIndent=16, textColor=colors.HexColor("#333333"),
        backColor=colors.HexColor("#f5f5f5"),
    )
    quote_style = ParagraphStyle(
        "ReportQuote", fontName=font, fontSize=10, leading=15, spaceAfter=3,
        leftIndent=12, textColor=colors.HexColor("#555555"),
        borderWidth=2, borderColor=colors.HexColor("#cccccc"),
        borderPad=4,
    )

    story = [
        Paragraph(_esc(_strip_emoji(ticker)) + " — " + _esc(_strip_emoji(analysis_type)), title_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")),
        Spacer(1, 0.3 * cm),
    ]

    lines = content.split("\n")
    i = 0
    in_code_block = False
    pending_table_rows: list[list[str]] = []

    def flush_table():
        if pending_table_rows:
            story.append(Spacer(1, 0.2 * cm))
            story.append(_build_table(pending_table_rows, font))
            story.append(Spacer(1, 0.2 * cm))
            pending_table_rows.clear()

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1

        # Toggle code block
        if line.startswith("```"):
            flush_table()
            in_code_block = not in_code_block
            continue

        if in_code_block:
            safe = _esc(_strip_emoji(line))
            if safe:
                story.append(Paragraph(safe, code_style))
            continue

        # Table separator — skip
        if _is_table_sep(line):
            continue

        # Table row — collect
        if _is_table_row(line):
            pending_table_rows.append(_parse_table_row(_strip_emoji(line)))
            continue

        # Non-table line — flush any pending table first
        flush_table()

        if not line:
            story.append(Spacer(1, 0.15 * cm))
            continue

        # Headings
        if line.startswith("# "):
            text = _inline_bold(_esc(_strip_emoji(line[2:].strip())))
            story.append(Paragraph(text, h1_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
            continue

        if line.startswith("## ") or line.startswith("### "):
            text = _inline_bold(_esc(_strip_emoji(line.lstrip("# ").strip())))
            story.append(Paragraph(text, h2_style))
            continue

        # Blockquote
        if line.startswith("> "):
            text = _inline_bold(_esc(_strip_emoji(line[2:])))
            story.append(Paragraph(text, quote_style))
            continue

        # Horizontal rule
        if line.startswith("---"):
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#eeeeee")))
            story.append(Spacer(1, 0.1 * cm))
            continue

        # Bullet points
        if line.startswith("• ") or line.startswith("- ") or line.startswith("* "):
            text = _inline_bold(_esc(_strip_emoji(line[2:])))
            story.append(Paragraph(f"&bull;&nbsp;&nbsp;{text}", body_style))
            continue

        if re.match(r"^\d+\. ", line):
            text = _inline_bold(_esc(_strip_emoji(re.sub(r"^\d+\. ", "", line))))
            story.append(Paragraph(text, body_style))
            continue

        # Full-line bold (whole line is **...**)
        if line.startswith("**") and line.endswith("**") and len(line) > 4:
            text = _esc(_strip_emoji(line[2:-2]))
            story.append(Paragraph(f"<b>{text}</b>", body_style))
            continue

        # Normal paragraph with possible inline bold
        text = _inline_bold(_esc(_strip_emoji(line)))
        story.append(Paragraph(text, body_style))

    flush_table()
    doc.build(story)
    return buffer.getvalue()
