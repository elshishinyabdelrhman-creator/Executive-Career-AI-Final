from __future__ import annotations

import json
import os
import re
from collections import Counter
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
MAX_INPUT_CHARS = 12000

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for", "from",
    "has", "have", "having", "he", "her", "hers", "him", "his", "i", "in", "into", "is",
    "it", "its", "of", "on", "or", "our", "ours", "she", "that", "the", "their", "theirs",
    "them", "they", "this", "to", "was", "we", "were", "will", "with", "you", "your",
    "role", "job", "work", "working", "experience", "required", "requirements", "preferred",
    "responsibilities", "responsibility", "skills", "ability", "including", "using", "within",
    "company", "candidate", "position", "opportunity", "benefits", "salary", "holiday", "package",
    "remote", "office", "training", "recognition", "rewards", "global", "team", "success",
}

PHRASE_PATTERNS = [
    r"\bpartner marketing\b", r"\bpartner enablement\b", r"\bpartner management\b",
    r"\bmarketing plans?\b", r"\btrusted advisor\b", r"\bclient liaison\b",
    r"\bstakeholder management\b", r"\brelationship management\b",
    r"\bagency management\b", r"\bvendor management\b", r"\bevent planning\b",
    r"\bcampaign performance\b", r"\bperformance reporting\b", r"\bprocess improvement\b",
    r"\bcontent localization\b", r"\bmarket development funds?\b", r"\bMDF\b",
    r"\bquarterly business reviews?\b", r"\bQBRs?\b", r"\bIT channel\b",
    r"\bcloud service provider\b", r"\bMENAT\b", r"\bMiddle East\b",
    r"\bcustomer acquisition\b", r"\bcustomer retention\b",
    r"\bconversion rate optimization\b", r"\bcommercial strategy\b",
    r"\bbusiness development\b", r"\bcross-functional collaboration\b",
    r"\bperformance marketing\b", r"\bmarketing automation\b",
    r"\bsales forecasting\b", r"\bdata analysis\b", r"\bmarket analysis\b",
    r"\bproject management\b", r"\bdigital transformation\b",
    r"\bcustomer experience\b", r"\baccount management\b",
    r"\bsearch engine optimization\b", r"\bemail marketing\b",
    r"\breturn on investment\b", r"\bkey performance indicators\b",
]

# Requirement groups are only activated when their JD terms appear. Variants allow
# honest semantic matching instead of fragile exact-word counting.
REQUIREMENT_GROUPS: list[dict[str, Any]] = [
    {"label": "Partner marketing", "weight": 5, "jd": ["partner marketing"],
     "exact": ["partner marketing"], "transfer": ["partnership development", "strategic partnerships", "marketing strategy"]},
    {"label": "Partner enablement", "weight": 5, "jd": ["partner enablement", "enable partners", "partner program enablement"],
     "exact": ["partner enablement"], "transfer": ["partner support", "strategic guidance", "consultative service"]},
    {"label": "Partner relationship management", "weight": 5, "jd": ["partner relationship", "partner management", "partner network"],
     "exact": ["partner relationship", "partner management", "partner network"],
     "transfer": ["relationship management", "strategic partnerships", "client relationships", "stakeholder relationships"]},
    {"label": "Marketing plan development", "weight": 4, "jd": ["marketing plans", "marketing plan", "marketing strategies"],
     "exact": ["marketing plan", "marketing strategy"], "transfer": ["campaign planning", "content strategy", "integrated marketing"]},
    {"label": "Trusted-advisor consultation", "weight": 4, "jd": ["trusted advisor", "strategic guidance", "advise on marketing"],
     "exact": ["trusted advisor", "strategic guidance", "marketing consultancy"],
     "transfer": ["consultative service", "advisory", "client relationship management"]},
    {"label": "Stakeholder and decision-maker relationships", "weight": 4,
     "jd": ["key stakeholders", "decision-makers", "stakeholder coordination", "stakeholder alignment"],
     "exact": ["key stakeholders", "decision-makers", "stakeholder management", "stakeholder coordination"],
     "transfer": ["senior stakeholders", "executive stakeholders", "board members", "cross-functional"]},
    {"label": "Client liaison", "weight": 3, "jd": ["client liaison", "main point of contact", "client meetings"],
     "exact": ["client liaison", "point of contact", "client meetings"],
     "transfer": ["client relationships", "relationship manager", "partner relationships"]},
    {"label": "Digital and offline campaigns", "weight": 4,
     "jd": ["online", "offline", "email marketing", "seo", "sea", "social networks", "display advertising", "telemarketing", "print advertising", "sponsoring"],
     "exact": ["email marketing", "seo", "sem", "sea", "paid social", "social media", "display advertising", "events", "sponsorship"],
     "transfer": ["multi-channel", "digital marketing", "integrated campaigns", "performance marketing"]},
    {"label": "Campaign performance analysis", "weight": 4,
     "jd": ["track", "analyse", "analyze", "optimise", "optimize", "campaign performance", "actionable recommendations"],
     "exact": ["campaign performance", "performance analysis", "campaign optimization", "actionable insights", "actionable recommendations"],
     "transfer": ["a/b testing", "analytics", "data-driven", "performance reporting"]},
    {"label": "Agency management", "weight": 4, "jd": ["external agencies", "manage agencies", "agency management"],
     "exact": ["external agencies", "agency management", "managed agencies"],
     "transfer": ["vendors", "production partners", "third-party"]},
    {"label": "Event planning and execution", "weight": 4,
     "jd": ["events", "event planning", "on-site execution", "post-event"],
     "exact": ["events", "event planning", "on-site execution", "post-event", "exhibitions"],
     "transfer": ["experiential", "activation", "venue operations"]},
    {"label": "MDF process management", "weight": 5, "jd": ["mdf", "market development fund", "request submissions", "claims"],
     "exact": ["mdf", "market development fund", "request submissions", "claims processing"], "transfer": []},
    {"label": "QBR and executive reporting", "weight": 3,
     "jd": ["quarterly business review", "qbr", "end-of-month reports"],
     "exact": ["quarterly business review", "qbr", "end-of-month report"],
     "transfer": ["executive reporting", "performance reports", "reported directly to senior management"]},
    {"label": "Process improvement and operational efficiency", "weight": 3,
     "jd": ["process improvement", "drive efficiency", "operational ability", "innovation"],
     "exact": ["process improvement", "operational efficiency", "workflow efficiency"],
     "transfer": ["marketing automation", "streamlining workflows", "operations"]},
    {"label": "MENAT market knowledge", "weight": 4, "jd": ["menat", "mena", "middle east", "market specificities"],
     "exact": ["menat", "mena", "middle east"], "transfer": ["ksa", "saudi arabia", "gcc", "regional market"]},
    {"label": "Israel market coverage", "weight": 4, "jd": ["israel region", "across israel", "events across the country"],
     "exact": ["israel"], "transfer": []},
    {"label": "Hebrew content localization", "weight": 3, "jd": ["hebrew", "content localization", "localisation"],
     "exact": ["hebrew", "content localization", "content localisation"], "transfer": []},
    {"label": "Arabic language", "weight": 4, "jd": ["arabic"], "exact": ["arabic", "native arabic"], "transfer": []},
    {"label": "English language", "weight": 4, "jd": ["english"], "exact": ["english", "c2"], "transfer": []},
    {"label": "Technology / IT-channel exposure", "weight": 3,
     "jd": ["tech sector", "technology", "it channel", "cloud service provider", "it resellers", "software companies"],
     "exact": ["technology sector", "tech sector", "it channel", "cloud service", "it reseller", "software companies"],
     "transfer": ["digital platforms", "e-commerce", "crm systems", "app communication"]},
    {"label": "Microsoft Office", "weight": 2,
     "jd": ["powerpoint", "excel", "word skills", "microsoft office"],
     "exact": ["powerpoint", "excel", "microsoft word", "microsoft office"],
     "transfer": ["microsoft office suite"]},
    {"label": "Smartsheet", "weight": 1, "jd": ["smartsheet"], "exact": ["smartsheet"], "transfer": []},
    {"label": "Commercial and business growth", "weight": 3,
     "jd": ["business growth", "business outcomes", "measurable outcomes", "sales strategies"],
     "exact": ["business growth", "business outcomes", "measurable outcomes", "sales strategy"],
     "transfer": ["revenue growth", "commercial growth", "sales-qualified leads", "lead generation"]},
    {"label": "Project management", "weight": 3,
     "jd": ["planning", "coordinate", "execution", "timely delivery"],
     "exact": ["project management", "planning", "coordination", "execution", "timely delivery"],
     "transfer": ["end-to-end", "timeline management", "program ownership"]},
]

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
]

REQUIRED_KEYS = {
    "company_style", "detected_industry", "company_size", "company_focus",
    "industry_positioning", "current_role_positioning_line", "executive_profile",
    "strategic_competencies", "current_experience", "key_skills",
    "selected_completed_courses", "recommended_courses", "missing_keywords",
    "improvement_suggestions", "cover_letter", "linkedin_about",
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
    return normalized


def _normalize_match_text(text: str) -> str:
    text = str(text or "").casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#./]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains(text: str, variants: list[str]) -> bool:
    normalized = _normalize_match_text(text)
    return any(_normalize_match_text(v) in normalized for v in variants if v)


def _scorable_jd(text: str) -> str:
    value = str(text or "")
    lower = value.casefold()
    starts = [lower.find(x) for x in ("about the role", "what you'll do", "what you will do") if lower.find(x) >= 0]
    if starts:
        value = value[min(starts):]
    # Benefits are employer offerings, not candidate requirements.
    value = re.split(r"(?im)^\s*benefits\s*:?[\s]*$", value, maxsplit=1)[0]
    # Remove the logistics block but preserve Qualifications that may follow it.
    value = re.sub(
        r"(?ims)^\s*additional information\s*:?.*?(?=^\s*qualifications\s*:?)",
        "\n",
        value,
    )
    return value.strip()


def _extract_keywords(text: str, max_keywords: int = 30) -> list[str]:
    lowered = _scorable_jd(text).lower()
    phrases: list[str] = []
    for pattern in PHRASE_PATTERNS:
        match = re.search(pattern, lowered, flags=re.I)
        if match:
            phrases.append(match.group(0))
    words = re.findall(r"[a-z][a-z0-9+#./-]{2,}", lowered)
    counts = Counter(word for word in words if word not in STOPWORDS and not word.isdigit())
    singles = [word for word, _ in counts.most_common(max_keywords)]
    output: list[str] = []
    seen: set[str] = set()
    for keyword in [*phrases, *singles]:
        key = keyword.casefold()
        if key not in seen:
            seen.add(key)
            output.append(keyword)
        if len(output) >= max_keywords:
            break
    return output


def _active_requirements(job_description: str) -> list[dict[str, Any]]:
    jd = _scorable_jd(job_description)
    active = [group for group in REQUIREMENT_GROUPS if _contains(jd, group["jd"])]
    return active


def _requirement_status(text: str, requirement: dict[str, Any]) -> tuple[str, float]:
    if _contains(text, requirement.get("exact", [])):
        return "matched", 1.0
    if _contains(text, requirement.get("transfer", [])):
        return "transferable", 0.65
    return "missing", 0.0


def _score_requirement_coverage(job_description: str, text: str) -> tuple[int, list[str], list[str], list[str]]:
    requirements = _active_requirements(job_description)
    if not requirements:
        keywords = _extract_keywords(job_description)
        if not keywords:
            return 0, [], [], []
        matched = [k for k in keywords if _contains(text, [k])]
        missing = [k for k in keywords if k not in matched]
        return round(100 * len(matched) / len(keywords)), matched, [], missing

    total_weight = sum(float(r["weight"]) for r in requirements)
    earned = 0.0
    matched: list[str] = []
    transferable: list[str] = []
    missing: list[str] = []
    for requirement in requirements:
        status, factor = _requirement_status(text, requirement)
        earned += float(requirement["weight"]) * factor
        if status == "matched":
            matched.append(requirement["label"])
        elif status == "transferable":
            transferable.append(requirement["label"])
        else:
            missing.append(requirement["label"])
    score = round((earned / total_weight) * 100) if total_weight else 0
    return score, matched, transferable, missing


def _claim_present(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, str(text or ""), flags=re.I) for pattern in patterns)


def _unsupported_claims(result: dict[str, Any], evidence_text: str) -> dict[str, list[str]]:
    generated = "\n".join([
        result.get("target_headline", ""), result.get("executive_profile", ""),
        result.get("current_role_positioning_line", ""), *result.get("strategic_competencies", []),
        *result.get("current_experience", []), *result.get("key_skills", []),
        result.get("cover_letter", ""), result.get("linkedin_about", ""),
    ])
    unsupported: dict[str, list[str]] = {}
    for label, patterns in CRITICAL_CLAIMS.items():
        if _claim_present(generated, patterns) and not _claim_present(evidence_text, patterns):
            unsupported[label] = patterns
    return unsupported


def _remove_sentences_with_patterns(text: str, patterns: list[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    kept = [s for s in sentences if s and not _claim_present(s, patterns)]
    return " ".join(kept).strip()


def _safe_profile() -> str:
    return (
        "Marketing, partnerships, and commercial-growth leader with 10+ years of experience across Saudi Arabia and the GCC. "
        "Proven record building strategic relationships with banks, insurers, corporate clients, agencies, and vendors; directing integrated digital and offline campaigns; and translating activity into measurable engagement and qualified pipeline. "
        "Experienced in executive stakeholder communication, performance reporting, contract negotiation, cross-functional leadership, and large-scale event delivery. "
        "Managed a SAR 30M project portfolio, led 150+ internal and external stakeholders, delivered exhibitions for 5,000+ attendees, generated 3,000+ Sales Qualified Leads, and increased customer engagement by 35%."
    )


def _rank_verified_bullets(job_description: str) -> list[str]:
    jd_tokens = set(re.findall(r"[a-z0-9+#./-]{3,}", _normalize_match_text(_scorable_jd(job_description))))
    ranked: list[tuple[int, int, str]] = []
    for index, bullet in enumerate(VERIFIED_CURRENT_ROLE_BULLETS):
        tokens = set(re.findall(r"[a-z0-9+#./-]{3,}", _normalize_match_text(bullet)))
        score = len(tokens.intersection(jd_tokens))
        ranked.append((score, -index, bullet))
    ranked.sort(reverse=True)
    return [row[2] for row in ranked]


def _sanitize_result(result: dict[str, Any], master_resume: str, job_description: str) -> dict[str, Any]:
    evidence_text = f"{master_resume}\n{VERIFIED_EVIDENCE}"
    unsupported = _unsupported_claims(result, evidence_text)
    all_patterns = [p for patterns in unsupported.values() for p in patterns]
    if all_patterns:
        for key in ("executive_profile", "current_role_positioning_line", "cover_letter", "linkedin_about"):
            result[key] = _remove_sentences_with_patterns(str(result.get(key, "")), all_patterns)
        result["current_experience"] = [
            item for item in result.get("current_experience", []) if not _claim_present(item, all_patterns)
        ]
        result["key_skills"] = [item for item in result.get("key_skills", []) if not _claim_present(item, all_patterns)]
        cleaned_competencies: list[str] = []
        for line in result.get("strategic_competencies", []):
            if ":" in line:
                heading, details = line.split(":", 1)
                parts = [p.strip() for p in details.split("|") if p.strip() and not _claim_present(p, all_patterns)]
                if parts:
                    cleaned_competencies.append(f"{heading.strip()}: {' | '.join(parts)}")
            elif not _claim_present(line, all_patterns):
                cleaned_competencies.append(line)
        result["strategic_competencies"] = cleaned_competencies[:5]
        headline_parts = [p.strip() for p in str(result.get("target_headline", "")).split("|")]
        headline_parts = [p for p in headline_parts if p and not _claim_present(p, all_patterns)]
        result["target_headline"] = " | ".join(headline_parts)

    if len(str(result.get("executive_profile", "")).split()) < 65:
        result["executive_profile"] = _safe_profile()

    safe_headline_parts = [p.strip() for p in str(result.get("target_headline", "")).split("|") if p.strip()]
    fallback_parts = ["PARTNER MARKETING", "STRATEGIC PARTNERSHIPS", "MULTI-CHANNEL CAMPAIGNS"]
    for part in fallback_parts:
        if len(safe_headline_parts) >= 3:
            break
        if part.casefold() not in {x.casefold() for x in safe_headline_parts}:
            safe_headline_parts.append(part)
    result["target_headline"] = " | ".join(safe_headline_parts[:3])

    bullets = _clean_list(result.get("current_experience"), limit=8)
    seen = {b.casefold() for b in bullets}
    for bullet in _rank_verified_bullets(job_description):
        if len(bullets) >= 8:
            break
        if bullet.casefold() not in seen:
            bullets.append(bullet)
            seen.add(bullet.casefold())
    result["current_experience"] = bullets[:8]
    result["unsupported_generated_claims"] = list(unsupported.keys())
    result["truthfulness_score"] = max(0, 100 - (len(unsupported) * 12))
    return result


def _select_dynamic_highlights(role: str, job_description: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    target = f"{role} {_scorable_jd(job_description)}".casefold()
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
    career_highlights = [{"value": str(i["value"]), "label": str(i["label"])} for i in selected]
    signature_impact = [{"label": str(i["impact_label"]), "text": str(i["impact_text"])} for i in selected[:4]]
    return career_highlights, signature_impact


def _full_generated_text(result: dict[str, Any]) -> str:
    older = []
    for role in OLDER_EXPERIENCE:
        older.extend([role.get("title", ""), role.get("company", ""), *role.get("bullets", [])])
    profile_static = [
        PROFILE.get("location", ""), *PROFILE.get("languages", []), *PROFILE.get("tools", []),
        *[" ".join(item) for item in PROFILE.get("education", [])],
    ]
    return "\n".join([
        result.get("target_headline", ""), result.get("executive_profile", ""),
        *result.get("strategic_competencies", []), result.get("current_role_positioning_line", ""),
        *result.get("current_experience", []), *result.get("key_skills", []),
        *result.get("selected_completed_courses", []),
        *[f"{x.get('value', '')} {x.get('label', '')}" for x in result.get("career_highlights", [])],
        *older, *profile_static,
    ])


def _calculate_scores(job_description: str, master_resume: str, result: dict[str, Any]) -> dict[str, Any]:
    generated_text = _full_generated_text(result)
    evidence_text = f"{master_resume}\n{VERIFIED_EVIDENCE}\n" + "\n".join(PROFILE.get("languages", []))
    generated_coverage, matched, transferable, generated_missing = _score_requirement_coverage(job_description, generated_text)
    evidence_coverage, evidence_matched, evidence_transferable, evidence_missing = _score_requirement_coverage(job_description, evidence_text)

    # ATS score measures the tailored document, not the unedited source resume.
    # 15 points reflect complete ATS sections/format; 85 points reflect JD coverage.
    ats = round(15 + (generated_coverage * 0.85))
    ats = max(0, min(98, ats))

    # Match is evidence-based and cannot be inflated by generated wording.
    match = max(0, min(98, evidence_coverage))

    critical_gap_labels = {"MDF process management", "Israel market coverage", "Hebrew content localization"}
    critical_gaps = [item for item in evidence_missing if item in critical_gap_labels]
    interview = round((match * 0.72) + (ats * 0.28) - (len(critical_gaps) * 3))
    interview = max(5, min(95, interview))

    return {
        "match": match,
        "ats": ats,
        "interview_probability": interview,
        "matched_requirements": matched,
        "transferable_requirements": transferable,
        "unsupported_requirements": evidence_missing,
        "evidence_matched_requirements": evidence_matched,
        "evidence_transferable_requirements": evidence_transferable,
        "generated_missing_requirements": generated_missing,
        "critical_gaps": critical_gaps,
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
    prompt = f"""
You are an executive resume strategist and evidence-based ATS optimizer.
Return ONLY one valid JSON object. Do not include markdown or commentary.

Required schema:
{{
  "company_style": "",
  "detected_industry": "",
  "company_size": "",
  "company_focus": "",
  "target_headline": "three concise role-aligned functional pillars separated by |",
  "industry_positioning": "2-5 truthful functional words",
  "current_role_positioning_line": "one concise sentence",
  "executive_profile": "85-105 words",
  "strategic_competencies": ["CATEGORY: skill | skill | skill"],
  "current_experience": ["bullet without bullet symbol"],
  "key_skills": ["skill"],
  "selected_completed_courses": ["exact course as provided"],
  "recommended_courses": ["course recommendation only"],
  "missing_keywords": ["unsupported material requirement"],
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
1. Preserve every historical employer, title, date, degree, and language exactly as supplied.
2. Tailor only the profile, competencies, current-role positioning, current-role bullets, key skills, and selected completed courses.
3. Every claim must be supported by the master resume or additional verified evidence.
4. NEVER claim MDF, QBR, Israel-market, Hebrew-localization, Smartsheet, cloud-provider, reseller, software-company, or IT-channel experience unless those exact facts appear in the evidence.
5. Do not convert a target requirement into candidate experience. Unsupported requirements belong only in missing_keywords and improvement_suggestions.
6. Generate exactly 8 current-experience bullets, each 18-31 words, specific, ATS-friendly, and defensible.
7. Use exact JD terminology only where evidence supports it; use credible transferable wording otherwise.
8. selected_completed_courses may contain only exact items supplied above.
9. industry_positioning describes transferable functions, not the target company's industry.
10. Strategic competencies: exactly 5 category lines. Key skills: 18-28 concise skills.
11. target_headline must use functional pillars, not an unsupported job title or industry claim.
12. No bullet symbols inside JSON strings. No markdown.
"""

    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )
    parsed = _parse_json(_extract_response_text(response))
    result = _normalize_result(parsed, completed_courses)
    result = _sanitize_result(result, master_resume, job_description)

    career_highlights, signature_impact = _select_dynamic_highlights(role, job_description)
    result["career_highlights"] = career_highlights
    result["signature_impact"] = signature_impact

    calculated = _calculate_scores(job_description, master_resume, result)
    result.update(calculated)

    # Gap list displayed to the user is deterministic and evidence-based.
    result["missing_keywords"] = calculated["unsupported_requirements"][:12]
    existing_suggestions = _clean_list(result.get("improvement_suggestions"), limit=8)
    for gap in calculated["critical_gaps"]:
        suggestion = f"Address the {gap} requirement only with real experience, training, or role clarification; do not add it as an unsupported resume claim."
        if suggestion.casefold() not in {x.casefold() for x in existing_suggestions}:
            existing_suggestions.append(suggestion)
    result["improvement_suggestions"] = existing_suggestions[:8]
    return result
