# Plan review resolution

Independent review produced 13 actionable findings in
`../review-findings-plan.json`. The plan was revised before implementation:

- migration 030 now backfills existing ri-01 rows before constraints change;
- every storage attempt is isolated and only a current-lease fenced
  transaction can publish;
- ready identities remain immutable under full rebuild;
- the target contract is mandatory and non-skipping;
- the thin `storage_pg.py` boundary, physical table behavior, crash retry, and
  publication algorithm are frozen;
- the embedding protocol is an earlier independent package;
- source policy includes bounded local secret scanning and dependency scope;
- absent versus unavailable embedding contracts have distinct outcomes;
- provider parameters are whitelisted and canonicalized;
- a strict v2 index record and constrained execution result are explicit;
- parent linkage, manifest semantics, and final validation gates are guarded.

The independent reviewer re-ran its blocker/high audit after these changes and
reported no unresolved blocker or high-severity finding.

External vendor dispatch was also attempted. Claude returned an unknown CLI
error and Gemini timed out; `review-manifest.json` records both failures. No
external findings were available for consensus synthesis.
