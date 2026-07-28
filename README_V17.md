# Executive Career Hub V17 — Smart Fit

V17 fixes the low/unstable score problem caused by a static partner-marketing requirement dictionary.

## What changed

- Claude now extracts a role-specific requirement map from every JD.
- Recruiter marketing, contact details, benefits, company descriptions, and social-media footer noise are removed before scoring.
- Each requirement is classified as hard, core, or preferred and as direct, transferable, or gap.
- Direct and transferable claims require a verbatim evidence quote from the master resume or verified evidence.
- The score separates Evidence Fit, ATS Coverage, Hard-Requirement Fit, Interview Estimate, and Truthfulness.
- Major hard gaps cap the interview estimate instead of hiding them with keyword stuffing.
- The resume headline and current-role bullets are built from verified functional evidence only.
- Unsupported industry terms such as direct FMCG experience, UV/CVR/AOV ownership, MIS ownership, NielsenIQ, EPOS, MDF, or QBR are removed unless evidenced.
- Career Highlights remain dynamic and prioritize digital/CRM/growth metrics for e-commerce JDs.

## Install

```bash
pip install -r requirements.txt
streamlit run app.py
```

No Supabase schema change is required from V16.
