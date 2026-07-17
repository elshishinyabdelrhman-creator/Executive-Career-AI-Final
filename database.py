from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from supabase import Client, create_client


class DatabaseError(RuntimeError):
    pass


@st.cache_resource
def get_supabase() -> Client:
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
    except Exception:
        url = key = ""
    url = str(url or os.getenv("SUPABASE_URL", "")).strip()
    key = str(key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")).strip()
    if not url or not key:
        raise DatabaseError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(url, key)


def get_or_create_user(full_name: str, email: str) -> dict[str, Any]:
    db = get_supabase()
    found = db.table("users").select("*").eq("email", email).limit(1).execute().data
    if found:
        return found[0]
    created = db.table("users").insert({"full_name": full_name, "email": email}).execute().data
    if not created:
        raise DatabaseError("Could not create user.")
    return created[0]


def save_master_resume(user_id: str, raw_resume: str) -> dict[str, Any]:
    db = get_supabase()
    existing = db.table("master_resume").select("id").eq("user_id", user_id).limit(1).execute().data
    payload = {"user_id": user_id, "raw_resume": raw_resume, "updated_at": datetime.now(timezone.utc).isoformat()}
    if existing:
        rows = db.table("master_resume").update(payload).eq("id", existing[0]["id"]).execute().data
    else:
        rows = db.table("master_resume").insert(payload).execute().data
    if not rows:
        raise DatabaseError("Could not save master resume.")
    return rows[0]


def get_master_resume(user_id: str) -> dict[str, Any] | None:
    rows = db_rows = get_supabase().table("master_resume").select("*").eq("user_id", user_id).limit(1).execute().data
    return rows[0] if rows else None


def save_application(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "company_name", "role_title", "location", "job_url", "job_description",
        "detected_industry", "company_size", "company_style", "company_focus",
        "ats_score", "match_score", "interview_probability", "resume_version",
        "tailored_resume", "cover_letter", "linkedin_about", "application_status", "notes",
    }
    row = {key: payload.get(key, "") for key in allowed}
    row["user_id"] = user_id
    row["ats_score"] = int(payload.get("ats_score", 0))
    row["match_score"] = int(payload.get("match_score", 0))
    row["interview_probability"] = int(payload.get("interview_probability", 0))
    row["application_status"] = payload.get("application_status", "Applied")
    rows = get_supabase().table("applications").insert(row).execute().data
    if not rows:
        raise DatabaseError("Could not save application.")
    return rows[0]


def list_applications(user_id: str, search: str = "", limit: int = 500) -> list[dict[str, Any]]:
    rows = (
        get_supabase().table("applications").select("*").eq("user_id", user_id)
        .order("created_at", desc=True).limit(limit).execute().data or []
    )
    if search:
        term = search.casefold()
        rows = [row for row in rows if term in " ".join(str(row.get(k, "")) for k in ("company_name", "role_title", "application_status")).casefold()]
    return rows


def update_application(application_id: str, payload: dict[str, Any]) -> None:
    allowed = {"application_status", "notes", "interview_notes", "recruiter_name", "recruiter_email"}
    update = {k: v for k, v in payload.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    get_supabase().table("applications").update(update).eq("id", application_id).execute()


def delete_application(application_id: str) -> None:
    get_supabase().table("applications").delete().eq("id", application_id).execute()


def dashboard_stats(user_id: str) -> dict[str, Any]:
    rows = list_applications(user_id)
    if not rows:
        return {"total": 0, "avg_ats": 0, "avg_match": 0, "interviews": 0, "offers": 0}
    total = len(rows)
    return {
        "total": total,
        "avg_ats": round(sum(int(r.get("ats_score") or 0) for r in rows) / total),
        "avg_match": round(sum(int(r.get("match_score") or 0) for r in rows) / total),
        "interviews": sum(str(r.get("application_status", "")).lower() == "interview" for r in rows),
        "offers": sum(str(r.get("application_status", "")).lower() == "offer" for r in rows),
    }
