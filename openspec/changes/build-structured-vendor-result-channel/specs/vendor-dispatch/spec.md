## ADDED Requirements

### Requirement: Structured Vendor Results

Vendor CLI adapters SHALL consume structured (JSON) output on their primary result path instead of regex-scraping stdout.

#### Scenario: No regex scraping on primary path

WHEN a vendor adapter dispatches work
THEN completion state and task identifiers SHALL come from the vendor's structured output mode or the coordinator ledger, not stdout regex patterns.

#### Scenario: Output format change fails loudly

WHEN a vendor CLI changes its output format
THEN the adapter SHALL surface a structured parse error rather than hanging or silently mis-reporting completion.

### Requirement: Dispatch Completion Ledger

The coordinator work queue SHALL be the single source of dispatch state for asynchronous vendor work.

#### Scenario: Async work lifecycle recorded

WHEN an async vendor task is dispatched
THEN a work-queue entry SHALL record the submission
AND completion SHALL be recorded via complete_work before results are consumed downstream.

### Requirement: Lock Release by Agent

The coordinator HTTP API SHALL support listing and bulk-releasing locks by agent id.

#### Scenario: Cloud session end releases locks

WHEN a cloud session deregisters
THEN all locks held by its agent id SHALL be released without waiting for TTL expiry.
