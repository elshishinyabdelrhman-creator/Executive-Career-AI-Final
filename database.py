from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

try:
    from supabase import Client, create_client
except Exception:  # optional in local mode
    Client = Any  # type: ignore
    create_client = None  # type: ignore


class DatabaseError(RuntimeError):
    pass


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()


def using_supabase() -> bool:
    return bool(_secret("SUPABASE_URL") and (_secret("SUPABASE_SERVICE_ROLE_KEY") or _secret("SUPABASE_ANON_KEY")))


@st.cache_resource
def get_supabase() -> Client:
    url = _secret("SUPABASE_URL")
    key = _secret("SUPABASE_SERVICE_ROLE_KEY") or _secret("SUPABASE_ANON_KEY")
    if not url or not key or create_client is None:
        raise DatabaseError("Supabase is not configured; local SQLite mode is active.")
    return create_client(url, key)


DB_PATH = Path(os.getenv("LOCAL_DB_PATH", "/tmp/executive_career_hub.db"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS master_resume (
      id TEXT PRIMARY KEY, user_id TEXT UNIQUE NOT NULL, raw_resume TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS applications (
      id TEXT PRIMARY KEY, user_id TEXT NOT NULL, serial_number INTEGER, company_name TEXT, role_title TEXT, location TEXT,
      job_url TEXT, job_description TEXT, detected_industry TEXT, company_size TEXT, company_style TEXT,
      company_focus TEXT, ats_score INTEGER DEFAULT 0, match_score INTEGER DEFAULT 0,
      interview_probability INTEGER DEFAULT 0, resume_version TEXT, tailored_resume TEXT,
      cover_letter TEXT, linkedin_about TEXT, generation_data TEXT, completed_courses TEXT, resume_theme TEXT,
      application_status TEXT DEFAULT 'Applied', notes TEXT, interview_notes TEXT, recruiter_name TEXT, recruiter_email TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    """)
    # Safe migrations for existing local databases.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(applications)").fetchall()}
    migrations = {
        "serial_number": "INTEGER",
        "generation_data": "TEXT",
        "completed_courses": "TEXT",
        "resume_theme": "TEXT",
    }
    for column, column_type in migrations.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE applications ADD COLUMN {column} {column_type}")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def get_or_create_user(full_name: str, email: str) -> dict[str, Any]:
    if using_supabase():
        db = get_supabase()
        found = db.table("users").select("*").eq("email", email).limit(1).execute().data
        if found:
            return found[0]
        created = db.table("users").insert({"full_name": full_name, "email": email}).execute().data
        if not created:
            raise DatabaseError("Could not create user.")
        return created[0]
    with _conn() as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            return dict(row)
        uid = str(uuid.uuid4())
        db.execute("INSERT INTO users VALUES (?,?,?,?)", (uid, full_name, email, _now()))
        return dict(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


def save_master_resume(user_id: str, raw_resume: str) -> dict[str, Any]:
    if using_supabase():
        db = get_supabase()
        existing = db.table("master_resume").select("id").eq("user_id", user_id).limit(1).execute().data
        payload = {"user_id": user_id, "raw_resume": raw_resume, "updated_at": _now()}
        rows = (db.table("master_resume").update(payload).eq("id", existing[0]["id"]).execute().data
                if existing else db.table("master_resume").insert(payload).execute().data)
        if not rows:
            raise DatabaseError("Could not save master resume.")
        return rows[0]
    with _conn() as db:
        row = db.execute("SELECT id FROM master_resume WHERE user_id=?", (user_id,)).fetchone()
        rid = row["id"] if row else str(uuid.uuid4())
        db.execute("INSERT OR REPLACE INTO master_resume(id,user_id,raw_resume,updated_at) VALUES(?,?,?,?)",
                   (rid, user_id, raw_resume, _now()))
        return dict(db.execute("SELECT * FROM master_resume WHERE id=?", (rid,)).fetchone())


def get_master_resume(user_id: str) -> dict[str, Any] | None:
    if using_supabase():
        rows = get_supabase().table("master_resume").select("*").eq("user_id", user_id).limit(1).execute().data
        return rows[0] if rows else None
    with _conn() as db:
        return _dict(db.execute("SELECT * FROM master_resume WHERE user_id=?", (user_id,)).fetchone())


def repair_serial_numbers(user_id: str) -> list[dict[str, Any]]:
    """Renumber every application for one user as 1..N in chronological order.

    This repairs legacy NULL/0/duplicate serials and closes gaps after deletion.
    The database UUID remains the stable internal identifier.
    """
    if using_supabase():
        db = get_supabase()
        rows = (db.table("applications").select("id,serial_number,created_at")
                .eq("user_id", user_id).order("created_at", desc=False).execute().data or [])
        expected = list(range(1, len(rows) + 1))
        current = [int(r.get("serial_number") or 0) for r in rows]
        if current != expected:
            # Use temporary negative values first so a unique (user_id, serial_number)
            # index cannot collide while numbers are being reassigned.
            for i, row in enumerate(rows, start=1):
                db.table("applications").update({"serial_number": -i}).eq("id", row["id"]).execute()
            for i, row in enumerate(rows, start=1):
                db.table("applications").update({"serial_number": i}).eq("id", row["id"]).execute()
                row["serial_number"] = i
        return rows

    with _conn() as db:
        rows = [dict(x) for x in db.execute(
            "SELECT id, serial_number, created_at FROM applications WHERE user_id=? ORDER BY created_at ASC, id ASC",
            (user_id,),
        ).fetchall()]
        expected = list(range(1, len(rows) + 1))
        current = [int(r.get("serial_number") or 0) for r in rows]
        if current != expected:
            for i, row in enumerate(rows, start=1):
                db.execute("UPDATE applications SET serial_number=? WHERE id=?", (-i, row["id"]))
            for i, row in enumerate(rows, start=1):
                db.execute("UPDATE applications SET serial_number=? WHERE id=?", (i, row["id"]))
                row["serial_number"] = i
        return rows


def _next_serial_number(user_id: str) -> int:
    if using_supabase():
        rows = (get_supabase().table("applications").select("serial_number")
                .eq("user_id", user_id).order("serial_number", desc=True).limit(1).execute().data or [])
        return int(rows[0].get("serial_number") or 0) + 1 if rows else 1
    with _conn() as db:
        row = db.execute("SELECT COALESCE(MAX(serial_number), 0) AS maximum FROM applications WHERE user_id=?", (user_id,)).fetchone()
        return int(row["maximum"] or 0) + 1


def save_application(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = ["company_name","role_title","location","job_url","job_description","detected_industry",
               "company_size","company_style","company_focus","ats_score","match_score","interview_probability",
               "resume_version","tailored_resume","cover_letter","linkedin_about","generation_data",
               "completed_courses","resume_theme","application_status","notes"]
    row = {k: payload.get(k, "") for k in allowed}
    row.update(
        user_id=user_id,
        serial_number=int(payload.get("serial_number") or _next_serial_number(user_id)),
        ats_score=int(payload.get("ats_score", 0)),
        match_score=int(payload.get("match_score", 0)),
        interview_probability=int(payload.get("interview_probability", 0)),
        application_status=payload.get("application_status", "Applied"),
    )
    if using_supabase():
        rows = get_supabase().table("applications").insert(row).execute().data
        if not rows:
            raise DatabaseError("Could not save application.")
        return rows[0]
    if isinstance(row.get("generation_data"), (dict, list)):
        row["generation_data"] = json.dumps(row["generation_data"], ensure_ascii=False)
    if isinstance(row.get("completed_courses"), (dict, list)):
        row["completed_courses"] = json.dumps(row["completed_courses"], ensure_ascii=False)
    row.update(id=str(uuid.uuid4()), created_at=_now(), updated_at=_now())
    cols = list(row); marks = ",".join("?" for _ in cols)
    with _conn() as db:
        db.execute(f"INSERT INTO applications ({','.join(cols)}) VALUES ({marks})", [row[c] for c in cols])
        return dict(db.execute("SELECT * FROM applications WHERE id=?", (row["id"],)).fetchone())


def list_applications(user_id: str, search: str = "", limit: int = 500) -> list[dict[str, Any]]:
    # Repair old NULL/zero/duplicate serials. If database permissions block the
    # migration, the UI still gets a correct calculated display serial below.
    try:
        repair_serial_numbers(user_id)
    except Exception:
        pass

    if using_supabase():
        rows = (get_supabase().table("applications").select("*").eq("user_id", user_id)
                .order("created_at", desc=True).limit(limit).execute().data or [])
    else:
        with _conn() as db:
            rows = [dict(x) for x in db.execute(
                "SELECT * FROM applications WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()]

    # Reliable UI sequence: oldest application is #1. This is independent of
    # legacy database values and therefore can never display duplicate zeros.
    chronological = sorted(
        rows,
        key=lambda r: (str(r.get("created_at") or ""), str(r.get("id") or "")),
    )
    display_by_id = {str(r.get("id")): i for i, r in enumerate(chronological, start=1)}
    for row in rows:
        row["display_serial"] = display_by_id.get(
            str(row.get("id")), int(row.get("serial_number") or 0)
        )

    if search:
        term = search.casefold()
        rows = [r for r in rows if term in " ".join(
            str(r.get(k, "")) for k in ("company_name", "role_title", "application_status")
        ).casefold()]
    return rows


def update_application(application_id: str, payload: dict[str, Any]) -> None:
    allowed = {"application_status","notes","interview_notes","recruiter_name","recruiter_email"}
    update = {k:v for k,v in payload.items() if k in allowed}
    if not update: return
    update["updated_at"] = _now()
    if using_supabase():
        get_supabase().table("applications").update(update).eq("id", application_id).execute(); return
    with _conn() as db:
        db.execute(f"UPDATE applications SET {','.join(f'{k}=?' for k in update)} WHERE id=?", [*update.values(), application_id])


def delete_application(application_id: str) -> None:
    user_id = ""
    if using_supabase():
        db = get_supabase()
        found = db.table("applications").select("user_id").eq("id", application_id).limit(1).execute().data or []
        if found:
            user_id = str(found[0].get("user_id") or "")
        db.table("applications").delete().eq("id", application_id).execute()
        if user_id:
            repair_serial_numbers(user_id)
        return
    with _conn() as db:
        row = db.execute("SELECT user_id FROM applications WHERE id=?", (application_id,)).fetchone()
        user_id = str(row["user_id"]) if row else ""
        db.execute("DELETE FROM applications WHERE id=?", (application_id,))
    if user_id:
        repair_serial_numbers(user_id)


def dashboard_stats(user_id: str) -> dict[str, Any]:
    rows = list_applications(user_id)
    if not rows: return {"total":0,"avg_ats":0,"avg_match":0,"interviews":0,"offers":0,"response_rate":0}
    total=len(rows); interviews=sum(str(r.get("application_status","")).lower() in {"interview","offer"} for r in rows)
    return {"total":total,"avg_ats":round(sum(int(r.get("ats_score") or 0) for r in rows)/total),
            "avg_match":round(sum(int(r.get("match_score") or 0) for r in rows)/total),"interviews":interviews,
            "offers":sum(str(r.get("application_status","")).lower()=="offer" for r in rows),
            "response_rate":round(interviews*100/total)}
