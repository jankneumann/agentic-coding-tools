## ADDED Requirements

### Requirement: Lead Session Bash Sandbox Configuration

The project-shared harness settings SHALL enable the harness's native Bash sandbox for interactive sessions and SHALL approve sandboxed Bash commands without a prompt. The settings MUST NOT require the sandbox to be available.

#### Scenario: Sandbox and auto-allow are on
WHEN `.claude/settings.json` is loaded
THEN `sandbox.enabled` SHALL be `true`
AND `sandbox.autoAllowBashIfSandboxed` SHALL be `true`

#### Scenario: A host without sandbox prerequisites still works
WHEN `.claude/settings.json` is loaded
THEN `sandbox.failIfUnavailable` SHALL be absent or `false`
AND `sandbox.allowUnsandboxedCommands` SHALL be absent or `true`

#### Scenario: Toolchain caches are writable
WHEN `.claude/settings.json` is loaded
THEN `sandbox.filesystem.allowWrite` SHALL include the uv cache directory for Linux and for macOS

### Requirement: Sandboxed Commands Cannot Read Credentials or Sibling Checkouts

The sandbox configuration SHALL deny reads of credential locations in the operator's home directory and of the directory that contains the project checkout, and SHALL re-allow reads of the project checkout itself.

#### Scenario: Credential locations are denied
WHEN `.claude/settings.json` is loaded
THEN `sandbox.filesystem.denyRead` SHALL include `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.netrc`, `~/.kube`, `~/.docker`, `~/.config/gh`, `~/.config/gcloud` and `~/.claude/.credentials.json`

#### Scenario: Sibling checkouts are denied and the project is not
WHEN `.claude/settings.json` is loaded
THEN `sandbox.filesystem.denyRead` SHALL include the parent of the project root
AND `sandbox.filesystem.allowRead` SHALL include the project root

#### Scenario: The denial is demonstrated on a sandboxed host
WHEN the sandbox probe runs inside the sandbox on a host where a denied credential directory exists
THEN the probe SHALL report that read as `enforced`
AND the probe SHALL report a read of a sibling directory of the project as `enforced`

### Requirement: Outward Commands Run Outside the Sandbox Under Permission Rules

Commands that reach a git remote or a deployment platform SHALL be excluded from the sandbox so that the permission rules decide them, and the sandbox network allowlist MUST NOT contain a host that accepts a git push.

#### Scenario: Outward commands are excluded
WHEN `.claude/settings.json` is loaded
THEN `sandbox.excludedCommands` SHALL include patterns for `git push`, `git fetch`, `git pull`, `gh`, `railway` and `docker`

#### Scenario: Git hosts are not reachable from inside the sandbox
WHEN `.claude/settings.json` is loaded
THEN `sandbox.network.allowedDomains` SHALL NOT contain `github.com` or any subdomain of it

#### Scenario: Network allowlist is limited to registries and the coordinator
WHEN `.claude/settings.json` is loaded
THEN every entry of `sandbox.network.allowedDomains` SHALL appear in the allowlist recorded in the test

### Requirement: Irreversible Command Classes Remain Gated

Every command class in the irreversible set (force-push, deletion, merge, deploy, migration, secret write) SHALL remain denied or prompted when the sandbox is on, by a deny rule, a content-scoped ask rule, or the irreversible guard hook. A bare `Bash` ask rule MUST NOT be the only gate for any class.

#### Scenario: Each class has a gate that survives auto-allow
WHEN the test enumerates representative commands for each class in the irreversible set
THEN each command SHALL match a deny rule, or a content-scoped ask rule, or SHALL receive a deny or ask verdict from `irreversible_guard.check`

#### Scenario: No gated command is also allowed outright
WHEN the test enumerates the same commands
THEN a command gated only by the hook SHALL NOT be listed for an unconditional skip of that hook
AND the PreToolUse Bash hook entry for `irreversible_guard.py` SHALL be present with `onFailure` set to `block`

#### Scenario: Recording a gate decision still prompts
WHEN the test enumerates `gate-answer` invocations of `runner.py` and `cycle_state.py`
THEN each SHALL match a content-scoped ask rule
AND a `relayed-gate-answer` or `gate-check` invocation SHALL NOT match one

#### Scenario: Ask rules are content-scoped
WHEN `.claude/settings.json` is loaded
THEN `permissions.ask` SHALL NOT contain `Bash` or `Bash(*)`

### Requirement: Allow List Grants No General Reader or Interpreter

The `permissions.allow` list SHALL NOT approve a Bash command whose first word is a general file reader or a language interpreter or test runner, because such a rule approves the same command when it is retried outside the sandbox.

#### Scenario: Readers and interpreters are absent
WHEN the test inspects every `Bash(...)` entry of `permissions.allow`
THEN no entry SHALL begin with `cat`, `head`, `tail`, `grep`, `rg`, `find`, `sed`, `jq`, `sort`, `uniq`, `wc`, `ls`, `python`, `python3`, `uv`, `pytest`, `bash` or `sh`, or with a path that ends in `/python` or `/pytest`

#### Scenario: The list is shorter
WHEN the test counts `permissions.allow`
THEN the count SHALL be less than half of the count before this change, which the test records

#### Scenario: Excluded fetch commands stay promptless
WHEN `.claude/settings.json` is loaded
THEN `permissions.allow` SHALL include rules for `git fetch` and `git pull`

### Requirement: Sandbox Probe

The `session-bootstrap` skill SHALL provide a probe that attempts the reads, writes and connections the sandbox is configured to refuse and reports each as `enforced`, `not_enforced` or `not_applicable`, without printing the content of any file it manages to read.

#### Scenario: Probe is skipped where isolation is provided
WHEN the probe runs and `environment_profile.detect()` reports `isolation_provided` as true
THEN the probe SHALL report status `skipped` with the detection source
AND SHALL exit `0` without attempting any read

#### Scenario: Probe reports an unenforced denial
WHEN the probe runs on a host without provided isolation and a denied path is readable
THEN the probe SHALL report that check as `not_enforced`
AND SHALL exit non-zero

#### Scenario: Probe does not leak content
WHEN a probed file is readable
THEN the probe output SHALL contain the path and the verdict only

#### Scenario: Probe targets come from the settings file
WHEN the probe runs
THEN the paths it checks SHALL be read from `sandbox.filesystem.denyRead` of the project settings, not from a second list

### Requirement: Lead Session Sandbox Guidance

The project documentation SHALL describe how to write Bash commands under the sandbox, the host prerequisites, how to run the probe and how to turn the sandbox off for one checkout.

#### Scenario: Claude-specific guidance matches the settings
WHEN `CLAUDE.md` is read
THEN it SHALL state that sandboxed commands need no allow rule
AND it SHALL name the excluded commands that still follow permission rules
AND it SHALL NOT instruct the reader to rely on an allow rule that this change removed

#### Scenario: Guide covers prerequisites and rollback
WHEN `docs/guides/lead-session-sandbox.md` is read
THEN it SHALL name the Linux prerequisites `bubblewrap` and `socat`
AND it SHALL give the probe command
AND it SHALL give the `.claude/settings.local.json` setting that disables the sandbox
