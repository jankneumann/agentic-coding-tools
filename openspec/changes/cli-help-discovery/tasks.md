# Tasks: cli-help-discovery

## Phase 1: Core Service and Tests

- [ ] 1.1 Write tests for HelpService — overview, topic detail, unknown topic, compactness, topic completeness, related topic validity
  **Spec scenarios**: agent-coordinator.1 (overview), agent-coordinator.2 (topic detail), agent-coordinator.3 (unknown topic), agent-coordinator.5 (compact), agent-coordinator.6 (all groups), agent-coordinator.7 (related valid)
  **Dependencies**: None

- [ ] 1.2 Create help_service.py — HelpTopic dataclass, static registry with 15 topics, get_help_overview(), get_help_topic(), list_topic_names()
  **Dependencies**: 1.1

## Phase 2: Transport Integration and Tests

- [ ] 2.1 Write tests for help() MCP tool — overview mode, topic mode, unknown topic error with suggestions
  **Spec scenarios**: agent-coordinator.1 (overview via MCP), agent-coordinator.2 (detail via MCP), agent-coordinator.3 (unknown via MCP)
  **Dependencies**: 1.2

- [ ] 2.2 Write tests for HTTP help endpoints — GET /help (no auth, 200), GET /help/{topic} (200), GET /help/unknown (404 with suggestions), no auth required
  **Spec scenarios**: agent-coordinator.1 (overview via HTTP), agent-coordinator.2 (detail via HTTP), agent-coordinator.3 (unknown via HTTP 404), agent-coordinator.4 (no auth)
  **Dependencies**: 1.2

- [ ] 2.3 Write tests for CLI help subcommand — exit codes, human-readable output, JSON output
  **Spec scenarios**: agent-coordinator.8 (human output), agent-coordinator.9 (JSON output)
  **Dependencies**: 1.2

- [ ] 2.4 Add help() MCP tool to coordination_mcp.py — delegates to help_service, returns overview or detail or error with available topics
  **Dependencies**: 2.1

- [ ] 2.5 Add GET /help and GET /help/{topic} to coordination_api.py — no auth, 404 for unknown topics with suggestions
  **Dependencies**: 2.2

- [ ] 2.6 Add help CLI subcommand to coordination_cli.py — cmd_help handler, argparse registration, human-readable and JSON modes
  **Dependencies**: 2.3

## Phase 3: Validation

- [ ] 3.1 Run full test suite and linter — pytest tests/test_help_service.py, ruff check on all modified files
  **Dependencies**: 2.4, 2.5, 2.6

- [ ] 3.2 Verify spec compliance — all 9 scenarios pass, help overview under 500 tokens, all 15 topics present
  **Dependencies**: 3.1
