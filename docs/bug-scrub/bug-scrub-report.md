# Bug Scrub Report

**Timestamp**: 2026-07-28T14:26:40.320045+00:00
**Sources**: pytest, ruff, mypy, openspec, architecture, security, deferred, markers
**Severity filter**: low
**Total findings**: 3813

## Summary

### By Severity

| Severity | Count |
|----------|-------|
| high | 7 |
| medium | 3123 |
| low | 683 |

### By Source

| Source | Count |
|--------|-------|
| architecture | 2878 |
| deferred:impl-findings | 2 |
| deferred:open-tasks | 887 |
| markers | 33 |
| ruff | 13 |

## Critical / High Findings

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:26
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:27
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:28
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:29
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:30
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:31
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:32
- **Detail**: Module level import not at top of file

## Medium Findings

| Source | Location | Title |
|--------|----------|-------|
| markers | skills/bug-scrub/tests/test_collect_markers.py:60 | FIXME: race condition\n") |
| markers | skills/bug-scrub/tests/test_collect_markers.py:69 | HACK: fragile workaround\n") |
| markers | skills/bug-scrub/tests/test_collect_markers.py:105 | FIXME: second item\n" |
| markers | skills/bug-scrub/tests/test_collect_markers.py:106 | HACK: third item\n" |
| markers | skills/bug-scrub/tests/test_collect_markers.py:135 | FIXME: in b\n") |
| markers | skills/bug-scrub/tests/test_collect_markers.py:292 | FIXME: no git here\n") |
| markers | skills/refresh-architecture/scripts/tests/test_comment_linker.py:39 | FIXME: broken", "language": "python", |
| markers | skills/refresh-architecture/scripts/tests/test_enrich_with_treesitter.py:91 | FIXME: broken") |
| ruff | openspec/changes/add-adaptive-model-router/contracts/generated/models.py:15 | F401: `typing.Any` imported but unused |
| ruff | scripts/ai_dora_snapshot.py:31 | F401: `collections.Counter` imported but unused |
| ruff | scripts/ai_dora_snapshot.py:36 | F401: `typing.Iterable` imported but unused |
| ruff | scripts/impl_review_driver.py:40 | F401: `consensus_synthesizer` imported but unused |
| ruff | tests/test_architecture/test_analysis.py:313 | F841: Local variable `functions_by_name` is assigned to but never used |
| ruff | tests/test_architecture/test_analysis.py:838 | F841: Local variable `report` is assigned to but never used |
| architecture | coordination_api.py:2591 | [reachability] Entrypoint 'gen_eval_list_scenarios' has no downstream dependencies |
| architecture | coordination_api.py:2914 | [reachability] Entrypoint 'get_sync_points_status' has no downstream dependencies |
| architecture | coordination_api.py:2927 | [reachability] Entrypoint 'get_active_worktrees' has no downstream dependencies |
| architecture | coordination_api.py:3305 | [reachability] Entrypoint 'live' has no downstream dependencies |
| architecture | coordination_mcp.py:3016 | [reachability] Entrypoint 'get_gen_eval_coverage' has no downstream dependencies |
| architecture | coordination_mcp.py:3048 | [reachability] Entrypoint 'get_gen_eval_report' has no downstream dependencies |
| architecture | coordination_mcp.py:3095 | [reachability] Entrypoint 'coordinate_file_edit' has no downstream dependencies |
| architecture | coordination_mcp.py:3117 | [reachability] Entrypoint 'start_work_session' has no downstream dependencies |
| architecture | coordination_api.py:1984 | [disconnected_flow] Backend route 'remove_from_merge_queue_endpoint' has no frontend callers |
| architecture | coordination_api.py:2887 | [disconnected_flow] Backend route 'help_topic' has no frontend callers |
| architecture | coordination_mcp.py:2555 | [disconnected_flow] Backend route 'get_current_locks' has no frontend callers |
| architecture | coordination_api.py:1071 | [disconnected_flow] Backend route 'get_task_endpoint' has no frontend callers |
| architecture | coordination_mcp.py:2778 | [disconnected_flow] Backend route 'get_active_features_resource' has no frontend callers |
| architecture | coordination_api.py:868 | [disconnected_flow] Backend route 'check_lock_status' has no frontend callers |
| architecture | coordination_api.py:1546 | [disconnected_flow] Backend route 'validate_cedar_policy' has no frontend callers |
| architecture | coordination_api.py:3111 | [disconnected_flow] Backend route 'kick_agent' has no frontend callers |
| architecture | coordination_mcp.py:2654 | [disconnected_flow] Backend route 'get_recent_memories' has no frontend callers |
| architecture | coordination_api.py:1519 | [disconnected_flow] Backend route 'check_policy' has no frontend callers |
| architecture | coordination_api.py:1389 | [disconnected_flow] Backend route 'query_audit' has no frontend callers |
| architecture | coordination_api.py:1577 | [disconnected_flow] Backend route 'allocate_ports' has no frontend callers |
| architecture | coordination_api.py:839 | [disconnected_flow] Backend route 'release_lock' has no frontend callers |
| architecture | coordination_mcp.py:3117 | [disconnected_flow] Backend route 'start_work_session' has no frontend callers |
| architecture | coordination_api.py:2408 | [disconnected_flow] Backend route 'test_notification' has no frontend callers |
| architecture | coordination_api.py:1245 | [disconnected_flow] Backend route 'close_issue' has no frontend callers |
| architecture | coordination_api.py:2668 | [disconnected_flow] Backend route 'gen_eval_run' has no frontend callers |
| architecture | coordination_mcp.py:2622 | [disconnected_flow] Backend route 'get_pending_work' has no frontend callers |
| architecture | coordination_api.py:3305 | [disconnected_flow] Backend route 'live' has no frontend callers |
| architecture | coordination_api.py:1196 | [disconnected_flow] Backend route 'show_issue' has no frontend callers |
| architecture | coordination_api.py:1152 | [disconnected_flow] Backend route 'list_issues' has no frontend callers |
| architecture | coordination_api.py:2972 | [disconnected_flow] Backend route 'stream_work_events' has no frontend callers |
| architecture | coordination_api.py:2714 | [disconnected_flow] Backend route 'ready_issues' has no frontend callers |
| architecture | coordination_api.py:1965 | [disconnected_flow] Backend route 'mark_merged_endpoint' has no frontend callers |
| architecture | coordination_api.py:2877 | [disconnected_flow] Backend route 'help_overview' has no frontend callers |
| architecture | coordination_api.py:1213 | [disconnected_flow] Backend route 'update_issue' has no frontend callers |
| architecture | coordination_api.py:1857 | [disconnected_flow] Backend route 'enqueue_merge_endpoint' has no frontend callers |
| architecture | coordination_api.py:3333 | [disconnected_flow] Backend route 'github_prs' has no frontend callers |
| architecture | coordination_api.py:2202 | [disconnected_flow] Backend route 'merge_train_metrics_endpoint' has no frontend callers |
| architecture | coordination_api.py:2818 | [disconnected_flow] Backend route 'check_approval_endpoint' has no frontend callers |
| architecture | coordination_api.py:1299 | [disconnected_flow] Backend route 'check_guardrails' has no frontend callers |
| architecture | coordination_api.py:1345 | [disconnected_flow] Backend route 'get_my_profile' has no frontend callers |
| architecture | coordination_api.py:2527 | [disconnected_flow] Backend route 'discovery_heartbeat' has no frontend callers |
| architecture | coordination_mcp.py:2713 | [disconnected_flow] Backend route 'get_current_profile' has no frontend callers |
| architecture | coordination_api.py:2445 | [disconnected_flow] Backend route 'notifications_status' has no frontend callers |
| architecture | coordination_api.py:2554 | [disconnected_flow] Backend route 'discovery_cleanup' has no frontend callers |
| architecture | coordination_mcp.py:2683 | [disconnected_flow] Backend route 'get_guardrail_patterns' has no frontend callers |
| architecture | coordination_api.py:1118 | [disconnected_flow] Backend route 'create_issue' has no frontend callers |
| architecture | coordination_mcp.py:2749 | [disconnected_flow] Backend route 'get_recent_audit' has no frontend callers |
| architecture | coordination_mcp.py:3048 | [disconnected_flow] Backend route 'get_gen_eval_report' has no frontend callers |
| architecture | coordination_api.py:1004 | [disconnected_flow] Backend route 'complete_work' has no frontend callers |
| architecture | coordination_api.py:1686 | [disconnected_flow] Backend route 'list_policy_versions_endpoint' has no frontend callers |
| architecture | coordination_api.py:2591 | [disconnected_flow] Backend route 'gen_eval_list_scenarios' has no frontend callers |
| architecture | coordination_api.py:802 | [disconnected_flow] Backend route 'acquire_lock' has no frontend callers |
| architecture | coordination_api.py:925 | [disconnected_flow] Backend route 'query_memories' has no frontend callers |
| architecture | coordination_api.py:1803 | [disconnected_flow] Backend route 'list_active_features_endpoint' has no frontend callers |
| architecture | coordination_mcp.py:2581 | [disconnected_flow] Backend route 'get_recent_handoffs' has no frontend callers |
| architecture | coordination_api.py:2779 | [disconnected_flow] Backend route 'request_approval_endpoint' has no frontend callers |
| architecture | coordination_api.py:1036 | [disconnected_flow] Backend route 'submit_work' has no frontend callers |
| architecture | coordination_api.py:3023 | [disconnected_flow] Backend route 'patch_issue_labels' has no frontend callers |
| architecture | coordination_api.py:2061 | [disconnected_flow] Backend route 'eject_from_train_endpoint' has no frontend callers |
| architecture | coordination_api.py:1833 | [disconnected_flow] Backend route 'analyze_feature_conflicts_endpoint' has no frontend callers |
| architecture | coordination_api.py:1940 | [disconnected_flow] Backend route 'run_pre_merge_checks_endpoint' has no frontend callers |
| architecture | coordination_api.py:2740 | [disconnected_flow] Backend route 'request_permission_endpoint' has no frontend callers |
| architecture | coordination_api.py:1449 | [disconnected_flow] Backend route 'write_handoff' has no frontend callers |
| architecture | coordination_api.py:2914 | [disconnected_flow] Backend route 'get_sync_points_status' has no frontend callers |
| architecture | coordination_api.py:2619 | [disconnected_flow] Backend route 'gen_eval_validate' has no frontend callers |
| architecture | coordination_api.py:1277 | [disconnected_flow] Backend route 'comment_issue' has no frontend callers |
| architecture | coordination_api.py:1375 | [disconnected_flow] Backend route 'get_agent_dispatch_configs' has no frontend callers |
| architecture | coordination_api.py:2939 | [disconnected_flow] Backend route 'mint_events_token' has no frontend callers |
| architecture | coordination_api.py:2179 | [disconnected_flow] Backend route 'affected_tests_endpoint' has no frontend callers |
| architecture | coordination_api.py:2462 | [disconnected_flow] Backend route 'discovery_register' has no frontend callers |
| architecture | coordination_api.py:1718 | [disconnected_flow] Backend route 'register_feature_endpoint' has no frontend callers |
| architecture | coordination_api.py:1659 | [disconnected_flow] Backend route 'decide_approval' has no frontend callers |
| architecture | coordination_api.py:1779 | [disconnected_flow] Backend route 'get_feature_endpoint' has no frontend callers |
| architecture | coordination_api.py:1648 | [disconnected_flow] Backend route 'list_pending_approvals' has no frontend callers |
| architecture | coordination_api.py:1890 | [disconnected_flow] Backend route 'get_merge_queue_endpoint' has no frontend callers |
| architecture | coordination_api.py:3075 | [disconnected_flow] Backend route 'force_release_lock' has no frontend callers |
| architecture | coordination_api.py:1599 | [disconnected_flow] Backend route 'release_ports' has no frontend callers |
| architecture | coordination_api.py:2493 | [disconnected_flow] Backend route 'discovery_agents' has no frontend callers |
| architecture | coordination_api.py:3456 | [disconnected_flow] Backend route 'search_code_endpoint' has no frontend callers |
| architecture | coordination_api.py:2007 | [disconnected_flow] Backend route 'compose_train_endpoint' has no frontend callers |
| architecture | coordination_api.py:3269 | [disconnected_flow] Backend route 'post_kanban_audit' has no frontend callers |
| architecture | coordination_api.py:3322 | [disconnected_flow] Backend route 'health' has no frontend callers |
| architecture | coordination_api.py:1478 | [disconnected_flow] Backend route 'read_handoff' has no frontend callers |
| architecture | coordination_api.py:3232 | [disconnected_flow] Backend route 'put_saved_view' has no frontend callers |
| architecture | coordination_api.py:3373 | [disconnected_flow] Backend route 'openspec_proposals' has no frontend callers |
| architecture | coordination_mcp.py:3095 | [disconnected_flow] Backend route 'coordinate_file_edit' has no frontend callers |
| architecture | coordination_api.py:893 | [disconnected_flow] Backend route 'store_memory' has no frontend callers |
| architecture | coordination_api.py:1608 | [disconnected_flow] Backend route 'port_status' has no frontend callers |
| architecture | coordination_mcp.py:3016 | [disconnected_flow] Backend route 'get_gen_eval_coverage' has no frontend callers |
| architecture | coordination_api.py:1752 | [disconnected_flow] Backend route 'deregister_feature_endpoint' has no frontend callers |
| architecture | coordination_api.py:1699 | [disconnected_flow] Backend route 'rollback_policy_endpoint' has no frontend callers |
| architecture | coordination_api.py:2927 | [disconnected_flow] Backend route 'get_active_worktrees' has no frontend callers |
| architecture | coordination_api.py:2698 | [disconnected_flow] Backend route 'search_issues' has no frontend callers |
| architecture | coordination_api.py:970 | [disconnected_flow] Backend route 'claim_work' has no frontend callers |
| architecture | coordination_api.py:2315 | [disconnected_flow] Backend route 'report_status' has no frontend callers |
| architecture | coordination_mcp.py:2810 | [disconnected_flow] Backend route 'get_merge_queue_resource' has no frontend callers |
| architecture | coordination_api.py:2110 | [disconnected_flow] Backend route 'get_train_status_endpoint' has no frontend callers |
| architecture | coordination_api.py:1179 | [disconnected_flow] Backend route 'blocked_issues_early' has no frontend callers |
| architecture | coordination_api.py:3419 | [disconnected_flow] Backend route 'code_search_status_endpoint' has no frontend callers |
| architecture | coordination_api.py:2140 | [disconnected_flow] Backend route 'report_spec_result_endpoint' has no frontend callers |
| architecture | coordination_api.py:3310 | [disconnected_flow] Backend route 'ready' has no frontend callers |
| architecture | coordination_api.py:1919 | [disconnected_flow] Backend route 'get_next_merge_endpoint' has no frontend callers |
| architecture | coordination_api.py:2643 | [disconnected_flow] Backend route 'gen_eval_create' has no frontend callers |
| architecture | coordination_api.py:2238 | [disconnected_flow] Backend route 'resolve_archetype_for_phase_endpoint' has no frontend callers |
| architecture | agents_config.py:413 | [test_coverage] Function 'PollConfig' has no corresponding test references |
| architecture | agents_config.py:431 | [test_coverage] Function 'ModeConfig' has no corresponding test references |
| architecture | agents_config.py:440 | [test_coverage] Function 'CliConfig' has no corresponding test references |
| architecture | agents_config.py:460 | [test_coverage] Function 'SdkConfig' has no corresponding test references |
| architecture | agents_config.py:477 | [test_coverage] Function 'AgentEntry' has no corresponding test references |
| architecture | agents_config.py:500 | [test_coverage] Function 'EscalationConfig' has no corresponding test references |
| architecture | agents_config.py:514 | [test_coverage] Function 'ArchetypeConfig' has no corresponding test references |
| architecture | agents_config.py:529 | [test_coverage] Function 'PhaseMappingEntry' has no corresponding test references |
| architecture | agents_config.py:543 | [test_coverage] Function 'ModelSpec' has no corresponding test references |
| architecture | agents_config.py:557 | [test_coverage] Function 'ResolvedArchetype' has no corresponding test references |
| architecture | agents_config.py:573 | [test_coverage] Function 'ProviderModelMappingError' has no corresponding test references |
| architecture | approval.py:15 | [test_coverage] Function 'ApprovalRequest' has no corresponding test references |
| architecture | approval.py:32 | [test_coverage] Function 'ApprovalService' has no corresponding test references |
| architecture | audit.py:18 | [test_coverage] Function 'AuditEntry' has no corresponding test references |
| architecture | audit.py:56 | [test_coverage] Function 'AuditResult' has no corresponding test references |
| architecture | audit.py:72 | [test_coverage] Function 'AuditService' has no corresponding test references |
| architecture | audit.py:206 | [test_coverage] Function 'AuditTimer' has no corresponding test references |
| architecture | audit_triage.py:52 | [test_coverage] Function 'AuditTriageConfig' has no corresponding test references |
| architecture | audit_triage.py:67 | [test_coverage] Function 'AuditTriageBuffer' has no corresponding test references |
| architecture | cloudflare_access.py:56 | [test_coverage] Function 'CloudflareAccessError' has no corresponding test references |
| architecture | cloudflare_access.py:60 | [test_coverage] Function 'CloudflareAccessVerifier' has no corresponding test references |
| architecture | cloudflare_access.py:125 | [test_coverage] Function 'CloudflareAccessMiddleware' has no corresponding test references |
| architecture | code_search.py:64 | [test_coverage] Function 'CodeSearchError' has no corresponding test references |
| architecture | code_search.py:71 | [test_coverage] Function 'CodeSearchForbiddenError' has no corresponding test references |
| architecture | code_search.py:76 | [test_coverage] Function 'CodeSearchState' has no corresponding test references |
| architecture | code_search.py:85 | [test_coverage] Function '_ClosedModel' has no corresponding test references |
| architecture | code_search.py:89 | [test_coverage] Function 'SearchNamespace' has no corresponding test references |
| architecture | code_search.py:100 | [test_coverage] Function 'ExplicitScope' has no corresponding test references |
| architecture | code_search.py:113 | [test_coverage] Function 'WorkPackageScope' has no corresponding test references |
| architecture | code_search.py:130 | [test_coverage] Function 'CodeSearchRequest' has no corresponding test references |
| architecture | code_search.py:172 | [test_coverage] Function 'RequestedIdentity' has no corresponding test references |
| architecture | code_search.py:179 | [test_coverage] Function 'IndexProvenance' has no corresponding test references |
| architecture | code_search.py:192 | [test_coverage] Function 'ScopeDisposition' has no corresponding test references |
| architecture | code_search.py:198 | [test_coverage] Function 'CodeSearchHit' has no corresponding test references |
| architecture | code_search.py:211 | [test_coverage] Function 'Fallback' has no corresponding test references |
| architecture | code_search.py:217 | [test_coverage] Function 'CodeSearchResponse' has no corresponding test references |
| architecture | code_search.py:261 | [test_coverage] Function 'CodeSearchService' has no corresponding test references |
| architecture | code_search_authorization.py:18 | [test_coverage] Function 'ScopeAuthorizationError' has no corresponding test references |
| architecture | code_search_authorization.py:22 | [test_coverage] Function 'ScopeForbiddenError' has no corresponding test references |
| architecture | code_search_authorization.py:26 | [test_coverage] Function 'ScopeRejectedError' has no corresponding test references |
| architecture | code_search_authorization.py:31 | [test_coverage] Function 'ExplicitScopeRequest' has no corresponding test references |
| architecture | code_search_authorization.py:41 | [test_coverage] Function 'WorkPackageScopeRequest' has no corresponding test references |
| architecture | code_search_authorization.py:57 | [test_coverage] Function 'PrincipalCodeSearchGrant' has no corresponding test references |
| architecture | code_search_authorization.py:83 | [test_coverage] Function 'WorkPackageScopeRecord' has no corresponding test references |
| architecture | code_search_authorization.py:104 | [test_coverage] Function 'WorkPackageScopeResolver' has no corresponding test references |
| architecture | code_search_authorization.py:118 | [test_coverage] Function 'EffectiveCodeSearchScope' has no corresponding test references |
| architecture | code_search_authorization.py:391 | [test_coverage] Function '_GlobToken' has no corresponding test references |
| architecture | code_search_runtime.py:57 | [test_coverage] Function 'CodeSearchOverloadedError' has no corresponding test references |
| architecture | code_search_runtime.py:67 | [test_coverage] Function 'CodeSearchStatus' has no corresponding test references |
| architecture | code_search_runtime.py:104 | [test_coverage] Function 'CodeSearchRuntimeConfig' has no corresponding test references |
| architecture | code_search_runtime.py:147 | [test_coverage] Function '_Cache' has no corresponding test references |
| architecture | code_search_runtime.py:157 | [test_coverage] Function 'CodeSearchRuntime' has no corresponding test references |
| architecture | config.py:50 | [test_coverage] Function 'SupabaseConfig' has no corresponding test references |
| architecture | config.py:75 | [test_coverage] Function 'AgentConfig' has no corresponding test references |
| architecture | config.py:99 | [test_coverage] Function 'LockConfig' has no corresponding test references |
| architecture | config.py:113 | [test_coverage] Function 'PostgresConfig' has no corresponding test references |
| architecture | config.py:130 | [test_coverage] Function 'DatabaseConfig' has no corresponding test references |
| architecture | config.py:145 | [test_coverage] Function 'GuardrailsConfig' has no corresponding test references |
| architecture | config.py:165 | [test_coverage] Function 'ProfilesConfig' has no corresponding test references |
| architecture | config.py:189 | [test_coverage] Function 'AuditConfig' has no corresponding test references |
| architecture | config.py:204 | [test_coverage] Function 'NetworkPolicyConfig' has no corresponding test references |
| architecture | config.py:217 | [test_coverage] Function 'PolicyEngineConfig' has no corresponding test references |
| architecture | config.py:241 | [test_coverage] Function 'OpenBaoConfig' has no corresponding test references |
| architecture | config.py:323 | [test_coverage] Function 'ObservabilityConfig' has no corresponding test references |
| architecture | config.py:340 | [test_coverage] Function 'LangfuseConfig' has no corresponding test references |
| architecture | config.py:374 | [test_coverage] Function 'PortAllocatorConfig' has no corresponding test references |
| architecture | config.py:393 | [test_coverage] Function 'ApiConfig' has no corresponding test references |
| architecture | config.py:448 | [test_coverage] Function 'CloudflareAccessConfig' has no corresponding test references |
| architecture | config.py:502 | [test_coverage] Function 'ApprovalConfig' has no corresponding test references |
| architecture | config.py:525 | [test_coverage] Function 'PolicySyncConfig' has no corresponding test references |
| architecture | config.py:547 | [test_coverage] Function 'RiskScoringConfig' has no corresponding test references |
| architecture | config.py:574 | [test_coverage] Function 'SessionGrantsConfig' has no corresponding test references |
| architecture | config.py:628 | [test_coverage] Function 'Config' has no corresponding test references |
| architecture | coordination_api.py:72 | [test_coverage] Function '_CodeSearchProblemError' has no corresponding test references |
| architecture | coordination_api.py:86 | [test_coverage] Function 'LockAcquireRequest' has no corresponding test references |
| architecture | coordination_api.py:95 | [test_coverage] Function 'LockReleaseRequest' has no corresponding test references |
| architecture | coordination_api.py:100 | [test_coverage] Function 'MemoryStoreRequest' has no corresponding test references |
| architecture | coordination_api.py:111 | [test_coverage] Function 'MemoryQueryRequest' has no corresponding test references |
| architecture | coordination_api.py:118 | [test_coverage] Function 'WorkClaimRequest' has no corresponding test references |
| architecture | coordination_api.py:124 | [test_coverage] Function 'WorkCompleteRequest' has no corresponding test references |
| architecture | coordination_api.py:132 | [test_coverage] Function 'WorkSubmitRequest' has no corresponding test references |
| architecture | coordination_api.py:141 | [test_coverage] Function 'WorkGetTaskRequest' has no corresponding test references |
| architecture | coordination_api.py:145 | [test_coverage] Function 'IssueCreateRequest' has no corresponding test references |
| architecture | coordination_api.py:156 | [test_coverage] Function 'IssueListRequest' has no corresponding test references |
| architecture | coordination_api.py:165 | [test_coverage] Function 'IssueUpdateRequest' has no corresponding test references |
| architecture | coordination_api.py:176 | [test_coverage] Function 'IssueCloseRequest' has no corresponding test references |
| architecture | coordination_api.py:182 | [test_coverage] Function 'IssueCommentRequest' has no corresponding test references |
| architecture | coordination_api.py:187 | [test_coverage] Function 'GuardrailsCheckRequest' has no corresponding test references |
| architecture | coordination_api.py:192 | [test_coverage] Function 'AuditQueryParams' has no corresponding test references |
| architecture | coordination_api.py:198 | [test_coverage] Function 'HandoffWriteRequest' has no corresponding test references |
| architecture | coordination_api.py:210 | [test_coverage] Function 'HandoffReadRequest' has no corresponding test references |
| architecture | coordination_api.py:215 | [test_coverage] Function 'PolicyCheckRequest' has no corresponding test references |
| architecture | coordination_api.py:223 | [test_coverage] Function 'PolicyValidateRequest' has no corresponding test references |
| architecture | coordination_api.py:227 | [test_coverage] Function 'PortAllocateRequest' has no corresponding test references |
| architecture | coordination_api.py:231 | [test_coverage] Function 'PortReleaseRequest' has no corresponding test references |
| architecture | coordination_api.py:235 | [test_coverage] Function 'ApprovalDecisionRequest' has no corresponding test references |
| architecture | coordination_api.py:241 | [test_coverage] Function 'PolicyRollbackRequest' has no corresponding test references |
| architecture | coordination_api.py:245 | [test_coverage] Function 'FeatureRegisterRequest' has no corresponding test references |
| architecture | coordination_api.py:255 | [test_coverage] Function 'FeatureDeregisterRequest' has no corresponding test references |
| architecture | coordination_api.py:260 | [test_coverage] Function 'FeatureConflictsRequest' has no corresponding test references |
| architecture | coordination_api.py:265 | [test_coverage] Function 'StatusReportRequest' has no corresponding test references |
| architecture | coordination_api.py:289 | [test_coverage] Function 'ResolveForPhaseRequest' has no corresponding test references |
| architecture | coordination_api.py:311 | [test_coverage] Function 'MergeQueueEnqueueRequest' has no corresponding test references |
| architecture | coordination_api.py:316 | [test_coverage] Function 'DiscoveryRegisterRequest' has no corresponding test references |
| architecture | coordination_api.py:326 | [test_coverage] Function 'DiscoveryHeartbeatRequest' has no corresponding test references |
| architecture | coordination_api.py:332 | [test_coverage] Function 'DiscoveryCleanupRequest' has no corresponding test references |
| architecture | coordination_api.py:338 | [test_coverage] Function 'GenEvalValidateRequest' has no corresponding test references |
| architecture | coordination_api.py:342 | [test_coverage] Function 'GenEvalCreateRequest' has no corresponding test references |
| architecture | coordination_api.py:350 | [test_coverage] Function 'GenEvalRunRequest' has no corresponding test references |
| architecture | coordination_api.py:356 | [test_coverage] Function 'IssueSearchRequest' has no corresponding test references |
| architecture | coordination_api.py:363 | [test_coverage] Function 'IssueReadyRequest' has no corresponding test references |
| architecture | coordination_api.py:370 | [test_coverage] Function 'PermissionRequestRequest' has no corresponding test references |
| architecture | coordination_api.py:377 | [test_coverage] Function 'ApprovalSubmitRequest' has no corresponding test references |
| architecture | coordination_api.py:386 | [test_coverage] Function 'MergeTrainEjectRequest' has no corresponding test references |
| architecture | coordination_api.py:391 | [test_coverage] Function 'MergeTrainReportResultRequest' has no corresponding test references |
| architecture | coordination_api.py:397 | [test_coverage] Function 'AffectedTestsRequest' has no corresponding test references |
| architecture | coordination_api.py:403 | [test_coverage] Function 'EventsAuthRequest' has no corresponding test references |
| architecture | coordination_api.py:408 | [test_coverage] Function 'PatchLabelsRequest' has no corresponding test references |
| architecture | coordination_api.py:413 | [test_coverage] Function 'KickAgentRequest' has no corresponding test references |
| architecture | coordination_api.py:427 | [test_coverage] Function 'SavedViewRequest' has no corresponding test references |
| architecture | coordination_api.py:431 | [test_coverage] Function 'KanbanAuditRequest' has no corresponding test references |
| architecture | db.py:25 | [test_coverage] Function 'DatabaseClient' has no corresponding test references |
| architecture | db.py:73 | [test_coverage] Function 'SupabaseClient' has no corresponding test references |
| architecture | db_postgres.py:78 | [test_coverage] Function 'DirectPostgresClient' has no corresponding test references |
| architecture | discovery.py:20 | [test_coverage] Function 'AgentInfo' has no corresponding test references |
| architecture | discovery.py:61 | [test_coverage] Function 'RegisterResult' has no corresponding test references |
| architecture | discovery.py:76 | [test_coverage] Function 'DiscoverResult' has no corresponding test references |
| architecture | discovery.py:88 | [test_coverage] Function 'HeartbeatResult' has no corresponding test references |
| architecture | discovery.py:105 | [test_coverage] Function 'CleanupResult' has no corresponding test references |
| architecture | discovery.py:121 | [test_coverage] Function 'DiscoveryService' has no corresponding test references |
| architecture | event_bus.py:37 | [test_coverage] Function 'CoordinatorEvent' has no corresponding test references |
| architecture | event_bus.py:110 | [test_coverage] Function 'EventBusService' has no corresponding test references |
| architecture | feature_flags.py:61 | [test_coverage] Function 'FlagsConfigError' has no corresponding test references |
| architecture | feature_flags.py:69 | [test_coverage] Function 'InvalidFlagNameError' has no corresponding test references |
| architecture | feature_flags.py:79 | [test_coverage] Function 'Flag' has no corresponding test references |
| architecture | feature_flags.py:153 | [test_coverage] Function 'FeatureFlagService' has no corresponding test references |
| architecture | feature_registry.py:26 | [test_coverage] Function 'Feasibility' has no corresponding test references |
| architecture | feature_registry.py:35 | [test_coverage] Function 'Feature' has no corresponding test references |
| architecture | feature_registry.py:75 | [test_coverage] Function 'RegisterResult' has no corresponding test references |
| architecture | feature_registry.py:94 | [test_coverage] Function 'DeregisterResult' has no corresponding test references |
| architecture | feature_registry.py:113 | [test_coverage] Function 'ConflictReport' has no corresponding test references |
| architecture | feature_registry.py:124 | [test_coverage] Function 'FeatureRegistryService' has no corresponding test references |
| architecture | git_adapter.py:51 | [test_coverage] Function 'InvalidRefNameError' has no corresponding test references |
| architecture | git_adapter.py:55 | [test_coverage] Function 'GitVersionError' has no corresponding test references |
| architecture | git_adapter.py:65 | [test_coverage] Function 'MergeTreeResult' has no corresponding test references |
| architecture | git_adapter.py:79 | [test_coverage] Function 'FastForwardResult' has no corresponding test references |
| architecture | git_adapter.py:88 | [test_coverage] Function 'ChangedFiles' has no corresponding test references |
| architecture | git_adapter.py:102 | [test_coverage] Function 'GitAdapter' has no corresponding test references |
| architecture | git_adapter.py:176 | [test_coverage] Function 'SubprocessGitAdapter' has no corresponding test references |
| architecture | github_coordination.py:30 | [test_coverage] Function 'BranchInfo' has no corresponding test references |
| architecture | github_coordination.py:61 | [test_coverage] Function 'LabelLock' has no corresponding test references |
| architecture | github_coordination.py:69 | [test_coverage] Function 'WebhookSyncResult' has no corresponding test references |
| architecture | github_coordination.py:89 | [test_coverage] Function 'GitHubCoordinationService' has no corresponding test references |
| architecture | guardrails.py:146 | [test_coverage] Function 'GuardrailPattern' has no corresponding test references |
| architecture | guardrails.py:167 | [test_coverage] Function 'GuardrailViolation' has no corresponding test references |
| architecture | guardrails.py:190 | [test_coverage] Function 'GuardrailResult' has no corresponding test references |
| architecture | guardrails.py:268 | [test_coverage] Function 'GuardrailsService' has no corresponding test references |
| architecture | handoffs.py:22 | [test_coverage] Function 'HandoffDocument' has no corresponding test references |
| architecture | handoffs.py:59 | [test_coverage] Function 'WriteHandoffResult' has no corresponding test references |
| architecture | handoffs.py:80 | [test_coverage] Function 'ReadHandoffResult' has no corresponding test references |
| architecture | handoffs.py:95 | [test_coverage] Function 'HandoffService' has no corresponding test references |
| architecture | help_service.py:20 | [test_coverage] Function 'HelpTopic' has no corresponding test references |
| architecture | http_proxy.py:92 | [test_coverage] Function 'HttpProxyConfig' has no corresponding test references |
| architecture | issue_service.py:47 | [test_coverage] Function 'Issue' has no corresponding test references |
| architecture | issue_service.py:154 | [test_coverage] Function 'Comment' has no corresponding test references |
| architecture | issue_service.py:186 | [test_coverage] Function 'IssueService' has no corresponding test references |
| architecture | kanban_viz_files.py:107 | [test_coverage] Function 'SchemaValidationError' has no corresponding test references |
| architecture | langfuse_middleware.py:29 | [test_coverage] Function 'LangfuseTracingMiddleware' has no corresponding test references |
| architecture | locks.py:89 | [test_coverage] Function 'Lock' has no corresponding test references |
| architecture | locks.py:119 | [test_coverage] Function 'LockResult' has no corresponding test references |
| architecture | locks.py:149 | [test_coverage] Function 'LockService' has no corresponding test references |
| architecture | memory.py:36 | [test_coverage] Function 'EpisodicMemory' has no corresponding test references |
| architecture | memory.py:72 | [test_coverage] Function 'MemoryResult' has no corresponding test references |
| architecture | memory.py:91 | [test_coverage] Function 'RecallResult' has no corresponding test references |
| architecture | memory.py:105 | [test_coverage] Function 'MemoryService' has no corresponding test references |
| architecture | merge_queue.py:37 | [test_coverage] Function 'MergeStatus' has no corresponding test references |
| architecture | merge_queue.py:49 | [test_coverage] Function 'PreMergeCheckResult' has no corresponding test references |
| architecture | merge_queue.py:60 | [test_coverage] Function 'MergeQueueEntry' has no corresponding test references |
| architecture | merge_queue.py:88 | [test_coverage] Function 'MergeQueueService' has no corresponding test references |
| architecture | merge_train.py:69 | [test_coverage] Function 'TrainAuthorizationError' has no corresponding test references |
| architecture | merge_train.py:77 | [test_coverage] Function 'TrainDeadlockError' has no corresponding test references |
| architecture | merge_train.py:92 | [test_coverage] Function 'PartitionResult' has no corresponding test references |
| architecture | merge_train.py:622 | [test_coverage] Function 'EjectResult' has no corresponding test references |
| architecture | merge_train.py:851 | [test_coverage] Function '_MergeNode' has no corresponding test references |
| architecture | merge_train.py:868 | [test_coverage] Function 'WaveMergeResult' has no corresponding test references |
| architecture | merge_train.py:1121 | [test_coverage] Function 'CrashRecoveryResult' has no corresponding test references |
| architecture | merge_train_service.py:115 | [test_coverage] Function 'MergeTrainService' has no corresponding test references |
| architecture | merge_train_service.py:419 | [test_coverage] Function 'MergeTrainSweeper' has no corresponding test references |
| architecture | merge_train_types.py:58 | [test_coverage] Function 'MergeTrainStatus' has no corresponding test references |
| architecture | merge_train_types.py:98 | [test_coverage] Function 'TrainEntry' has no corresponding test references |
| architecture | merge_train_types.py:151 | [test_coverage] Function 'TrainPartition' has no corresponding test references |
| architecture | merge_train_types.py:169 | [test_coverage] Function 'CrossPartitionEntry' has no corresponding test references |
| architecture | merge_train_types.py:183 | [test_coverage] Function 'TrainComposition' has no corresponding test references |
| architecture | merge_watcher.py:24 | [test_coverage] Function 'MergeWatcher' has no corresponding test references |
| architecture | model_routing/exploration.py:25 | [test_coverage] Function 'ExplorationBudget' has no corresponding test references |
| architecture | model_routing/exploration.py:42 | [test_coverage] Function 'Selection' has no corresponding test references |
| architecture | model_routing/feedback.py:52 | [test_coverage] Function 'FeedbackObservation' has no corresponding test references |
| architecture | model_routing/feedback.py:65 | [test_coverage] Function 'PosteriorEstimate' has no corresponding test references |
| architecture | model_routing/resolver.py:39 | [test_coverage] Function 'Weights' has no corresponding test references |
| architecture | model_routing/resolver.py:59 | [test_coverage] Function 'Posterior' has no corresponding test references |
| architecture | model_routing/resolver.py:70 | [test_coverage] Function 'CandidateInput' has no corresponding test references |
| architecture | model_routing/resolver.py:93 | [test_coverage] Function 'ScoredCandidate' has no corresponding test references |
| architecture | network_policies.py:15 | [test_coverage] Function 'AccessDecision' has no corresponding test references |
| architecture | network_policies.py:33 | [test_coverage] Function 'NetworkPolicyService' has no corresponding test references |
| architecture | notifications/base.py:11 | [test_coverage] Function 'NotificationChannel' has no corresponding test references |
| architecture | notifications/base.py:29 | [test_coverage] Function 'GmailChannelFake' has no corresponding test references |
| architecture | notifications/gmail.py:46 | [test_coverage] Function 'GmailChannel' has no corresponding test references |
| architecture | notifications/notifier.py:30 | [test_coverage] Function 'NotifierService' has no corresponding test references |
| architecture | notifications/telegram.py:20 | [test_coverage] Function 'TelegramChannel' has no corresponding test references |
| architecture | notifications/webhook.py:18 | [test_coverage] Function 'WebhookChannel' has no corresponding test references |
| architecture | openspec_sources.py:38 | [test_coverage] Function 'SourceDescriptor' has no corresponding test references |
| architecture | openspec_sources.py:47 | [test_coverage] Function 'ParseWarning' has no corresponding test references |
| architecture | openspec_sources.py:55 | [test_coverage] Function 'LocalSourceCache' has no corresponding test references |
| architecture | policy_engine.py:84 | [test_coverage] Function 'PolicyDecision' has no corresponding test references |
| architecture | policy_engine.py:102 | [test_coverage] Function 'ValidationResult' has no corresponding test references |
| architecture | policy_engine.py:109 | [test_coverage] Function 'NativePolicyEngine' has no corresponding test references |
| architecture | policy_engine.py:455 | [test_coverage] Function 'CedarPolicyEngine' has no corresponding test references |
| architecture | policy_sync.py:17 | [test_coverage] Function 'PolicySyncService' has no corresponding test references |
| architecture | policy_sync.py:37 | [test_coverage] Function 'PgListenNotifyPolicySyncService' has no corresponding test references |
| architecture | port_allocator.py:24 | [test_coverage] Function 'PortAllocation' has no corresponding test references |
| architecture | port_allocator.py:52 | [test_coverage] Function 'PortAllocatorService' has no corresponding test references |
| architecture | profiles.py:20 | [test_coverage] Function 'AgentProfile' has no corresponding test references |
| architecture | profiles.py:53 | [test_coverage] Function 'ProfileResult' has no corresponding test references |
| architecture | profiles.py:77 | [test_coverage] Function 'OperationCheck' has no corresponding test references |
| architecture | profiles.py:91 | [test_coverage] Function 'ProfilesService' has no corresponding test references |
| architecture | refresh_rpc_client.py:59 | [test_coverage] Function 'RefreshClientUnavailable' has no corresponding test references |
| architecture | refresh_rpc_client.py:78 | [test_coverage] Function '_Runner' has no corresponding test references |
| architecture | refresh_rpc_client.py:124 | [test_coverage] Function 'RefreshRpcClient' has no corresponding test references |
| architecture | risk_scorer.py:33 | [test_coverage] Function 'RiskScore' has no corresponding test references |
| architecture | risk_scorer.py:41 | [test_coverage] Function 'RiskScorer' has no corresponding test references |
| architecture | session_grants.py:14 | [test_coverage] Function 'PermissionGrant' has no corresponding test references |
| architecture | session_grants.py:27 | [test_coverage] Function 'SessionGrantService' has no corresponding test references |
| architecture | sse_log_redaction.py:31 | [test_coverage] Function '_TokenRedactionFilter' has no corresponding test references |
| architecture | teams.py:48 | [test_coverage] Function 'AgentDefinition' has no corresponding test references |
| architecture | teams.py:58 | [test_coverage] Function 'TeamsConfig' has no corresponding test references |
| architecture | telemetry.py:217 | [test_coverage] Function '_NoOpSpan' has no corresponding test references |
| architecture | watchdog.py:31 | [test_coverage] Function 'WatchdogService' has no corresponding test references |
| architecture | work_queue.py:68 | [test_coverage] Function 'Task' has no corresponding test references |
| architecture | work_queue.py:120 | [test_coverage] Function 'ClaimResult' has no corresponding test references |
| architecture | work_queue.py:157 | [test_coverage] Function 'CompleteResult' has no corresponding test references |
| architecture | work_queue.py:180 | [test_coverage] Function 'SubmitResult' has no corresponding test references |
| architecture | work_queue.py:198 | [test_coverage] Function 'WorkQueueService' has no corresponding test references |
| architecture | agents_config.py:576 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | agents_config.py:597 | [test_coverage] Function '_default_agents_path' has no corresponding test references |
| architecture | agents_config.py:601 | [test_coverage] Function '_default_secrets_path' has no corresponding test references |
| architecture | agents_config.py:605 | [test_coverage] Function 'load_agents_config' has no corresponding test references |
| architecture | agents_config.py:658 | [test_coverage] Function '_parse_mode' has no corresponding test references |
| architecture | agents_config.py:732 | [test_coverage] Function '_resolve_api_key_from_openbao' has no corresponding test references |
| architecture | agents_config.py:783 | [test_coverage] Function 'get_api_key_identities' has no corresponding test references |
| architecture | agents_config.py:840 | [test_coverage] Function 'get_mcp_env' has no corresponding test references |
| architecture | agents_config.py:878 | [test_coverage] Function 'get_agents_config' has no corresponding test references |
| architecture | agents_config.py:894 | [test_coverage] Function 'get_agent_config' has no corresponding test references |
| architecture | agents_config.py:902 | [test_coverage] Function 'reset_agents_config' has no corresponding test references |
| architecture | agents_config.py:912 | [test_coverage] Function 'get_dispatch_configs' has no corresponding test references |
| architecture | agents_config.py:979 | [test_coverage] Function 'get_agent_isolation' has no corresponding test references |
| architecture | agents_config.py:995 | [test_coverage] Function '_default_archetypes_path' has no corresponding test references |
| architecture | agents_config.py:999 | [test_coverage] Function 'load_archetypes_config' has no corresponding test references |
| architecture | agents_config.py:1083 | [test_coverage] Function 'get_archetype' has no corresponding test references |
| architecture | agents_config.py:1097 | [test_coverage] Function 'get_phase_mapping' has no corresponding test references |
| architecture | agents_config.py:1109 | [test_coverage] Function 'reset_archetypes_config' has no corresponding test references |
| architecture | agents_config.py:1117 | [test_coverage] Function '_normalize_provider_model_map' has no corresponding test references |
| architecture | agents_config.py:1144 | [test_coverage] Function 'get_provider_model_map' has no corresponding test references |
| architecture | agents_config.py:1151 | [test_coverage] Function '_tier_entry_to_spec' has no corresponding test references |
| architecture | agents_config.py:1166 | [test_coverage] Function 'resolve_provider_model_spec' has no corresponding test references |
| architecture | agents_config.py:1219 | [test_coverage] Function 'resolve_provider_model' has no corresponding test references |
| architecture | agents_config.py:1239 | [test_coverage] Function 'compose_prompt' has no corresponding test references |
| architecture | agents_config.py:1255 | [test_coverage] Function '_unique_dir_prefixes' has no corresponding test references |
| architecture | agents_config.py:1274 | [test_coverage] Function 'resolve_model' has no corresponding test references |
| architecture | agents_config.py:1313 | [test_coverage] Function '_resolve_model_spec' has no corresponding test references |
| architecture | agents_config.py:1322 | [test_coverage] Function '_finalize' has no corresponding test references |
| architecture | agents_config.py:1379 | [test_coverage] Function 'resolve_archetype_for_phase' has no corresponding test references |
| architecture | approval.py:35 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | approval.py:39 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | approval.py:44 | [test_coverage] Function 'submit_request' has no corresponding test references |
| architecture | approval.py:89 | [test_coverage] Function 'check_request' has no corresponding test references |
| architecture | approval.py:99 | [test_coverage] Function 'decide_request' has no corresponding test references |
| architecture | approval.py:137 | [test_coverage] Function 'expire_stale_requests' has no corresponding test references |
| architecture | approval.py:154 | [test_coverage] Function 'list_pending' has no corresponding test references |
| architecture | approval.py:166 | [test_coverage] Function '_row_to_request' has no corresponding test references |
| architecture | approval.py:186 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | approval.py:199 | [test_coverage] Function 'get_approval_service' has no corresponding test references |
| architecture | approval.py:207 | [test_coverage] Function 'reset_approval_service' has no corresponding test references |
| architecture | audit.py:34 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | audit.py:64 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | audit.py:75 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | audit.py:79 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | audit.py:84 | [test_coverage] Function 'log_operation' has no corresponding test references |
| architecture | audit.py:151 | [test_coverage] Function '_insert_audit_entry' has no corresponding test references |
| architecture | audit.py:159 | [test_coverage] Function 'query' has no corresponding test references |
| architecture | audit.py:201 | [test_coverage] Function 'timed' has no corresponding test references |
| architecture | audit.py:209 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | audit.py:214 | [test_coverage] Function '__aenter__' has no corresponding test references |
| architecture | audit.py:218 | [test_coverage] Function '__aexit__' has no corresponding test references |
| architecture | audit.py:237 | [test_coverage] Function 'get_audit_service' has no corresponding test references |
| architecture | audit_triage.py:75 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | audit_triage.py:79 | [test_coverage] Function 'push' has no corresponding test references |
| architecture | audit_triage.py:91 | [test_coverage] Function 'drain_all' has no corresponding test references |
| architecture | audit_triage.py:106 | [test_coverage] Function 'validate_finding' has no corresponding test references |
| architecture | audit_triage.py:123 | [test_coverage] Function 'load_prompt' has no corresponding test references |
| architecture | audit_triage.py:140 | [test_coverage] Function 'drain_and_classify' has no corresponding test references |
| architecture | audit_triage.py:259 | [test_coverage] Function 'get_triage_buffer' has no corresponding test references |
| architecture | audit_triage.py:267 | [test_coverage] Function 'reset_triage_buffer' has no corresponding test references |
| architecture | axi_output.py:25 | [test_coverage] Function 'probe_truncation' has no corresponding test references |
| architecture | axi_output.py:39 | [test_coverage] Function 'truncation_hint' has no corresponding test references |
| architecture | axi_output.py:44 | [test_coverage] Function 'list_envelope' has no corresponding test references |
| architecture | cloudflare_access.py:68 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | cloudflare_access.py:91 | [test_coverage] Function '_signing_key' has no corresponding test references |
| architecture | cloudflare_access.py:106 | [test_coverage] Function 'verify' has no corresponding test references |
| architecture | cloudflare_access.py:134 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | cloudflare_access.py:146 | [test_coverage] Function '_is_exempt' has no corresponding test references |
| architecture | cloudflare_access.py:156 | [test_coverage] Function '__call__' has no corresponding test references |
| architecture | cloudflare_access.py:185 | [test_coverage] Function '_deny' has no corresponding test references |
| architecture | cloudflare_access.py:192 | [test_coverage] Function 'install_cloudflare_access' has no corresponding test references |
| architecture | code_search.py:53 | [test_coverage] Function 'code_search_enabled' has no corresponding test references |
| architecture | code_search.py:94 | [test_coverage] Function 'validate_main_key' has no corresponding test references |
| architecture | code_search.py:107 | [test_coverage] Function 'validate_patterns' has no corresponding test references |
| architecture | code_search.py:121 | [test_coverage] Function 'validate_reference' has no corresponding test references |
| architecture | code_search.py:144 | [test_coverage] Function 'validate_languages' has no corresponding test references |
| architecture | code_search.py:158 | [test_coverage] Function 'validate_paths' has no corresponding test references |
| architecture | code_search.py:166 | [test_coverage] Function 'require_non_main_index' has no corresponding test references |
| architecture | code_search.py:227 | [test_coverage] Function 'validate_state_invariants' has no corresponding test references |
| architecture | code_search.py:253 | [test_coverage] Function 'to_dict' has no corresponding test references |
| architecture | code_search.py:264 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | code_search.py:282 | [test_coverage] Function 'search' has no corresponding test references |
| architecture | code_search.py:451 | [test_coverage] Function '_select_index' has no corresponding test references |
| architecture | code_search.py:463 | [test_coverage] Function 'metrics_snapshot' has no corresponding test references |
| architecture | code_search.py:468 | [test_coverage] Function '_observe_response' has no corresponding test references |
| architecture | code_search.py:482 | [test_coverage] Function '_observe' has no corresponding test references |
| architecture | code_search.py:517 | [test_coverage] Function '_authorization_scope' has no corresponding test references |
| architecture | code_search.py:532 | [test_coverage] Function '_index_provenance' has no corresponding test references |
| architecture | code_search.py:550 | [test_coverage] Function '_hit' has no corresponding test references |
| architecture | code_search.py:564 | [test_coverage] Function '_non_ready_response' has no corresponding test references |
| architecture | code_search.py:585 | [test_coverage] Function 'get_code_search_service' has no corresponding test references |
| architecture | code_search.py:591 | [test_coverage] Function 'init_code_search_service' has no corresponding test references |
| architecture | code_search_authorization.py:35 | [test_coverage] Function '__post_init__' has no corresponding test references |
| architecture | code_search_authorization.py:46 | [test_coverage] Function '__post_init__' has no corresponding test references |
| architecture | code_search_authorization.py:67 | [test_coverage] Function '__post_init__' has no corresponding test references |
| architecture | code_search_authorization.py:93 | [test_coverage] Function '__post_init__' has no corresponding test references |
| architecture | code_search_authorization.py:105 | [test_coverage] Function '__call__' has no corresponding test references |
| architecture | code_search_authorization.py:128 | [test_coverage] Function 'allow_path_regexes' has no corresponding test references |
| architecture | code_search_authorization.py:136 | [test_coverage] Function 'deny_path_regexes' has no corresponding test references |
| architecture | code_search_authorization.py:140 | [test_coverage] Function 'path_regexes' has no corresponding test references |
| architecture | code_search_authorization.py:143 | [test_coverage] Function 'allows' has no corresponding test references |
| architecture | code_search_authorization.py:153 | [test_coverage] Function 'authorize_code_search_scope' has no corresponding test references |
| architecture | code_search_authorization.py:237 | [test_coverage] Function 'validate_safe_glob' has no corresponding test references |
| architecture | code_search_authorization.py:245 | [test_coverage] Function 'glob_to_postgres_regex' has no corresponding test references |
| architecture | code_search_authorization.py:280 | [test_coverage] Function '_matches_any' has no corresponding test references |
| architecture | code_search_authorization.py:284 | [test_coverage] Function '_regex_union' has no corresponding test references |
| architecture | code_search_authorization.py:291 | [test_coverage] Function '_validate_patterns' has no corresponding test references |
| architecture | code_search_authorization.py:297 | [test_coverage] Function '_canonical_patterns' has no corresponding test references |
| architecture | code_search_authorization.py:306 | [test_coverage] Function '_deduplicated' has no corresponding test references |
| architecture | code_search_authorization.py:310 | [test_coverage] Function '_require_nonempty_effective_scope' has no corresponding test references |
| architecture | code_search_authorization.py:381 | [test_coverage] Function '_require_compilable_scope_patterns' has no corresponding test references |
| architecture | code_search_authorization.py:400 | [test_coverage] Function '_compile_glob_layer' has no corresponding test references |
| architecture | code_search_authorization.py:404 | [test_coverage] Function '_compile_glob' has no corresponding test references |
| architecture | code_search_authorization.py:443 | [test_coverage] Function '_glob_layer_start' has no corresponding test references |
| architecture | code_search_authorization.py:450 | [test_coverage] Function '_glob_layer_closure' has no corresponding test references |
| architecture | code_search_authorization.py:467 | [test_coverage] Function '_glob_layer_step' has no corresponding test references |
| architecture | code_search_authorization.py:493 | [test_coverage] Function '_glob_layer_accepts' has no corresponding test references |
| architecture | code_search_authorization.py:497 | [test_coverage] Function '_scope_alphabet' has no corresponding test references |
| architecture | code_search_authorization.py:516 | [test_coverage] Function '_next_segment_state' has no corresponding test references |
| architecture | code_search_authorization.py:528 | [test_coverage] Function '_valid_reference' has no corresponding test references |
| architecture | code_search_authorization.py:534 | [test_coverage] Function '_is_normalized_relative' has no corresponding test references |
| architecture | code_search_runtime.py:50 | [test_coverage] Function 'code_search_enabled' has no corresponding test references |
| architecture | code_search_runtime.py:63 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | code_search_runtime.py:78 | [test_coverage] Function 'validate_truth_table' has no corresponding test references |
| architecture | code_search_runtime.py:99 | [test_coverage] Function 'to_dict' has no corresponding test references |
| architecture | code_search_runtime.py:115 | [test_coverage] Function '__post_init__' has no corresponding test references |
| architecture | code_search_runtime.py:129 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | code_search_runtime.py:152 | [test_coverage] Function 'clear' has no corresponding test references |
| architecture | code_search_runtime.py:160 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | code_search_runtime.py:176 | [test_coverage] Function 'create' has no corresponding test references |
| architecture | code_search_runtime.py:198 | [test_coverage] Function 'provider_factory' has no corresponding test references |
| architecture | code_search_runtime.py:242 | [test_coverage] Function 'embed_one' has no corresponding test references |
| architecture | code_search_runtime.py:277 | [test_coverage] Function 'state_counts' has no corresponding test references |
| architecture | code_search_runtime.py:282 | [test_coverage] Function 'status_snapshot' has no corresponding test references |
| architecture | code_search_runtime.py:291 | [test_coverage] Function 'status' has no corresponding test references |
| architecture | code_search_runtime.py:299 | [test_coverage] Function '_status_after_lock' has no corresponding test references |
| architecture | code_search_runtime.py:352 | [test_coverage] Function '_finish_initialization' has no corresponding test references |
| architecture | code_search_runtime.py:361 | [test_coverage] Function '_record_status' has no corresponding test references |
| architecture | code_search_runtime.py:391 | [test_coverage] Function 'search' has no corresponding test references |
| architecture | code_search_runtime.py:432 | [test_coverage] Function 'invalidate' has no corresponding test references |
| architecture | code_search_runtime.py:438 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | code_search_runtime.py:461 | [test_coverage] Function '_provider_ready' has no corresponding test references |
| architecture | code_search_runtime.py:484 | [test_coverage] Function '_cache_failure' has no corresponding test references |
| architecture | code_search_runtime.py:493 | [test_coverage] Function '_close_pool' has no corresponding test references |
| architecture | code_search_runtime.py:505 | [test_coverage] Function '_close_provider' has no corresponding test references |
| architecture | code_search_runtime.py:524 | [test_coverage] Function '_assert_owner' has no corresponding test references |
| architecture | code_search_runtime.py:532 | [test_coverage] Function 'start_code_search_runtime' has no corresponding test references |
| architecture | code_search_runtime.py:541 | [test_coverage] Function 'stop_code_search_runtime' has no corresponding test references |
| architecture | code_search_runtime.py:548 | [test_coverage] Function 'get_code_search_runtime' has no corresponding test references |
| architecture | code_search_runtime.py:554 | [test_coverage] Function 'set_code_search_runtime' has no corresponding test references |
| architecture | code_search_runtime.py:561 | [test_coverage] Function 'principal_id_for_api_key' has no corresponding test references |
| architecture | code_search_runtime.py:574 | [test_coverage] Function '_status' has no corresponding test references |
| architecture | code_search_runtime.py:583 | [test_coverage] Function '_duration_bucket' has no corresponding test references |
| architecture | code_search_runtime.py:593 | [test_coverage] Function '_sanitized_unavailable' has no corresponding test references |
| architecture | code_search_runtime.py:634 | [test_coverage] Function '_pool_from_env' has no corresponding test references |
| architecture | code_search_runtime.py:644 | [test_coverage] Function '_provider_from_env' has no corresponding test references |
| architecture | code_search_runtime.py:670 | [test_coverage] Function '_grant_resolver_from_env' has no corresponding test references |
| architecture | code_search_runtime.py:677 | [test_coverage] Function 'resolve' has no corresponding test references |
| architecture | code_search_runtime.py:688 | [test_coverage] Function '_float_env' has no corresponding test references |
| architecture | code_search_runtime.py:692 | [test_coverage] Function '_int_env' has no corresponding test references |
| architecture | config.py:58 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:83 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:106 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:121 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:137 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:152 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:173 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:196 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:210 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:226 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:263 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:274 | [test_coverage] Function 'is_enabled' has no corresponding test references |
| architecture | config.py:278 | [test_coverage] Function 'create_client' has no corresponding test references |
| architecture | config.py:331 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:360 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:383 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:405 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:468 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:591 | [test_coverage] Function '_default_workdir_root' has no corresponding test references |
| architecture | config.py:606 | [test_coverage] Function 'resolve_workdir_path' has no corresponding test references |
| architecture | config.py:667 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:723 | [test_coverage] Function 'get_config' has no corresponding test references |
| architecture | config.py:731 | [test_coverage] Function 'reset_config' has no corresponding test references |
| architecture | coordination_api.py:75 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | coordination_api.py:441 | [test_coverage] Function '_extract_api_key' has no corresponding test references |
| architecture | coordination_api.py:458 | [test_coverage] Function '_principal_for_api_key' has no corresponding test references |
| architecture | coordination_api.py:471 | [test_coverage] Function 'verify_api_key' has no corresponding test references |
| architecture | coordination_api.py:493 | [test_coverage] Function 'optional_api_key' has no corresponding test references |
| architecture | coordination_api.py:505 | [test_coverage] Function 'resolve_identity' has no corresponding test references |
| architecture | coordination_api.py:535 | [test_coverage] Function 'authorize_operation' has no corresponding test references |
| architecture | coordination_api.py:556 | [test_coverage] Function 'resolve_trust_level' has no corresponding test references |
| architecture | coordination_api.py:577 | [test_coverage] Function 'create_coordination_api' has no corresponding test references |
| architecture | coordination_api.py:599 | [test_coverage] Function 'lifespan' has no corresponding test references |
| architecture | coordination_api.py:724 | [test_coverage] Function 'code_search_problem_handler' has no corresponding test references |
| architecture | coordination_api.py:736 | [test_coverage] Function 'request_validation_handler' has no corresponding test references |
| architecture | coordination_api.py:802 | [test_coverage] Function 'acquire_lock' has no corresponding test references |
| architecture | coordination_api.py:839 | [test_coverage] Function 'release_lock' has no corresponding test references |
| architecture | coordination_api.py:868 | [test_coverage] Function 'check_lock_status' has no corresponding test references |
| architecture | coordination_api.py:893 | [test_coverage] Function 'store_memory' has no corresponding test references |
| architecture | coordination_api.py:925 | [test_coverage] Function 'query_memories' has no corresponding test references |
| architecture | coordination_api.py:970 | [test_coverage] Function 'claim_work' has no corresponding test references |
| architecture | coordination_api.py:1004 | [test_coverage] Function 'complete_work' has no corresponding test references |
| architecture | coordination_api.py:1036 | [test_coverage] Function 'submit_work' has no corresponding test references |
| architecture | coordination_api.py:1071 | [test_coverage] Function 'get_task_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1118 | [test_coverage] Function 'create_issue' has no corresponding test references |
| architecture | coordination_api.py:1152 | [test_coverage] Function 'list_issues' has no corresponding test references |
| architecture | coordination_api.py:1179 | [test_coverage] Function 'blocked_issues_early' has no corresponding test references |
| architecture | coordination_api.py:1196 | [test_coverage] Function 'show_issue' has no corresponding test references |
| architecture | coordination_api.py:1213 | [test_coverage] Function 'update_issue' has no corresponding test references |
| architecture | coordination_api.py:1245 | [test_coverage] Function 'close_issue' has no corresponding test references |
| architecture | coordination_api.py:1277 | [test_coverage] Function 'comment_issue' has no corresponding test references |
| architecture | coordination_api.py:1299 | [test_coverage] Function 'check_guardrails' has no corresponding test references |
| architecture | coordination_api.py:1345 | [test_coverage] Function 'get_my_profile' has no corresponding test references |
| architecture | coordination_api.py:1375 | [test_coverage] Function 'get_agent_dispatch_configs' has no corresponding test references |
| architecture | coordination_api.py:1389 | [test_coverage] Function 'query_audit' has no corresponding test references |
| architecture | coordination_api.py:1449 | [test_coverage] Function 'write_handoff' has no corresponding test references |
| architecture | coordination_api.py:1478 | [test_coverage] Function 'read_handoff' has no corresponding test references |
| architecture | coordination_api.py:1519 | [test_coverage] Function 'check_policy' has no corresponding test references |
| architecture | coordination_api.py:1546 | [test_coverage] Function 'validate_cedar_policy' has no corresponding test references |
| architecture | coordination_api.py:1577 | [test_coverage] Function 'allocate_ports' has no corresponding test references |
| architecture | coordination_api.py:1599 | [test_coverage] Function 'release_ports' has no corresponding test references |
| architecture | coordination_api.py:1608 | [test_coverage] Function 'port_status' has no corresponding test references |
| architecture | coordination_api.py:1630 | [test_coverage] Function '_approval_to_dict' has no corresponding test references |
| architecture | coordination_api.py:1648 | [test_coverage] Function 'list_pending_approvals' has no corresponding test references |
| architecture | coordination_api.py:1659 | [test_coverage] Function 'decide_approval' has no corresponding test references |
| architecture | coordination_api.py:1686 | [test_coverage] Function 'list_policy_versions_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1699 | [test_coverage] Function 'rollback_policy_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1718 | [test_coverage] Function 'register_feature_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1752 | [test_coverage] Function 'deregister_feature_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1779 | [test_coverage] Function 'get_feature_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1803 | [test_coverage] Function 'list_active_features_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1833 | [test_coverage] Function 'analyze_feature_conflicts_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1857 | [test_coverage] Function 'enqueue_merge_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1890 | [test_coverage] Function 'get_merge_queue_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1919 | [test_coverage] Function 'get_next_merge_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1940 | [test_coverage] Function 'run_pre_merge_checks_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1965 | [test_coverage] Function 'mark_merged_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1984 | [test_coverage] Function 'remove_from_merge_queue_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2007 | [test_coverage] Function 'compose_train_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2061 | [test_coverage] Function 'eject_from_train_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2110 | [test_coverage] Function 'get_train_status_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2140 | [test_coverage] Function 'report_spec_result_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2179 | [test_coverage] Function 'affected_tests_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2202 | [test_coverage] Function 'merge_train_metrics_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2238 | [test_coverage] Function 'resolve_archetype_for_phase_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2315 | [test_coverage] Function 'report_status' has no corresponding test references |
| architecture | coordination_api.py:2408 | [test_coverage] Function 'test_notification' has no corresponding test references |
| architecture | coordination_api.py:2445 | [test_coverage] Function 'notifications_status' has no corresponding test references |
| architecture | coordination_api.py:2462 | [test_coverage] Function 'discovery_register' has no corresponding test references |
| architecture | coordination_api.py:2493 | [test_coverage] Function 'discovery_agents' has no corresponding test references |
| architecture | coordination_api.py:2527 | [test_coverage] Function 'discovery_heartbeat' has no corresponding test references |
| architecture | coordination_api.py:2554 | [test_coverage] Function 'discovery_cleanup' has no corresponding test references |
| architecture | coordination_api.py:2591 | [test_coverage] Function 'gen_eval_list_scenarios' has no corresponding test references |
| architecture | coordination_api.py:2619 | [test_coverage] Function 'gen_eval_validate' has no corresponding test references |
| architecture | coordination_api.py:2643 | [test_coverage] Function 'gen_eval_create' has no corresponding test references |
| architecture | coordination_api.py:2668 | [test_coverage] Function 'gen_eval_run' has no corresponding test references |
| architecture | coordination_api.py:2698 | [test_coverage] Function 'search_issues' has no corresponding test references |
| architecture | coordination_api.py:2714 | [test_coverage] Function 'ready_issues' has no corresponding test references |
| architecture | coordination_api.py:2740 | [test_coverage] Function 'request_permission_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2779 | [test_coverage] Function 'request_approval_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2818 | [test_coverage] Function 'check_approval_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2849 | [test_coverage] Function '_database_health' has no corresponding test references |
| architecture | coordination_api.py:2877 | [test_coverage] Function 'help_overview' has no corresponding test references |
| architecture | coordination_api.py:2887 | [test_coverage] Function 'help_topic' has no corresponding test references |
| architecture | coordination_api.py:2914 | [test_coverage] Function 'get_sync_points_status' has no corresponding test references |
| architecture | coordination_api.py:2927 | [test_coverage] Function 'get_active_worktrees' has no corresponding test references |
| architecture | coordination_api.py:2939 | [test_coverage] Function 'mint_events_token' has no corresponding test references |
| architecture | coordination_api.py:2972 | [test_coverage] Function 'stream_work_events' has no corresponding test references |
| architecture | coordination_api.py:3023 | [test_coverage] Function 'patch_issue_labels' has no corresponding test references |
| architecture | coordination_api.py:3075 | [test_coverage] Function 'force_release_lock' has no corresponding test references |
| architecture | coordination_api.py:3111 | [test_coverage] Function 'kick_agent' has no corresponding test references |
| architecture | coordination_api.py:3232 | [test_coverage] Function 'put_saved_view' has no corresponding test references |
| architecture | coordination_api.py:3269 | [test_coverage] Function 'post_kanban_audit' has no corresponding test references |
| architecture | coordination_api.py:3305 | [test_coverage] Function 'live' has no corresponding test references |
| architecture | coordination_api.py:3310 | [test_coverage] Function 'ready' has no corresponding test references |
| architecture | coordination_api.py:3322 | [test_coverage] Function 'health' has no corresponding test references |
| architecture | coordination_api.py:3333 | [test_coverage] Function 'github_prs' has no corresponding test references |
| architecture | coordination_api.py:3373 | [test_coverage] Function 'openspec_proposals' has no corresponding test references |
| architecture | coordination_api.py:3419 | [test_coverage] Function 'code_search_status_endpoint' has no corresponding test references |
| architecture | coordination_api.py:3439 | [test_coverage] Function 'verify_code_search_principal' has no corresponding test references |
| architecture | coordination_api.py:3456 | [test_coverage] Function 'search_code_endpoint' has no corresponding test references |
| architecture | coordination_api.py:3494 | [test_coverage] Function 'main' has no corresponding test references |
| architecture | coordination_cli.py:24 | [test_coverage] Function '_run' has no corresponding test references |
| architecture | coordination_cli.py:29 | [test_coverage] Function '_output' has no corresponding test references |
| architecture | coordination_cli.py:48 | [test_coverage] Function '_print_dict' has no corresponding test references |
| architecture | coordination_cli.py:72 | [test_coverage] Function '_error' has no corresponding test references |
| architecture | coordination_cli.py:78 | [test_coverage] Function '_emit_list' has no corresponding test references |
| architecture | coordination_cli.py:135 | [test_coverage] Function 'cmd_health' has no corresponding test references |
| architecture | coordination_cli.py:162 | [test_coverage] Function 'cmd_feature_register' has no corresponding test references |
| architecture | coordination_cli.py:185 | [test_coverage] Function 'cmd_feature_deregister' has no corresponding test references |
| architecture | coordination_cli.py:202 | [test_coverage] Function 'cmd_feature_show' has no corresponding test references |
| architecture | coordination_cli.py:223 | [test_coverage] Function 'cmd_feature_list' has no corresponding test references |
| architecture | coordination_cli.py:250 | [test_coverage] Function 'cmd_feature_conflicts' has no corresponding test references |
| architecture | coordination_cli.py:271 | [test_coverage] Function 'cmd_mq_enqueue' has no corresponding test references |
| architecture | coordination_cli.py:290 | [test_coverage] Function 'cmd_mq_status' has no corresponding test references |
| architecture | coordination_cli.py:316 | [test_coverage] Function 'cmd_mq_next' has no corresponding test references |
| architecture | coordination_cli.py:333 | [test_coverage] Function 'cmd_mq_check' has no corresponding test references |
| architecture | coordination_cli.py:348 | [test_coverage] Function 'cmd_mq_merged' has no corresponding test references |
| architecture | coordination_cli.py:357 | [test_coverage] Function 'cmd_mq_remove' has no corresponding test references |
| architecture | coordination_cli.py:369 | [test_coverage] Function 'cmd_lock_acquire' has no corresponding test references |
| architecture | coordination_cli.py:390 | [test_coverage] Function 'cmd_lock_release' has no corresponding test references |
| architecture | coordination_cli.py:406 | [test_coverage] Function 'cmd_lock_status' has no corresponding test references |
| architecture | coordination_cli.py:435 | [test_coverage] Function 'cmd_work_submit' has no corresponding test references |
| architecture | coordination_cli.py:452 | [test_coverage] Function 'cmd_work_claim' has no corresponding test references |
| architecture | coordination_cli.py:472 | [test_coverage] Function 'cmd_work_complete' has no corresponding test references |
| architecture | coordination_cli.py:492 | [test_coverage] Function 'cmd_work_get' has no corresponding test references |
| architecture | coordination_cli.py:515 | [test_coverage] Function 'cmd_handoff_write' has no corresponding test references |
| architecture | coordination_cli.py:531 | [test_coverage] Function 'cmd_handoff_read' has no corresponding test references |
| architecture | coordination_cli.py:564 | [test_coverage] Function 'cmd_memory_store' has no corresponding test references |
| architecture | coordination_cli.py:582 | [test_coverage] Function 'cmd_memory_query' has no corresponding test references |
| architecture | coordination_cli.py:614 | [test_coverage] Function 'cmd_guardrails_check' has no corresponding test references |
| architecture | coordination_cli.py:635 | [test_coverage] Function 'cmd_audit_query' has no corresponding test references |
| architecture | coordination_cli.py:668 | [test_coverage] Function 'cmd_help' has no corresponding test references |
| architecture | coordination_cli.py:745 | [test_coverage] Function 'build_parser' has no corresponding test references |
| architecture | coordination_cli.py:931 | [test_coverage] Function 'main' has no corresponding test references |
| architecture | coordination_mcp.py:59 | [test_coverage] Function '_mcp_lifespan' has no corresponding test references |
| architecture | coordination_mcp.py:97 | [test_coverage] Function 'get_agent_id' has no corresponding test references |
| architecture | coordination_mcp.py:102 | [test_coverage] Function 'get_agent_type' has no corresponding test references |
| architecture | coordination_mcp.py:113 | [test_coverage] Function 'acquire_lock' has no corresponding test references |
| architecture | coordination_mcp.py:167 | [test_coverage] Function 'release_lock' has no corresponding test references |
| architecture | coordination_mcp.py:195 | [test_coverage] Function 'check_locks' has no corresponding test references |
| architecture | coordination_mcp.py:231 | [test_coverage] Function 'get_work' has no corresponding test references |
| architecture | coordination_mcp.py:274 | [test_coverage] Function 'complete_work' has no corresponding test references |
| architecture | coordination_mcp.py:322 | [test_coverage] Function 'submit_work' has no corresponding test references |
| architecture | coordination_mcp.py:387 | [test_coverage] Function 'get_task' has no corresponding test references |
| architecture | coordination_mcp.py:443 | [test_coverage] Function 'issue_create' has no corresponding test references |
| architecture | coordination_mcp.py:521 | [test_coverage] Function 'issue_list' has no corresponding test references |
| architecture | coordination_mcp.py:578 | [test_coverage] Function 'issue_show' has no corresponding test references |
| architecture | coordination_mcp.py:605 | [test_coverage] Function 'issue_update' has no corresponding test references |
| architecture | coordination_mcp.py:673 | [test_coverage] Function 'issue_close' has no corresponding test references |
| architecture | coordination_mcp.py:726 | [test_coverage] Function 'issue_comment' has no corresponding test references |
| architecture | coordination_mcp.py:761 | [test_coverage] Function 'issue_ready' has no corresponding test references |
| architecture | coordination_mcp.py:803 | [test_coverage] Function 'issue_blocked' has no corresponding test references |
| architecture | coordination_mcp.py:831 | [test_coverage] Function 'issue_search' has no corresponding test references |
| architecture | coordination_mcp.py:874 | [test_coverage] Function 'write_handoff' has no corresponding test references |
| architecture | coordination_mcp.py:937 | [test_coverage] Function 'read_handoff' has no corresponding test references |
| architecture | coordination_mcp.py:1002 | [test_coverage] Function 'register_session' has no corresponding test references |
| architecture | coordination_mcp.py:1048 | [test_coverage] Function 'discover_agents' has no corresponding test references |
| architecture | coordination_mcp.py:1101 | [test_coverage] Function 'heartbeat' has no corresponding test references |
| architecture | coordination_mcp.py:1125 | [test_coverage] Function 'cleanup_dead_agents' has no corresponding test references |
| architecture | coordination_mcp.py:1164 | [test_coverage] Function 'remember' has no corresponding test references |
| architecture | coordination_mcp.py:1219 | [test_coverage] Function 'recall' has no corresponding test references |
| architecture | coordination_mcp.py:1279 | [test_coverage] Function 'check_guardrails' has no corresponding test references |
| architecture | coordination_mcp.py:1350 | [test_coverage] Function 'get_my_profile' has no corresponding test references |
| architecture | coordination_mcp.py:1387 | [test_coverage] Function 'get_agent_dispatch_configs' has no corresponding test references |
| architecture | coordination_mcp.py:1411 | [test_coverage] Function 'query_audit' has no corresponding test references |
| architecture | coordination_mcp.py:1466 | [test_coverage] Function 'check_policy' has no corresponding test references |
| architecture | coordination_mcp.py:1513 | [test_coverage] Function 'validate_cedar_policy' has no corresponding test references |
| architecture | coordination_mcp.py:1557 | [test_coverage] Function 'allocate_ports' has no corresponding test references |
| architecture | coordination_mcp.py:1606 | [test_coverage] Function 'release_ports' has no corresponding test references |
| architecture | coordination_mcp.py:1633 | [test_coverage] Function 'ports_status' has no corresponding test references |
| architecture | coordination_mcp.py:1678 | [test_coverage] Function 'request_approval' has no corresponding test references |
| architecture | coordination_mcp.py:1710 | [test_coverage] Function 'check_approval' has no corresponding test references |
| architecture | coordination_mcp.py:1736 | [test_coverage] Function 'list_policy_versions' has no corresponding test references |
| architecture | coordination_mcp.py:1756 | [test_coverage] Function 'request_permission' has no corresponding test references |
| architecture | coordination_mcp.py:1789 | [test_coverage] Function 'register_feature' has no corresponding test references |
| architecture | coordination_mcp.py:1845 | [test_coverage] Function 'deregister_feature' has no corresponding test references |
| architecture | coordination_mcp.py:1880 | [test_coverage] Function 'get_feature' has no corresponding test references |
| architecture | coordination_mcp.py:1914 | [test_coverage] Function 'list_active_features' has no corresponding test references |
| architecture | coordination_mcp.py:1944 | [test_coverage] Function 'analyze_feature_conflicts' has no corresponding test references |
| architecture | coordination_mcp.py:1985 | [test_coverage] Function 'enqueue_merge' has no corresponding test references |
| architecture | coordination_mcp.py:2026 | [test_coverage] Function 'get_merge_queue' has no corresponding test references |
| architecture | coordination_mcp.py:2055 | [test_coverage] Function 'get_next_merge' has no corresponding test references |
| architecture | coordination_mcp.py:2084 | [test_coverage] Function 'run_pre_merge_checks' has no corresponding test references |
| architecture | coordination_mcp.py:2114 | [test_coverage] Function 'mark_merged' has no corresponding test references |
| architecture | coordination_mcp.py:2136 | [test_coverage] Function 'remove_from_merge_queue' has no corresponding test references |
| architecture | coordination_mcp.py:2161 | [test_coverage] Function '_current_trust_level' has no corresponding test references |
| architecture | coordination_mcp.py:2176 | [test_coverage] Function 'compose_train' has no corresponding test references |
| architecture | coordination_mcp.py:2235 | [test_coverage] Function 'eject_from_train' has no corresponding test references |
| architecture | coordination_mcp.py:2293 | [test_coverage] Function 'get_train_status' has no corresponding test references |
| architecture | coordination_mcp.py:2326 | [test_coverage] Function 'report_spec_result' has no corresponding test references |
| architecture | coordination_mcp.py:2369 | [test_coverage] Function 'affected_tests' has no corresponding test references |
| architecture | coordination_mcp.py:2407 | [test_coverage] Function 'report_status' has no corresponding test references |
| architecture | coordination_mcp.py:2508 | [test_coverage] Function 'help' has no corresponding test references |
| architecture | coordination_mcp.py:2555 | [test_coverage] Function 'get_current_locks' has no corresponding test references |
| architecture | coordination_mcp.py:2581 | [test_coverage] Function 'get_recent_handoffs' has no corresponding test references |
| architecture | coordination_mcp.py:2622 | [test_coverage] Function 'get_pending_work' has no corresponding test references |
| architecture | coordination_mcp.py:2654 | [test_coverage] Function 'get_recent_memories' has no corresponding test references |
| architecture | coordination_mcp.py:2683 | [test_coverage] Function 'get_guardrail_patterns' has no corresponding test references |
| architecture | coordination_mcp.py:2713 | [test_coverage] Function 'get_current_profile' has no corresponding test references |
| architecture | coordination_mcp.py:2749 | [test_coverage] Function 'get_recent_audit' has no corresponding test references |
| architecture | coordination_mcp.py:2778 | [test_coverage] Function 'get_active_features_resource' has no corresponding test references |
| architecture | coordination_mcp.py:2810 | [test_coverage] Function 'get_merge_queue_resource' has no corresponding test references |
| architecture | coordination_mcp.py:2840 | [test_coverage] Function 'list_scenarios' has no corresponding test references |
| architecture | coordination_mcp.py:2884 | [test_coverage] Function 'validate_scenario' has no corresponding test references |
| architecture | coordination_mcp.py:2919 | [test_coverage] Function 'create_scenario' has no corresponding test references |
| architecture | coordination_mcp.py:2970 | [test_coverage] Function 'run_gen_eval' has no corresponding test references |
| architecture | coordination_mcp.py:3016 | [test_coverage] Function 'get_gen_eval_coverage' has no corresponding test references |
| architecture | coordination_mcp.py:3048 | [test_coverage] Function 'get_gen_eval_report' has no corresponding test references |
| architecture | coordination_mcp.py:3095 | [test_coverage] Function 'coordinate_file_edit' has no corresponding test references |
| architecture | coordination_mcp.py:3117 | [test_coverage] Function 'start_work_session' has no corresponding test references |
| architecture | coordination_mcp.py:3140 | [test_coverage] Function '_code_search_enabled' has no corresponding test references |
| architecture | coordination_mcp.py:3149 | [test_coverage] Function 'search_code' has no corresponding test references |
| architecture | coordination_mcp.py:3225 | [test_coverage] Function 'main' has no corresponding test references |
| architecture | db.py:32 | [test_coverage] Function 'rpc' has no corresponding test references |
| architecture | db.py:36 | [test_coverage] Function 'query' has no corresponding test references |
| architecture | db.py:45 | [test_coverage] Function 'insert' has no corresponding test references |
| architecture | db.py:54 | [test_coverage] Function 'update' has no corresponding test references |
| architecture | db.py:64 | [test_coverage] Function 'delete' has no corresponding test references |
| architecture | db.py:68 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | db.py:80 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | db.py:85 | [test_coverage] Function 'config' has no corresponding test references |
| architecture | db.py:96 | [test_coverage] Function 'client' has no corresponding test references |
| architecture | db.py:101 | [test_coverage] Function '_headers' has no corresponding test references |
| architecture | db.py:109 | [test_coverage] Function 'rpc' has no corresponding test references |
| architecture | db.py:130 | [test_coverage] Function 'query' has no corresponding test references |
| architecture | db.py:154 | [test_coverage] Function 'insert' has no corresponding test references |
| architecture | db.py:184 | [test_coverage] Function 'update' has no corresponding test references |
| architecture | db.py:217 | [test_coverage] Function 'delete' has no corresponding test references |
| architecture | db.py:237 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | db.py:244 | [test_coverage] Function 'create_db_client' has no corresponding test references |
| architecture | db.py:271 | [test_coverage] Function 'get_db' has no corresponding test references |
| architecture | db.py:279 | [test_coverage] Function 'close_db' has no corresponding test references |
| architecture | db.py:287 | [test_coverage] Function 'reset_db' has no corresponding test references |
| architecture | db_postgres.py:25 | [test_coverage] Function '_coerce_filter_value' has no corresponding test references |
| architecture | db_postgres.py:46 | [test_coverage] Function '_validate_identifier' has no corresponding test references |
| architecture | db_postgres.py:54 | [test_coverage] Function '_validate_select_clause' has no corresponding test references |
| architecture | db_postgres.py:66 | [test_coverage] Function '_serialize_for_asyncpg' has no corresponding test references |
| architecture | db_postgres.py:85 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | db_postgres.py:89 | [test_coverage] Function '_get_pool' has no corresponding test references |
| architecture | db_postgres.py:98 | [test_coverage] Function 'rpc' has no corresponding test references |
| architecture | db_postgres.py:128 | [test_coverage] Function 'query' has no corresponding test references |
| architecture | db_postgres.py:217 | [test_coverage] Function 'insert' has no corresponding test references |
| architecture | db_postgres.py:245 | [test_coverage] Function 'update' has no corresponding test references |
| architecture | db_postgres.py:287 | [test_coverage] Function 'delete' has no corresponding test references |
| architecture | db_postgres.py:309 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | discovery.py:38 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:39 | [test_coverage] Function 'parse_dt' has no corresponding test references |
| architecture | discovery.py:68 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:82 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:96 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:113 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:124 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | discovery.py:128 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | discovery.py:133 | [test_coverage] Function 'register' has no corresponding test references |
| architecture | discovery.py:184 | [test_coverage] Function 'discover' has no corresponding test references |
| architecture | discovery.py:208 | [test_coverage] Function 'heartbeat' has no corresponding test references |
| architecture | discovery.py:266 | [test_coverage] Function 'cleanup_dead_agents' has no corresponding test references |
| architecture | discovery.py:309 | [test_coverage] Function 'get_discovery_service' has no corresponding test references |
| architecture | docker_manager.py:29 | [test_coverage] Function 'is_colima_installed' has no corresponding test references |
| architecture | docker_manager.py:34 | [test_coverage] Function 'is_colima_running' has no corresponding test references |
| architecture | docker_manager.py:47 | [test_coverage] Function '_ensure_colima_vm' has no corresponding test references |
| architecture | docker_manager.py:100 | [test_coverage] Function 'detect_runtime' has no corresponding test references |
| architecture | docker_manager.py:168 | [test_coverage] Function 'is_container_running' has no corresponding test references |
| architecture | docker_manager.py:182 | [test_coverage] Function 'start_container' has no corresponding test references |
| architecture | docker_manager.py:267 | [test_coverage] Function 'wait_for_healthy' has no corresponding test references |
| architecture | event_bus.py:50 | [test_coverage] Function '__post_init__' has no corresponding test references |
| architecture | event_bus.py:57 | [test_coverage] Function 'to_json' has no corresponding test references |
| architecture | event_bus.py:71 | [test_coverage] Function 'from_json' has no corresponding test references |
| architecture | event_bus.py:96 | [test_coverage] Function 'classify_urgency' has no corresponding test references |
| architecture | event_bus.py:119 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | event_bus.py:140 | [test_coverage] Function 'running' has no corresponding test references |
| architecture | event_bus.py:144 | [test_coverage] Function 'failed' has no corresponding test references |
| architecture | event_bus.py:148 | [test_coverage] Function 'on_event' has no corresponding test references |
| architecture | event_bus.py:159 | [test_coverage] Function 'off_event' has no corresponding test references |
| architecture | event_bus.py:188 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | event_bus.py:206 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | event_bus.py:225 | [test_coverage] Function 'restart' has no corresponding test references |
| architecture | event_bus.py:230 | [test_coverage] Function '_listen_loop' has no corresponding test references |
| architecture | event_bus.py:262 | [test_coverage] Function '_connect_and_listen' has no corresponding test references |
| architecture | event_bus.py:275 | [test_coverage] Function '_notification_handler' has no corresponding test references |
| architecture | event_bus.py:306 | [test_coverage] Function '_dispatch' has no corresponding test references |
| architecture | event_bus.py:329 | [test_coverage] Function '_safe_callback' has no corresponding test references |
| architecture | event_bus.py:343 | [test_coverage] Function 'get_event_bus' has no corresponding test references |
| architecture | event_bus.py:351 | [test_coverage] Function 'reset_event_bus' has no corresponding test references |
| architecture | event_stream.py:46 | [test_coverage] Function '_get_signing_key' has no corresponding test references |
| architecture | event_stream.py:51 | [test_coverage] Function '_signing_key_or_503' has no corresponding test references |
| architecture | event_stream.py:64 | [test_coverage] Function 'mint_events_token' has no corresponding test references |
| architecture | event_stream.py:111 | [test_coverage] Function 'validate_events_token' has no corresponding test references |
| architecture | event_stream.py:153 | [test_coverage] Function '_prune_nonces' has no corresponding test references |
| architecture | event_stream.py:163 | [test_coverage] Function '_build_snapshot' has no corresponding test references |
| architecture | event_stream.py:203 | [test_coverage] Function 'sse_event_generator' has no corresponding test references |
| architecture | event_stream.py:232 | [test_coverage] Function '_normalize_status' has no corresponding test references |
| architecture | event_stream.py:237 | [test_coverage] Function '_make_transition' has no corresponding test references |
| architecture | event_stream.py:258 | [test_coverage] Function '_make_audit' has no corresponding test references |
| architecture | event_stream.py:271 | [test_coverage] Function '_on_task_event' has no corresponding test references |
| architecture | event_stream.py:276 | [test_coverage] Function '_on_audit_event' has no corresponding test references |
| architecture | feature_flags.py:89 | [test_coverage] Function 'is_enabled' has no corresponding test references |
| architecture | feature_flags.py:92 | [test_coverage] Function 'to_yaml_dict' has no corresponding test references |
| architecture | feature_flags.py:106 | [test_coverage] Function 'from_yaml_dict' has no corresponding test references |
| architecture | feature_flags.py:107 | [test_coverage] Function '_parse' has no corresponding test references |
| architecture | feature_flags.py:129 | [test_coverage] Function 'normalize_flag_name' has no corresponding test references |
| architecture | feature_flags.py:164 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | feature_flags.py:173 | [test_coverage] Function 'load' has no corresponding test references |
| architecture | feature_flags.py:183 | [test_coverage] Function '_load_unlocked' has no corresponding test references |
| architecture | feature_flags.py:242 | [test_coverage] Function '_get_registry' has no corresponding test references |
| architecture | feature_flags.py:250 | [test_coverage] Function 'resolve_flag' has no corresponding test references |
| architecture | feature_flags.py:283 | [test_coverage] Function 'is_enabled' has no corresponding test references |
| architecture | feature_flags.py:287 | [test_coverage] Function 'check_undeclared_env_vars' has no corresponding test references |
| architecture | feature_flags.py:308 | [test_coverage] Function 'create_flag' has no corresponding test references |
| architecture | feature_flags.py:347 | [test_coverage] Function 'enable_flag' has no corresponding test references |
| architecture | feature_flags.py:363 | [test_coverage] Function '_write_registry' has no corresponding test references |
| architecture | feature_flags.py:393 | [test_coverage] Function 'get_feature_flag_service' has no corresponding test references |
| architecture | feature_flags.py:402 | [test_coverage] Function 'reset_feature_flag_service' has no corresponding test references |
| architecture | feature_flags.py:409 | [test_coverage] Function 'create_flag' has no corresponding test references |
| architecture | feature_flags.py:417 | [test_coverage] Function 'enable_flag' has no corresponding test references |
| architecture | feature_flags.py:421 | [test_coverage] Function 'resolve_flag' has no corresponding test references |
| architecture | feature_flags.py:425 | [test_coverage] Function 'is_enabled' has no corresponding test references |
| architecture | feature_registry.py:51 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | feature_registry.py:52 | [test_coverage] Function 'parse_dt' has no corresponding test references |
| architecture | feature_registry.py:84 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | feature_registry.py:103 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | feature_registry.py:131 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | feature_registry.py:135 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | feature_registry.py:140 | [test_coverage] Function 'register' has no corresponding test references |
| architecture | feature_registry.py:198 | [test_coverage] Function 'deregister' has no corresponding test references |
| architecture | feature_registry.py:233 | [test_coverage] Function 'get_feature' has no corresponding test references |
| architecture | feature_registry.py:248 | [test_coverage] Function 'get_active_features' has no corresponding test references |
| architecture | feature_registry.py:260 | [test_coverage] Function 'analyze_conflicts' has no corresponding test references |
| architecture | feature_registry.py:320 | [test_coverage] Function 'get_feature_registry_service' has no corresponding test references |
| architecture | git_adapter.py:108 | [test_coverage] Function 'create_speculative_ref' has no corresponding test references |
| architecture | git_adapter.py:115 | [test_coverage] Function 'delete_speculative_refs' has no corresponding test references |
| architecture | git_adapter.py:117 | [test_coverage] Function 'fast_forward_main' has no corresponding test references |
| architecture | git_adapter.py:119 | [test_coverage] Function 'get_changed_files' has no corresponding test references |
| architecture | git_adapter.py:121 | [test_coverage] Function 'list_speculative_refs' has no corresponding test references |
| architecture | git_adapter.py:129 | [test_coverage] Function 'validate_speculative_ref_name' has no corresponding test references |
| architecture | git_adapter.py:143 | [test_coverage] Function 'validate_branch_name' has no corresponding test references |
| architecture | git_adapter.py:159 | [test_coverage] Function 'parse_git_version' has no corresponding test references |
| architecture | git_adapter.py:183 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | git_adapter.py:189 | [test_coverage] Function '_ensure_git_version' has no corresponding test references |
| architecture | git_adapter.py:212 | [test_coverage] Function '_run' has no corresponding test references |
| architecture | git_adapter.py:225 | [test_coverage] Function 'create_speculative_ref' has no corresponding test references |
| architecture | git_adapter.py:317 | [test_coverage] Function 'delete_speculative_refs' has no corresponding test references |
| architecture | git_adapter.py:342 | [test_coverage] Function 'fast_forward_main' has no corresponding test references |
| architecture | git_adapter.py:372 | [test_coverage] Function 'get_changed_files' has no corresponding test references |
| architecture | git_adapter.py:406 | [test_coverage] Function 'list_speculative_refs' has no corresponding test references |
| architecture | git_adapter.py:426 | [test_coverage] Function '_parse_conflict_files' has no corresponding test references |
| architecture | github_classifier.py:16 | [test_coverage] Function '_load_classifier' has no corresponding test references |
| architecture | github_coordination.py:39 | [test_coverage] Function 'parse' has no corresponding test references |
| architecture | github_coordination.py:79 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | github_coordination.py:92 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | github_coordination.py:96 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | github_coordination.py:101 | [test_coverage] Function 'parse_lock_labels' has no corresponding test references |
| architecture | github_coordination.py:121 | [test_coverage] Function 'parse_branch' has no corresponding test references |
| architecture | github_coordination.py:132 | [test_coverage] Function 'sync_label_locks' has no corresponding test references |
| architecture | github_coordination.py:212 | [test_coverage] Function 'sync_branch_tracking' has no corresponding test references |
| architecture | github_coordination.py:265 | [test_coverage] Function 'handle_push_webhook' has no corresponding test references |
| architecture | github_coordination.py:294 | [test_coverage] Function 'handle_issues_webhook' has no corresponding test references |
| architecture | github_coordination.py:328 | [test_coverage] Function 'get_github_coordination_service' has no corresponding test references |
| architecture | github_openspec_fetcher.py:36 | [test_coverage] Function '_github_headers' has no corresponding test references |
| architecture | github_openspec_fetcher.py:44 | [test_coverage] Function '_parse_h1_title' has no corresponding test references |
| architecture | github_openspec_fetcher.py:53 | [test_coverage] Function '_b64decode' has no corresponding test references |
| architecture | github_openspec_fetcher.py:59 | [test_coverage] Function '_make_warning' has no corresponding test references |
| architecture | github_openspec_fetcher.py:68 | [test_coverage] Function '_now_iso' has no corresponding test references |
| architecture | github_openspec_fetcher.py:77 | [test_coverage] Function 'fetch_proposals_from_github' has no corresponding test references |
| architecture | github_openspec_fetcher.py:131 | [test_coverage] Function '_do_fetch' has no corresponding test references |
| architecture | github_openspec_fetcher.py:288 | [test_coverage] Function '_probe_branch' has no corresponding test references |
| architecture | github_openspec_fetcher.py:319 | [test_coverage] Function '_count_outside_changes' has no corresponding test references |
| architecture | github_prs_api.py:47 | [test_coverage] Function '_parse_repos' has no corresponding test references |
| architecture | github_prs_api.py:57 | [test_coverage] Function 'reduce_reviews' has no corresponding test references |
| architecture | github_prs_api.py:106 | [test_coverage] Function 'derive_pr_status' has no corresponding test references |
| architecture | github_prs_api.py:128 | [test_coverage] Function '_fetch_reviews' has no corresponding test references |
| architecture | github_prs_api.py:155 | [test_coverage] Function '_fetch_prs_for_repo' has no corresponding test references |
| architecture | github_prs_api.py:190 | [test_coverage] Function '_guarded_fetch' has no corresponding test references |
| architecture | github_prs_api.py:232 | [test_coverage] Function 'get_prs' has no corresponding test references |
| architecture | guardrails.py:33 | [test_coverage] Function '_ensure_guardrail_instruments' has no corresponding test references |
| architecture | guardrails.py:55 | [test_coverage] Function 'reset_guardrail_instruments' has no corresponding test references |
| architecture | guardrails.py:156 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | guardrails.py:178 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | guardrails.py:198 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | guardrails.py:209 | [test_coverage] Function '_check_session_scope' has no corresponding test references |
| architecture | guardrails.py:271 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | guardrails.py:277 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | guardrails.py:282 | [test_coverage] Function '_load_patterns' has no corresponding test references |
| architecture | guardrails.py:308 | [test_coverage] Function 'check_operation' has no corresponding test references |
| architecture | guardrails.py:459 | [test_coverage] Function 'get_guardrails_service' has no corresponding test references |
| architecture | handoffs.py:37 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | handoffs.py:67 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | handoffs.py:88 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | handoffs.py:98 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | handoffs.py:102 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | handoffs.py:107 | [test_coverage] Function 'write' has no corresponding test references |
| architecture | handoffs.py:191 | [test_coverage] Function 'read' has no corresponding test references |
| architecture | handoffs.py:241 | [test_coverage] Function 'get_recent' has no corresponding test references |
| architecture | handoffs.py:264 | [test_coverage] Function 'get_handoff_service' has no corresponding test references |
| architecture | help_service.py:40 | [test_coverage] Function '_register' has no corresponding test references |
| architecture | help_service.py:611 | [test_coverage] Function 'get_help_overview' has no corresponding test references |
| architecture | help_service.py:632 | [test_coverage] Function 'get_help_topic' has no corresponding test references |
| architecture | help_service.py:655 | [test_coverage] Function 'list_topic_names' has no corresponding test references |
| architecture | http_proxy.py:41 | [test_coverage] Function '_validate_url' has no corresponding test references |
| architecture | http_proxy.py:107 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | http_proxy.py:146 | [test_coverage] Function 'probe_database' has no corresponding test references |
| architecture | http_proxy.py:170 | [test_coverage] Function 'probe_http_api' has no corresponding test references |
| architecture | http_proxy.py:186 | [test_coverage] Function 'select_transport' has no corresponding test references |
| architecture | http_proxy.py:217 | [test_coverage] Function 'init_client' has no corresponding test references |
| architecture | http_proxy.py:228 | [test_coverage] Function 'get_config' has no corresponding test references |
| architecture | http_proxy.py:235 | [test_coverage] Function 'get_client' has no corresponding test references |
| architecture | http_proxy.py:242 | [test_coverage] Function 'shutdown_client' has no corresponding test references |
| architecture | http_proxy.py:250 | [test_coverage] Function '_build_default_headers' has no corresponding test references |
| architecture | http_proxy.py:268 | [test_coverage] Function '_error_response' has no corresponding test references |
| architecture | http_proxy.py:275 | [test_coverage] Function '_request' has no corresponding test references |
| architecture | http_proxy.py:352 | [test_coverage] Function '_agent_identity' has no corresponding test references |
| architecture | http_proxy.py:370 | [test_coverage] Function 'proxy_acquire_lock' has no corresponding test references |
| architecture | http_proxy.py:385 | [test_coverage] Function 'proxy_release_lock' has no corresponding test references |
| architecture | http_proxy.py:394 | [test_coverage] Function 'proxy_check_locks' has no corresponding test references |
| architecture | http_proxy.py:445 | [test_coverage] Function 'proxy_get_work' has no corresponding test references |
| architecture | http_proxy.py:456 | [test_coverage] Function 'proxy_complete_work' has no corresponding test references |
| architecture | http_proxy.py:473 | [test_coverage] Function 'proxy_submit_work' has no corresponding test references |
| architecture | http_proxy.py:492 | [test_coverage] Function 'proxy_get_task' has no corresponding test references |
| architecture | http_proxy.py:501 | [test_coverage] Function 'proxy_search_code' has no corresponding test references |
| architecture | http_proxy.py:562 | [test_coverage] Function 'proxy_issue_create' has no corresponding test references |
| architecture | http_proxy.py:587 | [test_coverage] Function 'proxy_issue_list' has no corresponding test references |
| architecture | http_proxy.py:608 | [test_coverage] Function 'proxy_issue_show' has no corresponding test references |
| architecture | http_proxy.py:613 | [test_coverage] Function 'proxy_issue_update' has no corresponding test references |
| architecture | http_proxy.py:638 | [test_coverage] Function 'proxy_issue_close' has no corresponding test references |
| architecture | http_proxy.py:653 | [test_coverage] Function 'proxy_issue_comment' has no corresponding test references |
| architecture | http_proxy.py:666 | [test_coverage] Function 'proxy_issue_search' has no corresponding test references |
| architecture | http_proxy.py:679 | [test_coverage] Function 'proxy_issue_ready' has no corresponding test references |
| architecture | http_proxy.py:692 | [test_coverage] Function 'proxy_issue_blocked' has no corresponding test references |
| architecture | http_proxy.py:702 | [test_coverage] Function 'proxy_write_handoff' has no corresponding test references |
| architecture | http_proxy.py:723 | [test_coverage] Function 'proxy_read_handoff' has no corresponding test references |
| architecture | http_proxy.py:741 | [test_coverage] Function 'proxy_register_session' has no corresponding test references |
| architecture | http_proxy.py:756 | [test_coverage] Function 'proxy_discover_agents' has no corresponding test references |
| architecture | http_proxy.py:769 | [test_coverage] Function 'proxy_heartbeat' has no corresponding test references |
| architecture | http_proxy.py:775 | [test_coverage] Function 'proxy_cleanup_dead_agents' has no corresponding test references |
| architecture | http_proxy.py:791 | [test_coverage] Function 'proxy_remember' has no corresponding test references |
| architecture | http_proxy.py:812 | [test_coverage] Function 'proxy_recall' has no corresponding test references |
| architecture | http_proxy.py:834 | [test_coverage] Function 'proxy_check_guardrails' has no corresponding test references |
| architecture | http_proxy.py:847 | [test_coverage] Function 'proxy_get_my_profile' has no corresponding test references |
| architecture | http_proxy.py:852 | [test_coverage] Function 'proxy_get_agent_dispatch_configs' has no corresponding test references |
| architecture | http_proxy.py:857 | [test_coverage] Function 'proxy_query_audit' has no corresponding test references |
| architecture | http_proxy.py:876 | [test_coverage] Function 'proxy_check_policy' has no corresponding test references |
| architecture | http_proxy.py:891 | [test_coverage] Function 'proxy_validate_cedar_policy' has no corresponding test references |
| architecture | http_proxy.py:900 | [test_coverage] Function 'proxy_list_policy_versions' has no corresponding test references |
| architecture | http_proxy.py:912 | [test_coverage] Function 'proxy_request_permission' has no corresponding test references |
| architecture | http_proxy.py:925 | [test_coverage] Function 'proxy_request_approval' has no corresponding test references |
| architecture | http_proxy.py:940 | [test_coverage] Function 'proxy_check_approval' has no corresponding test references |
| architecture | http_proxy.py:950 | [test_coverage] Function 'proxy_allocate_ports' has no corresponding test references |
| architecture | http_proxy.py:959 | [test_coverage] Function 'proxy_release_ports' has no corresponding test references |
| architecture | http_proxy.py:968 | [test_coverage] Function 'proxy_ports_status' has no corresponding test references |
| architecture | http_proxy.py:985 | [test_coverage] Function 'proxy_register_feature' has no corresponding test references |
| architecture | http_proxy.py:1006 | [test_coverage] Function 'proxy_deregister_feature' has no corresponding test references |
| architecture | http_proxy.py:1019 | [test_coverage] Function 'proxy_get_feature' has no corresponding test references |
| architecture | http_proxy.py:1024 | [test_coverage] Function 'proxy_list_active_features' has no corresponding test references |
| architecture | http_proxy.py:1029 | [test_coverage] Function 'proxy_analyze_feature_conflicts' has no corresponding test references |
| architecture | http_proxy.py:1047 | [test_coverage] Function 'proxy_enqueue_merge' has no corresponding test references |
| architecture | http_proxy.py:1060 | [test_coverage] Function 'proxy_get_merge_queue' has no corresponding test references |
| architecture | http_proxy.py:1065 | [test_coverage] Function 'proxy_get_next_merge' has no corresponding test references |
| architecture | http_proxy.py:1070 | [test_coverage] Function 'proxy_run_pre_merge_checks' has no corresponding test references |
| architecture | http_proxy.py:1079 | [test_coverage] Function 'proxy_mark_merged' has no corresponding test references |
| architecture | http_proxy.py:1088 | [test_coverage] Function 'proxy_remove_from_merge_queue' has no corresponding test references |
| architecture | http_proxy.py:1098 | [test_coverage] Function 'proxy_report_status' has no corresponding test references |
| architecture | http_proxy.py:1125 | [test_coverage] Function 'proxy_list_scenarios' has no corresponding test references |
| architecture | http_proxy.py:1149 | [test_coverage] Function 'proxy_validate_scenario' has no corresponding test references |
| architecture | http_proxy.py:1158 | [test_coverage] Function 'proxy_create_scenario' has no corresponding test references |
| architecture | http_proxy.py:1177 | [test_coverage] Function 'proxy_run_gen_eval' has no corresponding test references |
| architecture | issue_service.py:72 | [test_coverage] Function 'from_row' has no corresponding test references |
| architecture | issue_service.py:73 | [test_coverage] Function 'parse_dt' has no corresponding test references |
| architecture | issue_service.py:108 | [test_coverage] Function 'to_dict' has no corresponding test references |
| architecture | issue_service.py:164 | [test_coverage] Function 'from_row' has no corresponding test references |
| architecture | issue_service.py:176 | [test_coverage] Function 'to_dict' has no corresponding test references |
| architecture | issue_service.py:189 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | issue_service.py:193 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | issue_service.py:198 | [test_coverage] Function 'create' has no corresponding test references |
| architecture | issue_service.py:251 | [test_coverage] Function 'list_issues' has no corresponding test references |
| architecture | issue_service.py:306 | [test_coverage] Function 'show' has no corresponding test references |
| architecture | issue_service.py:344 | [test_coverage] Function 'update' has no corresponding test references |
| architecture | issue_service.py:410 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | issue_service.py:453 | [test_coverage] Function 'comment' has no corresponding test references |
| architecture | issue_service.py:479 | [test_coverage] Function 'ready' has no corresponding test references |
| architecture | issue_service.py:525 | [test_coverage] Function 'blocked' has no corresponding test references |
| architecture | issue_service.py:554 | [test_coverage] Function 'search' has no corresponding test references |
| architecture | issue_service.py:594 | [test_coverage] Function 'get_issue_service' has no corresponding test references |
| architecture | kanban_viz_files.py:69 | [test_coverage] Function '_load_schema' has no corresponding test references |
| architecture | kanban_viz_files.py:115 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | kanban_viz_files.py:124 | [test_coverage] Function '_validate_against' has no corresponding test references |
| architecture | kanban_viz_files.py:135 | [test_coverage] Function '_validate_slug' has no corresponding test references |
| architecture | kanban_viz_files.py:142 | [test_coverage] Function '_git_sha' has no corresponding test references |
| architecture | kanban_viz_files.py:156 | [test_coverage] Function '_atomic_write' has no corresponding test references |
| architecture | kanban_viz_files.py:171 | [test_coverage] Function 'write_saved_view' has no corresponding test references |
| architecture | kanban_viz_files.py:211 | [test_coverage] Function 'write_audit_event' has no corresponding test references |
| architecture | langfuse_middleware.py:44 | [test_coverage] Function 'dispatch' has no corresponding test references |
| architecture | langfuse_middleware.py:98 | [test_coverage] Function '_resolve_agent_id' has no corresponding test references |
| architecture | langfuse_middleware.py:114 | [test_coverage] Function '_finalize_trace' has no corresponding test references |
| architecture | langfuse_tracing.py:30 | [test_coverage] Function '_is_enabled' has no corresponding test references |
| architecture | langfuse_tracing.py:34 | [test_coverage] Function 'init_langfuse' has no corresponding test references |
| architecture | langfuse_tracing.py:79 | [test_coverage] Function 'get_langfuse' has no corresponding test references |
| architecture | langfuse_tracing.py:84 | [test_coverage] Function 'shutdown_langfuse' has no corresponding test references |
| architecture | langfuse_tracing.py:102 | [test_coverage] Function 'create_trace' has no corresponding test references |
| architecture | langfuse_tracing.py:130 | [test_coverage] Function 'create_span' has no corresponding test references |
| architecture | langfuse_tracing.py:153 | [test_coverage] Function 'end_span' has no corresponding test references |
| architecture | langfuse_tracing.py:175 | [test_coverage] Function 'trace_operation' has no corresponding test references |
| architecture | langfuse_tracing.py:229 | [test_coverage] Function 'reset_langfuse' has no corresponding test references |
| architecture | locks.py:29 | [test_coverage] Function '_get_instruments' has no corresponding test references |
| architecture | locks.py:58 | [test_coverage] Function '_ensure_instruments' has no corresponding test references |
| architecture | locks.py:81 | [test_coverage] Function 'is_valid_lock_key' has no corresponding test references |
| architecture | locks.py:101 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | locks.py:102 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | locks.py:131 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | locks.py:152 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | locks.py:156 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | locks.py:161 | [test_coverage] Function 'acquire' has no corresponding test references |
| architecture | locks.py:276 | [test_coverage] Function 'release' has no corresponding test references |
| architecture | locks.py:341 | [test_coverage] Function 'check' has no corresponding test references |
| architecture | locks.py:368 | [test_coverage] Function 'extend' has no corresponding test references |
| architecture | locks.py:392 | [test_coverage] Function 'is_locked' has no corresponding test references |
| architecture | locks.py:404 | [test_coverage] Function 'force_release' has no corresponding test references |
| architecture | locks.py:465 | [test_coverage] Function 'get_lock_service' has no corresponding test references |
| architecture | memory.py:51 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | memory.py:81 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | memory.py:97 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | memory.py:108 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | memory.py:112 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | memory.py:117 | [test_coverage] Function 'remember' has no corresponding test references |
| architecture | memory.py:197 | [test_coverage] Function 'recall' has no corresponding test references |
| architecture | memory.py:235 | [test_coverage] Function 'get_memory_service' has no corresponding test references |
| architecture | merge_queue.py:73 | [test_coverage] Function 'from_feature' has no corresponding test references |
| architecture | merge_queue.py:99 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | merge_queue.py:108 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | merge_queue.py:114 | [test_coverage] Function 'registry' has no corresponding test references |
| architecture | merge_queue.py:119 | [test_coverage] Function 'enqueue' has no corresponding test references |
| architecture | merge_queue.py:210 | [test_coverage] Function 'get_queue' has no corresponding test references |
| architecture | merge_queue.py:246 | [test_coverage] Function 'get_next_to_merge' has no corresponding test references |
| architecture | merge_queue.py:260 | [test_coverage] Function 'run_pre_merge_checks' has no corresponding test references |
| architecture | merge_queue.py:349 | [test_coverage] Function 'mark_merged' has no corresponding test references |
| architecture | merge_queue.py:376 | [test_coverage] Function 'remove_from_queue' has no corresponding test references |
| architecture | merge_queue.py:404 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | merge_queue.py:417 | [test_coverage] Function 'get_merge_queue_service' has no corresponding test references |
| architecture | merge_train.py:114 | [test_coverage] Function '_entry_prefix_set' has no corresponding test references |
| architecture | merge_train.py:137 | [test_coverage] Function '_find_cycles_in_cross_partition_graph' has no corresponding test references |
| architecture | merge_train.py:176 | [test_coverage] Function '_dfs' has no corresponding test references |
| architecture | merge_train.py:212 | [test_coverage] Function 'compute_partitions' has no corresponding test references |
| architecture | merge_train.py:294 | [test_coverage] Function '_speculative_ref_name' has no corresponding test references |
| architecture | merge_train.py:299 | [test_coverage] Function '_sort_entries_by_priority' has no corresponding test references |
| architecture | merge_train.py:304 | [test_coverage] Function '_handle_conflict' has no corresponding test references |
| architecture | merge_train.py:318 | [test_coverage] Function '_handle_speculative_success' has no corresponding test references |
| architecture | merge_train.py:339 | [test_coverage] Function 'compose_train' has no corresponding test references |
| architecture | merge_train.py:445 | [test_coverage] Function '_speculate' has no corresponding test references |
| architecture | merge_train.py:547 | [test_coverage] Function '_declared_namespaces' has no corresponding test references |
| architecture | merge_train.py:557 | [test_coverage] Function 'validate_post_speculation_claims' has no corresponding test references |
| architecture | merge_train.py:644 | [test_coverage] Function '_caller_is_authorized_to_eject' has no corresponding test references |
| architecture | merge_train.py:659 | [test_coverage] Function 'eject_from_train' has no corresponding test references |
| architecture | merge_train.py:768 | [test_coverage] Function 'reset_blocked_entry' has no corresponding test references |
| architecture | merge_train.py:811 | [test_coverage] Function 'reset_abandoned_entry' has no corresponding test references |
| architecture | merge_train.py:884 | [test_coverage] Function '_build_merge_graph' has no corresponding test references |
| architecture | merge_train.py:974 | [test_coverage] Function '_compute_wave_order' has no corresponding test references |
| architecture | merge_train.py:1017 | [test_coverage] Function 'execute_wave_merge' has no corresponding test references |
| architecture | merge_train.py:1137 | [test_coverage] Function '_group_refs_by_train_id' has no corresponding test references |
| architecture | merge_train.py:1157 | [test_coverage] Function 'cleanup_orphaned_speculative_refs' has no corresponding test references |
| architecture | merge_train.py:1206 | [test_coverage] Function 'gc_aged_speculative_refs' has no corresponding test references |
| architecture | merge_train_service.py:66 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | merge_train_service.py:77 | [test_coverage] Function '_feature_to_train_entry' has no corresponding test references |
| architecture | merge_train_service.py:123 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | merge_train_service.py:138 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | merge_train_service.py:144 | [test_coverage] Function 'registry' has no corresponding test references |
| architecture | merge_train_service.py:150 | [test_coverage] Function 'git_adapter' has no corresponding test references |
| architecture | merge_train_service.py:160 | [test_coverage] Function 'refresh_client' has no corresponding test references |
| architecture | merge_train_service.py:167 | [test_coverage] Function '_load_entries' has no corresponding test references |
| architecture | merge_train_service.py:177 | [test_coverage] Function '_save_entry' has no corresponding test references |
| architecture | merge_train_service.py:197 | [test_coverage] Function '_persist_entries' has no corresponding test references |
| architecture | merge_train_service.py:208 | [test_coverage] Function '_probe_and_maybe_refresh' has no corresponding test references |
| architecture | merge_train_service.py:256 | [test_coverage] Function 'compose_train' has no corresponding test references |
| architecture | merge_train_service.py:288 | [test_coverage] Function 'eject_from_train' has no corresponding test references |
| architecture | merge_train_service.py:338 | [test_coverage] Function 'get_train_status' has no corresponding test references |
| architecture | merge_train_service.py:343 | [test_coverage] Function 'report_spec_result' has no corresponding test references |
| architecture | merge_train_service.py:396 | [test_coverage] Function 'get_merge_train_service' has no corresponding test references |
| architecture | merge_train_service.py:404 | [test_coverage] Function 'reset_merge_train_service' has no corresponding test references |
| architecture | merge_train_service.py:438 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | merge_train_service.py:457 | [test_coverage] Function 'service' has no corresponding test references |
| architecture | merge_train_service.py:463 | [test_coverage] Function 'running' has no corresponding test references |
| architecture | merge_train_service.py:466 | [test_coverage] Function 'run_once' has no corresponding test references |
| architecture | merge_train_service.py:484 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | merge_train_service.py:494 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | merge_train_service.py:506 | [test_coverage] Function '_loop' has no corresponding test references |
| architecture | merge_train_service.py:521 | [test_coverage] Function 'get_merge_train_sweeper' has no corresponding test references |
| architecture | merge_train_service.py:529 | [test_coverage] Function 'reset_merge_train_sweeper' has no corresponding test references |
| architecture | merge_train_types.py:127 | [test_coverage] Function 'is_terminal' has no corresponding test references |
| architecture | merge_train_types.py:130 | [test_coverage] Function 'to_metadata_dict' has no corresponding test references |
| architecture | merge_train_types.py:162 | [test_coverage] Function 'all_passed' has no corresponding test references |
| architecture | merge_train_types.py:202 | [test_coverage] Function 'new_train_id' has no corresponding test references |
| architecture | merge_train_types.py:206 | [test_coverage] Function 'all_entries' has no corresponding test references |
| architecture | merge_train_types.py:213 | [test_coverage] Function 'total_entry_count' has no corresponding test references |
| architecture | merge_train_types.py:252 | [test_coverage] Function 'file_path_to_namespaces' has no corresponding test references |
| architecture | merge_train_types.py:287 | [test_coverage] Function 'claim_prefix' has no corresponding test references |
| architecture | merge_watcher.py:25 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | merge_watcher.py:30 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | merge_watcher.py:39 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | merge_watcher.py:50 | [test_coverage] Function '_loop' has no corresponding test references |
| architecture | merge_watcher.py:61 | [test_coverage] Function '_tick' has no corresponding test references |
| architecture | merge_watcher.py:68 | [test_coverage] Function 'get_merge_watcher' has no corresponding test references |
| architecture | migrations.py:35 | [test_coverage] Function 'discover_migrations' has no corresponding test references |
| architecture | migrations.py:50 | [test_coverage] Function '_checksum' has no corresponding test references |
| architecture | migrations.py:55 | [test_coverage] Function 'run_migrations' has no corresponding test references |
| architecture | migrations.py:146 | [test_coverage] Function 'ensure_schema' has no corresponding test references |
| architecture | model_routing/exploration.py:33 | [test_coverage] Function 'exhausted' has no corresponding test references |
| architecture | model_routing/exploration.py:48 | [test_coverage] Function 'choose' has no corresponding test references |
| architecture | model_routing/feedback.py:29 | [test_coverage] Function '_observation_value_is_sane' has no corresponding test references |
| architecture | model_routing/feedback.py:73 | [test_coverage] Function '_decayed_weight' has no corresponding test references |
| architecture | model_routing/feedback.py:80 | [test_coverage] Function 'aggregate' has no corresponding test references |
| architecture | model_routing/feedback.py:120 | [test_coverage] Function 'normalize_vendor_switch' has no corresponding test references |
| architecture | model_routing/feedback.py:147 | [test_coverage] Function 'normalize_vendor_notes' has no corresponding test references |
| architecture | model_routing/resolver.py:106 | [test_coverage] Function 'blend_quality' has no corresponding test references |
| architecture | model_routing/resolver.py:122 | [test_coverage] Function 'effective_cost' has no corresponding test references |
| architecture | model_routing/resolver.py:149 | [test_coverage] Function 'feasibility_reason' has no corresponding test references |
| architecture | model_routing/resolver.py:167 | [test_coverage] Function '_min_max_norm' has no corresponding test references |
| architecture | model_routing/resolver.py:177 | [test_coverage] Function '_headroom_fraction' has no corresponding test references |
| architecture | model_routing/resolver.py:184 | [test_coverage] Function 'score_and_rank' has no corresponding test references |
| architecture | network_policies.py:24 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | network_policies.py:36 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | network_policies.py:40 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | network_policies.py:45 | [test_coverage] Function 'check_domain' has no corresponding test references |
| architecture | network_policies.py:85 | [test_coverage] Function 'get_network_policy_service' has no corresponding test references |
| architecture | notifications/base.py:16 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/base.py:20 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/base.py:24 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/base.py:34 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/base.py:37 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/base.py:41 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/base.py:44 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/gmail.py:55 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/gmail.py:71 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/gmail.py:128 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/gmail.py:143 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/gmail.py:148 | [test_coverage] Function 'start_imap_listener' has no corresponding test references |
| architecture | notifications/gmail.py:214 | [test_coverage] Function 'stop_imap_listener' has no corresponding test references |
| architecture | notifications/gmail.py:222 | [test_coverage] Function '_process_imap_message' has no corresponding test references |
| architecture | notifications/gmail.py:348 | [test_coverage] Function '_send_reply_email' has no corresponding test references |
| architecture | notifications/gmail.py:368 | [test_coverage] Function '_render' has no corresponding test references |
| architecture | notifications/gmail.py:380 | [test_coverage] Function '_thread_message_id' has no corresponding test references |
| architecture | notifications/gmail.py:387 | [test_coverage] Function 'get_gmail_channel' has no corresponding test references |
| architecture | notifications/notifier.py:33 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/notifier.py:38 | [test_coverage] Function 'register_channel' has no corresponding test references |
| architecture | notifications/notifier.py:43 | [test_coverage] Function 'enabled' has no corresponding test references |
| architecture | notifications/notifier.py:47 | [test_coverage] Function 'start_digest_loop' has no corresponding test references |
| architecture | notifications/notifier.py:54 | [test_coverage] Function 'stop_digest_loop' has no corresponding test references |
| architecture | notifications/notifier.py:67 | [test_coverage] Function '_digest_loop' has no corresponding test references |
| architecture | notifications/notifier.py:77 | [test_coverage] Function '_flush_digest' has no corresponding test references |
| architecture | notifications/notifier.py:110 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/notifier.py:169 | [test_coverage] Function '_send_with_retry' has no corresponding test references |
| architecture | notifications/notifier.py:208 | [test_coverage] Function '_passes_filter' has no corresponding test references |
| architecture | notifications/notifier.py:223 | [test_coverage] Function 'get_notifier' has no corresponding test references |
| architecture | notifications/notifier.py:231 | [test_coverage] Function 'reset_notifier' has no corresponding test references |
| architecture | notifications/relay.py:29 | [test_coverage] Function 'extract_token' has no corresponding test references |
| architecture | notifications/relay.py:39 | [test_coverage] Function 'parse_reply' has no corresponding test references |
| architecture | notifications/relay.py:72 | [test_coverage] Function 'validate_sender' has no corresponding test references |
| architecture | notifications/relay.py:82 | [test_coverage] Function 'clean_reply_body' has no corresponding test references |
| architecture | notifications/relay.py:109 | [test_coverage] Function 'route_reply' has no corresponding test references |
| architecture | notifications/telegram.py:28 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/telegram.py:39 | [test_coverage] Function 'client' has no corresponding test references |
| architecture | notifications/telegram.py:44 | [test_coverage] Function '_api_url' has no corresponding test references |
| architecture | notifications/telegram.py:47 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/telegram.py:106 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/telegram.py:122 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/telegram.py:126 | [test_coverage] Function '_escape_markdown' has no corresponding test references |
| architecture | notifications/telegram.py:131 | [test_coverage] Function '_format_message' has no corresponding test references |
| architecture | notifications/telegram.py:148 | [test_coverage] Function 'get_telegram_channel' has no corresponding test references |
| architecture | notifications/templates.py:10 | [test_coverage] Function '_esc' has no corresponding test references |
| architecture | notifications/templates.py:15 | [test_coverage] Function '_sanitize_header' has no corresponding test references |
| architecture | notifications/templates.py:46 | [test_coverage] Function '_wrap' has no corresponding test references |
| architecture | notifications/templates.py:56 | [test_coverage] Function '_change_label' has no corresponding test references |
| architecture | notifications/templates.py:61 | [test_coverage] Function '_field' has no corresponding test references |
| architecture | notifications/templates.py:71 | [test_coverage] Function 'render_approval_email' has no corresponding test references |
| architecture | notifications/templates.py:100 | [test_coverage] Function 'render_status_email' has no corresponding test references |
| architecture | notifications/templates.py:119 | [test_coverage] Function 'render_escalation_email' has no corresponding test references |
| architecture | notifications/templates.py:147 | [test_coverage] Function 'render_stale_agent_email' has no corresponding test references |
| architecture | notifications/templates.py:165 | [test_coverage] Function 'render_digest_email' has no corresponding test references |
| architecture | notifications/webhook.py:26 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/webhook.py:37 | [test_coverage] Function 'client' has no corresponding test references |
| architecture | notifications/webhook.py:42 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/webhook.py:83 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/webhook.py:109 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/webhook.py:113 | [test_coverage] Function 'get_webhook_channel' has no corresponding test references |
| architecture | openspec_proposals_api.py:61 | [test_coverage] Function '_get_repo_root' has no corresponding test references |
| architecture | openspec_proposals_api.py:79 | [test_coverage] Function '_run_git' has no corresponding test references |
| architecture | openspec_proposals_api.py:90 | [test_coverage] Function '_has_git_dir' has no corresponding test references |
| architecture | openspec_proposals_api.py:96 | [test_coverage] Function '_resolve_branch' has no corresponding test references |
| architecture | openspec_proposals_api.py:118 | [test_coverage] Function '_count_code_changes_outside_proposal' has no corresponding test references |
| architecture | openspec_proposals_api.py:162 | [test_coverage] Function '_detect_impl_state' has no corresponding test references |
| architecture | openspec_proposals_api.py:199 | [test_coverage] Function '_parse_h1_title' has no corresponding test references |
| architecture | openspec_proposals_api.py:208 | [test_coverage] Function '_git_log_iso' has no corresponding test references |
| architecture | openspec_proposals_api.py:224 | [test_coverage] Function '_enumerate_proposals' has no corresponding test references |
| architecture | openspec_proposals_api.py:301 | [test_coverage] Function 'get_proposals' has no corresponding test references |
| architecture | openspec_proposals_api.py:323 | [test_coverage] Function '_get_proposals_implicit_local' has no corresponding test references |
| architecture | openspec_proposals_api.py:382 | [test_coverage] Function '_get_proposals_multi_source' has no corresponding test references |
| architecture | openspec_proposals_api.py:475 | [test_coverage] Function '_resolve_local_repo' has no corresponding test references |
| architecture | openspec_proposals_api.py:485 | [test_coverage] Function '_fetch_github_with_cache' has no corresponding test references |
| architecture | openspec_proposals_api.py:516 | [test_coverage] Function '_combine_status' has no corresponding test references |
| architecture | openspec_sources.py:77 | [test_coverage] Function 'parse_sources' has no corresponding test references |
| architecture | openspec_sources.py:144 | [test_coverage] Function 'derive_local_repo' has no corresponding test references |
| architecture | openspec_sources.py:204 | [test_coverage] Function '_walk_local_source' has no corresponding test references |
| architecture | openspec_sources.py:256 | [test_coverage] Function 'warm_local_sources' has no corresponding test references |
| architecture | openspec_sources.py:290 | [test_coverage] Function 'get_or_walk_local' has no corresponding test references |
| architecture | openspec_sources.py:314 | [test_coverage] Function 'invalidate_local_walk_cache' has no corresponding test references |
| architecture | policy_engine.py:29 | [test_coverage] Function '_ensure_policy_instruments' has no corresponding test references |
| architecture | policy_engine.py:93 | [test_coverage] Function 'allow' has no corresponding test references |
| architecture | policy_engine.py:97 | [test_coverage] Function 'deny' has no corresponding test references |
| architecture | policy_engine.py:116 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | policy_engine.py:120 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | policy_engine.py:125 | [test_coverage] Function 'check_operation' has no corresponding test references |
| architecture | policy_engine.py:166 | [test_coverage] Function '_do_check_operation' has no corresponding test references |
| architecture | policy_engine.py:351 | [test_coverage] Function 'check_network_access' has no corresponding test references |
| architecture | policy_engine.py:374 | [test_coverage] Function 'list_policy_versions' has no corresponding test references |
| architecture | policy_engine.py:393 | [test_coverage] Function 'rollback_policy' has no corresponding test references |
| architecture | policy_engine.py:419 | [test_coverage] Function '_log_policy_decision' has no corresponding test references |
| architecture | policy_engine.py:465 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | policy_engine.py:481 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | policy_engine.py:486 | [test_coverage] Function '_load_default_policies' has no corresponding test references |
| architecture | policy_engine.py:500 | [test_coverage] Function '_load_schema' has no corresponding test references |
| architecture | policy_engine.py:518 | [test_coverage] Function '_load_policies' has no corresponding test references |
| architecture | policy_engine.py:573 | [test_coverage] Function '_build_entity' has no corresponding test references |
| architecture | policy_engine.py:610 | [test_coverage] Function '_build_resource_entity' has no corresponding test references |
| architecture | policy_engine.py:637 | [test_coverage] Function '_determine_resource_type' has no corresponding test references |
| architecture | policy_engine.py:649 | [test_coverage] Function 'check_operation' has no corresponding test references |
| architecture | policy_engine.py:690 | [test_coverage] Function '_do_check_operation' has no corresponding test references |
| architecture | policy_engine.py:779 | [test_coverage] Function 'check_network_access' has no corresponding test references |
| architecture | policy_engine.py:798 | [test_coverage] Function 'validate_policy' has no corresponding test references |
| architecture | policy_engine.py:819 | [test_coverage] Function 'list_policies' has no corresponding test references |
| architecture | policy_engine.py:838 | [test_coverage] Function 'invalidate_cache' has no corresponding test references |
| architecture | policy_engine.py:843 | [test_coverage] Function 'list_policy_versions' has no corresponding test references |
| architecture | policy_engine.py:862 | [test_coverage] Function 'rollback_policy' has no corresponding test references |
| architecture | policy_engine.py:889 | [test_coverage] Function '_log_policy_decision' has no corresponding test references |
| architecture | policy_engine.py:929 | [test_coverage] Function 'get_policy_engine' has no corresponding test references |
| architecture | policy_engine.py:946 | [test_coverage] Function 'reset_policy_engine' has no corresponding test references |
| architecture | policy_engine.py:952 | [test_coverage] Function 'reset_policy_instruments' has no corresponding test references |
| architecture | policy_sync.py:21 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | policy_sync.py:25 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | policy_sync.py:29 | [test_coverage] Function 'on_policy_change' has no corresponding test references |
| architecture | policy_sync.py:45 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | policy_sync.py:60 | [test_coverage] Function 'running' has no corresponding test references |
| architecture | policy_sync.py:64 | [test_coverage] Function 'on_policy_change' has no corresponding test references |
| architecture | policy_sync.py:67 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | policy_sync.py:79 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | policy_sync.py:93 | [test_coverage] Function '_listen_loop' has no corresponding test references |
| architecture | policy_sync.py:121 | [test_coverage] Function '_connect_and_listen' has no corresponding test references |
| architecture | policy_sync.py:127 | [test_coverage] Function '_notification_handler' has no corresponding test references |
| architecture | policy_sync.py:149 | [test_coverage] Function '_safe_callback' has no corresponding test references |
| architecture | policy_sync.py:163 | [test_coverage] Function 'get_policy_sync_service' has no corresponding test references |
| architecture | policy_sync.py:171 | [test_coverage] Function 'reset_policy_sync_service' has no corresponding test references |
| architecture | port_allocator.py:37 | [test_coverage] Function 'env_snippet' has no corresponding test references |
| architecture | port_allocator.py:55 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | port_allocator.py:74 | [test_coverage] Function 'allocate' has no corresponding test references |
| architecture | port_allocator.py:132 | [test_coverage] Function 'release' has no corresponding test references |
| architecture | port_allocator.py:141 | [test_coverage] Function 'status' has no corresponding test references |
| architecture | port_allocator.py:151 | [test_coverage] Function '_cleanup_expired' has no corresponding test references |
| architecture | port_allocator.py:166 | [test_coverage] Function '_compose_project_name' has no corresponding test references |
| architecture | port_allocator.py:178 | [test_coverage] Function 'get_port_allocator' has no corresponding test references |
| architecture | port_allocator.py:189 | [test_coverage] Function 'reset_port_allocator' has no corresponding test references |
| architecture | profile_loader.py:64 | [test_coverage] Function 'deep_merge' has no corresponding test references |
| architecture | profile_loader.py:87 | [test_coverage] Function '_load_secrets_file' has no corresponding test references |
| architecture | profile_loader.py:114 | [test_coverage] Function '_load_secrets_openbao' has no corresponding test references |
| architecture | profile_loader.py:159 | [test_coverage] Function '_load_secrets' has no corresponding test references |
| architecture | profile_loader.py:171 | [test_coverage] Function 'resolve_dynamic_dsn' has no corresponding test references |
| architecture | profile_loader.py:231 | [test_coverage] Function 'interpolate' has no corresponding test references |
| architecture | profile_loader.py:239 | [test_coverage] Function '_replace' has no corresponding test references |
| architecture | profile_loader.py:260 | [test_coverage] Function '_interpolate_tree' has no corresponding test references |
| architecture | profile_loader.py:277 | [test_coverage] Function '_resolve_profile' has no corresponding test references |
| architecture | profile_loader.py:311 | [test_coverage] Function '_flatten' has no corresponding test references |
| architecture | profile_loader.py:323 | [test_coverage] Function '_inject_env' has no corresponding test references |
| architecture | profile_loader.py:339 | [test_coverage] Function 'load_profile' has no corresponding test references |
| architecture | profile_loader.py:372 | [test_coverage] Function 'apply_profile' has no corresponding test references |
| architecture | profiles.py:36 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | profiles.py:63 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | profiles.py:84 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | profiles.py:94 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | profiles.py:99 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | profiles.py:104 | [test_coverage] Function 'get_profile' has no corresponding test references |
| architecture | profiles.py:153 | [test_coverage] Function 'check_operation' has no corresponding test references |
| architecture | profiles.py:214 | [test_coverage] Function '_log_denial' has no corresponding test references |
| architecture | profiles.py:237 | [test_coverage] Function 'get_profiles_service' has no corresponding test references |
| architecture | refresh_rpc_client.py:69 | [test_coverage] Function '__repr__' has no corresponding test references |
| architecture | refresh_rpc_client.py:85 | [test_coverage] Function '__call__' has no corresponding test references |
| architecture | refresh_rpc_client.py:134 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | refresh_rpc_client.py:150 | [test_coverage] Function 'is_graph_stale' has no corresponding test references |
| architecture | refresh_rpc_client.py:164 | [test_coverage] Function 'trigger_refresh' has no corresponding test references |
| architecture | refresh_rpc_client.py:174 | [test_coverage] Function 'get_refresh_status' has no corresponding test references |
| architecture | refresh_rpc_client.py:183 | [test_coverage] Function '_invoke' has no corresponding test references |
| architecture | refresh_rpc_client.py:277 | [test_coverage] Function 'compute_affected_tests' has no corresponding test references |
| architecture | risk_scorer.py:44 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | risk_scorer.py:56 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | risk_scorer.py:61 | [test_coverage] Function 'compute_score' has no corresponding test references |
| architecture | risk_scorer.py:108 | [test_coverage] Function 'get_violation_count' has no corresponding test references |
| architecture | risk_scorer.py:125 | [test_coverage] Function '_trust_factor' has no corresponding test references |
| architecture | risk_scorer.py:130 | [test_coverage] Function '_operation_factor' has no corresponding test references |
| architecture | risk_scorer.py:141 | [test_coverage] Function '_resource_factor' has no corresponding test references |
| architecture | risk_scorer.py:152 | [test_coverage] Function '_violation_factor' has no corresponding test references |
| architecture | risk_scorer.py:161 | [test_coverage] Function '_session_age_factor' has no corresponding test references |
| architecture | risk_scorer.py:174 | [test_coverage] Function 'get_risk_scorer' has no corresponding test references |
| architecture | risk_scorer.py:182 | [test_coverage] Function 'reset_risk_scorer' has no corresponding test references |
| architecture | session_grants.py:30 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | session_grants.py:34 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | session_grants.py:39 | [test_coverage] Function 'request_grant' has no corresponding test references |
| architecture | session_grants.py:70 | [test_coverage] Function 'get_active_grants' has no corresponding test references |
| architecture | session_grants.py:78 | [test_coverage] Function 'has_grant' has no corresponding test references |
| architecture | session_grants.py:86 | [test_coverage] Function 'revoke_grants' has no corresponding test references |
| architecture | session_grants.py:100 | [test_coverage] Function '_row_to_grant' has no corresponding test references |
| architecture | session_grants.py:113 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | session_grants.py:125 | [test_coverage] Function 'get_session_grant_service' has no corresponding test references |
| architecture | session_grants.py:133 | [test_coverage] Function 'reset_session_grant_service' has no corresponding test references |
| architecture | sse_log_redaction.py:39 | [test_coverage] Function 'filter' has no corresponding test references |
| architecture | sse_log_redaction.py:58 | [test_coverage] Function '_scrub' has no corresponding test references |
| architecture | sse_log_redaction.py:64 | [test_coverage] Function 'install_token_redaction_filter' has no corresponding test references |
| architecture | sse_log_redaction.py:79 | [test_coverage] Function 'redact_token' has no corresponding test references |
| architecture | status.py:12 | [test_coverage] Function 'generate_token' has no corresponding test references |
| architecture | status.py:17 | [test_coverage] Function 'store_token' has no corresponding test references |
| architecture | status.py:52 | [test_coverage] Function 'validate_token' has no corresponding test references |
| architecture | status.py:80 | [test_coverage] Function 'lookup_token_failure' has no corresponding test references |
| architecture | status.py:100 | [test_coverage] Function 'cleanup_expired_tokens' has no corresponding test references |
| architecture | sync_points.py:35 | [test_coverage] Function '_parse_iso' has no corresponding test references |
| architecture | sync_points.py:45 | [test_coverage] Function '_load_registry' has no corresponding test references |
| architecture | sync_points.py:60 | [test_coverage] Function '_check_active_worktrees' has no corresponding test references |
| architecture | sync_points.py:81 | [test_coverage] Function 'get_sync_points_status' has no corresponding test references |
| architecture | teams.py:69 | [test_coverage] Function 'from_file' has no corresponding test references |
| architecture | teams.py:93 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | teams.py:129 | [test_coverage] Function 'get_agent' has no corresponding test references |
| architecture | teams.py:143 | [test_coverage] Function 'get_agents_with_capability' has no corresponding test references |
| architecture | teams.py:154 | [test_coverage] Function 'validate' has no corresponding test references |
| architecture | teams.py:180 | [test_coverage] Function 'get_teams_config' has no corresponding test references |
| architecture | teams.py:200 | [test_coverage] Function 'reset_teams_config' has no corresponding test references |
| architecture | telemetry.py:33 | [test_coverage] Function '_metrics_enabled' has no corresponding test references |
| architecture | telemetry.py:37 | [test_coverage] Function '_traces_enabled' has no corresponding test references |
| architecture | telemetry.py:41 | [test_coverage] Function '_prometheus_enabled' has no corresponding test references |
| architecture | telemetry.py:45 | [test_coverage] Function 'init_telemetry' has no corresponding test references |
| architecture | telemetry.py:74 | [test_coverage] Function '_init_metrics' has no corresponding test references |
| architecture | telemetry.py:145 | [test_coverage] Function '_init_traces' has no corresponding test references |
| architecture | telemetry.py:192 | [test_coverage] Function 'get_lock_meter' has no corresponding test references |
| architecture | telemetry.py:197 | [test_coverage] Function 'get_queue_meter' has no corresponding test references |
| architecture | telemetry.py:202 | [test_coverage] Function 'get_policy_meter' has no corresponding test references |
| architecture | telemetry.py:207 | [test_coverage] Function 'get_tracer' has no corresponding test references |
| architecture | telemetry.py:220 | [test_coverage] Function 'set_attribute' has no corresponding test references |
| architecture | telemetry.py:223 | [test_coverage] Function 'set_status' has no corresponding test references |
| architecture | telemetry.py:226 | [test_coverage] Function 'record_exception' has no corresponding test references |
| architecture | telemetry.py:229 | [test_coverage] Function '__enter__' has no corresponding test references |
| architecture | telemetry.py:232 | [test_coverage] Function '__exit__' has no corresponding test references |
| architecture | telemetry.py:239 | [test_coverage] Function 'start_span' has no corresponding test references |
| architecture | telemetry.py:252 | [test_coverage] Function 'get_prometheus_app' has no corresponding test references |
| architecture | telemetry.py:274 | [test_coverage] Function 'reset_telemetry' has no corresponding test references |
| architecture | watchdog.py:34 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | watchdog.py:55 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | watchdog.py:61 | [test_coverage] Function 'running' has no corresponding test references |
| architecture | watchdog.py:64 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | watchdog.py:72 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | watchdog.py:84 | [test_coverage] Function 'run_once' has no corresponding test references |
| architecture | watchdog.py:93 | [test_coverage] Function '_loop' has no corresponding test references |
| architecture | watchdog.py:107 | [test_coverage] Function '_check_stale_agents' has no corresponding test references |
| architecture | watchdog.py:166 | [test_coverage] Function '_check_aging_approvals' has no corresponding test references |
| architecture | watchdog.py:207 | [test_coverage] Function '_check_expiring_locks' has no corresponding test references |
| architecture | watchdog.py:235 | [test_coverage] Function '_cleanup_expired_tokens' has no corresponding test references |
| architecture | watchdog.py:252 | [test_coverage] Function '_check_event_bus_health' has no corresponding test references |
| architecture | watchdog.py:275 | [test_coverage] Function '_check_vendor_health' has no corresponding test references |
| architecture | watchdog.py:346 | [test_coverage] Function '_emit_event' has no corresponding test references |
| architecture | watchdog.py:391 | [test_coverage] Function 'get_watchdog' has no corresponding test references |
| architecture | watchdog.py:399 | [test_coverage] Function 'reset_watchdog' has no corresponding test references |
| architecture | work_queue.py:30 | [test_coverage] Function '_ensure_instruments' has no corresponding test references |
| architecture | work_queue.py:88 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | work_queue.py:89 | [test_coverage] Function 'parse_dt' has no corresponding test references |
| architecture | work_queue.py:133 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | work_queue.py:166 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | work_queue.py:187 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | work_queue.py:201 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | work_queue.py:205 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | work_queue.py:210 | [test_coverage] Function '_resolve_trust_level' has no corresponding test references |
| architecture | work_queue.py:225 | [test_coverage] Function 'claim' has no corresponding test references |
| architecture | work_queue.py:452 | [test_coverage] Function 'complete' has no corresponding test references |
| architecture | work_queue.py:603 | [test_coverage] Function 'submit' has no corresponding test references |
| architecture | work_queue.py:739 | [test_coverage] Function 'get_pending' has no corresponding test references |
| architecture | work_queue.py:763 | [test_coverage] Function 'get_task' has no corresponding test references |
| architecture | work_queue.py:775 | [test_coverage] Function 'get_my_tasks' has no corresponding test references |
| architecture | work_queue.py:799 | [test_coverage] Function 'cancel_task_convention' has no corresponding test references |
| architecture | work_queue.py:832 | [test_coverage] Function 'get_work_queue_service' has no corresponding test references |
| architecture | work_queue.py:840 | [test_coverage] Function 'reset_instruments' has no corresponding test references |
| architecture | worktrees_view.py:24 | [test_coverage] Function '_repo_root' has no corresponding test references |
| architecture | worktrees_view.py:29 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | worktrees_view.py:41 | [test_coverage] Function 'get_active_worktrees' has no corresponding test references |
| architecture | kanban-viz/src/App.tsx:14 | [test_coverage] Function 'App' has no corresponding test references |
| architecture | kanban-viz/src/components/Board.tsx:24 | [test_coverage] Function 'Board' has no corresponding test references |
| architecture | kanban-viz/src/components/Card.tsx:41 | [test_coverage] Function 'Card' has no corresponding test references |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:72 | [test_coverage] Function 'ClusterBadge' has no corresponding test references |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:81 | [test_coverage] Function 'ClusterBadgeInner' has no corresponding test references |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:130 | [test_coverage] Function 'ClusterHighlightWrapper' has no corresponding test references |
| architecture | kanban-viz/src/components/Column.tsx:25 | [test_coverage] Function 'Column' has no corresponding test references |
| architecture | kanban-viz/src/components/ConsentPrompt.tsx:12 | [test_coverage] Function 'ConsentPrompt' has no corresponding test references |
| architecture | kanban-viz/src/components/HiddenReposToggle.tsx:30 | [test_coverage] Function 'HiddenReposToggle' has no corresponding test references |
| architecture | kanban-viz/src/components/PRCardView.tsx:75 | [test_coverage] Function 'PRCardView' has no corresponding test references |
| architecture | kanban-viz/src/components/ProposalCardView.tsx:22 | [test_coverage] Function 'ProposalCardView' has no corresponding test references |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:69 | [test_coverage] Function 'PROriginFilter' has no corresponding test references |
| architecture | kanban-viz/src/components/RefreshButton.tsx:30 | [test_coverage] Function 'RefreshButton' has no corresponding test references |
| architecture | kanban-viz/src/components/RepoBadge.tsx:53 | [test_coverage] Function 'RepoBadge' has no corresponding test references |
| architecture | kanban-viz/src/components/SaveViewButton.tsx:53 | [test_coverage] Function 'SaveViewButton' has no corresponding test references |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:108 | [test_coverage] Function 'IssueSourceRow' has no corresponding test references |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:245 | [test_coverage] Function 'PRSourceRow' has no corresponding test references |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:393 | [test_coverage] Function 'PartialResultChip' has no corresponding test references |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:442 | [test_coverage] Function 'ProposalSourceRow' has no corresponding test references |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:554 | [test_coverage] Function 'SourceSwimlanes' has no corresponding test references |
| architecture | kanban-viz/src/components/SyncPointBanner.tsx:43 | [test_coverage] Function 'SyncPointBanner' has no corresponding test references |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:64 | [test_coverage] Function 'VendorSwimlanes' has no corresponding test references |
| architecture | kanban-viz/src/components/Card.tsx:28 | [test_coverage] Function 'relativeTime' has no corresponding test references |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:22 | [test_coverage] Function 'emitHighlight' has no corresponding test references |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:32 | [test_coverage] Function 'useHighlightState' has no corresponding test references |
| architecture | kanban-viz/src/components/HiddenReposToggle.tsx:16 | [test_coverage] Function 'shortForm' has no corresponding test references |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:28 | [test_coverage] Function 'loadFromStorage' has no corresponding test references |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:45 | [test_coverage] Function 'saveToStorage' has no corresponding test references |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:137 | [test_coverage] Function 'filterByOrigin' has no corresponding test references |
| architecture | kanban-viz/src/components/RefreshButton.tsx:134 | [test_coverage] Function 'formatRelative' has no corresponding test references |
| architecture | kanban-viz/src/components/RepoBadge.tsx:22 | [test_coverage] Function 'hashString' has no corresponding test references |
| architecture | kanban-viz/src/components/RepoBadge.tsx:33 | [test_coverage] Function 'repoToColor' has no corresponding test references |
| architecture | kanban-viz/src/components/SaveViewButton.tsx:43 | [test_coverage] Function 'slugify' has no corresponding test references |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:70 | [test_coverage] Function 'bucketIssues' has no corresponding test references |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:79 | [test_coverage] Function 'bucketPRs' has no corresponding test references |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:88 | [test_coverage] Function 'bucketProposals' has no corresponding test references |
| architecture | kanban-viz/src/components/SyncPointBanner.tsx:24 | [test_coverage] Function 'fetchSyncStatus' has no corresponding test references |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:29 | [test_coverage] Function 'extractVendor' has no corresponding test references |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:46 | [test_coverage] Function 'groupByVendor' has no corresponding test references |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:60 | [test_coverage] Function 'determineConsensus' has no corresponding test references |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:57 | [test_coverage] Function 'clusterBoardCards' has no corresponding test references |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:179 | [test_coverage] Function 'fetchPRs' has no corresponding test references |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:190 | [test_coverage] Function 'fetchProposals' has no corresponding test references |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:211 | [test_coverage] Function 'useBoardCards' has no corresponding test references |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:64 | [test_coverage] Function 'fetchIssuesForSingleChange' has no corresponding test references |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:96 | [test_coverage] Function 'fetchIssuesUnioned' has no corresponding test references |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:114 | [test_coverage] Function 'mintEventsToken' has no corresponding test references |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:132 | [test_coverage] Function 'useCoordinator' has no corresponding test references |
| architecture | kanban-viz/src/lib/coordinator-types.ts:208 | [test_coverage] Function 'assertNever' has no corresponding test references |
| architecture | kanban-viz/src/lib/coordinator-types.ts:218 | [test_coverage] Function 'issueStatusToColumn' has no corresponding test references |
| architecture | kanban-viz/src/lib/coordinator-types.ts:236 | [test_coverage] Function 'prStatusToColumn' has no corresponding test references |
| architecture | kanban-viz/src/lib/coordinator-types.ts:250 | [test_coverage] Function 'proposalStatusToColumn' has no corresponding test references |
| architecture | kanban-viz/src/lib/coordinator-types.ts:295 | [test_coverage] Function 'toIssueCard' has no corresponding test references |
| architecture | kanban-viz/src/lib/coordinator-types.ts:336 | [test_coverage] Function 'deriveIssueRepo' has no corresponding test references |
| architecture | kanban-viz/src/lib/coordinator-types.ts:364 | [test_coverage] Function 'getClusterKey' has no corresponding test references |
| architecture | kanban-viz/src/lib/reversibility.ts:46 | [test_coverage] Function 'classify' has no corresponding test references |
| architecture | kanban-viz/src/lib/reversibility.ts:54 | [test_coverage] Function 'classifyOrDefault' has no corresponding test references |
| architecture | kanban-viz/src/lib/reversibility.ts:59 | [test_coverage] Function 'requiresConsent' has no corresponding test references |
| architecture | kanban-viz/src/lib/runtime.ts:12 | [test_coverage] Function 'isTauri' has no corresponding test references |
| architecture | kanban-viz/src/lib/runtime.ts:21 | [test_coverage] Function 'isBrowser' has no corresponding test references |
| architecture | kanban-viz/src/lib/saveView.ts:35 | [test_coverage] Function 'saveView' has no corresponding test references |
| architecture | kanban-viz/src/lib/saveView.ts:47 | [test_coverage] Function 'saveBrowser' has no corresponding test references |
| architecture | kanban-viz/src/lib/saveView.ts:68 | [test_coverage] Function 'saveTauri' has no corresponding test references |
| architecture | __init__.py:1 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1 | [orphan] 'agents_config' is unreachable from any entrypoint or test |
| architecture | approval.py:1 | [orphan] 'approval' is unreachable from any entrypoint or test |
| architecture | assurance.py:1 | [orphan] 'assurance' is unreachable from any entrypoint or test |
| architecture | audit.py:1 | [orphan] 'audit' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:1 | [orphan] 'audit_triage' is unreachable from any entrypoint or test |
| architecture | axi_output.py:1 | [orphan] 'axi_output' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:1 | [orphan] 'cloudflare_access' is unreachable from any entrypoint or test |
| architecture | code_search.py:1 | [orphan] 'code_search' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:1 | [orphan] 'code_search_authorization' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:1 | [orphan] 'code_search_runtime' is unreachable from any entrypoint or test |
| architecture | config.py:1 | [orphan] 'config' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:1 | [orphan] 'coordination_api' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:1 | [orphan] 'coordination_cli' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1 | [orphan] 'coordination_mcp' is unreachable from any entrypoint or test |
| architecture | db.py:1 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:1 | [orphan] 'db_postgres' is unreachable from any entrypoint or test |
| architecture | discovery.py:1 | [orphan] 'discovery' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:1 | [orphan] 'docker_manager' is unreachable from any entrypoint or test |
| architecture | event_bus.py:1 | [orphan] 'event_bus' is unreachable from any entrypoint or test |
| architecture | event_stream.py:1 | [orphan] 'event_stream' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:1 | [orphan] 'feature_flags' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:1 | [orphan] 'feature_registry' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:1 | [orphan] 'git_adapter' is unreachable from any entrypoint or test |
| architecture | github_classifier.py:1 | [orphan] 'github_classifier' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:1 | [orphan] 'github_coordination' is unreachable from any entrypoint or test |
| architecture | github_openspec_fetcher.py:1 | [orphan] 'github_openspec_fetcher' is unreachable from any entrypoint or test |
| architecture | github_prs_api.py:1 | [orphan] 'github_prs_api' is unreachable from any entrypoint or test |
| architecture | guardrails.py:1 | [orphan] 'guardrails' is unreachable from any entrypoint or test |
| architecture | handoffs.py:1 | [orphan] 'handoffs' is unreachable from any entrypoint or test |
| architecture | help_service.py:1 | [orphan] 'help_service' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1 | [orphan] 'http_proxy' is unreachable from any entrypoint or test |
| architecture | issue_service.py:1 | [orphan] 'issue_service' is unreachable from any entrypoint or test |
| architecture | kanban_viz_files.py:1 | [orphan] 'kanban_viz_files' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:1 | [orphan] 'langfuse_middleware' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:1 | [orphan] 'langfuse_tracing' is unreachable from any entrypoint or test |
| architecture | locks.py:1 | [orphan] 'locks' is unreachable from any entrypoint or test |
| architecture | memory.py:1 | [orphan] 'memory' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:1 | [orphan] 'merge_queue' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1 | [orphan] 'merge_train' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:1 | [orphan] 'merge_train_service' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:1 | [orphan] 'merge_train_types' is unreachable from any entrypoint or test |
| architecture | merge_watcher.py:1 | [orphan] 'merge_watcher' is unreachable from any entrypoint or test |
| architecture | migrations.py:1 | [orphan] 'migrations' is unreachable from any entrypoint or test |
| architecture | model_routing/__init__.py:1 | [orphan] 'model_routing' is unreachable from any entrypoint or test |
| architecture | model_routing/exploration.py:1 | [orphan] 'model_routing.exploration' is unreachable from any entrypoint or test |
| architecture | model_routing/feedback.py:1 | [orphan] 'model_routing.feedback' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:1 | [orphan] 'model_routing.resolver' is unreachable from any entrypoint or test |
| architecture | network_policies.py:1 | [orphan] 'network_policies' is unreachable from any entrypoint or test |
| architecture | notifications/__init__.py:1 | [orphan] 'notifications' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:1 | [orphan] 'notifications.base' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:1 | [orphan] 'notifications.gmail' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:1 | [orphan] 'notifications.notifier' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:1 | [orphan] 'notifications.relay' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:1 | [orphan] 'notifications.telegram' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:1 | [orphan] 'notifications.templates' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:1 | [orphan] 'notifications.webhook' is unreachable from any entrypoint or test |
| architecture | openspec_proposals_api.py:1 | [orphan] 'openspec_proposals_api' is unreachable from any entrypoint or test |
| architecture | openspec_sources.py:1 | [orphan] 'openspec_sources' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:1 | [orphan] 'policy_engine' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:1 | [orphan] 'policy_sync' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:1 | [orphan] 'port_allocator' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:1 | [orphan] 'profile_loader' is unreachable from any entrypoint or test |
| architecture | profiles.py:1 | [orphan] 'profiles' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:1 | [orphan] 'refresh_rpc_client' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:1 | [orphan] 'risk_scorer' is unreachable from any entrypoint or test |
| architecture | session_grants.py:1 | [orphan] 'session_grants' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:1 | [orphan] 'sse_log_redaction' is unreachable from any entrypoint or test |
| architecture | status.py:1 | [orphan] 'status' is unreachable from any entrypoint or test |
| architecture | sync_points.py:1 | [orphan] 'sync_points' is unreachable from any entrypoint or test |
| architecture | teams.py:1 | [orphan] 'teams' is unreachable from any entrypoint or test |
| architecture | telemetry.py:1 | [orphan] 'telemetry' is unreachable from any entrypoint or test |
| architecture | watchdog.py:1 | [orphan] 'watchdog' is unreachable from any entrypoint or test |
| architecture | work_queue.py:1 | [orphan] 'work_queue' is unreachable from any entrypoint or test |
| architecture | worktrees_view.py:1 | [orphan] 'worktrees_view' is unreachable from any entrypoint or test |
| architecture | agents_config.py:413 | [orphan] 'PollConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:431 | [orphan] 'ModeConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:440 | [orphan] 'CliConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:460 | [orphan] 'SdkConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:477 | [orphan] 'AgentEntry' is unreachable from any entrypoint or test |
| architecture | agents_config.py:500 | [orphan] 'EscalationConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:514 | [orphan] 'ArchetypeConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:529 | [orphan] 'PhaseMappingEntry' is unreachable from any entrypoint or test |
| architecture | agents_config.py:543 | [orphan] 'ModelSpec' is unreachable from any entrypoint or test |
| architecture | agents_config.py:557 | [orphan] 'ResolvedArchetype' is unreachable from any entrypoint or test |
| architecture | agents_config.py:573 | [orphan] 'ProviderModelMappingError' is unreachable from any entrypoint or test |
| architecture | approval.py:15 | [orphan] 'ApprovalRequest' is unreachable from any entrypoint or test |
| architecture | approval.py:32 | [orphan] 'ApprovalService' is unreachable from any entrypoint or test |
| architecture | audit.py:18 | [orphan] 'AuditEntry' is unreachable from any entrypoint or test |
| architecture | audit.py:56 | [orphan] 'AuditResult' is unreachable from any entrypoint or test |
| architecture | audit.py:72 | [orphan] 'AuditService' is unreachable from any entrypoint or test |
| architecture | audit.py:206 | [orphan] 'AuditTimer' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:52 | [orphan] 'AuditTriageConfig' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:67 | [orphan] 'AuditTriageBuffer' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:56 | [orphan] 'CloudflareAccessError' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:60 | [orphan] 'CloudflareAccessVerifier' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:125 | [orphan] 'CloudflareAccessMiddleware' is unreachable from any entrypoint or test |
| architecture | code_search.py:64 | [orphan] 'CodeSearchError' is unreachable from any entrypoint or test |
| architecture | code_search.py:71 | [orphan] 'CodeSearchForbiddenError' is unreachable from any entrypoint or test |
| architecture | code_search.py:76 | [orphan] 'CodeSearchState' is unreachable from any entrypoint or test |
| architecture | code_search.py:85 | [orphan] '_ClosedModel' is unreachable from any entrypoint or test |
| architecture | code_search.py:89 | [orphan] 'SearchNamespace' is unreachable from any entrypoint or test |
| architecture | code_search.py:100 | [orphan] 'ExplicitScope' is unreachable from any entrypoint or test |
| architecture | code_search.py:113 | [orphan] 'WorkPackageScope' is unreachable from any entrypoint or test |
| architecture | code_search.py:130 | [orphan] 'CodeSearchRequest' is unreachable from any entrypoint or test |
| architecture | code_search.py:172 | [orphan] 'RequestedIdentity' is unreachable from any entrypoint or test |
| architecture | code_search.py:179 | [orphan] 'IndexProvenance' is unreachable from any entrypoint or test |
| architecture | code_search.py:192 | [orphan] 'ScopeDisposition' is unreachable from any entrypoint or test |
| architecture | code_search.py:198 | [orphan] 'CodeSearchHit' is unreachable from any entrypoint or test |
| architecture | code_search.py:211 | [orphan] 'Fallback' is unreachable from any entrypoint or test |
| architecture | code_search.py:217 | [orphan] 'CodeSearchResponse' is unreachable from any entrypoint or test |
| architecture | code_search.py:261 | [orphan] 'CodeSearchService' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:18 | [orphan] 'ScopeAuthorizationError' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:22 | [orphan] 'ScopeForbiddenError' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:26 | [orphan] 'ScopeRejectedError' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:31 | [orphan] 'ExplicitScopeRequest' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:41 | [orphan] 'WorkPackageScopeRequest' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:57 | [orphan] 'PrincipalCodeSearchGrant' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:83 | [orphan] 'WorkPackageScopeRecord' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:104 | [orphan] 'WorkPackageScopeResolver' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:118 | [orphan] 'EffectiveCodeSearchScope' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:391 | [orphan] '_GlobToken' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:57 | [orphan] 'CodeSearchOverloadedError' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:67 | [orphan] 'CodeSearchStatus' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:104 | [orphan] 'CodeSearchRuntimeConfig' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:147 | [orphan] '_Cache' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:157 | [orphan] 'CodeSearchRuntime' is unreachable from any entrypoint or test |
| architecture | config.py:50 | [orphan] 'SupabaseConfig' is unreachable from any entrypoint or test |
| architecture | config.py:75 | [orphan] 'AgentConfig' is unreachable from any entrypoint or test |
| architecture | config.py:99 | [orphan] 'LockConfig' is unreachable from any entrypoint or test |
| architecture | config.py:113 | [orphan] 'PostgresConfig' is unreachable from any entrypoint or test |
| architecture | config.py:130 | [orphan] 'DatabaseConfig' is unreachable from any entrypoint or test |
| architecture | config.py:145 | [orphan] 'GuardrailsConfig' is unreachable from any entrypoint or test |
| architecture | config.py:165 | [orphan] 'ProfilesConfig' is unreachable from any entrypoint or test |
| architecture | config.py:189 | [orphan] 'AuditConfig' is unreachable from any entrypoint or test |
| architecture | config.py:204 | [orphan] 'NetworkPolicyConfig' is unreachable from any entrypoint or test |
| architecture | config.py:217 | [orphan] 'PolicyEngineConfig' is unreachable from any entrypoint or test |
| architecture | config.py:241 | [orphan] 'OpenBaoConfig' is unreachable from any entrypoint or test |
| architecture | config.py:323 | [orphan] 'ObservabilityConfig' is unreachable from any entrypoint or test |
| architecture | config.py:340 | [orphan] 'LangfuseConfig' is unreachable from any entrypoint or test |
| architecture | config.py:374 | [orphan] 'PortAllocatorConfig' is unreachable from any entrypoint or test |
| architecture | config.py:393 | [orphan] 'ApiConfig' is unreachable from any entrypoint or test |
| architecture | config.py:448 | [orphan] 'CloudflareAccessConfig' is unreachable from any entrypoint or test |
| architecture | config.py:502 | [orphan] 'ApprovalConfig' is unreachable from any entrypoint or test |
| architecture | config.py:525 | [orphan] 'PolicySyncConfig' is unreachable from any entrypoint or test |
| architecture | config.py:547 | [orphan] 'RiskScoringConfig' is unreachable from any entrypoint or test |
| architecture | config.py:574 | [orphan] 'SessionGrantsConfig' is unreachable from any entrypoint or test |
| architecture | config.py:628 | [orphan] 'Config' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:72 | [orphan] '_CodeSearchProblemError' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:86 | [orphan] 'LockAcquireRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:95 | [orphan] 'LockReleaseRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:100 | [orphan] 'MemoryStoreRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:111 | [orphan] 'MemoryQueryRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:118 | [orphan] 'WorkClaimRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:124 | [orphan] 'WorkCompleteRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:132 | [orphan] 'WorkSubmitRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:141 | [orphan] 'WorkGetTaskRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:145 | [orphan] 'IssueCreateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:156 | [orphan] 'IssueListRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:165 | [orphan] 'IssueUpdateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:176 | [orphan] 'IssueCloseRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:182 | [orphan] 'IssueCommentRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:187 | [orphan] 'GuardrailsCheckRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:192 | [orphan] 'AuditQueryParams' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:198 | [orphan] 'HandoffWriteRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:210 | [orphan] 'HandoffReadRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:215 | [orphan] 'PolicyCheckRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:223 | [orphan] 'PolicyValidateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:227 | [orphan] 'PortAllocateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:231 | [orphan] 'PortReleaseRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:235 | [orphan] 'ApprovalDecisionRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:241 | [orphan] 'PolicyRollbackRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:245 | [orphan] 'FeatureRegisterRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:255 | [orphan] 'FeatureDeregisterRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:260 | [orphan] 'FeatureConflictsRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:265 | [orphan] 'StatusReportRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:289 | [orphan] 'ResolveForPhaseRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:311 | [orphan] 'MergeQueueEnqueueRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:316 | [orphan] 'DiscoveryRegisterRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:326 | [orphan] 'DiscoveryHeartbeatRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:332 | [orphan] 'DiscoveryCleanupRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:338 | [orphan] 'GenEvalValidateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:342 | [orphan] 'GenEvalCreateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:350 | [orphan] 'GenEvalRunRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:356 | [orphan] 'IssueSearchRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:363 | [orphan] 'IssueReadyRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:370 | [orphan] 'PermissionRequestRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:377 | [orphan] 'ApprovalSubmitRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:386 | [orphan] 'MergeTrainEjectRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:391 | [orphan] 'MergeTrainReportResultRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:397 | [orphan] 'AffectedTestsRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:403 | [orphan] 'EventsAuthRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:408 | [orphan] 'PatchLabelsRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:413 | [orphan] 'KickAgentRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:427 | [orphan] 'SavedViewRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:431 | [orphan] 'KanbanAuditRequest' is unreachable from any entrypoint or test |
| architecture | db.py:25 | [orphan] 'DatabaseClient' is unreachable from any entrypoint or test |
| architecture | db.py:73 | [orphan] 'SupabaseClient' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:78 | [orphan] 'DirectPostgresClient' is unreachable from any entrypoint or test |
| architecture | discovery.py:20 | [orphan] 'AgentInfo' is unreachable from any entrypoint or test |
| architecture | discovery.py:61 | [orphan] 'RegisterResult' is unreachable from any entrypoint or test |
| architecture | discovery.py:76 | [orphan] 'DiscoverResult' is unreachable from any entrypoint or test |
| architecture | discovery.py:88 | [orphan] 'HeartbeatResult' is unreachable from any entrypoint or test |
| architecture | discovery.py:105 | [orphan] 'CleanupResult' is unreachable from any entrypoint or test |
| architecture | discovery.py:121 | [orphan] 'DiscoveryService' is unreachable from any entrypoint or test |
| architecture | event_bus.py:37 | [orphan] 'CoordinatorEvent' is unreachable from any entrypoint or test |
| architecture | event_bus.py:110 | [orphan] 'EventBusService' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:61 | [orphan] 'FlagsConfigError' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:69 | [orphan] 'InvalidFlagNameError' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:79 | [orphan] 'Flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:153 | [orphan] 'FeatureFlagService' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:26 | [orphan] 'Feasibility' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:35 | [orphan] 'Feature' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:75 | [orphan] 'RegisterResult' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:94 | [orphan] 'DeregisterResult' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:113 | [orphan] 'ConflictReport' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:124 | [orphan] 'FeatureRegistryService' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:51 | [orphan] 'InvalidRefNameError' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:55 | [orphan] 'GitVersionError' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:65 | [orphan] 'MergeTreeResult' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:79 | [orphan] 'FastForwardResult' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:88 | [orphan] 'ChangedFiles' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:102 | [orphan] 'GitAdapter' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:176 | [orphan] 'SubprocessGitAdapter' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:30 | [orphan] 'BranchInfo' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:61 | [orphan] 'LabelLock' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:69 | [orphan] 'WebhookSyncResult' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:89 | [orphan] 'GitHubCoordinationService' is unreachable from any entrypoint or test |
| architecture | guardrails.py:146 | [orphan] 'GuardrailPattern' is unreachable from any entrypoint or test |
| architecture | guardrails.py:167 | [orphan] 'GuardrailViolation' is unreachable from any entrypoint or test |
| architecture | guardrails.py:190 | [orphan] 'GuardrailResult' is unreachable from any entrypoint or test |
| architecture | guardrails.py:268 | [orphan] 'GuardrailsService' is unreachable from any entrypoint or test |
| architecture | handoffs.py:22 | [orphan] 'HandoffDocument' is unreachable from any entrypoint or test |
| architecture | handoffs.py:59 | [orphan] 'WriteHandoffResult' is unreachable from any entrypoint or test |
| architecture | handoffs.py:80 | [orphan] 'ReadHandoffResult' is unreachable from any entrypoint or test |
| architecture | handoffs.py:95 | [orphan] 'HandoffService' is unreachable from any entrypoint or test |
| architecture | help_service.py:20 | [orphan] 'HelpTopic' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:92 | [orphan] 'HttpProxyConfig' is unreachable from any entrypoint or test |
| architecture | issue_service.py:47 | [orphan] 'Issue' is unreachable from any entrypoint or test |
| architecture | issue_service.py:154 | [orphan] 'Comment' is unreachable from any entrypoint or test |
| architecture | issue_service.py:186 | [orphan] 'IssueService' is unreachable from any entrypoint or test |
| architecture | kanban_viz_files.py:107 | [orphan] 'SchemaValidationError' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:29 | [orphan] 'LangfuseTracingMiddleware' is unreachable from any entrypoint or test |
| architecture | locks.py:89 | [orphan] 'Lock' is unreachable from any entrypoint or test |
| architecture | locks.py:119 | [orphan] 'LockResult' is unreachable from any entrypoint or test |
| architecture | locks.py:149 | [orphan] 'LockService' is unreachable from any entrypoint or test |
| architecture | memory.py:36 | [orphan] 'EpisodicMemory' is unreachable from any entrypoint or test |
| architecture | memory.py:72 | [orphan] 'MemoryResult' is unreachable from any entrypoint or test |
| architecture | memory.py:91 | [orphan] 'RecallResult' is unreachable from any entrypoint or test |
| architecture | memory.py:105 | [orphan] 'MemoryService' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:37 | [orphan] 'MergeStatus' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:49 | [orphan] 'PreMergeCheckResult' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:60 | [orphan] 'MergeQueueEntry' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:88 | [orphan] 'MergeQueueService' is unreachable from any entrypoint or test |
| architecture | merge_train.py:69 | [orphan] 'TrainAuthorizationError' is unreachable from any entrypoint or test |
| architecture | merge_train.py:77 | [orphan] 'TrainDeadlockError' is unreachable from any entrypoint or test |
| architecture | merge_train.py:92 | [orphan] 'PartitionResult' is unreachable from any entrypoint or test |
| architecture | merge_train.py:622 | [orphan] 'EjectResult' is unreachable from any entrypoint or test |
| architecture | merge_train.py:851 | [orphan] '_MergeNode' is unreachable from any entrypoint or test |
| architecture | merge_train.py:868 | [orphan] 'WaveMergeResult' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1121 | [orphan] 'CrashRecoveryResult' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:115 | [orphan] 'MergeTrainService' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:419 | [orphan] 'MergeTrainSweeper' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:58 | [orphan] 'MergeTrainStatus' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:98 | [orphan] 'TrainEntry' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:151 | [orphan] 'TrainPartition' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:169 | [orphan] 'CrossPartitionEntry' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:183 | [orphan] 'TrainComposition' is unreachable from any entrypoint or test |
| architecture | merge_watcher.py:24 | [orphan] 'MergeWatcher' is unreachable from any entrypoint or test |
| architecture | model_routing/exploration.py:25 | [orphan] 'ExplorationBudget' is unreachable from any entrypoint or test |
| architecture | model_routing/exploration.py:42 | [orphan] 'Selection' is unreachable from any entrypoint or test |
| architecture | model_routing/feedback.py:52 | [orphan] 'FeedbackObservation' is unreachable from any entrypoint or test |
| architecture | model_routing/feedback.py:65 | [orphan] 'PosteriorEstimate' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:39 | [orphan] 'Weights' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:59 | [orphan] 'Posterior' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:70 | [orphan] 'CandidateInput' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:93 | [orphan] 'ScoredCandidate' is unreachable from any entrypoint or test |
| architecture | network_policies.py:15 | [orphan] 'AccessDecision' is unreachable from any entrypoint or test |
| architecture | network_policies.py:33 | [orphan] 'NetworkPolicyService' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:11 | [orphan] 'NotificationChannel' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:29 | [orphan] 'GmailChannelFake' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:46 | [orphan] 'GmailChannel' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:30 | [orphan] 'NotifierService' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:20 | [orphan] 'TelegramChannel' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:18 | [orphan] 'WebhookChannel' is unreachable from any entrypoint or test |
| architecture | openspec_sources.py:38 | [orphan] 'SourceDescriptor' is unreachable from any entrypoint or test |
| architecture | openspec_sources.py:47 | [orphan] 'ParseWarning' is unreachable from any entrypoint or test |
| architecture | openspec_sources.py:55 | [orphan] 'LocalSourceCache' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:84 | [orphan] 'PolicyDecision' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:102 | [orphan] 'ValidationResult' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:109 | [orphan] 'NativePolicyEngine' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:455 | [orphan] 'CedarPolicyEngine' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:17 | [orphan] 'PolicySyncService' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:37 | [orphan] 'PgListenNotifyPolicySyncService' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:24 | [orphan] 'PortAllocation' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:52 | [orphan] 'PortAllocatorService' is unreachable from any entrypoint or test |
| architecture | profiles.py:20 | [orphan] 'AgentProfile' is unreachable from any entrypoint or test |
| architecture | profiles.py:53 | [orphan] 'ProfileResult' is unreachable from any entrypoint or test |
| architecture | profiles.py:77 | [orphan] 'OperationCheck' is unreachable from any entrypoint or test |
| architecture | profiles.py:91 | [orphan] 'ProfilesService' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:59 | [orphan] 'RefreshClientUnavailable' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:78 | [orphan] '_Runner' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:124 | [orphan] 'RefreshRpcClient' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:33 | [orphan] 'RiskScore' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:41 | [orphan] 'RiskScorer' is unreachable from any entrypoint or test |
| architecture | session_grants.py:14 | [orphan] 'PermissionGrant' is unreachable from any entrypoint or test |
| architecture | session_grants.py:27 | [orphan] 'SessionGrantService' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:31 | [orphan] '_TokenRedactionFilter' is unreachable from any entrypoint or test |
| architecture | teams.py:48 | [orphan] 'AgentDefinition' is unreachable from any entrypoint or test |
| architecture | teams.py:58 | [orphan] 'TeamsConfig' is unreachable from any entrypoint or test |
| architecture | telemetry.py:217 | [orphan] '_NoOpSpan' is unreachable from any entrypoint or test |
| architecture | watchdog.py:31 | [orphan] 'WatchdogService' is unreachable from any entrypoint or test |
| architecture | work_queue.py:68 | [orphan] 'Task' is unreachable from any entrypoint or test |
| architecture | work_queue.py:120 | [orphan] 'ClaimResult' is unreachable from any entrypoint or test |
| architecture | work_queue.py:157 | [orphan] 'CompleteResult' is unreachable from any entrypoint or test |
| architecture | work_queue.py:180 | [orphan] 'SubmitResult' is unreachable from any entrypoint or test |
| architecture | work_queue.py:198 | [orphan] 'WorkQueueService' is unreachable from any entrypoint or test |
| architecture | agents_config.py:576 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | agents_config.py:732 | [orphan] '_resolve_api_key_from_openbao' is unreachable from any entrypoint or test |
| architecture | agents_config.py:783 | [orphan] 'get_api_key_identities' is unreachable from any entrypoint or test |
| architecture | agents_config.py:840 | [orphan] 'get_mcp_env' is unreachable from any entrypoint or test |
| architecture | agents_config.py:894 | [orphan] 'get_agent_config' is unreachable from any entrypoint or test |
| architecture | agents_config.py:902 | [orphan] 'reset_agents_config' is unreachable from any entrypoint or test |
| architecture | agents_config.py:979 | [orphan] 'get_agent_isolation' is unreachable from any entrypoint or test |
| architecture | agents_config.py:995 | [orphan] '_default_archetypes_path' is unreachable from any entrypoint or test |
| architecture | agents_config.py:999 | [orphan] 'load_archetypes_config' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1083 | [orphan] 'get_archetype' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1097 | [orphan] 'get_phase_mapping' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1109 | [orphan] 'reset_archetypes_config' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1117 | [orphan] '_normalize_provider_model_map' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1144 | [orphan] 'get_provider_model_map' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1151 | [orphan] '_tier_entry_to_spec' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1166 | [orphan] 'resolve_provider_model_spec' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1219 | [orphan] 'resolve_provider_model' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1239 | [orphan] 'compose_prompt' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1255 | [orphan] '_unique_dir_prefixes' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1274 | [orphan] 'resolve_model' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1313 | [orphan] '_resolve_model_spec' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1322 | [orphan] '_finalize' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1379 | [orphan] 'resolve_archetype_for_phase' is unreachable from any entrypoint or test |
| architecture | approval.py:35 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | approval.py:39 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | approval.py:44 | [orphan] 'submit_request' is unreachable from any entrypoint or test |
| architecture | approval.py:89 | [orphan] 'check_request' is unreachable from any entrypoint or test |
| architecture | approval.py:99 | [orphan] 'decide_request' is unreachable from any entrypoint or test |
| architecture | approval.py:137 | [orphan] 'expire_stale_requests' is unreachable from any entrypoint or test |
| architecture | approval.py:154 | [orphan] 'list_pending' is unreachable from any entrypoint or test |
| architecture | approval.py:166 | [orphan] '_row_to_request' is unreachable from any entrypoint or test |
| architecture | approval.py:186 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | approval.py:207 | [orphan] 'reset_approval_service' is unreachable from any entrypoint or test |
| architecture | audit.py:34 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | audit.py:64 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | audit.py:75 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | audit.py:79 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | audit.py:84 | [orphan] 'log_operation' is unreachable from any entrypoint or test |
| architecture | audit.py:151 | [orphan] '_insert_audit_entry' is unreachable from any entrypoint or test |
| architecture | audit.py:159 | [orphan] 'query' is unreachable from any entrypoint or test |
| architecture | audit.py:201 | [orphan] 'timed' is unreachable from any entrypoint or test |
| architecture | audit.py:209 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | audit.py:214 | [orphan] '__aenter__' is unreachable from any entrypoint or test |
| architecture | audit.py:218 | [orphan] '__aexit__' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:75 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:79 | [orphan] 'push' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:91 | [orphan] 'drain_all' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:106 | [orphan] 'validate_finding' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:123 | [orphan] 'load_prompt' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:140 | [orphan] 'drain_and_classify' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:259 | [orphan] 'get_triage_buffer' is unreachable from any entrypoint or test |
| architecture | audit_triage.py:267 | [orphan] 'reset_triage_buffer' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:68 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:91 | [orphan] '_signing_key' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:106 | [orphan] 'verify' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:134 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:146 | [orphan] '_is_exempt' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:156 | [orphan] '__call__' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:185 | [orphan] '_deny' is unreachable from any entrypoint or test |
| architecture | cloudflare_access.py:192 | [orphan] 'install_cloudflare_access' is unreachable from any entrypoint or test |
| architecture | code_search.py:94 | [orphan] 'validate_main_key' is unreachable from any entrypoint or test |
| architecture | code_search.py:107 | [orphan] 'validate_patterns' is unreachable from any entrypoint or test |
| architecture | code_search.py:121 | [orphan] 'validate_reference' is unreachable from any entrypoint or test |
| architecture | code_search.py:144 | [orphan] 'validate_languages' is unreachable from any entrypoint or test |
| architecture | code_search.py:158 | [orphan] 'validate_paths' is unreachable from any entrypoint or test |
| architecture | code_search.py:166 | [orphan] 'require_non_main_index' is unreachable from any entrypoint or test |
| architecture | code_search.py:227 | [orphan] 'validate_state_invariants' is unreachable from any entrypoint or test |
| architecture | code_search.py:264 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | code_search.py:282 | [orphan] 'search' is unreachable from any entrypoint or test |
| architecture | code_search.py:451 | [orphan] '_select_index' is unreachable from any entrypoint or test |
| architecture | code_search.py:463 | [orphan] 'metrics_snapshot' is unreachable from any entrypoint or test |
| architecture | code_search.py:468 | [orphan] '_observe_response' is unreachable from any entrypoint or test |
| architecture | code_search.py:482 | [orphan] '_observe' is unreachable from any entrypoint or test |
| architecture | code_search.py:517 | [orphan] '_authorization_scope' is unreachable from any entrypoint or test |
| architecture | code_search.py:532 | [orphan] '_index_provenance' is unreachable from any entrypoint or test |
| architecture | code_search.py:550 | [orphan] '_hit' is unreachable from any entrypoint or test |
| architecture | code_search.py:564 | [orphan] '_non_ready_response' is unreachable from any entrypoint or test |
| architecture | code_search.py:585 | [orphan] 'get_code_search_service' is unreachable from any entrypoint or test |
| architecture | code_search.py:591 | [orphan] 'init_code_search_service' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:35 | [orphan] '__post_init__' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:46 | [orphan] '__post_init__' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:67 | [orphan] '__post_init__' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:93 | [orphan] '__post_init__' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:105 | [orphan] '__call__' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:128 | [orphan] 'allow_path_regexes' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:136 | [orphan] 'deny_path_regexes' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:140 | [orphan] 'path_regexes' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:143 | [orphan] 'allows' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:153 | [orphan] 'authorize_code_search_scope' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:237 | [orphan] 'validate_safe_glob' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:245 | [orphan] 'glob_to_postgres_regex' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:280 | [orphan] '_matches_any' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:284 | [orphan] '_regex_union' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:291 | [orphan] '_validate_patterns' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:297 | [orphan] '_canonical_patterns' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:306 | [orphan] '_deduplicated' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:310 | [orphan] '_require_nonempty_effective_scope' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:381 | [orphan] '_require_compilable_scope_patterns' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:400 | [orphan] '_compile_glob_layer' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:404 | [orphan] '_compile_glob' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:443 | [orphan] '_glob_layer_start' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:450 | [orphan] '_glob_layer_closure' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:467 | [orphan] '_glob_layer_step' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:493 | [orphan] '_glob_layer_accepts' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:497 | [orphan] '_scope_alphabet' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:516 | [orphan] '_next_segment_state' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:528 | [orphan] '_valid_reference' is unreachable from any entrypoint or test |
| architecture | code_search_authorization.py:534 | [orphan] '_is_normalized_relative' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:50 | [orphan] 'code_search_enabled' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:63 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:78 | [orphan] 'validate_truth_table' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:99 | [orphan] 'to_dict' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:115 | [orphan] '__post_init__' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:129 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:152 | [orphan] 'clear' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:160 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:176 | [orphan] 'create' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:198 | [orphan] 'provider_factory' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:242 | [orphan] 'embed_one' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:277 | [orphan] 'state_counts' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:282 | [orphan] 'status_snapshot' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:291 | [orphan] 'status' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:299 | [orphan] '_status_after_lock' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:352 | [orphan] '_finish_initialization' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:361 | [orphan] '_record_status' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:391 | [orphan] 'search' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:432 | [orphan] 'invalidate' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:438 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:461 | [orphan] '_provider_ready' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:484 | [orphan] '_cache_failure' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:493 | [orphan] '_close_pool' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:505 | [orphan] '_close_provider' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:524 | [orphan] '_assert_owner' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:532 | [orphan] 'start_code_search_runtime' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:541 | [orphan] 'stop_code_search_runtime' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:554 | [orphan] 'set_code_search_runtime' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:574 | [orphan] '_status' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:583 | [orphan] '_duration_bucket' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:634 | [orphan] '_pool_from_env' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:644 | [orphan] '_provider_from_env' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:670 | [orphan] '_grant_resolver_from_env' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:688 | [orphan] '_float_env' is unreachable from any entrypoint or test |
| architecture | code_search_runtime.py:692 | [orphan] '_int_env' is unreachable from any entrypoint or test |
| architecture | config.py:58 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:83 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:106 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:121 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:137 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:152 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:173 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:196 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:210 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:226 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:263 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:274 | [orphan] 'is_enabled' is unreachable from any entrypoint or test |
| architecture | config.py:278 | [orphan] 'create_client' is unreachable from any entrypoint or test |
| architecture | config.py:331 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:360 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:383 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:405 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:468 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:667 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:731 | [orphan] 'reset_config' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:75 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:441 | [orphan] '_extract_api_key' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:458 | [orphan] '_principal_for_api_key' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:471 | [orphan] 'verify_api_key' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:493 | [orphan] 'optional_api_key' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:577 | [orphan] 'create_coordination_api' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:599 | [orphan] 'lifespan' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:724 | [orphan] 'code_search_problem_handler' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:736 | [orphan] 'request_validation_handler' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:3439 | [orphan] 'verify_code_search_principal' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:3494 | [orphan] 'main' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:24 | [orphan] '_run' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:29 | [orphan] '_output' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:48 | [orphan] '_print_dict' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:72 | [orphan] '_error' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:78 | [orphan] '_emit_list' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:135 | [orphan] 'cmd_health' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:162 | [orphan] 'cmd_feature_register' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:185 | [orphan] 'cmd_feature_deregister' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:202 | [orphan] 'cmd_feature_show' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:223 | [orphan] 'cmd_feature_list' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:250 | [orphan] 'cmd_feature_conflicts' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:271 | [orphan] 'cmd_mq_enqueue' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:290 | [orphan] 'cmd_mq_status' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:316 | [orphan] 'cmd_mq_next' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:333 | [orphan] 'cmd_mq_check' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:348 | [orphan] 'cmd_mq_merged' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:357 | [orphan] 'cmd_mq_remove' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:369 | [orphan] 'cmd_lock_acquire' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:390 | [orphan] 'cmd_lock_release' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:406 | [orphan] 'cmd_lock_status' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:435 | [orphan] 'cmd_work_submit' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:452 | [orphan] 'cmd_work_claim' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:472 | [orphan] 'cmd_work_complete' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:492 | [orphan] 'cmd_work_get' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:515 | [orphan] 'cmd_handoff_write' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:531 | [orphan] 'cmd_handoff_read' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:564 | [orphan] 'cmd_memory_store' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:582 | [orphan] 'cmd_memory_query' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:614 | [orphan] 'cmd_guardrails_check' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:635 | [orphan] 'cmd_audit_query' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:668 | [orphan] 'cmd_help' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:745 | [orphan] 'build_parser' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:931 | [orphan] 'main' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:59 | [orphan] '_mcp_lifespan' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:97 | [orphan] 'get_agent_id' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:102 | [orphan] 'get_agent_type' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:113 | [orphan] 'acquire_lock' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:167 | [orphan] 'release_lock' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:195 | [orphan] 'check_locks' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:231 | [orphan] 'get_work' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:274 | [orphan] 'complete_work' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:322 | [orphan] 'submit_work' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:387 | [orphan] 'get_task' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:443 | [orphan] 'issue_create' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:521 | [orphan] 'issue_list' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:578 | [orphan] 'issue_show' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:605 | [orphan] 'issue_update' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:673 | [orphan] 'issue_close' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:726 | [orphan] 'issue_comment' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:761 | [orphan] 'issue_ready' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:803 | [orphan] 'issue_blocked' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:831 | [orphan] 'issue_search' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:874 | [orphan] 'write_handoff' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:937 | [orphan] 'read_handoff' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1002 | [orphan] 'register_session' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1048 | [orphan] 'discover_agents' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1101 | [orphan] 'heartbeat' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1125 | [orphan] 'cleanup_dead_agents' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1164 | [orphan] 'remember' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1219 | [orphan] 'recall' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1279 | [orphan] 'check_guardrails' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1350 | [orphan] 'get_my_profile' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1387 | [orphan] 'get_agent_dispatch_configs' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1411 | [orphan] 'query_audit' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1466 | [orphan] 'check_policy' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1513 | [orphan] 'validate_cedar_policy' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1557 | [orphan] 'allocate_ports' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1606 | [orphan] 'release_ports' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1633 | [orphan] 'ports_status' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1678 | [orphan] 'request_approval' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1710 | [orphan] 'check_approval' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1736 | [orphan] 'list_policy_versions' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1756 | [orphan] 'request_permission' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1789 | [orphan] 'register_feature' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1845 | [orphan] 'deregister_feature' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1880 | [orphan] 'get_feature' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1914 | [orphan] 'list_active_features' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1944 | [orphan] 'analyze_feature_conflicts' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1985 | [orphan] 'enqueue_merge' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2026 | [orphan] 'get_merge_queue' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2055 | [orphan] 'get_next_merge' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2084 | [orphan] 'run_pre_merge_checks' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2114 | [orphan] 'mark_merged' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2136 | [orphan] 'remove_from_merge_queue' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2161 | [orphan] '_current_trust_level' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2176 | [orphan] 'compose_train' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2235 | [orphan] 'eject_from_train' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2293 | [orphan] 'get_train_status' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2326 | [orphan] 'report_spec_result' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2369 | [orphan] 'affected_tests' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2407 | [orphan] 'report_status' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2508 | [orphan] 'help' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2840 | [orphan] 'list_scenarios' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2884 | [orphan] 'validate_scenario' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2919 | [orphan] 'create_scenario' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2970 | [orphan] 'run_gen_eval' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:3140 | [orphan] '_code_search_enabled' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:3149 | [orphan] 'search_code' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:3225 | [orphan] 'main' is unreachable from any entrypoint or test |
| architecture | db.py:32 | [orphan] 'rpc' is unreachable from any entrypoint or test |
| architecture | db.py:36 | [orphan] 'query' is unreachable from any entrypoint or test |
| architecture | db.py:45 | [orphan] 'insert' is unreachable from any entrypoint or test |
| architecture | db.py:54 | [orphan] 'update' is unreachable from any entrypoint or test |
| architecture | db.py:64 | [orphan] 'delete' is unreachable from any entrypoint or test |
| architecture | db.py:68 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | db.py:80 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | db.py:85 | [orphan] 'config' is unreachable from any entrypoint or test |
| architecture | db.py:96 | [orphan] 'client' is unreachable from any entrypoint or test |
| architecture | db.py:101 | [orphan] '_headers' is unreachable from any entrypoint or test |
| architecture | db.py:109 | [orphan] 'rpc' is unreachable from any entrypoint or test |
| architecture | db.py:130 | [orphan] 'query' is unreachable from any entrypoint or test |
| architecture | db.py:154 | [orphan] 'insert' is unreachable from any entrypoint or test |
| architecture | db.py:184 | [orphan] 'update' is unreachable from any entrypoint or test |
| architecture | db.py:217 | [orphan] 'delete' is unreachable from any entrypoint or test |
| architecture | db.py:237 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | db.py:279 | [orphan] 'close_db' is unreachable from any entrypoint or test |
| architecture | db.py:287 | [orphan] 'reset_db' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:25 | [orphan] '_coerce_filter_value' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:46 | [orphan] '_validate_identifier' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:54 | [orphan] '_validate_select_clause' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:66 | [orphan] '_serialize_for_asyncpg' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:85 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:89 | [orphan] '_get_pool' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:98 | [orphan] 'rpc' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:128 | [orphan] 'query' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:217 | [orphan] 'insert' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:245 | [orphan] 'update' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:287 | [orphan] 'delete' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:309 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | discovery.py:38 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:39 | [orphan] 'parse_dt' is unreachable from any entrypoint or test |
| architecture | discovery.py:68 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:82 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:96 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:113 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:124 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | discovery.py:128 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | discovery.py:133 | [orphan] 'register' is unreachable from any entrypoint or test |
| architecture | discovery.py:184 | [orphan] 'discover' is unreachable from any entrypoint or test |
| architecture | discovery.py:208 | [orphan] 'heartbeat' is unreachable from any entrypoint or test |
| architecture | discovery.py:266 | [orphan] 'cleanup_dead_agents' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:29 | [orphan] 'is_colima_installed' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:34 | [orphan] 'is_colima_running' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:47 | [orphan] '_ensure_colima_vm' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:100 | [orphan] 'detect_runtime' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:168 | [orphan] 'is_container_running' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:182 | [orphan] 'start_container' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:267 | [orphan] 'wait_for_healthy' is unreachable from any entrypoint or test |
| architecture | event_bus.py:50 | [orphan] '__post_init__' is unreachable from any entrypoint or test |
| architecture | event_bus.py:57 | [orphan] 'to_json' is unreachable from any entrypoint or test |
| architecture | event_bus.py:71 | [orphan] 'from_json' is unreachable from any entrypoint or test |
| architecture | event_bus.py:119 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | event_bus.py:140 | [orphan] 'running' is unreachable from any entrypoint or test |
| architecture | event_bus.py:144 | [orphan] 'failed' is unreachable from any entrypoint or test |
| architecture | event_bus.py:148 | [orphan] 'on_event' is unreachable from any entrypoint or test |
| architecture | event_bus.py:159 | [orphan] 'off_event' is unreachable from any entrypoint or test |
| architecture | event_bus.py:188 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | event_bus.py:206 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | event_bus.py:225 | [orphan] 'restart' is unreachable from any entrypoint or test |
| architecture | event_bus.py:230 | [orphan] '_listen_loop' is unreachable from any entrypoint or test |
| architecture | event_bus.py:262 | [orphan] '_connect_and_listen' is unreachable from any entrypoint or test |
| architecture | event_bus.py:275 | [orphan] '_notification_handler' is unreachable from any entrypoint or test |
| architecture | event_bus.py:306 | [orphan] '_dispatch' is unreachable from any entrypoint or test |
| architecture | event_bus.py:329 | [orphan] '_safe_callback' is unreachable from any entrypoint or test |
| architecture | event_bus.py:351 | [orphan] 'reset_event_bus' is unreachable from any entrypoint or test |
| architecture | event_stream.py:64 | [orphan] 'mint_events_token' is unreachable from any entrypoint or test |
| architecture | event_stream.py:153 | [orphan] '_prune_nonces' is unreachable from any entrypoint or test |
| architecture | event_stream.py:271 | [orphan] '_on_task_event' is unreachable from any entrypoint or test |
| architecture | event_stream.py:276 | [orphan] '_on_audit_event' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:89 | [orphan] 'is_enabled' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:92 | [orphan] 'to_yaml_dict' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:106 | [orphan] 'from_yaml_dict' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:107 | [orphan] '_parse' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:129 | [orphan] 'normalize_flag_name' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:164 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:173 | [orphan] 'load' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:183 | [orphan] '_load_unlocked' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:242 | [orphan] '_get_registry' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:250 | [orphan] 'resolve_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:283 | [orphan] 'is_enabled' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:287 | [orphan] 'check_undeclared_env_vars' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:308 | [orphan] 'create_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:347 | [orphan] 'enable_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:363 | [orphan] '_write_registry' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:393 | [orphan] 'get_feature_flag_service' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:402 | [orphan] 'reset_feature_flag_service' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:409 | [orphan] 'create_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:417 | [orphan] 'enable_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:421 | [orphan] 'resolve_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:425 | [orphan] 'is_enabled' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:51 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:52 | [orphan] 'parse_dt' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:84 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:103 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:131 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:135 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:140 | [orphan] 'register' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:198 | [orphan] 'deregister' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:233 | [orphan] 'get_feature' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:248 | [orphan] 'get_active_features' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:260 | [orphan] 'analyze_conflicts' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:108 | [orphan] 'create_speculative_ref' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:115 | [orphan] 'delete_speculative_refs' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:117 | [orphan] 'fast_forward_main' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:119 | [orphan] 'get_changed_files' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:121 | [orphan] 'list_speculative_refs' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:129 | [orphan] 'validate_speculative_ref_name' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:143 | [orphan] 'validate_branch_name' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:159 | [orphan] 'parse_git_version' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:183 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:189 | [orphan] '_ensure_git_version' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:212 | [orphan] '_run' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:225 | [orphan] 'create_speculative_ref' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:317 | [orphan] 'delete_speculative_refs' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:342 | [orphan] 'fast_forward_main' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:372 | [orphan] 'get_changed_files' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:406 | [orphan] 'list_speculative_refs' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:426 | [orphan] '_parse_conflict_files' is unreachable from any entrypoint or test |
| architecture | github_classifier.py:16 | [orphan] '_load_classifier' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:39 | [orphan] 'parse' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:79 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:92 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:96 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:101 | [orphan] 'parse_lock_labels' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:121 | [orphan] 'parse_branch' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:132 | [orphan] 'sync_label_locks' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:212 | [orphan] 'sync_branch_tracking' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:265 | [orphan] 'handle_push_webhook' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:294 | [orphan] 'handle_issues_webhook' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:328 | [orphan] 'get_github_coordination_service' is unreachable from any entrypoint or test |
| architecture | guardrails.py:33 | [orphan] '_ensure_guardrail_instruments' is unreachable from any entrypoint or test |
| architecture | guardrails.py:55 | [orphan] 'reset_guardrail_instruments' is unreachable from any entrypoint or test |
| architecture | guardrails.py:156 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | guardrails.py:178 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | guardrails.py:198 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | guardrails.py:209 | [orphan] '_check_session_scope' is unreachable from any entrypoint or test |
| architecture | guardrails.py:271 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | guardrails.py:277 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | guardrails.py:282 | [orphan] '_load_patterns' is unreachable from any entrypoint or test |
| architecture | guardrails.py:308 | [orphan] 'check_operation' is unreachable from any entrypoint or test |
| architecture | handoffs.py:37 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | handoffs.py:67 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | handoffs.py:88 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | handoffs.py:98 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | handoffs.py:102 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | handoffs.py:107 | [orphan] 'write' is unreachable from any entrypoint or test |
| architecture | handoffs.py:191 | [orphan] 'read' is unreachable from any entrypoint or test |
| architecture | handoffs.py:241 | [orphan] 'get_recent' is unreachable from any entrypoint or test |
| architecture | help_service.py:40 | [orphan] '_register' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:41 | [orphan] '_validate_url' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:107 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:146 | [orphan] 'probe_database' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:170 | [orphan] 'probe_http_api' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:186 | [orphan] 'select_transport' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:217 | [orphan] 'init_client' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:228 | [orphan] 'get_config' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:235 | [orphan] 'get_client' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:242 | [orphan] 'shutdown_client' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:250 | [orphan] '_build_default_headers' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:268 | [orphan] '_error_response' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:275 | [orphan] '_request' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:352 | [orphan] '_agent_identity' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:370 | [orphan] 'proxy_acquire_lock' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:385 | [orphan] 'proxy_release_lock' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:394 | [orphan] 'proxy_check_locks' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:445 | [orphan] 'proxy_get_work' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:456 | [orphan] 'proxy_complete_work' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:473 | [orphan] 'proxy_submit_work' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:492 | [orphan] 'proxy_get_task' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:501 | [orphan] 'proxy_search_code' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:562 | [orphan] 'proxy_issue_create' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:587 | [orphan] 'proxy_issue_list' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:608 | [orphan] 'proxy_issue_show' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:613 | [orphan] 'proxy_issue_update' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:638 | [orphan] 'proxy_issue_close' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:653 | [orphan] 'proxy_issue_comment' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:666 | [orphan] 'proxy_issue_search' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:679 | [orphan] 'proxy_issue_ready' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:692 | [orphan] 'proxy_issue_blocked' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:702 | [orphan] 'proxy_write_handoff' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:723 | [orphan] 'proxy_read_handoff' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:741 | [orphan] 'proxy_register_session' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:756 | [orphan] 'proxy_discover_agents' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:769 | [orphan] 'proxy_heartbeat' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:775 | [orphan] 'proxy_cleanup_dead_agents' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:791 | [orphan] 'proxy_remember' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:812 | [orphan] 'proxy_recall' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:834 | [orphan] 'proxy_check_guardrails' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:847 | [orphan] 'proxy_get_my_profile' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:852 | [orphan] 'proxy_get_agent_dispatch_configs' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:857 | [orphan] 'proxy_query_audit' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:876 | [orphan] 'proxy_check_policy' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:891 | [orphan] 'proxy_validate_cedar_policy' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:900 | [orphan] 'proxy_list_policy_versions' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:912 | [orphan] 'proxy_request_permission' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:925 | [orphan] 'proxy_request_approval' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:940 | [orphan] 'proxy_check_approval' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:950 | [orphan] 'proxy_allocate_ports' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:959 | [orphan] 'proxy_release_ports' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:968 | [orphan] 'proxy_ports_status' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:985 | [orphan] 'proxy_register_feature' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1006 | [orphan] 'proxy_deregister_feature' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1019 | [orphan] 'proxy_get_feature' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1024 | [orphan] 'proxy_list_active_features' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1029 | [orphan] 'proxy_analyze_feature_conflicts' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1047 | [orphan] 'proxy_enqueue_merge' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1060 | [orphan] 'proxy_get_merge_queue' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1065 | [orphan] 'proxy_get_next_merge' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1070 | [orphan] 'proxy_run_pre_merge_checks' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1079 | [orphan] 'proxy_mark_merged' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1088 | [orphan] 'proxy_remove_from_merge_queue' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1098 | [orphan] 'proxy_report_status' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1125 | [orphan] 'proxy_list_scenarios' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1149 | [orphan] 'proxy_validate_scenario' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1158 | [orphan] 'proxy_create_scenario' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1177 | [orphan] 'proxy_run_gen_eval' is unreachable from any entrypoint or test |
| architecture | issue_service.py:72 | [orphan] 'from_row' is unreachable from any entrypoint or test |
| architecture | issue_service.py:73 | [orphan] 'parse_dt' is unreachable from any entrypoint or test |
| architecture | issue_service.py:108 | [orphan] 'to_dict' is unreachable from any entrypoint or test |
| architecture | issue_service.py:164 | [orphan] 'from_row' is unreachable from any entrypoint or test |
| architecture | issue_service.py:176 | [orphan] 'to_dict' is unreachable from any entrypoint or test |
| architecture | issue_service.py:189 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | issue_service.py:193 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | issue_service.py:198 | [orphan] 'create' is unreachable from any entrypoint or test |
| architecture | issue_service.py:251 | [orphan] 'list_issues' is unreachable from any entrypoint or test |
| architecture | issue_service.py:306 | [orphan] 'show' is unreachable from any entrypoint or test |
| architecture | issue_service.py:344 | [orphan] 'update' is unreachable from any entrypoint or test |
| architecture | issue_service.py:410 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | issue_service.py:453 | [orphan] 'comment' is unreachable from any entrypoint or test |
| architecture | issue_service.py:479 | [orphan] 'ready' is unreachable from any entrypoint or test |
| architecture | issue_service.py:525 | [orphan] 'blocked' is unreachable from any entrypoint or test |
| architecture | issue_service.py:554 | [orphan] 'search' is unreachable from any entrypoint or test |
| architecture | kanban_viz_files.py:69 | [orphan] '_load_schema' is unreachable from any entrypoint or test |
| architecture | kanban_viz_files.py:115 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:44 | [orphan] 'dispatch' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:98 | [orphan] '_resolve_agent_id' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:114 | [orphan] '_finalize_trace' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:30 | [orphan] '_is_enabled' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:34 | [orphan] 'init_langfuse' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:79 | [orphan] 'get_langfuse' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:84 | [orphan] 'shutdown_langfuse' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:102 | [orphan] 'create_trace' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:130 | [orphan] 'create_span' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:153 | [orphan] 'end_span' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:175 | [orphan] 'trace_operation' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:229 | [orphan] 'reset_langfuse' is unreachable from any entrypoint or test |
| architecture | locks.py:29 | [orphan] '_get_instruments' is unreachable from any entrypoint or test |
| architecture | locks.py:58 | [orphan] '_ensure_instruments' is unreachable from any entrypoint or test |
| architecture | locks.py:81 | [orphan] 'is_valid_lock_key' is unreachable from any entrypoint or test |
| architecture | locks.py:101 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | locks.py:102 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | locks.py:131 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | locks.py:152 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | locks.py:156 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | locks.py:161 | [orphan] 'acquire' is unreachable from any entrypoint or test |
| architecture | locks.py:276 | [orphan] 'release' is unreachable from any entrypoint or test |
| architecture | locks.py:341 | [orphan] 'check' is unreachable from any entrypoint or test |
| architecture | locks.py:368 | [orphan] 'extend' is unreachable from any entrypoint or test |
| architecture | locks.py:392 | [orphan] 'is_locked' is unreachable from any entrypoint or test |
| architecture | locks.py:404 | [orphan] 'force_release' is unreachable from any entrypoint or test |
| architecture | memory.py:51 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | memory.py:81 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | memory.py:97 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | memory.py:108 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | memory.py:112 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | memory.py:117 | [orphan] 'remember' is unreachable from any entrypoint or test |
| architecture | memory.py:197 | [orphan] 'recall' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:73 | [orphan] 'from_feature' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:99 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:108 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:114 | [orphan] 'registry' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:119 | [orphan] 'enqueue' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:210 | [orphan] 'get_queue' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:246 | [orphan] 'get_next_to_merge' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:260 | [orphan] 'run_pre_merge_checks' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:349 | [orphan] 'mark_merged' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:376 | [orphan] 'remove_from_queue' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:404 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | merge_train.py:114 | [orphan] '_entry_prefix_set' is unreachable from any entrypoint or test |
| architecture | merge_train.py:137 | [orphan] '_find_cycles_in_cross_partition_graph' is unreachable from any entrypoint or test |
| architecture | merge_train.py:176 | [orphan] '_dfs' is unreachable from any entrypoint or test |
| architecture | merge_train.py:212 | [orphan] 'compute_partitions' is unreachable from any entrypoint or test |
| architecture | merge_train.py:294 | [orphan] '_speculative_ref_name' is unreachable from any entrypoint or test |
| architecture | merge_train.py:299 | [orphan] '_sort_entries_by_priority' is unreachable from any entrypoint or test |
| architecture | merge_train.py:304 | [orphan] '_handle_conflict' is unreachable from any entrypoint or test |
| architecture | merge_train.py:318 | [orphan] '_handle_speculative_success' is unreachable from any entrypoint or test |
| architecture | merge_train.py:339 | [orphan] 'compose_train' is unreachable from any entrypoint or test |
| architecture | merge_train.py:445 | [orphan] '_speculate' is unreachable from any entrypoint or test |
| architecture | merge_train.py:547 | [orphan] '_declared_namespaces' is unreachable from any entrypoint or test |
| architecture | merge_train.py:557 | [orphan] 'validate_post_speculation_claims' is unreachable from any entrypoint or test |
| architecture | merge_train.py:644 | [orphan] '_caller_is_authorized_to_eject' is unreachable from any entrypoint or test |
| architecture | merge_train.py:659 | [orphan] 'eject_from_train' is unreachable from any entrypoint or test |
| architecture | merge_train.py:768 | [orphan] 'reset_blocked_entry' is unreachable from any entrypoint or test |
| architecture | merge_train.py:811 | [orphan] 'reset_abandoned_entry' is unreachable from any entrypoint or test |
| architecture | merge_train.py:884 | [orphan] '_build_merge_graph' is unreachable from any entrypoint or test |
| architecture | merge_train.py:974 | [orphan] '_compute_wave_order' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1017 | [orphan] 'execute_wave_merge' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1137 | [orphan] '_group_refs_by_train_id' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1157 | [orphan] 'cleanup_orphaned_speculative_refs' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1206 | [orphan] 'gc_aged_speculative_refs' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:66 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:77 | [orphan] '_feature_to_train_entry' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:123 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:138 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:144 | [orphan] 'registry' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:150 | [orphan] 'git_adapter' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:160 | [orphan] 'refresh_client' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:167 | [orphan] '_load_entries' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:177 | [orphan] '_save_entry' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:197 | [orphan] '_persist_entries' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:208 | [orphan] '_probe_and_maybe_refresh' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:256 | [orphan] 'compose_train' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:288 | [orphan] 'eject_from_train' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:338 | [orphan] 'get_train_status' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:343 | [orphan] 'report_spec_result' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:404 | [orphan] 'reset_merge_train_service' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:438 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:457 | [orphan] 'service' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:463 | [orphan] 'running' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:466 | [orphan] 'run_once' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:484 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:494 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:506 | [orphan] '_loop' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:521 | [orphan] 'get_merge_train_sweeper' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:529 | [orphan] 'reset_merge_train_sweeper' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:127 | [orphan] 'is_terminal' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:130 | [orphan] 'to_metadata_dict' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:162 | [orphan] 'all_passed' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:202 | [orphan] 'new_train_id' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:206 | [orphan] 'all_entries' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:213 | [orphan] 'total_entry_count' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:252 | [orphan] 'file_path_to_namespaces' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:287 | [orphan] 'claim_prefix' is unreachable from any entrypoint or test |
| architecture | merge_watcher.py:25 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | merge_watcher.py:30 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | merge_watcher.py:39 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | merge_watcher.py:50 | [orphan] '_loop' is unreachable from any entrypoint or test |
| architecture | merge_watcher.py:61 | [orphan] '_tick' is unreachable from any entrypoint or test |
| architecture | merge_watcher.py:68 | [orphan] 'get_merge_watcher' is unreachable from any entrypoint or test |
| architecture | migrations.py:35 | [orphan] 'discover_migrations' is unreachable from any entrypoint or test |
| architecture | migrations.py:50 | [orphan] '_checksum' is unreachable from any entrypoint or test |
| architecture | migrations.py:55 | [orphan] 'run_migrations' is unreachable from any entrypoint or test |
| architecture | migrations.py:146 | [orphan] 'ensure_schema' is unreachable from any entrypoint or test |
| architecture | model_routing/exploration.py:33 | [orphan] 'exhausted' is unreachable from any entrypoint or test |
| architecture | model_routing/exploration.py:48 | [orphan] 'choose' is unreachable from any entrypoint or test |
| architecture | model_routing/feedback.py:29 | [orphan] '_observation_value_is_sane' is unreachable from any entrypoint or test |
| architecture | model_routing/feedback.py:73 | [orphan] '_decayed_weight' is unreachable from any entrypoint or test |
| architecture | model_routing/feedback.py:80 | [orphan] 'aggregate' is unreachable from any entrypoint or test |
| architecture | model_routing/feedback.py:120 | [orphan] 'normalize_vendor_switch' is unreachable from any entrypoint or test |
| architecture | model_routing/feedback.py:147 | [orphan] 'normalize_vendor_notes' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:106 | [orphan] 'blend_quality' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:122 | [orphan] 'effective_cost' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:149 | [orphan] 'feasibility_reason' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:167 | [orphan] '_min_max_norm' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:177 | [orphan] '_headroom_fraction' is unreachable from any entrypoint or test |
| architecture | model_routing/resolver.py:184 | [orphan] 'score_and_rank' is unreachable from any entrypoint or test |
| architecture | network_policies.py:24 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | network_policies.py:36 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | network_policies.py:40 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | network_policies.py:45 | [orphan] 'check_domain' is unreachable from any entrypoint or test |
| architecture | network_policies.py:85 | [orphan] 'get_network_policy_service' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:16 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:20 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:24 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:34 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:37 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:41 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:44 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:55 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:71 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:128 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:143 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:148 | [orphan] 'start_imap_listener' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:214 | [orphan] 'stop_imap_listener' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:222 | [orphan] '_process_imap_message' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:348 | [orphan] '_send_reply_email' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:368 | [orphan] '_render' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:380 | [orphan] '_thread_message_id' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:387 | [orphan] 'get_gmail_channel' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:33 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:38 | [orphan] 'register_channel' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:43 | [orphan] 'enabled' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:47 | [orphan] 'start_digest_loop' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:54 | [orphan] 'stop_digest_loop' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:67 | [orphan] '_digest_loop' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:77 | [orphan] '_flush_digest' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:110 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:169 | [orphan] '_send_with_retry' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:208 | [orphan] '_passes_filter' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:223 | [orphan] 'get_notifier' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:231 | [orphan] 'reset_notifier' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:29 | [orphan] 'extract_token' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:39 | [orphan] 'parse_reply' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:72 | [orphan] 'validate_sender' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:82 | [orphan] 'clean_reply_body' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:109 | [orphan] 'route_reply' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:28 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:39 | [orphan] 'client' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:44 | [orphan] '_api_url' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:47 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:106 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:122 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:126 | [orphan] '_escape_markdown' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:131 | [orphan] '_format_message' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:148 | [orphan] 'get_telegram_channel' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:10 | [orphan] '_esc' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:15 | [orphan] '_sanitize_header' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:46 | [orphan] '_wrap' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:56 | [orphan] '_change_label' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:61 | [orphan] '_field' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:71 | [orphan] 'render_approval_email' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:100 | [orphan] 'render_status_email' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:119 | [orphan] 'render_escalation_email' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:147 | [orphan] 'render_stale_agent_email' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:165 | [orphan] 'render_digest_email' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:26 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:37 | [orphan] 'client' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:42 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:83 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:109 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:113 | [orphan] 'get_webhook_channel' is unreachable from any entrypoint or test |
| architecture | openspec_proposals_api.py:199 | [orphan] '_parse_h1_title' is unreachable from any entrypoint or test |
| architecture | openspec_sources.py:256 | [orphan] 'warm_local_sources' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:29 | [orphan] '_ensure_policy_instruments' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:93 | [orphan] 'allow' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:97 | [orphan] 'deny' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:116 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:120 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:125 | [orphan] 'check_operation' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:166 | [orphan] '_do_check_operation' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:351 | [orphan] 'check_network_access' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:374 | [orphan] 'list_policy_versions' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:393 | [orphan] 'rollback_policy' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:419 | [orphan] '_log_policy_decision' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:465 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:481 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:486 | [orphan] '_load_default_policies' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:500 | [orphan] '_load_schema' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:518 | [orphan] '_load_policies' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:573 | [orphan] '_build_entity' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:610 | [orphan] '_build_resource_entity' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:637 | [orphan] '_determine_resource_type' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:649 | [orphan] 'check_operation' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:690 | [orphan] '_do_check_operation' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:779 | [orphan] 'check_network_access' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:798 | [orphan] 'validate_policy' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:819 | [orphan] 'list_policies' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:838 | [orphan] 'invalidate_cache' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:843 | [orphan] 'list_policy_versions' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:862 | [orphan] 'rollback_policy' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:889 | [orphan] '_log_policy_decision' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:946 | [orphan] 'reset_policy_engine' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:952 | [orphan] 'reset_policy_instruments' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:21 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:25 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:29 | [orphan] 'on_policy_change' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:45 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:60 | [orphan] 'running' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:64 | [orphan] 'on_policy_change' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:67 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:79 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:93 | [orphan] '_listen_loop' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:121 | [orphan] '_connect_and_listen' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:127 | [orphan] '_notification_handler' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:149 | [orphan] '_safe_callback' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:163 | [orphan] 'get_policy_sync_service' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:171 | [orphan] 'reset_policy_sync_service' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:37 | [orphan] 'env_snippet' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:55 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:74 | [orphan] 'allocate' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:132 | [orphan] 'release' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:141 | [orphan] 'status' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:151 | [orphan] '_cleanup_expired' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:166 | [orphan] '_compose_project_name' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:189 | [orphan] 'reset_port_allocator' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:64 | [orphan] 'deep_merge' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:114 | [orphan] '_load_secrets_openbao' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:159 | [orphan] '_load_secrets' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:171 | [orphan] 'resolve_dynamic_dsn' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:239 | [orphan] '_replace' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:260 | [orphan] '_interpolate_tree' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:277 | [orphan] '_resolve_profile' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:311 | [orphan] '_flatten' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:323 | [orphan] '_inject_env' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:339 | [orphan] 'load_profile' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:372 | [orphan] 'apply_profile' is unreachable from any entrypoint or test |
| architecture | profiles.py:36 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | profiles.py:63 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | profiles.py:84 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | profiles.py:94 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | profiles.py:99 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | profiles.py:104 | [orphan] 'get_profile' is unreachable from any entrypoint or test |
| architecture | profiles.py:153 | [orphan] 'check_operation' is unreachable from any entrypoint or test |
| architecture | profiles.py:214 | [orphan] '_log_denial' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:69 | [orphan] '__repr__' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:85 | [orphan] '__call__' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:134 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:150 | [orphan] 'is_graph_stale' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:164 | [orphan] 'trigger_refresh' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:174 | [orphan] 'get_refresh_status' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:183 | [orphan] '_invoke' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:44 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:56 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:61 | [orphan] 'compute_score' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:108 | [orphan] 'get_violation_count' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:125 | [orphan] '_trust_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:130 | [orphan] '_operation_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:141 | [orphan] '_resource_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:152 | [orphan] '_violation_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:161 | [orphan] '_session_age_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:174 | [orphan] 'get_risk_scorer' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:182 | [orphan] 'reset_risk_scorer' is unreachable from any entrypoint or test |
| architecture | session_grants.py:30 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | session_grants.py:34 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | session_grants.py:39 | [orphan] 'request_grant' is unreachable from any entrypoint or test |
| architecture | session_grants.py:70 | [orphan] 'get_active_grants' is unreachable from any entrypoint or test |
| architecture | session_grants.py:78 | [orphan] 'has_grant' is unreachable from any entrypoint or test |
| architecture | session_grants.py:86 | [orphan] 'revoke_grants' is unreachable from any entrypoint or test |
| architecture | session_grants.py:100 | [orphan] '_row_to_grant' is unreachable from any entrypoint or test |
| architecture | session_grants.py:113 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | session_grants.py:133 | [orphan] 'reset_session_grant_service' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:39 | [orphan] 'filter' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:58 | [orphan] '_scrub' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:64 | [orphan] 'install_token_redaction_filter' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:79 | [orphan] 'redact_token' is unreachable from any entrypoint or test |
| architecture | status.py:12 | [orphan] 'generate_token' is unreachable from any entrypoint or test |
| architecture | status.py:17 | [orphan] 'store_token' is unreachable from any entrypoint or test |
| architecture | status.py:52 | [orphan] 'validate_token' is unreachable from any entrypoint or test |
| architecture | status.py:80 | [orphan] 'lookup_token_failure' is unreachable from any entrypoint or test |
| architecture | status.py:100 | [orphan] 'cleanup_expired_tokens' is unreachable from any entrypoint or test |
| architecture | sync_points.py:35 | [orphan] '_parse_iso' is unreachable from any entrypoint or test |
| architecture | sync_points.py:45 | [orphan] '_load_registry' is unreachable from any entrypoint or test |
| architecture | sync_points.py:60 | [orphan] '_check_active_worktrees' is unreachable from any entrypoint or test |
| architecture | sync_points.py:81 | [orphan] 'get_sync_points_status' is unreachable from any entrypoint or test |
| architecture | teams.py:69 | [orphan] 'from_file' is unreachable from any entrypoint or test |
| architecture | teams.py:93 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | teams.py:129 | [orphan] 'get_agent' is unreachable from any entrypoint or test |
| architecture | teams.py:143 | [orphan] 'get_agents_with_capability' is unreachable from any entrypoint or test |
| architecture | teams.py:180 | [orphan] 'get_teams_config' is unreachable from any entrypoint or test |
| architecture | teams.py:200 | [orphan] 'reset_teams_config' is unreachable from any entrypoint or test |
| architecture | telemetry.py:33 | [orphan] '_metrics_enabled' is unreachable from any entrypoint or test |
| architecture | telemetry.py:37 | [orphan] '_traces_enabled' is unreachable from any entrypoint or test |
| architecture | telemetry.py:41 | [orphan] '_prometheus_enabled' is unreachable from any entrypoint or test |
| architecture | telemetry.py:45 | [orphan] 'init_telemetry' is unreachable from any entrypoint or test |
| architecture | telemetry.py:74 | [orphan] '_init_metrics' is unreachable from any entrypoint or test |
| architecture | telemetry.py:145 | [orphan] '_init_traces' is unreachable from any entrypoint or test |
| architecture | telemetry.py:192 | [orphan] 'get_lock_meter' is unreachable from any entrypoint or test |
| architecture | telemetry.py:197 | [orphan] 'get_queue_meter' is unreachable from any entrypoint or test |
| architecture | telemetry.py:202 | [orphan] 'get_policy_meter' is unreachable from any entrypoint or test |
| architecture | telemetry.py:207 | [orphan] 'get_tracer' is unreachable from any entrypoint or test |
| architecture | telemetry.py:220 | [orphan] 'set_attribute' is unreachable from any entrypoint or test |
| architecture | telemetry.py:223 | [orphan] 'set_status' is unreachable from any entrypoint or test |
| architecture | telemetry.py:226 | [orphan] 'record_exception' is unreachable from any entrypoint or test |
| architecture | telemetry.py:229 | [orphan] '__enter__' is unreachable from any entrypoint or test |
| architecture | telemetry.py:232 | [orphan] '__exit__' is unreachable from any entrypoint or test |
| architecture | telemetry.py:239 | [orphan] 'start_span' is unreachable from any entrypoint or test |
| architecture | telemetry.py:252 | [orphan] 'get_prometheus_app' is unreachable from any entrypoint or test |
| architecture | telemetry.py:274 | [orphan] 'reset_telemetry' is unreachable from any entrypoint or test |
| architecture | watchdog.py:34 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | watchdog.py:55 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | watchdog.py:61 | [orphan] 'running' is unreachable from any entrypoint or test |
| architecture | watchdog.py:64 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | watchdog.py:72 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | watchdog.py:84 | [orphan] 'run_once' is unreachable from any entrypoint or test |
| architecture | watchdog.py:93 | [orphan] '_loop' is unreachable from any entrypoint or test |
| architecture | watchdog.py:107 | [orphan] '_check_stale_agents' is unreachable from any entrypoint or test |
| architecture | watchdog.py:166 | [orphan] '_check_aging_approvals' is unreachable from any entrypoint or test |
| architecture | watchdog.py:207 | [orphan] '_check_expiring_locks' is unreachable from any entrypoint or test |
| architecture | watchdog.py:235 | [orphan] '_cleanup_expired_tokens' is unreachable from any entrypoint or test |
| architecture | watchdog.py:252 | [orphan] '_check_event_bus_health' is unreachable from any entrypoint or test |
| architecture | watchdog.py:275 | [orphan] '_check_vendor_health' is unreachable from any entrypoint or test |
| architecture | watchdog.py:346 | [orphan] '_emit_event' is unreachable from any entrypoint or test |
| architecture | watchdog.py:391 | [orphan] 'get_watchdog' is unreachable from any entrypoint or test |
| architecture | watchdog.py:399 | [orphan] 'reset_watchdog' is unreachable from any entrypoint or test |
| architecture | work_queue.py:30 | [orphan] '_ensure_instruments' is unreachable from any entrypoint or test |
| architecture | work_queue.py:88 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | work_queue.py:89 | [orphan] 'parse_dt' is unreachable from any entrypoint or test |
| architecture | work_queue.py:133 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | work_queue.py:166 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | work_queue.py:187 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | work_queue.py:201 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | work_queue.py:205 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | work_queue.py:210 | [orphan] '_resolve_trust_level' is unreachable from any entrypoint or test |
| architecture | work_queue.py:225 | [orphan] 'claim' is unreachable from any entrypoint or test |
| architecture | work_queue.py:452 | [orphan] 'complete' is unreachable from any entrypoint or test |
| architecture | work_queue.py:603 | [orphan] 'submit' is unreachable from any entrypoint or test |
| architecture | work_queue.py:739 | [orphan] 'get_pending' is unreachable from any entrypoint or test |
| architecture | work_queue.py:763 | [orphan] 'get_task' is unreachable from any entrypoint or test |
| architecture | work_queue.py:775 | [orphan] 'get_my_tasks' is unreachable from any entrypoint or test |
| architecture | work_queue.py:799 | [orphan] 'cancel_task_convention' is unreachable from any entrypoint or test |
| architecture | work_queue.py:840 | [orphan] 'reset_instruments' is unreachable from any entrypoint or test |
| architecture | worktrees_view.py:24 | [orphan] '_repo_root' is unreachable from any entrypoint or test |
| architecture | worktrees_view.py:29 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | worktrees_view.py:41 | [orphan] 'get_active_worktrees' is unreachable from any entrypoint or test |
| architecture | kanban-viz/vite.config.ts:1 | [orphan] 'kanban-viz/vite.config' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/App.tsx:1 | [orphan] 'kanban-viz/src/App' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/main.tsx:1 | [orphan] 'kanban-viz/src/main' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/vite-env.d.ts:1 | [orphan] 'kanban-viz/src/vite-env.d' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/Board.tsx:1 | [orphan] 'kanban-viz/src/components/Board' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/Card.tsx:1 | [orphan] 'kanban-viz/src/components/Card' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:1 | [orphan] 'kanban-viz/src/components/ClusterBadge' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/Column.tsx:1 | [orphan] 'kanban-viz/src/components/Column' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ConsentPrompt.tsx:1 | [orphan] 'kanban-viz/src/components/ConsentPrompt' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/HiddenReposToggle.tsx:1 | [orphan] 'kanban-viz/src/components/HiddenReposToggle' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/PRCardView.tsx:1 | [orphan] 'kanban-viz/src/components/PRCardView' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ProposalCardView.tsx:1 | [orphan] 'kanban-viz/src/components/ProposalCardView' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:1 | [orphan] 'kanban-viz/src/components/PROriginFilter' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/RefreshButton.tsx:1 | [orphan] 'kanban-viz/src/components/RefreshButton' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/RepoBadge.tsx:1 | [orphan] 'kanban-viz/src/components/RepoBadge' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SaveViewButton.tsx:1 | [orphan] 'kanban-viz/src/components/SaveViewButton' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:1 | [orphan] 'kanban-viz/src/components/SourceSwimlanes' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SyncPointBanner.tsx:1 | [orphan] 'kanban-viz/src/components/SyncPointBanner' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:1 | [orphan] 'kanban-viz/src/components/VendorSwimlanes' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:1 | [orphan] 'kanban-viz/src/hooks/useBoardCards' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:1 | [orphan] 'kanban-viz/src/hooks/useCoordinator' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/coordinator-types.ts:1 | [orphan] 'kanban-viz/src/lib/coordinator-types' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/reversibility.ts:1 | [orphan] 'kanban-viz/src/lib/reversibility' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/runtime.ts:1 | [orphan] 'kanban-viz/src/lib/runtime' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/saveView.ts:1 | [orphan] 'kanban-viz/src/lib/saveView' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/App.tsx:14 | [orphan] 'App' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/Board.tsx:24 | [orphan] 'Board' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/Card.tsx:41 | [orphan] 'Card' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:72 | [orphan] 'ClusterBadge' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:81 | [orphan] 'ClusterBadgeInner' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:130 | [orphan] 'ClusterHighlightWrapper' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/Column.tsx:25 | [orphan] 'Column' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ConsentPrompt.tsx:12 | [orphan] 'ConsentPrompt' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/HiddenReposToggle.tsx:30 | [orphan] 'HiddenReposToggle' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/PRCardView.tsx:75 | [orphan] 'PRCardView' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ProposalCardView.tsx:22 | [orphan] 'ProposalCardView' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:69 | [orphan] 'PROriginFilter' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/RefreshButton.tsx:30 | [orphan] 'RefreshButton' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/RepoBadge.tsx:53 | [orphan] 'RepoBadge' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SaveViewButton.tsx:53 | [orphan] 'SaveViewButton' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:108 | [orphan] 'IssueSourceRow' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:245 | [orphan] 'PRSourceRow' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:393 | [orphan] 'PartialResultChip' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:442 | [orphan] 'ProposalSourceRow' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:554 | [orphan] 'SourceSwimlanes' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SyncPointBanner.tsx:43 | [orphan] 'SyncPointBanner' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:64 | [orphan] 'VendorSwimlanes' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/Card.tsx:28 | [orphan] 'relativeTime' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:22 | [orphan] 'emitHighlight' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/ClusterBadge.tsx:32 | [orphan] 'useHighlightState' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/HiddenReposToggle.tsx:16 | [orphan] 'shortForm' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:28 | [orphan] 'loadFromStorage' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:45 | [orphan] 'saveToStorage' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/PROriginFilter.tsx:137 | [orphan] 'filterByOrigin' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/RefreshButton.tsx:134 | [orphan] 'formatRelative' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/RepoBadge.tsx:22 | [orphan] 'hashString' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/RepoBadge.tsx:33 | [orphan] 'repoToColor' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SaveViewButton.tsx:43 | [orphan] 'slugify' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:70 | [orphan] 'bucketIssues' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:79 | [orphan] 'bucketPRs' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SourceSwimlanes.tsx:88 | [orphan] 'bucketProposals' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/SyncPointBanner.tsx:24 | [orphan] 'fetchSyncStatus' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:29 | [orphan] 'extractVendor' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:46 | [orphan] 'groupByVendor' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/components/VendorSwimlanes.tsx:60 | [orphan] 'determineConsensus' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:57 | [orphan] 'clusterBoardCards' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:179 | [orphan] 'fetchPRs' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:190 | [orphan] 'fetchProposals' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useBoardCards.ts:211 | [orphan] 'useBoardCards' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:64 | [orphan] 'fetchIssuesForSingleChange' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:96 | [orphan] 'fetchIssuesUnioned' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:114 | [orphan] 'mintEventsToken' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/hooks/useCoordinator.ts:132 | [orphan] 'useCoordinator' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/coordinator-types.ts:208 | [orphan] 'assertNever' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/coordinator-types.ts:218 | [orphan] 'issueStatusToColumn' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/coordinator-types.ts:236 | [orphan] 'prStatusToColumn' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/coordinator-types.ts:250 | [orphan] 'proposalStatusToColumn' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/coordinator-types.ts:295 | [orphan] 'toIssueCard' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/coordinator-types.ts:336 | [orphan] 'deriveIssueRepo' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/coordinator-types.ts:364 | [orphan] 'getClusterKey' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/reversibility.ts:46 | [orphan] 'classify' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/reversibility.ts:54 | [orphan] 'classifyOrDefault' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/reversibility.ts:59 | [orphan] 'requiresConsent' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/runtime.ts:12 | [orphan] 'isTauri' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/runtime.ts:21 | [orphan] 'isBrowser' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/saveView.ts:35 | [orphan] 'saveView' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/saveView.ts:47 | [orphan] 'saveBrowser' is unreachable from any entrypoint or test |
| architecture | kanban-viz/src/lib/saveView.ts:68 | [orphan] 'saveTauri' is unreachable from any entrypoint or test |
| deferred:open-tasks | N/A | 2.1 Write integration tests for routing migrations — additive-only, idempotent re-apply [S] |
| deferred:open-tasks | N/A | 2.2 Create migration `00X_model_routing.sql` per DB contract [S] |
| deferred:open-tasks | N/A | 2.3 Write tests for catalog service — CRUD, no-external-call read path, staleness flag [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.4 Implement `src/model_routing/catalog.py` — catalog service over routing tables [M] |
| deferred:open-tasks | N/A | 2.5 Write tests for OpenRouter refresher — price update, failure keeps rows, staleness [M] |
| deferred:open-tasks | N/A | 2.6 Implement OpenRouter REST refresher with standing-key auth [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.7 Write tests for local endpoint health probe — unhealthy exclusion, latency capture [S] |
| deferred:open-tasks | N/A | 2.8 Implement local endpoint registration plus health probe [S] |
| deferred:open-tasks | N/A | 2.9 Write tests for spend/counterfactual ledger — actual vs baseline, estimate labelling [M] |
| deferred:open-tasks | N/A | 2.10 Implement `src/model_routing/ledger.py` — spend accrual, counterfactual computation [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.11 Wire refresher, probes, ledger rollup into WatchdogService schedules [S] |
| deferred:open-tasks | N/A | 3.4 Implement Cedar feasibility policies plus vendor attribute schema [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.7 Write tests for routing API endpoints plus MCP tool parity [M] |
| deferred:open-tasks | N/A | 3.8 Expose resolver via HTTP endpoints plus MCP tool [M] |
| deferred:open-tasks | N/A | 3.9 Write tests for archetype delegation — flag off equals static result; timeout fallback signal [M] |
| deferred:open-tasks | N/A | 3.10 Implement `ROUTING_ADAPTIVE` delegation in `agents_config.resolve_archetype_for_phase` [S] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.11 Add `endpoint_kind`/`base_url` fields to agents.yaml schema with validation [S] |
| deferred:open-tasks | N/A | 4.6 Enforce exploration gating in roadmap dispatch path [S] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 5.4 Wire learning-log writers to POST `/routing/feedback` (best-effort, non-blocking) [S] |
| deferred:open-tasks | N/A | 5.5 Write tests for gen-eval calibration seeding of local-model priors [S] |
| deferred:open-tasks | N/A | 5.6 Implement gen-eval calibration suite runner seeding local priors [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 6.1 Write tests for ToS monitor — hash diff emits signal, vendor freeze until ack [S] |
| deferred:open-tasks | N/A | 6.2 Implement ToS monitor probe [S] |
| deferred:open-tasks | N/A | 6.3 Write tests for model canary — fingerprint drift invalidates posteriors [S] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 6.4 Implement model canary probe [S] |
| deferred:open-tasks | N/A | 6.5 Write tests for tripwire evaluation — economic kill, posture-flip signals [M] |
| deferred:open-tasks | N/A | 6.7 Write tests for quota probe — quota-axi JSON normalized to signal, resilience down-rank, graceful degrade [S] |
| deferred:open-tasks | N/A | 6.8 Implement optional quota probe (quota-axi subprocess adapter, off by default) [S] |
| deferred:open-tasks | N/A | 6.6 Implement tripwire evaluator with posture flips as signals [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope, verify quota probe degrades cleanly |
| deferred:open-tasks | N/A | 7.1 Write component tests for usage dashboard — scoreboard render, estimate labelling [M] |
| deferred:open-tasks | N/A | 7.2 Scaffold `apps/usage-viz` from kanban-viz conventions (auth, SSE/poll hooks) [M] |
| deferred:open-tasks | N/A | 7.3 Implement spend, savings, scoreboard, exploration burn-down views [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 7.4 Write tests for routing telemetry emission — fallback label present [S] |
| deferred:open-tasks | N/A | 7.5 Emit routing OTel measurements on `coordinator.signal` meter [S] |
| deferred:open-tasks | N/A | 8.1 Run full test suite across coordinator plus skills venvs [S] |
| deferred:open-tasks | N/A | 8.2 E2E: flag-on routed quick-task to local endpoint; flag-off parity check [M] |
| deferred:open-tasks | N/A | 8.3 Archive absorbed changes with superseded-by pointers (`cross-vendor-arbitrage-instrument`, `usage-stats-multi-model` |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 8.4 Register OpenRouter MCP server in `.mcp.json` as dev-time tool with setup docs [XS] |
| deferred:open-tasks | N/A | 8.5 Write ADR for adaptive routing placement plus objective-profile semantics [S] |
| deferred:open-tasks | N/A | 0.1 (S) Confirm the `add-adaptive-model-router` ledger + policy interfaces this consumes |
| deferred:open-tasks | N/A | 1.1 (S) Validate `contracts/openapi/v1.yaml`; generate Pydantic models into |
| deferred:open-tasks | N/A | Checkpoint: openapi validates, models import |
| deferred:open-tasks | N/A | 2.1 (S) Write a smoke test that starts the gateway container and asserts `/health` + |
| deferred:open-tasks | N/A | 2.2 (M) Add `docker/llm-gateway/` — pinned LiteLLM proxy compose service + |
| deferred:open-tasks | N/A | Checkpoint: gateway starts; embedding round-trips against a test upstream |
| deferred:open-tasks | N/A | 3.1 (M) Write tests for `llm_gateway.py` — trust-bounded issuance, vault-unavailable |
| deferred:open-tasks | N/A | 3.2 (M) Implement `agent-coordinator/src/llm_gateway.py` — DI service over (vault, gateway |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope (agent-coordinator only) |
| deferred:open-tasks | N/A | 3.3 (S) Write surface tests — flag off hides MCP tools + 404s HTTP routes; op-kind |
| deferred:open-tasks | N/A | 3.4 (S) Register `issue_llm_key/revoke_llm_key/get_llm_budget/get_llm_spend` in |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.1 (S) Migration test — `llm_gateway_keys` additive shape; asserts NO spend columns |
| deferred:open-tasks | N/A | 4.2 (S) Add additive migration `NNN_llm_gateway_keys.sql` |
| deferred:open-tasks | N/A | 4.3 (M) Wire the gateway spend callback → router ledger; buffer-and-reconcile on ledger |
| deferred:open-tasks | N/A | 5.1 (S) Repoint `code_search.py`'s embedder at the gateway `/embeddings` behind a config |
| deferred:open-tasks | N/A | 5.2 (S) Docs: `docs/guides/llm-gateway.md` — control/data-plane split, the coverage |
| deferred:open-tasks | N/A | 5.3 (M) End-to-end (where a gateway + model are reachable): issue a key, embed via the |
| deferred:open-tasks | N/A | Checkpoint: suite green, diff maps to tasks, scope verified |
| deferred:open-tasks | N/A | 2.4 Follow-up (dispatch plumbing): translate `thinking` to vendor flags at the CLI |
| deferred:open-tasks | N/A | 2.5 Follow-up (model selection): consult the OpenRouter Pareto (cost vs performance) |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | 1.1 Write tests for the merge-plan schema and its producer |
| deferred:open-tasks | N/A | 1.2 Add `build_plan.py` (or extend the analysis round) to emit `merge-plan.json` from `discover_prs` + `check_staleness` |
| deferred:open-tasks | N/A | 1.3 Derive dependency edges from file overlap + base-branch relationships between PR nodes |
| deferred:open-tasks | N/A | 1.4 Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.1 Write tests for the `merge-plan.md` renderer (fidelity + non-mutation) |
| deferred:open-tasks | N/A | 2.2 Implement the `merge-plan.md` renderer as a pure projection of `merge-plan.json` |
| deferred:open-tasks | N/A | 3.1 Write tests for tier selection degrading to the file when no coordinator is available |
| deferred:open-tasks | N/A | 3.2 Wire plan storage to `merge_backend.py` detection so file tier is authoritative absent a coordinator; stub the coord |
| deferred:open-tasks | N/A | 3.3 Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.1 Write tests for `--execute <plan> --pr <n>`: live re-check, gate halt, security-backstop deferral, outcome write-bac |
| deferred:open-tasks | N/A | 4.2 Implement `--execute --pr <n>` in the skill entrypoint: load plan, re-check live PR/CI, refresh if stale, run `vendo |
| deferred:open-tasks | N/A | 4.3 On successful merge, flag downstream nodes (`needs_revalidation=true`) and recompute mergeability before executing a |
| deferred:open-tasks | N/A | 4.4 Enforce canonical `skills/...` helper paths in the executor (no `.claude/skills` mirror dependence) |
| deferred:open-tasks | N/A | 4.5 Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 5.1 Write tests for inserting a discovered prerequisite node and for the comment-addressing delegation hand-off |
| deferred:open-tasks | N/A | 5.2 Implement plan amendment: insert prerequisite node + edges with a reason; block affected nodes until it merges |
| deferred:open-tasks | N/A | 5.3 Implement the comment-addressing seam: record unresolved comments on the node and offer delegation to `iterate-on-im |
| deferred:open-tasks | N/A | 5.4 Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 6.1 Update `merge-pull-requests/SKILL.md`: document the plan artifact, `--execute --pr <n>`, gates, and the fresh-contex |
| deferred:open-tasks | N/A | 6.2 Sync runtime mirrors (`bash skills/install.sh --mode rsync --force --deps none --python-tools none`) and run the ski |
| deferred:open-tasks | N/A | P2.1 Coordinator system-of-record: model plan nodes as `work_queue` (`task_type=pr_merge`, `blockedBy`) + `merge_queue`  |
| deferred:open-tasks | N/A | P2.2 Event-driven re-validation over `event_bus` LISTEN/NOTIFY (design.md D4) |
| deferred:open-tasks | N/A | P2.3 Cross-host dispatch of per-PR executors with worktree isolation (design.md D5) |
| deferred:open-tasks | N/A | P2.4 Auth scoping for cloud-SDK plan endpoints (design.md D10) |
| deferred:open-tasks | N/A | P2.5 Automated comment-addressing via worktree-isolated sub-agents (out of scope here; design.md D8) |
| deferred:open-tasks | N/A | 0.1 Create `skills/references/prioritization-frameworks.md` |
| deferred:open-tasks | N/A | 0.2 Extend the proposal template with optional discovery sections |
| deferred:open-tasks | N/A | 0.3 Extend the roadmap schema/templates with optional `outcome` / `okr` fields |
| deferred:open-tasks | N/A | 0.4 Create the 12 new test dirs (each with a placeholder `test_skill_md.py` containing a |
| deferred:open-tasks | N/A | 0.5 Stub the "Product discovery" group in `docs/skills-catalogue.md` |
| deferred:open-tasks | N/A | 1.1.1 Tests for `create-prd` and `opportunity-solution-tree` |
| deferred:open-tasks | N/A | 1.1.2 Author `skills/create-prd/SKILL.md` (output renders as a valid `proposal.md`) |
| deferred:open-tasks | N/A | 1.1.3 Author `skills/opportunity-solution-tree/SKILL.md` (leaves = change candidates) |
| deferred:open-tasks | N/A | 1.2.1 Tests for `prioritize-features` and `identify-assumptions` |
| deferred:open-tasks | N/A | 1.2.2 Author `skills/prioritize-features/SKILL.md` (cites `references/prioritization-frameworks.md`) |
| deferred:open-tasks | N/A | 1.2.3 Author `skills/identify-assumptions/SKILL.md` |
| deferred:open-tasks | N/A | 1.3.1 Tests for `strategy-red-team` and `pre-mortem` |
| deferred:open-tasks | N/A | 1.3.2 Author `skills/strategy-red-team/SKILL.md` (findings in `iterate-on-plan` shape) |
| deferred:open-tasks | N/A | 1.3.3 Author `skills/pre-mortem/SKILL.md` |
| deferred:open-tasks | N/A | 1.4.1 Tests for `user-stories` and `test-scenarios` |
| deferred:open-tasks | N/A | 1.4.2 Author `skills/user-stories/SKILL.md` (output includes WHEN/THEN blocks) |
| deferred:open-tasks | N/A | 1.4.3 Author `skills/test-scenarios/SKILL.md` |
| deferred:open-tasks | N/A | 1.5.1 Tests for `intended-vs-implemented` (user-invocable) and `shipping-artifacts` (infra, exempt) |
| deferred:open-tasks | N/A | 1.5.2 Author `skills/intended-vs-implemented/SKILL.md` |
| deferred:open-tasks | N/A | 1.5.3 Author `skills/shipping-artifacts/SKILL.md` (`user_invocable: false`, no tail block) |
| deferred:open-tasks | N/A | 1.6.1 Tests for `outcome-roadmap` and `brainstorm-okrs` |
| deferred:open-tasks | N/A | 1.6.2 Author `skills/outcome-roadmap/SKILL.md` |
| deferred:open-tasks | N/A | 1.6.3 Author `skills/brainstorm-okrs/SKILL.md` |
| deferred:open-tasks | N/A | 2.1.1 Wire `explore-feature/SKILL.md` to consume `opportunity-solution-tree` output + outcome framing |
| deferred:open-tasks | N/A | 2.1.2 Wire `plan-feature/SKILL.md` Gate-1 discovery to incorporate `identify-assumptions` + `strategy-red-team` |
| deferred:open-tasks | N/A | 2.1.3 Wire seam 1 producer→consumer: `plan-roadmap`, `plan-feature`, and the proposal template consume `create-prd` / `o |
| deferred:open-tasks | N/A | 2.1.4 Wire seam 3's `iterate-on-plan` consumer: `iterate-on-plan/SKILL.md` consumes `pre-mortem` findings (using the exi |
| deferred:open-tasks | N/A | 2.1.5 Wire seam 4: `plan-feature` spec generation and `validate-feature` consume `user-stories` / `test-scenarios` so ge |
| deferred:open-tasks | N/A | 2.2.1 Wire `prioritize-proposals/SKILL.md` to compose `prioritize-features` scoring axes |
| deferred:open-tasks | N/A | 2.3.1 Wire `validate-feature/SKILL.md` (+ a note in the OpenSpec verification workflow docs under `docs/guides/` — there |
| deferred:open-tasks | N/A | 2.3.2 Wire `autopilot-roadmap` / `roadmap-runtime` to reference optional `okr` fields |
| deferred:open-tasks | N/A | 3.1 Run `skills/install.sh --mode rsync` dry run; confirm all 12 skills + the reference install |
| deferred:open-tasks | N/A | 3.2 Confirm every new skill's `related:` targets resolve (install warns on none) |
| deferred:open-tasks | N/A | 3.3 `cd skills && uv run pytest skills/tests/<12 new dirs>` green |
| deferred:open-tasks | N/A | 3.4 Fill the 12 rows in the `docs/skills-catalogue.md` "Product discovery" group; update counts |
| deferred:open-tasks | N/A | 3.5 `openspec validate add-product-management-skills --strict` passes |
| deferred:open-tasks | N/A | 3.6 Write the session log (decisions, deviations) per the session-log skill |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | 6.1 Orchestrator review |
| deferred:open-tasks | N/A | 6.2 Merge |
| deferred:open-tasks | N/A | 1.1 Write tests for `annotations.py`: record construction, 240-char text truncation, artifact-header population, round-t |
| deferred:open-tasks | N/A | 1.2 Implement `skills/shared/plan_review/annotations.py` — `Annotation` dataclass, `append(change_id, record)` (running  |
| deferred:open-tasks | N/A | 2.1 Write tests for `render.py`: proposal.md + `specs/**/spec.md` deltas + tasks.md → HTML with a `data-plan-anchor` on  |
| deferred:open-tasks | N/A | 2.2 Implement `skills/shared/plan_review/render.py` — parse the change's `proposal.md`, its `specs/**/spec.md` delta req |
| deferred:open-tasks | N/A | 3.1 Write tests for `server.py`: loopback binding, long-poll returns queued annotations, a terminal `complete` event end |
| deferred:open-tasks | N/A | 3.2 Implement `skills/shared/plan_review/server.py` — serve the artifact on `127.0.0.1`; require a per-session random to |
| deferred:open-tasks | N/A | 4.1 Wire `--visual-review` into `plan-feature` **after `tasks.md` is generated (Step 6)** so the task DAG is populated:  |
| deferred:open-tasks | N/A | 4.2 Teach `parallel-review-plan` to attach `plan-annotations.json` (when present) to reviewer context |
| deferred:open-tasks | N/A | 4.3 Update `skills/plan-feature/SKILL.md` and `skills/parallel-review-plan/SKILL.md` docs; run `skills/install.sh` to re |
| deferred:open-tasks | N/A | 5.1 Integration test: full loop on a fixture change — render, queue two annotations (one anchored, one text-range), poll |
| deferred:open-tasks | N/A | 5.2 Run `openspec validate add-visual-plan-review --strict`; run skill test suite; update this change's `session-log.md` |
| deferred:open-tasks | N/A | G1 Confirm the `warning`-severity layout policy (Decision D / D4): warnings render normally and are surfaced as annotati |
| deferred:open-tasks | N/A | 0.1 Write characterization test for `convergence_loop.converge()` capturing |
| deferred:open-tasks | N/A | 0.2 Write unit tests for the `refine-core` primitive surface (iterate, |
| deferred:open-tasks | N/A | 0.3 Extract `refine_core.py` in `skills/parallel-infrastructure/scripts/` |
| deferred:open-tasks | N/A | 0.4 Re-point `convergence_loop.converge()` to delegate to `refine-core`; |
| deferred:open-tasks | N/A | 0.5 Checkpoint: run convergence + refine-core tests, review diff, verify |
| deferred:open-tasks | N/A | 1.1 Write tests for `post-commit` hook behavior: enqueues on commit, exits |
| deferred:open-tasks | N/A | 1.2 Write tests for the ambient review runner: single-vendor dispatch, |
| deferred:open-tasks | N/A | 1.3 Add `ambient` to the `review_type` enum in |
| deferred:open-tasks | N/A | 1.4 Implement `.githooks/post-commit` mirroring the `post-merge` resolution |
| deferred:open-tasks | N/A | 1.5 Implement the ambient review runner (single-vendor dispatch via the |
| deferred:open-tasks | N/A | 1.6 Wire the kill-switch (`REVIEW_AMBIENT=0` / config flag) and update the |
| deferred:open-tasks | N/A | 1.7 Checkpoint: run hook + runner tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.1 Write tests for ledger read/write: local-first source of truth, write |
| deferred:open-tasks | N/A | 2.2 Write tests for lifecycle transitions (`open`→`addressed`→`retired`) |
| deferred:open-tasks | N/A | 2.3 Author `contracts/review-ledger.schema.json` and a ledger-entry model [S] |
| deferred:open-tasks | N/A | 2.4 Implement the ledger library: local-first store, stable-id keying, |
| deferred:open-tasks | N/A | 2.5 Implement `compact` re-verification reusing `consensus_synthesizer` |
| deferred:open-tasks | N/A | 2.6 Checkpoint: run ledger + compact tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.7 Write test for gate skills reading the ledger as warm context without |
| deferred:open-tasks | N/A | 2.8 Wire gate-time review skills to load outstanding ledger findings as |
| deferred:open-tasks | N/A | 3.1 Write tests for the standalone refine entry point: runs over a commit |
| deferred:open-tasks | N/A | 3.2 Implement the standalone refine entry point over `refine-core`, |
| deferred:open-tasks | N/A | 3.3 Checkpoint: run refine tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.1 Write tests for issue sync: blocking confirmed finding files one issue, |
| deferred:open-tasks | N/A | 4.2 Implement issue sync over the GitHub MCP tools: file on |
| deferred:open-tasks | N/A | 4.3 Checkpoint: run issue-sync tests, review diff, verify scope |
| deferred:open-tasks | N/A | 5.1 Write component tests for the ledger swimlane: renders cards by |
| deferred:open-tasks | N/A | 5.2 Add the SSE event payload for ledger changes (server side) [S] |
| deferred:open-tasks | N/A | 5.3 Implement the review-ledger swimlane component in `apps/kanban-viz` [M] |
| deferred:open-tasks | N/A | 5.4 Checkpoint: run kanban-viz tests, review diff, verify scope |
| deferred:open-tasks | N/A | 6.1 End-to-end test: commit → ambient review → ledger → compact → issue |
| deferred:open-tasks | N/A | 6.2 Document the ambient-review-ledger workflow including the kill-switch |
| deferred:open-tasks | N/A | 6.3 Checkpoint: full test suite, review cumulative diff, verify scope |
| deferred:open-tasks | N/A | 5.1 Pilot `--format=toon` behind a flag on the tabular list commands and A/B the token delta vs. JSON |
| deferred:open-tasks | N/A | 5.2 Update any human-facing docs / skill prompts that show example `feature list` output to reflect the envelope |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Live multi-vendor execution on the GX10 (real CLIs + keys) — nightly |
| deferred:open-tasks | N/A | 10-scenario suite + nightly cadence + `/improve-harness` wiring |
| deferred:open-tasks | N/A | Incident auto-seeding (`auto-seed-scenarios-from-incidents`) |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | 6.4 Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | 1.1 Validate the four contract schemas parse as JSON Schema 2020-12 and add a schema-lint test |
| deferred:open-tasks | N/A | 1.2 Add fixture instances (one valid + one invalid) per contract schema for downstream tests to reuse |
| deferred:open-tasks | N/A | 1.3 Checkpoint: run schema-lint + fixtures, review diff, verify scope (contracts/ only) |
| deferred:open-tasks | N/A | 2.1 Write tests for `arbitrage_signal` recording — five families, async non-blocking, no-op when disabled |
| deferred:open-tasks | N/A | 2.2 Create `agent-coordinator/src/arbitrage_signal.py` — record via `AuditService.log_operation` (operation `arbitrage.s |
| deferred:open-tasks | N/A | 2.3 Register the `coordinator.signal` OTel meter in `telemetry.py` and emit labelled measurements (vendor/model/modality |
| deferred:open-tasks | N/A | 2.4 Checkpoint: run coordinator unit tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.5 Write tests for the kill-switch flag `ARBITRAGE_INSTRUMENT_ENABLED` — default off no-ops recording + telemetry |
| deferred:open-tasks | N/A | 2.6 Implement the feature-flag gate in `arbitrage_signal` and a shared `is_enabled()` helper |
| deferred:open-tasks | N/A | 2.7 Write tests for Cedar eligibility — programmatic-ineligible vendor rejected; eligibility change takes effect without |
| deferred:open-tasks | N/A | 2.8 Extend `cedar/schema.cedarschema` with Agent attributes `vendor` / `modality` / `data_residency` and add `forbid()`  |
| deferred:open-tasks | N/A | 2.9 Add eligibility values to `agents.yaml` / `agent_profiles.metadata` (mutable, NOTIFY-invalidated) — Claude lead-elig |
| deferred:open-tasks | N/A | 2.10 Checkpoint: run coordinator unit + policy tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.1 Write tests for the ToS monitor — changed content hash emits a compliance signal; unchanged emits none |
| deferred:open-tasks | N/A | 3.2 Create `agent-coordinator/src/probes/tos_monitor.py` — fetch + hash + diff the configured automation-clause URLs; re |
| deferred:open-tasks | N/A | 3.3 Write tests for the model canary — changed fingerprint emits a quality_drift signal |
| deferred:open-tasks | N/A | 3.4 Create `agent-coordinator/src/probes/model_canary.py` — fixed prompt per model, fingerprint response, record signal  |
| deferred:open-tasks | N/A | 3.5 Checkpoint: run probe tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.6 Register both probes as `WatchdogService` periodic jobs; verify they do not schedule when the instrument flag is off |
| deferred:open-tasks | N/A | 4.1 Write tests for the cost ledger — actual + counterfactual recorded; missing usage flagged estimated; headline metric |
| deferred:open-tasks | N/A | 4.2 Create `skills/vendor-arbitrage/scripts/ledger.py` + `eligibility.py` — load the versioned pricing/eligibility confi |
| deferred:open-tasks | N/A | 4.3 Write tests for the static-priority router — cheapest eligible tier; spill on 429; provenance recorded; rejects infe |
| deferred:open-tasks | N/A | 4.4 Create `skills/vendor-arbitrage/scripts/router.py` — `select_assignment(work_unit, feasible_set)`; feasibility via c |
| deferred:open-tasks | N/A | 4.5 Checkpoint: run skill tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.6 Write tests for tripwires — ToS-diff freezes a vendor; economic-kill fires below maintenance threshold; each writes  |
| deferred:open-tasks | N/A | 4.7 Create `skills/vendor-arbitrage/scripts/tripwires.py` — declarative thresholds; flip posture flag (vendor freeze) ho |
| deferred:open-tasks | N/A | 4.8 Write tests for the digest — reports net savings with/without estimates and lists fired tripwires |
| deferred:open-tasks | N/A | 4.9 Create `skills/vendor-arbitrage/scripts/digest.py` + `SKILL.md` — assemble the landscape report from the signal subs |
| deferred:open-tasks | N/A | 4.10 Checkpoint: run skill tests, review diff, verify scope |
| deferred:open-tasks | N/A | 5.1 Write an end-to-end test: feature-flag off ⇒ dispatch identical to baseline; flag on ⇒ a routed unit produces a ledg |
| deferred:open-tasks | N/A | 5.2 Cross-reference the new spec: mark the `observability` cost requirement fulfilled and the `symphony` `token-rate-lim |
| deferred:open-tasks | N/A | 5.3 Wire the `vendor-arbitrage` skill into `skills/install.sh` sync and add the kill-switch flag to docs |
| deferred:open-tasks | N/A | 5.4 Checkpoint: run full suite (coordinator + skills), `openspec validate --strict`, review cumulative diff, verify no s |
| deferred:open-tasks | N/A | 8.1 Run full `validate-feature` end-to-end on the sample frontend: deploy → smoke → gen-eval (Playwright path) → securit |
| deferred:open-tasks | N/A | 8.3 Verify `harness-engineering-features` rebases cleanly: cherry-pick its open commits onto this branch's HEAD and conf |
| deferred:open-tasks | N/A | 10.3 Commit on `openspec/fix-autopilot-archetype-and-apply-outcome` with subject `fix(autopilot): introduce validator ar |
| deferred:open-tasks | N/A | 10.4 Push to origin. (Left for the orchestrator.) |
| deferred:open-tasks | N/A | 11.1 (Out of scope for the change; done after merge:) update `docs/parallel-agentic-development.md` with the new dispatc |
| deferred:open-tasks | N/A | 11.2 (Out of scope:) consider whether structural enforcement of the loop-state.json contract (filesystem permissions, gi |
| deferred:open-tasks | N/A | 11.3 (Out of scope:) consider whether harness-silent-no-op detection (separate failure mode noted in proposal "Out of Sc |
| deferred:open-tasks | N/A | 6.1 Commit on `openspec/fix-compact-hook-phase-boundary-detection` with subject `fix(session-bootstrap): gate compact-ho |
| deferred:open-tasks | N/A | 6.2 Push to origin. |
| deferred:open-tasks | N/A | 6.3 (Out of scope for this change — done after merge to main:) update `docs/lessons-learned.md` if the gate semantics su |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | 0.1 (S) Validate `contracts/db/schema.sql`, `contracts/openapi/v1.yaml`, |
| deferred:open-tasks | N/A | 1.1 (S) Write migration test: applying `026_usage_stats.sql` creates |
| deferred:open-tasks | N/A | 1.2 (S) Create `agent-coordinator/database/migrations/026_usage_stats.sql` |
| deferred:open-tasks | N/A | 1.3 (M) Write tests for `UsageRecord` schema + `record_hash` stability and |
| deferred:open-tasks | N/A | 1.4 (M) Implement `collector/schema.py` (`UsageRecord` + `record_hash`) and |
| deferred:open-tasks | N/A | Checkpoint: run migration + schema/pricing tests, review diff, verify scope |
| deferred:open-tasks | N/A | 1.5 (M) Write tests for the Claude adapter against fixture JSONL |
| deferred:open-tasks | N/A | 1.6 (M) Implement `collector/adapters/base.py` (adapter protocol + |
| deferred:open-tasks | N/A | 1.7 (M) Write tests for `collector/store.py`: incremental watermark resume, |
| deferred:open-tasks | N/A | 1.8 (M) Implement `collector/store.py` (watermark, dedupe, spool) and the |
| deferred:open-tasks | N/A | Checkpoint: run collector test suite, review diff, verify scope |
| deferred:open-tasks | N/A | 2.1 (M) Write API tests: `/usage/ingest` idempotent batch, `/usage/summary` |
| deferred:open-tasks | N/A | 2.2 (M) Implement `/usage/*` routes in `coordination_api.py` (reuse Bearer |
| deferred:open-tasks | N/A | 2.3 (S) Add `GET /events/usage` SSE endpoint (Bearer-auth, optional |
| deferred:open-tasks | N/A | Checkpoint: run API + SSE tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.1 (M) Scaffold `apps/usage-stats/` from the kanban-viz Vite/TS config; |
| deferred:open-tasks | N/A | 3.2 (M) Implement `useUsage.ts` (Bearer fetch, SSE primary, polling |
| deferred:open-tasks | N/A | 3.3 (M) Write component tests, then implement chart components |
| deferred:open-tasks | N/A | Checkpoint: run frontend test suite, typecheck, review diff, verify scope |
| deferred:open-tasks | N/A | 4.1 (S) Write a test that the session-end hook invokes the collector and |
| deferred:open-tasks | N/A | 4.2 (S) Wire collector invocation into session-end (`skills/session-bootstrap` |
| deferred:open-tasks | N/A | 4.3 (M) Write Codex adapter tests against fixture `rollout-*.jsonl` |
| deferred:open-tasks | N/A | Checkpoint: run hook + Codex tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.4 (M) Write Gemini adapter tests against fixture `telemetry.log` OTEL |
| deferred:open-tasks | N/A | 4.5 (S) Implement `collector/adapters/antigravity.py` as an explicit |
| deferred:open-tasks | N/A | 5.1 (M) Merge packages; run full backend + frontend suites; end-to-end |
| deferred:open-tasks | N/A | 5.2 (S) Document at `docs/usage-stats/README.md` (collector run, vendor |
| deferred:open-tasks | N/A | Checkpoint: full suite green, review cumulative diff, verify all scopes |
| deferred:open-tasks | N/A | 1.1 Write contract test at two levels: (a) `review-findings.schema.json` is |
| deferred:open-tasks | N/A | 1.2 Add a new self-contained |
| deferred:open-tasks | N/A | 1.3 Write test for shared `emit_finding()` and `record_phase_status()` |
| deferred:open-tasks | N/A | 1.4 Implement `emit_finding()` + `record_phase_status()` (e.g. |
| deferred:open-tasks | N/A | 1.5 Write test for the fixability classifier: mechanical finding-types |
| deferred:open-tasks | N/A | 1.6 Implement the classifier with a mechanical-type allowlist; default |
| deferred:open-tasks | N/A | 1.7 Write test for the narrow single-finding auto-fix step: one `auto-fix` |
| deferred:open-tasks | N/A | 1.8 Implement the narrow single-finding fixer: map a finding class to its |
| deferred:open-tasks | N/A | 1.9 Write test: the report renderer produces `validation-report.md` from |
| deferred:open-tasks | N/A | 1.10 Refactor SKILL.md §11/§12 report step to render from the findings file; |
| deferred:open-tasks | N/A | 1.C **Checkpoint**: `pytest skills/tests/validate-feature/` green; a sample |
| deferred:open-tasks | N/A | 2.1 Write test for the critical-subset runner: it executes only `smoke`, spec |
| deferred:open-tasks | N/A | 2.2 Implement the critical-subset runner reusing the existing phase scripts |
| deferred:open-tasks | N/A | 2.3 Write tests for wiring + inert-until-enabled + kill-switch: (a) fresh |
| deferred:open-tasks | N/A | 2.4 Add the `.githooks/pre-push` hook (inert no-op unless the |
| deferred:open-tasks | N/A | 2.5 Document the gate (install, kill-switch, `--no-verify`) in SKILL.md and |
| deferred:open-tasks | N/A | 2.C **Checkpoint**: with the hook installed, a drifted `tasks.md` blocks a |
| deferred:open-tasks | N/A | 3.1 Write test: on a clean tree `--ephemeral` runs in a scratch worktree |
| deferred:open-tasks | N/A | 3.2 Implement `--ephemeral` (+ `--include-dirty`) over the `worktree` skill |
| deferred:open-tasks | N/A | 3.3 Write test: under a stubbed cloud-harness `detect()`, `--ephemeral` |
| deferred:open-tasks | N/A | 3.4 Implement the cloud-harness fallback via `environment_profile.detect()`. |
| deferred:open-tasks | N/A | 3.C **Checkpoint**: after an `--ephemeral` run, `git status` on the branch |
| deferred:open-tasks | N/A | 4.1 Write test for the `triage_state` apply/render path: `approve` / `fix` / |
| deferred:open-tasks | N/A | 4.2 Implement the shared `triage_state` apply/render path (single source for |
| deferred:open-tasks | N/A | 4.3 Write test for `--auto` / `-y`: deterministic defaults — resolved |
| deferred:open-tasks | N/A | 4.4 Implement `--triage` (AskUserQuestion in-harness / CLI prompt loop) and |
| deferred:open-tasks | N/A | 4.5 Document `--triage` / `--auto` and the fixability/triage_state lifecycle in SKILL.md. |
| deferred:open-tasks | N/A | 4.C **Checkpoint**: a triage session marks a finding `skip`; a re-run skips |
| deferred:open-tasks | N/A | 5.1 Run `openspec validate validate-feature-findings-gate --strict` and fix |
| deferred:open-tasks | N/A | 5.2 Update `skills/validate-feature/SKILL.md` argument list + phase table to |
| deferred:open-tasks | N/A | 5.3 Sync runtime skill copies via `install.sh` (per CLAUDE.md skills guide). |

## Low / Info Findings

- **Low**: 683 findings
- **Info**: 0 findings

_(See JSON report for full details)_

## Recommendations

1. Run /fix-scrub --tier auto for quick lint fixes
2. Consolidate deferred items into a follow-up proposal
3. Consider running /fix-scrub --dry-run to preview remediation plan
