from __future__ import annotations

import json
import os
import re
from typing import Any

import anthropic
import streamlit as st
from json_repair import repair_json

from ats_engine import calculate_scores
from learning_advisor import build_learning_plan

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
MAX_OUTPUT_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "8000"))
MAX_RESUME_CHARS = 15000
MAX_JD_CHARS = 7000


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    key = _secret("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY in Streamlit secrets.")
    return anthropic.Anthropic(api_key=key)


def _response_text(response: Any) -> str:
    parts = [
        str(getattr(block, "text", ""))
        for block in getattr(response, "content", []) or []
        if getattr(block, "text", None)
    ]
    if not parts:
        raise ValueError("Claude returned an empty response.")
    return "\n".join(parts)


def _parse_json(text: str) -> dict[str, Any]:
    """Parse Claude output and repair minor JSON syntax mistakes safely."""
    cleaned = text.replace("```json", "").replace("```", "").strip()

    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError as exc:
            last_error = exc

        # Claude occasionally misses a comma, quote, or closing bracket in long JSON.
        # json-repair fixes syntax only; it does not invent resume content.
        try:
            repaired = repair_json(candidate, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
            if isinstance(repaired, str):
                value = json.loads(repaired)
                if isinstance(value, dict):
                    return value
        except Exception as exc:
            last_error = exc

    detail = f": {last_error}" if last_error else ""
    raise ValueError(f"Claude returned invalid JSON{detail}")


def _string(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _list(value: Any, limit: int | None = None) -> list[str]:
    values = value if isinstance(value, list) else re.split(r"\n+|;", str(value or ""))
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        item = re.sub(r"^[\s•\-*\d.)]+", "", _string(item))
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
        if limit and len(result) >= limit:
            break
    return result


def _normalize_experiences(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("Claude did not return an experience list.")
    output: list[dict[str, Any]] = []
    for index, item in enumerate(value[:8]):
        if not isinstance(item, dict):
            continue
        bullets = _list(item.get("bullets"), 15)
        if not bullets:
            continue
        output.append(
            {
                "dates": _string(item.get("dates")),
                "location": _string(item.get("location")),
                "title": _string(item.get("title")),
                "company": _string(item.get("company")),
                "positioning": _string(item.get("positioning")) if index == 0 else "",
                "bullets": bullets,
            }
        )
    if not output:
        raise ValueError("Claude generated no usable experience entries.")
    if len(output[0]["bullets"]) < 10:
        raise ValueError("Current role must contain at least 10 evidence-based bullets.")
    return output


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    result = {
        "candidate_name": _string(data.get("candidate_name")),
        "contact_line": _string(data.get("contact_line")),
        "company_style": _string(data.get("company_style")),
        "detected_industry": _string(data.get("detected_industry")),
        "company_size": _string(data.get("company_size")),
        "company_focus": _string(data.get("company_focus")),
        "industry_positioning": _string(data.get("industry_positioning")),
        "executive_profile": _string(data.get("executive_profile")),
        "strategic_competencies": _list(data.get("strategic_competencies"), 6),
        "experiences": _normalize_experiences(data.get("experiences")),
        "education": _list(data.get("education"), 8),
        "languages": _list(data.get("languages"), 8),
        "key_skills": _list(data.get("key_skills"), 38),
        "completed_courses": _list(data.get("completed_courses"), 12),
        "auto_resume_enhancements": _list(data.get("auto_resume_enhancements"), 12),
        "unsupported_requirements": _list(data.get("unsupported_requirements"), 10),
        "improvement_suggestions": _list(data.get("improvement_suggestions"), 10),
        "cover_letter": str(data.get("cover_letter") or "").strip(),
        "linkedin_about": str(data.get("linkedin_about") or "").strip(),
        "recruiter_message": str(data.get("recruiter_message") or "").strip(),
        "referral_message": str(data.get("referral_message") or "").strip(),
        "follow_up_message": str(data.get("follow_up_message") or "").strip(),
        "recruiter_hook": _string(data.get("recruiter_hook")),
        "recruiter_objections": _list(data.get("recruiter_objections"), 8),
        "screening_call_prep": _list(data.get("screening_call_prep"), 10),
        "key_achievements": _list(data.get("key_achievements"), 8),
        "evidence_map": data.get("evidence_map") if isinstance(data.get("evidence_map"), list) else [],
        "elevator_pitch": str(data.get("elevator_pitch") or "").strip(),
        "star_stories": data.get("star_stories") if isinstance(data.get("star_stories"), list) else [],
        "interview_questions": _list(data.get("interview_questions"), 12),
    }
    required = ["executive_profile", "strategic_competencies", "experiences", "key_skills"]
    if any(not result[key] for key in required):
        raise ValueError("Claude omitted required resume sections.")
    return result


def tailor_resume(
    company: str,
    role: str,
    job_description: str,
    master_resume: str,
    completed_courses: list[str] | None = None,
    include_learning_roadmap: bool = True,
) -> dict[str, Any]:
    company = company.strip()
    role = role.strip()
    job_description = job_description.strip()
    master_resume = master_resume.strip()
    completed_courses = _list(completed_courses or [], 12)

    if not all((company, role, job_description, master_resume)):
        raise ValueError("Company, role, job description, and master resume are required.")

    prompt = f"""
You are an executive resume writer, ATS strategist, and evidence auditor.
Return ONLY valid JSON. Do not use markdown.

MISSION
Create a complete tailored executive resume from the candidate's master resume.
The primary objective is to maximize truthful recruiter-response and interview probability, not merely keyword count.
Do all work automatically. Never ask the candidate questions.
Apply every defensible ATS improvement directly to the resume.
Keep genuinely unsupported hard requirements outside the resume.

TARGET COMPANY: {company}
TARGET ROLE: {role}

JOB DESCRIPTION:
{job_description[:MAX_JD_CHARS]}

MASTER RESUME — THIS IS THE ONLY SOURCE OF CANDIDATE FACTS:
{master_resume[:MAX_RESUME_CHARS]}

CANDIDATE-CONFIRMED COMPLETED COURSES:
{json.dumps(completed_courses, ensure_ascii=False)}

OUTPUT SCHEMA
{{
  "candidate_name": "preserve from master resume",
  "contact_line": "preserve available phone/email/location/LinkedIn only",
  "company_style": "short description",
  "detected_industry": "target industry",
  "company_size": "likely company scale or Unknown",
  "company_focus": "short business focus",
  "industry_positioning": "truthful functional positioning, 3-8 words",
  "executive_profile": "90-125 words",
  "strategic_competencies": ["CATEGORY: item | item | item | item"],
  "experiences": [
    {{
      "dates": "exact original dates",
      "location": "exact original location if present",
      "title": "exact original title",
      "company": "exact original company",
      "positioning": "current role only: truthful target-aligned positioning line",
      "bullets": ["evidence-based executive bullet"]
    }}
  ],
  "education": ["preserve exact education"],
  "languages": ["preserve exact languages and levels"],
  "key_skills": ["supported skill"],
  "completed_courses": ["only candidate-confirmed completed course"],
  "auto_resume_enhancements": ["supported improvement already applied"],
  "unsupported_requirements": ["hard target requirement not evidenced"],
  "improvement_suggestions": ["automatic next-step plan without asking questions"],
  "cover_letter": "250-330 words",
  "linkedin_about": "130-180 words",
  "recruiter_hook": "one sentence explaining why the recruiter should call",
  "recruiter_objections": ["likely recruiter objection and truthful response strategy"],
  "recruiter_message": "70-110 word direct LinkedIn message",
  "referral_message": "70-110 word referral request",
  "follow_up_message": "50-90 word follow-up after 3-5 days",
  "screening_call_prep": ["concise screening-call talking point"],
  "key_achievements": ["short evidence-based highlight using an existing metric or scope"],
  "evidence_map": [{{"requirement":"target requirement","evidence":"exact resume evidence","confidence":"High|Medium|Low"}}],
  "elevator_pitch": "45-60 second spoken introduction",
  "star_stories": [{{"title":"story title","situation":"","task":"","action":"","result":"truthful result; no invented number"}}],
  "interview_questions": ["likely question followed by a concise answer strategy"]
}}

EVIDENCE RULES
1. Preserve every employer, title, date, location, education item, and language exactly. Never rename a role to the target role.
2. Never invent employers, industries, grocery experience, responsibilities, products, clients, metrics, budgets, team sizes, tools, certifications, courses, degrees, or achievements.
3. Never claim a numerical result unless that exact number exists in the master resume.
4. Never copy or lightly paraphrase a complete sentence from the job description.
5. Every rewritten bullet must trace to explicit evidence in the master resume.
6. Transferable mapping is allowed only when logically supported. Example: partnerships may support vendor collaboration, but must not become grocery supplier management.
7. Use cautious verbs such as supported, contributed, partnered, coordinated, or applied when evidence does not support ownership.
8. Do not add recommended tools to resume skills unless they are evidenced in the master resume.
9. Add completed courses only from CANDIDATE-CONFIRMED COMPLETED COURSES.
10. Recommended learning belongs in the development plan, never as completed education.

BULLET EXPANSION RULES
- Current role: 9-11 bullets.
- Second role: 6-8 bullets.
- Third role: 5-7 bullets.
- Older roles: 2-4 bullets each.
- Use fewer bullets if the master resume lacks enough evidence; do not fabricate filler.
- Each bullet should normally be 16-28 words. Keep wording concise to control generation cost.
- Start with a strong action verb.
- Emphasize leadership, commercial objective, scope, collaboration, decision-making, and business value when supported.
- Include measurable outcomes only when present in the master resume.
- Avoid repeated sentence structures and repeated keywords.

ATS GAP RESOLUTION
- HIGH confidence: insert naturally into profile, competencies, experience, and skills.
- MEDIUM confidence: insert only with qualified, defensible language.
- LOW confidence or unsupported: list under unsupported_requirements and never claim it in the resume.
- improvement_suggestions must provide immediate resume action, 30-day learning, 90-day career development, and interview preparation where relevant.

QUALITY CHECK BEFORE RETURNING
- The resume must sound like the candidate, not the job description.
- The current position title and employer must remain unchanged.
- Specific grocery, category-management, pricing ownership, supplier negotiation, logistics ownership, or tool proficiency must not appear unless present in the master resume.
- The first third of page one must make seniority, scope, commercial value, and target relevance immediately clear.
- Generate concise recruiter outreach, a 45-60 second elevator pitch, exactly 3 STAR stories, and no more than 8 likely interview questions.
- key_achievements must use only facts already evidenced in the master resume.
- evidence_map must explicitly show why each major job requirement is supported, transferable, or unsupported.
- Return exactly one JSON object.
"""

    response = get_client().messages.create(
        model=MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.05,
        messages=[{"role": "user", "content": prompt}],
    )
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise ValueError(
            "Claude response was truncated before the JSON finished. "
            "Please retry; the output limit has been increased in this version."
        )
    result = _normalize(_parse_json(_response_text(response)))

    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    # Claude 3 Haiku standard API pricing: $0.25/MTok input, $1.25/MTok output.
    # For an overridden model, this remains an estimate and is labelled accordingly in the UI.
    model_lower = MODEL.lower()
    if "claude-3-haiku" in model_lower and "3-5" not in model_lower:
        input_rate, output_rate = 0.25, 1.25
    elif "haiku" in model_lower:
        input_rate, output_rate = 1.0, 5.0
    else:
        input_rate, output_rate = 3.0, 15.0
    result["api_model"] = MODEL
    result["input_tokens"] = input_tokens
    result["output_tokens"] = output_tokens
    result["estimated_api_cost_usd"] = round(
        (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 4
    )

    learning = build_learning_plan(
        job_description=job_description,
        role=role,
        industry=result["detected_industry"],
        master_resume=master_resume,
    )
    result.update(learning)
    result["include_learning_roadmap"] = bool(include_learning_roadmap)

    scores = calculate_scores(job_description, master_resume, result)
    result.update(scores)
    result["missing_keywords"] = result["unsupported_requirements"][:10]
    return result
