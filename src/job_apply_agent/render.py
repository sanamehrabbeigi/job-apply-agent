"""Render a resume written in a small Markdown dialect into a polished, ATS-friendly .docx.

The layout is a classic single-column resume:
centered name and contact line, ruled uppercase section headings, entry titles with
right-aligned dates, italic organization lines, and compact bullets.

Markdown dialect (what the tailoring agent is asked to produce):

    # Full Name
    email | phone | linkedin.com/in/... | github.com/...

    ## Section Title
    A plain paragraph (e.g. the summary).

    ### Entry Title | Dates
    *Organization | Location*
    - Bullet with **bold** and *italic* text.

Anything else is rendered as a normal paragraph, so hand edits never break rendering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph


@dataclass
class ResumeStyle:
    font: str = "Calibri"
    body_size: float = 10
    name_size: float = 16
    heading_size: float = 11
    contact_size: float = 9.5
    margin_left: float = 0.45  # inches
    margin_right: float = 0.45
    margin_top: float = 0.45
    margin_bottom: float = 0.45
    link_color: RGBColor = RGBColor(0x1F, 0x4E, 0x99)


def style_from_reference(reference_docx: str | Path | None) -> ResumeStyle:
    """Take page margins from the user's own resume so the length and density feel familiar."""
    style = ResumeStyle()
    if not reference_docx or Path(reference_docx).suffix.lower() != ".docx":
        return style
    try:
        section = Document(str(reference_docx)).sections[0]
    except Exception:  # A broken reference file should never block rendering.
        return style
    for attr, value in (
        ("margin_left", section.left_margin),
        ("margin_right", section.right_margin),
        ("margin_top", section.top_margin),
        ("margin_bottom", section.bottom_margin),
    ):
        if value is not None and 0.2 <= value.inches <= 1.5:
            setattr(style, attr, round(value.inches, 2))
    return style


def render_resume_docx(
    markdown: str,
    out_path: str | Path,
    *,
    reference_docx: str | Path | None = None,
    style: ResumeStyle | None = None,
) -> Path:
    style = style or style_from_reference(reference_docx)
    doc = Document()
    _setup_document(doc, style)
    text_width = doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin

    seen_name = False
    in_header = True  # lines between the name and the first section are contact lines
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or re.fullmatch(r"[-*_=]{3,}", line):
            continue

        if line.startswith("# ") and not seen_name:
            seen_name = True
            _name(doc, line[2:].strip(), style)
        elif line.startswith("## "):
            in_header = False
            _section_heading(doc, line[3:].strip(), style)
        elif line.startswith("### "):
            in_header = False
            _entry_heading(doc, line[4:].strip(), style, text_width)
        elif in_header and seen_name:
            _contact(doc, line, style)
        elif re.match(r"^[-*•]\s+", line):
            _bullet(doc, re.sub(r"^[-*•]\s+", "", line), style)
        elif _is_fully_italic(line):
            _subtitle(doc, line[1:-1].strip(), style)
        else:
            p = doc.add_paragraph()
            _fmt(p, after=2)
            _add_inline(p, line, style)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


# --- building blocks -------------------------------------------------------------------


def _setup_document(doc: Document, style: ResumeStyle) -> None:
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.left_margin = Inches(style.margin_left)
    section.right_margin = Inches(style.margin_right)
    section.top_margin = Inches(style.margin_top)
    section.bottom_margin = Inches(style.margin_bottom)

    normal = doc.styles["Normal"]
    normal.font.name = style.font
    normal.font.size = Pt(style.body_size)
    rpr = normal.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), style.font)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.0


def _fmt(p: Paragraph, before: float = 0, after: float = 0) -> None:
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)


def _name(doc: Document, text: str, style: ResumeStyle) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _fmt(p, after=1)
    run = p.add_run(_strip_md(text).upper())
    run.bold = True
    run.font.size = Pt(style.name_size)


def _contact(doc: Document, text: str, style: ResumeStyle) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _fmt(p, after=2)
    parts = [part.strip() for part in re.split(r"\s+\|\s+", _strip_md(text)) if part.strip()]
    for i, part in enumerate(parts):
        if i:
            sep = p.add_run("  |  ")
            sep.font.size = Pt(style.contact_size)
        url = _url_for(part)
        if url:
            _add_hyperlink(p, part, url, style)
        else:
            run = p.add_run(part)
            run.font.size = Pt(style.contact_size)


def _section_heading(doc: Document, text: str, style: ResumeStyle) -> None:
    p = doc.add_paragraph()
    _fmt(p, before=7, after=3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(_strip_md(text).upper())
    run.bold = True
    run.font.size = Pt(style.heading_size)
    _bottom_border(p)


def _entry_heading(doc: Document, text: str, style: ResumeStyle, text_width) -> None:
    title, date = _split_date(text)
    p = doc.add_paragraph()
    _fmt(p, before=3)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.tab_stops.add_tab_stop(text_width, WD_TAB_ALIGNMENT.RIGHT)
    _add_inline(p, title, style, bold=True)
    if date:
        run = p.add_run("\t" + _strip_md(date))
        run.italic = True


def _subtitle(doc: Document, text: str, style: ResumeStyle) -> None:
    p = doc.add_paragraph()
    _fmt(p, after=1)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(_strip_md(text))
    run.italic = True


def _bullet(doc: Document, text: str, style: ResumeStyle) -> None:
    p = doc.add_paragraph(style="List Bullet")
    _fmt(p, after=1)
    p.paragraph_format.left_indent = Inches(0.22)
    p.paragraph_format.first_line_indent = Inches(-0.16)
    _add_inline(p, text, style)


def _bottom_border(p: Paragraph) -> None:
    ppr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "000000")):
        bottom.set(qn(key), value)
    borders.append(bottom)
    ppr.append(borders)


def _add_hyperlink(p: Paragraph, text: str, url: str, style: ResumeStyle) -> None:
    r_id = p.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), str(style.link_color))
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), str(int(style.contact_size * 2)))
    rpr.extend([color, size])
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    p._p.append(link)


# --- text helpers ----------------------------------------------------------------------

_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def _strip_md(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = text.replace("\\|", "|").replace("\\", "")
    return re.sub(r"\*+", "", text).strip()


def _add_inline(p: Paragraph, text: str, style: ResumeStyle, bold: bool = False) -> None:
    text = _LINK.sub(r"\1", text).replace("\\|", "|")
    for chunk in _INLINE.split(text):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            run = p.add_run(chunk[2:-2])
            run.bold = True
        elif chunk.startswith("*") and chunk.endswith("*") and len(chunk) > 1:
            run = p.add_run(chunk[1:-1])
            run.italic = True
            run.bold = bold or None
        else:
            run = p.add_run(chunk)
            run.bold = bold or None


def _is_fully_italic(line: str) -> bool:
    return bool(re.fullmatch(r"\*[^*].*[^*]\*|\*[^*]\*", line)) and not line.startswith("**")


def _split_date(text: str) -> tuple[str, str]:
    """'Data Analyst | 01/2026 – Present' -> ('Data Analyst', '01/2026 – Present')."""
    if " | " in text:
        title, date = text.rsplit(" | ", 1)
        return title.strip(), date.strip()
    return text, ""


def _url_for(part: str) -> str | None:
    if re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", part):
        return f"mailto:{part}"
    if re.match(r"^(https?://|www\.)", part, re.I):
        return part if part.lower().startswith("http") else f"https://{part}"
    if re.match(r"^(linkedin\.com|github\.com|[\w-]+\.(github\.io|dev|me|io))/?", part, re.I):
        return f"https://{part}"
    return None
