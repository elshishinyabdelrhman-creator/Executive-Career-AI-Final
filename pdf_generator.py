from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SECTION_HEADINGS = {
    "EXECUTIVE PROFILE",
    "CORE COMPETENCIES",
    "PROFESSIONAL EXPERIENCE",
    "EDUCATION",
    "LANGUAGES",
    "TECHNICAL & PROFESSIONAL SKILLS",
    "COURSES & PROFESSIONAL TRAINING",
    "PROFESSIONAL DEVELOPMENT FOCUS",
}

ROLE_RE = re.compile(r"^[A-Z][A-Z &/\-–—,.()]{5,}$")
DATE_RE = re.compile(r"(?:CURRENT|PRESENT|\b20\d{2}\b|\b19\d{2}\b)", re.I)
METRIC_RE = re.compile(r"\b(?:\d+(?:\.\d+)?%|\d+\+|ROI|AOV|KPI|KPIs|CRM|SEO|PPC|SEM|UX/UI|GCC|KSA)\b")


@dataclass(frozen=True)
class Theme:
    navy: str
    accent: str
    dark: str
    muted: str
    light: str
    name_size: float
    heading_size: float


THEMES = {
    "ATS Classic": Theme("#17365D", "#17365D", "#111111", "#555555", "#F5F7FA", 20, 11),
    "Executive Premium": Theme("#143A52", "#2E6F8E", "#111820", "#5B6570", "#EEF4F7", 25, 12),
    "Modern Corporate": Theme("#1F3B5B", "#3F6E93", "#18212B", "#626D78", "#F1F4F7", 24, 12),
    "Consulting": Theme("#202A35", "#6B7A89", "#111111", "#555555", "#F3F4F5", 23, 11.5),
    "Big Tech": Theme("#163A63", "#4377A8", "#101820", "#5A6673", "#EEF3F8", 24, 12),
    "Banking": Theme("#132B44", "#9A7B3F", "#111111", "#555555", "#F5F1E8", 24, 12),
    "GCC Executive": Theme("#1E3A3A", "#8A6A32", "#121817", "#5D6663", "#F3F1EA", 25, 12),
}


def _register_fonts() -> tuple[str, str, str]:
    candidates = [
        (
            "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
            "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf",
            "/usr/share/fonts/truetype/crosextra/Carlito-Italic.ttf",
            "Carlito",
        ),
        (
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
            "LiberationSans",
        ),
    ]
    for regular, bold, italic, family in candidates:
        if all(Path(path).exists() for path in (regular, bold, italic)):
            for suffix, path in (("", regular), ("-Bold", bold), ("-Italic", italic)):
                name = f"{family}{suffix}"
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, path))
            return family, f"{family}-Bold", f"{family}-Italic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def _split_sections(resume_text: str) -> tuple[list[str], dict[str, list[str]]]:
    lines = [line.strip() for line in resume_text.splitlines()]
    meaningful = [line for line in lines if line]
    identity = meaningful[:2]
    sections: dict[str, list[str]] = {}
    current = ""
    for line in meaningful[2:]:
        if line in SECTION_HEADINGS:
            current = line
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return identity, sections


def _safe(text: str) -> str:
    return escape(text, quote=False)


def _highlight_metrics(text: str) -> str:
    safe = _safe(text)
    return METRIC_RE.sub(lambda m: f"<b>{m.group(0)}</b>", safe)


def _first_words_bold(text: str, count: int = 2) -> str:
    safe = _highlight_metrics(text)
    words = safe.split()
    if len(words) <= count:
        return f"<b>{safe}</b>"
    return f"<b>{' '.join(words[:count])}</b> {' '.join(words[count:])}"


def _extract_title(profile_lines: list[str]) -> str:
    if not profile_lines:
        return "Executive Leader"
    text = " ".join(profile_lines)
    match = re.search(r"(?:Results-driven|Accomplished|Strategic)?\s*([^,.]{12,65}(?:Director|Leader|Executive|Manager))", text, re.I)
    return match.group(1).strip().title() if match else "Digital Commerce & Business Development Executive"


def _key_highlights(sections: dict[str, list[str]]) -> list[str]:
    profile = " ".join(sections.get("EXECUTIVE PROFILE", []))
    bullets = sections.get("PROFESSIONAL EXPERIENCE", [])
    all_text = profile + " " + " ".join(bullets)
    candidates: list[str] = []
    year = re.search(r"\b(\d{1,2}\+ years)\b", all_text, re.I)
    if year:
        candidates.append(year.group(1).title())
    elif "10+" in all_text:
        candidates.append("10+ Years Experience")
    if "MBA" in all_text or any("MBA" in x for x in sections.get("EDUCATION", [])):
        candidates.append("MBA")
    metric = re.search(r"\b\d+(?:\.\d+)?%[^.]{0,45}", all_text)
    if metric:
        candidates.append(metric.group(0).strip().rstrip(",;"))
    keyword_map = [
        ("Partnership", "Strategic Partnerships"),
        ("Lifecycle", "CRM & Lifecycle Growth"),
        ("Team", "Team Leadership"),
        ("E-Commerce", "Digital Commerce"),
        ("customer acquisition", "Customer Acquisition"),
        ("revenue", "Revenue Growth"),
    ]
    for needle, label in keyword_map:
        if needle.lower() in all_text.lower() and label not in candidates:
            candidates.append(label)
    return candidates[:6]


def _section_header(title: str, styles: dict[str, ParagraphStyle], theme: Theme):
    return [
        Spacer(1, 4),
        Paragraph(_safe(title), styles["section"]),
        HRFlowable(width="100%", thickness=0.8, color=colors.HexColor(theme.accent), spaceBefore=1, spaceAfter=5),
    ]


def _experience_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if DATE_RE.search(line) and "|" in line and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return [block for block in blocks if block]


def _job_block(block: list[str], styles: dict[str, ParagraphStyle], theme: Theme) -> list:
    date_line = block[0] if block and DATE_RE.search(block[0]) else ""
    rest = block[1:] if date_line else block[:]
    role = rest[0] if rest and ROLE_RE.match(rest[0]) else ""
    rest = rest[1:] if role else rest
    company = rest[0] if rest and not rest[0].startswith("•") else ""
    rest = rest[1:] if company else rest
    descriptor = rest[0] if rest and not rest[0].startswith("•") else ""
    rest = rest[1:] if descriptor else rest

    job_story: list = []
    if role:
        job_story.append(Paragraph(_safe(role), styles["role"]))
    if company or date_line:
        company_text = f"<b>{_safe(company)}</b>" if company else ""
        if date_line:
            company_text += (" &nbsp;&nbsp;|&nbsp;&nbsp; " if company_text else "") + _safe(date_line)
        job_story.append(Paragraph(company_text, styles["company"]))
    if descriptor:
        job_story.append(Paragraph(_safe(descriptor), styles["descriptor"]))
    for line in rest:
        if line.startswith("•"):
            job_story.append(Paragraph(_first_words_bold(line[1:].strip()), styles["bullet"], bulletText="●"))
        else:
            job_story.append(Paragraph(_safe(line), styles["body"]))
    job_story.append(Spacer(1, 5))
    return job_story


def _footer(canvas, doc, font_regular: str, theme: Theme):
    canvas.saveState()
    canvas.setFont(font_regular, 7.5)
    canvas.setFillColor(colors.HexColor(theme.muted))
    canvas.drawString(16 * mm, 8 * mm, "ABDELRHMAN EL SHISHINY")
    canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def generate_pdf(resume_text: str, theme_name: str = "Executive Premium") -> bytes:
    theme = THEMES.get(theme_name, THEMES["Executive Premium"])
    font_regular, font_bold, font_italic = _register_fonts()
    identity, sections = _split_sections(resume_text)
    name = identity[0] if identity else "Candidate Name"
    contact = identity[1] if len(identity) > 1 else ""
    title = _extract_title(sections.get("EXECUTIVE PROFILE", []))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=13 * mm,
        bottomMargin=14 * mm,
        title=f"{name} - Executive Resume",
        author=name,
    )
    base = getSampleStyleSheet()
    styles = {
        "name": ParagraphStyle("Name", parent=base["Title"], fontName=font_bold, fontSize=theme.name_size, leading=theme.name_size + 3, textColor=colors.HexColor(theme.navy), alignment=TA_LEFT, spaceAfter=1),
        "title": ParagraphStyle("Title", parent=base["Normal"], fontName=font_regular, fontSize=11.5, leading=14, textColor=colors.HexColor(theme.accent), alignment=TA_LEFT, spaceAfter=3),
        "contact": ParagraphStyle("Contact", parent=base["Normal"], fontName=font_regular, fontSize=8.5, leading=11, textColor=colors.HexColor(theme.muted), spaceAfter=5),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontName=font_bold, fontSize=theme.heading_size, leading=14, textColor=colors.HexColor(theme.navy), spaceBefore=3, spaceAfter=0),
        "profile": ParagraphStyle("Profile", parent=base["Normal"], fontName=font_regular, fontSize=9.2, leading=13, textColor=colors.HexColor(theme.dark), spaceAfter=4),
        "role": ParagraphStyle("Role", parent=base["Normal"], fontName=font_bold, fontSize=10.3, leading=12.5, textColor=colors.HexColor(theme.dark), spaceBefore=2, spaceAfter=1),
        "company": ParagraphStyle("Company", parent=base["Normal"], fontName=font_regular, fontSize=8.7, leading=11, textColor=colors.HexColor(theme.accent), spaceAfter=1),
        "descriptor": ParagraphStyle("Descriptor", parent=base["Normal"], fontName=font_italic, fontSize=8.4, leading=11, textColor=colors.HexColor(theme.muted), spaceAfter=3),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontName=font_regular, fontSize=8.6, leading=11.5, textColor=colors.HexColor(theme.dark), spaceAfter=2),
        "bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontName=font_regular, fontSize=8.55, leading=11.5, leftIndent=11, firstLineIndent=-8, bulletIndent=1, bulletFontName=font_bold, bulletFontSize=5.5, textColor=colors.HexColor(theme.dark), spaceAfter=2.4),
        "chip": ParagraphStyle("Chip", parent=base["Normal"], fontName=font_bold, fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor(theme.navy)),
        "small": ParagraphStyle("Small", parent=base["Normal"], fontName=font_regular, fontSize=8.3, leading=11, textColor=colors.HexColor(theme.dark), spaceAfter=2),
    }

    story: list = []
    story.extend([
        Paragraph(_safe(name), styles["name"]),
        Paragraph(_safe(title), styles["title"]),
        Paragraph(_safe(contact), styles["contact"]),
        HRFlowable(width="100%", thickness=1.2, color=colors.HexColor(theme.accent), spaceAfter=7),
    ])

    # PAGE 1: recruiter hook, summary, highlights, current role.
    story.extend(_section_header("EXECUTIVE SUMMARY", styles, theme))
    profile_text = " ".join(sections.get("EXECUTIVE PROFILE", []))
    story.append(Paragraph(_safe(profile_text), styles["profile"]))

    highlights = _key_highlights(sections)
    if highlights:
        story.extend(_section_header("CAREER HIGHLIGHTS", styles, theme))
        rows = []
        for i in range(0, len(highlights), 3):
            cells = []
            for item in highlights[i:i + 3]:
                cells.append(Paragraph(_safe(item), styles["chip"]))
            while len(cells) < 3:
                cells.append("")
            rows.append(cells)
        table = Table(rows, colWidths=[(A4[0] - 32 * mm - 8) / 3] * 3, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme.light)),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DEE5")),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DEE5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    exp_blocks = _experience_blocks(sections.get("PROFESSIONAL EXPERIENCE", []))
    story.extend(_section_header("CURRENT EXPERIENCE", styles, theme))
    if exp_blocks:
        story.extend(_job_block(exp_blocks[0], styles, theme))

    # PAGE 2: prior roles.
    story.append(PageBreak())
    story.extend(_section_header("EARLIER PROFESSIONAL EXPERIENCE", styles, theme))
    for block in exp_blocks[1:]:
        story.extend(_job_block(block, styles, theme))

    # PAGE 3: credentials and supporting material.
    story.append(PageBreak())
    for section in (
        "CORE COMPETENCIES",
        "TECHNICAL & PROFESSIONAL SKILLS",
        "EDUCATION",
        "LANGUAGES",
        "COURSES & PROFESSIONAL TRAINING",
        "PROFESSIONAL DEVELOPMENT FOCUS",
    ):
        lines = sections.get(section, [])
        if not lines:
            continue
        story.extend(_section_header(section, styles, theme))
        for line in lines:
            if line.startswith("•"):
                story.append(Paragraph(_highlight_metrics(line[1:].strip()), styles["bullet"], bulletText="●"))
            elif ":" in line and section == "CORE COMPETENCIES":
                label, value = line.split(":", 1)
                story.append(Paragraph(f"<b>{_safe(label)}:</b>{_safe(value)}", styles["small"]))
            else:
                story.append(Paragraph(_highlight_metrics(line), styles["small"]))

    doc.build(
        story,
        onFirstPage=lambda c, d: _footer(c, d, font_regular, theme),
        onLaterPages=lambda c, d: _footer(c, d, font_regular, theme),
    )
    return buffer.getvalue()
