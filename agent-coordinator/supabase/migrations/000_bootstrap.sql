-- Bootstrap: create roles, schemas, and publications that Supabase hosted
-- provides automatically but aren't present in the bare supabase/postgres image.
-- This must sort before 001_core_schema.sql.

-- =============================================================================
-- ROLES (PostgREST switches to these based on JWT claims)
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN;
    END IF;
END$$;

-- Grant usage so PostgREST can switch to these roles
GRANT anon TO postgres;
GRANT authenticated TO postgres;
GRANT service_role TO postgres;

-- =============================================================================
-- AUTH SCHEMA (normally created by Supabase GoTrue)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS auth;

-- auth.role() reads the JWT role claim set by PostgREST.
-- Supports both legacy GUCs (request.jwt.claim.role) and
-- the newer JSON format (request.jwt.claims -> 'role').
CREATE OR REPLACE FUNCTION auth.role() RETURNS TEXT AS $$
    SELECT coalesce(
        nullif(current_setting('request.jwt.claim.role', true), ''),
        nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'role', '')
    );
$$ LANGUAGE sql STABLE;

-- =============================================================================
-- REALTIME PUBLICATION (normally created by Supabase Realtime)
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        CREATE PUBLICATION supabase_realtime;
    END IF;
END$$;

-- =============================================================================
-- SCHEMA GRANTS (PostgREST needs access to public schema objects)
-- =============================================================================

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
