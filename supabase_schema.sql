CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS master_resume (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    executive_summary TEXT,
    experiences JSONB DEFAULT '[]'::jsonb,
    education JSONB DEFAULT '[]'::jsonb,
    skills JSONB DEFAULT '[]'::jsonb,
    certifications JSONB DEFAULT '[]'::jsonb,
    courses JSONB DEFAULT '[]'::jsonb,
    tools JSONB DEFAULT '[]'::jsonb,
    core_competencies JSONB DEFAULT '[]'::jsonb,
    languages JSONB DEFAULT '[]'::jsonb,
    achievements JSONB DEFAULT '[]'::jsonb,
    raw_resume TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    serial_number INTEGER,
    company_name TEXT NOT NULL,
    role_title TEXT NOT NULL,
    location TEXT,
    job_url TEXT,
    job_description TEXT,
    detected_industry TEXT,
    company_size TEXT,
    company_style TEXT,
    company_focus TEXT,
    ats_score INTEGER DEFAULT 0 CHECK (ats_score BETWEEN 0 AND 100),
    match_score INTEGER DEFAULT 0 CHECK (match_score BETWEEN 0 AND 100),
    interview_probability INTEGER DEFAULT 0 CHECK (interview_probability BETWEEN 0 AND 100),
    resume_version TEXT,
    tailored_resume TEXT,
    cover_letter TEXT,
    linkedin_about TEXT,
    generation_data JSONB DEFAULT '{}'::jsonb,
    completed_courses JSONB DEFAULT '[]'::jsonb,
    resume_theme TEXT,
    interview_notes TEXT,
    application_status TEXT DEFAULT 'Applied',
    recruiter_name TEXT,
    recruiter_email TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT UNIQUE NOT NULL,
    industry TEXT,
    company_size TEXT,
    hiring_style TEXT,
    company_focus TEXT,
    keywords JSONB DEFAULT '[]'::jsonb,
    required_skills JSONB DEFAULT '[]'::jsonb,
    preferred_skills JSONB DEFAULT '[]'::jsonb,
    responsibilities JSONB DEFAULT '[]'::jsonb,
    cached_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_applications_user_created ON applications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company_name);
CREATE INDEX IF NOT EXISTS idx_applications_role ON applications(role_title);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE master_resume ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_cache ENABLE ROW LEVEL SECURITY;

-- This Streamlit app uses the service-role key only on the server.
-- Do not expose the service-role key in source control or client-side code.


-- Safe migration for existing Supabase projects
ALTER TABLE applications ADD COLUMN IF NOT EXISTS serial_number INTEGER;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS generation_data JSONB DEFAULT '{}'::jsonb;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS completed_courses JSONB DEFAULT '[]'::jsonb;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS resume_theme TEXT;

-- Repair ALL serial numbers per user in chronological order.
-- This fixes legacy NULL, zero, duplicate, and gapped values.
DROP INDEX IF EXISTS idx_applications_user_serial;

WITH numbered AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at ASC, id ASC) AS seq
    FROM applications
)
UPDATE applications a
SET serial_number = numbered.seq
FROM numbered
WHERE a.id = numbered.id;

ALTER TABLE applications ALTER COLUMN serial_number SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_user_serial
ON applications(user_id, serial_number);
