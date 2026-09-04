# Migrations

Applied in filename order by `src/migrations.py`, each in its own transaction,
tracked by filename + SHA-256 checksum in `schema_migrations`.

## Requirements for a fresh database

- **PostgreSQL 16+** — the target is plain PostgreSQL; Supabase is the opt-in
  alternative, not the assumption.
- **`pgvector`** — `028_code_search_registry.sql` runs `CREATE EXTENSION vector`.
  Install `postgresql-16-pgvector` (or equivalent) before first boot.
- **A role that may `CREATE ROLE`** — `000_bootstrap.sql` creates the `anon`,
  `authenticated` and `service_role` roles that PostgREST-shaped deployments
  expect, plus the `auth` schema and the `supabase_realtime` publication that a
  managed provider would have created for you.

`000_bootstrap.sql` grants those roles to `CURRENT_USER`. It must never name a
specific superuser: the database owner is `postgres` on Supabase but something
else nearly everywhere, and this file's whole purpose is to remove environment
assumptions rather than add one.

## First-run behavior, and why it is narrow

When `schema_migrations` is empty, the runner assumes the database *may* have
been seeded out-of-band (Docker `initdb` running `seed.sql`), so a migration
that fails because **its objects already exist** is recorded as applied instead
of aborting the boot.

That tolerance is limited to duplicate-object SQLSTATEs plus `23505`
(unique_violation — what a re-executed *data* migration such as 019's renames
raises on a seeded database)
(`_ALREADY_APPLIED_SQLSTATES` in `src/migrations.py`). Every other failure
propagates and stops the boot.

It has to be that narrow. The branch used to swallow *all* first-run errors,
which turned a single broken statement into permanent invisible schema skew —
the tracking row said "applied", so no later run ever retried it:

1. `000_bootstrap.sql` hardcoded `GRANT anon TO postgres`, so on a database
   owned by any other role it aborted with `role "postgres" does not exist`.
2. Recorded as applied. The `auth` schema and `supabase_realtime` publication
   were therefore never created.
3. `001_core_schema.sql` aborted at `ALTER PUBLICATION`, `002` at `auth.role()`,
   `015` at the `work_queue` table `001` never reached — each recorded in turn.
4. The coordinator booted, logged every migration as applied, and ran against a
   database missing half its tables and functions.
5. `024`'s `audit_log` trigger *did* apply, and called `coordinator_notify()` —
   a function `015` never created. Every audit write failed, silently.

The lesson is the failure mode, not the specific bug: an error handler that
records success is worse than no handler, because it destroys the evidence that
anything went wrong.

## Testing

- `tests/test_migration_bootstrap_failures.py` — runs everywhere. Asserts real
  failures are not mistaken for duplicate-object ones, and that no migration
  hardcodes the `postgres` role.
- `tests/integration/postgres/test_fresh_database_migration.py` — needs a live
  server. Creates a throwaway database, applies every migration, and checks the
  **catalog** for the tables and functions the services call. Counting applied
  migrations is not enough; that count was complete on a half-empty database.

Every other migration test reads the `.sql` files as text. Only the integration
test has PostgreSQL parse them, which is why nothing caught the cascade above.
