# Change Context: cli-help-discovery

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-coordinator.1 | specs/agent-coordinator/spec.md | Agent requests capability overview — SHALL return structured overview with topic, summary, tools_count, usage hint, version | contracts/openapi/v1.yaml#/paths/~1help | --- | agent-coordinator/src/help_service.py, agent-coordinator/src/coordination_api.py, agent-coordinator/src/coordination_mcp.py | TestHelpOverview::test_returns_version, test_returns_usage_hint, test_returns_all_topics, test_each_topic_has_summary_and_count; TestHelpApi::test_get_help_overview | pass 7fbb673 |
| agent-coordinator.2 | specs/agent-coordinator/spec.md | Agent requests detailed topic help — SHALL return guide with topic, summary, description, tools, workflow, best_practices, examples, related_topics | contracts/openapi/v1.yaml#/paths/~1help~1{topic} | --- | agent-coordinator/src/help_service.py, agent-coordinator/src/coordination_api.py, agent-coordinator/src/coordination_mcp.py | TestHelpTopic::test_known_topic_returns_detail, test_detail_has_required_fields, test_tools_list_is_nonempty, test_workflow_has_ordered_steps, test_examples_have_description_and_code; TestHelpApi::test_get_help_topic | pass 7fbb673 |
| agent-coordinator.3 | specs/agent-coordinator/spec.md | Agent requests unknown topic — SHALL return error with available topic names, HTTP 404 | contracts/openapi/v1.yaml#/components/schemas/HelpTopicNotFound | --- | agent-coordinator/src/help_service.py, agent-coordinator/src/coordination_api.py, agent-coordinator/src/coordination_mcp.py | TestHelpTopic::test_unknown_topic_returns_none; TestHelpApi::test_get_help_unknown_topic | pass 7fbb673 |
| agent-coordinator.4 | specs/agent-coordinator/spec.md | Help available without authentication — SHALL NOT return 401 | contracts/openapi/v1.yaml (security: []) | --- | agent-coordinator/src/coordination_api.py | TestHelpApi::test_no_auth_required | pass 7fbb673 |
| agent-coordinator.5 | specs/agent-coordinator/spec.md | Help overview is context-efficient — SHALL be under 500 estimated tokens | --- | --- | agent-coordinator/src/help_service.py | TestHelpOverview::test_overview_is_compact | pass 7fbb673 |
| agent-coordinator.6 | specs/agent-coordinator/spec.md | Help covers all coordinator capability groups — SHALL include at minimum 15 topics | --- | --- | agent-coordinator/src/help_service.py | TestHelpOverview::test_returns_all_topics; TestHelpTopic::test_all_registered_topics_are_valid | pass 7fbb673 |
| agent-coordinator.7 | specs/agent-coordinator/spec.md | Related topics reference valid topics — every related_topics entry SHALL be a valid topic | --- | --- | agent-coordinator/src/help_service.py | TestHelpTopic::test_related_topics_exist | pass 7fbb673 |
| agent-coordinator.8 | specs/agent-coordinator/spec.md | CLI human-readable output — SHALL be formatted with aligned columns and usage hint | --- | --- | agent-coordinator/src/coordination_cli.py | TestHelpCli::test_help_overview_exit_code, test_help_topic_exit_code | pass 7fbb673 |
| agent-coordinator.9 | specs/agent-coordinator/spec.md | CLI JSON output — SHALL be valid JSON matching MCP/HTTP schema | --- | --- | agent-coordinator/src/coordination_cli.py | TestHelpCli::test_help_json_overview, test_help_json_topic | pass 7fbb673 |

## Coverage Summary

- **Requirements traced**: 9/9
- **Tests mapped**: 9 requirements have at least one test
- **Evidence collected**: 9/9 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
