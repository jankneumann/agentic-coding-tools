# Audit vendor headless auth and terms

> Parent roadmap: `sandboxed-flow`
> Change ID: `audit-vendor-headless-auth-and-terms`
> Effort: S
> Priority: 1

## Summary

A spike that records, for each of Claude, Codex, Antigravity and Grok, what the vendor's terms permit per lane (interactive, attended headless dispatch, unattended daemon, CI), where the credential material lives, whether token refresh needs a writable path, which hosts inference and refresh contact, and whether the CLI accepts a base-URL or proxy override. The Claude column starts from claude-auth-strategy.md in this workspace and re-verifies each quote against the live page. The result is a checked-in table that later items read, not production code.

## Dependencies

- None

## Acceptance Outcomes

- A checked-in document states, per vendor and per lane, whether subscription authentication is permitted, prohibited or unaddressed, with the governing sentence and its source.
- Every quote in claude-auth-strategy.md is re-verified against the live page, and any that differs is corrected.
- For each vendor the credential material, refresh-write requirement, inference hosts and proxy-override support are recorded from an observed run, not from memory.
- Any lane a vendor's terms prohibit or leave unaddressed for unattended use is marked as requiring an API-key or gateway-key lane.
- The statement in docs/proposals/factory-local-cloud-split.md about why the Claude review lane uses an API key is corrected to match the audit.

## Rationale

Subscription logins must be used unattended only where the vendor audit records that the terms permit it; the credential profile and the token injection spike both read this table.
