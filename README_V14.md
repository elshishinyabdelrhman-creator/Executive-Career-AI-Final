# Executive Career Hub V14 - Premium Resume Output

This version generates three resume files for every application:

1. **Premium Executive PDF** - two-page navy/gold recruiter version.
2. **Premium Executive DOCX** - editable Word version using the same design.
3. **ATS PDF** - clean, single-column, selectable-text version for application portals.

## What changed

- Added `premium_resume_generator.py` for the two-page executive design.
- Added `candidate_profile.py` with verified candidate evidence and career metrics.
- Updated the Claude prompt to:
  - use verified achievements such as SAR 30M, 3,000+ SQLs, 5,000+ attendees, 150+ team members, and 35% engagement growth;
  - return a shorter executive profile;
  - generate exactly eight concise current-role bullets;
  - return five competency groups and a role-aligned headline.
- Reduced ATS output to two pages by shortening earlier experience and limiting generated content.
- Fixed ATS PDF formatting so bullets containing words such as "banks" are not incorrectly rendered as company headings.
- Added three download buttons to the Streamlit result screen.

## Files to deploy

Replace the existing project files with the files in this folder and keep your existing `.streamlit/secrets.toml`.

Required secret:

```toml
ANTHROPIC_API_KEY = "your-key"
SUPABASE_URL = "your-url"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
```

## Install and run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment

Push the folder to GitHub and redeploy the Streamlit app. No new Supabase columns are required for the premium generator.

## Output behavior

The AI produces the role-specific content. The layout engine controls the visual system independently, so changing the prompt cannot break the design. The premium exporter also caps content length to protect the two-page layout.
