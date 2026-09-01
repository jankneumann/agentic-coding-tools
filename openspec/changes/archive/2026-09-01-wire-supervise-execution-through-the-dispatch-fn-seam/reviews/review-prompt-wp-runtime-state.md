# Independent implementation review request: wp-runtime-state

Review package `wp-runtime-state` in OpenSpec change `wire-supervise-execution-through-the-dispatch-fn-seam`. This is read-only.

Read the package definition in `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/work-packages.yaml`, all traced specs/contracts, and both the committed branch diff and current iteration working-tree diff (`git diff main...HEAD` and `git diff`). Check package scope, correctness, compatibility, security, performance, observability, resilience, contracts, and TDD evidence. Pay special attention to linked-worktree paths, checkpoint concurrency/crash recovery, exact result evidence, scheduler fail-closed scope semantics, and durable at-most-once callback/application recovery.

Output ONLY one JSON object conforming to `openspec/schemas/review-findings.schema.json`. Set `review_type` to `implementation`, `target` to `wp-runtime-state`, and populate `reviewer_vendor`. Every finding must include `axis`, `severity`, `type`, `criticality`, `description`, `resolution`, `disposition`, and `package_id`; code findings also need `file_path` and `line_range`. Severity prefixes must match. If no defect is found, emit at least two positive `severity: none` observations on different axes. Do not modify files.
