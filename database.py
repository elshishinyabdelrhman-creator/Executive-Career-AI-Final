from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

import streamlit as st
from supabase import Client, create_client


T = TypeVar("T")


class DatabaseError(RuntimeError):
    """Raised when a Supabase database operation fails."""


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(float(value or 0))))
    except (TypeError, ValueError):
        return 0


def _run(operation: Callable[[], T], action: str, retries: int = 2) -> T:
    """
    Run a Supabase operation with a small retry for temporary network errors.
    Authentication, schema, and validation errors are returned immediately.
    """
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()

            non_retryable = (
                "invalid api key",
                "permission denied",
                "row-level security",
                "could not find the table",
                "schema cache",
                "duplicate key",
                "violates",
                "401",
                "403",
                "404",
            )

            if any(token in message for token in non_retryable) or attempt >= retries:
                break

            time.sleep(0.6 * (attempt + 1))

    raise DatabaseError(f"{action} failed: {last_error}") from last_error


@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    """
    Create one cached Supabase client.

    Preferred server-side secret:
      SUPABASE_SERVICE_ROLE_KEY

    Fallback names are supported to avoid breaking existing installations.
    Never commit any of these values to GitHub.
    """
    url = _secret("SUPABASE_URL")
    key = (
        _secret("SUPABASE_SERVICE_ROLE_KEY")
        or _secret("SUPABASE_SECRET_KEY")
        or _secret("SUPABASE_KEY")
    )

    if not url:
        raise DatabaseError("Missing SUPABASE_URL in .streamlit/secrets.toml.")

    if not key:
        raise DatabaseError(
            "Missing SUPABASE_SERVICE_ROLE_KEY in .streamlit/secrets.toml."
        )

    try:
        return create_client(url, key)
    except Exception as exc:
        raise DatabaseError(f"Could not create Supabase client: {exc}") from exc


def test_connection() -> bool:
    def operation() -> bool:
        get_supabase().table("users").select("id").limit(1).execute()
        return True

    return _run(operation, "Supabase connection test", retries=0)


def get_or_create_user(full_name: str, email: str) -> dict[str, Any]:
    clean_name = str(full_name or "").strip()
    clean_email = str(email or "").strip().lower()

    if not clean_name or not clean_email:
        raise DatabaseError("Full name and email are required.")

    def operation() -> dict[str, Any]:
        db = get_supabase()

        found = (
            db.table("users")
            .select("*")
            .eq("email", clean_email)
            .limit(1)
            .execute()
            .data
            or []
        )

        if found:
            user = found[0]

            if user.get("full_name") != clean_name:
                updated = (
                    db.table("users")
                    .update({"full_name": clean_name, "updated_at": _now()})
                    .eq("id", user["id"])
                    .execute()
                    .data
                    or []
                )
                if updated:
                    return updated[0]

            return user

        created = (
            db.table("users")
            .insert(
                {
                    "full_name": clean_name,
                    "email": clean_email,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )
            .execute()
            .data
            or []
        )

        if not created:
            raise DatabaseError("Supabase returned no user after insert.")

        return created[0]

    return _run(operation, "Get or create user")


def save_master_resume(
    user_id: str,
    raw_resume: str,
    structured_resume: dict[str, Any] | None = None,
) -> dict[str, Any]:
    structured = structured_resume or {}

    payload = {
        "user_id": user_id,
        "raw_resume": str(raw_resume or ""),
        "executive_summary": structured.get("executive_summary", ""),
        "experiences": structured.get("experiences", []),
        "education": structured.get("education", []),
        "skills": structured.get("skills", []),
        "certifications": structured.get("certifications", []),
        "courses": structured.get("courses", []),
        "tools": structured.get("tools", []),
        "core_competencies": structured.get("core_competencies", []),
        "languages": structured.get("languages", []),
        "achievements": structured.get("achievements", []),
        "updated_at": _now(),
    }

    def operation() -> dict[str, Any]:
        db = get_supabase()

        existing = (
            db.table("master_resume")
            .select("id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
            or []
        )

        if existing:
            rows = (
                db.table("master_resume")
                .update(payload)
                .eq("id", existing[0]["id"])
                .eq("user_id", user_id)
                .execute()
                .data
                or []
            )
        else:
            payload["created_at"] = _now()
            rows = db.table("master_resume").insert(payload).execute().data or []

        if not rows:
            raise DatabaseError("Supabase returned no master resume after save.")

        return rows[0]

    return _run(operation, "Save master resume")


def get_master_resume(user_id: str) -> dict[str, Any] | None:
    def operation() -> dict[str, Any] | None:
        rows = (
            get_supabase()
            .table("master_resume")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None

    return _run(operation, "Load master resume")


def save_application(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    company_name = str(payload.get("company_name", "")).strip()
    role_title = str(payload.get("role_title", "")).strip()

    if not company_name or not role_title:
        raise DatabaseError("Company name and role title are required.")

    row = {
        "user_id": user_id,
        "company_name": company_name,
        "role_title": role_title,
        "location": str(payload.get("location", "") or ""),
        "job_url": str(payload.get("job_url", "") or ""),
        "job_description": str(payload.get("job_description", "") or ""),
        "detected_industry": str(payload.get("detected_industry", "") or ""),
        "company_size": str(payload.get("company_size", "") or ""),
        "company_style": str(payload.get("company_style", "") or ""),
        "company_focus": str(payload.get("company_focus", "") or ""),
        "ats_score": _score(payload.get("ats_score")),
        "match_score": _score(payload.get("match_score")),
        "interview_probability": _score(payload.get("interview_probability")),
        "resume_version": str(payload.get("resume_version", "") or ""),
        "tailored_resume": str(payload.get("tailored_resume", "") or ""),
        "cover_letter": str(payload.get("cover_letter", "") or ""),
        "linkedin_about": str(payload.get("linkedin_about", "") or ""),
        "interview_notes": str(payload.get("interview_notes", "") or ""),
        "application_status": str(
            payload.get("application_status", "Applied") or "Applied"
        ),
        "recruiter_name": str(payload.get("recruiter_name", "") or ""),
        "recruiter_email": str(payload.get("recruiter_email", "") or ""),
        "notes": str(payload.get("notes", "") or ""),
        "created_at": _now(),
        "updated_at": _now(),
    }

    def operation() -> dict[str, Any]:
        rows = (
            get_supabase()
            .table("applications")
            .insert(row)
            .execute()
            .data
            or []
        )

        if not rows:
            raise DatabaseError("Supabase returned no application after insert.")

        return rows[0]

    return _run(operation, "Save application")


def get_application(
    user_id: str,
    application_id: str,
) -> dict[str, Any] | None:
    def operation() -> dict[str, Any] | None:
        rows = (
            get_supabase()
            .table("applications")
            .select("*")
            .eq("id", application_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None

    return _run(operation, "Load application")


def list_applications(
    user_id: str,
    search: str = "",
    status: str = "",
    limit: int = 1000,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 1000), 5000))

    def operation() -> list[dict[str, Any]]:
        query = (
            get_supabase()
            .table("applications")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(safe_limit)
        )

        if status and status != "All":
            query = query.eq("application_status", status)

        rows = query.execute().data or []

        if search:
            needle = search.strip().casefold()
            rows = [
                row
                for row in rows
                if needle in str(row.get("company_name", "")).casefold()
                or needle in str(row.get("role_title", "")).casefold()
                or needle in str(row.get("application_status", "")).casefold()
                or needle in str(row.get("detected_industry", "")).casefold()
                or needle in str(row.get("job_description", "")).casefold()
            ]

        return rows

    return _run(operation, "Load application history")


def update_application(
    application_id: str,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any] | None:
    allowed = {
        "application_status",
        "notes",
        "interview_notes",
        "recruiter_name",
        "recruiter_email",
        "job_url",
        "location",
    }

    safe_payload = {
        key: value
        for key, value in payload.items()
        if key in allowed
    }

    if not safe_payload:
        return None

    safe_payload["updated_at"] = _now()

    def operation() -> dict[str, Any] | None:
        query = (
            get_supabase()
            .table("applications")
            .update(safe_payload)
            .eq("id", application_id)
        )

        if user_id:
            query = query.eq("user_id", user_id)

        rows = query.execute().data or []
        return rows[0] if rows else None

    return _run(operation, "Update application")


def delete_application(
    application_id: str,
    user_id: str | None = None,
) -> None:
    def operation() -> None:
        query = (
            get_supabase()
            .table("applications")
            .delete()
            .eq("id", application_id)
        )

        if user_id:
            query = query.eq("user_id", user_id)

        query.execute()

    _run(operation, "Delete application")


def dashboard_stats(user_id: str) -> dict[str, Any]:
    rows = list_applications(user_id, limit=5000)

    if not rows:
        return {
            "total": 0,
            "avg_ats": 0,
            "avg_match": 0,
            "avg_interview_probability": 0,
            "interviews": 0,
            "offers": 0,
            "rejected": 0,
            "response_rate": 0,
        }

    total = len(rows)
    statuses = [
        str(row.get("application_status", "") or "").strip().casefold()
        for row in rows
    ]

    interviews = sum(status == "interview" for status in statuses)
    offers = sum(status == "offer" for status in statuses)
    rejected = sum(status == "rejected" for status in statuses)
    responses = interviews + offers + rejected

    return {
        "total": total,
        "avg_ats": round(
            sum(_score(row.get("ats_score")) for row in rows) / total
        ),
        "avg_match": round(
            sum(_score(row.get("match_score")) for row in rows) / total
        ),
        "avg_interview_probability": round(
            sum(_score(row.get("interview_probability")) for row in rows)
            / total
        ),
        "interviews": interviews,
        "offers": offers,
        "rejected": rejected,
        "response_rate": round((responses / total) * 100),
    }


def count_applications(user_id: str) -> int:
    return dashboard_stats(user_id)["total"]
