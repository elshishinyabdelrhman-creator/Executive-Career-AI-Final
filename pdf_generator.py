from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

HEADINGS = {
    "EXECUTIVE PROFILE", "CORE COMPETENCIES", "PROFESSIONAL EXPERIENCE",
    "EDUCATION", "LANGUAGES", "TECHNICAL & PROFESSIONAL SKILLS",
    "COURSES & PROFESSIONAL TRAINING", "PROFESSIONAL DEVELOPMENT FOCUS",
}


def generate_pdf(resume_text: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Tailored Executive Resume",
    )
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "Name", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=16,
        leading=19, alignment=TA_CENTER, spaceAfter=4,
    )
    contact_style = ParagraphStyle(
        "Contact", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5,
        leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#444444"), spaceAfter=7,
    )
    heading_style = ParagraphStyle(
        "Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10,
        leading=13, spaceBefore=7, spaceAfter=4, borderWidth=0, textColor=colors.HexColor("#17365D"),
    )
    role_style = ParagraphStyle(
        "Role", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5,
        leading=12, spaceBefore=3, spaceAfter=1,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5,
        leading=11.5, spaceAfter=2,
    )
    bullet_style = ParagraphStyle(
        "Bullet", parent=body_style, leftIndent=10, firstLineIndent=-7, bulletIndent=2,
        spaceAfter=2,
    )

    lines = [line.strip() for line in resume_text.splitlines()]
    story = []
    meaningful = [line for line in lines if line]
    first_line = meaningful[0] if meaningful else ""
    second_line = meaningful[1] if len(meaningful) > 1 else ""
    used_name = used_contact = False

    for line in lines:
        if not line:
            story.append(Spacer(1, 2.5))
            continue
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if line == first_line and not used_name and line not in HEADINGS:
            story.append(Paragraph(safe, name_style)); used_name = True; continue
        if line == second_line and not used_contact and line not in HEADINGS:
            story.append(Paragraph(safe, contact_style)); used_contact = True; continue
        if line in HEADINGS:
            story.append(Paragraph(safe, heading_style)); continue
        if line.startswith("•"):
            story.append(Paragraph(safe[1:].strip(), bullet_style, bulletText="•")); continue
        if line.isupper() and len(line) < 95:
            story.append(Paragraph(safe, role_style)); continue
        story.append(Paragraph(safe, body_style))

    doc.build(story)
    return buffer.getvalue()
