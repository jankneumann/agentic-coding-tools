"""Help service — progressive discovery for coordinator capabilities.

Instead of dumping all tool schemas into an agent's context window,
this service lets agents pull detailed help on-demand:

  help()              → compact overview of all capability groups (~200 tokens)
  help(topic="locks") → detailed guide for one group (~400 tokens)

This follows the CLI progressive discovery pattern (git --help vs git commit --help)
and is dramatically more context-efficient than MCP's eager schema loading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HelpTopic:
    """A single help topic with progressive detail levels."""

    name: str
    summary: str
    description: str
    tools: list[str]
    workflow: list[str]
    best_practices: list[str]
    examples: list[dict[str, str]]
    related: list[str] = field(default_factory=list)


# =============================================================================
# Help content registry
# =============================================================================

_TOPICS: dict[str, HelpTopic] = {}


def _register(topic: HelpTopic) -> None:
    _TOPICS[topic.name] = topic


_register(HelpTopic(
    name="locks",
    summary="Exclusive file locking to prevent concurrent edits",
    description=(
        "File locks prevent merge conflicts when multiple agents work on the same "
        "codebase. Locks are advisory — agents should always check and respect them. "
        "Locks auto-expire after a configurable TTL (default 2 hours)."
    ),
    tools=["acquire_lock", "release_lock", "check_locks"],
    workflow=[
        "1. check_locks() to see if your target files are available",
        "2. acquire_lock(file_path, reason='...') to claim exclusive access",
        "3. Edit the file(s)",
        "4. release_lock(file_path) — ALWAYS release, even on error",
    ],
    best_practices=[
        "Always check locks before acquiring — another agent may already hold them",
        "Provide a descriptive reason so other agents understand the hold",
        "Release locks promptly — don't hold across session boundaries",
        "Lock at the most specific scope possible (single file, not directory)",
        "If a lock is held by a stale agent, wait for TTL expiry or contact the operator",
    ],
    examples=[
        {
            "description": "Safe file edit pattern",
            "code": (
                'locks = check_locks(["src/main.py"])\n'
                "# Verify it's free, then:\n"
                'acquire_lock("src/main.py", reason="refactoring error handling")\n'
                "# ... edit the file ...\n"
                'release_lock("src/main.py")'
            ),
        },
    ],
    related=["guardrails", "features"],
))

_register(HelpTopic(
    name="work-queue",
    summary="Task assignment, tracking, and dependency management",
    description=(
        "The work queue enables coordinated task distribution across agents. "
        "Tasks are claimed atomically — once you get a task, no other agent will. "
        "Supports priorities (1=highest, 10=lowest) and inter-task dependencies."
    ),
    tools=["get_work", "complete_work", "submit_work", "get_task"],
    workflow=[
        "1. get_work(task_types=['refactor','test']) to claim a task",
        "2. Perform the work described in the task",
        "3. complete_work(task_id, success=True, result={...}) to report completion",
        "4. Use submit_work() to create subtasks for other agents",
    ],
    best_practices=[
        "Always complete tasks — call complete_work even on failure (success=False)",
        "Use task_types to only claim work you're capable of handling",
        "Include meaningful result data so the requesting agent can use it",
        "Set depends_on when creating subtasks that require ordering",
        "Check get_task() to monitor subtask progress before proceeding",
    ],
    examples=[
        {
            "description": "Claim and complete a task",
            "code": (
                'work = get_work(task_types=["test", "review"])\n'
                'if work["success"]:\n'
                '    # Do the work...\n'
                '    complete_work(work["task_id"], success=True, result={"tests_passed": 42})'
            ),
        },
        {
            "description": "Create a subtask with dependencies",
            "code": (
                'result = submit_work(\n'
                '    task_type="test",\n'
                '    description="Write unit tests for cache module",\n'
                '    input_data={"files": ["src/cache.py"]},\n'
                '    priority=3\n'
                ')'
            ),
        },
    ],
    related=["issues"],
))

_register(HelpTopic(
    name="issues",
    summary="Issue tracking with epics, dependencies, and search",
    description=(
        "A built-in issue tracker for coordinating work across agents and sessions. "
        "Supports issue types (task, epic, bug, feature), parent-child relationships "
        "(epics), cross-issue dependencies, labels, and text search."
    ),
    tools=[
        "issue_create", "issue_list", "issue_show", "issue_update",
        "issue_close", "issue_comment", "issue_ready", "issue_blocked",
        "issue_search",
    ],
    workflow=[
        "1. issue_create() to log bugs, tasks, or feature requests",
        "2. issue_list(status='open') to see what needs doing",
        "3. issue_ready() to find issues with no blocking dependencies",
        "4. issue_update() to change status, priority, or assignment",
        "5. issue_comment() to log progress or decisions",
        "6. issue_close(reason='...') when done",
    ],
    best_practices=[
        "Use epics (issue_type='epic') to group related work items",
        "Set depends_on to model task ordering — issue_ready() respects this",
        "Use issue_blocked() to identify bottlenecks in your workflow",
        "Add labels for categorization — filters in issue_list support them",
        "Comment on issues to create an audit trail of decisions",
    ],
    examples=[
        {
            "description": "Create an epic with children",
            "code": (
                'epic = issue_create(title="Auth overhaul", issue_type="epic", priority=2)\n'
                'issue_create(\n'
                '    title="Add OAuth provider",\n'
                '    parent_id=epic["issue"]["id"],\n'
                '    labels=["auth", "backend"]\n'
                ')'
            ),
        },
    ],
    related=["work-queue"],
))

_register(HelpTopic(
    name="handoffs",
    summary="Session continuity documents for cross-session context",
    description=(
        "Handoff documents preserve session context when an agent's session ends "
        "or hits context limits. The next session reads the handoff to resume "
        "seamlessly without losing decisions, progress, or in-flight work."
    ),
    tools=["write_handoff", "read_handoff"],
    workflow=[
        "1. read_handoff() at session start to get previous context",
        "2. Do your work throughout the session",
        "3. write_handoff(summary, completed_work, next_steps, ...) before ending",
    ],
    best_practices=[
        "Always write a handoff before ending a session — future-you will thank past-you",
        "Include completed_work, in_progress, and next_steps for full context",
        "List relevant_files so the next session knows where to look",
        "Record key decisions so they aren't re-debated in the next session",
        "Read handoffs at session start even if you're the same agent — context may have compacted",
    ],
    examples=[
        {
            "description": "Write a session handoff",
            "code": (
                'write_handoff(\n'
                '    summary="Completed auth module refactor, tests passing",\n'
                '    completed_work=["Refactored auth middleware", "Added OAuth support"],\n'
                '    in_progress=["E2E test for login flow"],\n'
                '    decisions=["Chose PKCE over implicit grant for security"],\n'
                '    next_steps=["Finish E2E tests", "Update API docs"],\n'
                '    relevant_files=["src/auth/", "tests/test_auth.py"]\n'
                ')'
            ),
        },
    ],
    related=["memory", "discovery"],
))

_register(HelpTopic(
    name="memory",
    summary="Persistent episodic memory across sessions",
    description=(
        "Episodic memory lets agents store and recall experiences across sessions. "
        "Use it for lessons learned, past decisions, and patterns that should persist "
        "beyond a single context window. Supports tag-based retrieval."
    ),
    tools=["remember", "recall"],
    workflow=[
        "1. remember(event_type, summary, tags=[...]) to store an experience",
        "2. recall(tags=['relevant-tag']) to retrieve past experiences",
    ],
    best_practices=[
        "Store lessons learned from debugging — they prevent repeat mistakes",
        "Use consistent tags for retrieval (e.g., 'auth', 'performance', 'deployment')",
        "Record decisions with context so they can be re-evaluated later",
        "Include outcome field to track whether approaches succeeded or failed",
        "Don't over-store — focus on insights that generalize across sessions",
    ],
    examples=[
        {
            "description": "Store a debugging lesson",
            "code": (
                'remember(\n'
                '    event_type="debugging",\n'
                '    summary="Connection pool exhaustion caused by unclosed cursors",\n'
                '    details={"root_cause": "missing async with on db.cursor()"},\n'
                '    outcome="Fixed by adding context manager",\n'
                '    tags=["database", "performance", "debugging"]\n'
                ')'
            ),
        },
    ],
    related=["handoffs"],
))

_register(HelpTopic(
    name="discovery",
    summary="Agent registration, heartbeat, and peer discovery",
    description=(
        "Discovery lets agents register their presence, find peers, and maintain "
        "heartbeats. This enables multi-agent coordination — agents can discover "
        "who else is active and what they're working on."
    ),
    tools=["register_session", "discover_agents", "heartbeat", "cleanup_dead_agents"],
    workflow=[
        "1. register_session() at session start (auto-done via hooks)",
        "2. heartbeat() periodically to signal liveness",
        "3. discover_agents() to find active peers",
        "4. cleanup_dead_agents() to prune stale entries (admin only)",
    ],
    best_practices=[
        "Registration is typically handled by session hooks — don't double-register",
        "Use discover_agents() to check if other agents are active before starting work",
        "Heartbeats are sent automatically via hooks — manual heartbeat is rarely needed",
        "Include current_task in register_session so peers know what you're doing",
    ],
    examples=[
        {
            "description": "Discover active peers",
            "code": (
                'agents = discover_agents()\n'
                'for agent in agents["agents"]:\n'
                '    print(f"{agent[\'agent_id\']}: {agent[\'current_task\']}")'
            ),
        },
    ],
    related=["handoffs", "features"],
))

_register(HelpTopic(
    name="guardrails",
    summary="Detect and block destructive operations",
    description=(
        "Guardrails scan operation text for destructive patterns (rm -rf, DROP TABLE, "
        "force-push, etc.) and block or warn based on severity and agent trust level. "
        "Use this as a safety net before executing risky commands."
    ),
    tools=["check_guardrails"],
    workflow=[
        "1. check_guardrails(operation_text='git push --force') before executing",
        "2. If safe=False, review violations and either abort or escalate",
    ],
    best_practices=[
        "Check guardrails before any shell command that modifies shared state",
        "Include file_paths for context-aware risk assessment",
        "Higher trust levels get more permissive guardrails — don't try to bypass",
        "If blocked, consider a safer alternative rather than escalating",
    ],
    examples=[
        {
            "description": "Check before executing a command",
            "code": (
                'result = check_guardrails(\n'
                '    operation_text="rm -rf /tmp/build-artifacts",\n'
                '    file_paths=["/tmp/build-artifacts"]\n'
                ')\n'
                'if result["safe"]:\n'
                '    # Proceed with the operation\n'
                '    ...\n'
                'else:\n'
                '    # Review violations\n'
                '    for v in result["violations"]:\n'
                '        print(f"BLOCKED: {v[\'pattern_name\']} ({v[\'severity\']})")'
            ),
        },
    ],
    related=["policy", "profiles"],
))

_register(HelpTopic(
    name="profiles",
    summary="Agent identity, trust levels, and permissions",
    description=(
        "Agent profiles define trust levels (0-4) and operation restrictions. "
        "Higher trust levels unlock more capabilities. Profiles are configured "
        "in agents.yaml and enforced across all transports."
    ),
    tools=["get_my_profile", "get_agent_dispatch_configs"],
    workflow=[
        "1. get_my_profile() to see your trust level and restrictions",
        "2. Use this to understand what operations are available to you",
    ],
    best_practices=[
        "Check your profile at session start to understand your capabilities",
        "Don't attempt operations above your trust level — they'll be denied",
        "get_agent_dispatch_configs() shows how to dispatch work to other vendors",
    ],
    examples=[
        {
            "description": "Check your capabilities",
            "code": (
                'profile = get_my_profile()\n'
                'print(f"Trust level: {profile[\'trust_level\']}")\n'
                'print(f"Restrictions: {profile[\'restricted_operations\']}")'
            ),
        },
    ],
    related=["guardrails", "policy"],
))

_register(HelpTopic(
    name="policy",
    summary="Authorization checks and Cedar policy engine",
    description=(
        "The policy engine authorizes operations based on agent identity, trust level, "
        "and configurable policies. Supports both native profile-based authorization "
        "and Cedar policy language for fine-grained control."
    ),
    tools=["check_policy", "validate_cedar_policy"],
    workflow=[
        "1. check_policy(operation, resource) to verify authorization",
        "2. validate_cedar_policy(policy_text) to check Cedar syntax",
    ],
    best_practices=[
        "Policy checks happen automatically on HTTP endpoints — MCP agents are trusted",
        "Use check_policy() for pre-flight authorization before expensive operations",
        "Cedar policies enable fine-grained, composable authorization rules",
    ],
    examples=[
        {
            "description": "Check if an operation is allowed",
            "code": (
                'result = check_policy(\n'
                '    operation="delete_branch",\n'
                '    resource="main",\n'
                '    context={"force": True}\n'
                ')\n'
                'if result["allowed"]:\n'
                '    # Proceed\n'
                '    ...'
            ),
        },
    ],
    related=["guardrails", "profiles"],
))

_register(HelpTopic(
    name="audit",
    summary="Immutable operation audit trail",
    description=(
        "Every coordination operation is logged to an immutable audit trail. "
        "Use this for debugging, compliance, and understanding what happened "
        "during multi-agent sessions."
    ),
    tools=["query_audit"],
    workflow=[
        "1. query_audit(agent_id='...', operation='...') to search the log",
        "2. Review entries to understand operation history",
    ],
    best_practices=[
        "Audit logs are written automatically — you don't need to create them",
        "Use agent_id filter to see what a specific agent did",
        "Use operation filter to track specific action types",
        "Audit entries include duration_ms for performance analysis",
    ],
    examples=[
        {
            "description": "Review recent lock operations",
            "code": (
                'entries = query_audit(operation="acquire_lock", limit=10)\n'
                'for e in entries["entries"]:\n'
                '    print(f"{e[\'agent_id\']}: {e[\'operation\']} (success={e[\'success\']})")'
            ),
        },
    ],
    related=["profiles"],
))

_register(HelpTopic(
    name="features",
    summary="Parallel feature coordination and resource conflict detection",
    description=(
        "The feature registry tracks which features are being developed in parallel, "
        "what resources (files, modules) they claim, and detects conflicts before "
        "they cause merge problems. Essential for multi-agent parallel development."
    ),
    tools=[
        "register_feature", "deregister_feature", "get_feature",
        "list_active_features", "analyze_feature_conflicts",
    ],
    workflow=[
        "1. list_active_features() to see what's in progress",
        "2. analyze_feature_conflicts(feature_id, claims) BEFORE starting work",
        "3. register_feature(feature_id, resource_claims=[...]) to claim resources",
        "4. Develop your feature",
        "5. deregister_feature(feature_id) when merged or cancelled",
    ],
    best_practices=[
        "Always check for conflicts before registering — prevents wasted work",
        "Claim resources at the right granularity (file paths, module names)",
        "Register early so other agents can see your claims",
        "Deregister promptly after merge to free resources",
        "Use merge_priority to influence merge ordering",
    ],
    examples=[
        {
            "description": "Register a feature with resource claims",
            "code": (
                'register_feature(\n'
                '    feature_id="auth-overhaul",\n'
                '    resource_claims=["src/auth/", "src/middleware/auth.py"],\n'
                '    title="Authentication system overhaul",\n'
                '    branch_name="openspec/auth-overhaul"\n'
                ')'
            ),
        },
    ],
    related=["merge-queue", "locks"],
))

_register(HelpTopic(
    name="merge-queue",
    summary="Ordered PR merge queue with pre-merge checks",
    description=(
        "The merge queue manages the order in which feature branches are merged "
        "to main. It runs pre-merge checks (conflict detection, CI status) and "
        "enforces priority-based ordering to prevent merge conflicts."
    ),
    tools=[
        "enqueue_merge", "get_merge_queue", "get_next_merge",
        "run_pre_merge_checks", "mark_merged", "remove_from_merge_queue",
    ],
    workflow=[
        "1. enqueue_merge(feature_id, pr_url='...') when PR is ready",
        "2. get_next_merge() to see which feature should merge next",
        "3. run_pre_merge_checks(feature_id) before merging",
        "4. mark_merged(feature_id) after successful merge",
    ],
    best_practices=[
        "Enqueue features via /cleanup-feature skill — it handles the full flow",
        "Higher merge_priority (lower number) merges first",
        "Pre-merge checks detect resource conflicts with other queued features",
        "Use remove_from_merge_queue() to dequeue cancelled features",
    ],
    examples=[
        {
            "description": "Enqueue and merge a feature",
            "code": (
                'enqueue_merge(feature_id="auth-overhaul", pr_url="https://github.com/org/repo/pull/42")\n'
                'checks = run_pre_merge_checks("auth-overhaul")\n'
                'if checks["passed"]:\n'
                '    # Merge the PR, then:\n'
                '    mark_merged("auth-overhaul")'
            ),
        },
    ],
    related=["features"],
))

_register(HelpTopic(
    name="approvals",
    summary="Human-in-the-loop approval workflows",
    description=(
        "Approval workflows allow agents to request human authorization for "
        "high-risk operations. Requests are queued until a human decides. "
        "Use request_permission() for trust-level escalation within a session."
    ),
    tools=["request_approval", "check_approval", "request_permission"],
    workflow=[
        "1. request_approval(operation, justification) for one-off approvals",
        "2. check_approval(request_id) to poll for decision",
        "3. request_permission(operation, scope, justification) for session-scoped grants",
    ],
    best_practices=[
        "Provide clear justification — humans decide faster with good context",
        "Use request_permission() for repeated operations (grants last the session)",
        "Don't busy-wait on approvals — do other work and check back",
    ],
    examples=[
        {
            "description": "Request approval for a destructive operation",
            "code": (
                'result = request_approval(\n'
                '    operation="drop_table",\n'
                '    resource="users",\n'
                '    justification="Table redesigned; data migrated to users_v2"\n'
                ')\n'
                '# Later:\n'
                'status = check_approval(result["request_id"])'
            ),
        },
    ],
    related=["guardrails", "policy"],
))

_register(HelpTopic(
    name="ports",
    summary="Port allocation for isolated service instances",
    description=(
        "Port allocation prevents conflicts when multiple agents run local "
        "services (dev servers, databases, etc.) on the same machine. "
        "Each session gets a unique port range."
    ),
    tools=["allocate_ports", "release_ports", "ports_status"],
    workflow=[
        "1. allocate_ports(session_id) to claim a port range",
        "2. Use the allocated ports for your services",
        "3. release_ports(session_id) when done",
    ],
    best_practices=[
        "Always release ports when your session ends",
        "Use ports_status() to see current allocations before manual assignment",
        "Port ranges are session-scoped — they auto-release on session cleanup",
    ],
    examples=[
        {
            "description": "Allocate ports for a dev server",
            "code": (
                'ports = allocate_ports(session_id="my-session")\n'
                'api_port = ports["ports"]["api"]\n'
                'db_port = ports["ports"]["database"]'
            ),
        },
    ],
    related=["discovery"],
))

_register(HelpTopic(
    name="status",
    summary="Agent status reporting and phase tracking",
    description=(
        "Status reporting lets agents broadcast their current phase, progress, "
        "and whether they need human intervention. Reports also trigger heartbeats "
        "and can feed into notification channels (email, Telegram, webhooks)."
    ),
    tools=["report_status"],
    workflow=[
        "1. report_status(agent_id, change_id, phase, message) at phase transitions",
        "2. Set needs_human=True when you're blocked and need operator input",
    ],
    best_practices=[
        "Report at natural phase boundaries (planning → implementing → testing)",
        "Use needs_human=True sparingly — only when genuinely blocked",
        "Status reports double as heartbeats — no separate heartbeat needed",
        "Include metadata for structured information (test counts, error details)",
    ],
    examples=[
        {
            "description": "Report a phase transition",
            "code": (
                'report_status(\n'
                '    agent_id="claude-local",\n'
                '    change_id="auth-overhaul",\n'
                '    phase="IMPLEMENTING",\n'
                '    message="Tests passing, starting integration tests"\n'
                ')'
            ),
        },
    ],
    related=["discovery"],
))


# =============================================================================
# Service interface
# =============================================================================


def get_help_overview() -> dict[str, Any]:
    """Return a compact overview of all capability groups.

    Designed to be ~200 tokens — enough for an agent to decide
    which topic to drill into.
    """
    groups = []
    for topic in _TOPICS.values():
        groups.append({
            "topic": topic.name,
            "summary": topic.summary,
            "tools_count": len(topic.tools),
        })

    return {
        "version": "0.2.0",
        "usage": "Call help(topic='<name>') for detailed guidance on any topic",
        "topics": groups,
    }


def get_help_topic(topic: str) -> dict[str, Any] | None:
    """Return detailed help for a specific topic.

    Returns None if the topic doesn't exist.
    Designed to be ~300-500 tokens — enough for an agent to use
    the capability effectively without having read the source code.
    """
    t = _TOPICS.get(topic)
    if t is None:
        return None

    return {
        "topic": t.name,
        "summary": t.summary,
        "description": t.description,
        "tools": t.tools,
        "workflow": t.workflow,
        "best_practices": t.best_practices,
        "examples": t.examples,
        "related_topics": t.related,
    }


def list_topic_names() -> list[str]:
    """Return all available topic names."""
    return list(_TOPICS.keys())
