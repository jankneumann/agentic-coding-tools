# Design: audit-vendor-headless-auth-and-terms

## Context

Four vendors, four lanes, four mechanics fields. The audit is evidence for
later items, written in a container that can read vendor pages but cannot run
three of the four CLIs.

## Decisions

### D1. The YAML table is the source; the guide explains it

`docs/guides/vendor-auth-audit.yaml` holds the facts. The guide repeats the
verdicts for a reader and adds method and limits. A test checks the guide
names every vendor and every lane in the table. Rejected: generating the guide
from the table; a generator is more code than this spike warrants.

### D2. Three verdicts, and `unaddressed` is one of them

`permitted`, `prohibited`, `unaddressed`. A `permitted` or `prohibited`
verdict carries the governing sentence verbatim and its URL. `unaddressed`
carries the list of pages searched instead. No verdict is derived from another
vendor's terms.

### D3. Unattended lanes default to a keyed lane

For `unattended_daemon` and `ci`, any verdict other than `permitted` sets
`required_lane` to `api-key` or `gateway-key`. A `permitted` verdict may still
set it where the vendor documents a different mechanism for that lane (a
long-lived token rather than the interactive login); then `mechanism` says
which.

### D4. Evidence level per mechanics field

Each of `credential_material`, `refresh_writes`, `hosts`, `proxy_override` has
`evidence`: `observed` (seen on a host, with `observed_on` and
`observed_host_os`), `documented` (vendor documentation, with `source`) or
`not_observed` (neither). The acceptance outcome asks for observation; the
field shows exactly how far each vendor is from it.

### D5. Quote provenance is recorded

Each quote has `quote_evidence`: `raw` when the sentence was read in the
page's own text, `summarised` when it came through a fetch tool that
summarises. A `summarised` quote is not presented as verified.

### D6. Observation script reports metadata only

`observe_vendor_auth.py` takes a vendor name, lists that vendor's candidate
credential paths from a table in the script, and for each prints existence,
type, mode, size and modification time. With `--watch -- <command>` it takes
the snapshot before and after running the command and reports which paths
changed, which answers the refresh-write question. It never opens a
credential file. Hosts are not captured by the script; the guide gives the
operator a manual procedure, because capturing traffic needs privileges the
script should not ask for.

### D7. Corrections are made in place

`claude-auth-strategy.md` gets corrected quotes and a verification note with
the date. `factory-local-cloud-split.md` gets the corrected reason for the
API-key review lane and points to the audit. Neither keeps the wrong text.

## Risks

- Terms change. The table has a retrieval date and the guide says to re-check
  before relying on a verdict.
- A fetch tool may paraphrase. D5 exists for this.
- Observation may never be done. The roadmap item stays open and ri-03 can
  read `evidence` to decide what to trust.
