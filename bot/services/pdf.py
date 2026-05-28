import io
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_NAME = "NotoSans"
_FONT_REGISTERED = False

def _ensure_font() -> str:
    """Register CJK font if available. Returns font name to use."""
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

    return "Helvetica"  # fallback (no CJK support, but won't crash)


def generate_pdf(ticker: str, analysis_type: str, content: str) -> bytes:
    """Generate a PDF report and return raw bytes."""
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
    heading_style = ParagraphStyle(
        "ReportHeading", fontName=font, fontSize=13, leading=18,
        spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#16213e"),
    )
    body_style = ParagraphStyle(
        "ReportBody", fontName=font, fontSize=10, leading=16, spaceAfter=4,
    )

    story = [
        Paragraph(f"{ticker} — {analysis_type}", title_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")),
        Spacer(1, 0.3 * cm),
    ]

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.2 * cm))
            continue

        # Escape XML special characters
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if line.startswith("### ") or line.startswith("## "):
            story.append(Paragraph(safe.lstrip("# "), heading_style))
        elif line.startswith("**") and line.endswith("**"):
            story.append(Paragraph(f"<b>{safe[2:-2]}</b>", body_style))
        elif line.startswith("• ") or line.startswith("- "):
            story.append(Paragraph(f"&bull; {safe[2:]}", body_style))
        else:
            story.append(Paragraph(safe, body_style))

    doc.build(story)
    return buffer.getvalue()
