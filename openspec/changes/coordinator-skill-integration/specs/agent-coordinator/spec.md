## ADDED Requirements

### Requirement: Skill Integration Usage Patterns

The agent-coordinator documentation SHALL include usage patterns showing how workflow skills integrate with coordinator capabilities across both local CLI and Web/Cloud execution contexts.

#### Scenario: Documentation covers runtime and transport matrix
- **WHEN** a user reads agent-coordinator documentation
- **THEN** there SHALL be a matrix describing:
  - Claude Codex, Codex, and Gemini CLI runtimes using MCP transport
  - Web/Cloud runtimes using HTTP API transport
  - standalone fallback behavior when coordinator is unavailable

#### Scenario: Documentation maps skills to capabilities
- **WHEN** a user reviews skill integration documentation
- **THEN** it SHALL identify which skills consume lock, work queue, handoff, memory, and guardrail capabilities
- **AND** explain capability-gated behavior when only a subset is available

#### Scenario: Documentation covers setup for CLI and Web/Cloud
- **WHEN** a user wants to enable coordination
- **THEN** documentation SHALL reference `/setup-coordinator`
- **AND** include manual configuration guidance for MCP (CLI) and HTTP API (Web/Cloud) paths
