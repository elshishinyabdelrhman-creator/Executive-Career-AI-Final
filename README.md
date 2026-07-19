# Executive Career Hub V13

A Streamlit career application system focused on truthful recruiter response and interview conversion.

## Main features
- Evidence-constrained Claude resume tailoring
- Executive Premium three-page PDF
- ATS, recruiter, hiring-manager and interview-readiness scoring
- Transferable-experience scoring
- Cover letter, LinkedIn outreach, referral and follow-up messages
- Elevator pitch, STAR stories, likely interview questions and evidence map
- Supabase storage with automatic local SQLite fallback
- Application outcome dashboard and response-rate tracking

## Streamlit Cloud deployment
1. Upload all project files to GitHub.
2. Set `app.py` as the entry point.
3. Add these secrets in Streamlit Cloud:

```toml
ANTHROPIC_API_KEY = "..."
ANTHROPIC_MODEL = "claude-haiku-4-5"
SUPABASE_URL = "https://....supabase.co" # optional
SUPABASE_SERVICE_ROLE_KEY = "..."       # optional
```

The app works without Supabase using SQLite fallback, but Streamlit Cloud may reset local data after a restart.
Run `supabase_schema.sql` once in Supabase SQL Editor for persistent cloud storage.


## Economy mode

The default model is `claude-3-haiku-20240307` to bring typical generation cost back near one cent. You can override it in Streamlit secrets with:

```toml
ANTHROPIC_MODEL = "claude-haiku-4-5"
ANTHROPIC_MAX_TOKENS = "8000"
```

The app displays actual input/output token usage and an estimated API cost after each generation.
