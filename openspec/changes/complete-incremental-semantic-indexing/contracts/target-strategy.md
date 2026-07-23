# Target strategy: thin fenced Postgres adapter

## Selected boundary

CocoIndex owns source enumeration, per-file processing, chunking, and embedding.
`storage_pg.py` owns all physical revision storage:

- attempt-specific table creation;
- compatible-parent row copy;
- transactional per-file row replacement;
- attempt and published manifests;
- HNSW/schema/count/coverage verification;
- current-lease fenced atomic publication;
- abandoned attempt cleanup.

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
7. prove schema, vector dimension/index, manifest coverage, and counts before
   publication.

The non-skipping target-contract suite is mandatory. Live Postgres/CocoIndex
tests provide integration evidence but do not alter this selected boundary.
