from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any

import anthropic
import streamlit as st

from candidate_profile import CAREER_HIGHLIGHT_CANDIDATES, VERIFIED_EVIDENCE

MODEL = "claude-haiku-4-5"
MAX_INPUT_CHARS = 12000

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for", "from",
    "has", "have", "having", "he", "her", "hers", "him", "his", "i", "in", "into", "is",
    "it", "its", "of", "on", "or", "our", "ours", "she", "that", "the", "their", "theirs",
    "them", "they", "this", "to", "was", "we", "were", "will", "with", "you", "your",
    "role", "job", "work", "working", "experience", "required", "requirements", "preferred",
    "responsibilities", "responsibility", "skills", "ability", "including", "using", "within",
}

PHRASE_PATTERNS = [
    r"\b(?:customer|client) acquisition\b",
    r"\bcustomer retention\b",
    r"\bconversion rate optimization\b",
    r"\bcommercial strategy\b",
    r"\bbusiness development\b",
    r"\bstakeholder management\b",
    r"\bcross-functional collaboration\b",
    r"\bperformance marketing\b",
    r"\bmarketing automation\b",
    r"\bcategory management\b",
    r"\bproduct assortment\b",
    r"\bvendor management\b",
    r"\bsales forecasting\b",
    r"\bdata analysis\b",
    r"\bmarket analysis\b",
    r"\bproject management\b",
    r"\bproduct management\b",
    r"\bdigital transformation\b",
    r"\bcustomer experience\b",
    r"\baccount management\b",
    r"\bsearch engine optimization\b",
    r"\bemail marketing\b",
    r"\baffiliate marketing\b",
    r"\baverage order value\b",
    r"\breturn on investment\b",
    r"\bkey performance indicators\b",
]

REQUIRED_KEYS = {
    "company_style",
    "detected_industry",
    "company_size",
    "company_focus",
    "industry_positioning",
    "current_role_positioning_line",
    "executive_profile",
    "strategic_competencies",
    "current_experience",
    "key_skills",
    "selected_completed_courses",
    "recommended_courses",
    "missing_keywords",
    "improvement_suggestions",
    "cover_letter",
    "linkedin_about",
}


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()


def get_client() -> anthropic.Anthropic:
    key = _secret("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY in .streamlit/secrets.toml.")
    return anthropic.Anthropic(api_key=key)


def _extract_response_text(response: Any) -> str:
    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(str(text))
    if not chunks:
        raise ValueError("Claude returned an empty response.")
    return "\n".join(chunks)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("The AI response did not contain a JSON object.")

    candidate = cleaned[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Claude returned JSON, but it was not an object.")
    return parsed


def _clean_string(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[\s•\-*\d.)]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_list(value: Any, *, limit: int | None = None) -> list[str]:
    if value is None:
        items: list[Any] = []
    elif isinstance(value, list):
        items = value
    else:
        items = re.split(r"\n+|;", str(value))

    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean_string(item)
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
        if limit and len(output) >= limit:
            break
    return output


def _normalize_result(data: dict[str, Any], completed_courses: list[str]) -> dict[str, Any]:
    missing = REQUIRED_KEYS.difference(data)
    if missing:
        raise ValueError("Claude omitted required fields: " + ", ".join(sorted(missing)))

    normalized: dict[str, Any] = {
        "company_style": _clean_string(data.get("company_style")),
        "detected_industry": _clean_string(data.get("detected_industry")),
        "company_size": _clean_string(data.get("company_size")),
        "company_focus": _clean_string(data.get("company_focus")),
        "target_headline": _clean_string(data.get("target_headline")),
        "industry_positioning": _clean_string(data.get("industry_positioning")) or "Digital Commerce & Growth",
        "current_role_positioning_line": _clean_string(data.get("current_role_positioning_line")),
        "executive_profile": _clean_string(data.get("executive_profile")),
        "strategic_competencies": _clean_list(data.get("strategic_competencies"), limit=5),
        "current_experience": _clean_list(data.get("current_experience"), limit=8),
        "key_skills": _clean_list(data.get("key_skills"), limit=28),
        "recommended_courses": _clean_list(data.get("recommended_courses"), limit=8),
        "missing_keywords": _clean_list(data.get("missing_keywords"), limit=12),
        "improvement_suggestions": _clean_list(data.get("improvement_suggestions"), limit=8),
        "cover_letter": str(data.get("cover_letter") or "").strip(),
        "linkedin_about": str(data.get("linkedin_about") or "").strip(),
    }

    provided_map = {course.casefold(): course for course in completed_courses}
    selected = []
    for course in _clean_list(data.get("selected_completed_courses")):
        exact = provided_map.get(course.casefold())
        if exact and exact not in selected:
            selected.append(exact)
    normalized["selected_completed_courses"] = selected

    if len(normalized["current_experience"]) < 7:
        raise ValueError("Claude generated too few current-experience bullets.")

    return normalized


def _extract_keywords(text: str, max_keywords: int = 45) -> list[str]:
    lowered = text.lower()
    phrases: list[str] = []
    for pattern in PHRASE_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            phrases.append(match.group(0))

    words = re.findall(r"[a-z][a-z0-9+#./-]{2,}", lowered)
    counts = Counter(word for word in words if word not in STOPWORDS and not word.isdigit())
    single_terms = [word for word, _ in counts.most_common(max_keywords)]

    output: list[str] = []
    seen: set[str] = set()
    for keyword in [*phrases, *single_terms]:
        key = keyword.casefold()
        if key not in seen:
            seen.add(key)
            output.append(keyword)
        if len(output) >= max_keywords:
            break
    return output


def _select_dynamic_highlights(role: str, job_description: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Rank verified achievements against the target JD without inventing facts."""
    target = f"{role} {job_description}".casefold()
    target_tokens = set(re.findall(r"[a-z0-9+#./-]{3,}", target))

    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, item in enumerate(CAREER_HIGHLIGHT_CANDIDATES):
        score = float(item.get("priority", 0)) * 0.12
        for keyword in item.get("keywords", []):
            key = str(keyword).casefold().strip()
            if not key:
                continue
            if key in target:
                score += 5.0 if " " in key else 2.5
            else:
                parts = set(re.findall(r"[a-z0-9+#./-]{3,}", key))
                score += len(parts.intersection(target_tokens)) * 0.65
        ranked.append((score, -index, item))

    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)

    selected: list[dict[str, Any]] = []
    categories: set[str] = set()
    for _, _, item in ranked:
        category = str(item.get("category", ""))
        if category and category in categories:
            continue
        selected.append(item)
        categories.add(category)
        if len(selected) == 5:
            break

    if len(selected) < 5:
        for _, _, item in ranked:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) == 5:
                break

    career_highlights = [
        {"value": str(item["value"]), "label": str(item["label"])}
        for item in selected
    ]
    signature_impact = [
        {"label": str(item["impact_label"]), "text": str(item["impact_text"])}
        for item in selected[:4]
    ]
    return career_highlights, signature_impact


def _coverage_score(job_description: str, generated_text: str) -> tuple[int, list[str]]:
    keywords = _extract_keywords(job_description)
    haystack = generated_text.casefold()
    matched = [keyword for keyword in keywords if keyword.casefold() in haystack]
    missing = [keyword for keyword in keywords if keyword.casefold() not in haystack]

    if not keywords:
        return 0, []

    raw = round((len(matched) / len(keywords)) * 100)
    return max(0, min(100, raw)), missing[:12]


def _calculate_scores(job_description: str, master_resume: str, result: dict[str, Any]) -> dict[str, int]:
    generated_text = "\n".join(
        [
            result.get("executive_profile", ""),
            "\n".join(result.get("strategic_competencies", [])),
            result.get("current_role_positioning_line", ""),
            "\n".join(result.get("current_experience", [])),
            "\n".join(result.get("key_skills", [])),
            "\n".join(result.get("selected_completed_courses", [])),
            "\n".join(f"{x.get('value', '')} {x.get('label', '')}" for x in result.get("career_highlights", [])),
        ]
    )

    generated_coverage, _ = _coverage_score(job_description, generated_text)
    evidence_coverage, _ = _coverage_score(job_description, master_resume)

    ats = round((generated_coverage * 0.75) + (evidence_coverage * 0.25))
    match = round((generated_coverage * 0.55) + (evidence_coverage * 0.45))

    hard_gap_penalty = min(len(result.get("missing_keywords", [])) * 2, 18)
    match = max(0, min(98, match - hard_gap_penalty))
    ats = max(0, min(98, ats - round(hard_gap_penalty * 0.4)))

    interview = round((match * 0.65) + (ats * 0.35) - 8)
    interview = max(5, min(95, interview))

    return {"match": match, "ats": ats, "interview_probability": interview}


def tailor_resume(
    company: str,
    role: str,
    job_description: str,
    master_resume: str,
    completed_courses: list[str],
) -> dict[str, Any]:
    company = company.strip()
    role = role.strip()
    job_description = job_description.strip()
    master_resume = master_resume.strip()

    if not company or not role or not job_description or not master_resume:
        raise ValueError("Company, role, job description, and master resume are required.")

    completed_courses = [course.strip() for course in completed_courses if course.strip()]
    completed = "\n".join(f"- {course}" for course in completed_courses) or "None provided"

    prompt = f"""
You are an executive resume strategist and evidence-based ATS optimizer.
Return ONLY one valid JSON object. Do not include markdown or commentary.

Required schema:
{{
  "company_style": "",
  "detected_industry": "",
  "company_size": "",
  "company_focus": "",
  "target_headline": "three concise role-aligned pillars separated by |",
  "industry_positioning": "2-5 truthful functional words",
  "current_role_positioning_line": "one concise sentence",
  "executive_profile": "85-105 words",
  "strategic_competencies": ["CATEGORY: skill | skill | skill"],
  "current_experience": ["bullet without bullet symbol"],
  "key_skills": ["skill"],
  "selected_completed_courses": ["exact course as provided"],
  "recommended_courses": ["course recommendation only"],
  "missing_keywords": ["unsupported hard requirement"],
  "improvement_suggestions": ["truthful actionable suggestion"],
  "cover_letter": "250-350 words",
  "linkedin_about": "120-180 words"
}}

TARGET COMPANY: {company}
TARGET ROLE: {role}

JOB DESCRIPTION:
{job_description[:7000]}

MASTER RESUME:
{master_resume[:MAX_INPUT_CHARS]}

ADDITIONAL VERIFIED CANDIDATE EVIDENCE:
{VERIFIED_EVIDENCE}

COMPLETED COURSES OR CERTIFICATIONS SUPPLIED BY THE CANDIDATE:
{completed}

Non-negotiable rules:
1. Preserve every historical employer, title, employment date, degree, and language exactly as supplied.
2. Tailor only the executive profile, strategic competencies, current-role positioning line, current-role bullets, key skills, and selected completed courses.
3. Do not invent metrics, revenue figures, team sizes, employers, job titles, tools, certifications, courses, degrees, industries, clients, or responsibilities.
4. Use role-relevant transferable language only when the master resume contains supporting evidence.
5. Generate exactly 8 current-experience bullets. Each bullet must be 18-31 words, specific, ATS-friendly, and defensible in an interview. Prioritize verified quantified achievements where relevant.
6. Use exact job-description terminology naturally where evidence supports it. Avoid keyword stuffing and duplicate bullets.
7. selected_completed_courses may contain only exact items supplied above. If none are relevant, return an empty list.
8. recommended_courses are recommendations only and must not be represented as completed.
9. industry_positioning describes transferable functions, not the target company's industry. Do not falsely claim Dabouq operates in banking, healthcare, government, grocery, SaaS, or another target sector.
10. missing_keywords must contain only material requirements not supported by the master resume or generated truthful sections.
11. Strategic competencies: return exactly 5 category lines. Key skills: return 18-28 concise skills.
12. Cover letter must be tailored, credible, and free of fabricated achievements.
13. target_headline must contain three concise role-aligned pillars separated by | and must not claim an unsupported title.
14. No bullet symbols inside JSON strings. No markdown.
"""

    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = _extract_response_text(response)
    parsed = _parse_json(raw)
    result = _normalize_result(parsed, completed_courses)

    career_highlights, signature_impact = _select_dynamic_highlights(role, job_description)
    result["career_highlights"] = career_highlights
    result["signature_impact"] = signature_impact

    calculated = _calculate_scores(job_description, master_resume, result)
    result.update(calculated)

    _, uncovered = _coverage_score(
        job_description,
        "\n".join(
            [
                result["executive_profile"],
                *result["strategic_competencies"],
                result["current_role_positioning_line"],
                *result["current_experience"],
                *result["key_skills"],
            ]
        ),
    )

    existing_missing = {item.casefold() for item in result["missing_keywords"]}
    for keyword in uncovered:
        if keyword.casefold() not in existing_missing and len(result["missing_keywords"]) < 12:
            result["missing_keywords"].append(keyword)
            existing_missing.add(keyword.casefold())

    return result
