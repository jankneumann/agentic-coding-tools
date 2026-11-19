## ADDED Requirements

### Requirement: Vendor Auth Audit Table

The repository SHALL hold a machine-readable audit table at `docs/guides/vendor-auth-audit.yaml` that records, for each of the vendors `claude`, `codex`, `antigravity` and `grok`, a verdict on subscription authentication for each of the lanes `interactive`, `attended_headless`, `unattended_daemon` and `ci`.

#### Scenario: Every vendor has every lane
WHEN the audit table is loaded
THEN it SHALL contain the four vendors
AND each vendor SHALL have a record for each of the four lanes
AND each record's `subscription` value SHALL be `permitted`, `prohibited` or `unaddressed`

#### Scenario: A verdict carries its governing sentence
WHEN a lane record's verdict is `permitted` or `prohibited`
THEN the record SHALL contain a non-empty `quote` and an `https` `source`
AND `quote_evidence` SHALL be `raw` or `summarised`

#### Scenario: An unaddressed lane lists what was searched
WHEN a lane record's verdict is `unaddressed`
THEN the record SHALL contain a non-empty `searched` list of `https` sources

#### Scenario: The table is dated
WHEN the audit table is loaded
THEN it SHALL contain a `retrieved` date

### Requirement: Unattended Lanes Without Permission Require a Keyed Lane

A lane record for `unattended_daemon` or `ci` whose verdict is not `permitted` MUST name `api-key` or `gateway-key` as its `required_lane`.

#### Scenario: Prohibited or unaddressed unattended use is marked
WHEN a record for `unattended_daemon` or `ci` has the verdict `prohibited` or `unaddressed`
THEN its `required_lane` SHALL be `api-key` or `gateway-key`

### Requirement: Credential Mechanics With Evidence Level

For each vendor the audit table SHALL record the credential material, whether token refresh writes to disk, the hosts contacted for inference and authentication, and proxy or base-URL override support, each with an evidence level of `observed`, `documented` or `not_observed`.

#### Scenario: Every mechanics field has an evidence level
WHEN the audit table is loaded
THEN each vendor SHALL have the fields `credential_material`, `refresh_writes`, `hosts` and `proxy_override`
AND each field SHALL have an `evidence` value of `observed`, `documented` or `not_observed`

#### Scenario: Observed is claimed only with a host and date
WHEN a mechanics field has the evidence level `observed`
THEN it SHALL contain `observed_on` and `observed_host_os`

#### Scenario: Documented is claimed only with a source
WHEN a mechanics field has the evidence level `documented`
THEN it SHALL contain an `https` `source`

### Requirement: Credential Observation Script

The repository SHALL provide a script that reports metadata of a vendor's credential paths on the host where it runs, and MUST NOT read or print the content of any credential file.

#### Scenario: Metadata is reported without content
WHEN the script runs for a vendor whose credential file exists
THEN its output SHALL contain the path, mode and modification time
AND its output SHALL NOT contain any byte sequence from the file's content

#### Scenario: A refresh write is detected
WHEN the script runs in watch mode around a command that modifies a credential path
THEN it SHALL report that path as changed

#### Scenario: An unknown vendor is refused
WHEN the script is given a vendor that is not in the audit table
THEN it SHALL exit with a non-zero status

### Requirement: Audit Guide and Corrected Statements

The repository SHALL provide a guide at `docs/guides/vendor-auth-audit.md` consistent with the audit table, and statements elsewhere in the repository about subscription terms SHALL agree with the audit.

#### Scenario: The guide covers every vendor and lane
WHEN the guide is read
THEN it SHALL name each vendor and each lane in the audit table
AND it SHALL state which mechanics fields are not yet observed
AND it SHALL be listed in `docs/guides/documentation.md`

#### Scenario: The Claude strategy note records its verification
WHEN `openspec/roadmaps/sandboxed-flow/claude-auth-strategy.md` is read
THEN it SHALL state the date on which its quotes were checked against the live pages
AND it SHALL NOT say that the quotes are still to be verified

#### Scenario: The factory proposal no longer cites the wrong reason
WHEN `docs/proposals/factory-local-cloud-split.md` is read
THEN it SHALL NOT state that the Claude lane uses an API key "in line with the subscription terms"
AND it SHALL reference `docs/guides/vendor-auth-audit.md`
