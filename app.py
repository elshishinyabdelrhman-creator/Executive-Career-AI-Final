from __future__ import annotations

import html
import re
from typing import Any

import streamlit as st
from pypdf import PdfReader

from ai_engine import tailor_resume
from database import (
    DatabaseError,
    dashboard_stats,
    delete_application,
    get_master_resume,
    get_or_create_user,
    list_applications,
    save_application,
    save_master_resume,
    test_connection,
    update_application,
)
from pdf_generator import generate_pdf
from premium_resume_generator import generate_premium_docx, generate_premium_pdf
from resume_builder import build_resume


st.set_page_config(
    page_title="Executive Career Hub",
    page_icon="📄",
    layout="wide",
)

USER = {
    "name": "Abdelrhman El Shishiny",
    "email": "elshishinyabdelrhman@gmail.com",
}

STATUS_OPTIONS = [
    "Applied",
    "Screening",
    "Interview",
    "Assessment",
    "Final Interview",
    "Offer",
    "Rejected",
    "Withdrawn",
]

st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1450px;
    }

    .paper {
        background: white;
        border: 1px solid #d8d8d8;
        border-radius: 10px;
        padding: 36px;
        white-space: pre-wrap;
        line-height: 1.52;
        font-family: Arial, sans-serif;
        color: #111;
        box-shadow: 0 2px 12px rgba(0,0,0,.04);
    }

    .subtle-card {
        border: 1px solid #e5e5e5;
        border-radius: 10px;
        padding: 16px;
        background: white;
    }

    .stButton > button {
        width: 100%;
        font-weight: 700;
    }

    .stDownloadButton > button {
        width: 100%;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def extract_pdf(uploaded_file) -> str:
    reader = PdfReader(uploaded_file)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 200:
        raise ValueError(
            "The uploaded PDF contains too little readable text. "
            "Use a text-based PDF, not a scanned image."
        )

    return text


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return cleaned or "resume"


def show_resume(text: str) -> None:
    st.markdown(
        f'<div class="paper">{html.escape(text or "")}</div>',
        unsafe_allow_html=True,
    )


def initialize_session() -> None:
    defaults = {
        "last_result": None,
        "last_resume": "",
        "last_pdf": b"",
        "last_premium_pdf": b"",
        "last_premium_docx": b"",
        "last_company": "",
        "last_saved_id": "",
        "master_resume_text": "",
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def parse_completed_courses(raw_text: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()

    for line in str(raw_text or "").splitlines():
        course = line.strip(" •-\t")
        key = course.casefold()

        if course and key not in seen:
            seen.add(key)
            items.append(course)

    return items


def display_result(
    result: dict[str, Any],
    resume_text: str,
    pdf_bytes: bytes,
    premium_pdf_bytes: bytes,
    premium_docx_bytes: bytes,
) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Evidence fit", f"{int(result.get('match', 0))}%")
    c2.metric("Tailored ATS coverage", f"{int(result.get('ats', 0))}%")
    c3.metric(
        "Interview estimate",
        f"{int(result.get('interview_probability', 0))}%",
    )
    c4.metric("Truthfulness", f"{int(result.get('truthfulness_score', 100))}%")

    st.info(
        f"Style: {result.get('company_style', '—')} | "
        f"Industry: {result.get('detected_industry', '—')} | "
        f"Positioning: {result.get('industry_positioning', '—')}"
    )

    with st.expander("Requirement coverage, evidence gaps, and improvement plan"):
        matched = result.get("matched_requirements", [])
        transferable = result.get("transferable_requirements", [])
        missing = result.get("unsupported_requirements", result.get("missing_keywords", []))
        removed_claims = result.get("unsupported_generated_claims", [])
        recommended = result.get("recommended_courses", [])
        suggestions = result.get("improvement_suggestions", [])
        selected = result.get("selected_completed_courses", [])

        st.markdown("**Matched in the tailored resume**")
        if matched:
            for item in matched:
                st.write("•", item)
        else:
            st.write("No direct requirement matches detected.")

        st.markdown("**Covered through transferable experience**")
        if transferable:
            for item in transferable:
                st.write("•", item)
        else:
            st.write("No transferable matches detected.")

        st.markdown("**Real evidence gaps — not inserted as experience**")
        if missing:
            for item in missing:
                st.write("•", item)
        else:
            st.write("No material evidence gaps detected.")

        st.markdown("**Unsupported AI claims automatically removed**")
        if removed_claims:
            for item in removed_claims:
                st.write("•", item)
        else:
            st.write("No unsupported critical claims were detected.")

        st.markdown("**Completed courses added to the resume**")
        if selected:
            for item in selected:
                st.write("•", item)
        else:
            st.write("No completed courses were added.")

        st.markdown("**Recommended courses — not listed as completed**")
        if recommended:
            for item in recommended:
                st.write("•", item)
        else:
            st.write("No additional course recommendations.")

        st.markdown("**Improvement suggestions**")
        if suggestions:
            for item in suggestions:
                st.write("•", item)
        else:
            st.write("No additional suggestions.")

    st.markdown("### Download versions")
    d1, d2, d3 = st.columns(3)

    d1.download_button(
        "Download Premium PDF",
        data=premium_pdf_bytes,
        file_name=f"{safe_name(st.session_state['last_company'])}_premium_resume.pdf",
        mime="application/pdf",
        disabled=not bool(premium_pdf_bytes),
    )
    d2.download_button(
        "Download Premium Word",
        data=premium_docx_bytes,
        file_name=f"{safe_name(st.session_state['last_company'])}_premium_resume.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        disabled=not bool(premium_docx_bytes),
    )
    d3.download_button(
        "Download ATS PDF",
        data=pdf_bytes,
        file_name=f"{safe_name(st.session_state['last_company'])}_ats_resume.pdf",
        mime="application/pdf",
        disabled=not bool(pdf_bytes),
    )

    cover_letter = str(result.get("cover_letter", "") or "")
    st.download_button(
        "Download cover letter",
        data=cover_letter.encode("utf-8"),
        file_name=f"{safe_name(st.session_state['last_company'])}_cover_letter.txt",
        mime="text/plain",
        disabled=not bool(cover_letter),
    )

    with st.expander("Cover letter"):
        st.text_area(
            "Generated cover letter",
            value=cover_letter,
            height=260,
            disabled=True,
            label_visibility="collapsed",
        )

    with st.expander("LinkedIn About"):
        st.text_area(
            "Generated LinkedIn About",
            value=str(result.get("linkedin_about", "") or ""),
            height=220,
            disabled=True,
            label_visibility="collapsed",
        )

    st.markdown("### Resume preview")
    show_resume(resume_text)


initialize_session()

try:
    test_connection()
    user = get_or_create_user(USER["name"], USER["email"])
except Exception as exc:
    st.error(f"Supabase connection failed: {exc}")
    st.stop()


st.title("Executive Career Hub V16")
st.caption(
    "Evidence-based fit scoring, post-tailoring ATS coverage, claim validation, dynamic career highlights, "
    "premium PDF/DOCX export, Supabase history, and application tracking."
)

tab_generate, tab_history, tab_dashboard = st.tabs(
    [
        "Generate Resume",
        "Application History",
        "Dashboard",
    ]
)


with tab_generate:
    st.subheader("1. Master resume")

    saved_master = get_master_resume(user["id"])

    if saved_master and not st.session_state["master_resume_text"]:
        st.session_state["master_resume_text"] = str(
            saved_master.get("raw_resume", "") or ""
        )

    master_file = st.file_uploader(
        "Upload or replace your master resume PDF",
        type=["pdf"],
        help="The text is stored in Supabase so you do not need to upload it every time.",
    )

    save_master_col, master_status_col = st.columns([1, 2])

    if save_master_col.button("Save master resume", type="secondary"):
        if not master_file:
            st.warning("Upload a PDF first.")
        else:
            try:
                master_text = extract_pdf(master_file)
                save_master_resume(
                    user["id"],
                    raw_resume=master_text,
                    structured_resume={},
                )
                st.session_state["master_resume_text"] = master_text
                st.success("Master resume saved in Supabase.")
            except Exception as exc:
                st.error(f"Could not save master resume: {exc}")

    if st.session_state["master_resume_text"]:
        master_status_col.success("Master resume is available.")
    else:
        master_status_col.warning("No master resume is saved yet.")

    st.divider()
    st.subheader("2. Target vacancy")

    left, right = st.columns(2)

    with left:
        company = st.text_input("Target company")
        role = st.text_input("Target role")
        location = st.text_input(
            "Location",
            value="Jeddah, Saudi Arabia",
        )
        job_url = st.text_input("Job URL (optional)")

    with right:
        completed_courses_text = st.text_area(
            "Completed courses/certifications only",
            placeholder=(
                "One per line. Only items you actually completed "
                "can appear in the resume."
            ),
            height=168,
        )

    jd = st.text_area(
        "Job description",
        height=300,
        placeholder="Paste the complete job description here.",
    )

    uploaded_for_generation = st.file_uploader(
        "Use a different resume for this application (optional)",
        type=["pdf"],
        key="application_resume_override",
        help="Leave empty to use the master resume saved in Supabase.",
    )

    if st.button("Generate tailored resume", type="primary"):
        if not company.strip() or not role.strip() or not jd.strip():
            st.warning("Complete the company, role, and job description.")
        else:
            try:
                if uploaded_for_generation:
                    master_text = extract_pdf(uploaded_for_generation)
                else:
                    master_text = st.session_state["master_resume_text"]

                if not master_text:
                    raise ValueError(
                        "Save a master resume or upload a resume for this application."
                    )

                completed_courses = parse_completed_courses(completed_courses_text)

                with st.spinner(
                    "Analyzing the role and tailoring defensible resume sections..."
                ):
                    result = tailor_resume(
                        company=company,
                        role=role,
                        job_description=jd,
                        master_resume=master_text,
                        completed_courses=completed_courses,
                    )

                    resume_text = build_resume(result)
                    pdf_bytes = generate_pdf(resume_text)
                    premium_pdf_bytes = generate_premium_pdf(
                        result,
                        target_role=role,
                    )
                    premium_docx_bytes = generate_premium_docx(
                        result,
                        target_role=role,
                    )

                    app_row = save_application(
                        user["id"],
                        {
                            "company_name": company,
                            "role_title": role,
                            "location": location,
                            "job_url": job_url,
                            "job_description": jd,
                            "detected_industry": result.get(
                                "detected_industry",
                                "",
                            ),
                            "company_size": result.get("company_size", ""),
                            "company_style": result.get("company_style", ""),
                            "company_focus": result.get("company_focus", ""),
                            "ats_score": result.get("ats", 0),
                            "match_score": result.get("match", 0),
                            "interview_probability": result.get(
                                "interview_probability",
                                0,
                            ),
                            "resume_version": result.get(
                                "industry_positioning",
                                "",
                            ),
                            "tailored_resume": resume_text,
                            "cover_letter": result.get("cover_letter", ""),
                            "linkedin_about": result.get("linkedin_about", ""),
                            "application_status": "Applied",
                        },
                    )

                    st.session_state["last_result"] = result
                    st.session_state["last_resume"] = resume_text
                    st.session_state["last_pdf"] = pdf_bytes
                    st.session_state["last_premium_pdf"] = premium_pdf_bytes
                    st.session_state["last_premium_docx"] = premium_docx_bytes
                    st.session_state["last_company"] = company
                    st.session_state["last_saved_id"] = app_row["id"]

                    st.success("Resume generated and application saved.")

            except Exception as exc:
                st.error(
                    f"Generation failed: {type(exc).__name__}: {exc}"
                )

    if st.session_state.get("last_resume"):
        st.divider()
        display_result(
            st.session_state["last_result"],
            st.session_state["last_resume"],
            st.session_state["last_pdf"],
            st.session_state["last_premium_pdf"],
            st.session_state["last_premium_docx"],
        )


with tab_history:
    st.header("Application History")

    filter_col1, filter_col2 = st.columns([2, 1])

    search = filter_col1.text_input(
        "Search",
        placeholder="Company, role, status, industry, or JD keyword",
    )

    status_filter = filter_col2.selectbox(
        "Status filter",
        ["All", *STATUS_OPTIONS],
    )

    try:
        rows = list_applications(
            user["id"],
            search=search,
            status=status_filter,
            limit=2000,
        )
    except DatabaseError as exc:
        st.error(str(exc))
        rows = []

    st.caption(f"{len(rows)} saved applications")

    if not rows:
        st.info("No saved applications found.")

    for row in rows:
        title = (
            f"{row.get('company_name', '')} | "
            f"{row.get('role_title', '')} | "
            f"{row.get('application_status', 'Applied')} | "
            f"Match {row.get('match_score', 0)}% | "
            f"ATS {row.get('ats_score', 0)}%"
        )

        with st.expander(title):
            info1, info2, info3, info4 = st.columns(4)
            info1.write(
                f"**Created:** {str(row.get('created_at', ''))[:10]}"
            )
            info2.write(
                f"**Industry:** {row.get('detected_industry', '') or '—'}"
            )
            info3.write(
                f"**Interview estimate:** "
                f"{row.get('interview_probability', 0)}%"
            )
            info4.write(
                f"**Location:** {row.get('location', '') or '—'}"
            )

            current_status = row.get("application_status", "Applied")
            status_index = (
                STATUS_OPTIONS.index(current_status)
                if current_status in STATUS_OPTIONS
                else 0
            )

            edit1, edit2 = st.columns(2)

            status = edit1.selectbox(
                "Status",
                STATUS_OPTIONS,
                index=status_index,
                key=f"status_{row['id']}",
            )

            recruiter_name = edit2.text_input(
                "Recruiter name",
                value=row.get("recruiter_name", "") or "",
                key=f"recruiter_{row['id']}",
            )

            recruiter_email = st.text_input(
                "Recruiter email",
                value=row.get("recruiter_email", "") or "",
                key=f"recruiter_email_{row['id']}",
            )

            notes = st.text_area(
                "Notes",
                value=row.get("notes", "") or "",
                key=f"notes_{row['id']}",
            )

            interview_notes = st.text_area(
                "Interview notes",
                value=row.get("interview_notes", "") or "",
                key=f"interview_notes_{row['id']}",
            )

            b1, b2, b3 = st.columns(3)

            if b1.button(
                "Save updates",
                key=f"save_{row['id']}",
            ):
                update_application(
                    row["id"],
                    {
                        "application_status": status,
                        "notes": notes,
                        "interview_notes": interview_notes,
                        "recruiter_name": recruiter_name,
                        "recruiter_email": recruiter_email,
                    },
                    user_id=user["id"],
                )
                st.success("Updated.")
                st.rerun()

            if b2.button(
                "Delete",
                key=f"delete_{row['id']}",
            ):
                delete_application(
                    row["id"],
                    user_id=user["id"],
                )
                st.success("Deleted.")
                st.rerun()

            resume_text = row.get("tailored_resume", "") or ""

            try:
                history_pdf = generate_pdf(resume_text)
            except Exception:
                history_pdf = b""

            b3.download_button(
                "Download PDF",
                data=history_pdf,
                file_name=(
                    f"{safe_name(row.get('company_name', 'company'))}_resume.pdf"
                ),
                mime="application/pdf",
                key=f"pdf_{row['id']}",
                disabled=not bool(history_pdf),
            )

            st.markdown("#### Job Description")
            st.text_area(
                "Saved JD",
                value=row.get("job_description", "") or "",
                height=190,
                disabled=True,
                key=f"jd_{row['id']}",
                label_visibility="collapsed",
            )

            st.markdown("#### Resume")
            show_resume(resume_text)

            if row.get("cover_letter"):
                st.markdown("#### Cover Letter")
                st.text_area(
                    "Cover letter",
                    value=row["cover_letter"],
                    height=250,
                    disabled=True,
                    key=f"cl_{row['id']}",
                    label_visibility="collapsed",
                )

            if row.get("linkedin_about"):
                st.markdown("#### LinkedIn About")
                st.text_area(
                    "LinkedIn About",
                    value=row["linkedin_about"],
                    height=200,
                    disabled=True,
                    key=f"linkedin_{row['id']}",
                    label_visibility="collapsed",
                )


with tab_dashboard:
    st.header("Dashboard")

    try:
        stats = dashboard_stats(user["id"])
    except DatabaseError as exc:
        st.error(str(exc))
        stats = {
            "total": 0,
            "avg_ats": 0,
            "avg_match": 0,
            "avg_interview_probability": 0,
            "interviews": 0,
            "offers": 0,
            "rejected": 0,
            "response_rate": 0,
        }

    a, b, c, d = st.columns(4)
    a.metric("Applications", stats["total"])
    b.metric("Average ATS", f"{stats['avg_ats']}%")
    c.metric("Average Match", f"{stats['avg_match']}%")
    d.metric(
        "Average interview estimate",
        f"{stats['avg_interview_probability']}%",
    )

    e, f, g, h = st.columns(4)
    e.metric("Interviews", stats["interviews"])
    f.metric("Offers", stats["offers"])
    g.metric("Rejected", stats["rejected"])
    h.metric("Response rate", f"{stats['response_rate']}%")

    if stats["total"] >= 30 and stats["interviews"] == 0:
        st.warning(
            "No interviews are recorded yet. Review role targeting, "
            "resume positioning, application channels, and referral outreach."
        )
