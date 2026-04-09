"""Coordination CLI — token-efficient command-line interface for AI agents.

Mirrors all coordinator capabilities via subcommands with --json output.
Reuses the same async service layer as MCP and HTTP interfaces.

Usage:
    coordination-cli --help
    coordination-cli --json feature list
    coordination-cli merge-queue enqueue --feature-id my-feature
    coordination-cli health
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any


def _run(coro: Any) -> Any:
    """Bridge async service calls to synchronous CLI."""
    return asyncio.run(coro)


def _output(data: Any, *, json_mode: bool) -> None:
    """Print result as JSON or human-readable text."""
    if json_mode:
        print(json.dumps(data, indent=2, default=str))
        return

    if isinstance(data, dict):
        _print_dict(data)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                _print_dict(item)
                print()
            else:
                print(item)
    else:
        print(data)


def _print_dict(d: dict[str, Any], indent: int = 0) -> None:
    """Print a dict as aligned key: value pairs."""
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            print(f"{prefix}{k}:")
            _print_dict(v, indent + 1)
        elif isinstance(v, list):
            if not v:
                print(f"{prefix}{k}: []")
            elif len(v) <= 5 and all(isinstance(i, str) for i in v):
                print(f"{prefix}{k}: {', '.join(v)}")
            else:
                print(f"{prefix}{k}:")
                for item in v:
                    if isinstance(item, dict):
                        _print_dict(item, indent + 1)
                        print()
                    else:
                        print(f"{prefix}  - {item}")
        else:
            print(f"{prefix}{k}: {v}")


def _error(msg: str) -> int:
    """Print error to stderr and return exit code 1."""
    print(f"error: {msg}", file=sys.stderr)
    return 1


# =============================================================================
# Subcommand handlers
# =============================================================================


def cmd_health(args: argparse.Namespace) -> int:
    """Check coordinator health."""
    from .config import get_config
    from .db import get_db

    try:
        db = get_db()
        _run(db.query("file_locks", "limit=0"))
        cfg = get_config()
        data = {
            "status": "ok",
            "db": "connected",
            "backend": cfg.database.backend,
            "version": "0.2.0",
        }
    except Exception as exc:
        data = {"status": "error", "db": "unreachable", "error": str(exc)}
        _output(data, json_mode=args.json)
        return 1

    _output(data, json_mode=args.json)
    return 0


# -- Feature Registry --------------------------------------------------------


def cmd_feature_register(args: argparse.Namespace) -> int:
    """Register a feature with resource claims."""
    from .feature_registry import get_feature_registry_service

    claims = args.claims or []
    result = _run(get_feature_registry_service().register(
        feature_id=args.feature_id,
        resource_claims=claims,
        title=args.title,
        agent_id=args.agent_id,
        branch_name=args.branch_name,
        merge_priority=args.merge_priority,
        metadata=json.loads(args.metadata) if args.metadata else None,
    ))
    _output({
        "success": result.success,
        "feature_id": result.feature_id,
        "action": result.action,
        "reason": result.reason,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_feature_deregister(args: argparse.Namespace) -> int:
    """Deregister a feature."""
    from .feature_registry import get_feature_registry_service

    result = _run(get_feature_registry_service().deregister(
        feature_id=args.feature_id,
        status=args.status,
    ))
    _output({
        "success": result.success,
        "feature_id": result.feature_id,
        "status": result.status,
        "reason": result.reason,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_feature_show(args: argparse.Namespace) -> int:
    """Show details of a feature."""
    from .feature_registry import get_feature_registry_service

    feature = _run(get_feature_registry_service().get_feature(args.feature_id))
    if feature is None:
        return _error(f"feature not found: {args.feature_id}")
    _output({
        "feature_id": feature.feature_id,
        "title": feature.title,
        "status": feature.status,
        "registered_by": feature.registered_by,
        "resource_claims": feature.resource_claims,
        "branch_name": feature.branch_name,
        "merge_priority": feature.merge_priority,
        "metadata": feature.metadata,
        "registered_at": feature.registered_at.isoformat() if feature.registered_at else None,
    }, json_mode=args.json)
    return 0


def cmd_feature_list(args: argparse.Namespace) -> int:
    """List active features."""
    from .feature_registry import get_feature_registry_service

    features = _run(get_feature_registry_service().get_active_features())
    data = [
        {
            "feature_id": f.feature_id,
            "title": f.title,
            "status": f.status,
            "merge_priority": f.merge_priority,
            "claims": len(f.resource_claims),
            "branch_name": f.branch_name,
        }
        for f in features
    ]
    _output(data, json_mode=args.json)
    return 0


def cmd_feature_conflicts(args: argparse.Namespace) -> int:
    """Analyze resource conflicts for a candidate feature."""
    from .feature_registry import get_feature_registry_service

    report = _run(get_feature_registry_service().analyze_conflicts(
        args.feature_id,
        args.claims,
    ))
    _output({
        "candidate_feature_id": report.candidate_feature_id,
        "feasibility": report.feasibility.value,
        "total_candidate_claims": report.total_candidate_claims,
        "total_conflicting_claims": report.total_conflicting_claims,
        "conflicts": report.conflicts,
    }, json_mode=args.json)
    return 0


# -- Merge Queue -------------------------------------------------------------


def cmd_mq_enqueue(args: argparse.Namespace) -> int:
    """Enqueue a feature for merge."""
    from .merge_queue import get_merge_queue_service

    entry = _run(get_merge_queue_service().enqueue(
        feature_id=args.feature_id,
        pr_url=args.pr_url,
    ))
    if entry is None:
        return _error("feature not found or not active")
    _output({
        "feature_id": entry.feature_id,
        "merge_status": entry.merge_status.value,
        "merge_priority": entry.merge_priority,
        "pr_url": entry.pr_url,
    }, json_mode=args.json)
    return 0


def cmd_mq_status(args: argparse.Namespace) -> int:
    """Show merge queue status."""
    from .merge_queue import get_merge_queue_service

    entries = _run(get_merge_queue_service().get_queue())
    data = [
        {
            "feature_id": e.feature_id,
            "merge_status": e.merge_status.value,
            "merge_priority": e.merge_priority,
            "pr_url": e.pr_url,
            "queued_at": e.queued_at.isoformat() if e.queued_at else None,
        }
        for e in entries
    ]
    _output(data, json_mode=args.json)
    return 0


def cmd_mq_next(args: argparse.Namespace) -> int:
    """Show the next feature ready to merge."""
    from .merge_queue import get_merge_queue_service

    entry = _run(get_merge_queue_service().get_next_to_merge())
    if entry is None:
        _output({"entry": None, "reason": "no_features_ready"}, json_mode=args.json)
        return 0
    _output({
        "feature_id": entry.feature_id,
        "merge_status": entry.merge_status.value,
        "merge_priority": entry.merge_priority,
        "pr_url": entry.pr_url,
    }, json_mode=args.json)
    return 0


def cmd_mq_check(args: argparse.Namespace) -> int:
    """Run pre-merge checks on a feature."""
    from .merge_queue import get_merge_queue_service

    result = _run(get_merge_queue_service().run_pre_merge_checks(args.feature_id))
    _output({
        "feature_id": result.feature_id,
        "passed": result.passed,
        "checks": result.checks,
        "issues": result.issues,
        "conflicts": result.conflicts,
    }, json_mode=args.json)
    return 0 if result.passed else 1


def cmd_mq_merged(args: argparse.Namespace) -> int:
    """Mark a feature as merged."""
    from .merge_queue import get_merge_queue_service

    success = _run(get_merge_queue_service().mark_merged(args.feature_id))
    _output({"success": success, "feature_id": args.feature_id}, json_mode=args.json)
    return 0 if success else 1


def cmd_mq_remove(args: argparse.Namespace) -> int:
    """Remove a feature from the merge queue."""
    from .merge_queue import get_merge_queue_service

    success = _run(get_merge_queue_service().remove_from_queue(args.feature_id))
    _output({"success": success, "feature_id": args.feature_id}, json_mode=args.json)
    return 0 if success else 1


# -- Locks -------------------------------------------------------------------


def cmd_lock_acquire(args: argparse.Namespace) -> int:
    """Acquire a file lock."""
    from .locks import get_lock_service

    result = _run(get_lock_service().acquire(
        file_path=args.file_path,
        agent_id=args.agent_id,
        agent_type=args.agent_type or "cli",
        reason=args.reason,
        ttl_minutes=args.ttl_minutes,
    ))
    _output({
        "success": result.success,
        "action": result.action,
        "file_path": result.file_path,
        "expires_at": result.expires_at.isoformat() if result.expires_at else None,
        "reason": result.reason,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_lock_release(args: argparse.Namespace) -> int:
    """Release a file lock."""
    from .locks import get_lock_service

    result = _run(get_lock_service().release(
        file_path=args.file_path,
        agent_id=args.agent_id,
    ))
    _output({
        "success": result.success,
        "action": result.action,
        "file_path": result.file_path,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_lock_status(args: argparse.Namespace) -> int:
    """Check lock status."""
    from .locks import get_lock_service

    file_paths = args.file_paths or None
    locks = _run(get_lock_service().check(file_paths=file_paths))
    data = [
        {
            "file_path": lock.file_path,
            "locked_by": lock.locked_by,
            "agent_type": lock.agent_type,
            "reason": lock.reason,
            "expires_at": lock.expires_at.isoformat(),
        }
        for lock in locks
    ]
    _output(data, json_mode=args.json)
    return 0


# -- Work Queue --------------------------------------------------------------


def cmd_work_submit(args: argparse.Namespace) -> int:
    """Submit work to the queue."""
    from .work_queue import get_work_queue_service

    result = _run(get_work_queue_service().submit(
        task_type=args.task_type,
        description=args.description,
        priority=args.priority,
        input_data=json.loads(args.input_data) if args.input_data else None,
    ))
    _output({
        "success": result.success,
        "task_id": str(result.task_id) if result.task_id else None,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_work_claim(args: argparse.Namespace) -> int:
    """Claim work from the queue."""
    from .work_queue import get_work_queue_service

    result = _run(get_work_queue_service().claim(
        agent_id=args.agent_id,
        agent_type=args.agent_type or "cli",
        task_types=args.task_types,
    ))
    _output({
        "success": result.success,
        "task_id": str(result.task_id) if result.task_id else None,
        "task_type": result.task_type,
        "description": result.description,
        "priority": result.priority,
        "reason": result.reason,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_work_complete(args: argparse.Namespace) -> int:
    """Complete a work queue task."""
    from uuid import UUID

    from .work_queue import get_work_queue_service

    result = _run(get_work_queue_service().complete(
        task_id=UUID(args.task_id),
        success=args.success,
        result=json.loads(args.result_data) if args.result_data else None,
        error_message=args.error_message,
    ))
    _output({
        "success": result.success,
        "status": result.status,
        "task_id": str(result.task_id) if result.task_id else None,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_work_get(args: argparse.Namespace) -> int:
    """Get a specific task by ID."""
    from uuid import UUID

    from .work_queue import get_work_queue_service

    task = _run(get_work_queue_service().get_task(UUID(args.task_id)))
    if task is None:
        return _error(f"task not found: {args.task_id}")
    _output({
        "id": str(task.id),
        "task_type": task.task_type,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "claimed_by": task.claimed_by,
    }, json_mode=args.json)
    return 0


# -- Handoff -----------------------------------------------------------------


def cmd_handoff_write(args: argparse.Namespace) -> int:
    """Write a handoff document."""
    from .handoffs import get_handoff_service

    result = _run(get_handoff_service().write(
        summary=args.summary,
        agent_name=args.agent_id,
        session_id=args.session_id,
    ))
    _output({
        "success": result.success,
        "handoff_id": str(result.handoff_id) if result.handoff_id else None,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_handoff_read(args: argparse.Namespace) -> int:
    """Read handoff documents."""
    from .handoffs import get_handoff_service

    result = _run(get_handoff_service().read(
        agent_name=args.agent_name,
        limit=args.limit,
    ))
    data = [
        {
            "id": str(h.id),
            "agent_name": h.agent_name,
            "summary": h.summary,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in result.handoffs
    ]
    _output(data, json_mode=args.json)
    return 0


# -- Memory ------------------------------------------------------------------


def cmd_memory_store(args: argparse.Namespace) -> int:
    """Store an episodic memory."""
    from .memory import get_memory_service

    result = _run(get_memory_service().remember(
        event_type=args.event_type,
        summary=args.summary,
        tags=args.tags,
        agent_id=args.agent_id,
    ))
    _output({
        "success": result.success,
        "memory_id": result.memory_id,
        "action": result.action,
    }, json_mode=args.json)
    return 0 if result.success else 1


def cmd_memory_query(args: argparse.Namespace) -> int:
    """Query episodic memories."""
    from .memory import get_memory_service

    result = _run(get_memory_service().recall(
        tags=args.tags,
        event_type=args.event_type,
        limit=args.limit,
    ))
    data = [
        {
            "event_type": m.event_type,
            "summary": m.summary,
            "tags": m.tags,
            "relevance_score": m.relevance_score,
        }
        for m in result.memories
    ]
    _output(data, json_mode=args.json)
    return 0


# -- Guardrails --------------------------------------------------------------


def cmd_guardrails_check(args: argparse.Namespace) -> int:
    """Check an operation for destructive patterns."""
    from .guardrails import get_guardrails_service

    result = _run(get_guardrails_service().check_operation(
        operation_text=args.operation_text,
        file_paths=args.file_paths,
    ))
    _output({
        "safe": result.safe,
        "violations": [
            {"pattern_name": v.pattern_name, "severity": v.severity, "blocked": v.blocked}
            for v in result.violations
        ],
    }, json_mode=args.json)
    return 0 if result.safe else 1


# -- Audit -------------------------------------------------------------------


def cmd_audit_query(args: argparse.Namespace) -> int:
    """Query audit trail."""
    from .audit import get_audit_service

    entries = _run(get_audit_service().query(
        agent_id=args.agent_id,
        operation=args.operation,
        limit=args.limit,
    ))
    data = [
        {
            "operation": e.operation,
            "agent_id": e.agent_id,
            "success": e.success,
            "duration_ms": e.duration_ms,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]
    _output(data, json_mode=args.json)
    return 0


# -- Help (Progressive Discovery) --------------------------------------------


def cmd_help(args: argparse.Namespace) -> int:
    """Show help for coordinator capabilities with progressive detail."""
    from .help_service import get_help_overview, get_help_topic, list_topic_names

    topic = getattr(args, "topic", None)

    if topic is None:
        data = get_help_overview()
        if args.json:
            _output(data, json_mode=True)
        else:
            print("Coordinator Capabilities")
            print("=" * 50)
            print(f"Version: {data['version']}")
            print()
            for t in data["topics"]:
                print(f"  {t['topic']:<16} {t['summary']} ({t['tools_count']} tools)")
            print()
            print("Usage: coordination-cli help <topic>")
            print("  e.g. coordination-cli help locks")
        return 0

    detail = get_help_topic(topic)
    if detail is None:
        available = list_topic_names()
        if args.json:
            _output(
                {
                    "error": f"Unknown topic: {topic}",
                    "available_topics": available,
                    "hint": "Run coordination-cli help for all topics",
                },
                json_mode=True,
            )
        else:
            print(f"error: unknown topic '{topic}'")
            print(f"available: {', '.join(available)}")
        return 1

    if args.json:
        _output(detail, json_mode=True)
    else:
        print(f"{detail['topic']} — {detail['summary']}")
        print("=" * 50)
        print()
        print(detail["description"])
        print()
        print("Tools:")
        for tool in detail["tools"]:
            print(f"  - {tool}")
        print()
        print("Workflow:")
        for step in detail["workflow"]:
            print(f"  {step}")
        print()
        print("Best Practices:")
        for tip in detail["best_practices"]:
            print(f"  * {tip}")
        if detail["examples"]:
            print()
            print("Examples:")
            for ex in detail["examples"]:
                print(f"  # {ex['description']}")
                for line in ex["code"].split("\n"):
                    print(f"    {line}")
                print()
        if detail["related_topics"]:
            print(f"Related: {', '.join(detail['related_topics'])}")

    return 0


# =============================================================================
# Argument parser
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="coordination-cli",
        description="Multi-agent coordination CLI. Token-efficient alternative to MCP.",
    )
    parser.add_argument(
        "--json", action="store_true", help="JSON output (default: human-readable)",
    )
    subs = parser.add_subparsers(dest="command", help="Available command groups")

    # -- health --------------------------------------------------------------
    health_p = subs.add_parser("health", help="Check coordinator health and database connectivity")
    health_p.set_defaults(func=cmd_health)

    # -- help (progressive discovery) ----------------------------------------
    help_p = subs.add_parser("help", help="Show capabilities with progressive detail")
    help_p.add_argument("topic", nargs="?", default=None, help="Topic to get detailed help for")
    help_p.set_defaults(func=cmd_help)

    # -- feature -------------------------------------------------------------
    feat_p = subs.add_parser("feature", help="Feature registry operations")
    feat_subs = feat_p.add_subparsers(dest="subcommand")

    p = feat_subs.add_parser("register", help="Register a feature with resource claims")
    p.add_argument("--feature-id", required=True, help="Unique feature identifier")
    p.add_argument("--claims", nargs="*", default=[], help="Resource claim keys")
    p.add_argument("--title", help="Human-readable title")
    p.add_argument("--agent-id", help="Registering agent ID")
    p.add_argument("--branch-name", help="Git branch name")
    p.add_argument("--merge-priority", type=int, default=5, help="Merge priority (1=highest)")
    p.add_argument("--metadata", help="JSON metadata string")
    p.set_defaults(func=cmd_feature_register)

    p = feat_subs.add_parser("deregister", help="Deregister a feature (mark completed/cancelled)")
    p.add_argument("--feature-id", required=True)
    p.add_argument("--status", default="completed", choices=["completed", "cancelled"])
    p.set_defaults(func=cmd_feature_deregister)

    p = feat_subs.add_parser("show", help="Show details of a specific feature")
    p.add_argument("--feature-id", required=True)
    p.set_defaults(func=cmd_feature_show)

    p = feat_subs.add_parser("list", help="List all active features")
    p.set_defaults(func=cmd_feature_list)

    p = feat_subs.add_parser("conflicts", help="Analyze resource conflicts for a candidate feature")
    p.add_argument("--feature-id", required=True, help="Candidate feature ID")
    p.add_argument("--claims", nargs="+", required=True, help="Candidate resource claims")
    p.set_defaults(func=cmd_feature_conflicts)

    # -- merge-queue ---------------------------------------------------------
    mq_p = subs.add_parser("merge-queue", help="Merge queue operations")
    mq_subs = mq_p.add_subparsers(dest="subcommand")

    p = mq_subs.add_parser("enqueue", help="Add feature to merge queue")
    p.add_argument("--feature-id", required=True)
    p.add_argument("--pr-url", help="Pull request URL")
    p.set_defaults(func=cmd_mq_enqueue)

    p = mq_subs.add_parser("status", help="Show merge queue status")
    p.set_defaults(func=cmd_mq_status)

    p = mq_subs.add_parser("next", help="Show next feature ready to merge")
    p.set_defaults(func=cmd_mq_next)

    p = mq_subs.add_parser("check", help="Run pre-merge checks on a feature")
    p.add_argument("--feature-id", required=True)
    p.set_defaults(func=cmd_mq_check)

    p = mq_subs.add_parser("merged", help="Mark feature as merged")
    p.add_argument("--feature-id", required=True)
    p.set_defaults(func=cmd_mq_merged)

    p = mq_subs.add_parser("remove", help="Remove feature from merge queue without merging")
    p.add_argument("--feature-id", required=True)
    p.set_defaults(func=cmd_mq_remove)

    # -- lock ----------------------------------------------------------------
    lock_p = subs.add_parser("lock", help="File lock operations")
    lock_subs = lock_p.add_subparsers(dest="subcommand")

    p = lock_subs.add_parser("acquire", help="Acquire a file lock")
    p.add_argument("--file-path", required=True)
    p.add_argument("--agent-id", required=True)
    p.add_argument("--agent-type", default="cli")
    p.add_argument("--reason", help="Lock reason")
    p.add_argument("--ttl-minutes", type=int, default=120)
    p.set_defaults(func=cmd_lock_acquire)

    p = lock_subs.add_parser("release", help="Release a file lock")
    p.add_argument("--file-path", required=True)
    p.add_argument("--agent-id", required=True)
    p.set_defaults(func=cmd_lock_release)

    p = lock_subs.add_parser("status", help="Check active locks")
    p.add_argument("--file-paths", nargs="*", help="Specific files to check (all if omitted)")
    p.set_defaults(func=cmd_lock_status)

    # -- work ----------------------------------------------------------------
    work_p = subs.add_parser("work", help="Work queue operations")
    work_subs = work_p.add_subparsers(dest="subcommand")

    p = work_subs.add_parser("submit", help="Submit work to the queue")
    p.add_argument("--task-type", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--priority", type=int, default=5)
    p.add_argument("--input-data", help="JSON input data")
    p.set_defaults(func=cmd_work_submit)

    p = work_subs.add_parser("claim", help="Claim work from the queue")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--agent-type", default="cli")
    p.add_argument("--task-types", nargs="*")
    p.set_defaults(func=cmd_work_claim)

    p = work_subs.add_parser("complete", help="Complete a task")
    p.add_argument("--task-id", required=True)
    p.add_argument("--success", type=bool, default=True)
    p.add_argument("--result-data", help="JSON result data")
    p.add_argument("--error-message")
    p.set_defaults(func=cmd_work_complete)

    p = work_subs.add_parser("get", help="Get a specific task by ID")
    p.add_argument("--task-id", required=True)
    p.set_defaults(func=cmd_work_get)

    # -- handoff -------------------------------------------------------------
    handoff_p = subs.add_parser("handoff", help="Session handoff operations")
    handoff_subs = handoff_p.add_subparsers(dest="subcommand")

    p = handoff_subs.add_parser("write", help="Write a handoff document")
    p.add_argument("--summary", required=True)
    p.add_argument("--agent-id", required=True)
    p.add_argument("--session-id")
    p.set_defaults(func=cmd_handoff_write)

    p = handoff_subs.add_parser("read", help="Read handoff documents")
    p.add_argument("--agent-name")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_handoff_read)

    # -- memory --------------------------------------------------------------
    memory_p = subs.add_parser("memory", help="Episodic memory operations")
    memory_subs = memory_p.add_subparsers(dest="subcommand")

    p = memory_subs.add_parser("store", help="Store an episodic memory")
    p.add_argument("--event-type", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--tags", nargs="*")
    p.add_argument("--agent-id")
    p.set_defaults(func=cmd_memory_store)

    p = memory_subs.add_parser("query", help="Query memories")
    p.add_argument("--tags", nargs="*")
    p.add_argument("--event-type")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_memory_query)

    # -- guardrails ----------------------------------------------------------
    guard_p = subs.add_parser("guardrails", help="Guardrail operations")
    guard_subs = guard_p.add_subparsers(dest="subcommand")

    p = guard_subs.add_parser("check", help="Check operation for destructive patterns")
    p.add_argument("--operation-text", required=True)
    p.add_argument("--file-paths", nargs="*")
    p.set_defaults(func=cmd_guardrails_check)

    # -- audit ---------------------------------------------------------------
    audit_p = subs.add_parser("audit", help="Audit trail operations")
    audit_subs = audit_p.add_subparsers(dest="subcommand")

    p = audit_subs.add_parser("query", help="Query audit trail")
    p.add_argument("--agent-id")
    p.add_argument("--operation")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_audit_query)

    return parser


# =============================================================================
# Main
# =============================================================================


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if not hasattr(args, "func"):
        # Command group without subcommand
        parser.parse_args([args.command, "--help"])
        return 0

    try:
        result: int = args.func(args)
        return result
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
