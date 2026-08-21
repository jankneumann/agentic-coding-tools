---
name: setup-coordinator
description: Configure and verify coordinator access for CLI MCP and Web/Cloud HTTP runtimes
category: Coordination
tags: [coordinator, mcp, http, setup, parity]
triggers:
  - "setup coordinator"
  - "configure coordinator"
  - "coordinator setup"
  - "enable coordination"
  - "verify coordinator"
---

# Setup Coordinator

Configure coordinator access for local and cloud agent runtimes and verify
capability detection. The deterministic half of that work belongs to one tested
entrypoint; this file carries only what the entrypoint cannot — which transport
applies, when HTTP is the right answer, and what a failure means.

## Transport Model

The coordinator has two transports — **MCP (stdio)** and **HTTP** — both backed
by the same service layer and the same Postgres database. Coordination happens
at the database level, not the transport level.

| Scenario | Transport | Database |
|----------|-----------|----------|
| Local (solo or multi-agent) | MCP (stdio) to direct Postgres | Local ParadeDB |
| Cloud agents | HTTP to Coordination API | Railway Postgres |
| Cross-environment (local + cloud) | Local: HTTP bridge, Cloud: HTTP | Railway Postgres |

## When to use HTTP

- **Cloud or web agents** that cannot run an MCP stdio process at all.
- **Cross-environment coordination**, where local and cloud agents share state.
  Local agents switch to HTTP through the `coordination-bridge` sibling so the
  database is never publicly exposed.

For local-only multi-agent work MCP is sufficient — every CLI agent spawns its
own server process against the same ParadeDB. Reaching for HTTP there adds a
network hop and an API key to a path that already had neither.

## Entrypoint

Every deterministic step is a subcommand: `--profile <local|railway>` defaults
to `COORDINATOR_PROFILE` then `local`, `--root <path>` names the repository
whose settings file is read or written, and `--json` gives machine-readable
output. Resolve `<skill-base-dir>` to the directory holding this `SKILL.md`. An
external coordinator checkout is named by `COORDINATOR_DIR`; the HTTP path needs
only `COORDINATION_API_URL` and works with no checkout at all.

| Step | Subcommand |
|---|---|
| Which harnesses are installed on this host | `detect-harnesses` |
| Profile resolution and precondition report | `check` |
| Allow-list coordination tools in Claude Code | `configure --root <path>` |
| Capability-flag summary | `report` |

```bash
<skill-base-dir>/scripts/setup_coordinator.py check --profile local --root .
<skill-base-dir>/scripts/setup_coordinator.py detect-harnesses --json
<skill-base-dir>/scripts/setup_coordinator.py configure --root .
<skill-base-dir>/scripts/setup_coordinator.py report --json
```

`check` reports, per precondition, whether it is satisfied and — when it is not
— the exact operator command that satisfies it. Preconditions whose truth
cannot be established without starting a process are reported as `UNKNOWN` with
that command rather than guessed.

`detect-harnesses` reports **presence only**. A vendor shown as `ready` has its
CLI on PATH and its configuration artifact on disk; neither proves a valid or
unexpired credential. A vendor with no detectable configuration location is
reported `unknown`, never `config_missing`, because it has no login command to
recommend. A degraded run sets its flag and lists reasons, so an incomplete
report is never mistaken for a host with nothing installed.

`configure` is the only subcommand that writes anything, and it writes exactly
one file: the Claude Code permissions allow-list. The write is atomic, scoped to
`permissions.allow`, and a no-op when the wildcard is already there.

## Operator-owned steps

These are published by the coordinator checkout and stay operator-invoked. The
entrypoint reports whether each has taken effect; it never performs them.

```bash
cp "$COORDINATOR_DIR/.secrets.yaml.example" "$COORDINATOR_DIR/.secrets.yaml"
docker compose --project-directory "$COORDINATOR_DIR" -f "$COORDINATOR_DIR/docker-compose.yml" up -d
make -C "$COORDINATOR_DIR" mcp-setup
make -C "$COORDINATOR_DIR" hooks-setup
```

Fill in real values in `.secrets.yaml` first, and restart each CLI after MCP
registration. Hook installation is user-scoped and applies from any repository.

## Profile Configuration

Deployment profiles are YAML under `$COORDINATOR_DIR/profiles/`, with
inheritance and `${VAR}` interpolation from `$COORDINATOR_DIR/.secrets.yaml`;
existing environment variables win. `local.yaml` selects MCP plus local
ParadeDB, `railway.yaml` selects HTTP plus the cloud deployment, `base.yaml`
holds shared defaults. Agent identity comes from `AGENTS_YAML` when set and
otherwise `$COORDINATOR_DIR/agents.yaml` — never from the network.

## Fallback and Troubleshooting

Setup failure must not block feature work. Report the failing step and its error,
then continue standalone with `COORDINATOR_AVAILABLE=false`, transport `none`.

- API key rejected: the server's `COORDINATION_API_KEYS` must contain the key.
- SSRF filter blocking a cloud URL: add the host to `COORDINATION_ALLOWED_HOSTS`.
- Railway health check failing: `POSTGRES_DSN` must use the private network URL.
- MCP server shows disconnected: check its process, env vars, and `/health`.
- Some endpoints missing: keep `COORDINATOR_AVAILABLE=true` and set only the
  unreachable `CAN_*` flags false.
- Permission prompts on coordination tools: the allow-list write did not land.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I will just inline the JSON edit, it is three lines." | Those three lines are the four defects this entrypoint exists to remove. Run `configure`. |
| "The CLI is installed, so the vendor is authenticated." | Presence is not validity. Nothing here checks credential expiry. |
| "Detection found nothing, so this host is empty." | Only if the degradation flag is false. A degraded report asserts nothing. |
| "The roster is missing; I will assume the usual agents." | A guessed roster configures the wrong agents silently. Fix `AGENTS_YAML`. |
| "`check` reported UNKNOWN, so it is broken." | UNKNOWN means the step needs an operator command that this skill will not run for you. |

## Red Flags

- Copying a bash fragment out of this file instead of calling a subcommand.
- Reporting a vendor as ready because its binary exists, without saying that
  validity was not checked.
- Writing `.secrets.yaml`, starting a container, or registering an MCP server
  from inside this skill.
- Treating an absent vendor as a detection failure, or a degraded report as an
  empty one.
- Editing the settings file with a whole-file rewrite, a `grep` guard, or a
  path relative to the current working directory.

## Verification

1. `check` exits zero, or every unsatisfied precondition names a command.
2. `detect-harnesses --json` has `degraded: false`, or its `warnings` explain why.
3. `configure` run twice leaves the settings file byte-identical the second time.
4. `report` shows the transport you expect and `CAN_*` flags consistent with it.
5. Coordination tools no longer raise permission prompts during a workflow run.
