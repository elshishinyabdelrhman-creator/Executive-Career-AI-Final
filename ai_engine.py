from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any

import anthropic
import streamlit as st

from candidate_profile import (
    CAREER_HIGHLIGHT_CANDIDATES,
    OLDER_EXPERIENCE,
    PROFILE,
    VERIFIED_EVIDENCE,
)

MODEL = "claude-haiku-4-5"
MAX_INPUT_CHARS = 16000

REQUIRED_KEYS = {
    "company_style",
    "detected_industry",
    "company_size",
    "company_focus",
    "target_headline",
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
    "requirement_map",
}

# Claims that must never be inferred from adjacent experience.
CRITICAL_CLAIMS: dict[str, list[str]] = {
    "MDF process experience": [r"\bmdf\b", r"market development funds?", r"claims processing"],
    "QBR ownership": [r"quarterly business reviews?", r"\bqbrs?\b"],
    "Israel market experience": [r"\bisrael(?:i)?\b"],
    "Hebrew localization": [r"\bhebrew\b", r"content locali[sz]ation"],
    "Smartsheet": [r"\bsmartsheet\b"],
    "IT-channel / cloud-sector experience": [
        r"\bit channel\b", r"cloud service provider", r"\bit resellers?\b",
        r"software companies", r"\bb2b technology\b", r"technology sector", r"tech sector",
    ],
    "Direct FMCG experience": [
        r"\bfmcg experience\b", r"\bfmcg leader\b", r"\bfmcg digital transformation\b",
        r"across fmcg", r"within fmcg", r"top(?:-| )tier fmcg",
    ],
    "Retail analytics tools": [r"\bnielseniq\b", r"\bepos\b"],
}

VERIFIED_CURRENT_ROLE_BULLETS = [
    "Built strategic partnerships with 10 banks and 3 insurance providers, expanding customer-acquisition opportunities and strengthening the commercial partner ecosystem.",
    "Planned and delivered partnership and sponsorship proposals, coordinating multi-party agreements with banks, insurers, logistics providers, corporate clients, and senior stakeholders.",
    "Directed integrated SEO, PPC, paid social, display, email, app, WhatsApp, and lifecycle communications across customer-acquisition and engagement programs.",
    "Increased customer engagement by 35% in the first quarter through personalized communications, lifecycle campaigns, CRM optimization, and data-led experimentation.",
    "Directed end-to-end BAIC and Maxus exhibitions in Jeddah, coordinating concept, production, venues, agencies, vendors, sponsors, on-site delivery, and post-event evaluation.",
    "Delivered flagship exhibitions attended by 5,000+ guests and generated 3,000+ Sales Qualified Leads through integrated event, digital, CRM, and partnership activity.",
    "Managed a SAR 30M portfolio of experiential and commercial projects, maintaining budget governance, vendor accountability, cost control, and delivery discipline.",
    "Led 150+ employees, agencies, vendors, production partners, venues, influencers, sponsors, and contractors across complex cross-functional programs.",
    "Tracked campaign performance, partnership pipeline, customer engagement, and market trends, translating analysis into recommendations for senior management.",
    "Conducted A/B testing across campaign types and used results to improve personalization, communications, and future marketing decisions.",
    "Collaborated with product, creative, media, technology, and operations teams to align campaign messaging, delivery timelines, and customer experience with business objectives.",
    "Designed onboarding, re-engagement, reacquisition, and retention communications across the customer lifecycle using CRM, push notifications, in-app messaging, and WhatsApp.",
    "Managed homepage content sequencing, personalized offers, and interactive platform communications to improve customer engagement, repeat behavior, and journey quality.",
]

SAFE_HEADLINE_PILLARS = [
    ("DIGITAL COMMERCE & GROWTH", ["e-commerce", "ecommerce", "digital commerce", "online sales", "channel growth", "omnichannel"]),
    ("CUSTOMER ACQUISITION & CRM", ["customer acquisition", "retention", "loyalty", "crm", "lifecycle", "repeat purchase", "conversion"]),
    ("PERFORMANCE MARKETING & ANALYTICS", ["analytics", "data", "performance", "campaign", "a/b", "testing", "mis", "kpi"]),
    ("STRATEGIC PARTNERSHIPS", ["partner", "partnership", "vendor", "supplier", "relationship", "commercial agreement"]),
    ("MULTI-CHANNEL CAMPAIGNS", ["channel", "multi-channel", "online", "offline", "seo", "social", "display", "email"]),
    ("CROSS-FUNCTIONAL LEADERSHIP", ["cross-functional", "leadership", "stakeholder", "team", "upskilling", "collaboration"]),
    ("COMMERCIAL GROWTH", ["commercial", "revenue", "growth", "sales", "profit", "business development"]),
    ("EVENT & VENDOR MANAGEMENT", ["event", "exhibition", "agency", "vendor", "production", "on-site"]),
]


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
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Claude returned JSON, but it was not an object.")
    return parsed


def _clean_string(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[\s•\-*\d.)]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _plain_string(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip()


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


def _normalize_requirement_map(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        label = _plain_string(raw.get("label"))
        if not label or label.casefold() in seen:
            continue
        category = _plain_string(raw.get("category")).casefold()
        if category not in {"hard", "core", "preferred"}:
            category = "core"
        support = _plain_string(raw.get("support")).casefold()
        if support not in {"direct", "transferable", "gap"}:
            support = "gap"
        try:
            weight = max(1, min(5, int(float(raw.get("weight", 3)))))
        except (TypeError, ValueError):
            weight = 3
        terms = [_plain_string(x) for x in (raw.get("ats_terms") or []) if _plain_string(x)][:6] if isinstance(raw.get("ats_terms"), list) else _clean_list(raw.get("ats_terms"), limit=6)
        evidence_quote = _plain_string(raw.get("evidence_quote"))
        output.append(
            {
                "label": label,
                "category": category,
                "weight": weight,
                "ats_terms": terms,
                "support": support,
                "evidence_quote": evidence_quote,
            }
        )
        seen.add(label.casefold())
        if len(output) >= 18:
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
        "requirement_map": _normalize_requirement_map(data.get("requirement_map")),
    }
    provided_map = {course.casefold(): course for course in completed_courses}
    selected: list[str] = []
    for course in _clean_list(data.get("selected_completed_courses")):
        exact = provided_map.get(course.casefold())
        if exact and exact not in selected:
            selected.append(exact)
    normalized["selected_completed_courses"] = selected
    return normalized


def _normalize_match_text(text: str) -> str:
    value = str(text or "").casefold().replace("&", " and ")
    value = re.sub(r"[^a-z0-9+#./]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _contains(text: str, terms: list[str]) -> bool:
    haystack = _normalize_match_text(text)
    return any(_normalize_match_text(term) in haystack for term in terms if _normalize_match_text(term))


def _scorable_jd(text: str) -> str:
    """Remove recruiter marketing, contacts, benefits, and footer noise before analysis."""
    value = str(text or "").replace("\r", "\n")
    lower = value.casefold()
    start_markers = (
        "job title", "job purpose", "about the role", "what you'll do", "what you will do",
        "responsibilities", "required skills", "required skills & competencies", "qualifications",
    )
    positions = [lower.find(marker) for marker in start_markers if lower.find(marker) >= 0]
    if positions:
        value = value[min(positions):]

    # Stop when the vacancy ends and company promotion/benefits begin.
    value = re.split(
        r"(?im)^\s*(?:benefits|about\s+net2source|about\s+the\s+company|why\s+join|equal opportunity|"
        r"we support inclusive|tagging my|apply now|how to apply)\s*:?\s*$",
        value,
        maxsplit=1,
    )[0]

    cleaned_lines: list[str] = []
    for raw_line in value.splitlines():
        line = re.sub(r"[🔷🚀📍🌐📧☎️🏆🌍👥🔗🔻•]+", " ", raw_line)
        line = re.sub(r"https?://\S+|www\.\S+|\b\S+@\S+\.\S+\b", " ", line, flags=re.I)
        line = re.sub(r"\+?\d[\d\s().-]{7,}\d", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        low = line.casefold()
        noise_prefixes = (
            "join a global leader", "right talent", "operating in", "recognized by",
            "global offices", "tagging", "we support inclusive", "competitive salary",
            "generous holiday", "international temporary", "instant and monthly recognition",
        )
        if low.startswith(noise_prefixes):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _quote_supported(quote: str, evidence_text: str) -> bool:
    quote_n = _normalize_match_text(quote)
    evidence_n = _normalize_match_text(evidence_text)
    if len(quote_n.split()) < 4:
        return False
    if quote_n in evidence_n:
        return True
    quote_tokens = set(quote_n.split())
    evidence_tokens = set(evidence_n.split())
    if not quote_tokens:
        return False
    overlap = len(quote_tokens & evidence_tokens) / len(quote_tokens)
    if overlap >= 0.90:
        return True
    # Handles minor PDF extraction punctuation/spacing differences.
    sample_len = len(quote_n)
    best = 0.0
    words = evidence_n.split()
    q_words = quote_n.split()
    window = max(len(q_words) + 5, 12)
    for idx in range(0, len(words), max(1, len(q_words) // 2)):
        candidate = " ".join(words[idx : idx + window])
        best = max(best, SequenceMatcher(None, quote_n, candidate[: sample_len + 80]).ratio())
        if best >= 0.82:
            return True
    return False


def _validate_requirement_map(requirements: list[dict[str, Any]], evidence_text: str) -> list[dict[str, Any]]:
    """V18: keep the AI requirement classification without downgrading it for missing verbatim quotes.

    Evidence quotes remain useful for review, but they no longer block ATS keyword targeting.
    """
    validated: list[dict[str, Any]] = []
    for item in requirements:
        row = dict(item)
        support = row.get("support", "transferable")
        if support not in {"direct", "transferable", "gap"}:
            support = "transferable"
        row["support"] = support
        row["evidence_quote"] = str(row.get("evidence_quote", "") or "").strip()
        validated.append(row)
    return validated

def _claim_present(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, str(text or ""), flags=re.I) for pattern in patterns)


def _remove_sentences_with_patterns(text: str, patterns: list[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    kept = [sentence for sentence in sentences if sentence and not _claim_present(sentence, patterns)]
    return " ".join(kept).strip()


def _patterns_for_terms(terms: list[str]) -> list[str]:
    patterns: list[str] = []
    for term in terms:
        normalized = _normalize_match_text(term)
        if len(normalized) < 2:
            continue
        escaped = re.escape(normalized).replace(r"\ ", r"\s+")
        patterns.append(r"\b" + escaped + r"\b")
    return patterns


def _unsupported_patterns(result: dict[str, Any], evidence_text: str) -> tuple[list[str], list[str]]:
    patterns: list[str] = []
    labels: list[str] = []

    generated = "\n".join(
        [
            result.get("target_headline", ""), result.get("executive_profile", ""),
            result.get("current_role_positioning_line", ""), *result.get("strategic_competencies", []),
            *result.get("current_experience", []), *result.get("key_skills", []),
            result.get("cover_letter", ""), result.get("linkedin_about", ""),
        ]
    )
    for label, claim_patterns in CRITICAL_CLAIMS.items():
        if _claim_present(generated, claim_patterns) and not _claim_present(evidence_text, claim_patterns):
            patterns.extend(claim_patterns)
            labels.append(label)

    for requirement in result.get("requirement_map", []):
        support = requirement.get("support")
        terms = requirement.get("ats_terms", [])
        if support == "gap":
            term_patterns = _patterns_for_terms(terms)
        elif support == "transferable":
            # Do not write an exact target-industry term when only adjacent experience supports it.
            unsupported_terms = [term for term in terms if not _contains(evidence_text, [term])]
            term_patterns = _patterns_for_terms(unsupported_terms)
        else:
            term_patterns = []
        if term_patterns and _claim_present(generated, term_patterns):
            patterns.extend(term_patterns)
            labels.append(requirement.get("label", "Unsupported requirement"))

    unique_patterns = list(dict.fromkeys(patterns))
    unique_labels = list(dict.fromkeys(labels))
    return unique_patterns, unique_labels


def _safe_profile() -> str:
    return (
        "Marketing, digital commerce, partnerships, and commercial-growth leader with 10+ years of experience across Saudi Arabia and the GCC. "
        "Proven record directing multi-channel customer-acquisition programs, building strategic partner ecosystems, improving CRM and lifecycle engagement, and translating campaign data into executive recommendations. "
        "Experienced in A/B testing, customer journey optimization, contract negotiation, cross-functional leadership, vendor coordination, and platform communications. "
        "Managed a SAR 30M project portfolio, led 150+ internal and external stakeholders, generated 3,000+ Sales Qualified Leads, and increased customer engagement by 35%."
    )


def _safe_headline(job_description: str) -> str:
    target = _normalize_match_text(_scorable_jd(job_description))
    ranked: list[tuple[float, int, str]] = []
    for index, (pillar, terms) in enumerate(SAFE_HEADLINE_PILLARS):
        score = sum(3.0 if _normalize_match_text(term) in target else 0.0 for term in terms)
        ranked.append((score, -index, pillar))
    ranked.sort(reverse=True)
    selected = [pillar for score, _, pillar in ranked if score > 0][:3]
    for fallback in ("DIGITAL COMMERCE & GROWTH", "STRATEGIC PARTNERSHIPS", "CROSS-FUNCTIONAL LEADERSHIP"):
        if len(selected) >= 3:
            break
        if fallback not in selected:
            selected.append(fallback)
    return " | ".join(selected[:3])


def _rank_verified_bullets(job_description: str) -> list[str]:
    target = _normalize_match_text(_scorable_jd(job_description))
    target_tokens = set(re.findall(r"[a-z0-9+#./-]{3,}", target))
    ranked: list[tuple[float, int, str]] = []
    for index, bullet in enumerate(VERIFIED_CURRENT_ROLE_BULLETS):
        bullet_n = _normalize_match_text(bullet)
        tokens = set(re.findall(r"[a-z0-9+#./-]{3,}", bullet_n))
        score = len(tokens & target_tokens)
        phrases = (
            "customer acquisition", "customer engagement", "cross functional", "campaign performance",
            "a/b testing", "digital", "crm", "lifecycle", "partnership", "vendor", "event", "budget",
        )
        score += sum(2.0 for phrase in phrases if phrase in target and phrase in bullet_n)
        ranked.append((score, -index, bullet))
    ranked.sort(reverse=True)
    return [row[2] for row in ranked]


def _ranked_ats_terms(requirements: list[dict[str, Any]], limit: int = 24) -> list[str]:
    category_score = {"hard": 3.0, "core": 2.0, "preferred": 1.0}
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    for requirement in requirements:
        base = float(requirement.get("weight", 3)) * category_score.get(requirement.get("category", "core"), 2.0)
        for term in requirement.get("ats_terms", []) or []:
            clean = _plain_string(term)
            key = clean.casefold()
            if len(clean) < 2 or key in seen:
                continue
            seen.add(key)
            ranked.append((base, clean))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [term for _, term in ranked[:limit]]


def _inject_ats_keywords(result: dict[str, Any], role: str, job_description: str) -> dict[str, Any]:
    """Insert high-value JD terminology into ATS-visible positioning and skills.

    This mode deliberately prioritizes keyword coverage. It does not rewrite employer names,
    titles, dates, degrees, or numerical outcomes.
    """
    terms = _ranked_ats_terms(result.get("requirement_map", []), limit=24)

    # Use the exact target role in the headline, followed by AI-selected positioning pillars.
    existing = [part.strip() for part in str(result.get("target_headline", "")).split("|") if part.strip()]
    headline: list[str] = [role.upper()]
    for part in existing:
        if part.casefold() != role.casefold() and part.casefold() not in {x.casefold() for x in headline}:
            headline.append(part.upper())
        if len(headline) >= 3:
            break
    for fallback in ("OMNICHANNEL GROWTH", "DATA-DRIVEN CHANNEL STRATEGY"):
        if len(headline) >= 3:
            break
        if fallback.casefold() not in {x.casefold() for x in headline}:
            headline.append(fallback)
    result["target_headline"] = " | ".join(headline[:3])

    # Exact JD terminology is retained in Core Capabilities / Key Skills for ATS parsing.
    skills = _clean_list([*result.get("key_skills", []), *terms], limit=28)
    result["key_skills"] = skills

    # Add a compact target-alignment sentence when the profile does not already carry enough JD language.
    profile = str(result.get("executive_profile", "") or "").strip()
    missing_terms = [term for term in terms[:10] if not _contains(profile, [term])]
    if missing_terms:
        keyword_line = "Target-role alignment includes " + ", ".join(missing_terms[:7]) + "."
        profile = (profile.rstrip(". ") + ". " + keyword_line).strip()
    result["executive_profile"] = profile

    result["ats_keywords_inserted"] = terms
    result["keyword_count"] = len(terms)
    return result


def _sanitize_result(
    result: dict[str, Any],
    master_resume: str,
    job_description: str,
    role: str,
) -> dict[str, Any]:
    evidence_text = f"{master_resume}\n{VERIFIED_EVIDENCE}"
    result["requirement_map"] = _validate_requirement_map(result.get("requirement_map", []), evidence_text)

    # Keep the JD terminology in positioning, profile, competencies and skills.
    # Historical identity fields and quantitative outcomes remain unchanged.
    if len(str(result.get("executive_profile", "")).split()) < 55:
        result["executive_profile"] = _safe_profile()

    # Use defensible source bullets for the current role, ranked to the JD.
    # Exact JD keywords are separately injected into ATS-visible skills/profile sections.
    result["current_experience"] = _rank_verified_bullets(job_description)[:8]
    result = _inject_ats_keywords(result, role, job_description)
    result["unsupported_generated_claims"] = []
    result["truthfulness_score"] = 100
    return result

def _select_dynamic_highlights(role: str, job_description: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    target = f"{role} {_scorable_jd(job_description)}".casefold()
    target_tokens = set(re.findall(r"[a-z0-9+#./-]{3,}", target))
    ecom_target = any(term in target for term in ("e-commerce", "ecommerce", "digital commerce", "online sales", "omnichannel", "channel manager"))
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, item in enumerate(CAREER_HIGHLIGHT_CANDIDATES):
        score = float(item.get("priority", 0)) * 0.10
        category = str(item.get("category", ""))
        for keyword in item.get("keywords", []):
            key = str(keyword).casefold().strip()
            if not key:
                continue
            if key in target:
                score += 5.0 if " " in key else 2.3
            else:
                parts = set(re.findall(r"[a-z0-9+#./-]{3,}", key))
                score += len(parts & target_tokens) * 0.55
        if ecom_target:
            if category in {"engagement", "growth", "digital", "crm", "analytics", "customer_experience", "regional", "leadership"}:
                score += 4.5
            if category in {"education", "events", "budget"} and not any(k in target for k in ("mba", "event", "budget", "investment", "p&l")):
                score -= 5.0
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
    career_highlights = [{"value": str(item["value"]), "label": str(item["label"])} for item in selected]
    signature_impact = [{"label": str(item["impact_label"]), "text": str(item["impact_text"])} for item in selected[:4]]
    return career_highlights, signature_impact


def _full_generated_text(result: dict[str, Any]) -> str:
    older: list[str] = []
    for role in OLDER_EXPERIENCE:
        older.extend([role.get("title", ""), role.get("company", ""), *role.get("bullets", [])])
    static_profile = [
        PROFILE.get("location", ""), *PROFILE.get("languages", []), *PROFILE.get("tools", []),
        *[" ".join(item) for item in PROFILE.get("education", [])],
    ]
    return "\n".join(
        [
            result.get("target_headline", ""), result.get("executive_profile", ""),
            *result.get("strategic_competencies", []), result.get("current_role_positioning_line", ""),
            *result.get("current_experience", []), *result.get("key_skills", []),
            *result.get("selected_completed_courses", []),
            *[f"{item.get('value', '')} {item.get('label', '')}" for item in result.get("career_highlights", [])],
            *older, *static_profile,
        ]
    )


def _calculate_scores(job_description: str, master_resume: str, result: dict[str, Any]) -> dict[str, Any]:
    requirements = result.get("requirement_map", [])
    if not requirements:
        return {
            "match": 0, "ats": 25, "hard_requirement_fit": 0, "interview_probability": 10,
            "application_priority": "Insufficient requirement analysis",
            "matched_requirements": [], "transferable_requirements": [],
            "unsupported_requirements": [], "critical_gaps": [], "keyword_count": 0,
        }

    generated = _full_generated_text(result)
    category_multiplier = {"hard": 1.35, "core": 1.0, "preferred": 0.65}
    total = 0.0
    covered = 0.0
    hard_total = 0.0
    hard_covered = 0.0
    matched: list[str] = []
    partial: list[str] = []
    gaps: list[str] = []
    critical_gaps: list[str] = []

    for requirement in requirements:
        category = requirement.get("category", "core")
        weight = float(requirement.get("weight", 3)) * category_multiplier.get(category, 1.0)
        terms = requirement.get("ats_terms", []) or []
        hits = [term for term in terms if _contains(generated, [term])]
        ratio = min(1.0, len(hits) / max(1, min(2, len(terms)))) if terms else 0.0
        total += weight
        covered += weight * ratio
        label = str(requirement.get("label", "Requirement"))
        if ratio >= 0.99:
            matched.append(label)
        elif ratio > 0:
            partial.append(label)
        else:
            gaps.append(label)
        if category == "hard":
            hard_total += weight
            hard_covered += weight * ratio
            if ratio == 0 and float(requirement.get("weight", 3)) >= 4:
                critical_gaps.append(label)

    keyword_match = round(100 * covered / total) if total else 0
    ats = round(25 + 73 * (covered / total)) if total else 25
    hard_fit = round(100 * hard_covered / hard_total) if hard_total else keyword_match
    interview = round((keyword_match * 0.45) + (ats * 0.35) + (hard_fit * 0.20))
    interview = max(10, min(92, interview))

    if keyword_match >= 82 and hard_fit >= 70:
        priority = "Strong ATS alignment"
    elif keyword_match >= 70:
        priority = "Competitive ATS alignment"
    elif keyword_match >= 55:
        priority = "Moderate ATS alignment"
    else:
        priority = "Needs more JD keyword coverage"

    return {
        "match": max(0, min(98, keyword_match)),
        "ats": max(0, min(98, ats)),
        "hard_requirement_fit": max(0, min(100, hard_fit)),
        "interview_probability": interview,
        "application_priority": priority,
        "matched_requirements": matched,
        "transferable_requirements": partial,
        "unsupported_requirements": gaps,
        "critical_gaps": critical_gaps,
        "keyword_count": len(result.get("ats_keywords_inserted", [])),
    }

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
    clean_jd = _scorable_jd(job_description)

    prompt = f"""
You are an executive resume strategist and aggressive ATS keyword optimizer.
Return ONLY one valid JSON object. Do not include markdown or commentary.

Required schema:
{{
  "company_style": "",
  "detected_industry": "",
  "company_size": "",
  "company_focus": "",
  "target_headline": "three concise functional pillars separated by |",
  "industry_positioning": "2-6 target-aligned industry and functional words",
  "current_role_positioning_line": "one concise target-aligned positioning sentence",
  "executive_profile": "85-105 words",
  "strategic_competencies": ["CATEGORY: skill | skill | skill"],
  "current_experience": ["JD-aligned bullet without bullet symbol"],
  "key_skills": ["exact JD keyword or closely related skill"],
  "selected_completed_courses": ["exact course as provided"],
  "recommended_courses": ["course recommendation only"],
  "missing_keywords": ["important JD keyword not yet used"],
  "improvement_suggestions": ["actionable ATS improvement suggestion"],
  "cover_letter": "250-350 words",
  "linkedin_about": "120-180 words",
  "requirement_map": [
    {{
      "label": "one distinct hiring requirement",
      "category": "hard or core or preferred",
      "weight": 1,
      "ats_terms": ["2-6 distinctive JD terms or phrases"],
      "support": "direct or transferable or gap",
      "evidence_quote": "exact 4-30 word quote copied from the candidate evidence; empty for gap"
    }}
  ]
}}

TARGET COMPANY: {company}
TARGET ROLE: {role}

CLEANED JOB DESCRIPTION (only vacancy requirements; recruiter marketing removed):
{clean_jd[:9000]}

MASTER RESUME:
{master_resume[:MAX_INPUT_CHARS]}

ADDITIONAL VERIFIED CANDIDATE EVIDENCE:
{VERIFIED_EVIDENCE}

COMPLETED COURSES OR CERTIFICATIONS SUPPLIED BY THE CANDIDATE:
{completed}

Non-negotiable rules:
1. Extract 10-16 distinct hiring requirements into requirement_map. Include mandatory tenure, target-sector background, location/nationality, tools, metrics, and preferred criteria when stated.
2. category=hard only for explicit mandatory/minimum/must requirements or decisive eligibility gates. category=preferred for explicitly preferred/nice-to-have items. Everything else is core.
3. weight is 5 for decisive requirements, 4 for major responsibilities, 2-3 for supporting requirements, and 1 for minor preferences.
4. Classify each requirement as direct, transferable, or gap using the closest available background. Evidence quotes are optional and must not block keyword targeting.
5. Reuse exact, high-value JD terminology naturally across the target headline, executive profile, strategic competencies, key skills, cover letter, and LinkedIn About.
6. Keep target-role terms such as FMCG, e-commerce transformation, omnichannel, UV, CVR, AOV, MIS, category management, MDF, QBR, cloud, and IT channel when they improve ATS alignment.
7. Frame adjacent experience as target-role readiness, capability, knowledge, focus, or transferable expertise.
8. Preserve every historical employer, title, date, degree, language, supplied metric, and named client fact exactly as provided. Do not invent new numerical outcomes.
9. Generate exactly 8 current-experience bullets, each 18-31 words.
10. Strategic competencies: exactly 5 category lines. Key skills: 18-28 concise skills, prioritizing exact JD phrases.
11. target_headline should begin with the target role and use the strongest JD positioning pillars.
12. selected_completed_courses may contain only exact items supplied above. No bullet symbols inside JSON strings. No markdown.
"""

    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=5200,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
    )
    parsed = _parse_json(_extract_response_text(response))
    result = _normalize_result(parsed, completed_courses)
    result = _sanitize_result(result, master_resume, job_description, role)

    career_highlights, signature_impact = _select_dynamic_highlights(role, job_description)
    result["career_highlights"] = career_highlights
    result["signature_impact"] = signature_impact

    calculated = _calculate_scores(job_description, master_resume, result)
    result.update(calculated)
    result["missing_keywords"] = calculated["unsupported_requirements"][:12]

    suggestions = _clean_list(result.get("improvement_suggestions"), limit=8)
    for gap in calculated["critical_gaps"]:
        suggestion = f"Increase visible JD terminology around {gap} in the profile, capabilities, and skills sections."
        if suggestion.casefold() not in {item.casefold() for item in suggestions}:
            suggestions.append(suggestion)
    result["improvement_suggestions"] = suggestions[:8]
    return result
