"""Generate a PDF version of the solver guide markdown."""

from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import ListFlowable, ListItem, Paragraph, Preformatted, SimpleDocTemplate, Spacer

REPO_ROOT = Path(__file__).resolve().parents[3]
SOLVER_GUIDE_PATH = REPO_ROOT / "solver.md"
NEURON_FOOTER_PATH = REPO_ROOT / "frontend" / "public" / "neuron-footer.jpg"
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
ORDERED_LIST_RE = re.compile(r"^\d+\.\s+")


def build_solver_guide_pdf() -> bytes:
    """Render solver.md into a branded PDF document."""

    if not SOLVER_GUIDE_PATH.exists():
        raise FileNotFoundError(f"Solver guide source tidak ditemukan: {SOLVER_GUIDE_PATH}")

    markdown = SOLVER_GUIDE_PATH.read_text(encoding="utf-8")
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=30 * mm,
        title="VRP Planner Solver Guide",
        author="VRP Planner",
    )
    styles = _build_styles()
    story = _build_story(markdown, styles)
    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()


def _build_styles() -> dict[str, ParagraphStyle]:
    stylesheet = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "SolverGuideBody",
            parent=stylesheet["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#334155"),
            spaceAfter=0,
        ),
        "h1": ParagraphStyle(
            "SolverGuideH1",
            parent=stylesheet["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "SolverGuideH2",
            parent=stylesheet["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=21,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=6,
            spaceAfter=4,
        ),
        "h3": ParagraphStyle(
            "SolverGuideH3",
            parent=stylesheet["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=4,
            spaceAfter=2,
        ),
        "code": ParagraphStyle(
            "SolverGuideCode",
            parent=stylesheet["Code"],
            fontName="Courier",
            fontSize=9,
            leading=13,
            leftIndent=10,
            rightIndent=10,
            borderPadding=8,
            borderRadius=6,
            backColor=colors.HexColor("#f8fafc"),
            borderColor=colors.HexColor("#dbe4ee"),
            borderWidth=0.7,
            borderLeft=True,
            borderRight=True,
            borderTop=True,
            borderBottom=True,
            textColor=colors.HexColor("#0f172a"),
        ),
    }


def _build_story(markdown: str, styles: dict[str, ParagraphStyle]) -> list[object]:
    story: list[object] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []
    list_kind: str | None = None
    code_lines: list[str] = []
    in_code_fence = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        text = " ".join(part.strip() for part in paragraph_lines).strip()
        paragraph_lines = []
        if not text:
            return
        story.append(Paragraph(_format_inline_markup(text), styles["body"]))
        story.append(Spacer(1, 4))

    def flush_list() -> None:
        nonlocal list_items, list_kind
        if not list_items or not list_kind:
            list_items = []
            list_kind = None
            return

        flowable_items = [
            ListItem(Paragraph(_format_inline_markup(item), styles["body"]), spaceAfter=2) for item in list_items
        ]
        story.append(
            ListFlowable(
                flowable_items,
                bulletType="1" if list_kind == "ordered" else "bullet",
                start="1",
                bulletFontName="Helvetica",
                bulletFontSize=9,
                leftIndent=16,
            )
        )
        story.append(Spacer(1, 4))
        list_items = []
        list_kind = None

    def flush_code() -> None:
        nonlocal code_lines
        if not code_lines:
            return
        story.append(Preformatted("\n".join(code_lines), styles["code"]))
        story.append(Spacer(1, 6))
        code_lines = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code_fence:
                flush_code()
            in_code_fence = not in_code_fence
            continue

        if in_code_fence:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            flush_code()
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            flush_code()
            story.append(Paragraph(_format_inline_markup(stripped[2:].strip()), styles["h1"]))
            story.append(Spacer(1, 4))
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            flush_code()
            story.append(Paragraph(_format_inline_markup(stripped[3:].strip()), styles["h2"]))
            story.append(Spacer(1, 2))
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            flush_code()
            story.append(Paragraph(_format_inline_markup(stripped[4:].strip()), styles["h3"]))
            story.append(Spacer(1, 2))
            continue

        if stripped.startswith("- "):
            flush_paragraph()
            flush_code()
            item = stripped[2:].strip()
            if list_kind not in {None, "unordered"}:
                flush_list()
            list_kind = "unordered"
            list_items.append(item)
            continue

        if ORDERED_LIST_RE.match(stripped):
            flush_paragraph()
            flush_code()
            item = ORDERED_LIST_RE.sub("", stripped, count=1).strip()
            if list_kind not in {None, "ordered"}:
                flush_list()
            list_kind = "ordered"
            list_items.append(item)
            continue

        is_standalone_code = stripped.startswith("`") and stripped.endswith("`") and stripped.count("`") >= 2
        if is_standalone_code:
            flush_paragraph()
            flush_list()
            flush_code()
            code_lines.append(stripped[1:-1])
            flush_code()
            continue

        flush_list()
        flush_code()
        paragraph_lines.append(stripped)

    flush_paragraph()
    flush_list()
    flush_code()
    return story


def _format_inline_markup(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in INLINE_CODE_RE.finditer(text):
        parts.append(escape(text[cursor:match.start()]))
        parts.append(f'<font name="Courier">{escape(match.group(1))}</font>')
        cursor = match.end()
    parts.append(escape(text[cursor:]))
    return "".join(parts)


def _draw_footer(canvas, doc) -> None:
    footer_top = 22 * mm
    footer_image = _load_footer_image()
    page_width, _ = doc.pagesize

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d8e0ea"))
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, footer_top, page_width - doc.rightMargin, footer_top)

    canvas.setFillColor(colors.HexColor("#0a72bb"))
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(doc.leftMargin, 16 * mm, "Powered by NEURON")

    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(
        doc.leftMargin,
        11.5 * mm,
        "Engine optimisasi untuk perencanaan rute, armada, dan orkestrasi dispatch.",
    )
    canvas.drawRightString(page_width - doc.rightMargin, 16 * mm, f"Halaman {doc.page}")

    if footer_image is not None:
        image_width = 34 * mm
        image_height = image_width * footer_image.getSize()[1] / footer_image.getSize()[0]
        canvas.drawImage(
            footer_image,
            page_width - doc.rightMargin - image_width,
            6 * mm,
            width=image_width,
            height=image_height,
            preserveAspectRatio=True,
            mask="auto",
        )

    canvas.restoreState()


def _load_footer_image() -> ImageReader | None:
    if not NEURON_FOOTER_PATH.exists():
        return None
    return ImageReader(str(NEURON_FOOTER_PATH))
