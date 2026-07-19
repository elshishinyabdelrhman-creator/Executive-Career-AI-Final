from __future__ import annotations

import html
import re
from typing import Any

import streamlit as st
from pypdf import PdfReader

from ai_engine import tailor_resume
from database import (
    DatabaseError, dashboard_stats, delete_application, get_master_resume,
    get_or_create_user, list_applications, save_application, save_master_resume,
    update_application, using_supabase,
)
from pdf_generator import generate_pdf
from resume_builder import build_resume

st.set_page_config(page_title="Executive Career Hub V13 Economy", page_icon="📄", layout="wide")
USER = {"name": "Abdelrhman El Shishiny", "email": "elshishinyabdelrhman@gmail.com"}
STATUS_OPTIONS = ["Applied", "Interview", "Rejected", "Offer", "Withdrawn"]

st.markdown("""
<style>
.paper{background:white;border:1px solid #d8d8d8;padding:38px;white-space:pre-wrap;line-height:1.55;font-family:Arial,sans-serif;color:#111}
.stButton>button{width:100%;font-weight:700}.small-note{color:#666;font-size:.88rem}
</style>
""", unsafe_allow_html=True)


def extract_pdf(uploaded_file) -> str:
    reader = PdfReader(uploaded_file)
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise ValueError("No readable text was found in the PDF.")
    return text


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "resume"


def show_resume(text: str) -> None:
    st.markdown(f'<div class="paper">{html.escape(text)}</div>', unsafe_allow_html=True)


try:
    user = get_or_create_user(USER["name"], USER["email"])
except Exception as exc:
    st.error(f"Database initialization failed: {exc}")
    st.stop()

if not using_supabase():
    st.warning("Supabase is not configured. The app is running in local SQLite mode; data may reset when Streamlit Cloud restarts.")

st.title("Executive Career Hub V13 Economy")
st.caption("Truthful resume tailoring optimized for recruiter response and low API cost.")

tab_generate, tab_history, tab_dashboard = st.tabs(["Generate Resume", "Application History", "Dashboard"])

with tab_generate:
    st.subheader("1. Master resume")
    saved_master = get_master_resume(user["id"])
    resume_file = st.file_uploader("Upload or replace your master resume PDF", type=["pdf"])
    if saved_master and saved_master.get("raw_resume"):
        st.success("Master resume is available.")

    st.subheader("2. Target vacancy")
    resume_theme = st.selectbox("Resume design", ["Executive Premium", "ATS Classic", "Modern Corporate", "Consulting", "Big Tech", "Banking", "GCC Executive"], help="Executive Premium is recommended for recruiter impact. ATS Classic is the safest minimal design.")
    c1, c2, c3 = st.columns(3)
    company = c1.text_input("Target company")
    role = c2.text_input("Target role")
    location = c3.text_input("Location", value="Jeddah, Saudi Arabia")
    job_url = st.text_input("Job URL (optional)")
    completed_courses_text = st.text_area(
        "Your existing courses/certifications (optional)",
        placeholder="One per line. Only items entered here are treated as completed.", height=100,
    )
    jd = st.text_area("Job description", height=310)

    if st.button("Generate complete tailored resume", type="primary"):
        if not all([company.strip(), role.strip(), jd.strip()]):
            st.warning("Complete the company, role, and job description fields.")
        elif not resume_file and not (saved_master and saved_master.get("raw_resume")):
            st.warning("Upload a master resume first.")
        else:
            try:
                with st.spinner("Extracting evidence, resolving ATS gaps, and expanding executive experience..."):
                    if resume_file:
                        master_text = extract_pdf(resume_file)
                        save_master_resume(user["id"], master_text)
                    else:
                        master_text = saved_master["raw_resume"]
                    completed = [line.strip() for line in completed_courses_text.splitlines() if line.strip()]
                    result = tailor_resume(company, role, jd, master_text, completed)
                    resume_text = build_resume(result)
                    pdf_bytes = generate_pdf(resume_text, resume_theme)
                    row = save_application(user["id"], {
                        "company_name": company, "role_title": role, "location": location,
                        "job_url": job_url, "job_description": jd,
                        "detected_industry": result.get("detected_industry", ""),
                        "company_size": result.get("company_size", ""),
                        "company_style": result.get("company_style", ""),
                        "company_focus": result.get("company_focus", ""),
                        "ats_score": result.get("ats", 0), "match_score": result.get("match", 0),
                        "interview_probability": result.get("interview_probability", 0),
                        "resume_version": result.get("industry_positioning", ""),
                        "tailored_resume": resume_text, "cover_letter": result.get("cover_letter", ""),
                        "linkedin_about": result.get("linkedin_about", ""), "application_status": "Applied",
                    })
                    st.session_state.update(last_result=result, last_resume=resume_text, last_pdf=pdf_bytes,
                                            last_company=company, last_saved_id=row["id"], last_theme=resume_theme)
                    st.success("Resume generated and application saved.")
            except Exception as exc:
                st.error(f"Generation failed: {type(exc).__name__}: {exc}")

    if st.session_state.get("last_resume"):
        result: dict[str, Any] = st.session_state["last_result"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("ATS readiness", f"{result.get('ats_readiness', result.get('ats', 0))}%")
        m2.metric("Recruiter match", f"{result.get('recruiter_match', result.get('match', 0))}%")
        m3.metric("Hiring manager fit", f"{result.get('hiring_manager_fit', 0)}%")
        m4.metric("Interview probability", f"{result.get('interview_probability', 0)}%")
        st.info(f"Style: {result.get('company_style','—')} | Industry: {result.get('detected_industry','—')} | Positioning: {result.get('industry_positioning','—')}")
        st.caption(
            f"Claude model: {result.get('api_model', '—')} | "
            f"Tokens: {result.get('input_tokens', 0):,} in / {result.get('output_tokens', 0):,} out | "
            f"Estimated API cost: ${result.get('estimated_api_cost_usd', 0):.4f}"
        )

        with st.expander("ATS score breakdown", expanded=False):
            labels = {
                "keyword_score": "Keyword coverage", "leadership_score": "Leadership",
                "tools_score": "Tools", "responsibility_score": "Responsibilities",
                "commercial_score": "Commercial impact", "industry_score": "Industry",
                "evidence_score": "Evidence integrity", "transferability_score": "Transferable fit", "recruiter_hook_score": "Recruiter hook",
                "parseability_score": "ATS parseability",
            }
            for key, label in labels.items():
                st.progress(int(result.get(key, 0)) / 100, text=f"{label}: {result.get(key, 0)}%")

        with st.expander("ATS gaps, courses, and improvement plan", expanded=True):
            st.markdown("**Automatic resume enhancements already applied**")
            for item in result.get("auto_resume_enhancements", []) or ["No additional supported enhancements were required."]:
                st.write("✓", item)
            st.markdown("**Unsupported or weak requirements**")
            for item in result.get("unsupported_requirements", []) or ["No major unsupported hard requirements detected."]:
                st.write("•", item)
            st.markdown("**Completed courses added to the resume**")
            for item in result.get("completed_courses", []) or ["No completed courses were added."]:
                st.write("•", item)
            st.markdown("**AI professional development focus**")
            for item in result.get("recommended_courses", []): st.write("•", item)
            st.markdown("**Tools evidenced in your master resume**")
            st.write(" | ".join(result.get("evidenced_tools", [])) or "None detected.")
            st.markdown("**Tools to learn for this vacancy**")
            st.write(" | ".join(result.get("tools_to_learn", [])) or "No additional tools detected.")
            st.markdown("**Recommended books**")
            for item in result.get("recommended_books", []): st.write("•", item)
            st.markdown("**Priority industry keywords**")
            st.write(" | ".join(result.get("industry_keywords", [])))
            st.markdown("**Improvement plan**")
            for item in result.get("improvement_suggestions", []): st.write("•", item)

        a, b, c, d, e = st.tabs(["Resume preview", "Cover letter", "LinkedIn & Outreach", "Interview Conversion Pack", "Evidence Map"])
        with a:
            st.download_button("Download PDF", st.session_state["last_pdf"],
                file_name=f"{safe_name(st.session_state['last_company'])}_resume.pdf", mime="application/pdf")
            show_resume(st.session_state["last_resume"])
        with b: st.text_area("Cover letter", result.get("cover_letter", ""), height=380)
        with c:
            st.text_area("LinkedIn About", result.get("linkedin_about", ""), height=260)
            st.text_area("Recruiter message", result.get("recruiter_message", ""), height=160)
            st.text_area("Referral request", result.get("referral_message", ""), height=160)
            st.text_area("Follow-up after 3-5 days", result.get("follow_up_message", ""), height=140)
        with d:
            st.markdown("**Recruiter hook**")
            st.success(result.get("recruiter_hook", "—"))
            st.markdown("**45–60 second elevator pitch**")
            st.text_area("Elevator pitch", result.get("elevator_pitch", ""), height=160, label_visibility="collapsed")
            st.markdown("**Likely objections and truthful response strategy**")
            for item in result.get("recruiter_objections", []) or ["No major objection generated."]:
                st.write("•", item)
            st.markdown("**Screening-call talking points**")
            for item in result.get("screening_call_prep", []) or ["No preparation points generated."]:
                st.write("•", item)
            st.markdown("**Likely interview questions**")
            for item in result.get("interview_questions", []) or ["No questions generated."]:
                st.write("•", item)
            st.markdown("**STAR stories**")
            for story in result.get("star_stories", []):
                with st.expander(story.get("title", "Interview story")):
                    for label in ("situation", "task", "action", "result"):
                        st.markdown(f"**{label.title()}:** {story.get(label, '—')}")
        with e:
            st.markdown("**Evidence-to-requirement map**")
            for item in result.get("evidence_map", []):
                confidence = item.get("confidence", "—")
                st.markdown(f"**{item.get('requirement','Requirement')}** — `{confidence}`  \n{item.get('evidence','No evidence supplied')}")

with tab_history:
    st.header("Application History")
    search = st.text_input("Search company, role, or status")
    try:
        rows = list_applications(user["id"], search)
    except DatabaseError as exc:
        st.error(str(exc)); rows = []
    if not rows: st.info("No saved applications found.")
    for row in rows:
        with st.expander(f"{row.get('company_name','')} | {row.get('role_title','')} | Match {row.get('match_score',0)}% | ATS {row.get('ats_score',0)}%"):
            status = st.selectbox("Status", STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(row.get("application_status", "Applied")) if row.get("application_status") in STATUS_OPTIONS else 0,
                key=f"status_{row['id']}")
            notes = st.text_area("Notes", row.get("notes", "") or "", key=f"notes_{row['id']}")
            x, y, z = st.columns(3)
            if x.button("Save", key=f"save_{row['id']}"):
                update_application(row["id"], {"application_status": status, "notes": notes}); st.rerun()
            if y.button("Delete", key=f"delete_{row['id']}"):
                delete_application(row["id"]); st.rerun()
            z.download_button("Download PDF", generate_pdf(row.get("tailored_resume", "") or "", "Executive Premium"),
                file_name=f"{safe_name(row.get('company_name','company'))}_resume.pdf", mime="application/pdf", key=f"pdf_{row['id']}")
            show_resume(row.get("tailored_resume", "") or "")

with tab_dashboard:
    stats = dashboard_stats(user["id"])
    a, b, c, d, e, f = st.columns(6)
    a.metric("Applications", stats["total"]); b.metric("Average ATS", f"{stats['avg_ats']}%")
    c.metric("Average Match", f"{stats['avg_match']}%"); d.metric("Interviews", stats["interviews"]); e.metric("Offers", stats["offers"]); f.metric("Response rate", f"{stats.get('response_rate',0)}%")
