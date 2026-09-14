# Plan Findings: Add Cross-Roadmap Readiness Resolver

## Round 1

Real review dispatch attempted Antigravity, Claude, Grok, and Pi with Codex excluded. Antigravity returned six schema-valid `severity=none` findings. Claude and Grok reached the bounded 240-second timeout; Pi returned a schema-invalid findings object. The primary Codex review and independent Antigravity review therefore provide two-vendor evidence, while the dispatch manifest retains the degraded external-quorum evidence.

| ID | Type | Criticality | Finding | Disposition |
|---|---|---:|---|---|
| C1 | correctness | high | D2 did not distinguish soft roadmap/checkpoint status lag from hard-invalid checkpoint state. | Fixed: status lag remains checkpoint-authoritative and observable; only hard-invalid state withholds. |
| C2 | contract mismatch | high | The schema could not represent invalid roadmap or duplicate-roadmap diagnostics promised by D5. | Fixed: added bounded `roadmap_invalid` and `duplicate_roadmap_id` codes. |
| C3 | spec gap | medium | Fingerprint canonicalization was under-specified. | Fixed: D3 now enumerates normalized fields, ordering, absence, and malformed fallbacks. |
| A1-A6 | architecture/correctness/resilience/observability/compatibility | low | Antigravity independently found the authority boundary, checkpoint precedence, ordering, contract, and sequential package coherent. | Accepted; no change required. |

No roadmap re-decomposition is required. Round 2 must verify the three remediations and must not introduce new blocking findings.
## Convergence

The primary Codex re-review and independent Antigravity round-2 review found the D2, D3, D5, and schema remediations sound with no blocking findings. A final bounded Antigravity check verified the two normative scenarios from their actual line locations and independently ran strict OpenSpec validation. Plan review therefore converged across Codex and Antigravity. The external dispatcher remained operationally degraded because Claude and Grok timed out and Pi returned invalid schema in round 1; their raw/manifest evidence is retained and did not override the two successful vendors.
