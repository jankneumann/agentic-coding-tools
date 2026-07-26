# Target strategy: thin fenced Postgres adapter

## Selected boundary

CocoIndex owns source enumeration, per-file processing, chunking, and embedding.
`storage_pg.py` owns all physical revision storage:

- attempt-specific table creation;
- compatible-parent row copy;
- transactional per-file row replacement;
- HNSW/schema/count/coverage verification;
- current-lease fenced atomic publication;
- abandoned attempt cleanup.

The registry owns attempt and published manifest rows. During publication,
`storage_pg.py` invokes the registry's transaction-composable manifest
publisher on the same connection as the table rename, so the physical target
and published manifest commit or roll back together.

The built-in CocoIndex Postgres target is not responsible for final table
lifecycle because it cannot express the required lease-generation fence and
atomic attempt publication contract directly.

## Required conformance

The adapter SHALL:

1. write only to `ccs__<index_uuid_hex>__<attempt_count>` before publication;
2. reject publication unless the registry row still has the same current
   `lease_token` and `attempt_count`;
3. publish table rename plus final-manifest replacement in one transaction
   under an advisory transaction lock keyed by `index_id`;
4. leave a stale worker confined to its abandoned attempt table;
5. treat retry as a clean new attempt and never mutate a ready final table;
6. copy only manifest-proven unchanged eligible paths from a compatible ready
   parent;
7. acquire an access-exclusive lock on the attempt table before the decisive
   publication check, so no writer can mutate it between verification and
   rename;
8. prove or re-prove schema, vector dimension/index, exact manifest-derived
   file/chunk counts, and full manifest coverage on the same
   transaction-bound connection, under the current unexpired lease,
   immediately before table rename and manifest publication.

The non-skipping target-contract suite is mandatory. Live Postgres/CocoIndex
tests provide integration evidence but do not alter this selected boundary.
