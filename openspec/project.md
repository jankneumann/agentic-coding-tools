# Project Context

## Purpose
Agentic coding tools - a collection of systems for coordinating and enhancing AI coding agents. Primary components:
- **Agent Coordinator**: Multi-agent coordination system for safe collaboration on shared codebases
- **OpenSpec**: Spec-driven development workflow for AI assistants

## Tech Stack
- Python 3.11+
- FastMCP (MCP server framework)
- FastAPI (HTTP API)
- Supabase (PostgreSQL, real-time, auth)
- Docker (local development)

## Project Conventions

### Code Style
- Python: Follow PEP 8, use type hints
- Use async/await for I/O operations
- Prefer composition over inheritance
- Keep functions small and focused

### Architecture Patterns
- Layered architecture: Execution → Coordination → Trust → Governance
- Atomic database operations using PostgreSQL functions
- Hybrid read/write: Direct reads, coordinated writes
- MCP for local agents, HTTP for cloud agents

### Testing Strategy
- Unit tests for core logic (locks, memory, queue)
- Integration tests with mock Supabase
- E2E tests with multiple agent instances
- Pytest as test framework

### Git Workflow
- Main branch: `main`
- Feature branches: `feature/[description]`
- Commit messages: Conventional commits style

## Domain Context
- **Agent types**: Local (Claude Code, Codex CLI, Aider) and Cloud (Claude API, Codex Cloud)
- **Coordination primitives**: File locks, memory (episodic/working/procedural), work queue
- **Verification tiers**: Static (0) → Unit (1) → Integration (2) → System (3) → Manual (4)

## Important Constraints
- Lock TTL must be enforced to prevent deadlocks
- Memory deduplication within 1-hour window
- Task claiming must be atomic (no double-claiming)
- Cloud agents cannot use MCP (no stdio access)

## External Dependencies
- Supabase: Database, real-time subscriptions, auth
- GitHub Actions: Tier 1 verification execution
- E2B: Cloud sandbox for Tier 2 verification
- Local NTM: Integration/system test execution
