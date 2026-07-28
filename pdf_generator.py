from __future__ import annotations

import html
import io
import re
from typing import Callable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

PROFILE = {
    "name": "Abdelrhman El Shishiny",
    "phone": "(+966) 577534641",
    "email": "elshishinyabdelrhman@gmail.com",
    "address": "Jeddah, Saudi Arabia",
}

SECTION_NAMES = {
    "EXECUTIVE PROFILE",
    "STRATEGIC COMPETENCIES",
    "WORK EXPERIENCE",
    "EDUCATION & TRAINING",
    "LANGUAGE SKILLS",
    "KEY SKILLS",
    "RELEVANT PROFESSIONAL DEVELOPMENT",
}

DATE_PATTERN = re.compile(
    r"("
    r"\d{2}/\d{2}/\d{4}\s*-\s*CURRENT"
    r"|CURRENT"
    r"|\d{4}\s*-\s*\d{2}/\d{4}"
    r"|\d{4}\s*-\s*\d{4}"
    r")",
    re.IGNORECASE,
)


def _escape(value: str) -> str:
    return html.escape(value or "", quote=False)


def _add_page_number(canvas, doc) -> None:
    canvas.saveState()
    page = canvas.getPageNumber()
    text = f"Page {page}"

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#666666"))

    page_width, _ = A4
    width = stringWidth(text, "Helvetica", 7.5)
    canvas.drawString(page_width - doc.rightMargin - width, 11 * mm, text)
    canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "name": ParagraphStyle(
            "name",
            fontName="Helvetica-Bold",
            fontSize=18.5,
            leading=21,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111111"),
            spaceAfter=3,
        ),
        "contact": ParagraphStyle(
            "contact",
            fontName="Helvetica",
            fontSize=8.3,
            leading=10.5,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#333333"),
            spaceAfter=7,
        ),
        "section": ParagraphStyle(
            "section",
            fontName="Helvetica-Bold",
            fontSize=10.8,
            leading=13,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#111111"),
            keepWithNext=True,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "date": ParagraphStyle(
            "date",
            fontName="Helvetica-Bold",
            fontSize=9.1,
            leading=11.5,
            textColor=colors.HexColor("#111111"),
            keepWithNext=True,
            spaceBefore=5.5,
            spaceAfter=1.5,
        ),
        "role": ParagraphStyle(
            "role",
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=11.4,
            textColor=colors.HexColor("#111111"),
            keepWithNext=True,
            spaceAfter=1,
        ),
        "company": ParagraphStyle(
            "company",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11.2,
            textColor=colors.HexColor("#222222"),
            keepWithNext=True,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=8.8,
            leading=11.2,
            textColor=colors.HexColor("#111111"),
            alignment=TA_LEFT,
            allowWidows=0,
            allowOrphans=0,
            spaceAfter=3,
        ),
        "positioning": ParagraphStyle(
            "positioning",
            fontName="Helvetica-Oblique",
            fontSize=8.6,
            leading=11,
            textColor=colors.HexColor("#333333"),
            allowWidows=0,
            allowOrphans=0,
            spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName="Helvetica",
            fontSize=8.65,
            leading=11.15,
            textColor=colors.HexColor("#111111"),
            leftIndent=11,
            firstLineIndent=-8,
            bulletIndent=0,
            allowWidows=0,
            allowOrphans=0,
            spaceAfter=2.3,
        ),
        "skills": ParagraphStyle(
            "skills",
            fontName="Helvetica",
            fontSize=8.65,
            leading=11.2,
            textColor=colors.HexColor("#111111"),
            allowWidows=0,
            allowOrphans=0,
            spaceAfter=3,
        ),
    }


def _header_story(styles: dict[str, ParagraphStyle]) -> list:
    contact_line = (
        f'{_escape(PROFILE["phone"])}'
        f' | {_escape(PROFILE["email"])}'
        f' | {_escape(PROFILE["address"])}'
    )

    return [
        Paragraph(_escape(PROFILE["name"]), styles["name"]),
        Paragraph(contact_line, styles["contact"]),
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=colors.HexColor("#222222"),
            spaceBefore=0,
            spaceAfter=5,
        ),
    ]


def _is_role_heading(line: str) -> bool:
    if not line.isupper():
        return False

    if line in SECTION_NAMES:
        return False

    if len(line) > 100:
        return False

    role_words = (
        "DIRECTOR",
        "MANAGER",
        "EXECUTIVE",
        "HEAD",
        "OFFICER",
        "LEAD",
        "CONSULTANT",
        "SPECIALIST",
        "RELATIONSHIP",
    )
    return any(word in line for word in role_words)


def _is_company_line(line: str) -> bool:
    lowered = line.casefold()
    company_markers = (
        "trading co.",
        "bank",
        "spelenzo",
        "ship hero",
        "company",
        "group",
        "limited",
        "ltd",
        "inc.",
        "llc",
    )
    return any(marker in lowered for marker in company_markers)


def generate_pdf(text: str) -> bytes:
    """
    Convert the structured plain-text resume into an ATS-readable PDF.

    The PDF uses:
    - Standard fonts
    - No tables or text boxes
    - Selectable text
    - Consistent bullets
    - Page numbers
    """
    if not str(text or "").strip():
        raise ValueError("Resume text is empty.")

    buffer = io.BytesIO()
    styles = _styles()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=17 * mm,
        title=f'{PROFILE["name"]} Resume',
        author=PROFILE["name"],
        subject="Professional Resume",
    )

    story = _header_story(styles)
    lines = [line.strip() for line in str(text).splitlines()]

    previous_nonempty = ""
    current_section = ""
    index = 0

    while index < len(lines):
        line = lines[index]

        if not line:
            story.append(Spacer(1, 1.5))
            index += 1
            continue

        upper = line.upper()
        escaped = _escape(line)

        if upper in SECTION_NAMES:
            current_section = upper
            story.extend(
                [
                    Spacer(1, 2),
                    Paragraph(upper, styles["section"]),
                    HRFlowable(
                        width="100%",
                        thickness=0.3,
                        color=colors.HexColor("#888888"),
                        spaceBefore=0,
                        spaceAfter=3,
                    ),
                ]
            )

        elif DATE_PATTERN.search(line):
            block = [Paragraph(escaped, styles["date"])]

            lookahead = index + 1
            while lookahead < len(lines) and not lines[lookahead]:
                lookahead += 1

            if lookahead < len(lines) and _is_role_heading(lines[lookahead]):
                block.append(Paragraph(_escape(lines[lookahead]), styles["role"]))
                index = lookahead

                lookahead = index + 1
                while lookahead < len(lines) and not lines[lookahead]:
                    lookahead += 1

                if lookahead < len(lines) and _is_company_line(lines[lookahead]):
                    block.append(Paragraph(_escape(lines[lookahead]), styles["company"]))
                    index = lookahead

            story.append(KeepTogether(block))

        elif _is_role_heading(line):
            story.append(Paragraph(escaped, styles["role"]))

        elif line.startswith("•"):
            bullet_text = _escape(line[1:].strip())
            story.append(
                Paragraph(
                    f"&#8226;&nbsp;{bullet_text}",
                    styles["bullet"],
                )
            )

        elif _is_company_line(line):
            story.append(Paragraph(escaped, styles["company"]))

        elif (
            previous_nonempty.startswith("Dabouq Trading Co.")
            or (
                current_section == "WORK EXPERIENCE"
                and not previous_nonempty.startswith("•")
                and line.lower().startswith(
                    (
                        "leading ",
                        "driving ",
                        "directing ",
                        "building ",
                        "overseeing ",
                    )
                )
            )
        ):
            story.append(Paragraph(escaped, styles["positioning"]))

        elif current_section == "KEY SKILLS":
            story.append(Paragraph(escaped, styles["skills"]))

        else:
            story.append(Paragraph(escaped, styles["body"]))

        previous_nonempty = line
        index += 1

    doc.build(
        story,
        onFirstPage=_add_page_number,
        onLaterPages=_add_page_number,
    )

    buffer.seek(0)
    return buffer.getvalue()
