# Merge execution confirmation

A successful merge request is not necessarily a completed merge. The executor
records `merged` only when the backend explicitly reports `status: merged` or
live GitHub state confirms that the PR merged.

Successful responses with any other status (including a missing status) retain
the existing `in_progress` outcome and claim, with the optional
`awaiting_merge_confirmation: true` state field. They neither release dependent
PRs nor advance the plan's merge/compaction pointers. The JSON result reports
`action: awaiting_merge_confirmation`; the command retains its existing nonzero
exit status for outcomes other than `merged`.

Replaying execution checks live GitHub state first. An observed merge or closure
is reconciled without another merge call. While the PR remains open, even the
original claim holder cannot resubmit an acknowledged request. Old plan files
without the optional field preserve their existing recovery behavior. Deploy the
updated executor and schema together.

This is the first lifecycle correctness slice, not a queue controller. An open
PR alone cannot distinguish a queued request from one ejected by the provider;
both remain awaiting confirmation. Queue rejection/cancellation reconciliation,
safe retry authorization, expiring leases, and coordinator ownership are follow-up
work. A crash before the acknowledgement is persisted still uses the existing
in-progress claim recovery protocol.
