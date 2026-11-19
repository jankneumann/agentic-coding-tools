# Change Context: audit-vendor-headless-auth-and-terms

## Requirement Traceability Matrix

Tests live in `skills/tests/vendor-status/`. Contract Ref is `---` throughout:
`contracts/` holds only a README, because the change exposes no interface.

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| vendor-auth-audit.1 | specs/vendor-auth-audit/spec.md "Vendor Auth Audit Table" | A dated table gives each of four vendors a verdict per lane, with the governing sentence and its provenance, or the pages searched when nothing addresses the lane | --- | D1, D2, D5 | `docs/guides/vendor-auth-audit.yaml` | `test_vendor_auth_audit_table.py`: `test_table_has_exactly_the_four_vendors`, `test_every_vendor_has_every_lane`, `test_every_verdict_is_one_of_three`, `test_a_verdict_carries_quote_source_and_provenance`, `test_an_unaddressed_lane_lists_what_was_searched`, `test_the_table_is_dated` | pass 75c644f (table shape). Seven quotes are `summarised` or absent because the vendor's pages were unreachable |
| vendor-auth-audit.2 | "Unattended Lanes Without Permission Require a Keyed Lane" | An unattended lane whose subscription use is prohibited or unaddressed names a keyed lane to use instead | --- | D3 | `docs/guides/vendor-auth-audit.yaml` | `test_unattended_lane_without_permission_names_a_keyed_lane`, `test_any_required_lane_is_a_keyed_lane` | pass 75c644f |
| vendor-auth-audit.3 | "Credential Mechanics With Evidence Level" | Each mechanics field states whether it was observed, documented or not observed, with the host and date or the source that backs the claim | --- | D4 | `docs/guides/vendor-auth-audit.yaml` | `test_every_mechanics_field_has_an_evidence_level`, `test_observed_is_claimed_only_with_host_and_date`, `test_documented_is_claimed_only_with_a_source`, `test_not_observed_says_what_is_missing` | pass 75c644f (rules hold). No field is `observed`: task 4.1 is open |
| vendor-auth-audit.4 | "Credential Observation Script" | A script reports metadata of a vendor's credential paths, never content, detects a write during a command, and refuses an unknown vendor | --- | D6 | `skills/vendor-status/scripts/observe_vendor_auth.py` | `test_observe_vendor_auth.py` (14 tests) | pass 75c644f (temporary directories). Not run against a signed-in CLI |
| vendor-auth-audit.5 | "Audit Guide and Corrected Statements" | A guide covers every vendor and lane and says what is not observed; the Claude strategy note records its verification; the factory proposal no longer cites the wrong reason | --- | D1, D7 | `docs/guides/vendor-auth-audit.md`, `docs/guides/documentation.md`, `openspec/roadmaps/sandboxed-flow/claude-auth-strategy.md`, `docs/proposals/factory-local-cloud-split.md` | `test_vendor_auth_audit_docs.py` (13 tests) | pass 75c644f |

`skills/pyproject.toml` gained the `tests/vendor-status` test path so the suite
runs in CI.

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Later roadmap items need to read verdicts by program | `vendor-auth-audit.yaml` holds the data; the guide explains it and a test compares each guide row with the YAML | Prose alone cannot be tested, and two hand-kept copies drift |
| D2 | Silence in a vendor's terms is a finding, not a gap in the audit | Verdicts are `permitted`, `prohibited` or `unaddressed`; `unaddressed` requires a `searched` list | Forcing silence into yes or no would invent a licence reading |
| D3 | A wrong guess costs the account every other lane uses | `required_lane: api-key` on unattended lanes that are not `permitted`, and on the Codex CI lane whose quote is unverified | Defaulting to the subscription would treat silence as permission |
| D4 | Documentation and behaviour differ, and the audit could observe nothing | `evidence` per mechanics field; `observed` needs `observed_on` and `observed_host_os` | One level per vendor would hide the Antigravity host list, which no source gives |
| D5 | Some pages were read through a summarising tool | `quote_kind: raw` or `summarised` on each quoted lane | A paraphrase shown as a quotation is the error the Claude strategy note already made once |
| D6 | Output has to be safe to paste into a review | The script uses `lstat` and `listdir` only; a test fails if it calls `open` | Reading and then redacting can leak; never reading cannot |
| D7 | Two documents stated terms before the audit | Edited in place, with the check date and a pointer to the guide | A separate errata file would leave the wrong text where readers find it |

## Coverage Summary

- **Requirements traced**: 5/5
- **Tests mapped**: 5 requirements have at least one test
- **Evidence collected**: 5/5 requirements have pass evidence at 75c644f (39 tests in `skills/tests/vendor-status`)
- **Gaps identified**: No mechanics field is `observed`: only the Claude CLI was installed where the audit ran, and no CLI was signed in. No licence text was read for Codex, Antigravity or Grok, because their hosts were blocked by the environment's network policy; those verdicts rest on product documentation
- **Deferred items**: Task 4.1, host observation on the operator's machines. Re-reading the three vendors' terms once their hosts are allowed
