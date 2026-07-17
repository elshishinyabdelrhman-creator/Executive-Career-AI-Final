from __future__ import annotations

import re
from typing import Any


def _unique(items: list[str], limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = re.sub(r"\s+", " ", str(item or "")).strip(" •-")
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            result.append(text)
        if limit and len(result) >= limit:
            break
    return result


def _bullets(items: list[str]) -> str:
    return "\n".join(f"• {item}" for item in _unique(items))


def build_resume(data: dict[str, Any]) -> str:
    sections: list[str] = []
    if data.get("candidate_name"):
        sections.append(data["candidate_name"].upper())
    if data.get("contact_line"):
        sections.append(data["contact_line"])

    sections += [
        "",
        "EXECUTIVE PROFILE",
        data.get("executive_profile", ""),
        "",
        "CORE COMPETENCIES",
        "\n".join(_unique(data.get("strategic_competencies", []), 6)),
        "",
        "PROFESSIONAL EXPERIENCE",
    ]

    for exp in data.get("experiences", []):
        header = " | ".join(x for x in [exp.get("dates", ""), exp.get("location", "")] if x)
        if header:
            sections.append(header.upper())
        if exp.get("title"):
            sections.append(exp["title"].upper())
        if exp.get("company"):
            sections.append(exp["company"])
        if exp.get("positioning"):
            sections.append(exp["positioning"])
        sections.append(_bullets(exp.get("bullets", [])))
        sections.append("")

    if data.get("education"):
        sections += ["EDUCATION", "\n".join(_unique(data["education"], 8)), ""]
    if data.get("languages"):
        sections += ["LANGUAGES", " | ".join(_unique(data["languages"], 8)), ""]

    sections += [
        "TECHNICAL & PROFESSIONAL SKILLS",
        " | ".join(_unique(data.get("key_skills", []), 38)),
    ]

    completed = _unique(data.get("completed_courses", []), 12)
    if completed:
        sections += ["", "COURSES & PROFESSIONAL TRAINING", _bullets(completed)]

    if data.get("include_learning_roadmap"):
        recommended = _unique(data.get("recommended_courses", []), 6)
        if recommended:
            sections += ["", "PROFESSIONAL DEVELOPMENT FOCUS", _bullets(recommended)]

    return re.sub(r"\n{3,}", "\n\n", "\n".join(sections)).strip()
