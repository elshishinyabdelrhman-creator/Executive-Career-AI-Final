-- Executive Career Hub V5
-- Safe Supabase schema and migration script
-- Run this entire file in Supabase SQL Editor.

create extension if not exists pgcrypto;

-- =====================================================
-- USERS
-- =====================================================

create table if not exists public.users (
    id uuid primary key default gen_random_uuid(),
    full_name text not null,
    email text unique not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.users
    add column if not exists full_name text,
    add column if not exists email text,
    add column if not exists created_at timestamptz default now(),
    add column if not exists updated_at timestamptz default now();

create unique index if not exists idx_users_email
on public.users (lower(email));

-- =====================================================
-- MASTER RESUME
-- =====================================================

create table if not exists public.master_resume (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    executive_summary text default '',
    experiences jsonb not null default '[]'::jsonb,
    education jsonb not null default '[]'::jsonb,
    skills jsonb not null default '[]'::jsonb,
    certifications jsonb not null default '[]'::jsonb,
    courses jsonb not null default '[]'::jsonb,
    tools jsonb not null default '[]'::jsonb,
    core_competencies jsonb not null default '[]'::jsonb,
    languages jsonb not null default '[]'::jsonb,
    achievements jsonb not null default '[]'::jsonb,
    raw_resume text default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.master_resume
    add column if not exists executive_summary text default '',
    add column if not exists experiences jsonb not null default '[]'::jsonb,
    add column if not exists education jsonb not null default '[]'::jsonb,
    add column if not exists skills jsonb not null default '[]'::jsonb,
    add column if not exists certifications jsonb not null default '[]'::jsonb,
    add column if not exists courses jsonb not null default '[]'::jsonb,
    add column if not exists tools jsonb not null default '[]'::jsonb,
    add column if not exists core_competencies jsonb not null default '[]'::jsonb,
    add column if not exists languages jsonb not null default '[]'::jsonb,
    add column if not exists achievements jsonb not null default '[]'::jsonb,
    add column if not exists raw_resume text default '',
    add column if not exists created_at timestamptz default now(),
    add column if not exists updated_at timestamptz default now();

create unique index if not exists idx_master_resume_user
on public.master_resume (user_id);

-- =====================================================
-- APPLICATIONS
-- =====================================================

create table if not exists public.applications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    company_name text not null,
    role_title text not null,
    location text default '',
    job_url text default '',
    job_description text default '',
    detected_industry text default '',
    company_size text default '',
    company_style text default '',
    company_focus text default '',
    ats_score integer not null default 0,
    match_score integer not null default 0,
    interview_probability integer not null default 0,
    resume_version text default '',
    tailored_resume text default '',
    cover_letter text default '',
    linkedin_about text default '',
    interview_notes text default '',
    application_status text not null default 'Applied',
    recruiter_name text default '',
    recruiter_email text default '',
    notes text default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint applications_ats_score_check
        check (ats_score between 0 and 100),
    constraint applications_match_score_check
        check (match_score between 0 and 100),
    constraint applications_interview_probability_check
        check (interview_probability between 0 and 100)
);

alter table public.applications
    add column if not exists user_id uuid references public.users(id) on delete cascade,
    add column if not exists company_name text,
    add column if not exists role_title text,
    add column if not exists location text default '',
    add column if not exists job_url text default '',
    add column if not exists job_description text default '',
    add column if not exists detected_industry text default '',
    add column if not exists company_size text default '',
    add column if not exists company_style text default '',
    add column if not exists company_focus text default '',
    add column if not exists ats_score integer default 0,
    add column if not exists match_score integer default 0,
    add column if not exists interview_probability integer default 0,
    add column if not exists resume_version text default '',
    add column if not exists tailored_resume text default '',
    add column if not exists cover_letter text default '',
    add column if not exists linkedin_about text default '',
    add column if not exists interview_notes text default '',
    add column if not exists application_status text default 'Applied',
    add column if not exists recruiter_name text default '',
    add column if not exists recruiter_email text default '',
    add column if not exists notes text default '',
    add column if not exists created_at timestamptz default now(),
    add column if not exists updated_at timestamptz default now();

create index if not exists idx_applications_user_created
on public.applications (user_id, created_at desc);

create index if not exists idx_applications_company
on public.applications (company_name);

create index if not exists idx_applications_role
on public.applications (role_title);

create index if not exists idx_applications_status
on public.applications (application_status);

-- =====================================================
-- COMPANY CACHE
-- =====================================================

create table if not exists public.company_cache (
    id uuid primary key default gen_random_uuid(),
    company_name text unique not null,
    industry text default '',
    company_size text default '',
    hiring_style text default '',
    company_focus text default '',
    keywords jsonb not null default '[]'::jsonb,
    required_skills jsonb not null default '[]'::jsonb,
    preferred_skills jsonb not null default '[]'::jsonb,
    responsibilities jsonb not null default '[]'::jsonb,
    cached_at timestamptz not null default now()
);

create unique index if not exists idx_company_cache_name
on public.company_cache (lower(company_name));

-- =====================================================
-- UPDATED_AT TRIGGER
-- =====================================================

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_users_updated_at on public.users;
create trigger trg_users_updated_at
before update on public.users
for each row execute function public.set_updated_at();

drop trigger if exists trg_master_resume_updated_at on public.master_resume;
create trigger trg_master_resume_updated_at
before update on public.master_resume
for each row execute function public.set_updated_at();

drop trigger if exists trg_applications_updated_at on public.applications;
create trigger trg_applications_updated_at
before update on public.applications
for each row execute function public.set_updated_at();

-- =====================================================
-- ROW LEVEL SECURITY
-- =====================================================

alter table public.users enable row level security;
alter table public.master_resume enable row level security;
alter table public.applications enable row level security;
alter table public.company_cache enable row level security;

-- The Streamlit server should use SUPABASE_SERVICE_ROLE_KEY.
-- Service-role requests bypass RLS, so no permissive anon policies are needed.

-- Remove earlier overly-permissive policies if they exist.
drop policy if exists "allow anon read users" on public.users;
drop policy if exists "allow anon insert users" on public.users;
drop policy if exists "allow anon update users" on public.users;
drop policy if exists "users_select_policy" on public.users;
drop policy if exists "users_insert_policy" on public.users;
drop policy if exists "users_update_policy" on public.users;

-- Refresh PostgREST schema cache.
notify pgrst, 'reload schema';

-- Verification
select
    to_regclass('public.users') as users_table,
    to_regclass('public.master_resume') as master_resume_table,
    to_regclass('public.applications') as applications_table,
    to_regclass('public.company_cache') as company_cache_table;
