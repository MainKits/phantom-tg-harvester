-- Phantom TG Harvester — Supabase Schema
-- Run this in your Supabase SQL Editor: https://supabase.com/dashboard/project/srcvgetovcsaqcajyhdt/sql/new

-- 1. Accounts
CREATE TABLE IF NOT EXISTS public.accounts (
    id BIGSERIAL PRIMARY KEY,
    phone TEXT UNIQUE NOT NULL,
    session_file TEXT,
    session_data TEXT, -- Base64 encoded Telethon .session binary for cloud persistence
    proxy_type TEXT,
    proxy_host TEXT,
    proxy_port INTEGER,
    proxy_username TEXT,
    proxy_password TEXT,
    status TEXT DEFAULT 'inactive',
    messages_sent_today INTEGER DEFAULT 0,
    invites_sent_today INTEGER DEFAULT 0,
    last_used TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    flood_wait_until TIMESTAMPTZ
);

-- 2. Parsed Users
CREATE TABLE IF NOT EXISTS public.parsed_users (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    source_chat TEXT,
    last_online TIMESTAMPTZ,
    is_active_writer INTEGER DEFAULT 0,
    parsed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Send Tasks
CREATE TABLE IF NOT EXISTS public.send_tasks (
    id BIGSERIAL PRIMARY KEY,
    send_type TEXT DEFAULT 'users',
    repeat_interval INTEGER DEFAULT 0,
    targets_file TEXT,
    message_text TEXT NOT NULL,
    media_path TEXT,
    spintax_enabled INTEGER DEFAULT 0,
    messages_per_account INTEGER DEFAULT 35,
    delay_min INTEGER DEFAULT 45,
    delay_max INTEGER DEFAULT 120,
    status TEXT DEFAULT 'pending',
    total_sent INTEGER DEFAULT 0,
    total_failed INTEGER DEFAULT 0,
    auto_responder_enabled INTEGER DEFAULT 0,
    auto_responder_keywords TEXT DEFAULT '[]',
    forward_to_account TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Invite Tasks
CREATE TABLE IF NOT EXISTS public.invite_tasks (
    id BIGSERIAL PRIMARY KEY,
    target_chat TEXT NOT NULL,
    invites_per_account INTEGER DEFAULT 15,
    delay_min INTEGER DEFAULT 30,
    delay_max INTEGER DEFAULT 60,
    status TEXT DEFAULT 'pending',
    total_invited INTEGER DEFAULT 0,
    total_failed INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Event Logs
CREATE TABLE IF NOT EXISTS public.event_logs (
    id BIGSERIAL PRIMARY KEY,
    level TEXT DEFAULT 'info',
    source TEXT,
    message TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Daily Stats
CREATE TABLE IF NOT EXISTS public.daily_stats (
    date TEXT PRIMARY KEY,
    sent_total INTEGER DEFAULT 0,
    invited_total INTEGER DEFAULT 0,
    failed_total INTEGER DEFAULT 0
);

-- 7. TikTok Accounts
CREATE TABLE IF NOT EXISTS public.tiktok_accounts (
    id BIGSERIAL PRIMARY KEY,
    username TEXT,
    cookie_data TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. TikTok Tasks
CREATE TABLE IF NOT EXISTS public.tiktok_tasks (
    id BIGSERIAL PRIMARY KEY,
    video_path TEXT,
    description TEXT,
    status TEXT DEFAULT 'pending',
    total_accounts INTEGER,
    posted_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. Settings
CREATE TABLE IF NOT EXISTS public.settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 10. License Keys
CREATE TABLE IF NOT EXISTS public.license_keys (
    id BIGSERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'active',
    activated_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    note TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Disable Row Level Security (RLS) so the backend with service_role / anon key has full access
ALTER TABLE public.accounts DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.parsed_users DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.send_tasks DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.invite_tasks DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_logs DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_stats DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_accounts DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_tasks DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.settings DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.license_keys DISABLE ROW LEVEL SECURITY;

-- Insert default admin license key valid for 1 year if none exists
INSERT INTO public.license_keys (key, status, expires_at, note)
VALUES ('PHANTOM-PRO-2026', 'active', NOW() + INTERVAL '365 days', 'Default Master License')
ON CONFLICT (key) DO NOTHING;
