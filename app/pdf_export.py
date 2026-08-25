"""
PDF Export — converts the final report (markdown-ish text from the Writer
+ citations.py) into a PDF via ReportLab (Platypus: SimpleDocTemplate +
Paragraph + Spacer + ListFlowable), per this environment's own PDF-creation
guidance. Optionally embeds chart images in a "Data Visualizations"
section, placed just before the References/Works Cited section if one
exists, or at the end otherwise.

The markdown handling here is a small, purpose-built subset parser, not a
general one — it only needs to handle what the Writer's prompt actually
asks it to produce: #/##/### headings, plain paragraphs, "- " bullets,
"N. " numbered reference lines, and **bold**/*italic* inline emphasis. A
full CommonMark parser would be overkill for content whose shape is
already controlled by our own prompt.
"""

import re

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

REFERENCES_HEADINGS = {"references", "works cited"}

_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def _inline_markup_to_reportlab(text: str) -> str:
    """**bold** / *italic* -> ReportLab's <b>/<i> tags. Escapes literal
    &, <, > first so they can't be misread as markup or break the XML
    ReportLab expects inside a Paragraph."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = _BOLD_PATTERN.sub(r"<b>\1</b>", text)
    text = _ITALIC_PATTERN.sub(r"<i>\1</i>", text)
    return text


def _build_styles():
    styles = getSampleStyleSheet()
    styles["Heading1"].spaceBefore = 18
    styles["Heading1"].spaceAfter = 10
    styles["Heading2"].spaceBefore = 14
    styles["Heading2"].spaceAfter = 8
    styles["Heading3"].spaceBefore = 10
    styles["Heading3"].spaceAfter = 6
    styles["Normal"].leading = 15
    return styles


def markdown_to_flowables(text: str, styles) -> list:
    flowables: list = []
    bullet_buffer: list[str] = []

    def flush_bullets():
        if bullet_buffer:
            items = [ListItem(Paragraph(_inline_markup_to_reportlab(b), styles["Normal"])) for b in bullet_buffer]
            flowables.append(ListFlowable(items, bulletType="bullet", leftIndent=18))
            flowables.append(Spacer(1, 8))
            bullet_buffer.clear()

    for raw_line in text.split("\n"):
        line = raw_line.strip()

        if not line:
            flush_bullets()
            continue
        if line.startswith("### "):
            flush_bullets()
            flowables.append(Paragraph(_inline_markup_to_reportlab(line[4:]), styles["Heading3"]))
        elif line.startswith("## "):
            flush_bullets()
            flowables.append(Paragraph(_inline_markup_to_reportlab(line[3:]), styles["Heading2"]))
        elif line.startswith("# "):
            flush_bullets()
            flowables.append(Paragraph(_inline_markup_to_reportlab(line[2:]), styles["Heading1"]))
        elif line.startswith("- ") or line.startswith("* "):
            bullet_buffer.append(line[2:])
        elif re.match(r"^\d+\.\s", line):
            # Numbered reference lines — plain paragraphs, not a restarted
            # <ol>, since they carry their own [N]-matching number already.
            flush_bullets()
            flowables.append(Paragraph(_inline_markup_to_reportlab(line), styles["Normal"]))
            flowables.append(Spacer(1, 4))
        else:
            flush_bullets()
            flowables.append(Paragraph(_inline_markup_to_reportlab(line), styles["Normal"]))
            flowables.append(Spacer(1, 6))

    flush_bullets()
    return flowables


def _find_references_index(flowables: list) -> int:
    """Index where the References/Works Cited heading starts, so charts
    land just before it. Falls back to the end of the document if there
    isn't one (e.g. the no-Gemini fallback draft has no citations)."""
    for i, flowable in enumerate(flowables):
        if isinstance(flowable, Paragraph) and flowable.getPlainText().strip().lower() in REFERENCES_HEADINGS:
            return i
    return len(flowables)


def generate_pdf(
    title: str,
    report_text: str,
    output_path: str,
    chart_image_paths: list[str] | None = None,
) -> str:
    """Renders `report_text` to a PDF at output_path. Returns output_path."""
    styles = _build_styles()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=LETTER,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        title=title,
    )

    story = [Paragraph(_inline_markup_to_reportlab(title), styles["Title"]), Spacer(1, 16)]
    body = markdown_to_flowables(report_text, styles)

    if chart_image_paths:
        insert_at = _find_references_index(body)
        chart_block = [Paragraph("Data Visualizations", styles["Heading2"]), Spacer(1, 8)]
        for path in chart_image_paths:
            chart_block.append(Image(path, width=5 * inch, height=3.3 * inch))
            chart_block.append(Spacer(1, 12))
        body = body[:insert_at] + chart_block + body[insert_at:]

    story.extend(body)
    doc.build(story)
    return output_path
