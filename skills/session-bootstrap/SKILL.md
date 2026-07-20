---
name: session-bootstrap
description: "Cloud environment bootstrap (setup script + verify hook) and coordinator lifecycle hooks"
category: Infrastructure
tags: [bootstrap, cloud, setup, hooks, coordinator, session]
---

# Session Bootstrap

Infrastructure skill that provides cloud environment setup and coordinator lifecycle hooks.

## Architecture

Cloud environments are ephemeral. Two scripts handle setup at different lifecycle points:

| Script | When | Runs on resume? | What it does |
|--------|------|-----------------|-------------|
| `setup-cloud.sh` | Setup Script (cloud UI) | No (new sessions only) | Heavy installs: `uv sync`, `npm install`, skills, git config |
| `bootstrap-cloud.sh` | SessionStart hook | Yes (every start/resume) | Fast verify: file-existence checks, repair only if missing |

On a resumed session, `bootstrap-cloud.sh` takes <1 second — it only checks that venvs, openspec, and skills still exist. If something was deleted mid-session, it repairs it.

### Claude Code Web

- **Setup Script**: Paste `setup-cloud.sh` into Environment Settings > Setup Script
- **SessionStart hook**: Wired in `.claude/settings.json` (committed to repo)
- Pre-installed: Python 3.x, uv, pip, npm, pnpm, docker, git, PostgreSQL 16, Redis 7.0

### Codex

- **Setup Script**: Configure in environment settings (cached up to 12h)
- **Maintenance Script**: Use `bootstrap-cloud.sh` as the maintenance script for resume
- Pre-installed: Common languages and tools via `codex-universal` image

## Shipped Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup-cloud.sh` | Full install for cloud Setup Script field |
| `scripts/bootstrap-cloud.sh` | Fast verify + repair SessionStart hook |
| `scripts/bootstrap-cloud.sh --check` | Dry-run diagnostics |
| `scripts/hooks/print_coordinator_env.py` | Print coordinator config (SessionStart) |
| `scripts/hooks/register_agent.py` | Register session, load handoff (SessionStart) |
| `scripts/hooks/report_status.py` | Report phase completion (Stop/SubagentStop) |
| `scripts/hooks/deregister_agent.py` | Deregister session, write handoff (SessionEnd) |

## Wiring for Target Repos

### 1. Cloud Setup Script (Environment Settings UI)

The Setup Script field is a text area in the cloud UI (not committed to git).
A single snippet must serve **two repo layouts**:

- **Canonical layout** (this repo): the script ships only at
  `<repo>/skills/session-bootstrap/scripts/setup-cloud.sh`. The runtime mirrors
  `.claude/skills/` and `.agents/skills/` are gitignored, so a fresh clone does
  NOT contain them — `setup-cloud.sh` rebuilds them via `skills/install.sh`.
- **Mirror layout** (consumer repos): there is no canonical `skills/`; the
  script is committed at `<repo>/.claude/skills/...` and `<repo>/.agents/skills/...`.

Paste this **one** snippet into Environment Settings > Setup Script — it works
for both layouts and both harnesses (Claude Code web and Codex):

```bash
# Find session-bootstrap's setup-cloud.sh across BOTH repo layouts:
#   canonical  <repo>/skills/session-bootstrap/scripts/setup-cloud.sh   (mirrors gitignored)
#   mirror     <repo>/.claude/skills/... or <repo>/.agents/skills/...   (mirrors committed)
# At Setup-Script time pwd is often the PARENT of the clone, so search downward.
matches="$(find "$(pwd)" -maxdepth 8 \
  -path '*/session-bootstrap/scripts/setup-cloud.sh' \
  -not -path '*/.git-worktrees/*' -not -path '*/node_modules/*' -print)"

# Reduce every match to its repo root, then dedupe: one repo may expose the
# script in 1-3 layouts, but they must all resolve to a SINGLE root.
roots="$(printf '%s\n' "$matches" | sed '/^$/d' | while IFS= read -r m; do
  r="${m%/skills/session-bootstrap/scripts/setup-cloud.sh}"   # strip common tail
  r="${r%/.claude}"; r="${r%/.agents}"                        # strip mirror dir, if any
  printf '%s\n' "$r"
done | sort -u)"

nroots="$(printf '%s\n' "$roots" | sed '/^$/d' | wc -l | tr -d '[:space:]')"
if [ "$nroots" -ne 1 ]; then
  printf 'setup-cloud.sh: expected exactly 1 repo, found %s:\n' "$nroots" >&2
  printf '%s\n' "$matches" >&2
  exit 1
fi

# One repo — prefer canonical skills/, then the Claude mirror, then the Codex mirror.
for cand in skills .claude/skills .agents/skills; do
  candidate="$roots/$cand/session-bootstrap/scripts/setup-cloud.sh"
  if [ -f "$candidate" ]; then
    echo "setup-cloud.sh: using $candidate"
    exec bash "$candidate"
  fi
done
echo "setup-cloud.sh: no runnable copy under $roots" >&2
exit 1
```

For Codex's **Maintenance Script** field (runs on resume), paste the same
snippet with every `setup-cloud.sh` replaced by `bootstrap-cloud.sh`.

**Why search-then-resolve instead of a literal path.** `CLAUDE_PROJECT_DIR`
isn't set yet at Setup-Script time (Claude Code injects it later, for hooks),
and on Claude Code web `$(pwd)` is the **parent** of the clone — typically
`/home/user`, while the repo lives at `/home/user/<reponame>/`. The older
`bash "$(pwd)/.claude/skills/session-bootstrap/scripts/setup-cloud.sh"`
therefore resolves to `/home/user/.claude/...` and fails "file not found" —
and it hard-codes the mirror layout, which the canonical repo no longer ships.

The snippet instead searches downward, collapses every hit to its **repo
root**, and:

- **Fails loudly** when the matches span more than one repo root (sibling
  repos cloned under `/home/user`, each carrying `session-bootstrap` — common
  on accounts that clone multiple projects). Failing fast is safer than
  `-print -quit`, which would silently bootstrap whichever repo `find` visited
  first — filesystem-order dependent and repo-wrong more often than you'd think.
- Within the one repo, **prefers canonical `skills/`**, then `.claude/skills/`,
  then `.agents/skills/` — so the canonical repo runs its source-of-truth copy
  (and rebuilds the gitignored mirrors via `install.sh`), while a mirror-layout
  consumer repo, which has no `skills/`, falls through to its committed
  `.claude/skills/` copy. The dedupe-by-root step keeps the canonical repo's
  local-dev checkout (where all three layouts coexist after `install.sh`) from
  tripping the multi-repo guard.

Once a copy is chosen, `setup-cloud.sh` derives its own `PROJECT_DIR` from
`BASH_SOURCE[0]` (git-root walk), so `uv sync` / `npm install` / `install.sh`
run in the right directory regardless of which layout was matched.

The wrapper intentionally avoids `mapfile` and process substitution: some cloud
runners invoke the field via `/bin/sh`, and some images still ship older Bash
where `mapfile` is unavailable. The `find` + `sort -u` + `wc -l` variant is
portable across both. Keep each `-path` argument on a single line when copying
into the cloud UI; a wrapped line that injects whitespace inside
`session-bootstrap/scripts/...` breaks the match.

### 2. `.claude/settings.json` — Hooks

**Hook path depends on layout.** The template below uses `.claude/skills/…`,
which is correct for **mirror-layout consumer repos** (mirrors are committed and
tracked, so the hook scripts survive a resume). In a **canonical-layout repo**
where `.claude/skills/` is gitignored (like this one), point the session-bootstrap
hooks at canonical `skills/session-bootstrap/scripts/…` instead. Rationale: the
runtime mirror can be wiped on an ephemeral resume, and `bootstrap-cloud.sh` is
the hook that *rebuilds* it (`verify_skills()`) — if that hook lived only in the
wiped mirror it could never run to repair itself. Canonical `skills/` is tracked,
so it always survives. (The langfuse Stop hook already follows this pattern.)
`$CLAUDE_PROJECT_DIR` is set for hooks, so no `find` is needed here — unlike the
Setup Script in §1, which runs before it is injected.

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/bootstrap-cloud.sh", "timeout": 30 },
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/print_coordinator_env.py" },
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/register_agent.py" }
      ]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/report_status.py" }
      ]
    }],
    "SubagentStop": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/report_status.py --subagent" }
      ]
    }],
    "SessionEnd": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/deregister_agent.py" }
      ]
    }]
  }
}
```

### 3. Environment Variables (cloud UI)

```
COORDINATION_API_URL=https://coord.yourdomain.com
COORDINATION_API_KEY=<your-api-key>
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `COORDINATION_API_URL` | No | Coordinator HTTP API URL (hooks skip gracefully if unset) |
| `COORDINATION_API_KEY` | No | API key for `X-API-Key` header |
| `AGENT_ID` | No | Optional legacy agent identifier; API-key identity wins when bound |
| `AGENT_TYPE` | No | Optional legacy agent type; API-key identity wins when bound |
| `CLAUDE_CODE_REMOTE` | Auto | Set to `true` by Claude Code web — can be used to skip local execution |
| `CLAUDE_ENV_FILE` | Auto | File path for persisting env vars across Bash calls |

All hook scripts are **stdlib-only** (no third-party dependencies) and **never block sessions** (all exceptions swallowed, always exit 0).

## Canonical Source

The hook scripts here are the canonical copies for distribution via `install.sh`. The `agent-coordinator/scripts/` directory contains equivalent scripts for local development and the Makefile's user-scope hook targets.
