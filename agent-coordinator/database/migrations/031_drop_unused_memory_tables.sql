-- Migration 031: drop unused working and procedural memory tables.
--
-- Migration 004 declared three memory layers (episodic, working, procedural),
-- but only `memory_episodic` was ever wired to a writer and a reader (the
-- coordinator `remember`/`recall` service, the bridge `try_remember`/
-- `try_recall` helpers, and the capability-gap tag pipeline). `memory_working`
-- and `memory_procedural` had no code path storing to or querying from them —
-- they were empty tables with documented ambitions.
--
-- Roadmap item ri-15 resolves the memory-layer decision by descoping the two
-- unconsumed layers rather than wiring them (Option B). Roadmap learnings keep
-- their existing home: `learnings/<item-id>.md` files written by
-- roadmap-runtime's learning writer and read back by the replanner. See
-- docs/guides/memory-conventions.md ("Memory Layers") for the rationale.
--
-- DROP TABLE ... CASCADE removes the associated indexes and RLS policies
-- created in 004_memory_tables.sql. This migration is additive-forward only:
-- it does not touch `memory_episodic`.

DROP TABLE IF EXISTS memory_working CASCADE;
DROP TABLE IF EXISTS memory_procedural CASCADE;
