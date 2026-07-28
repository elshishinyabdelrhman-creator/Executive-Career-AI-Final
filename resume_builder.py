from __future__ import annotations

import re
from typing import Any, Iterable


CURRENT_ROLE_DATE = "13/01/2025 - CURRENT"
CURRENT_ROLE_LOCATION = "JEDDAH, SAUDI ARABIA"
CURRENT_ROLE_TITLE = "MARKETING & BUSINESS DEVELOPMENT DIRECTOR"
CURRENT_COMPANY = "Dabouq Trading Co."

OLDER_EXPERIENCE = """
2020 - 01/2025 | JEDDAH, SAUDI ARABIA
MARKETING AND BUSINESS DEVELOPMENT DIRECTOR
Hero / Spelenzo
• Developed integrated social media, digital marketing, and business development strategies across client portfolios.
• Built influencer and media partnerships that expanded brand visibility and strengthened market positioning.
• Directed multi-channel campaigns across SEO, PPC, paid social, and email to drive lead generation and revenue growth.
• Partnered with board members and senior stakeholders on budgets, operating priorities, and commercial decisions.
• Negotiated contracts and pricing agreements while improving workflow efficiency through marketing automation.
• Led team performance, coaching, and client relationship development to exceed sales and delivery targets.

2013 - 2020 | JEDDAH, SAUDI ARABIA
SALES AND MARKETING EXECUTIVE
Spelenzo
• Drove GCC revenue growth through display advertising, PPC, retargeting, paid social, and conversion-led campaigns.
• Planned and measured experiments across SEO/SEM, email, social, web, and display channels.
• Managed brand reputation and content performance while identifying optimization and testing opportunities.
• Developed targeted promotions and segmented campaigns to increase lead generation and revenue.

2009 - 2013 | CAIRO, EGYPT
SENIOR RELATIONSHIP MANAGER
Citi Bank
• Managed high-value client relationships and supported business development initiatives within the banking sector.
• Strengthened client retention through consultative service, portfolio support, and relationship management.

2006 - 2009 | CAIRO, EGYPT
RELATIONSHIP MANAGER
Citi Bank
• Supported client relationship management, banking operations, and portfolio servicing.
""".strip()

EDUCATION_AND_LANGUAGES = """
EDUCATION & TRAINING
MASTER OF BUSINESS ADMINISTRATION (MBA) - UNIVERSITY OF CUMBRIA
BACHELOR OF COMMERCE, BUSINESS MANAGEMENT - AIN SHAMS UNIVERSITY

LANGUAGE SKILLS
Arabic: Native
English: C2
German: B2
French: B2
""".strip()


def clean(value: Any) -> str:
    """Normalize generated text while preserving sentence punctuation."""
    text = str(value or "").strip()
    text = re.sub(r"^[\s•\-*\d.)]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_heading(value: Any, fallback: str = "") -> str:
    text = clean(value) or fallback
    text = re.sub(r"[()]+", "", text)
    return text.strip(" -|")


def unique_items(items: Iterable[Any], limit: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    for item in items or []:
        text = clean(item)
        key = text.casefold()

        if not text or key in seen:
            continue

        seen.add(key)
        output.append(text)

        if limit and len(output) >= limit:
            break

    return output


def bullets(items: Iterable[Any], limit: int | None = None) -> str:
    return "\n".join(f"• {item}" for item in unique_items(items, limit=limit))


def competency_lines(items: Iterable[Any]) -> str:
    lines: list[str] = []

    for item in unique_items(items, limit=7):
        if ":" in item:
            heading, details = item.split(":", 1)
            heading = clean(heading).upper()
            details = clean(details)
            lines.append(f"{heading}: {details}")
        else:
            lines.append(item)

    return "\n".join(lines)


def skills_line(items: Iterable[Any]) -> str:
    return " | ".join(unique_items(items, limit=45))


def career_highlight_lines(items: Iterable[Any]) -> str:
    lines: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        value = clean(item.get("value"))
        label = clean(item.get("label"))
        if value and label:
            lines.append(f"{value} — {label}")
        if len(lines) >= 5:
            break
    return " | ".join(lines)


def build_resume(data: dict[str, Any]) -> str:
    """
    Build the final ATS-readable resume.

    Only these sections are generated dynamically:
    - Executive profile
    - Strategic competencies
    - Current role industry positioning
    - Current role positioning line
    - Current role bullets
    - Key skills
    - Completed courses supplied by the user

    Older experience, education, and languages remain fixed.
    """
    executive_profile = clean(data.get("executive_profile"))
    career_highlights = career_highlight_lines(data.get("career_highlights", []))
    competencies = competency_lines(data.get("strategic_competencies", []))
    current_bullets = bullets(data.get("current_experience", []), limit=8)
    skills = " | ".join(unique_items(data.get("key_skills", []), limit=28))

    industry_positioning = clean_heading(
        data.get("industry_positioning"),
        fallback="Digital Commerce & Growth",
    )
    role_positioning_line = clean(data.get("current_role_positioning_line"))

    completed_courses = unique_items(
        data.get("selected_completed_courses", []),
        limit=10,
    )

    sections = [
        "EXECUTIVE PROFILE",
        executive_profile,
        "",
        "CAREER HIGHLIGHTS",
        career_highlights,
        "",
        "STRATEGIC COMPETENCIES",
        competencies,
        "",
        "WORK EXPERIENCE",
        "",
        f"{CURRENT_ROLE_DATE} | {CURRENT_ROLE_LOCATION}",
        CURRENT_ROLE_TITLE,
        f"{CURRENT_COMPANY} ({industry_positioning})",
    ]

    if role_positioning_line:
        sections.append(role_positioning_line)

    if current_bullets:
        sections.append(current_bullets)

    sections.extend(
        [
            "",
            OLDER_EXPERIENCE,
            "",
            EDUCATION_AND_LANGUAGES,
            "",
            "KEY SKILLS",
            skills,
        ]
    )

    if completed_courses:
        sections.extend(
            [
                "",
                "RELEVANT PROFESSIONAL DEVELOPMENT",
                bullets(completed_courses),
            ]
        )

    resume = "\n".join(sections)
    resume = re.sub(r"\n{3,}", "\n\n", resume)
    return resume.strip()
