# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-04-01

### Added
- Live service testing pipeline for end-to-end validation (`validate`)
- Session log refactored to living artifact with phase-boundary append (`session-log`)
- Interactive discovery, two-gate approval, and assumption surfacing in plan skill (`plan`)
- Notification system with Gmail relay and remote control for coordinator (`coordinator`)
- Vendor-review dispatch after iterate loop converges (`iterate`)
- SDK fallback and three-tier vendor selection for dispatch (`dispatch`)
- Unified parallel/linear skills into tiered execution model
- Parallel and multi-vendor scrub pipeline
- Automatic schema migration runner for coordinator
- OpenTelemetry observability for locks, queue, and policy
- Conversation history storage with OpenSpec changes (`session-log`)
- Automated dev loop with multi-vendor review convergence
- Multi-vendor review integration for large unreviewed PRs (`merge-prs`)
- Gemini-remote Jules dispatch and multi-group task ID extraction (`mvro`)
- Async dispatch with configurable polling transport (`mvro`)
- Multi-vendor dispatch wired into skill prompts (`mvro`)
- OpenBao secret management guide

### Changed
- Replaced codex/gemini install targets with unified `.agents/skills` (`install`)
- Simplified dispatch modes from 3 to 2 (`mvro`)
- Renamed agents to consistent local/remote convention
- Enforced TDD test-first ordering and consolidated parallel docs (`workflow`)
- Renamed archive directories to date-prefixed convention

### Fixed
- Agent discovery to agent_sessions in notification trigger migration (`coordinator`)
- Hardened repo for open-source readiness (`security`)
- Smoke tests and compose for live E2E validation (`validate`)
- Review findings for remote-control-coordinator (`coordinator`)
- Codex and Gemini agent model configurations (`agents`)
- MCP-based coordinator discovery replacing broken `claude mcp call` (`mvro`)
- Cross-vendor confirmed findings (`mvro`)
- `prompt_via_stdin` for Claude adapter (`mvro`)

## [0.1.0] - 2026-02-01

### Added
- Initial project setup with OpenSpec-driven development workflow
- Agent coordinator service with MCP and HTTP transports
- Skill framework with plan, implement, validate, and cleanup lifecycle
- Worktree isolation for parallel agent execution
- Bug scrub diagnostic skill
- Security review skill
- Architecture analysis and refresh tooling
- Parallel infrastructure (DAG scheduler, review dispatcher, consensus synthesizer)
- Coordination bridge with HTTP fallback
- Skills install script with multi-agent runtime sync
