from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

NAVY = "17365D"
DARK = "111111"
GRAY = "E7E6E6"
MID_GRAY = "666666"
WHITE = "FFFFFF"
SECTION_NAMES = {
    "PROFESSIONAL SUMMARY", "SELECTED CAREER HIGHLIGHTS",
    "CORE LEADERSHIP & TECHNICAL EXPERTISE", "PROFESSIONAL EXPERIENCE",
    "EARLIER PROFESSIONAL EXPERIENCE", "EDUCATION & PROFESSIONAL DEVELOPMENT",
    "TECHNICAL SKILLS", "CERTIFICATIONS", "EDUCATION",
}


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _cell_margins(cell, top=55, start=80, bottom=55, end=80) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _bottom_border(paragraph, color=NAVY, size="8") -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        p_pr.append(borders)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)


def _page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("Page ")
    run.font.name = "Arial"
    run.font.size = Pt(8)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    paragraph._p.append(fld)


def _add_highlighted_text(paragraph, text: str, font_size=9.2) -> None:
    pattern = re.compile(
        r"((?:₹|\$|€|£)\s?\d[\d,.]*(?:\s?(?:M|B|K|million|billion|crore|lakh))?|"
        r"\b\d+(?:\.\d+)?%|\b\d+\+?\s+(?:years?|users?|applications?|countries?|"
        r"projects?|programs?|people|employees|members|markets?|releases?|defects?)\b)",
        re.I,
    )
    last = 0
    for match in pattern.finditer(text):
        if match.start() > last:
            run = paragraph.add_run(text[last:match.start()])
            run.font.name = "Arial"; run.font.size = Pt(font_size)
        run = paragraph.add_run(match.group(0))
        run.bold = True; run.font.name = "Arial"; run.font.size = Pt(font_size); run.font.color.rgb = RGBColor.from_string(NAVY)
        last = match.end()
    if last < len(text):
        run = paragraph.add_run(text[last:])
        run.font.name = "Arial"; run.font.size = Pt(font_size)


def _role_band(document: Document, line: str) -> None:
    parts = [part.strip() for part in line.split("|")]
    left = " | ".join(parts[:-1]) if len(parts) > 1 else line
    right = parts[-1] if len(parts) > 1 else ""
    table = document.add_table(rows=1, cols=2)
    table.autofit = False
    table.columns[0].width = Inches(5.85)
    table.columns[1].width = Inches(1.15)
    for cell in table.rows[0].cells:
        _shade(cell, GRAY); _cell_margins(cell); cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p1 = table.cell(0, 0).paragraphs[0]
    p1.paragraph_format.space_after = Pt(0)
    r1 = p1.add_run(left)
    r1.bold = True; r1.font.name = "Arial"; r1.font.size = Pt(9.2); r1.font.color.rgb = RGBColor.from_string(DARK)
    p2 = table.cell(0, 1).paragraphs[0]
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT; p2.paragraph_format.space_after = Pt(0)
    r2 = p2.add_run(right)
    r2.bold = True; r2.font.name = "Arial"; r2.font.size = Pt(8.8); r2.font.color.rgb = RGBColor.from_string(DARK)


def build_docx(resume_text: str) -> bytes:
    document = Document()
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.48)
    section.bottom_margin = Inches(0.48)
    section.left_margin = Inches(0.58)
    section.right_margin = Inches(0.58)
    section.header_distance = Inches(0.2)
    section.footer_distance = Inches(0.2)
    _page_number(section.footer.paragraphs[0])

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(9.2)
    normal.font.color.rgb = RGBColor.from_string(DARK)
    normal.paragraph_format.space_after = Pt(2.2)
    normal.paragraph_format.line_spacing = 1.04

    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    section_name = ""
    header_count = 0
    for line in lines:
        upper = line.upper().rstrip(":")
        if upper in {"NAME", "HEADLINE", "POSITIONING LINE", "CONTACT"}:
            continue
        if upper in SECTION_NAMES:
            section_name = upper
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(5)
            paragraph.paragraph_format.space_after = Pt(2.5)
            run = paragraph.add_run(upper)
            run.bold = True; run.font.name = "Arial"; run.font.size = Pt(9.4); run.font.color.rgb = RGBColor.from_string(NAVY)
            _bottom_border(paragraph)
            continue

        if header_count == 0:
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.space_after = Pt(0)
            run = paragraph.add_run(line.upper())
            run.bold = True; run.font.name = "Arial"; run.font.size = Pt(18); run.font.color.rgb = RGBColor.from_string(DARK)
            header_count += 1; continue
        if header_count == 1:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(1)
            run = paragraph.add_run(line.upper())
            run.bold = True; run.font.name = "Arial"; run.font.size = Pt(11.2); run.font.color.rgb = RGBColor.from_string(NAVY)
            header_count += 1; continue
        if header_count == 2:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(2)
            run = paragraph.add_run(line)
            run.bold = True; run.font.name = "Arial"; run.font.size = Pt(9.1); run.font.color.rgb = RGBColor.from_string(MID_GRAY)
            header_count += 1; continue
        if header_count == 3:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(4)
            run = paragraph.add_run(line)
            run.font.name = "Arial"; run.font.size = Pt(8.4); run.font.color.rgb = RGBColor.from_string(DARK)
            _bottom_border(paragraph, color="808080", size="4")
            header_count += 1; continue

        is_role = section_name == "PROFESSIONAL EXPERIENCE" and re.search(r"\b(?:19|20)\d{2}\b|\bPresent\b", line, re.I) and "|" in line
        if is_role:
            _role_band(document, line)
            continue

        if line.startswith(("- ", "• ", "▪ ", "* ")):
            text = line[2:].strip()
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.16)
            paragraph.paragraph_format.first_line_indent = Inches(-0.12)
            paragraph.paragraph_format.space_after = Pt(1.6)
            square = paragraph.add_run("▪ ")
            square.font.name = "Arial"; square.font.size = Pt(7.8); square.font.color.rgb = RGBColor.from_string(NAVY)
            _add_highlighted_text(paragraph, text)
        else:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(2)
            _add_highlighted_text(paragraph, line)

    output = BytesIO()
    document.save(output)
    return output.getvalue()
