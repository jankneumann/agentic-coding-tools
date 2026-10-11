## Review Round 1

The packet is complete; do not explore the repo for missing artifacts.

Review the attached artifacts for correctness, completeness, and adherence to project standards.

### Prompt contract
REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/adjudication-pass3-round-1.json b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/adjudication-pass3-round-1.json
new file mode 100644
index 00000000..678ed230
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/adjudication-pass3-round-1.json
@@ -0,0 +1,103 @@
+{
+  "phase": "PLAN_REVIEW",
+  "pass": 3,
+  "round": 1,
+  "adjudicator": "orchestrator (claude_code PLAN_REVIEW sub-agent)",
+  "at": "2026-10-11T02:37:18.518581+00:00",
+  "note": "pass 2 lost quorum: codex/pi failed with E2BIG (packet > 128 KiB as argv); pass 3 delivered the prompt to codex/pi over stdin (transport only)",
+  "decisions": [
+    {
+      "id": 27,
+      "vendor": "claude_code",
+      "criticality": "high",
+      "verdict": "valid",
+      "action": "fixed",
+      "rationale": "skuid drop rule would also drop DNS to 127.0.0.53; DNS exemption added before the drop; O4 checks getent."
+    },
+    {
+      "id": 28,
+      "vendor": "claude_code",
+      "criticality": "high",
+      "verdict": "valid",
+      "action": "fixed",
+      "rationale": "curl probe false-negative on non-HTTP ports; replaced with /dev/tcp connect probe in design, O4 and spec."
+    },
+    {
+      "id": 40,
+      "vendor": "codex",
+      "criticality": "high",
+      "verdict": "valid (corroborated by claude_code #33/#5)",
+      "action": "fixed",
+      "rationale": "EnvironmentFile= and LoadCredential= pinned in D7, tests 3.1, O2 and a spec scenario."
+    },
+    {
+      "id": 41,
+      "vendor": "codex",
+      "criticality": "high",
+      "verdict": "valid (corroborated by claude_code #6)",
+      "action": "fixed",
+      "rationale": "podman run --replace; mint script sweeps the instance's own offline registrations; tested and specified."
+    },
+    {
+      "id": 42,
+      "vendor": "codex",
+      "criticality": "high",
+      "verdict": "partially valid -> medium (clarity)",
+      "action": "fixed",
+      "rationale": "merge is the orchestrator's merge_worktrees.py step (implement-feature C5) with per-package scope checks; wp-integration description now says so."
+    }
+  ],
+  "addressed": [
+    3,
+    5,
+    6,
+    9,
+    16,
+    19,
+    20,
+    21,
+    23,
+    25,
+    27,
+    28,
+    29,
+    30,
+    32,
+    33,
+    34,
+    36,
+    38,
+    40,
+    41,
+    42,
+    43,
+    44,
+    45,
+    46,
+    48
+  ],
+  "parked_rejected": {
+    "17": "repo convention: change-local contract paths in work-packages are consumed pre-archive; path-stability rule targets tests",
+    "24": "repo convention for changes with no HTTP surface (recorded in contracts/README.md)",
+    "37": "reviewer itself recommends accept (same as #17/#24)",
+    "47": "same as #24; work-package schema requires an openapi block; not a plan defect of this change",
+    "22": "drift is caught by tests 2.1/3.3 tying expression and mint labels to the manifest; schema stays reusable",
+    "35": "reviewer recommends accept (same as #22)",
+    "26": "environment degradations, not plan defects",
+    "39": "environment degradations, not plan defects (duplicate of #26)",
+    "31": "proposal What-Changes item 4 fixed; session-log.md and plan-findings.md are historical phase records and are not rewritten"
+  },
+  "lanes": {
+    "succeeded": [
+      "claude_code",
+      "codex"
+    ],
+    "failed": {
+      "pi": "classified auth_required (pi wrote findings to a file instead of stdout) - dropped from later rounds per policy"
+    },
+    "not_dispatched": [
+      "antigravity",
+      "grok"
+    ]
+  }
+}
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/adjudication-round-1.json b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/adjudication-round-1.json
new file mode 100644
index 00000000..202e83fc
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/adjudication-round-1.json
@@ -0,0 +1,77 @@
+{
+  "phase": "PLAN_REVIEW",
+  "round": 1,
+  "adjudicator": "orchestrator (claude_code PLAN_REVIEW sub-agent, rubric adjudication of single-vendor high/critical judgment findings)",
+  "at": "2026-10-11T02:21:24.533705+00:00",
+  "decisions": [
+    {
+      "id": 10,
+      "vendor": "codex",
+      "criticality": "critical",
+      "verdict": "valid",
+      "action": "fixed",
+      "rationale": "merge_group commits can contain an approved fork PR; D3 fork test only covered pull_request. Canonical expression now uses an event allowlist (push, workflow_dispatch, same-repo pull_request); merge_group always hosted; D4 guard = negated eligibility clause; spec scenario 'Merge queue runs stay hosted'."
+    },
+    {
+      "id": 11,
+      "vendor": "codex",
+      "criticality": "high",
+      "verdict": "valid",
+      "action": "fixed",
+      "rationale": "Jobs API exposes display names, not YAML ids. D8 now defines a correlation contract (id or literal name:, matrix prefix match, unknown-job violation, unique display names asserted in 2.2); spec scenario 'Matrix expansions are correlated to their job id'."
+    },
+    {
+      "id": 12,
+      "vendor": "codex",
+      "criticality": "high",
+      "verdict": "valid",
+      "action": "fixed",
+      "rationale": "A10 trust premise ignored Dependabot/agent same-repo branches and leaked credentials (corroborated by claude_code #2, medium). Cache is now off by default; enabling it is a recorded operator risk acceptance; switch mechanism specified ($GX10_RUNNER_CACHE_ARGS) and tested."
+    },
+    {
+      "id": 1,
+      "vendor": "claude_code",
+      "criticality": "high",
+      "verdict": "valid",
+      "action": "fixed",
+      "rationale": "allow_host_loopback=false does not block services bound to 0.0.0.0/LAN/Tailscale through slirp4netns NAT. D6/A11 now require an operator nftables skuid rule (or loopback-only binding); O4 probes every host address; spec operator scenario added."
+    }
+  ],
+  "also_fixed_non_blocking": [
+    2,
+    4,
+    7,
+    8,
+    13,
+    14,
+    15,
+    18
+  ],
+  "left_open_advisory": [
+    3,
+    5,
+    6,
+    9,
+    16,
+    17,
+    19,
+    20,
+    21,
+    22,
+    23,
+    24,
+    25,
+    26
+  ],
+  "lanes": {
+    "succeeded": [
+      "claude_code",
+      "codex",
+      "pi"
+    ],
+    "failed": {
+      "antigravity": "timeout (240s) - dropped from later rounds",
+      "grok": "426 outdated CLI (vendor_unavailable) - dropped from later rounds"
+    }
+  }
+}
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/ledger.json b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/ledger.json
new file mode 100644
index 00000000..5201a6b9
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/ledger.json
@@ -0,0 +1,827 @@
+{
+  "schema_version": 1,
+  "change_id": "migrate-ci-to-self-hosted-gx10-runners",
+  "items": [
+    {
+      "id": 1,
+      "status": "addressed",
+      "axis": "security",
+      "type": "security",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "fingerprint": "c9581b9d73aa9e3b",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D6 (and A11, the Risks table, and O4) treat `--network slirp4netns:allow_host_loopback=false` as proof that host services are unreachable from PR code. That option only disables the 10.0.2.2 -> 127.0.0.1 mapping. slirp4netns still NATs container traffic through the host stack, so any host service bound to 0.0.0.0 or to the host's LAN/Tailscale address (a compose-published Postgres `0.0.0.0:54322` is the common case, and the ri-08 dispatcher daemon may also listen non-loopback) remains reachable by connecting to the host's real IP. The O4 verification (`curl http://10.0.2.2:54322`) would pass while Postgres is reachable at `http://<host-lan-ip>:54322`, so the isolation claim is unverified by the test the runbook prescribes. Fix: (a) state the binding assumption explicitly in D6/A11 (host services must bind to 127.0.0.1 only, verified in O4 with `ss -ltnp` for :54322 and the coordinator port); (b) extend the O4 check to `curl` the host's primary address (`hostname -I | awk '{print $1}'`) from inside the container; (c) optionally add a host nftables/ufw rule in O1 that drops `owner uid ghrunner` OUTPUT traffic to the host's own addresses, which is the only control that holds regardless of how services are bound.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 2,
+      "status": "addressed",
+      "axis": "security",
+      "type": "security",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/proposal.md",
+      "fingerprint": "e4f51b046bfc2344",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "A10 and D6 argue that every same-repository branch author is a trusted human principal. This repository explicitly accepts PRs from automated authors with push access (Dependabot, Jules, Codex and other agent PRs, per the merge-pull-requests skill and the `dependency-update-remediation` job). Their branches satisfy `head.repo.full_name == github.repository`, so with `CI_RUNNER_LANE=self-hosted` unreviewed agent-generated code and freshly bumped third-party packages execute on the GX10 host (shared kernel, shared uv cache that later `main` jobs read) before any human has looked at the diff. The hardening in D6 is good, but the written trust argument is wrong as stated, and the acceptance of the cache-poisoning risk rests on it. This is a threat-model call for the owner: either extend A10 to name automated same-repo authors and accept it, or add `github.actor` / branch-prefix exclusions (e.g. `dependabot/*`, bot actors) to the D3 expression so those PRs stay on hosted runners.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 3,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "spec_file": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "56cd250710eb9eae",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger items #3 and #16: still open. (1) The MUST that the `fromJSON` label set equals `routing.self_hosted_labels` has no scenario (the 'JIT labels' scenario is about the mint script), and nothing ties `vars.CI_RUNNER_LANE` / `inputs.runner_lane` in the expression to `routing.repository_variable` / `routing.dispatch_input`. (2) 'The CLI SHALL select runs only through explicit filters \u2026 and SHALL cap fetched runs with `--limit`' still has no WHEN/THEN; task 4.1 checks argument parsing only, which would not detect a client that paginates everything before truncating. Add one scenario for each clause (for #2: with a stubbed `gh` returning N pages, at most ceil(limit/per_page) requests are issued).",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 4,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/tasks.md",
+      "fingerprint": "bc91c408e26681e9",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "O1 creates `ghrunner` with `useradd --system`. On Ubuntu, system accounts receive no `/etc/subuid` / `/etc/subgid` range, and rootless podman cannot run an image whose process user is non-root (the actions-runner image runs as `runner`, uid 1001) without one: O3 (`podman build`) and O4 (`podman run`) fail with a 'no subuid ranges found' class error. Also, `--shell /usr/sbin/nologin` means the 'as `ghrunner`' instructions in O3/O4 cannot be followed via `su`/`machinectl shell`; the runbook should say `sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) ...` or `systemd-run --user --machine=ghrunner@`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 5,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "architecture",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "fingerprint": "413fcc05ae41a970",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The design uses 'the env file' for two different files: the operator configuration (`gx10-runner.env.example`: repo slug, limits, image ref, labels, `GX10_MINT_MAX_ELAPSED`) and the per-instance container env file written by the mint script (`%t/gx10-runner/%i.env`, JIT config and runner id only). D7's property list never names the `EnvironmentFile=` line that must load the former, nor how the credential reaches the unit (`LoadCredential=github-token:<path>` vs `GX10_RUNNER_TOKEN_FILE`), and test 3.1 does not assert either. Relatedly, 'GX10_RUNNER_UV_CACHE=off drops the volume' is not expressible in a plain `ExecStart=` line; it needs an unquoted `$GX10_UV_CACHE_ARGS` word-split variable or a wrapper, and either choice interacts with the test that scans `ExecStart` for a literal volume flag.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 6,
+      "status": "addressed",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "fingerprint": "d98399eb80bc1b11",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item #6: still open. The D6 option list has `--name gx10-runner-%i` without `--replace`, so after any unclean stop (podman client killed at `TimeoutStopSec`, host crash) the stale container name makes every subsequent `ExecStart` fail and `Restart=always` spins every 10 s with the instance silently out of the pool. Add `--replace` to the required options (and to test 3.1), and have `mint-jitconfig.sh` or `cleanup-runner.sh` sweep offline registrations matching `gx10-<hostname>-<instance>-*` before minting, since `ExecStopPost` never runs on power loss (O10).",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 7,
+      "status": "addressed",
+      "axis": "performance",
+      "type": "performance",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "fingerprint": "0c093c50516d6589",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The session log records the shared uv cache as 'the main source of speedup' for outcome 2, but nothing in D6/D10 ensures routed jobs actually use the mounted path. If the workflows use `astral-sh/setup-uv` with its default caching (the design does not say), the action exports `UV_CACHE_DIR` under `$RUNNER_TEMP` and round-trips the cache through GitHub's cache service, bypassing `/home/runner/.cache/uv` entirely; the volume would then be dead weight and the A6 threshold would be measured against a cold cache. The design should state the binding: set `UV_CACHE_DIR=/home/runner/.cache/uv` in the container image/env, and either set `cache-local-path` to it or `enable-cache: false` when `runner.environment == 'self-hosted'`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 8,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "fingerprint": "d56231a10286766f",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Stale or duplicated text left by the iteration edits: (1) D6 repeats the 'operator can disable the cache with GX10_RUNNER_UV_CACHE=off' paragraph twice in succession; (2) session-log.md PLAN section still says 'assumptions A1-A9' and its trade-off entry still claims 'locked hash verification applies', which plan-findings #4 and A10 explicitly retract; (3) spec signatures `median_wallclock(runs)` / `compare(baseline, candidate, threshold=0.85, min_n=5)` differ from design D8's keyword-only forms with a `conclusion` parameter.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 9,
+      "status": "addressed",
+      "axis": "security",
+      "type": "security",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "fingerprint": "193b54bf1df9db39",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item #9: still open, text unchanged. `ACTIONS_RUNNER_INPUT_JITCONFIG` stays in every step's environment and carries the runner's key material; PR code can act as that runner against the Actions broker for the job's lifetime. Replace 'gains nothing' with an explicit residual-risk statement bounded by ephemerality, optionally noting the `unset`-and-pass-`--jitconfig` entrypoint wrapper as a hardening follow-up.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 10,
+      "status": "addressed",
+      "axis": "security",
+      "type": "security",
+      "criticality": "critical",
+      "evidence_class": "judgment",
+      "fingerprint": "0cbdfa63f789f826",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "Design D3 excludes fork code only when `github.event_name == 'pull_request'`. A `merge_group` run can execute a temporary merge commit containing an approved fork PR, but the expression treats every `merge_group` as non-fork and routes it to GX10 whenever `CI_RUNNER_LANE=self-hosted`. This violates the requirement that fork code never execute on self-hosted runners. Route all `merge_group` runs to hosted runners unless fork provenance can be established safely.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 11,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "contract_mismatch",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "fingerprint": "37a99ecb7a21e25f",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "D8 requires `verify_run` to correlate manifest job IDs with jobs returned by GitHub's workflow-jobs API, but that API exposes display names rather than stable YAML job IDs; matrix jobs can also produce multiple names from one job definition. No mapping or naming contract is defined, so missing-job, lane, conditional-skip, and hosted/routed checks cannot be implemented reliably. Define and test a stable correlation mechanism, including matrix expansions.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 12,
+      "status": "addressed",
+      "axis": "security",
+      "type": "security",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "fingerprint": "406c53b7e351df2b",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "Assumption A10 equates the ability to create a same-repository branch with authorization to persist code into later trusted runs through the shared uv cache. That premise ignores Dependabot and other automation, compromised collaborator credentials, and branch-protection distinctions between pushing a branch and merging to protected main. A PR can poison the writable cache and influence a later main job with stronger credentials. Disable cross-trust cache sharing or isolate caches by trust level; otherwise require explicit human risk acceptance.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 13,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "fingerprint": "e01a3b397f3dc508",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "Operator step O11 invokes `verify-run` without `--expect-lane hosted`, although `verify-run` defaults to `self-hosted`. A correctly routed fork PR would therefore report every routed job on GitHub-hosted runners as a violation instead of producing the stated zero-violation result. O11 and its runbook command must pass `--expect-lane hosted`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 14,
+      "status": "addressed",
+      "axis": "resilience",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "8b78de0ce13095fd",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "D6 promises that `GX10_RUNNER_UV_CACHE=off` removes the cache volume, but neither the systemd-unit contract nor tasks 3.1\u20133.2 define or test how that switch changes `ExecStart`. An implementation can satisfy the planned tests while always mounting the cache or passing the literal value `off` to Podman. Specify the argument-expansion or wrapper mechanism and add positive tests for both enabled and disabled modes.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 15,
+      "status": "addressed",
+      "axis": "compatibility",
+      "type": "contract_mismatch",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "fingerprint": "edf215a657f5c2ed",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "The artifacts disagree on failed `continue-on-error` jobs. Design D8 and task 4.1 require them to be warnings, while the specification says `verify_run` SHALL report every conclusion other than `success` or `skipped`, and the CLI exits nonzero on every violation. Define the result model and exit behavior explicitly and add a WHEN/THEN scenario for the warning exception.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 16,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "13a65dafa7174bd8",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "The specification's normative CLI clause requiring explicit run filters and a bounded `--limit` has no WHEN/THEN scenario that verifies filtering or bounded pagination. Task 4.1 only checks argument parsing, which would not detect an implementation that fetches all pages before truncating. Add a scenario covering request selection and the maximum number of fetched results/pages.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 17,
+      "status": "parked",
+      "axis": "compatibility",
+      "type": "contract_mismatch",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "fingerprint": "caaf6d64d1eaf9c7",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "work-packages.yaml contracts.openapi.primary and files reference openspec/changes/migrate-ci-to-self-hosted-gx10-runners/... paths directly. Per OpenSpec path stability guide (docs/guides/openspec-path-stability.md), these paths are unstable \u2014 archival moves them to openspec/changes/archive/<date>-<id>/. Any tooling consuming work-packages.yaml for contract resolution may break post-archive. The package verification commands correctly use promoted .github/ paths.",
+      "resolution": "orchestrator adjudication: repo convention: change-local contract paths in work-packages are consumed pre-archive; path-stability rule targets tests",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 18,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "6fd69e129cff15a1",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "spec.md lacks an explicit SHALL requirement that both workflows MUST declare a workflow_dispatch trigger with runner_lane choice input (auto | hosted | self-hosted). Multiple scenarios (e.g., 'Dispatch input overrides the variable in both directions', 'Unset variable keeps CI on hosted runners') reference workflow_dispatch events and the runner_lane input, but no requirement mandates the trigger's existence. Tasks.md 2.7 and design.md D3 implement it.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 19,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "0ffdda7f9c2d26d5",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "spec.md 'Requirement: Runners Are Ephemeral Per Job' lists 7 SHALL statements but omits the cleanup-runner.sh ExecStopPost requirement. The scenario 'Unit runs a removable container with a single-use config' checks that ExecStopPost invokes cleanup-runner.sh, but the requirement text should include it for completeness.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 20,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "c34b6c06ab488508",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "spec.md 'Requirement: Runners Survive Host Reboot Via systemd' does not explicitly require the install-units.sh script to be copy-and-print-only (non-mutating during tests). The scenario 'Install script does not mutate the host during tests' covers this behavior, but the requirement text should mandate it.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 21,
+      "status": "addressed",
+      "axis": "observability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "f70da5bed79eb633",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "spec.md does not document the known limit that the tool-parity static scan only examines run: blocks and cannot detect container-engine commands invoked indirectly through scripts (e.g., run_live_matrix.sh calling podman). Design.md D10 explicitly documents this limit and the O6 dry-run backstop. The spec should include a scenario or note acknowledging this limitation.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 22,
+      "status": "parked",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "fingerprint": "7828314fe3659e34",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "runner-lanes.schema.json allows arbitrary self_hosted_labels array (minItems: 2, uniqueItems: true, contains: 'self-hosted') but the canonical D3 runs-on expression hardcodes fromJSON('[\"self-hosted\",\"linux\",\"ARM64\",\"gx10\"]'). The schema should constrain self_hosted_labels to exactly these 4 labels (or at minimum enforce the exact array) to prevent drift between manifest and expression. The spec scenario 'JIT labels match the routing labels' tests equality but the schema permits divergence.",
+      "resolution": "orchestrator adjudication: drift is caught by tests 2.1/3.3 tying expression and mint labels to the manifest; schema stays reusable",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 23,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "fingerprint": "b7b6dc89932b4b8a",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "wp-runner-kit package outputs.artifacts list omits gx10-runner.env.example, which is authored in task 3.2, referenced in design.md D7, and required for operator configuration. The artifact should be listed for completeness.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 24,
+      "status": "parked",
+      "axis": "compatibility",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "fingerprint": "53b303ad00b07601",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "work-packages.yaml contracts.openapi.primary points to a README.md file instead of an OpenAPI spec. The comment acknowledges 'The schema requires an openapi block, so primary points at the README that records that decision.' This workaround may cause tooling that expects a valid OpenAPI document to fail or misbehave.",
+      "resolution": "orchestrator adjudication: repo convention for changes with no HTTP surface (recorded in contracts/README.md)",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 25,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "fingerprint": "e57230fe6b51e883",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "proposal.md assumptions list has inconsistent formatting: A1-A9 use '- **A1.**' format with no blank lines between entries, but a blank line separates A9 from A10/A11, making them appear as a separate list. Minor readability issue.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 26,
+      "status": "parked",
+      "axis": "observability",
+      "type": "observability",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "fingerprint": "14f9da639442c346",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "pi"
+      ],
+      "description": "loop-state.json records two degradations: 'coordinator_projection_forbidden' (project-state submit returned forbidden) and 'audit_sink_failed' (audit sink reported failure for gate proposal_approval decision auto). These are infrastructure issues in the coordinator environment, not plan defects, but should be monitored as they may affect subsequent phases.",
+      "resolution": "orchestrator adjudication: environment degradations, not plan defects",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 27,
+      "status": "addressed",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "fingerprint": "bb03a33584753cc2",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The preferred host-isolation control in D6 (`meta skuid ghrunner fib daddr type local drop`, repeated in A11, tasks O4 and the spec scenario 'Operator verifies host services are unreachable on every host address') drops every packet owned by uid ghrunner whose destination is a local address. On an Ubuntu 24.04 host the resolver is systemd-resolved's stub at 127.0.0.53, which is a local address, so the rule also drops (a) the mint script's own DNS lookups for api.github.com \u2014 `ExecStartPre` then burns its whole `GX10_MINT_MAX_ELAPSED` budget on every start and no instance ever comes online \u2014 and (b) slirp4netns's forwarding of container DNS (10.0.2.3) to the host resolver, so even a minted runner cannot resolve github.com. The rule as written wedges the entire pool and the spec scenario would literally pass (the rule 'is listed'). Fix: exempt the resolver (`meta skuid ghrunner ip daddr 127.0.0.53 udp dport 53 accept` and the tcp equivalent, placed before the drop), or point the containers at a non-local resolver with `--dns` and state that the mint script's resolver must not be loopback; add that exemption to O4's listed rule and to the spec scenario's AND clause.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 28,
+      "status": "addressed",
+      "axis": "security",
+      "type": "correctness",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/tasks.md",
+      "fingerprint": "f88c6fe7256d0741",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The O4 isolation probe uses `curl http://<addr>:<port> && echo reachable || echo unreachable`. Against Postgres on :54322 the TCP connect succeeds, Postgres rejects the HTTP bytes and closes, and curl exits non-zero (52 'Empty reply' or 56 'Recv failure'), so the probe prints `unreachable` precisely when the port IS reachable. The same false negative applies to any non-HTTP service. Since the design (D6) makes this probe the required evidence that the nftables/loopback control holds, the runbook would certify isolation that does not exist. Use a transport-level check (`bash -c 'exec 3<>/dev/tcp/<addr>/<port>'`, `nc -z -w3`, or treat only curl exit codes 7 and 28 as 'unreachable') and reword the spec scenario 'every probe fails' to 'every TCP connect is refused or times out'.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 29,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "1040f0e2815c1bd3",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D6 (the ledger-#7 fix) now requires two concrete artefacts \u2014 the image sets `UV_CACHE_DIR=/home/runner/.cache/uv`, and routed jobs that use `astral-sh/setup-uv` pass `cache-local-path: /home/runner/.cache/uv` \u2014 but nothing implements or tests them: tasks 2.5\u20132.8 (workflow edits), 3.6/3.7 (Containerfile and its test) and the wp-workflows / wp-runner-kit package descriptions do not mention either, and no spec scenario covers them. The measured A6 speedup when the operator opts in would silently be against a bypassed cache. Add the `ENV UV_CACHE_DIR` line to task 3.7 (asserted in test 3.6), add the setup-uv `cache-local-path` edit to task 2.8 (asserted in test_tool_parity or test_routing_expression for routed jobs), and note that on the hosted lane the path is harmless because ubuntu-latest's user is also `runner`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 30,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/work-packages.yaml",
+      "fingerprint": "a496bdecf87338ad",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The D8 correlation contract makes `verify_run` depend on the workflow definition (job-level `if:`, literal `name:`, `strategy.matrix`, `continue-on-error`), yet (a) wp-tooling's scope lists `.github/workflows/**` under `deny` and omits it from `read_allow`, so the implementer cannot build fixtures from the live workflows; and (b) neither D8 nor task 4.3 says where the CLI obtains the definition \u2014 reading the local checkout while verifying a run from another commit (O6 on `main`, O11 on a fork PR) misattributes `if:`/names after any workflow edit. State that `verify-run` fetches `.github/workflows/<file>` at the run's `head_sha` via `gh api repos/{owner}/{repo}/contents/...?ref=<sha>` (read-only, within the boundary) or takes `--workflow-file`, and widen wp-tooling's read scope.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 31,
+      "status": "parked",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/session-log.md",
+      "fingerprint": "d00e299cacc2cf79",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The ledger-#12/#14 fix renamed the switch to `GX10_RUNNER_CACHE_ARGS` and inverted the default (cache off), but the companion documents were not updated: session-log.md's PLAN trade-off still says the cache is on, 'locked hash verification applies' and names `GX10_RUNNER_UV_CACHE=off`; its PLAN_ITERATE section still records 'Accept shared uv cache in solo mode as A10'; its Relevant Files line still says 'assumptions A1-A9'; plan-findings.md #4 still says team mode 'requires GX10_RUNNER_UV_CACHE=off'; and proposal.md \u00a7 What Changes item 4 still says verify-run checks 'every job succeeded', contradicting D8's skipped/warning rules. A reader following the session log will look for a variable that no longer exists.",
+      "resolution": "orchestrator adjudication: proposal What-Changes item 4 fixed; session-log.md and plan-findings.md are historical phase records and are not rewritten",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 32,
+      "status": "addressed",
+      "axis": "compatibility",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "fingerprint": "9fc70a779243e85a",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D5 sends the full manifest label set (`self-hosted`, `linux`, `ARM64`, `gx10`) as the `labels` field of `generate-jitconfig`, and spec scenario 'JIT labels match the routing labels' pins that equality. `self-hosted`, `Linux` and `ARM64` are runner-assigned default labels; GitHub's API documents `labels` as custom labels and may reject or silently dedupe the defaults (note also the case difference `linux` vs `Linux`, harmless for `runs-on` matching but visible in the runners list). Decide explicitly: either send only the custom labels (`gx10`) and have the test assert `manifest labels == defaults \u222a requested`, or record in O2/O6 that a 422 from `generate-jitconfig` on default labels is the expected failure signature and how to adapt.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 33,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "77d86697a19c3ecd",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item #5: partly resolved (the cache switch is now `$GX10_RUNNER_CACHE_ARGS` with word-splitting semantics specified and tested), but the remainder stands. D7's property list and test 3.1 still never name the `EnvironmentFile=%h/.config/gx10-runner/env` (or equivalent) line that must load `gx10-runner.env.example`'s values \u2014 without it `$GX10_RUNNER_CACHE_ARGS`, `--cpus`, `--memory`, the image ref and `GX10_MINT_MAX_ELAPSED` are all unset in `ExecStart`/`ExecStartPre` \u2014 nor whether the credential reaches the mint script via `LoadCredential=github-token:<path>` or `GX10_RUNNER_TOKEN_FILE` (O2 stores it at `~ghrunner/.config/gx10-runner/token`, which matches neither statement). Pin both in D7 and assert them in 3.1.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 34,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "spec_file": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "ee60fa1fa7936afb",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger items #19, #20, #21: all still open. The 'Runners Are Ephemeral Per Job' requirement text omits the `ExecStopPost` cleanup-runner.sh clause its own scenario checks; 'Runners Survive Host Reboot' does not require `install-units.sh` to be copy-and-print-only although its scenario does; and the tool-parity requirement does not acknowledge the D10 limit that indirect invocations via scripts are invisible to the scan and backstopped by O6. One sentence each closes them.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 35,
+      "status": "parked",
+      "axis": "compatibility",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/schemas/runner-lanes.schema.json",
+      "fingerprint": "7ace4db82dbe8be1",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item #22: still open but acceptable as-is. The schema permits any label array while D3 hard-codes four labels; drift is caught by the test in task 2.1 (expression labels == manifest) and 3.3 (mint labels == manifest), so the manifest remains the source of truth and the schema stays reusable if labels change. Accept, or tighten with `minItems: 4` plus `contains` for `gx10` if a stronger static guarantee is wanted.",
+      "resolution": "orchestrator adjudication: reviewer recommends accept (same as #22)",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 36,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "architecture",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/work-packages.yaml",
+      "fingerprint": "3f13e97cd0f3d3a3",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item #23: still open. wp-runner-kit `outputs.artifacts` lists five files but omits `deploy/gx10-runner/gx10-runner.env.example`, `Containerfile`'s companion `toolchain.txt`, and the systemd unit's env example that tests 3.1 and D7 depend on. Add them so the integration package's scope check sees the full output set.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 37,
+      "status": "parked",
+      "axis": "compatibility",
+      "type": "compatibility",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/work-packages.yaml",
+      "fingerprint": "027649b694694fb9",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger items #17 and #24: still present, accept. Pointing `contracts.openapi.primary` at the change-local README is this repository's recorded convention for changes with no HTTP surface, and change-local contract paths in work-packages.yaml are consumed only during the implementation phase, before archival; the path-stability rule targets tests. No action beyond the existing comment.",
+      "resolution": "orchestrator adjudication: reviewer itself recommends accept (same as #17/#24)",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 38,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/proposal.md",
+      "fingerprint": "7e24a3521efb623c",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item #25: still open. A blank line separates A9 from A10/A11 in the proposal's assumptions list, splitting it into two Markdown lists. Remove the blank line. Also in tasks O4, the bullet 'Before enabling the units, install the host-service isolation control' is placed after the `systemctl --user enable --now` instruction; move it first so the runbook's step order matches its own wording.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 39,
+      "status": "parked",
+      "axis": "observability",
+      "type": "observability",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/loop-state.json",
+      "fingerprint": "69db9233e56f9b51",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item #26: unchanged. The two recorded degradations (coordinator projection forbidden at INIT, audit sink failure at the PLAN gate) are environment issues, not plan defects. Accept for this review; the orchestrator should confirm the audit sink is healthy before the IMPLEMENT phase records package decisions.",
+      "resolution": "orchestrator adjudication: environment degradations, not plan defects (duplicate of #26)",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 40,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "contract_mismatch",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "fingerprint": "2cdc83dfde5d3604",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "The runner unit remains underspecified and may be nonfunctional. D7 and task 3.1 do not require an EnvironmentFile entry that loads gx10-runner.env.example, while task 3.2 expects that file to supply the repository, image, limits, labels, retry budget, and cache arguments used by ExecStartPre and ExecStart. They also do not require LoadCredential=github-token:<path>, and the example environment-file task does not include GX10_RUNNER_TOKEN_FILE. An implementation can therefore satisfy every planned unit test while the mint script receives neither its configuration nor a credential. Specify both files unambiguously and test the EnvironmentFile and credential wiring.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 41,
+      "status": "addressed",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "fingerprint": "1f338c484c0a57a2",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "The reboot/restart design still has no stale-container or stale-registration recovery. ExecStart uses a fixed container name without --replace, so a container retained after an unclean stop can make every subsequent restart fail with a name conflict. A hard reboot can also bypass ExecStopPost and leave an unused JIT registration offline indefinitely. Require tested pre-start cleanup or --replace for the container, and sweep offline registrations matching the instance's runner-name prefix before minting another registration.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 42,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "architecture",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "fingerprint": "6a27c11e6ed8a211",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "wp-integration is declared responsible for merging the package branches, but its scope.write_allow permits writes only below openspec/changes/migrate-ci-to-self-hosted-gx10-runners/**. Merging wp-workflows, wp-runner-kit, wp-tooling, and wp-docs necessarily materializes changes under .github/, deploy/, scripts/, docs/, and skills/. Under scope enforcement the integration package cannot perform its declared work. Either make package materialization an explicit coordinator operation completed before wp-integration starts, or grant the integration package the exact output paths it must merge.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 43,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "057599b55d4ab320",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "The requirement that the canonical expression's self-hosted labels equal routing.self_hosted_labels still lacks a scenario that changes the manifest independently and observes failure. The existing canonical-expression scenario can pass while repository_variable or dispatch_input in the manifest drifts from the hard-coded vars.CI_RUNNER_LANE and inputs.runner_lane references. Add a scenario and test tying all three routing fields to the expression.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 44,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "70d6478ab3c7f1a7",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "The normative CLI contract for explicit run filters and bounded --limit fetching still has no behavioral scenario. Task 4.1 checks argument parsing only, so an implementation that accepts --limit but fetches every page before truncating can pass. Add a stubbed-gh scenario that asserts the emitted query filters and bounds the number of fetched results or pages.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 45,
+      "status": "addressed",
+      "axis": "security",
+      "type": "security",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "fingerprint": "7ed646a5c4431299",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "D5 still claims that a job reading ACTIONS_RUNNER_INPUT_JITCONFIG gains nothing. The encoded JIT configuration contains runner identity and Actions-service credentials usable during the job's lifetime. Ephemerality limits the exposure but does not eliminate it. Document this residual capability accurately and either accept it explicitly or use an entrypoint that removes the value from the environment before executing job steps.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 46,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "spec_file": "/home/jankneumann/Coding/agentic-coding-tools/.git-worktrees/migrate-ci-to-self-hosted-gx10-runners/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md",
+      "fingerprint": "6144d0112ee68648",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "D8 says compare derives a run's lane from actual placement of its routed jobs but does not define the result when those jobs have mixed placement, no assigned runner, or conflicting labels. Such runs can otherwise be counted in either sample and distort the acceptance ratio. Define these runs as invalid or excluded with a diagnostic, and add a fixture covering mixed placement.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 47,
+      "status": "parked",
+      "axis": "compatibility",
+      "type": "contract_mismatch",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "fingerprint": "7f913e614e6c7379",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "contracts.openapi.primary still names contracts/README.md even though that file is not an OpenAPI document. Schema validation based only on path existence can pass while consumers that parse the declared primary contract fail. Represent the absence of an OpenAPI surface using the work-package schema's supported sentinel or contract type; if the schema truly cannot express this, escalate that schema defect instead of publishing Markdown as OpenAPI.",
+      "resolution": "orchestrator adjudication: same as #24; work-package schema requires an openapi block; not a plan defect of this change",
+      "parked_reason": "reject_out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 48,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "architecture",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "fingerprint": "e5073cbe44e06c3a",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "codex"
+      ],
+      "description": "wp-runner-kit still omits deploy/gx10-runner/gx10-runner.env.example from outputs.artifacts even though the package authors it and the unit depends on its configuration contract. Add it to the declared outputs so package handoff and evidence collection include the required operator configuration.",
+      "consensus_status": "unconfirmed"
+    }
+  ]
+}
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/README.md b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/README.md
new file mode 100644
index 00000000..902a207a
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/README.md
@@ -0,0 +1,21 @@
+# Contracts — migrate-ci-to-self-hosted-gx10-runners
+
+| Sub-type | Applies? | Artifact |
+|---|---|---|
+| OpenAPI | No. The change adds no HTTP endpoint. `ci_wallclock.py` only *consumes* GitHub's REST API through `gh api` | — |
+| Database | No. The change makes no schema change | — |
+| Events | No. The change adds no event payload | — |
+| Config schema | **Yes** | `schemas/runner-lanes.schema.json` |
+
+The lane manifest is the coordination boundary between packages. `wp-workflows` routes jobs
+according to it. `wp-runner-kit` reads `routing.self_hosted_labels` for the JIT label set.
+`wp-tooling` uses it to verify runs.
+
+`wp-contracts` promotes the draft here to `.github/runner-lanes.schema.json`. Every
+downstream package validates against that promoted copy.
+
+Two companion contracts are defined in `design.md` and tested in place, not schema'd:
+
+- The canonical `runs-on` expression (D3).
+- The container env-file contract (D5). The file contains only `ACTIONS_RUNNER_INPUT_JITCONFIG`
+  and `GX10_RUNNER_ID`.
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/schemas/runner-lanes.schema.json b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/schemas/runner-lanes.schema.json
new file mode 100644
index 00000000..5fc1533f
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/schemas/runner-lanes.schema.json
@@ -0,0 +1,71 @@
+{
+  "$schema": "https://json-schema.org/draft/2020-12/schema",
+  "$id": "runner-lanes.schema.json",
+  "title": "CI runner lane manifest",
+  "description": "Classifies every job of the routed GitHub Actions workflows as routed (follows the lane selector) or hosted (pinned to ubuntu-latest with a justification). See migrate-ci-to-self-hosted-gx10-runners design D1.",
+  "type": "object",
+  "additionalProperties": false,
+  "required": ["schema_version", "routing", "workflows"],
+  "properties": {
+    "schema_version": { "const": 1 },
+    "routing": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["repository_variable", "dispatch_input", "self_hosted_labels", "hosted_label"],
+      "properties": {
+        "repository_variable": { "type": "string", "pattern": "^[A-Z][A-Z0-9_]*$" },
+        "dispatch_input": { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" },
+        "self_hosted_labels": {
+          "type": "array",
+          "minItems": 2,
+          "uniqueItems": true,
+          "items": { "type": "string", "minLength": 1 },
+          "contains": { "const": "self-hosted" }
+        },
+        "hosted_label": { "const": "ubuntu-latest" }
+      }
+    },
+    "workflows": {
+      "type": "object",
+      "minProperties": 1,
+      "propertyNames": { "pattern": "^[A-Za-z0-9_.-]+\\.ya?ml$" },
+      "additionalProperties": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": ["jobs"],
+        "properties": {
+          "jobs": {
+            "type": "object",
+            "minProperties": 1,
+            "propertyNames": { "pattern": "^[A-Za-z_][A-Za-z0-9_-]*$" },
+            "additionalProperties": { "$ref": "#/$defs/job" }
+          }
+        }
+      }
+    }
+  },
+  "$defs": {
+    "job": {
+      "oneOf": [
+        {
+          "type": "object",
+          "additionalProperties": false,
+          "required": ["lane"],
+          "properties": { "lane": { "const": "routed" } }
+        },
+        {
+          "type": "object",
+          "additionalProperties": false,
+          "required": ["lane", "reason_code", "reason"],
+          "properties": {
+            "lane": { "const": "hosted" },
+            "reason_code": {
+              "enum": ["container-engine", "amd64-only", "privileged-token", "measured-slower"]
+            },
+            "reason": { "type": "string", "minLength": 10 }
+          }
+        }
+      ]
+    }
+  }
+}
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md
new file mode 100644
index 00000000..856ee1c7
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md
@@ -0,0 +1,515 @@
+# Design — migrate-ci-to-self-hosted-gx10-runners
+
+Selected approach: **A** (proposal.md). It combines four parts:
+- a lane manifest;
+- an inline canonical `runs-on` expression that defaults to the hosted lane and excludes forks;
+- host-minted JIT runners in rootless podman containers;
+- a systemd user template unit.
+
+## Context and constraints
+
+- **Host.** The GX10 runs linux/aarch64, Ubuntu 24.04 class, systemd 255, podman 4.9.3, rootless.
+  There is no Docker daemon.
+- **Rootless networking.** Podman 4.9 uses `slirp4netns` with `allow_host_loopback=false` by
+  default. A container therefore cannot reach host loopback services: the coordinator API and
+  Postgres on `:54322`.
+- **Current workflows.** `ci.yml` has 25 jobs and `security.yml` has 3, all on `ubuntu-latest`.
+  The triggers are `push` (main), `pull_request`, and `merge_group`.
+- **Other services on the host.** The host also carries the ri-08 dispatcher daemon and the
+  vendor CLIs. Runner containers must not exhaust its resources or reach its credentials.
+- **Implementation boundary (proposal.md § Hard boundary).** The implementation must not:
+  - register runners;
+  - mint tokens;
+  - change repository settings or variables;
+  - install, enable or start units or containers;
+  - touch `main`.
+
+## Decisions
+
+### D1 — A machine-readable lane manifest is the single source of routing truth
+
+`.github/runner-lanes.yaml` (schema `.github/runner-lanes.schema.json`, drafted in
+`contracts/schemas/runner-lanes.schema.json`) holds the following:
+
+```yaml
+schema_version: 1
+routing:
+  repository_variable: CI_RUNNER_LANE   # unset or anything but "self-hosted" => hosted
+  dispatch_input: runner_lane           # workflow_dispatch choice: auto | hosted | self-hosted
+  self_hosted_labels: [self-hosted, linux, ARM64, gx10]
+  hosted_label: ubuntu-latest
+workflows:
+  ci.yml:
+    jobs:
+      test: { lane: routed }
+      test-integration:
+        lane: hosted
+        reason_code: container-engine
+        reason: "services: paradedb container needs a container engine; none is exposed inside runner containers (D6)."
+      # ... every job, no omissions
+  security.yml:
+    jobs: { ... }
+```
+
+**Rationale.** The manifest is an auditable record of which jobs run on which lane and why. It
+also lets tests check the workflows against the manifest instead of hard-coding job names.
+Without it, the hosted pin is a bare `ubuntu-latest` string, and nothing distinguishes "pinned
+on purpose" from "never migrated".
+
+**Closed `reason_code` set:**
+
+| Code | Meaning |
+|---|---|
+| `container-engine` | The job needs `services:`, a Docker build, or podman |
+| `amd64-only` | The job uses an image, binary or validated artifact that exists only for amd64, or fails on arm64 |
+| `privileged-token` | The job holds a write-scoped `GITHUB_TOKEN` |
+| `measured-slower` | The operator moved the job back after measurement |
+
+### D2 — Initial job classification
+
+| Workflow | Job | Lane | Reason |
+|---|---|---|---|
+| ci | test-openbao-credentials, test, test-infra-skills, test-skills, skill-audit-freshness, validate-specs, context-drift-gate, contract-breaking-change-gate, coverage-ratchet, check-docker-imports, formal-coordination, gen-eval-tests, code-search-tests, system-one-decisions-tests, agent-scenarios-tests, requirement-traceability-sweep, context-eval, semantic-enablement-gate, validate-context-producers, test-codebase-atlas | routed | — |
+| ci | test-openbao-live | hosted | `container-engine`: `run_live_matrix.sh` starts an OpenBao container through podman or docker |
+| ci | test-integration, gen-eval | hosted | `container-engine`: `services:` Postgres (paradedb) and `sudo apt-get` |
+| ci | docker-smoke-import | hosted | `container-engine` (buildx with the `type=gha` cache). The image it validates is the amd64 production image (Railway), so arm64 would also check the wrong architecture |
+| ci | dependency-update-remediation | hosted | `privileged-token`: it holds `contents: write` and pushes. Write tokens stay off the shared host |
+| security | secret-scan, dependency-audit-coordinator, dependency-audit-skills | routed | — |
+
+`check-docker-imports` is routed because it is a static Python import check and needs no engine.
+
+Arm64 risk for `secret-scan` (gitleaks-action binary download) and `formal-coordination` (Java)
+is resolved by the operator dry run (O6). A failure there produces a manifest move to
+`amd64-only`, not a workaround.
+
+### D3 — Canonical inline `runs-on` expression (no routing job)
+
+Every routed job uses exactly this string. The tests compare it after whitespace normalization:
+
+```yaml
+runs-on: ${{ (github.event_name == 'push' || github.event_name == 'workflow_dispatch' || (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository)) && ((github.event_name == 'workflow_dispatch' && inputs.runner_lane != 'auto') && inputs.runner_lane || vars.CI_RUNNER_LANE) == 'self-hosted' && fromJSON('["self-hosted","linux","ARM64","gx10"]') || 'ubuntu-latest' }}
+```
+
+**Evaluation table.** This table is the spec for the tests' reference evaluator (task 2.1):
+
+| Event | Fork? | dispatch input | `vars.CI_RUNNER_LANE` | Result |
+|---|---|---|---|---|
+| pull_request | yes | — | any | `ubuntu-latest` |
+| pull_request | no | — | unset / `hosted` / other | `ubuntu-latest` |
+| pull_request | no | — | `self-hosted` | GX10 labels |
+| push | — | — | `self-hosted` | GX10 labels |
+| push | — | — | unset | `ubuntu-latest` |
+| merge_group | — | — | any | `ubuntu-latest` |
+| any other event | — | — | any | `ubuntu-latest` |
+| workflow_dispatch | — | `self-hosted` | any | GX10 labels |
+| workflow_dispatch | — | `hosted` | any | `ubuntu-latest` |
+| workflow_dispatch | — | `auto` | follows variable | follows variable |
+
+**Event eligibility is an allowlist, not a fork test.** Only three event shapes can reach the
+GX10: `push` (to `main`, i.e. code already merged), `workflow_dispatch` (started by a user with
+write access, on a ref of this repository) and a same-repository `pull_request`. Everything
+else resolves to `ubuntu-latest`. In particular, **`merge_group` always runs hosted**: a merge
+queue builds a temporary merge commit that can contain an approved *fork* PR's code, and the
+`merge_group` payload carries no reliable head-repository field to tell fork from same-repo
+entries. Routing it would let fork code execute on the host after a maintainer enqueues it,
+which the fork requirement forbids. The cost is that merge-queue runs keep hosted wall-clock
+time; the post-merge `push` run on `main` still routes. A later change may route `merge_group`
+only if fork provenance of every queued PR can be established safely.
+
+**Rejected: routing job (Approach B).** It adds a serial hosted hop in front of every job,
+which costs wall-clock time.
+
+**Rejected: YAML anchors.** GitHub Actions supports anchors, but `actionlint` and some
+downstream parsers in this repository do not handle them uniformly. Repeating the expression
+and enforcing it with a test is the safer option.
+
+The labels inside `fromJSON(...)` must equal `routing.self_hosted_labels` in the manifest, the
+`vars.<name>` reference must name `routing.repository_variable`, and the `inputs.<name>`
+references must name `routing.dispatch_input`. A test checks all three, so no field of the
+manifest's routing block is decorative.
+
+### D4 — Defense in depth: in-job fork guard and trigger allowlist
+
+Each routed job's **first** step:
+
+```yaml
+- name: Refuse ineligible events on self-hosted runner
+  if: runner.environment == 'self-hosted' && !(github.event_name == 'push' || github.event_name == 'workflow_dispatch' || (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository))
+  shell: bash
+  working-directory: ${{ github.workspace }}
+  run: |
+    echo "::error::Only push, workflow_dispatch and same-repository pull_request runs may execute on self-hosted runners (fork PRs and merge_group never); routing expression bypassed."
+    exit 1
+```
+
+The guard condition is `runner.environment == 'self-hosted'` combined with the **negation of
+the D3 event-eligibility clause**, character for character, so a fork `pull_request` and every
+`merge_group` run fail the job if they ever land on a self-hosted runner. A test pins the
+guard's clause to the clause inside the canonical expression.
+
+`working-directory` is overridden so that jobs with `defaults.run.working-directory` do not fail
+on a directory that has not been checked out yet.
+
+Trigger allowlist for both workflows: `push`, `pull_request`, `merge_group`,
+`workflow_dispatch`. A test fails if either workflow gains any of the following, because they
+run with base-repo privileges on fork-supplied input:
+- `pull_request_target`
+- `workflow_run`
+- `issue_comment`
+
+**Repository setting (operator-only, O5).** Set *Require approval for all external
+contributors* through the `fork-pr-contributor-approval` API. Approval only lets a fork run
+start. Under D3 that run still lands on `ubuntu-latest`, and so does any `merge_group` run that
+later carries the fork PR's code.
+
+### D5 — Host-minted JIT config; credentials never enter the container
+
+`deploy/gx10-runner/mint-jitconfig.sh <instance>` runs as the unit's `ExecStartPre` on the host.
+It works in four steps:
+
+1. It reads the credential from `$CREDENTIALS_DIRECTORY/github-token` (systemd
+   `LoadCredential=`), falling back to `GX10_RUNNER_TOKEN_FILE`. It refuses any credential file
+   whose mode is wider than 0600.
+2. It calls
+   `POST /repos/{owner}/{repo}/actions/runners/generate-jitconfig` with:
+   - `name=gx10-<hostname>-<instance>-<epoch>`
+   - `runner_group_id=1`
+   - `labels` = the **custom** labels only: manifest `self_hosted_labels` minus the labels the
+     runner assigns itself (`self-hosted`, `Linux`, `ARM64`, compared case-insensitively),
+     i.e. `["gx10"]` today, read from the env file. The API documents `labels` as custom
+     labels, so sending the defaults risks a 422; the effective label set is defaults ∪
+     requested, which must equal the manifest set (case-insensitively)
+   - `work_folder=_work`
+3. It writes `ACTIONS_RUNNER_INPUT_JITCONFIG=<encoded>` and the runner id into
+   `$XDG_RUNTIME_DIR/gx10-runner/<instance>.env`, with umask 077.
+4. On API failure it retries with exponential backoff (per-attempt delay capped at 300 s) inside
+   a **total retry budget** `GX10_MINT_MAX_ELAPSED` (default 600 s), then exits non-zero so
+   systemd restarts it. The budget must stay below the unit's `TimeoutStartSec=` (D7), or
+   systemd kills the script mid-backoff, restarts it after `RestartSec`, and the backoff never
+   takes effect (the API is hammered every ~10 s instead). A test pins
+   `GX10_MINT_MAX_ELAPSED < TimeoutStartSec`.
+
+The container receives only the single-use encoded JIT config, through `--env-file`. That value
+is not inert: it encodes the runner's identity and Actions-service credentials, and because it
+is in the runner's environment every job step inherits it, so PR code could act as that runner
+against the Actions service (read its own job message, post status) **while the job runs**.
+Ephemerality bounds this to one job on one single-use registration that cannot be reused after
+the job, and it grants nothing on the host or on other jobs. This residual is **accepted**. A
+narrower option, deferred, is an entrypoint wrapper that reads the variable, `unset`s it and
+passes it as `--jitconfig` (at the cost of the value appearing briefly in `ps`).
+
+**Credential choice.** A fine-grained PAT scoped to this repository with
+*Administration: read and write*, expiring in 90 days or less (A3).
+
+**Rejected: registration token plus `config.sh --ephemeral` inside the container.** Either the
+long-lived credential or a reusable registration token would sit inside the PR-code container.
+
+**Deferred: GitHub App.** It gives short-lived installation tokens, but needs JWT signing on the
+host. It is recorded as the upgrade path in the runbook.
+
+`cleanup-runner.sh <instance>` runs as `ExecStopPost`. If the JIT runner id from the env file
+is still registered and offline, it deletes the registration. Deletion is best-effort and
+always exits 0.
+
+`ExecStopPost` does not run after a power loss or hard reboot, so never-used registrations can
+survive it. Before minting, `mint-jitconfig.sh <instance>` therefore **sweeps** stale
+registrations: it lists the repository's runners (read-only GET, bounded by `per_page=100`)
+and deletes every **offline** runner whose name starts with `gx10-<hostname>-<instance>-`
+(the instance's own prefix, so it never touches another instance's or another host's runners).
+The sweep is best-effort: a failure is logged and does not consume the mint retry budget.
+
+**Host DNS must stay reachable for `ghrunner`.** The mint script resolves `api.github.com`
+through the host resolver; on Ubuntu 24.04 that is systemd-resolved's stub at `127.0.0.53`, a
+local address. The D6 nftables control therefore exempts the resolver (see D6).
+
+### D6 — Container hardening and isolation
+
+The `podman run` invocation in the unit (`ExecStart`) MUST include:
+- `--rm`
+- `--pull=never` (the image is the locally built `localhost/gx10-runner:<sha>` from O3; a start
+  must never pull a different image from a registry)
+- `--network slirp4netns:allow_host_loopback=false` (explicit, see below)
+- `--name gx10-runner-%i`
+- `--env-file %t/gx10-runner/%i.env`
+- `--security-opt no-new-privileges`
+- `--cap-drop ALL`
+- `--pids-limit`
+- `--cpus` and `--memory`, from the env file (default 2 CPU / 8 GiB per instance)
+- `--tmpfs /tmp`
+- the word `$GX10_RUNNER_CACHE_ARGS`, unbraced and standing alone, which systemd splits on
+  whitespace into zero or more arguments. It is empty by default (no cache volume); the only
+  opted-in value is `--volume gx10-runner-uv-cache:/home/runner/.cache/uv` (see the uv cache
+  trade-off below)
+
+It MUST NOT include any of the following:
+- `--privileged`
+- `--network host`
+- a mounted podman or docker socket (`*.sock`)
+- any bind mount of the host user's home directory
+
+**Network is pinned explicitly, not inherited from the podman default.** Podman 4.9 (the GX10
+today) defaults rootless networking to `slirp4netns` with `allow_host_loopback=false`, which
+makes host loopback services (coordinator API, Postgres on `:54322`) unreachable. Podman 5.x
+changes the default to `pasta`, which by default maps the gateway address to the host and
+would expose those services to PR code after a routine host upgrade. The unit therefore passes
+`--network slirp4netns:allow_host_loopback=false` and a test requires that exact option. If the
+host later moves to podman 5 and the operator prefers `pasta`, the equivalent is
+`--network pasta:--no-map-gw`, which is a reviewed unit change, not a default.
+
+**What the pin does not cover: services bound to non-loopback host addresses.**
+`allow_host_loopback=false` only removes the `10.0.2.2 → 127.0.0.1` mapping. slirp4netns still
+NATs container traffic through the host's network stack as the `ghrunner` user, so any host
+service listening on `0.0.0.0` or on the host's LAN or Tailscale address (a compose-published
+`0.0.0.0:54322` Postgres is the common case; the coordinator API and the ri-08 daemon may also
+bind non-loopback) stays reachable from PR code through the host's real IP. Isolation of host
+services therefore rests on one of two operator-enforced controls, and O4 must prove it:
+1. **Preferred — an nftables egress rule for the runner user**: in an `output` hook chain,
+   first accept DNS to the host stub resolver
+   (`meta skuid ghrunner ip daddr 127.0.0.53 udp dport 53 accept` and the same for `tcp`), then
+   drop every other packet whose socket owner is `ghrunner` and whose destination is a local
+   host address (`meta skuid ghrunner fib daddr type local drop`). Because slirp4netns runs as
+   `ghrunner`, this blocks every host-local service regardless of how it binds, while leaving
+   internet egress and name resolution intact (both for the mint script and for container DNS,
+   which slirp4netns forwards through the host resolver). Without the DNS exemption the mint
+   script cannot resolve `api.github.com`, burns its retry budget on every start, and no
+   instance ever comes online. Installing the rule is operator-only.
+2. **Fallback — loopback-only binding**: every host service the runners must not reach binds to
+   `127.0.0.1` only (compose ports published as `127.0.0.1:54322:5432`), checked with
+   `ss -ltnp`.
+
+O4's verification probes the coordinator API port and `:54322` on **each** host address
+(`10.0.2.2`, the LAN address and the Tailscale address, from `hostname -I`) from inside a
+runner container and requires every **TCP connect** to be refused or to time out. The probe is
+transport-level (`timeout 3 bash -c 'exec 3<>/dev/tcp/<addr>/<port>'`), not an HTTP request:
+`curl` against a non-HTTP service such as Postgres fails *after* connecting, which would report
+"unreachable" exactly when the port is reachable. A probe of `10.0.2.2` alone is not sufficient
+evidence. O4 also confirms DNS still works for `ghrunner` (`getent hosts api.github.com`).
+
+**Shared uv cache trade-off: off by default, explicit operator opt-in.** A cache shared across
+jobs speeds up `uv sync`. It is also a cross-trust poisoning vector: a same-repository PR job
+can write arbitrary files into a cache that a later `main` push job reads, and uv does not
+re-hash cached entries on reuse. Lockfile hash checking does **not** mitigate this: it applies
+at download time only, and several jobs run `uv sync --all-extras` without `--locked`,
+`uv run --with pytest-cov` or `uv pip install pip-audit`, which resolve outside the lockfile.
+
+"Every same-repository branch author is a trusted human" is **not** true here. Same-repository
+branches are also pushed by automation — Dependabot (whose PRs carry freshly bumped third-party
+packages) and the agent PR sources the `merge-pull-requests` skill accepts (Jules, Codex and
+other agent branches) — and by any holder of a leaked collaborator credential. Pushing a branch
+is also weaker than merging to protected `main`. With a shared writable cache, such a branch
+could influence a later `main` job before any human has reviewed its diff.
+
+Per-trust-tier volumes are not available: the container starts before the job is assigned, so
+the unit cannot choose a volume by event. The design therefore makes the cache **opt-in**:
+- `gx10-runner.env.example` ships `GX10_RUNNER_CACHE_ARGS=` (empty), so a default install
+  mounts no shared cache and every job starts with an empty in-container cache.
+- Enabling it is an operator decision recorded as an explicit risk acceptance (assumption A10,
+  runbook step O4): the operator sets
+  `GX10_RUNNER_CACHE_ARGS=--volume gx10-runner-uv-cache:/home/runner/.cache/uv`, and records
+  in the runbook's acceptance line who accepted the risk and on what date, having confirmed that
+  every same-repository writer (humans and automation) is acceptable as a cache writer.
+- Disabling it again is the same variable set back to empty, plus
+  `podman volume rm gx10-runner-uv-cache`. A move to team mode requires disabling it.
+- A trust-split follow-up (a separate cache-holding pool selected by label for `push` runs
+  only) is the upgrade path if the cache is needed without the shared-writer risk.
+
+When the cache is on, routed jobs must actually use it: the container sets
+`UV_CACHE_DIR=/home/runner/.cache/uv`, and routed jobs that use `astral-sh/setup-uv` pass
+`cache-local-path: /home/runner/.cache/uv` so the action does not redirect the cache to
+`$RUNNER_TEMP`. The setup-* toolcache stays inside the container, because concurrent writers
+would race on a shared toolcache.
+
+**Runner image.** `deploy/gx10-runner/Containerfile` is built
+`FROM ghcr.io/actions/actions-runner:<version>@sha256:<digest>`, a multi-arch image that is
+pinned with no `latest`. It adds a baseline toolchain declared in
+`deploy/gx10-runner/toolchain.txt`:
+- `git`, `curl`, `jq`, `make`, `build-essential`
+- `unzip`, `xz-utils`, `zstd`, `ca-certificates`, `python3`
+
+The entrypoint is `/home/runner/run.sh` with the JIT config from the environment. The runner
+user stays non-root, and sudo is not granted to it.
+
+### D7 — systemd user template unit, dedicated lingering user
+
+`deploy/gx10-runner/systemd/gx10-runner@.service` is installed as a **user** unit for a
+dedicated `ghrunner` account (A4). It has these properties:
+- `Restart=always` and `RestartSec=10`. The container exits after its single job, and systemd
+  starts a fresh one. This is the per-job ephemerality mechanism.
+- `StartLimitIntervalSec=0` in the **`[Unit]`** section (that is where systemd ≥ 230 reads it;
+  in `[Service]` it is ignored with a warning), because restarts after normal jobs are frequent
+  and expected. Back-off on persistent API failure lives in `mint-jitconfig.sh`, not in the
+  start limit.
+- `TimeoutStartSec=900`, which bounds `ExecStartPre` and must exceed the mint script's total
+  retry budget `GX10_MINT_MAX_ELAPSED` (D5). The default of 90 s would kill the script in the
+  middle of its backoff.
+- `EnvironmentFile=%h/.config/gx10-runner/env`: the operator's copy of
+  `gx10-runner.env.example`. It supplies the repository slug, image reference, CPU and memory
+  limits, labels, `GX10_MINT_MAX_ELAPSED` and `GX10_RUNNER_CACHE_ARGS` to `ExecStartPre` and
+  `ExecStart`; without it they are all unset. It is distinct from the per-instance container
+  env file `%t/gx10-runner/%i.env` that the mint script writes (JIT config and runner id only).
+- `LoadCredential=github-token:%h/.config/gx10-runner/token`: the registration credential (O2
+  stores it at that path, mode 0600). systemd exposes it to `ExecStartPre` as
+  `$CREDENTIALS_DIRECTORY/github-token`, the mint script's primary source;
+  `GX10_RUNNER_TOKEN_FILE` remains only as a fallback for running the script by hand and is
+  not set in the env file.
+- `ExecStartPre` is the mint script.
+- `ExecStart` is `podman run --replace …` (D6). `--replace` removes a leftover container of the
+  same name (from an unclean stop or a crash before `--rm` cleanup) instead of failing on the
+  name conflict, which would otherwise make `Restart=always` retry every 10 s forever while the
+  instance silently drops out of the pool.
+- `ExecStopPost` is the cleanup script.
+- `TimeoutStopSec=90`.
+- `[Install] WantedBy=default.target`.
+
+Reboot survival comes from `loginctl enable-linger ghrunner`, an operator-only step (O1). It
+starts the user manager at boot without a login, and the user manager starts enabled
+`default.target` units.
+
+`deploy/gx10-runner/install-units.sh` is a script for the **operator** to run. It copies the
+units and scripts into `<prefix>/.config/systemd/user` and `<prefix>/.local/lib/gx10-runner`.
+`--prefix` defaults to the `ghrunner` home directory. The script then prints the
+`loginctl enable-linger` and `systemctl --user enable --now` commands. It never executes
+`systemctl`, `loginctl` or `podman`. The implementation tests it only with
+`--prefix <tmpdir>`, and never runs it against a real home directory.
+
+**Initial instance count.** 8 (A9). The operator tunes it against O8.
+
+**Rejected: a system unit running rootful podman.** It gives a larger blast radius on container
+escape.
+
+**Rejected: rootless podman under the operator's own account.** That account holds vendor CLI
+credentials and SSH keys.
+
+### D8 — Measurement and verification tooling is pure over JSON
+
+`scripts/ci/ci_wallclock.py` provides:
+- `median_wallclock(runs, *, conclusion="success")`. It computes `run_started_at → updated_at`
+  seconds over successful runs and excludes cancelled and failed runs.
+- `compare(baseline, candidate, *, threshold=0.85, min_n=5)`. It returns pass/fail plus the
+  numbers. Pass requires `candidate_median ≤ threshold × baseline_median` and `n ≥ min_n` on
+  both sides (A6).
+- `verify_run(jobs, manifest, workflow, *, expected_lane="self-hosted")`. It returns one
+  violation per job in these cases:
+  - with `expected_lane="self-hosted"`, a routed job did not run on a runner labelled `gx10`;
+    with `expected_lane="hosted"`, a routed job ran on a self-hosted runner (the O12 rollback
+    check);
+  - a hosted job ran on a self-hosted runner;
+  - a job concluded anything other than `success` or `skipped` (a job declared
+    `continue-on-error: true` is reported as a **warning**, not a violation; the result model is
+    `{violations: [...], warnings: [...]}` and the CLI exits non-zero only on violations);
+  - a job concluded `skipped` although its workflow definition has **no** job-level `if:`
+    (an unconditional job can only be skipped by an upstream failure, which is a violation);
+  - a manifest job is missing from the run's jobs list.
+
+  A job that concluded `skipped` **and** has a job-level `if:` is not a violation, and its
+  runner placement is not checked, because a skipped job is never assigned a runner. This is
+  the normal case for `dependency-update-remediation`, whose `if:` limits it to Dependabot pull
+  requests: it is skipped on every dispatch, push and ordinary PR run. Without this rule every
+  O6, O7, O11 and O12 check would report a false violation.
+
+**Job correlation contract.** The jobs API returns each job's display `name`, not its YAML job
+id. `verify_run` maps a manifest job id to API job entries by deriving the expected display
+name from the workflow definition:
+- a job with no `name:` key is displayed as its job id; a job with a literal `name:` is
+  displayed as that string;
+- a job with a `strategy.matrix` expands to one API entry per combination, displayed as
+  `<display name> (<v1>, <v2>, …)`; `verify_run` matches the prefix `<display name> (` and
+  checks every expansion individually (each must meet the lane and conclusion rules, and at
+  least one expansion must be present);
+- a `name:` that contains an expression (`${{`) is rejected by the manifest completeness test,
+  because it cannot be resolved statically.
+
+`verify-run` reads the workflow definition **at the run's `head_sha`**, fetched read-only with
+`gh api repos/{owner}/{repo}/contents/.github/workflows/<file>?ref=<head_sha>` (or from a local
+file passed with `--workflow-file`, which the tests use), never from the local checkout, so a
+run of an older or newer commit is judged against the job-level `if:`, `name:`,
+`strategy.matrix` and `continue-on-error` it actually ran with.
+
+Today no job in `ci.yml` or `security.yml` sets `name:` or `strategy.matrix`, so every display
+name equals its job id. The completeness test (task 2.2) asserts that derived display names are
+unique within each workflow, so the mapping is one-to-one; an API entry that matches no
+manifest job is reported as a violation ("unknown job"), which also catches a renamed job.
+
+A run's lane is derived from where its routed jobs actually ran, using the runner labels in the
+jobs API. It is not derived from dispatch inputs, because the runs API does not expose them.
+`compare --baseline-lane hosted --candidate-lane self-hosted` groups runs on that basis. A run
+is classified only when **all** its routed jobs that were assigned a runner ran on the same
+lane. A run with mixed placement, or with no routed job assigned a runner, is **excluded** from
+both samples and listed in a diagnostic (`excluded_runs` with a reason), so it cannot distort
+the ratio.
+
+Run selection for `median` and `compare` is explicit, so that the A6 measurement is reproducible:
+- `--workflow <file>` (required);
+- `--head-sha <sha>` restricts to runs of one commit, which is how the paired O8 dispatch runs
+  are selected;
+- `--event <name>` (for example `workflow_dispatch` for O8, `pull_request` for the corroborating
+  window);
+- `--since` / `--until` (ISO dates) bound the before/after window;
+- `--limit` (default 200) caps the number of runs fetched, so a paginated fetch is bounded.
+
+The CLI wrappers (`median`, `compare`, `verify-run`) shell out to `gh api` only when the
+**operator** runs them. The tests use JSON fixtures only, with no network access.
+
+### D9 — Hosted fallback is operator-switched; automatic fallback deferred
+
+When `CI_RUNNER_LANE=self-hosted` and no GX10 runner is online, routed jobs queue. GitHub's
+queue limit is 24 h, and `timeout-minutes` does not cover queue time.
+
+The documented fallback works in three steps:
+1. `gh variable set CI_RUNNER_LANE --body hosted`, or `gh variable delete CI_RUNNER_LANE`.
+2. Cancel the queued runs.
+3. Re-run them.
+
+The runbook gives a detection command that counts runs queued for more than 10 minutes.
+
+Automatic fallback needs a token that can list runners. That is either a routing job (Approach
+B, rejected for latency) or a host-side watchdog that changes repository variables, which is
+outside this change's boundary. It is filed as a follow-up candidate for the ri-18 operator
+status surface.
+
+### D10 — Tool parity for routed jobs
+
+Some routed jobs call tools that `ubuntu-latest` preinstalls but the runner image does not, for
+example `npm` in `validate-specs`. Each such job either:
+- gains an explicit setup action (`actions/setup-node` pinned to the same major version the
+  repository uses elsewhere), or
+- uses a tool listed in `toolchain.txt`.
+
+A static test scans the `run:` blocks of routed jobs for a fixed list of commands that are
+hosted-only. It matches a command only in **command position**: at the start of a line or after
+`;`, `&&`, `||`, `|`, `$(`, `sudo ` or `env `, followed by whitespace or end of line. A
+substring such as `scripts/check_docker_imports.py` therefore never matches `docker`. The
+commands are:
+- `npm`, `npx`, `node`, `java`, `go`
+- `docker`, `podman`, `sudo`, `apt-get`
+
+For every hit, the job must have the matching setup action, or must be hosted. `docker`,
+`podman`, `sudo` and `apt-get` are always disallowed in routed jobs. The test keeps an
+allowlist mechanism (each entry: workflow, job, command and a comment) for a future justified
+exception; it starts **empty**, because command-position matching already ignores the
+`check_docker_imports.py` script path.
+
+**Known limit.** The scan sees only `run:` text. A command invoked indirectly, from inside a
+script the step calls (as `run_live_matrix.sh` does with podman), is invisible to it. The O6
+self-hosted dry run is the backstop for that class, and any job it catches moves to `hosted`
+through the manifest.
+
+## Operator-only steps (summary; the full runbook is in `docs/guides/self-hosted-ci-runners.md`)
+
+O1–O12 are listed in tasks.md § 7, each with its verification command. None is an
+implementation task, and nothing in the implementation phases performs them.
+
+## Risks
+
+| Risk | Mitigation |
+|---|---|
+| A routed job fails on arm64 | O6 dry run with `verify-run`. Move the job to `amd64-only` through the manifest |
+| Lower concurrency (8 vs ~20 hosted) lengthens the critical path | Measure in O8. Tune the instance count, or move jobs back with `measured-slower` |
+| PAT leak from the host | 0600 file or systemd credential; dedicated user; 90-day expiry; minimum scope; App upgrade path |
+| Host down with lane=self-hosted | D9 manual flip plus the queued-run detection command |
+| New jobs added by concurrent changes | Manifest completeness test fails until they are classified |
+| Podman upgrade changes the rootless network default to `pasta` and exposes host loopback | Explicit `--network slirp4netns:allow_host_loopback=false` in the unit, pinned by a test (D6) |
+| PR code reaches a host service bound to `0.0.0.0` or a LAN/Tailscale address through slirp4netns NAT | Operator nftables rule dropping `ghrunner`-owned traffic to local addresses, or loopback-only binding; O4 probes every host address (D6) |
+| Mint script killed mid-backoff by the start timeout, hammering the API | Explicit `TimeoutStartSec` above the bounded `GX10_MINT_MAX_ELAPSED` budget, pinned by a test (D5, D7) |
+| Cache poisoning by a same-repository PR job (human, Dependabot or agent branch) | Cache off by default; enabling it is a recorded operator risk acceptance (A10); disabled again by emptying `GX10_RUNNER_CACHE_ARGS`, mandated on a move to team mode |
+| A routed job invokes a container engine indirectly through a script | O6 dry run backstop; the static scan only sees `run:` text (D10) |
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/loop-state.json b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/loop-state.json
new file mode 100644
index 00000000..5c45dc82
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/loop-state.json
@@ -0,0 +1,86 @@
+{
+  "schema_version": 6,
+  "change_id": "migrate-ci-to-self-hosted-gx10-runners",
+  "current_phase": "PLAN_REVIEW",
+  "iteration": 0,
+  "total_iterations": 4,
+  "max_phase_iterations": 3,
+  "findings_trend": [],
+  "blocking_findings": [],
+  "vendor_availability": {},
+  "packages_status": {},
+  "package_authors": {},
+  "implementation_strategy": {},
+  "memory_ids": [],
+  "handoff_ids": [
+    "05bf94d2-17bb-4e98-9cf1-dd3e4e6b01c7",
+    "626043b7-a679-4f06-96d8-8550b4acc092",
+    "e5d105c4-b774-438b-8735-66d13766b4da"
+  ],
+  "phase_history": [
+    {
+      "at": "2026-10-11T01:54:17.788250+00:00",
+      "outcome": "proceed_with_review",
+      "phase": "GATEKEEPER"
+    },
+    {
+      "at": "2026-10-11T02:05:21.079895+00:00",
+      "outcome": "created",
+      "phase": "PLAN"
+    },
+    {
+      "at": "2026-10-11T02:10:13.950176+00:00",
+      "outcome": "complete",
+      "phase": "PLAN_ITERATE"
+    }
+  ],
+  "last_handoff_id": "e5d105c4-b774-438b-8735-66d13766b4da",
+  "started_at": "2026-10-11T01:52:33.759559+00:00",
+  "phase_started_at": "2026-10-11T02:10:16.521979+00:00",
+  "previous_phase": null,
+  "escalation_reason": null,
+  "val_review_enabled": true,
+  "cli_review_enabled": true,
+  "error": null,
+  "phase_archetype": "architect",
+  "force": false,
+  "gate_signals": {},
+  "gate_verdict": "proceed_with_review",
+  "gate_decisions": [
+    {
+      "approval_id": null,
+      "authorizing_disposition": "auto",
+      "default_action": null,
+      "disposition": "auto",
+      "gate": "proposal_approval",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "PLAN",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'proposal_approval' auto-approved by trust posture",
+      "recorded_at": "2026-10-11T02:05:25.600576+00:00",
+      "resolution": "auto",
+      "scope": "roadmap_approval",
+      "timeout_seconds": null
+    }
+  ],
+  "pending_gate": null,
+  "goal_gate": null,
+  "park": null,
+  "degradations": [
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "project-state submit returned forbidden",
+      "phase": "INIT"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision auto",
+      "phase": "PLAN"
+    }
+  ]
+}
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/plan-findings.md b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/plan-findings.md
new file mode 100644
index 00000000..d68a028c
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/plan-findings.md
@@ -0,0 +1,33 @@
+# Plan Findings — migrate-ci-to-self-hosted-gx10-runners
+
+## Iteration 1 (autopilot PLAN_ITERATE, archetype architect, non-interactive)
+
+Baseline: `openspec validate --strict` green; work-packages VALID. Facts were checked against the
+live `ci.yml` / `security.yml` (job-level `if:`, run-block commands, setup actions) and the host
+(`podman version 4.9.3`).
+
+| # | Type | Criticality | Description | Fix |
+|---|------|-------------|-------------|-----|
+| 1 | feasibility | high | `mint-jitconfig.sh` backs off up to 300 s inside `ExecStartPre`, but the unit set no `TimeoutStartSec` (default 90 s): systemd kills the script mid-backoff and restarts it every `RestartSec`, so the backoff never applies and the API is hammered. | D5/D7: total budget `GX10_MINT_MAX_ELAPSED` (600 s) < explicit `TimeoutStartSec=900`; new spec scenario "Mint retries are bounded below the start timeout"; tasks 3.1/3.2/3.3/3.4. |
+| 2 | security | high | Host-loopback isolation relied on the podman default. Podman 5 defaults to `pasta`, which maps the gateway to host loopback, exposing the coordinator API / Postgres to PR code after a routine upgrade. | D6: explicit `--network slirp4netns:allow_host_loopback=false` and `--pull=never`, pinned by test; A11; O4 verification made concrete (`podman exec`, `podman inspect`). |
+| 3 | correctness/testability | high | `verify_run` flagged every non-`success` job, but `dependency-update-remediation` has a job-level `if:` (Dependabot PRs only) and is `skipped` with no runner on every dispatch/push/PR run, so O6/O7/O11/O12 would always fail. | D8 + spec: `skipped` accepted (placement unchecked) for jobs with a job-level `if:`; unconditional skips remain violations; two new scenarios; task 4.1. |
+| 4 | security/assumptions | high | D6 claimed `uv sync --locked` hash checks mitigate shared-cache poisoning. They do not: hashes are checked at download only, and many jobs run `uv sync` without `--locked`, `uv run --with`, `uv pip install`. | D6 rationale corrected; risk accepted explicitly as A10 (solo mode, same-repo writers already trusted); team-mode transition requires `GX10_RUNNER_UV_CACHE=off`; runbook task 5.2. |
+| 5 | consistency | medium | Ephemerality scenario listed names via the runners API, but JIT runners deregister after their job, so names are gone. | Spec + O9 use the jobs API `runner_name`. |
+| 6 | consistency | medium | `expected_lane` / `--expect-lane` (D8, O12) absent from the spec requirement and tasks 4.1/4.3. | Added to spec signature, a rollback scenario, and tasks. |
+| 7 | completeness | medium | `compare` had no run selection, so A6's "paired runs on the same commit" was not reproducible; `--paginate` unbounded. | D8/spec/task 4.3: `--workflow`, `--head-sha`, `--event`, `--since`, `--until`, `--limit` (200); O8 command updated. |
+| 8 | consistency | medium | Tool-parity requirement had no allowlist clause while its scenario did; the `check-docker-imports` allowlist rationale was wrong (only `check_docker_imports.py` appears). | D10: command-position matching, allowlist mechanism retained but empty; spec requirement + new scenario; documented limit (indirect script invocations) backstopped by O6. |
+| 9 | clarity | medium | `StartLimitIntervalSec=0` "in [Service] or [Unit]" — systemd only honours it in `[Unit]`. | D7/spec/task 3.1 pin it to `[Unit]`. |
+| 10 | parallelizability | medium | Tasks 2.5–2.8 all edit `ci.yml`/`security.yml` with no ordering between them. | Explicit serial chain 2.5 → 2.6 → 2.7 → 2.8 inside `wp-workflows`. |
+| 11 | clarity | low | Routed-lane requirement omitted the fork exclusion in its main sentence. | Clause added. |
+
+## Iteration 2 (re-review)
+
+No findings at or above `medium`. Remaining low items, left for operator tuning:
+- A9 default 8 × (2 CPU / 8 GiB) = 64 GiB on a host whose unified memory is shared with GPU
+  workloads and the ri-08 daemon; tuned at O8.
+- `secret-scan` (gitleaks-action binary) and `formal-coordination` (Java) arm64 parity remains
+  an O6 dry-run outcome, by design (D2).
+
+Termination: threshold met after iteration 1 fixes. Multi-vendor review not run here (no
+`--vendor-review` flag; coordinator projection forbidden) — the autopilot PLAN_REVIEW phase
+owns it.
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/proposal.md b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/proposal.md
new file mode 100644
index 00000000..cfb439a1
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/proposal.md
@@ -0,0 +1,236 @@
+# Migrate CI to self-hosted GX10 runners
+
+> Parent roadmap: `roadmap-always-on-agent-automation` · Roadmap item `ri-20`
+> Change ID: `migrate-ci-to-self-hosted-gx10-runners`
+> Effort: M · Priority: 2 · Depends on: none
+> Planned by: autopilot PLAN phase (non-interactive, archetype `architect`). There was no human
+> in the loop, so every discovery answer below is an **explicit assumption** (§ Assumptions),
+> and Gate 2 is replaced by the supervisor-owned `proposal_approval` gate.
+
+## Why
+
+CI wall-clock time sets how often merge sync windows can run. Every job in `ci.yml` (25 jobs)
+and `security.yml` (3 jobs) runs on `ubuntu-latest`. Each run starts from a cold VM: it
+installs Python through `uv`, resolves the whole lockfile again, and pays for queueing on the
+hosted runners. The always-on GX10 host is a linux/aarch64 machine of the NVIDIA DGX Spark
+class. It already holds the vendor CLIs, a warm `uv` cache and podman, and it is idle for most
+of the day. Moving the jobs that are compatible to ephemeral, containerized self-hosted runners
+on that host should shorten the CI critical path and stop CI from depending on hosted-runner
+queueing.
+
+A self-hosted runner that executes pull-request code is a code-execution surface on that host.
+For that reason the roadmap treats fork-PR safety and aarch64 parity as first-class
+requirements, not as hardening to add later.
+
+## What Changes
+
+1. **Lane manifest (new, `.github/runner-lanes.yaml`).** This file records how every job in
+   `ci.yml` and `security.yml` is routed, in a form a machine can read. Each job is either
+   `routed`, meaning it follows the lane selector, or `hosted`, meaning it is pinned to
+   `ubuntu-latest`. A hosted job carries a `reason_code` from a closed set and a written reason.
+   The file also holds the self-hosted label set, the repository variable name and the
+   dispatch input name. A JSON Schema (`.github/runner-lanes.schema.json`) validates it.
+2. **Workflow routing (`ci.yml` and `security.yml`, on this branch only).**
+   - Every `routed` job gets the same canonical `runs-on` expression. It selects the GX10
+     label set only when both of these hold:
+     - The event is a `push`, a `workflow_dispatch`, or a same-repository pull request. Fork
+       pull requests and `merge_group` runs (whose merge commit can contain approved fork code)
+       always run hosted.
+     - The lane resolves to `self-hosted`. The lane comes from the `runner_lane`
+       `workflow_dispatch` input, or else from the `CI_RUNNER_LANE` repository variable.
+   - In every other case, including when the variable is unset (the default), the expression
+     evaluates to `ubuntu-latest`. Merging this change therefore changes no CI behaviour until
+     an operator sets the variable.
+   - Every routed job's first step is an in-job guard. It fails the job if a fork pull request
+     or a `merge_group` run ever reaches a self-hosted runner.
+   - Hosted-pinned jobs keep a literal `runs-on: ubuntu-latest`. Each has a justification in
+     the manifest. The pinned jobs are the container-engine jobs (`test-integration`,
+     `gen-eval`, `test-openbao-live`), `docker-smoke-import` (production image architecture is
+     amd64, and it needs a container engine), and the write-token job
+     `dependency-update-remediation`.
+   - Both workflows gain a `workflow_dispatch` trigger with a `runner_lane` choice input
+     (`auto` | `hosted` | `self-hosted`). It is used for A/B measurement and for dry runs.
+   - Routed jobs that rely on tools preinstalled on `ubuntu-latest` (for example `npm` in
+     `validate-specs`) get an explicit setup step, or rely on the runner image baseline.
+3. **Runner host kit (new, `deploy/gx10-runner/`).** This is written and tested, but it is
+   never installed by this change. It contains:
+   - A pinned arm64 `Containerfile` built on the official `actions-runner` image.
+   - A host-side `mint-jitconfig.sh`. It mints a single-use just-in-time runner configuration
+     with a host-held credential, so the credential never enters the container.
+   - A `cleanup-runner.sh` that removes a runner registration that was never used.
+   - A systemd **user** template unit, `gx10-runner@.service`. It runs one `podman run --rm`
+     container per instance with `Restart=always`, so each job gets a fresh container. The
+     unit is meant to run as a dedicated lingering host user, so the runners start again after
+     a reboot.
+   - An example environment file.
+4. **Measurement and verification tooling (new, `scripts/ci/ci_wallclock.py`).** These are
+   pure functions over `gh api` JSON, with a thin CLI:
+   - `median` computes the median wall-clock time of successful runs per lane and time window.
+   - `compare` applies the acceptance threshold.
+   - `verify-run` checks one workflow run against the manifest: each routed job ran on the
+     expected lane, each hosted job ran on a GitHub-hosted runner, and every job succeeded or
+     was skipped by its own job-level `if:` (failed `continue-on-error` jobs are warnings;
+     design D8).
+5. **Operator runbook (new, `docs/guides/self-hosted-ci-runners.md`).** It covers each
+   operator-only step with a concrete verification command: host user and linger, credential,
+   image build, enabling the units, the fork-approval repository setting, the A/B dry run,
+   flipping the variable, measuring wall-clock time, checking ephemerality, checking reboot
+   survival, the fork-PR test and rollback.
+6. **Tests (new, `skills/tests/ci_runners/`).** Static tests over the workflow YAML, the
+   manifest, the systemd unit, the container and host scripts, and the measurement functions.
+
+### Hard boundary (applies to every task and package)
+
+The implementation **may** write workflow YAML on this branch, systemd unit files, container
+and runner scripts, docs and tests. It **must not**:
+- Register runners or mint registration or JIT tokens.
+- Change repository or organization settings or variables.
+- Install, enable or start systemd units or containers on any host.
+- Push to, or edit workflows on, `main`.
+
+Every outcome that needs one of those actions is an **operator-only step** (tasks.md § 7). It
+is not an implementation task.
+
+## Approaches Considered
+
+### Approach A — Lane manifest, inline canonical `runs-on` expression, host-minted JIT runners under systemd user units (**Recommended**)
+
+**Description:** A checked-in manifest classifies every job. Routed jobs carry one canonical
+`runs-on` expression that defaults to hosted and excludes forks. That expression appears
+verbatim in each job, and a test enforces it. The runners are rootless podman containers, one
+job per container. A systemd template unit restarts them. The unit's `ExecStartPre` mints a
+single-use JIT config on the host.
+
+- **Pros:**
+  - The default is safe: when the variable is unset the result is `ubuntu-latest`, so merging
+    is a no-op.
+  - It adds no serial routing job, so the critical path does not grow.
+  - The manifest is an auditable, machine-readable record of why each job is pinned.
+  - The routing credential never enters the container that runs PR code.
+  - JIT configs are inherently one job per registration.
+  - Per-job tuning after measurement is a one-line manifest change.
+- **Cons:**
+  - The routing expression is long and repeated about 23 times. A test pins it, but humans
+    will find it noisy.
+  - Falling back to hosted when the host is down is manual: the operator flips the variable.
+  - Container-engine jobs stay hosted in v1.
+- **Effort:** M
+
+### Approach B — Routing job (`route`) that computes `runs-on` once, consumed via `needs.route.outputs`
+
+**Description:** A small job on `ubuntu-latest` evaluates lane, fork status and runner
+availability (through a token that can list runners), then emits a JSON label array. Every
+other job `needs: route` and uses `runs-on: ${{ fromJSON(needs.route.outputs.runs_on) }}`.
+
+- **Pros:**
+  - The expression lives in one place.
+  - With a token that can list runners, the job could fall back to hosted automatically when
+    no GX10 runner is online.
+- **Cons:**
+  - It adds a serial hosted job of about 15 to 30 s, including queueing, in front of every
+    job. That works directly against outcome 2.
+  - Every job gains a `needs:` edge, which touches the existing dependency structure and the
+    tests that parse it.
+  - An automatic availability probe needs a token with administration read scope inside a
+    workflow that runs PR code.
+- **Effort:** M
+
+### Approach C — actions-runner-controller (ARC) on a single-node k3s cluster on the GX10
+
+**Description:** Run GitHub's Kubernetes runner scale sets on the host, which provide
+autoscaled ephemeral pods and container-mode jobs.
+
+- **Pros:**
+  - It is the upstream-supported autoscaling and ephemeral model.
+  - Container mode could also serve `services:` jobs.
+- **Cons:**
+  - It brings in Kubernetes as a new operational dependency on a box that runs podman and
+    systemd today.
+  - It has far more moving parts to secure and keep running.
+  - Its scale-set listener needs a GitHub App installed with broader scope.
+  - Its value only shows at concurrency levels a single host does not need.
+- **Effort:** L
+
+### Selected Approach
+
+**Approach A.** The autopilot PLAN phase chose it at Gate 1 with no human present. It
+preserves outcome 2, because it adds no serial routing hop. It keeps merge risk at zero,
+because hosted is the default. It satisfies the "auditable over minimal diff" preference
+through the manifest. It keeps the trust boundary narrow, because the credential stays on the
+host and the container has no engine socket.
+
+Approach B's single source of truth comes back cheaply through the test-enforced canonical
+expression. Its automatic fallback is deferred as a follow-up (see design.md D9). Approach C is
+recorded as the path to take if engine-backed jobs or multi-host scaling are later required.
+
+## Assumptions (discovery answered by the planner, not by a human)
+
+- **A1. Repository visibility is treated as public (worst case).** Fork PRs must never route to
+  self-hosted, even after approval. Approval only lets a fork run start; it then runs on
+  `ubuntu-latest`.
+- **A2. Runners are registered at repository scope**, not organization scope. They use the
+  default runner group, so no other repository can schedule jobs on them.
+- **A3. The registration credential is a fine-grained PAT** scoped to this one repository with
+  *Administration: read and write* only. It is held on the host as a 0600 file or a systemd
+  credential. A GitHub App is the documented upgrade path (design.md D5).
+- **A4. The runners run under a dedicated unprivileged host user** (`ghrunner`), never the
+  operator's own account, which holds vendor CLI credentials, SSH keys and the coordinator
+  stack.
+- **A5. Container-engine jobs stay hosted in v1.** These are `services:` containers, Docker
+  builds and the podman-driven OpenBao matrix. No container engine socket is exposed inside a
+  container that runs PR code.
+- **A6. "Measurably drops" means** the median wall-clock time of successful CI runs on the
+  self-hosted lane is at most 0.85 × the hosted median. That is a reduction of at least 15 %,
+  over at least 5 paired `workflow_dispatch` runs per lane on the same commit, with at least
+  20 PR runs per lane in the before/after window as a corroborating measure.
+- **A7. The hosted fallback is operator-switched**, by setting `CI_RUNNER_LANE` to `hosted` or
+  deleting it. An unset variable means hosted. Automatic fallback is deferred (D9).
+- **A8. aarch64 Python compatibility is not a blocker.** The planning host is itself aarch64,
+  and both `uv` venvs resolve and run here. Any routed job that fails on arm64 during the
+  operator dry run is moved to `hosted` with `reason_code: amd64-only` through a manifest
+  change. That decision is recorded, not hidden.
+- **A9. Initial runner concurrency is 8 instances**, configurable. The operator tunes it
+  against the wall-clock measurement. The ri-08 dispatcher daemon shares the host, so per-
+  container CPU and memory limits are mandatory.
+- **A10. The shared uv cache volume is off by default and enabled only by explicit operator
+  risk acceptance.** Same-repository branches are written not only by the owner but also by
+  automation (Dependabot, agent PR sources such as Jules and Codex) and potentially by a leaked
+  collaborator credential, and lockfile hashes do not protect cached entries on reuse (design
+  D6). A shared writable cache would let such a branch influence a later `main` job. The kit
+  therefore ships with no cache volume; the operator may enable it (`GX10_RUNNER_CACHE_ARGS`)
+  only after recording, in the runbook, an acceptance that names the date and confirms every
+  same-repository writer is acceptable. A move to team mode requires disabling it.
+- **A11. Rootless container networking is pinned, not inherited.** The unit passes
+  `--network slirp4netns:allow_host_loopback=false` explicitly, so a podman 5 upgrade (whose
+  default `pasta` maps the gateway to host loopback) cannot silently expose the coordinator
+  API or Postgres to PR code (design D6). The pin covers host *loopback* only: a service bound
+  to `0.0.0.0` or to a LAN/Tailscale address stays reachable through slirp4netns NAT. Host
+  services are therefore isolated by an operator-installed nftables rule that drops
+  `ghrunner`-owned traffic to local addresses (or, as a fallback, by binding them to
+  `127.0.0.1` only), and O4 verifies it by probing every host address from a runner container.
+
+## Impact
+
+- **New capability:** `ci-runner-infrastructure`.
+- **Files written:**
+  - `.github/runner-lanes.yaml`
+  - `.github/runner-lanes.schema.json`
+  - `.github/workflows/ci.yml` and `.github/workflows/security.yml` (routing only)
+  - `deploy/gx10-runner/**`
+  - `scripts/ci/ci_wallclock.py`
+  - `docs/guides/self-hosted-ci-runners.md`
+  - `skills/tests/ci_runners/**`
+  - `skills/pyproject.toml` (registers the test path)
+- **Interactions:**
+  - Several active changes add jobs to `ci.yml`, including
+    `gate-drift-with-mirrors-hooks-and-blocking-ci`, `assert-generated-artifacts-validate-in-ci`
+    and `enforce-fork-policies-in-ci-worktrees-and-sync-points`.
+  - The manifest completeness test fails for any job that is not classified. Whichever change
+    merges second must add its jobs to the manifest. That is the intended forcing function.
+  - The tests that already parse `ci.yml` (`skills/tests/ci_coverage/`,
+    `skills/tests/project-context-refresh/`) must stay green. Only `runs-on`, a guard step,
+    `workflow_dispatch` and setup steps change.
+- **Not changed:**
+  - Branch-protection required-check names, because job ids are unchanged.
+  - `concurrency` semantics.
+  - Job `permissions`.
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/session-log.md b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/session-log.md
new file mode 100644
index 00000000..9be94844
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/session-log.md
@@ -0,0 +1,102 @@
+# Session Log: migrate-ci-to-self-hosted-gx10-runners
+
+> Decision rationale, trade-offs, and alternatives recorded at each workflow phase.
+> Auto-generated by workflow skills. Sanitized before commit.
+
+## Phase: GATEKEEPER (2026-10-11)
+
+**Agent**: autopilot-gatekeeper | **Session**: N/A
+
+### Decisions
+1. **Outcome proceed_with_review** — Verifiable via static tests (actionlint/YAML assertions on runs-on labels, hosted-lane pinning, fork guards, ephemeral --ephemeral flag + Restart= in units); risk is branch-scoped and reversible, no host/settings mutation.
+2. **Enable VAL_REVIEW for security signal** — Self-hosted runner + pull_request trigger is a code-execution-on-host surface; fork-PR protection partly depends on repo settings outside autopilot scope, so an extra review should confirm workflow-level guards and operator runbook.
+3. **Live-only outcomes become operator steps** — Outcomes 1 (green on real arm64 runner), 2 (median wall-clock drop), and the settings half of 3 and host half of 4 cannot be verified pre-merge; PLAN must encode them as pending_gate operator steps with a measurement method, not claimed as done.
+
+### Next Steps
+- PLAN: WHEN/THEN specs per outcome; tests statically asserting labels/fallback lane/fork guard/unit config; explicit operator checklist (register runner, fork-approval setting, enable units, baseline CI timing)
+
+### Context
+Verdict: proceed_with_review. ri-20 has four concrete, checkable acceptance outcomes; all autonomous writes are branch-only (workflow YAML, systemd units, scripts, docs, tests) and reversible behind the mandatory human merge gate. Security-sensitive surface (self-hosted runners exposed to PR code, fork-approval) warrants the extra VAL_REVIEW phase.
+
+---
+
+## Phase: PLAN (2026-10-11)
+
+**Agent**: autopilot-plan | **Session**: N/A
+
+### Decisions
+1. **Lane manifest as routing source of truth** `architectural: ci-runner-infrastructure` — Every job is routed or hosted, and each hosted pin carries a closed reason_code plus a written reason. Tests compare the workflows with the manifest, so an unclassified job fails CI.
+2. **Inline canonical runs-on expression defaulting to hosted** `architectural: ci-runner-infrastructure` — With the variable unset the result is ubuntu-latest, so merging is a no-op. There is no serial routing job, which preserves the wall-clock outcome. A dispatch input runner_lane allows A/B measurement.
+3. **Fork PRs never route to self-hosted, even after approval** `architectural: ci-runner-infrastructure` — The fork check sits in the routing expression, the first step of every routed job is a runner.environment guard, and a trigger allowlist bans pull_request_target, workflow_run and issue_comment. The approval policy is set by the operator in step O5.
+4. **Host-minted single-use JIT config; credential never in container** `architectural: ci-runner-infrastructure` — ExecStartPre mints generate-jitconfig with a 0600 fine-grained PAT owned by a dedicated lingering ghrunner user. The container receives only the consumed JIT config and has no engine socket, no host network and no privileges.
+5. **Container-engine and write-token jobs stay hosted in v1** `architectural: ci-runner-infrastructure` — test-integration, gen-eval, test-openbao-live and docker-smoke-import need a container engine, and docker-smoke-import also validates an amd64 production image. dependency-update-remediation holds contents:write.
+6. **Measurable threshold for 'median drops'** `architectural: ci-runner-infrastructure` — The candidate median must be at most 0.85x the baseline, with n>=5 paired dispatch runs per lane, corroborated by at least 20 PR runs before and after. This is implemented as pure functions in scripts/ci/ci_wallclock.py.
+
+### Alternatives Considered
+- Routing job computing runs-on once (needs.route.outputs): rejected because It adds a serial hosted hop in front of every job, against outcome 2, and an automatic availability probe would need an admin-scoped token in a workflow that runs PR code.
+- actions-runner-controller on k3s: rejected because It adds Kubernetes as an operational dependency on a podman/systemd host, which is too much for a single box.
+- Registration token with config.sh --ephemeral inside the container: rejected because The reusable credential or registration token would sit inside the container that runs PR code.
+- YAML anchors for the runs-on expression: rejected because Parser and tool support across the repository's workflow tests and actionlint is not uniform.
+
+### Trade-offs
+- Accepted Manual hosted fallback by flipping CI_RUNNER_LANE over Automatic fallback because Automatic fallback needs a runner-listing token or a host watchdog that mutates repository variables, which is outside the boundary. It is deferred to follow-up work on the ri-18 status surface.
+- Accepted Shared uv cache volume across ephemeral jobs over Cold caches per job because This is the main source of speedup. Forks never route here, locked hash verification applies, and the operator can disable it with GX10_RUNNER_UV_CACHE=off.
+- Accepted Long routing expression repeated across 23 jobs over Single-source routing job because It costs no latency, and a test pins it.
+
+### Open Questions
+- [ ] Does gitleaks-action resolve a linux/arm64 binary? This is settled by the O6 dry run; if not, move the job to amd64-only.
+- [ ] Is 8 runner instances enough to beat about 20 parallel hosted jobs on critical path? Tune in O8.
+- [ ] Should the GitHub App replace the fine-grained PAT before the PAT's 90-day expiry?
+
+### Next Steps
+- IMPLEMENT: start with wp-contracts (schema promotion and manifest), then run wp-workflows, wp-runner-kit, wp-tooling and wp-docs in parallel.
+- Keep the hard boundary: no runner registration, token minting, repository-setting changes or host unit/container install.
+
+### Relevant Files
+- `openspec/changes/migrate-ci-to-self-hosted-gx10-runners/proposal.md` — approaches, selected approach A, assumptions A1-A9
+- `openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md` — decisions D1-D10
+- `openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md` — WHEN/THEN requirements
+- `openspec/changes/migrate-ci-to-self-hosted-gx10-runners/tasks.md` — implementation phases 1-6 and operator-only O1-O12
+- `openspec/changes/migrate-ci-to-self-hosted-gx10-runners/work-packages.yaml` — 6-package DAG
+
+### Context
+Planned ri-20 non-interactively (coordinated tier, Gate 2 skipped for supervisor proposal_approval). Selected Approach A: a lane manifest classifying all 28 ci.yml/security.yml jobs, an inline test-pinned runs-on expression that defaults to ubuntu-latest and never routes fork PRs, and host-minted JIT runners in hardened rootless podman containers under a systemd user template unit. Live outcomes (green on arm64, wall-clock drop, approval setting, reboot survival) are operator-only steps O1-O12 with verification commands.
+
+---
+
+## Phase: PLAN_ITERATE (2026-10-11)
+
+**Agent**: claude-code | **Session**: N/A
+
+### Decisions
+1. **Pin rootless network explicitly** — Podman 5 defaults to pasta, which maps the gateway to host loopback; isolation must not depend on a package default (A11, D6).
+2. **verify_run accepts skipped jobs with a job-level if** — dependency-update-remediation is skipped on every non-Dependabot run; otherwise every operator verify-run would falsely fail.
+3. **Accept shared uv cache in solo mode as explicit assumption A10** — Lockfile hashes do not protect cached entries; same-repo writers already hold write access; off switch mandated on move to team mode.
+4. **Skip multi-vendor review in this phase** `architectural: skill-procedure-deviation` — No --vendor-review flag and coordinator projection forbidden; autopilot PLAN_REVIEW owns vendor review.
+5. **Record assumptions instead of AskUserQuestion** `architectural: skill-procedure-deviation` — Non-interactive supervised run; assumptions A10/A11 written into proposal.md.
+6. **Run analysis inline rather than five Explore sub-agents** `architectural: skill-procedure-deviation` — Single spec delta and four documents; direct verification against live workflow YAML was more reliable than fan-out.
+
+### Alternatives Considered
+- Per-trust-tier uv cache volumes: rejected because Runner container does not know the job event at start; cannot pick a volume per event.
+
+### Trade-offs
+- Accepted Shared uv cache speed over Strict per-job cache isolation because Solo-mode repository; documented off switch.
+
+### Open Questions
+- [ ] Are gitleaks-action and setup-java arm64-clean? Resolved only by the O6 dry run.
+
+### Completed Work
+- F1 mint retry budget vs TimeoutStartSec
+- F2 explicit slirp4netns + --pull=never
+- F3 verify_run skipped semantics
+- F4 uv cache rationale + A10
+- F5 ephemerality via jobs API
+- F6 expected_lane in spec/tasks
+- F7 compare run selection flags
+- F8 command-position tool-parity matching
+- F9 StartLimitIntervalSec in [Unit]
+- F10 serial chain 2.5-2.8
+
+### Context
+Iterate-on-plan converged in one fix iteration plus a clean re-review: 4 high and 6 medium findings fixed across design, spec delta, tasks, proposal and work-packages. Key fixes: bounded mint retries below an explicit TimeoutStartSec, explicit slirp4netns network pin against the podman-5 pasta default, verify_run accepting conditionally skipped jobs, and a corrected uv-cache poisoning rationale (A10).
+
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md
new file mode 100644
index 00000000..d8bac625
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md
@@ -0,0 +1,262 @@
+## ADDED Requirements
+
+### Requirement: Lane Manifest Classifies Every Workflow Job
+
+The repository SHALL maintain a lane manifest at `.github/runner-lanes.yaml`, valid against `.github/runner-lanes.schema.json`. The manifest SHALL classify every job in `.github/workflows/ci.yml` and `.github/workflows/security.yml` as either `routed` or `hosted`. Every `hosted` job MUST carry a `reason_code` from the closed set `container-engine`, `amd64-only`, `privileged-token` and `measured-slower`, together with a non-empty written `reason`.
+
+#### Scenario: Unclassified job fails the suite
+- **WHEN** a job id exists in `ci.yml` or `security.yml` but not in the manifest
+- **THEN** the lane manifest test fails and names the unclassified workflow and job id
+
+#### Scenario: Stale manifest entry fails the suite
+- **WHEN** the manifest names a job id that no longer exists in its workflow
+- **THEN** the lane manifest test fails and names the stale entry
+
+#### Scenario: Hosted job without justification is rejected
+- **WHEN** a manifest entry has `lane: hosted` and lacks `reason_code` or has an empty `reason`
+- **THEN** schema validation of the manifest fails
+
+### Requirement: Routed Jobs Default To The Hosted Lane
+
+Every `routed` job SHALL use the single canonical `runs-on` expression defined in design D3. Under that expression a job SHALL resolve to `ubuntu-latest` unless the event is eligible — a `push`, a `workflow_dispatch`, or a same-repository `pull_request` (never a fork `pull_request`, never `merge_group`, never any other event) — and one of the following holds:
+- a `workflow_dispatch` `runner_lane` input of `self-hosted` is supplied;
+- the `CI_RUNNER_LANE` repository variable equals `self-hosted`, and no dispatch override of `hosted` is supplied.
+
+The self-hosted label set inside the expression MUST equal the manifest's `routing.self_hosted_labels`.
+
+Both `ci.yml` and `security.yml` SHALL declare a `workflow_dispatch` trigger with a `runner_lane` choice input whose options are exactly `auto`, `hosted` and `self-hosted`, with default `auto`.
+
+#### Scenario: Unset variable keeps CI on hosted runners
+- **WHEN** the reference evaluator resolves the canonical expression for a same-repository `pull_request`, `push` or `merge_group` event with `CI_RUNNER_LANE` unset
+- **THEN** the result is `ubuntu-latest`
+
+#### Scenario: Variable opts same-repository events into the self-hosted lane
+- **WHEN** the reference evaluator resolves the expression for a same-repository `pull_request` with `CI_RUNNER_LANE` set to `self-hosted`
+- **THEN** the result is the manifest's self-hosted label set
+
+#### Scenario: Dispatch input overrides the variable in both directions
+- **WHEN** the expression is resolved for a `workflow_dispatch` event with `runner_lane` set to `hosted` while `CI_RUNNER_LANE` is `self-hosted`
+- **THEN** the result is `ubuntu-latest`
+- **AND** with `runner_lane` set to `self-hosted` while the variable is unset, the result is the self-hosted label set
+
+#### Scenario: Expression is tied to every manifest routing field
+- **WHEN** the routing test changes the manifest's `routing.self_hosted_labels`, `routing.repository_variable` or `routing.dispatch_input` without changing the workflows
+- **THEN** the test fails, because the expression's `fromJSON` labels, its `vars.<name>` reference and its `inputs.<name>` reference must equal those three fields
+
+#### Scenario: Merge queue runs stay hosted
+- **WHEN** the reference evaluator resolves the expression for a `merge_group` event with `CI_RUNNER_LANE` set to `self-hosted`
+- **THEN** the result is `ubuntu-latest`, because a merge-group commit can contain an approved fork pull request's code
+
+#### Scenario: Dispatch trigger and lane input are declared
+- **WHEN** the fork guard test reads `ci.yml` and `security.yml`
+- **THEN** each declares `workflow_dispatch` with a `runner_lane` choice input of options `auto`, `hosted`, `self-hosted` and default `auto`
+
+#### Scenario: Routed job drifts from the canonical expression
+- **WHEN** any `routed` job's `runs-on` differs from the canonical expression after whitespace normalization
+- **THEN** the workflow routing test fails and names the job
+
+### Requirement: Hosted-Pinned Jobs Are Explicit
+
+Every `hosted` job SHALL declare a literal `runs-on: ubuntu-latest` and MUST NOT use the routing expression. A `routed` job MUST NOT declare `services:`, and its `run:` blocks MUST NOT invoke `docker`, `podman`, `sudo` or `apt-get` in command position, except for an entry in the tool-parity allowlist that names the workflow, job and command with a justifying comment (the allowlist starts empty). A `routed` job that invokes `npm`, `npx`, `node`, `java` or `go` in command position MUST include the matching setup action. A command name that appears only inside a path or identifier, such as `scripts/check_docker_imports.py`, is not an invocation. The scan covers `run:` text only; a command invoked indirectly from inside a script that a step calls is outside its reach and is caught by the operator's self-hosted dry run (O6), which moves such a job to `hosted` through the manifest.
+
+#### Scenario: Container-engine job marked routed is rejected
+- **WHEN** a job that declares `services:` or runs `docker`, `podman`, `sudo` or `apt-get` is classified `routed`
+- **THEN** the tool-parity test fails, unless the job and command appear in the documented allowlist with a comment
+
+#### Scenario: Hosted job uses a literal hosted label
+- **WHEN** the routing test reads a manifest job with `lane: hosted`
+- **THEN** that job's `runs-on` equals the string `ubuntu-latest`
+
+#### Scenario: Command name inside a script path is not an invocation
+- **WHEN** a routed job's `run:` block contains `uv run python scripts/check_docker_imports.py` and no other container command
+- **THEN** the tool-parity test passes for that job without an allowlist entry
+
+#### Scenario: Routed job calls npm without setup-node
+- **WHEN** a routed job's `run:` block invokes `npm` and the job has no `actions/setup-node` step
+- **THEN** the tool-parity test fails and names the job and command
+
+### Requirement: Fork Pull Requests Never Execute On Self-Hosted Runners
+
+A `pull_request` event whose head repository differs from the base repository, and every `merge_group` event (whose merge commit can contain approved fork code), SHALL resolve to `ubuntu-latest` regardless of the variable value. Every `routed` job's first step SHALL be a guard that fails the job when it is running on a self-hosted runner for any event outside the D3 eligibility allowlist, which includes every fork pull request and every `merge_group` run. Neither workflow SHALL declare the triggers `pull_request_target`, `workflow_run` or `issue_comment`. The repository's fork-PR contributor approval policy MUST be set to require approval for all external contributors; this is an operator-only step with a verification command.
+
+#### Scenario: Fork pull request routes to hosted even with the self-hosted lane enabled
+- **WHEN** the reference evaluator resolves the expression for a fork `pull_request` with `CI_RUNNER_LANE` set to `self-hosted`
+- **THEN** the result is `ubuntu-latest`
+
+#### Scenario: Routed job lacks the in-job fork guard
+- **WHEN** a routed job's first step is not the canonical guard, with condition `runner.environment == 'self-hosted'` combined with the negation of the D3 event-eligibility clause
+- **THEN** the fork guard test fails and names the job
+
+#### Scenario: Privileged trigger is introduced
+- **WHEN** `ci.yml` or `security.yml` declares `pull_request_target`, `workflow_run` or `issue_comment`
+- **THEN** the trigger allowlist test fails
+
+#### Scenario: Operator verifies the approval policy
+- **WHEN** the operator runs `gh api repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval --jq .approval_policy`
+- **THEN** the output is `all_external_contributors`
+
+### Requirement: Runners Are Ephemeral Per Job
+
+The runner kit under `deploy/gx10-runner/` SHALL meet all of the following:
+- It SHALL register each runner with a single-use just-in-time configuration minted on the host before the container starts.
+- It SHALL run the runner in a container started with `--rm`, so that one container serves exactly one job, and with `--replace`, so that a container left over from an unclean stop cannot wedge the restart loop.
+- It SHALL delete the instance's own registration on stop (`ExecStopPost` runs `cleanup-runner.sh`) and, before minting, SHALL delete only the instance's own stale offline registrations, identified by the runner-name prefix `gx10-<hostname>-<instance>-`.
+- It SHALL load its operator configuration through `EnvironmentFile=` and deliver the registration credential through `LoadCredential=`.
+- It SHALL NOT pass the registration credential, a container engine socket, host networking or privileged mode into the container.
+- It SHALL pin the container network explicitly to `slirp4netns:allow_host_loopback=false`, so that host loopback services stay unreachable regardless of the host's podman default.
+- It SHALL start only the locally built image (`--pull=never`).
+- It SHALL bound the mint script's total retry time below the unit's start timeout.
+- It SHALL pin its base image by version and digest.
+- It SHALL mount no shared cache volume by default; a shared uv cache volume is mounted only when the operator sets `GX10_RUNNER_CACHE_ARGS` to the documented named-volume value after recording a risk acceptance.
+- Its runbook SHALL require an operator-installed control that keeps host services unreachable from runner containers on every host address, not only through the loopback mapping.
+
+#### Scenario: Unit runs a removable container with a single-use config
+- **WHEN** the unit test parses `gx10-runner@.service`
+- **THEN** `ExecStartPre` invokes `mint-jitconfig.sh`
+- **AND** `ExecStart` invokes `podman run` with `--rm`, `--pull=never`, `--env-file`, `--cap-drop ALL`, `--security-opt no-new-privileges` and `--network slirp4netns:allow_host_loopback=false`
+
+#### Scenario: Dangerous container options are absent
+- **WHEN** the unit test scans `ExecStart`
+- **THEN** none of `--privileged`, `--network host`, `--network=host`, a `--network` value other than `slirp4netns:allow_host_loopback=false`, or a volume whose source ends in `.sock` is present
+
+#### Scenario: Credential stays on the host
+- **WHEN** the runner-kit tests inspect `mint-jitconfig.sh` and the container env-file contract
+- **THEN** the env file written for the container contains only the JIT config and the runner id
+- **AND** the mint script refuses a credential file whose mode is wider than `0600`
+
+#### Scenario: Mint retries are bounded below the start timeout
+- **WHEN** the stubbed GitHub API returns HTTP 503 on every call and the test sets a short retry budget
+- **THEN** `mint-jitconfig.sh` retries with growing delays, exits non-zero once the budget is spent, and writes no env file
+- **AND** the unit's `TimeoutStartSec` is greater than the default `GX10_MINT_MAX_ELAPSED` in the example env file
+
+#### Scenario: Unit wiring delivers configuration and credential
+- **WHEN** the unit test parses `gx10-runner@.service` and `gx10-runner.env.example`
+- **THEN** `[Service]` declares `EnvironmentFile=` for the operator env file and `LoadCredential=github-token:<path>`
+- **AND** every variable referenced by `ExecStartPre` or `ExecStart` is defined in the example env file
+
+#### Scenario: Stale registrations of the instance are swept before minting
+- **WHEN** the stubbed runners API lists an offline runner `gx10-<host>-1-<epoch>`, an online runner with the same prefix, and an offline runner `gx10-<host>-2-<epoch>`, and `mint-jitconfig.sh 1` runs
+- **THEN** it deletes only the offline instance-1 runner before requesting a new JIT config
+
+#### Scenario: Shared cache is off unless the operator opts in
+- **WHEN** the unit test expands `ExecStart` with the example env file's `GX10_RUNNER_CACHE_ARGS` (empty)
+- **THEN** no `--volume` argument is present
+- **AND** with the documented opt-in value the only added arguments are `--volume gx10-runner-uv-cache:/home/runner/.cache/uv`
+
+#### Scenario: Operator verifies host services are unreachable on every host address
+- **WHEN** the operator attempts a TCP connect (not an HTTP request) to `:54322` and the coordinator API port from inside a runner container at `10.0.2.2` and at every address printed by `hostname -I`
+- **THEN** every connect is refused or times out
+- **AND** either the nftables rules (a DNS exemption for the host stub resolver followed by a drop of `ghrunner`-owned traffic to local addresses) are listed, or `ss -ltnp` shows those ports bound to `127.0.0.1` only
+- **AND** `ghrunner` can still resolve `api.github.com`
+
+#### Scenario: JIT labels match the routing labels
+- **WHEN** the runner-kit test compares the labels requested by `mint-jitconfig.sh` with `routing.self_hosted_labels`
+- **THEN** the request carries no runner default label (`self-hosted`, `Linux`, `ARM64`)
+- **AND** the defaults together with the requested labels equal `routing.self_hosted_labels`, compared case-insensitively
+
+#### Scenario: Base image is pinned
+- **WHEN** the runner-kit test reads `deploy/gx10-runner/Containerfile`
+- **THEN** its `FROM` line names a version tag and an `@sha256:` digest, and does not use `latest`
+
+#### Scenario: Operator observes per-job ephemerality
+- **WHEN** after three jobs have run on instance 1 the operator reads the runner names those jobs ran on with `gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[].runner_name'` (JIT runners deregister after their job, so the runners list no longer shows them) and inspects `podman ps -a --filter name=gx10-runner --filter status=exited`
+- **THEN** each executed job ran on a distinct runner name
+- **AND** no exited runner container remains
+
+### Requirement: Runners Survive Host Reboot Via systemd
+
+The runner kit SHALL provide a systemd user template unit, `gx10-runner@.service`, with `Restart=always` and an explicit `TimeoutStartSec` in `[Service]`, `StartLimitIntervalSec=0` in `[Unit]`, and `WantedBy=default.target` in `[Install]`. The unit is intended to run under a dedicated lingering, unprivileged host user. Enabling linger and the units is an operator-only step. The kit's `install-units.sh` SHALL only copy files beneath its `--prefix` and print, never execute, the `loginctl` and `systemctl` commands that enable them.
+
+#### Scenario: Unit restart and install properties
+- **WHEN** the unit test parses `gx10-runner@.service`
+- **THEN** `[Service]` has `Restart=always` and a `TimeoutStartSec` greater than 90
+- **AND** `[Unit]` has `StartLimitIntervalSec=0`
+- **AND** `[Install]` has `WantedBy=default.target`
+
+#### Scenario: Install script does not mutate the host during tests
+- **WHEN** the runner-kit test runs `install-units.sh --prefix <tmpdir>`
+- **THEN** it writes only beneath that prefix
+- **AND** it prints, without executing, the `loginctl enable-linger` and `systemctl --user enable --now` commands
+
+#### Scenario: Operator verifies reboot survival
+- **WHEN** the GX10 is rebooted and nobody logs in
+- **THEN** `systemctl --user --machine=ghrunner@ is-active gx10-runner@1` reports `active`
+- **AND** the runner appears `online` in `gh api repos/{owner}/{repo}/actions/runners`
+
+### Requirement: CI Wall-Clock Measurement And Run Verification
+
+The repository SHALL provide `scripts/ci/ci_wallclock.py` with three functions:
+- `median_wallclock(runs)` SHALL compute the median wall-clock seconds over successful runs only.
+- `compare(baseline, candidate, threshold=0.85, min_n=5)` SHALL pass only when the candidate median is at most `threshold` times the baseline median and both samples meet `min_n`.
+- `verify_run(jobs, manifest, workflow, expected_lane="self-hosted")` SHALL report: every routed job that did not run on a `gx10`-labelled runner (or, with `expected_lane="hosted"`, every routed job that ran on a self-hosted runner); every hosted job that ran on a self-hosted runner; every job that concluded anything other than `success` or `skipped`, except that a job declared `continue-on-error: true` SHALL be reported as a warning rather than a violation; every `skipped` job whose definition has no job-level `if:`; and every manifest job missing from the run. A `skipped` job that has a job-level `if:` SHALL NOT be reported, and its runner placement SHALL NOT be checked. `verify_run` SHALL correlate manifest job ids with jobs-API entries through the display name derived from the workflow definition (the job id, or a literal `name:`; matrix expansions match `<display name> (` and are each checked), and SHALL report any jobs-API entry that matches no manifest job.
+
+The CLI SHALL select runs only through explicit filters (`--workflow`, `--head-sha`, `--event`, `--since`, `--until`) and SHALL cap fetched runs with `--limit`.
+
+#### Scenario: CLI fetches are filtered and bounded
+- **WHEN** `ci_wallclock.py compare` runs under test with a stubbed `gh` that records its calls and serves more matching runs than `--limit 10`, with `--workflow ci.yml --event workflow_dispatch --head-sha <sha>`
+- **THEN** the recorded `gh api` requests carry the workflow, event and `head_sha` filters, are all GET requests, and stop fetching pages once 10 runs are collected
+
+#### Scenario: Runs with mixed placement are excluded from comparison
+- **WHEN** `compare` receives a run whose routed jobs ran partly on `gx10` runners and partly on hosted runners
+- **THEN** that run is excluded from both samples and listed in the result's `excluded_runs` with a reason
+
+#### Scenario: Median ignores cancelled and failed runs
+- **WHEN** `median_wallclock` receives runs whose conclusions include `cancelled` and `failure`
+- **THEN** only `success` runs contribute to the median
+
+#### Scenario: Comparison enforces threshold and sample size
+- **WHEN** `compare` receives a baseline median of 600 s and a candidate median of 540 s, each with n=6
+- **THEN** it fails, because 540 is greater than 0.85 × 600 = 510
+- **AND** with a candidate median of 500 s it passes
+- **AND** with n=4 on either side it fails for insufficient samples
+
+#### Scenario: Run verification flags misrouted jobs
+- **WHEN** `verify_run` receives a run in which a routed job ran on a `ubuntu-latest` runner while the lane was self-hosted, and a hosted job ran on a runner labelled `gx10`
+- **THEN** it returns one violation for each job, naming the job and the expected lane
+
+#### Scenario: Conditionally skipped job is not a violation
+- **WHEN** `verify_run` receives a run in which `dependency-update-remediation`, which has a job-level `if:`, concluded `skipped` with no runner assigned, and every other job succeeded on its expected lane
+- **THEN** it returns zero violations
+
+#### Scenario: Matrix expansions are correlated to their job id
+- **WHEN** `verify_run` receives a workflow definition whose job `lint` has a two-entry `strategy.matrix`, and the jobs API returns `lint (a)` on a `gx10` runner and `lint (b)` on a hosted runner while the lane is self-hosted
+- **THEN** it returns a violation for `lint (b)` and none for `lint (a)`
+- **AND** a jobs-API entry whose name matches no manifest job is reported as an unknown job
+
+#### Scenario: Unconditional job skipped by an upstream failure is a violation
+- **WHEN** a job with no job-level `if:` concluded `skipped`
+- **THEN** `verify_run` returns a violation naming that job
+
+#### Scenario: Failed continue-on-error job is a warning
+- **WHEN** a job declared `continue-on-error: true` concluded `failure` and every other job succeeded on its expected lane
+- **THEN** `verify_run` returns zero violations and one warning naming that job
+- **AND** the `verify-run` CLI exits zero, printing the warning (it exits non-zero only on violations)
+
+#### Scenario: Rollback check expects hosted placement
+- **WHEN** `verify_run` is called with `expected_lane="hosted"` and a routed job ran on a runner labelled `gx10`
+- **THEN** it returns a violation naming that job
+
+#### Scenario: Operator confirms both workflows green on the self-hosted lane
+- **WHEN** the operator dispatches `ci.yml` and `security.yml` with `runner_lane=self-hosted` and runs `python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow <file>` for each run
+- **THEN** both report zero violations
+
+### Requirement: Implementation Does Not Mutate Hosts Or Repository Settings
+
+The implementation of this capability MUST NOT perform any of the following actions:
+- register runners;
+- mint registration or JIT tokens;
+- change repository or organization settings or variables;
+- install, enable or start systemd units or containers;
+- modify workflows on `main`.
+
+Each of those actions SHALL be documented as an operator-only runbook step in `docs/guides/self-hosted-ci-runners.md`, and each step MUST carry a concrete verification command.
+
+#### Scenario: Runbook covers every operator step with a verification command
+- **WHEN** the runbook test parses `docs/guides/self-hosted-ci-runners.md`
+- **THEN** each operator step O1 to O12 appears as a heading
+- **AND** each step contains at least one fenced verification command block
+
+#### Scenario: Scripts default to non-mutating behaviour
+- **WHEN** `install-units.sh` runs, with any arguments, or `ci_wallclock.py` runs under test
+- **THEN** no `systemctl`, `loginctl` or `podman` command and no mutating `gh api` call is executed
+- **AND** the commands that would mutate the host are only printed
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/tasks.md b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/tasks.md
new file mode 100644
index 00000000..65e0ee95
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/tasks.md
@@ -0,0 +1,486 @@
+# Tasks — migrate-ci-to-self-hosted-gx10-runners
+
+> Change ID: `migrate-ci-to-self-hosted-gx10-runners` · Roadmap item `roadmap-always-on-agent-automation/ri-20`
+
+**Conventions**
+- Sizes follow the plan-feature sizing table. No task is XL, and none is L.
+- Ordering is TDD: every test task comes before the implementation task it verifies, and that
+  implementation task depends on it.
+- Spec scenario references use the form `ci-runner-infrastructure / "<scenario>"`.
+- Design decisions are cited by D-number from `design.md`.
+- All tests live in `skills/tests/ci_runners/`. Run them with
+  `skills/.venv/bin/python -m pytest skills/tests/ci_runners -q`.
+- No test may pin `openspec/changes/<id>/`. Tests read the promoted `.github/` copies only.
+
+**HARD BOUNDARY — applies to every task in § 1–6.** Implementation tasks write files on this
+branch only. They MUST NOT do any of the following:
+- register runners;
+- mint registration or JIT tokens;
+- call a mutating GitHub API;
+- set repository or organization settings or variables;
+- run `systemctl`, `loginctl` or `podman run`/`podman build` against the host;
+- push to `main`.
+
+Everything of that kind is in § 7 (operator-only).
+
+## Status
+
+- [x] Planning
+- [ ] Implementation
+- [ ] Testing
+- [ ] Review
+- [ ] Done
+
+## Phase 1 — Contracts: manifest schema, manifest, test package
+
+- [ ] 1.1 Write `skills/tests/ci_runners/test_manifest_schema.py` (S)
+  - The promoted `.github/runner-lanes.schema.json` is valid Draft 2020-12.
+  - `.github/runner-lanes.yaml` validates against it.
+  - Negative fixtures are rejected:
+    - a hosted job with no `reason_code`;
+    - a hosted job with an empty `reason`;
+    - an unknown `reason_code`;
+    - `hosted_label` set to anything other than `ubuntu-latest`;
+    - `self_hosted_labels` without `self-hosted`.
+
+  **Spec scenarios**: ci-runner-infrastructure / "Hosted job without justification is rejected"
+  **Contracts**: contracts/schemas/runner-lanes.schema.json
+  **Design decisions**: D1
+  **Dependencies**: none
+- [ ] 1.2 Promote the schema from the change's `contracts/schemas/` to
+      `.github/runner-lanes.schema.json`, then author `.github/runner-lanes.yaml` (S)
+  - The manifest classifies every current job of `ci.yml` (25) and `security.yml` (3) exactly
+    as the design D2 table does.
+  - The routing block is `CI_RUNNER_LANE` / `runner_lane` /
+    `[self-hosted, linux, ARM64, gx10]` / `ubuntu-latest`.
+
+  **Spec scenarios**: ci-runner-infrastructure / "Hosted job without justification is rejected"
+  **Design decisions**: D1, D2
+  **Dependencies**: 1.1
+- [ ] 1.3 Create the `skills/tests/ci_runners/` package skeleton and register it (XS)
+  - Add `__init__.py`.
+  - Add `conftest.py` with fixtures `repo_root`, `manifest` and `load_workflow(name)`.
+  - Register the directory in the `testpaths` of `skills/pyproject.toml`, so that
+    `skills/tests/ci_coverage/test_ci_test_coverage.py` stays green.
+
+  **Dependencies**: none
+- [ ] Checkpoint: run tests, review diff, verify scope
+
+## Phase 2 — Workflow routing (`ci.yml`, `security.yml` on this branch)
+
+- [ ] 2.1 Write `test_routing_expression.py` (M)
+  - It contains a minimal reference evaluator for the D3 expression grammar:
+    - the `&&`/`||` value semantics of GitHub expressions;
+    - `==`/`!=`;
+    - `fromJSON` of a literal;
+    - context lookups from a dict.
+  - It asserts every row of the D3 evaluation table.
+  - It asserts that every routed job's `runs-on` equals the canonical string after whitespace
+    normalization.
+  - It asserts that the labels inside `fromJSON(...)` equal `routing.self_hosted_labels`, that
+    the `vars.<name>` reference equals `routing.repository_variable`, and that the
+    `inputs.<name>` references equal `routing.dispatch_input` (mutating any one manifest field
+    makes the test fail).
+
+  **Spec scenarios**: ci-runner-infrastructure / "Unset variable keeps CI on hosted runners",
+  "Variable opts same-repository events into the self-hosted lane", "Dispatch input overrides
+  the variable in both directions", "Expression is tied to every manifest routing field",
+  "Merge queue runs stay hosted", "Routed job drifts from the
+  canonical expression", "Fork pull request routes to hosted even with the self-hosted lane
+  enabled"
+  **Contracts**: .github/runner-lanes.schema.json
+  **Design decisions**: D3
+  **Dependencies**: 1.2, 1.3
+- [ ] 2.2 Write `test_manifest_completeness.py` (S)
+  - The set of job ids in each workflow equals the manifest's job set for that workflow, so
+    unclassified and stale entries are both caught.
+  - Every hosted job has `runs-on == "ubuntu-latest"` as a literal string.
+  - Derived display names (D8 correlation contract: job id, or a literal `name:`) are unique
+    within each workflow, and no job uses an expression in `name:`.
+
+  **Spec scenarios**: ci-runner-infrastructure / "Unclassified job fails the suite", "Stale
+  manifest entry fails the suite", "Hosted job uses a literal hosted label"
+  **Design decisions**: D1, D2
+  **Dependencies**: 1.2, 1.3
+- [ ] 2.3 Write `test_fork_guard.py` (S)
+  - Every routed job's first step is the D4 guard: its `if` condition and its `exit 1`.
+  - The guard's eligibility clause equals, after whitespace normalization, the negated
+    event-eligibility clause of the canonical D3 expression (so `merge_group` and fork PRs are
+    refused on a self-hosted runner).
+  - Both workflows' triggers are a subset of `{push, pull_request, merge_group,
+    workflow_dispatch}`.
+  - Both workflows declare a `workflow_dispatch` `runner_lane` choice input with options
+    `[auto, hosted, self-hosted]` and default `auto`.
+
+  **Spec scenarios**: ci-runner-infrastructure / "Routed job lacks the in-job fork guard",
+  "Privileged trigger is introduced", "Dispatch trigger and lane input are declared"
+  **Design decisions**: D4
+  **Dependencies**: 1.2, 1.3
+- [ ] 2.4 Write `test_tool_parity.py` (S)
+  - A routed job must not declare `services:`.
+  - A routed job's `run:` blocks must not invoke `docker`, `podman`, `sudo` or `apt-get` in
+    command position (D10 matching rule), except for entries in the commented allowlist, which
+    starts empty.
+  - A path such as `scripts/check_docker_imports.py` is not an invocation (positive fixture).
+  - A routed job that invokes `npm`/`npx`/`node`, `java` or `go` must have the matching
+    `actions/setup-*` step.
+
+  **Spec scenarios**: ci-runner-infrastructure / "Container-engine job marked routed is
+  rejected", "Command name inside a script path is not an invocation", "Routed job calls npm
+  without setup-node"
+  **Design decisions**: D2, D10
+  **Dependencies**: 1.2, 1.3
+- [ ] Checkpoint: run tests (expect 2.1–2.4 RED), review diff, verify scope
+> **Same-file chain.** 2.5 → 2.6 → 2.7 → 2.8 all edit `ci.yml` and/or `security.yml` and run
+> serially inside `wp-workflows`; they are never split across agents.
+
+- [ ] 2.5 Route the 20 routed `ci.yml` jobs (M)
+  - Replace their `runs-on` with the canonical expression and insert the D4 guard as their
+    first step.
+  - Leave the 5 hosted jobs on a literal `ubuntu-latest`, each with a one-line comment that
+    points to the manifest reason.
+  - Do not change job ids, `needs`, `permissions`, `concurrency` or `timeout-minutes`.
+
+  **Dependencies**: 2.1, 2.2, 2.3
+- [ ] 2.6 Route the 3 `security.yml` jobs (S)
+  - Apply the canonical expression and the D4 guard, as in 2.5.
+
+  **Dependencies**: 2.1, 2.2, 2.3, 2.5 (serial; same package)
+- [ ] 2.7 Add the `workflow_dispatch` trigger to both workflows (XS)
+  - Add the trigger with the `runner_lane` choice input: `auto` | `hosted` | `self-hosted`,
+    default `auto`.
+  - Leave the existing triggers unchanged.
+
+  **Dependencies**: 2.3, 2.6 (serial; edits both workflows after routing)
+- [ ] 2.8 Add explicit setup steps to routed jobs that rely on hosted-preinstalled tools (S)
+  - `validate-specs` needs `npm` and gets `actions/setup-node` at the repository's pinned
+    major version. Any other job that 2.4 flags gets the same treatment.
+  - The setup step goes after the D4 guard, which must stay the first step.
+  - Every routed job that uses `astral-sh/setup-uv` passes
+    `cache-local-path: /home/runner/.cache/uv`, so an opted-in shared cache is actually used
+    (D6); on the hosted lane the path is harmless because the hosted user is also `runner`.
+    Test 2.4 asserts it for routed jobs.
+
+  **Dependencies**: 2.4, 2.7 (serial; edits `ci.yml` after routing)
+- [ ] 2.9 Run the existing tests that parse workflows and confirm they stay green (XS)
+  - `skills/tests/ci_coverage/`
+  - `skills/tests/validate-feature/test_ci_sweep_wiring.py`
+  - `skills/tests/project-context-refresh/test_gate.py`
+  - `skills/tests/project-context-refresh/test_remediation_policy.py`
+  - `skills/tests/install_sh/test_consumer_portability.py`
+
+  Fix only by adjusting this change's workflow edits, never by editing those tests' contracts.
+
+  **Dependencies**: 2.5, 2.6, 2.7, 2.8
+- [ ] Checkpoint: run tests (2.1–2.4 GREEN), review diff, verify scope
+
+## Phase 3 — Runner kit (`deploy/gx10-runner/`), written and never installed
+
+- [ ] 3.1 Write `test_systemd_unit.py` (S)
+  - Parse `systemd/gx10-runner@.service` with an INI parser that allows repeated keys.
+  - `Restart=always` and `StartLimitIntervalSec=0` are set, and `WantedBy=default.target` is
+    present.
+  - `Restart=always` and `TimeoutStartSec` (> 90, and > the example env file's
+    `GX10_MINT_MAX_ELAPSED`) are in `[Service]`; `StartLimitIntervalSec=0` is in `[Unit]`.
+  - `ExecStartPre` invokes `mint-jitconfig.sh`, and `ExecStopPost` invokes `cleanup-runner.sh`.
+  - `[Service]` has `EnvironmentFile=%h/.config/gx10-runner/env` and
+    `LoadCredential=github-token:%h/.config/gx10-runner/token` (D7), and every `$VAR` that
+    `ExecStartPre`/`ExecStart` reference is defined in `gx10-runner.env.example`.
+  - `ExecStart` is `podman run` with each of these: `--rm`, `--replace`, `--pull=never`, `--env-file`,
+    `--cap-drop ALL`, `--security-opt no-new-privileges`,
+    `--network slirp4netns:allow_host_loopback=false`, `--pids-limit`, `--cpus`, `--memory`.
+  - `ExecStart` contains none of these: `--privileged`, `--network host`/`--network=host`, any
+    other `--network` value, a `*.sock` volume source, or `%h`/`$HOME` as a bind source.
+  - Cache switch (D6/A10): `ExecStart` contains `$GX10_RUNNER_CACHE_ARGS` as a standalone,
+    unbraced word and no literal cache `--volume`; the example env file sets it empty. Expanding
+    `ExecStart` with systemd word-splitting semantics yields no `--volume` argument when the
+    value is empty, and exactly `--volume gx10-runner-uv-cache:/home/runner/.cache/uv` (a named
+    volume, never a bind path) when it holds the documented opt-in value.
+  - If `systemd-analyze` is present, also run `systemd-analyze verify --user` on a copy whose
+    `Exec*` paths are stubbed. Otherwise skip that check.
+
+  **Spec scenarios**: ci-runner-infrastructure / "Unit runs a removable container with a
+  single-use config", "Dangerous container options are absent", "Unit restart and install
+  properties", "Unit wiring delivers configuration and credential", "Shared cache is off unless
+  the operator opts in"
+  **Design decisions**: D5, D6, D7
+  **Dependencies**: 1.3
+- [ ] 3.2 Author `deploy/gx10-runner/systemd/gx10-runner@.service` and
+      `deploy/gx10-runner/gx10-runner.env.example` (S)
+  - The example env file sets: repo slug, instance CPU and memory limits, image reference,
+    `GX10_RUNNER_CACHE_ARGS=` (empty: no shared cache, D6/A10), `GX10_MINT_MAX_ELAPSED`
+    (default 600), and labels mirrored from the
+    manifest. It does not set `GX10_RUNNER_TOKEN_FILE`: the unit delivers the credential
+    through `LoadCredential=` (D7).
+
+  **Dependencies**: 3.1
+- [ ] 3.3 Write `test_jit_scripts.py` (M)
+  - Run `mint-jitconfig.sh` and `cleanup-runner.sh` under `bash` with a stub `curl` on `PATH`.
+    The stub records its arguments and returns fixture JSON, so the test never touches the
+    network.
+  - The mint script refuses a credential file whose mode is wider than 0600.
+  - The mint script POSTs to `actions/runners/generate-jitconfig` with only the custom labels;
+    the runner defaults (`self-hosted`, `Linux`, `ARM64`) ∪ the requested labels equal
+    `routing.self_hosted_labels`, compared case-insensitively (D5).
+  - The output env file has mode 0600 and contains only `ACTIONS_RUNNER_INPUT_JITCONFIG` and
+    `GX10_RUNNER_ID`.
+  - The mint script retries with backoff on HTTP 5xx and exits non-zero, writing no env file,
+    once `GX10_MINT_MAX_ELAPSED` is spent. The test overrides the base delay and the budget so
+    it stays fast.
+  - The cleanup script issues a DELETE only for an offline runner id and always exits 0.
+  - Before minting, the mint script DELETEs only **offline** runners whose name starts with
+    `gx10-<hostname>-<instance>-`; an online runner, another instance's runner and another
+    host's runner are left alone, and a failing sweep does not stop the mint (D5).
+
+  **Spec scenarios**: ci-runner-infrastructure / "Credential stays on the host", "Mint retries
+  are bounded below the start timeout", "JIT labels match the routing labels", "Stale
+  registrations of the instance are swept before minting"
+  **Design decisions**: D5
+  **Dependencies**: 1.2, 1.3
+- [ ] Checkpoint: run tests, review diff, verify scope
+- [ ] 3.4 Author `deploy/gx10-runner/mint-jitconfig.sh` (S)
+  - Use `set -euo pipefail`.
+  - Read the credential from `$CREDENTIALS_DIRECTORY/github-token`, falling back to
+    `GX10_RUNNER_TOKEN_FILE`.
+  - Write with umask 077.
+  - Sweep this instance's stale offline registrations before minting (D5).
+  - Use exponential backoff with a per-attempt cap of 300 s, inside the total budget
+    `GX10_MINT_MAX_ELAPSED` (default 600 s).
+
+  **Dependencies**: 3.3
+- [ ] 3.5 Author `deploy/gx10-runner/cleanup-runner.sh` (XS)
+  - Delete the runner registration only if it is still registered and offline. Cleanup is
+    best-effort and always exits 0.
+
+  **Dependencies**: 3.3
+- [ ] 3.6 Write `test_runner_image.py` (XS)
+  - The `FROM` line of `Containerfile` names `ghcr.io/actions/actions-runner:<version>@sha256:<64 hex>`
+    and does not use `latest`.
+  - Every package in `toolchain.txt` is installed by the Containerfile.
+  - The final `USER` is not root.
+  - The image sets `ENV UV_CACHE_DIR=/home/runner/.cache/uv` (D6).
+  - No `sudoers` grant is added.
+
+  **Spec scenarios**: ci-runner-infrastructure / "Base image is pinned"
+  **Design decisions**: D6
+  **Dependencies**: 1.3
+- [ ] 3.7 Author `deploy/gx10-runner/Containerfile` and `deploy/gx10-runner/toolchain.txt` (S)
+  - Pin the base image digest: read it from the registry manifest with `podman manifest
+    inspect` or `skopeo inspect`. Reading is allowed; building or running an image is not.
+  - Follow the D6 baseline toolchain.
+
+  **Dependencies**: 3.6
+- [ ] 3.8 Write `test_install_units.py` (XS)
+  - Run `install-units.sh --prefix <tmp>` with stub `systemctl`/`loginctl`/`podman` on `PATH`.
+    Each stub fails the test if it is invoked.
+  - Files land only beneath `<tmp>`.
+  - The `loginctl enable-linger` and `systemctl --user enable --now gx10-runner@{1..N}`
+    commands are printed but not executed.
+
+  **Spec scenarios**: ci-runner-infrastructure / "Install script does not mutate the host
+  during tests", "Scripts default to non-mutating behaviour"
+  **Design decisions**: D7
+  **Dependencies**: 1.3
+- [ ] 3.9 Author `deploy/gx10-runner/install-units.sh` (XS)
+  - Use the copy-and-print-only behaviour of D7.
+
+  **Dependencies**: 3.8
+- [ ] Checkpoint: run tests, review diff, verify scope
+
+## Phase 4 — Measurement and run verification (`scripts/ci/ci_wallclock.py`)
+
+- [ ] 4.1 Write `test_ci_wallclock.py` over JSON fixtures in `skills/tests/ci_runners/fixtures/` (S)
+  - The median uses `success` runs only.
+  - `compare` checks the 600/540/500 threshold cases and n<5 (insufficient sample).
+  - `verify_run` flags each of these:
+    - a misrouted routed job (both `expected_lane` values);
+    - a hosted job on `gx10`;
+    - a conclusion other than `success`/`skipped`, with jobs marked `continue-on-error`
+      reported as warnings;
+    - a `skipped` job that has no job-level `if:`;
+    - a missing job;
+    - a jobs-API entry that matches no manifest job (unknown job).
+  - Correlation follows the D8 contract: display name = job id or literal `name:`, matrix
+    expansions matched by `<display name> (` prefix and each checked (fixture with a matrix job).
+  - `verify_run` does **not** flag `dependency-update-remediation` concluding `skipped` with no
+    runner (it has a job-level `if:`).
+  - The CLI's argument parsing, including `--head-sha`, `--event`, `--since`, `--until`,
+    `--limit`, `--expect-lane` and `--workflow-file`, works with no network access. `gh` is
+    stubbed.
+  - With a recording `gh` stub that serves more matching runs than `--limit`, the issued
+    requests are GETs carrying the workflow/event/`head_sha` filters, and paging stops once
+    `--limit` runs are collected (no fetch-all-then-truncate).
+  - `compare` excludes a run with mixed routed-job placement (or no assigned routed runner)
+    from both samples and lists it in `excluded_runs`.
+  - `verify-run` without `--workflow-file` fetches the definition at the run's `head_sha`
+    (asserted on the recorded `gh api .../contents/...?ref=<sha>` call).
+
+  **Spec scenarios**: ci-runner-infrastructure / "Median ignores cancelled and failed runs",
+  "Comparison enforces threshold and sample size", "Run verification flags misrouted jobs",
+  "Conditionally skipped job is not a violation", "Unconditional job skipped by an upstream
+  failure is a violation", "Rollback check expects hosted placement", "Matrix expansions are
+  correlated to their job id", "Failed continue-on-error job is a warning", "CLI fetches are
+  filtered and bounded", "Runs with mixed placement are excluded from comparison"
+  **Design decisions**: D8
+  **Dependencies**: 1.2, 1.3
+- [ ] 4.2 Implement the pure functions `median_wallclock`, `compare` and `verify_run` in
+      `scripts/ci/ci_wallclock.py` (S)
+  - Use the standard library plus PyYAML only.
+
+  **Dependencies**: 4.1
+- [ ] 4.3 Add the CLI subcommands `median`, `compare` and `verify-run` (S)
+  - Each fetches through `gh api` read-only GETs, bounded by `--limit` (default 200).
+  - `median` and `compare` select runs with `--workflow` (required), `--head-sha`, `--event`,
+    `--since` and `--until` (D8).
+  - `verify-run` takes `--expect-lane self-hosted|hosted` (default `self-hosted`) and exits
+    non-zero on any violation; warnings (failed `continue-on-error` jobs) are printed and do
+    not change the exit code.
+
+  **Dependencies**: 4.2
+- [ ] Checkpoint: run tests, review diff, verify scope
+
+## Phase 5 — Operator runbook
+
+- [ ] 5.1 Write `test_runbook.py` (XS)
+  - `docs/guides/self-hosted-ci-runners.md` has headings `O1` through `O12`.
+  - Each section contains at least one fenced `bash` verification block.
+  - The runbook states the hard boundary.
+  - The runbook names the rollback command (`gh variable set CI_RUNNER_LANE --body hosted`).
+
+  **Spec scenarios**: ci-runner-infrastructure / "Runbook covers every operator step with a
+  verification command"
+  **Design decisions**: D9
+  **Dependencies**: 1.3
+- [ ] 5.2 Author `docs/guides/self-hosted-ci-runners.md` (S)
+  - Write steps O1–O12 from § 7, each with its exact commands and verification.
+  - Include the queued-run detection command for D9.
+  - Include the GitHub App upgrade path for D5.
+  - Include the cache opt-in for D6: it is off by default; enabling it sets
+    `GX10_RUNNER_CACHE_ARGS=--volume gx10-runner-uv-cache:/home/runner/.cache/uv` only after the
+    operator fills in a recorded risk-acceptance line (date, confirmation that every
+    same-repository writer, including Dependabot and agent branches, is acceptable); disabling
+    empties it and removes the volume; a move to team mode requires disabling it (A10).
+  - Include the podman-5 note: keep the explicit `slirp4netns` network, or switch to
+    `pasta:--no-map-gw` only through a reviewed unit change (A11).
+
+  **Dependencies**: 5.1
+- [ ] 5.3 Link the runbook from `docs/guides/documentation.md`, under setup and deployment (XS)
+
+  **Dependencies**: 5.2
+- [ ] Checkpoint: run tests, review diff, verify scope
+
+## Phase 6 — Integration
+
+- [ ] 6.1 Run the full skills suite and validators (S)
+  - Run the full skills suite with `skills/.venv/bin/python -m pytest skills/tests -q`.
+  - Run `openspec validate migrate-ci-to-self-hosted-gx10-runners --strict`.
+  - If `actionlint` is available, run it over both workflows. Otherwise record it as skipped.
+  - Confirm with `git diff origin/main --stat` that the diff touches only files inside the
+    package scopes.
+
+  **Dependencies**: 2.9, 3.2, 3.4, 3.5, 3.7, 3.9, 4.3, 5.3
+
+## Phase 7 — OPERATOR-ONLY (post-merge; NOT implementation tasks)
+
+> These steps need a human with host and repository-admin access. Autopilot phases MUST NOT
+> perform them or mark them done. The validation report lists them as `pending_gate`. The
+> runbook (§ 5) holds the full commands.
+>
+> **Order:** O1–O5 first, then O6 as the dry run, O7 to flip, O8–O11 to measure and verify, and
+> O12 to roll back if needed.
+
+- [ ] O1 Create the dedicated host user and enable linger *(outcome 4, host half)*
+  - Run `sudo useradd --system --create-home --shell /usr/sbin/nologin ghrunner`, then give it
+    a subordinate id range, which `useradd --system` does not allocate and rootless podman
+    needs for the non-root `runner` user in the image:
+    `sudo usermod --add-subuids 200000-265535 --add-subgids 200000-265535 ghrunner`.
+  - Run `sudo loginctl enable-linger ghrunner`.
+  - Because the account has no login shell, run every later "as `ghrunner`" command as
+    `sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) <command>` (or
+    `systemctl --user --machine=ghrunner@ …` for unit operations).
+  - **Verify**: `loginctl show-user ghrunner -p Linger` prints `Linger=yes`, and
+    `grep ghrunner /etc/subuid /etc/subgid` shows one range in each file.
+- [ ] O2 Provision the registration credential
+  - Create a fine-grained PAT for this repository only, with *Administration: read and write*
+    and an expiry of 90 days or less.
+  - Store it as `~ghrunner/.config/gx10-runner/token` with mode 0600; the unit's
+    `LoadCredential=github-token:%h/.config/gx10-runner/token` reads it from there (D7).
+  - Copy `deploy/gx10-runner/gx10-runner.env.example` to `~ghrunner/.config/gx10-runner/env`
+    and fill in the repository slug and image reference (`EnvironmentFile=`, D7).
+  - **Verify**: `stat -c %a ~ghrunner/.config/gx10-runner/token` prints `600`, and
+    `GH_TOKEN=$(sudo cat …) gh api repos/{owner}/{repo}/actions/runners --jq .total_count`
+    exits 0.
+- [ ] O3 Build the runner image on the GX10 as `ghrunner`
+  - Run `podman build -t localhost/gx10-runner:<sha> deploy/gx10-runner`.
+  - **Verify**: `podman image inspect localhost/gx10-runner:<sha> --format '{{.Architecture}}'`
+    prints `arm64`.
+- [ ] O4 Install the host-service isolation control, then install and enable the units
+  - First, as root, install the isolation control (D6). Preferred: an nftables `output` hook
+    chain with, in order, `meta skuid ghrunner ip daddr 127.0.0.53 udp dport 53 accept`, the
+    same rule for `tcp`, and `meta skuid ghrunner fib daddr type local drop`. Fallback: rebind
+    every host service the runners must not reach to `127.0.0.1`.
+  - Then run `deploy/gx10-runner/install-units.sh`, then `systemctl --user daemon-reload` and
+    `systemctl --user enable --now gx10-runner@{1..8}` as `ghrunner`.
+  - **Verify**:
+    `gh api repos/{owner}/{repo}/actions/runners --jq '[.runners[]|select(any(.labels[];.name=="gx10"))|.status]'`
+    lists 8 entries, all `online`.
+  - **Also verify**: for each address in `10.0.2.2 $(hostname -I)` and each port in
+    `54322 <coordinator-port>`,
+    `podman exec gx10-runner-1 bash -c 'timeout 3 bash -c "exec 3<>/dev/tcp/<addr>/<port>" && echo reachable || echo unreachable'`
+    prints `unreachable` (a transport-level connect; an HTTP `curl` probe is wrong here, because
+    it fails after connecting to a non-HTTP service such as Postgres);
+    `sudo -u ghrunner getent hosts api.github.com` resolves (the DNS exemption works);
+    `sudo nft list ruleset | grep skuid` shows the rules (or `ss -ltnp` shows those ports bound
+    to `127.0.0.1` only); and
+    `podman inspect gx10-runner-1 --format '{{.HostConfig.NetworkMode}}'` shows `slirp4netns`.
+    A probe of `10.0.2.2` alone is not sufficient (D6).
+  - If the operator opts in to the shared uv cache (D6/A10), fill in the runbook's
+    risk-acceptance line (date; confirmation that every same-repository writer, including
+    Dependabot and agent branches, is acceptable) before setting `GX10_RUNNER_CACHE_ARGS`.
+- [ ] O5 Set the fork-PR approval policy *(outcome 3, settings half)*
+  - Run `gh api -X PUT repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors`.
+  - Confirm the runners are repository-scoped, not organization-scoped.
+  - **Verify**:
+    `gh api repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval --jq .approval_policy`
+    prints `all_external_contributors`.
+- [ ] O6 Self-hosted dry run before flipping *(outcome 1)*
+  - Run `gh workflow run ci.yml --ref main -f runner_lane=self-hosted` and the same command for
+    `security.yml`.
+  - **Verify**: `python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow ci.yml`, and
+    the same for `security.yml`, report 0 violations.
+  - If a routed job fails on arm64, open a PR that moves it to `hosted` with
+    `reason_code: amd64-only`, then repeat O6.
+- [ ] O7 Flip the lane
+  - Run `gh variable set CI_RUNNER_LANE --body self-hosted`.
+  - **Verify**: `gh variable get CI_RUNNER_LANE` prints `self-hosted`, and the next PR's
+    `verify-run` reports 0 violations.
+- [ ] O8 Measure wall-clock time *(outcome 2)*
+  - Dispatch 5 or more paired runs per lane on the same commit (`runner_lane=hosted` versus
+    `self-hosted`).
+  - **Verify**: `python scripts/ci/ci_wallclock.py compare --baseline-lane hosted --candidate-lane self-hosted --workflow ci.yml --event workflow_dispatch --head-sha <sha>`
+    passes, meaning the median ratio is 0.85 or less with n ≥ 5 on each side.
+  - **Corroborate**: run `median` over 20 or more PR runs before and after the O7 date.
+  - If the comparison fails, tune the instance count, or move the slowest routed jobs to
+    `measured-slower`.
+- [ ] O9 Check per-job ephemerality *(outcome 4)*
+  - **Verify**: after 3 or more jobs have run on instance 1,
+    `journalctl --user -u gx10-runner@1 | grep -c 'Listening for Jobs'` is 3 or more, and
+    `gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[].runner_name'` shows
+    distinct names (JIT runners deregister after their job, so the runners list cannot show
+    them).
+  - **Also verify**: `podman ps -a --filter name=gx10-runner --filter status=exited` is empty.
+- [ ] O10 Check reboot survival *(outcome 4)*
+  - Run `sudo systemctl reboot`. Do not log in as `ghrunner`.
+  - **Verify**: `sudo systemctl --user --machine=ghrunner@ is-active gx10-runner@1` prints
+    `active`, and the runner shows `online` in the runners API within 2 minutes of boot.
+- [ ] O11 Fork-PR end-to-end check *(outcome 3)*
+  - Open a trivial PR from a fork account.
+  - **Verify**: `gh run list --branch <fork-branch> --json status,conclusion` shows the run
+    awaiting approval (`action_required`).
+  - After approval, `python scripts/ci/ci_wallclock.py verify-run <run-id> --workflow ci.yml --expect-lane hosted`
+    reports 0 violations: every job ran on GitHub-hosted runners (without `--expect-lane hosted`
+    the default `self-hosted` expectation would flag every routed job).
+- [ ] O12 Rollback drill
+  - Run `gh variable set CI_RUNNER_LANE --body hosted`.
+  - **Verify**: the next CI run's `verify-run --expect-lane hosted` shows every job on
+    GitHub-hosted runners. Then restore with O7.
diff --git a/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/work-packages.yaml b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/work-packages.yaml
new file mode 100644
index 00000000..7370743b
--- /dev/null
+++ b/openspec/changes/migrate-ci-to-self-hosted-gx10-runners/work-packages.yaml
@@ -0,0 +1,449 @@
+schema_version: 1
+
+feature:
+  id: migrate-ci-to-self-hosted-gx10-runners
+  title: "Migrate CI to self-hosted GX10 runners (roadmap-always-on-agent-automation ri-20)"
+  plan_revision: 2
+  created_by: claude-code
+  # No running service. The change consists of workflow YAML, a host kit that is never
+  # installed, a measurement CLI, docs and static tests. validate-feature skips the
+  # deploy/smoke/scan phases. The live outcomes are the operator-only steps O1-O12 in tasks.md
+  # section 7, and the validation report records them as pending_gate.
+  deployable: false
+
+contracts:
+  revision: 1
+  # No OpenAPI surface (see contracts/README.md). The schema requires an openapi block, so
+  # `primary` points at the README that records that decision. The real boundary between
+  # packages is the lane-manifest JSON Schema.
+  openapi:
+    primary: "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/README.md"
+    files:
+      - "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/README.md"
+      - "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/schemas/runner-lanes.schema.json"
+
+defaults:
+  priority: 5
+  lock_ttl_minutes: 120
+  timeout_minutes: 60
+  retry_budget: 2
+  verification_tier_required: B
+  min_trust_level: 2
+
+packages:
+  # ─────────────────────────────────────────────────────────────────────
+  # wp-contracts — lane manifest schema + manifest + test package (DAG root)
+  # ─────────────────────────────────────────────────────────────────────
+  - package_id: wp-contracts
+    title: "Contracts — runner-lanes schema promoted, manifest authored, test package registered"
+    task_type: contracts
+    description: |
+      tasks.md 1.1-1.3. Promote the change-local draft schema to
+      .github/runner-lanes.schema.json. Author .github/runner-lanes.yaml, classifying all 28 jobs
+      as in design D2. Create the skills/tests/ci_runners package with its conftest fixtures and
+      register it in the testpaths of skills/pyproject.toml. HARD BOUNDARY: write files only; no
+      mutating host, repository-settings or GitHub API calls.
+    role: contracts-author
+    priority: 1
+    depends_on: []
+    locks:
+      files:
+        - ".github/runner-lanes.yaml"
+        - ".github/runner-lanes.schema.json"
+        - "skills/pyproject.toml"
+      keys:
+        - "contract:runner-lanes-schema"
+      ttl_minutes: 60
+      reason: "Lane manifest schema consumed by workflow, runner-kit and tooling packages"
+    scope:
+      write_allow:
+        - ".github/runner-lanes.yaml"
+        - ".github/runner-lanes.schema.json"
+        - "skills/pyproject.toml"
+        - "skills/tests/ci_runners/__init__.py"
+        - "skills/tests/ci_runners/conftest.py"
+        - "skills/tests/ci_runners/test_manifest_schema.py"
+        - "skills/tests/ci_runners/fixtures/manifests/**"
+      read_allow:
+        - "openspec/**"
+        - ".github/**"
+        - "skills/**"
+    worktree:
+      name: migrate-ci-to-self-hosted-gx10-runners-wp-contracts
+      mode: isolated
+    timeout_minutes: 30
+    retry_budget: 1
+    min_trust_level: 2
+    verification:
+      tier_required: B
+      steps:
+        - name: "Manifest validates against the promoted schema; negative fixtures rejected"
+          kind: command
+          command: "uv run pytest tests/ci_runners/test_manifest_schema.py tests/ci_coverage -q"
+          cwd: "skills"
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["contracts_valid"]
+    metadata:
+      loc_estimate: 180
+      complexity: low
+      package_kind: config
+    context_impact:
+      surfaces: [capabilities, documentation]
+    inputs: {}
+    outputs:
+      result_keys: ["contracts_valid"]
+      artifacts:
+        - ".github/runner-lanes.yaml"
+        - ".github/runner-lanes.schema.json"
+
+  # ─────────────────────────────────────────────────────────────────────
+  # wp-workflows — canonical routing expression, fork guard, dispatch input, tool parity
+  # ─────────────────────────────────────────────────────────────────────
+  - package_id: wp-workflows
+    title: "Workflow routing — ci.yml and security.yml lanes, fork guard, dispatch input"
+    task_type: backend
+    description: |
+      tasks.md 2.1-2.9. Write the reference-evaluator routing tests, the manifest-completeness
+      tests, the fork-guard and trigger-allowlist tests, and the tool-parity tests (RED). Then
+      add three things to every routed job of ci.yml (20 jobs) and security.yml (3 jobs): the
+      canonical D3 runs-on expression, the D4 fork guard as the first step, and the setup steps
+      D10 requires. Add a workflow_dispatch trigger to both files with the runner_lane input.
+      Hosted jobs keep a literal ubuntu-latest. Job ids, needs, permissions and concurrency are
+      unchanged. The existing tests that parse workflows must stay green. HARD BOUNDARY: edit
+      the workflows on this branch only; never set CI_RUNNER_LANE and never touch main.
+    role: implementer
+    priority: 2
+    depends_on: [wp-contracts]
+    locks:
+      files:
+        - ".github/workflows/ci.yml"
+        - ".github/workflows/security.yml"
+      keys: []  # file locks suffice; no logical namespace (api/db/event/flag/env/contract) applies
+      ttl_minutes: 120
+      reason: "Routing edits to CI workflows"
+    scope:
+      write_allow:
+        - ".github/workflows/ci.yml"
+        - ".github/workflows/security.yml"
+        - "skills/tests/ci_runners/test_routing_expression.py"
+        - "skills/tests/ci_runners/test_manifest_completeness.py"
+        - "skills/tests/ci_runners/test_fork_guard.py"
+        - "skills/tests/ci_runners/test_tool_parity.py"
+        - "skills/tests/ci_runners/_gha_expr.py"
+      read_allow:
+        - ".github/**"
+        - "skills/**"
+        - "openspec/**"
+      deny:
+        - "deploy/**"
+        - "scripts/ci/**"
+    worktree:
+      name: migrate-ci-to-self-hosted-gx10-runners-wp-workflows
+      mode: isolated
+    timeout_minutes: 90
+    retry_budget: 2
+    min_trust_level: 2
+    verification:
+      tier_required: B
+      steps:
+        - name: "Routing and workflow-parser tests green"
+          kind: command
+          command: "uv run pytest tests/ci_runners tests/ci_coverage tests/validate-feature/test_ci_sweep_wiring.py tests/project-context-refresh tests/install_sh/test_consumer_portability.py -q"
+          cwd: "skills"
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["workflows_routed"]
+    metadata:
+      loc_estimate: 450
+      complexity: medium
+      package_kind: config
+    context_impact:
+      surfaces: [capabilities]
+    inputs: {}
+    outputs:
+      result_keys: ["workflows_routed"]
+      artifacts:
+        - ".github/workflows/ci.yml"
+        - ".github/workflows/security.yml"
+
+  # ─────────────────────────────────────────────────────────────────────
+  # wp-runner-kit — Containerfile, JIT mint/cleanup scripts, systemd user unit, install script
+  # ─────────────────────────────────────────────────────────────────────
+  - package_id: wp-runner-kit
+    title: "Runner kit — pinned arm64 image, host-minted JIT config, systemd user template unit"
+    task_type: backend
+    description: |
+      tasks.md 3.1-3.9. Write deploy/gx10-runner/ test-first:
+        - the Containerfile, pinned by digest, and toolchain.txt;
+        - mint-jitconfig.sh and cleanup-runner.sh;
+        - systemd/gx10-runner@.service, with Restart=always, StartLimitIntervalSec=0,
+          WantedBy=default.target and the hardened podman run of D6;
+        - gx10-runner.env.example;
+        - install-units.sh, which copies and prints only.
+      Tests stub curl, systemctl, loginctl and podman on PATH, and must fail if a host-mutating
+      binary is invoked. HARD BOUNDARY: never build or run an image, never call
+      generate-jitconfig, and never install or enable a unit. Reading a registry manifest to
+      pin the digest is allowed.
+    role: implementer
+    priority: 2
+    depends_on: [wp-contracts]
+    locks:
+      files:
+        - "deploy/gx10-runner/Containerfile"
+        - "deploy/gx10-runner/systemd/gx10-runner@.service"
+      keys: []  # file locks suffice; no logical namespace (api/db/event/flag/env/contract) applies
+      ttl_minutes: 120
+      reason: "GX10 runner host kit"
+    scope:
+      write_allow:
+        - "deploy/gx10-runner/**"
+        - "skills/tests/ci_runners/test_systemd_unit.py"
+        - "skills/tests/ci_runners/test_jit_scripts.py"
+        - "skills/tests/ci_runners/test_runner_image.py"
+        - "skills/tests/ci_runners/test_install_units.py"
+        - "skills/tests/ci_runners/fixtures/jit/**"
+      read_allow:
+        - ".github/runner-lanes.yaml"
+        - ".github/runner-lanes.schema.json"
+        - "skills/**"
+        - "openspec/**"
+      deny:
+        - ".github/workflows/**"
+        - "scripts/ci/**"
+    worktree:
+      name: migrate-ci-to-self-hosted-gx10-runners-wp-runner-kit
+      mode: isolated
+    timeout_minutes: 90
+    retry_budget: 2
+    min_trust_level: 2
+    verification:
+      tier_required: B
+      steps:
+        - name: "Runner-kit tests green, host binaries stubbed"
+          kind: command
+          command: "uv run pytest tests/ci_runners/test_systemd_unit.py tests/ci_runners/test_jit_scripts.py tests/ci_runners/test_runner_image.py tests/ci_runners/test_install_units.py -q"
+          cwd: "skills"
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["runner_kit_valid"]
+        - name: "Shell scripts pass shellcheck when available"
+          kind: command
+          command: "if command -v shellcheck >/dev/null; then shellcheck deploy/gx10-runner/*.sh; else echo 'shellcheck unavailable: skipped'; fi"
+          cwd: "."
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["shellcheck"]
+    metadata:
+      loc_estimate: 520
+      complexity: medium
+      package_kind: config
+    context_impact:
+      surfaces: [capabilities, documentation]
+    inputs: {}
+    outputs:
+      result_keys: ["runner_kit_valid", "shellcheck"]
+      artifacts:
+        - "deploy/gx10-runner/Containerfile"
+        - "deploy/gx10-runner/systemd/gx10-runner@.service"
+        - "deploy/gx10-runner/mint-jitconfig.sh"
+        - "deploy/gx10-runner/cleanup-runner.sh"
+        - "deploy/gx10-runner/install-units.sh"
+        - "deploy/gx10-runner/gx10-runner.env.example"
+        - "deploy/gx10-runner/toolchain.txt"
+
+  # ─────────────────────────────────────────────────────────────────────
+  # wp-tooling — wall-clock measurement + run verification CLI
+  # ─────────────────────────────────────────────────────────────────────
+  - package_id: wp-tooling
+    title: "Measurement tooling — ci_wallclock.py median/compare/verify-run"
+    task_type: backend
+    description: |
+      tasks.md 4.1-4.3. Write the pure functions median_wallclock, compare (threshold 0.85,
+      min_n 5) and verify_run (with expected_lane), tested over JSON fixtures. Add the CLI
+      subcommands, which use read-only `gh api` GETs bounded by --limit and select runs with
+      --workflow/--head-sha/--event/--since/--until. verify_run accepts `skipped` for jobs with a
+      job-level `if:` (design D8). Tests stub gh and make no network calls.
+    role: implementer
+    priority: 3
+    depends_on: [wp-contracts]
+    locks:
+      files:
+        - "scripts/ci/ci_wallclock.py"
+      keys: []  # file locks suffice; no logical namespace (api/db/event/flag/env/contract) applies
+      ttl_minutes: 90
+      reason: "CI measurement CLI"
+    scope:
+      write_allow:
+        - "scripts/ci/**"
+        - "skills/tests/ci_runners/test_ci_wallclock.py"
+        - "skills/tests/ci_runners/fixtures/runs/**"
+      read_allow:
+        - ".github/runner-lanes.yaml"
+        - ".github/workflows/**"  # read-only: verify_run's D8 correlation reads job definitions; writes stay with wp-workflows
+        - "skills/**"
+        - "openspec/**"
+      deny:
+        - "deploy/**"
+    worktree:
+      name: migrate-ci-to-self-hosted-gx10-runners-wp-tooling
+      mode: isolated
+    timeout_minutes: 60
+    retry_budget: 2
+    min_trust_level: 2
+    verification:
+      tier_required: B
+      steps:
+        - name: "ci_wallclock tests green offline"
+          kind: command
+          command: "uv run pytest tests/ci_runners/test_ci_wallclock.py -q"
+          cwd: "skills"
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["tooling_valid"]
+    metadata:
+      loc_estimate: 300
+      complexity: low
+      package_kind: algorithm
+    context_impact:
+      surfaces: [semantic_code]
+    inputs: {}
+    outputs:
+      result_keys: ["tooling_valid"]
+      artifacts:
+        - "scripts/ci/ci_wallclock.py"
+
+  # ─────────────────────────────────────────────────────────────────────
+  # wp-docs — operator runbook O1-O12
+  # ─────────────────────────────────────────────────────────────────────
+  - package_id: wp-docs
+    title: "Operator runbook — O1-O12 with verification commands"
+    task_type: docs
+    description: |
+      tasks.md 5.1-5.3. Write the runbook test, then docs/guides/self-hosted-ci-runners.md.
+      The runbook covers operator steps O1-O12 from tasks.md section 7, each with a fenced
+      verification command. It also states the hard boundary, the D9 rollback and the
+      queued-run detection, the App upgrade path and the cache-disable switch. Link the runbook
+      from docs/guides/documentation.md.
+    role: documenter
+    priority: 3
+    depends_on: [wp-contracts]
+    locks:
+      files:
+        - "docs/guides/self-hosted-ci-runners.md"
+        - "docs/guides/documentation.md"
+      keys: []  # file locks suffice; no logical namespace (api/db/event/flag/env/contract) applies
+      ttl_minutes: 60
+      reason: "Operator runbook"
+    scope:
+      write_allow:
+        - "docs/guides/self-hosted-ci-runners.md"
+        - "docs/guides/documentation.md"
+        - "skills/tests/ci_runners/test_runbook.py"
+      read_allow:
+        - "openspec/**"
+        - "deploy/**"
+        - "scripts/**"
+        - ".github/**"
+        - "docs/**"
+        - "skills/**"
+    worktree:
+      name: migrate-ci-to-self-hosted-gx10-runners-wp-docs
+      mode: isolated
+    timeout_minutes: 45
+    retry_budget: 1
+    min_trust_level: 2
+    verification:
+      tier_required: B
+      steps:
+        - name: "Runbook test green"
+          kind: command
+          command: "uv run pytest tests/ci_runners/test_runbook.py -q"
+          cwd: "skills"
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["runbook_valid"]
+    metadata:
+      loc_estimate: 300
+      complexity: low
+      package_kind: config
+    context_impact:
+      surfaces: [documentation]
+    inputs: {}
+    outputs:
+      result_keys: ["runbook_valid"]
+      artifacts:
+        - "docs/guides/self-hosted-ci-runners.md"
+
+  # ─────────────────────────────────────────────────────────────────────
+  # wp-integration — merge, full suite, validators (DAG sink)
+  # ─────────────────────────────────────────────────────────────────────
+  - package_id: wp-integration
+    title: "Integration — merge packages, full skills suite, openspec validate, actionlint"
+    task_type: integration
+    description: |
+      tasks.md 6.1. The package branches are merged by the orchestrator's merge step
+      (implement-feature C5, merge_worktrees.py) before this package starts, and each package's
+      diff is scope-checked against its own write_allow, so the materialized .github/, deploy/,
+      scripts/, docs/ and skills/ files are not writes of this package. This package writes only
+      under the change directory (evidence, validation notes). Run the full skills suite, `openspec validate
+      --strict` and actionlint (if it is installed), and confirm that the diff stays inside the
+      package scopes. Operator steps O1-O12 are NOT run here. They are recorded as pending_gate.
+    role: integrator
+    priority: 4
+    depends_on: [wp-workflows, wp-runner-kit, wp-tooling, wp-docs]
+    locks:
+      files: []
+      keys: []
+    scope:
+      write_allow:
+        - "openspec/changes/migrate-ci-to-self-hosted-gx10-runners/**"
+      read_allow:
+        - "**"
+    worktree:
+      name: migrate-ci-to-self-hosted-gx10-runners-wp-integration
+      mode: shared
+    timeout_minutes: 60
+    retry_budget: 1
+    min_trust_level: 2
+    verification:
+      tier_required: B
+      steps:
+        - name: "Skills suite green"
+          kind: command
+          command: "uv run pytest tests/ -q"
+          cwd: "skills"
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["skills_suite_green"]
+        - name: "OpenSpec valid"
+          kind: command
+          command: "openspec validate migrate-ci-to-self-hosted-gx10-runners --strict"
+          cwd: "."
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["openspec_valid"]
+        - name: "actionlint over routed workflows (skipped if unavailable)"
+          kind: command
+          command: "if command -v actionlint >/dev/null; then actionlint .github/workflows/ci.yml .github/workflows/security.yml; else echo 'actionlint unavailable: skipped'; fi"
+          cwd: "."
+          expect_exit_code: 0
+          evidence:
+            artifacts: []
+            result_keys: ["actionlint"]
+    metadata:
+      loc_estimate: 20
+      complexity: low
+      package_kind: integration
+    inputs: {}
+    outputs:
+      result_keys: ["skills_suite_green", "openspec_valid", "actionlint"]
+      artifacts: []

```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/adjudication-pass3-round-1.json
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/adjudication-round-1.json
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/.review-ledger/ledger.json
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/README.md
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/contracts/schemas/runner-lanes.schema.json
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/design.md
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/loop-state.json
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/plan-findings.md
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/proposal.md
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/session-log.md
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/tasks.md
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/work-packages.yaml

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/migrate-ci-to-self-hosted-gx10-runners/specs/ci-runner-infrastructure/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

### Spec excerpts
#### specs/ci-runner-infrastructure/spec.md
## ADDED Requirements

### Requirement: Lane Manifest Classifies Every Workflow Job

The repository SHALL maintain a lane manifest at `.github/runner-lanes.yaml`, valid against `.github/runner-lanes.schema.json`. The manifest SHALL classify every job in `.github/workflows/ci.yml` and `.github/workflows/security.yml` as either `routed` or `hosted`. Every `hosted` job MUST carry a `reason_code` from the closed set `container-engine`, `amd64-only`, `privileged-token` and `measured-slower`, together with a non-empty written `reason`.

#### Scenario: Unclassified job fails the suite
- **WHEN** a job id exists in `ci.yml` or `security.yml` but not in the manifest
- **THEN** the lane manifest test fails and names the unclassified workflow and job id

#### Scenario: Stale manifest entry fails the suite
- **WHEN** the manifest names a job id that no longer exists in its workflow
- **THEN** the lane manifest test fails and names the stale entry

#### Scenario: Hosted job without justification is rejected
- **WHEN** a manifest entry has `lane: hosted` and lacks `reason_code` or has an empty `reason`
- **THEN** schema validation of the manifest fails

### Requirement: Routed Jobs Default To The Hosted Lane

Every `routed` job SHALL use the single canonical `runs-on` expression defined in design D3. Under that expression a job SHALL resolve to `ubuntu-latest` unless the event is eligible — a `push`, a `workflow_dispatch`, or a same-repository `pull_request` (never a fork `pull_request`, never `merge_group`, never any other event) — and one of the following holds:
- a `workflow_dispatch` `runner_lane` input of `self-hosted` is supplied;
- the `CI_RUNNER_LANE` repository variable equals `self-hosted`, and no dispatch override of `hosted` is supplied.

The self-hosted label set inside the expression MUST equal the manifest's `routing.self_hosted_labels`.

Both `ci.yml` and `security.yml` SHALL declare a `workflow_dispatch` trigger with a `runner_lane` choice input whose options are exactly `auto`, `hosted` and `self-hosted`, with default `auto`.

#### Scenario: Unset variable keeps CI on hosted runners
- **WHEN** the reference evaluator resolves the canonical expression for a same-repository `pull_request`, `push` or `merge_group` event with `CI_RUNNER_LANE` unset
- **THEN** the result is `ubuntu-latest`

#### Scenario: Variable opts same-repository events into the self-hosted lane
- **WHEN** the reference evaluator resolves the expression for a same-repository `pull_request` with `CI_RUNNER_LANE` set to `self-hosted`
- **THEN** the result is the manifest's self-hosted label set

#### Scenario: Dispatch input overrides the variable in both directions
- **WHEN** the expression is resolved for a `workflow_dispatch` event with `runner_lane` set to `hosted` while `CI_RUNNER_LANE` is `self-hosted`
- **THEN** the result is `ubuntu-latest`
- **AND** with `runner_lane` set to `self-hosted` while the variable is unset, the result is the self-hosted label set

#### Scenario: Expression is tied to every manifest routing field
- **WHEN** the routing test changes the manifest's `routing.self_hosted_labels`, `routing.repository_variable` or `routing.dispatch_input` without changing the workflows
- **THEN** the test fails, because the expression's `fromJSON` labels, its `vars.<name>` reference and its `inputs.<name>` reference must equal those three fields

#### Scenario: Merge queue runs stay hosted
- **WHEN** the reference evaluator resolves the expression for a `merge_group` event with `CI_RUNNER_LANE` set to `self-hosted`
- **THEN** the result is `ubuntu-latest`, because a merge-group commit can contain an approved fork pull request's code

#### Scenario: Dispatch trigger and lane input are declared
- **WHEN** the fork guard test reads `ci.yml` and `security.yml`
- **THEN** each declares `workflow_dispatch` with a `runner_lane` choice input of options `auto`, `hosted`, `self-hosted` and default `auto`

#### Scenario: Routed job drifts from the canonical expression
- **WHEN** any `routed` job's `runs-on` differs from the canonical expression after whitespace normalization
- **THEN** the workflow routing test fails and names the job

### Requirement: Hosted-Pinned Jobs Are Explicit

Every `hosted` job SHALL declare a literal `runs-on: ubuntu-latest` and MUST NOT use the routing expression. A `routed` job MUST NOT declare `services:`, and its `run:` blocks MUST NOT invoke `docker`, `podman`, `sudo` or `apt-get` in command position, except for an entry in the tool-parity allowlist that names the workflow, job and command with a justifying comment (the allowlist starts empty). A `routed` job that invokes `npm`, `npx`, `node`, `java` or `go` in command position MUST include the matching setup action. A command name that appears only inside a path or identifier, such as `scripts/check_docker_imports.py`, is not an invocation. The scan covers `run:` text only; a command invoked indirectly from inside a script that a step calls is outside its reach and is caught by the operator's self-hosted dry run (O6), which moves such a job to `hosted` through the manifest.

#### Scenario: Container-engine job marked routed is rejected
- **WHEN** a job that declares `services:` or runs `docker`, `podman`, `sudo` or `apt-get` is classified `routed`
- **THEN** the tool-parity test fails, unless the job and command appear in the documented allowlist with a comment

#### Scenario: Hosted job uses a literal hosted label
- **WHEN** the routing test reads a manifest job with `lane: hosted`
- **THEN** that job's `runs-on` equals the string `ubuntu-latest`

#### Scenario: Command name inside a script path is not an invocation
- **WHEN** a routed job's `run:` block contains `uv run python scripts/check_docker_imports.py` and no other container command
- **THEN** the tool-parity test passes for that job without an allowlist entry

#### Scenario: Routed job calls npm without setup-node
- **WHEN** a routed job's `run:` block invokes `npm` and the job has no `actions/setup-node` step
- **THEN** the tool-parity test fails and names the job and command

### Requirement: Fork Pull Requests Never Execute On Self-Hosted Runners

A `pull_request` event whose head repository differs from the base repository, and every `merge_group` event (whose merge commit can contain approved fork code), SHALL resolve to `ubuntu-latest` regardless of the variable value. Every `routed` job's first step SHALL be a guard that fails the job when it is running on a self-hosted runner for any event outside the D3 eligibility allowlist, which includes every fork pull request and every `merge_group` run. Neither workflow SHALL declare the triggers `pull_request_target`, `workflow_run` or `issue_comment`. The repository's fork-PR contributor approval policy MUST be set to require approval for all external contributors; this is an operator-only step with a verification command.

#### Scenario: Fork pull request routes to hosted even with the self-hosted lane enabled
- **WHEN** the reference evaluator resolves the expression for a fork `pull_request` with `CI_RUNNER_LANE` set to `self-hosted`
- **THEN** the result is `ubuntu-latest`

#### Scenario: Routed job lacks the in-job fork guard
- **WHEN** a routed job's first step is not the canonical guard, with condition `runner.environment == 'self-hosted'` combined with the negation of the D3 event-eligibility clause
- **THEN** the fork guard test fails and names the job

#### Scenario: Privileged trigger is introduced
- **WHEN** `ci.yml` or `security.yml` declares `pull_request_target`, `workflow_run` or `issue_comment`
- **THEN** the trigger allowlist test fails

#### Scenario: Operator verifies the approval policy
- **WHEN** the operator runs `gh api repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval --jq .approval_policy`
- **THEN** the output is `all_external_contributors`

### Requirement: Runners Are Ephemeral Per Job

The runner kit under `deploy/gx10-runner/` SHALL meet all of the following:
- It SHALL register each runner with a single-use just-in-time configuration minted on the host before the container starts.
- It SHALL run the runner in a container started with `--rm`, so that one container serves exactly one job, and with `--replace`, so that a container left over from an unclean stop cannot wedge the restart loop.
- It SHALL delete the instance's own registration on stop (`ExecStopPost` runs `cleanup-runner.sh`) and, before minting, SHALL delete only the instance's own stale offline registrations, identified by the runner-name prefix `gx10-<hostname>-<instance>-`.
- It SHALL load its operator configuration through `EnvironmentFile=` and deliver the registration credential through `LoadCredential=`.
- It SHALL NOT pass the registration credential, a container engine socket, host networking or privileged mode into the container.
- It SHALL pin the container network explicitly to `slirp4netns:allow_host_loopback=false`, so that host loopback services stay unreachable regardless of the host's podman default.
- It SHALL start only the locally built image (`--pull=never`).
- It SHALL bound the mint script's total retry time below the unit's start timeout.
- It SHALL pin its base image by version and digest.
- It SHALL mount no shared cache volume by default; a shared uv cache volume is mounted only when the operator sets `GX10_RUNNER_CACHE_ARGS` to the documented named-volume value after recording a risk acceptance.
- Its runbook SHALL require an operator-installed control that keeps host services unreachable from runner containers on every host address, not only through the loopback mapping.

#### Scenario: Unit runs a removable container with a single-use config
- **WHEN** the unit test parses `gx10-runner@.service`
- **THEN** `ExecStartPre` invokes `mint-jitconfig.sh`
- **AND** `ExecStart` invokes `podman run` with `--rm`, `--pull=never`, `--env-file`, `--cap-drop ALL`, `--security-opt no-new-privileges` and `--network slirp4netns:allow_host_loopback=false`

#### Scenario: Dangerous container options are absent
- **WHEN** the unit test scans `ExecStart`
- **THEN** none of `--privileged`, `--network host`, `--network=host`, a `--network` value other than `slirp4netns:allow_host_loopback=false`, or a volume whose source ends in `.sock` is present

#### Scenario: Credential stays on the host
- **WHEN** the runner-kit tests inspect `mint-jitconfig.sh` and the container env-file contract
- **THEN** the env file written for the container contains only the JIT config and the runner id
- **AND** the mint script refuses a credential file whose mode is wider than `0600`

#### Scenario: Mint retries are bounded below the start timeout
- **WHEN** the stubbed GitHub API returns HTTP 503 on every call and the test sets a short retry budget
- **THEN** `mint-jitconfig.sh` retries with growing delays, exits non-zero once the budget is spent, and writes no env file
- **AND** the unit's `TimeoutStartSec` is greater than the default `GX10_MINT_MAX_ELAPSED` in the example env file

#### Scenario: Unit wiring delivers configuration and credential
- **WHEN** the unit test parses `gx10-runner@.service` and `gx10-runner.env.example`
- **THEN** `[Service]` declares `EnvironmentFile=` for the operator env file and `LoadCredential=github-token:<path>`
- **AND** every variable referenced by `ExecStartPre` or `ExecStart` is defined in the example env file

#### Scenario: Stale registrations of the instance are swept before minting
- **WHEN** the stubbed runners API lists an offline runner `gx10-<host>-1-<epoch>`, an online runner with the same prefix, and an offline runner `gx10-<host>-2-<epoch>`, and `mint-jitconfig.sh 1` runs
- **THEN** it deletes only the offline instance-1 runner before requesting a new JIT config

#### Scenario: Shared cache is off unless the operator opts in
- **WHEN** the unit test expands `ExecStart` with the example env file's `GX10_RUNNER_CACHE_ARGS` (empty)
- **THEN** no `--volume` argum

[spec excerpt truncated]


### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.