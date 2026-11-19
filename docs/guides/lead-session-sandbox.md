# Lead-Session Sandbox

The interactive Claude Code session in this repository runs its Bash commands
inside the harness's OS sandbox. Sandboxed commands are approved automatically,
so development commands no longer prompt. What a command can reach is decided
by the sandbox, not by a list of approved command prefixes.

Configuration lives in the `sandbox` block of `.claude/settings.json`. This
guide covers installing the prerequisites, checking that the sandbox is
enforced on your host, and switching it off.

## What changes

| | Before | Now |
|---|---|---|
| `pytest`, `uv run`, `grep`, `python3 …` | Approved by an allow rule, unrestricted | Sandboxed, no prompt |
| Reading `~/.ssh`, `~/.aws`, other credential directories | Possible from any approved command | Refused inside the sandbox |
| Reading a sibling checkout | Possible | Refused inside the sandbox |
| Network from Bash | Unrestricted | Package registries and the coordinator only |
| `git push`, `git fetch`, `git pull`, `gh`, `railway`, `docker` | Permission rules | Unchanged: they run outside the sandbox under the same rules |
| Migrations, secret writes, gate recording, force-push, deletion | Prompt or refused | Prompt or refused |

The allow list lost its readers, interpreters and test runners. Keeping a rule
such as `Bash(cat *)` would approve the same command when it is retried outside
the sandbox, which would undo the read restrictions.

## Limits

- The sandbox wraps Bash commands only. Hooks, MCP servers and the Read and
  Edit tools are not sandboxed; the `Read(...)` deny rules still cover the
  Read tool.
- Vendor CLIs dispatched from the lead session (`codex`, `agy`, `grok`) need
  their own credentials and hosts, so they fail inside the sandbox and fall
  back to a prompt. Sandboxing them is the work of later roadmap items.
- `excludedCommands` matches on command text. It is a convenience, not the
  boundary. The boundary is that `github.com` is not an allowed host, so a
  wrapped `git push` inside the sandbox cannot connect.
- The gate-recording ask rules match `runner.py gate-answer` and
  `cycle_state.py gate-answer` by text. A wrapper script evades them.

## Prerequisites

**macOS**: none. The harness uses the built-in Seatbelt sandbox.

**Linux and WSL2**: install `bubblewrap` and `socat`.

```bash
sudo apt-get install bubblewrap socat   # Debian, Ubuntu
sudo dnf install bubblewrap socat       # Fedora
```

Without them the harness runs commands unsandboxed and the permission rules
decide each one. Because the broad allow rules are gone, that shows up as more
prompts, not as less control.

**Cloud sessions**: nothing to do. The container is already the isolation
boundary and the harness does not wrap commands there.

## Verify on your host

Run these once per host, in a new session, by asking the agent to run each
command through its Bash tool. Running the probe from your own terminal tests
nothing, because your terminal is not sandboxed.

1. Run the probe:

   ```bash
   python3 skills/session-bootstrap/scripts/sandbox_probe.py
   ```

   The first line is the overall status; each further line is a verdict, a
   check and a path. The probe prints no file content.

   | Status or verdict | Meaning |
   |---|---|
   | `enforced` | The sandbox refused the access, or allowed the project read it should allow |
   | `not_enforced` | The access succeeded. The probe exits 1 |
   | `not_applicable` | The path does not exist on this host |
   | `skipped` | Isolation is provided by the environment (cloud); nothing was attempted |
   | `disabled` | The sandbox is switched off in settings; nothing was attempted |

2. Run `uv run --project skills pytest -q` and `git status`. Neither should
   prompt.
3. Run `alembic --help`. It should prompt: ask rules apply to sandboxed
   commands.
4. Ask the agent to run `git push origin main`. It should prompt or be
   refused. Decline it.
5. Ask the agent to run `git reset --hard HEAD`. The irreversible-command hook
   should stop it. Decline it if it prompts.

### Reading a failed check

| Result | Likely cause | What to do |
|---|---|---|
| Every check `not_enforced` | Sandbox not active: prerequisites missing, or the probe was run outside the Bash tool | Install the prerequisites; run it through the agent |
| `project_readable` is `not_enforced` | The `..` read denial is taking precedence over the `.` allowance | Remove `".."` from `sandbox.filesystem.denyRead`; sibling checkouts are then readable |
| `sibling_read` is `not_enforced`, credentials `enforced` | The relative `..` entry is not honoured | Replace `".."` with the absolute path of the directory holding your checkouts, in `.claude/settings.local.json` |
| `connect github.com:443` is `not_enforced` | Network restriction not active | Check `socat` is installed (Linux); check for a wider `allowedDomains` in user settings |
| Step 3 does not prompt | Ask rules are not applied to sandboxed commands on this harness version | Switch the sandbox off (below) and report it; migrations would otherwise run unprompted |
| A tool fails writing its cache | Cache path not in `sandbox.filesystem.allowWrite` | Add the path |

These behaviours were taken from the harness documentation and could not be
exercised where this change was written, because the cloud container has no
sandbox. Steps 1, 3 and 5 are the checks that confirm them.

## Switch it off

Create or edit `.claude/settings.local.json` in the checkout. The file is not
committed, so this affects only your machine:

```json
{
  "sandbox": {
    "enabled": false
  }
}
```

Start a new session. With the sandbox off, commands go through the permission
rules, and most development commands prompt. To get the previous promptless
behaviour back without the sandbox, add your own allow rules to the same file.

## Adding a host or a path

Network hosts are listed in `sandbox.network.allowedDomains`, and the test
`skills/tests/session-bootstrap/test_lead_session_sandbox_settings.py` holds
the same list. Add a host to both in one commit, so that widening the sandbox
is visible in review. Do not add a Git host: pushes belong to the excluded
commands, where the push rules apply.

Writable paths outside the checkout go in `sandbox.filesystem.allowWrite`.
Credential paths to hide go in `sandbox.filesystem.denyRead`; the probe picks
them up from there.
