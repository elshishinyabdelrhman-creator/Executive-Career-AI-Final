from __future__ import annotations

import re
from collections import Counter
from typing import Any

STOP = {
    "and", "the", "for", "with", "that", "from", "this", "will", "within", "into",
    "role", "job", "work", "years", "year", "required", "preferred", "strong", "skills",
    "experience", "responsible", "including", "ensure", "other", "related", "business",
}

CATEGORY_TERMS = {
    "leadership_score": ["lead", "leadership", "team", "manage", "director", "stakeholder", "mentor", "coach"],
    "tools_score": ["sql", "power bi", "tableau", "looker", "ga4", "analytics", "crm", "excel", "shopify"],
    "responsibility_score": ["strategy", "planning", "execution", "forecast", "analysis", "campaign", "operations"],
    "commercial_score": ["revenue", "sales", "commercial", "growth", "profit", "pricing", "acquisition", "retention"],
    "industry_score": ["e-commerce", "ecommerce", "retail", "grocery", "digital commerce", "online"],
}


def _terms(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+./-]{2,}", text.lower())
    return [word for word in words if word not in STOP]


def _coverage(source: str, terms: list[str]) -> int:
    lower = source.lower()
    unique = list(dict.fromkeys(term.lower() for term in terms if term))
    hits = sum(1 for term in unique if term in lower)
    return round(100 * hits / max(1, len(unique)))


def _jd_copy_ratio(job_description: str, generated: str) -> int:
    jd_phrases = set(re.findall(r"\b(?:[a-z]+\s+){3,6}[a-z]+\b", job_description.lower()))
    if not jd_phrases:
        return 0
    copied = sum(1 for phrase in jd_phrases if phrase in generated.lower())
    return min(100, round(100 * copied / len(jd_phrases)))


def calculate_scores(job_description: str, master_resume: str, result: dict[str, Any]) -> dict[str, Any]:
    generated = " ".join([
        result.get("executive_profile", ""),
        " ".join(result.get("strategic_competencies", [])),
        " ".join(result.get("key_skills", [])),
        " ".join(bullet for exp in result.get("experiences", []) for bullet in exp.get("bullets", [])),
    ])
    counts = Counter(_terms(job_description))
    priority = [term for term, _ in counts.most_common(45)]
    keyword_score = _coverage(generated, priority)
    category_scores = {key: _coverage(generated, terms) for key, terms in CATEGORY_TERMS.items()}

    unsupported = len(result.get("unsupported_requirements", []))
    enhancements = len(result.get("auto_resume_enhancements", []))
    evidence_score = max(0, min(100, 72 + enhancements * 2 - unsupported * 3))
    jd_copy_ratio = _jd_copy_ratio(job_description, generated)
    hallucination_risk = max(0, min(100, (100 - evidence_score) + jd_copy_ratio // 2))
    parseability = 98
    recruiter_hook = min(100, round(
        category_scores["commercial_score"] * 0.30
        + category_scores["leadership_score"] * 0.25
        + category_scores["responsibility_score"] * 0.20
        + evidence_score * 0.25
    ))

    ats_readiness = round(
        keyword_score * 0.26
        + category_scores["responsibility_score"] * 0.18
        + category_scores["tools_score"] * 0.08
        + category_scores["leadership_score"] * 0.12
        + category_scores["commercial_score"] * 0.14
        + category_scores["industry_score"] * 0.08
        + evidence_score * 0.09
        + parseability * 0.05
    )
    recruiter_match = round(
        recruiter_hook * 0.35
        + category_scores["leadership_score"] * 0.15
        + category_scores["commercial_score"] * 0.20
        + category_scores["industry_score"] * 0.12
        + evidence_score * 0.18
    )
    hiring_manager_fit = round(
        category_scores["responsibility_score"] * 0.25
        + category_scores["commercial_score"] * 0.25
        + category_scores["leadership_score"] * 0.20
        + category_scores["industry_score"] * 0.12
        + evidence_score * 0.18
    )
    interview_probability = round(
        recruiter_match * 0.34
        + hiring_manager_fit * 0.31
        + ats_readiness * 0.20
        + evidence_score * 0.15
        - unsupported * 1.5
    )

    clamp = lambda value: max(0, min(100, int(round(value))))
    return {
        "ats": clamp(ats_readiness),
        "match": clamp(recruiter_match),
        "interview_probability": clamp(interview_probability),
        "ats_readiness": clamp(ats_readiness),
        "recruiter_match": clamp(recruiter_match),
        "hiring_manager_fit": clamp(hiring_manager_fit),
        "resume_confidence": clamp(evidence_score),
        "recruiter_hook_score": clamp(recruiter_hook),
        "keyword_score": keyword_score,
        "evidence_score": clamp(evidence_score),
        "parseability_score": parseability,
        "jd_copy_ratio": jd_copy_ratio,
        "hallucination_risk": hallucination_risk,
        "supported_claims": clamp(evidence_score),
        "transferable_enhancements": enhancements,
        "unsupported_claims": 0,
        **category_scores,
    }
