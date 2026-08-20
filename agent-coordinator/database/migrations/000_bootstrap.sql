-- Bootstrap: create roles, schemas, and publications that managed Postgres
-- providers create automatically but aren't present in bare PostgreSQL.
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

-- Grant usage so PostgREST can switch to these roles.
--
-- Granted to CURRENT_USER, not to a hardcoded `postgres`. This file's whole
-- job is to stand in for objects a managed provider would have created, so it
-- cannot also assume the provider's conventional superuser name: a database
-- owned by any other role (`coord`, `app`, an RDS master user) aborted here on
-- `role "postgres" does not exist`, and because a first run treats every
-- migration error as "already applied", the failure was recorded as success.
-- The `auth` schema and the publication below were then never created, so 001,
-- 002 and 015 aborted in turn and were likewise recorded — producing a
-- database that reported 33 applied migrations while missing a third of its
-- tables. Granting to the role actually running the migration is what was
-- meant in every case, including on Supabase, where CURRENT_USER *is*
-- `postgres`.
DO $$
BEGIN
    EXECUTE format('GRANT anon TO %I', CURRENT_USER);
    EXECUTE format('GRANT authenticated TO %I', CURRENT_USER);
    EXECUTE format('GRANT service_role TO %I', CURRENT_USER);
END$$;

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
