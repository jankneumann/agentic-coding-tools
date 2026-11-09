"""Join capability-gap memory signals to the dispatch tier that ran them.

Design D4. Attribution precedence per entry: loop-state (nearest
``phase_history`` entry to the memory ``created_at``), then a coordinator
discovery session with the same ``agent_id`` whose heartbeat window contains
``created_at``, then ``unknown``. Entries are never dropped: ``unknown`` is a
row. Tier resolution goes through ``archetype_roster.resolve_tier_for_provider``
so it matches dispatch exactly.

Query and tag parsing reuse ``improve-harness/scripts/analyze_failures.py``
so the memory tag schema is stated once.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from audit_paths import ensure_sibling_paths, load_bridge
from audit_findings import Finding

ensure_sibling_paths()

from analyze_failures import (  # noqa: E402
    SEVERITY_WEIGHTS,
    _extract_all_tags,
    _extract_tag,
    build_memory_query,
    deduplicate_findings,
    normalize_memory_entries,
)
from archetype_roster import (  # noqa: E402
    load_archetypes_raw,
    model_aliases,
    phase_mapping,
    resolve_tier_for_provider,
)

AGENT_ID = "skill-audit"
CONCENTRATION_SHARE = 0.6
CONCENTRATION_SESSIONS = 3
KNOWN_SOURCES = ("self-reported", "coordinator-emitted", "session-log", "transcript-mined")
SEVERITIES = ("low", "medium", "high", "critical")
ATTRIBUTION_RANK = {"loop-state": 0, "discovery": 1, "unknown": 2}
_CHANGE_PATH_RE = re.compile(r"openspec/changes/(?:archive/\d{4}-\d{2}-\d{2}-)?([a-z0-9][a-z0-9-]*)")
_ARCHIVE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")


@dataclass
class EvidenceResult:
    status: str  # available | unavailable
    reason: str | None = None
    tier_rows: list[dict[str, Any]] = field(default_factory=list)
    multi_source_fraction: float | None = None
    total: int = 0
    multi_source_count: int = 0
    findings: list[Finding] = field(default_factory=list)

    def to_ledger(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status, "tier_rows": self.tier_rows}
        if self.reason:
            out["reason"] = self.reason
        if self.status == "available":
            out["multi_source_fraction"] = float(self.multi_source_fraction or 0.0)
        return out


# --- time helpers -------------------------------------------------------------


def parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# --- inputs ---------------------------------------------------------------------


def fetch_memory_entries(
    bridge: Any | None,
    *,
    window_days: int,
    limit: int = 500,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """``(entries, None)`` on success, ``(None, reason)`` when memory is unavailable."""
    if bridge is None:
        return None, "bridge_unavailable"
    query = build_memory_query(time_window_days=window_days, limit=limit)
    try:
        result = bridge.try_recall(agent_id=AGENT_ID, tags=query["tags"], limit=query["limit"])
    except Exception as exc:  # the bridge promises not to raise; be safe anyway
        return None, f"bridge_error: {type(exc).__name__}"
    if not isinstance(result, dict) or result.get("status") != "ok":
        reason = "coordinator_unreachable"
        if isinstance(result, dict):
            reason = str(result.get("reason") or result.get("error") or result.get("status") or reason)
        return None, reason
    payload = result.get("response")
    if payload is None:
        payload = result.get("data")
    if isinstance(payload, dict):
        rows = payload.get("memories")
        if rows is None:
            rows = payload.get("entries", [])
    else:
        rows = payload
    if not isinstance(rows, list):
        return None, "malformed_response"
    return [r for r in rows if isinstance(r, dict)], None


def fetch_discovery_sessions(bridge: Any | None) -> list[dict[str, Any]]:
    """``GET /discovery/agents`` through the bridge transport; ``[]`` on any failure."""
    if bridge is None:
        return []
    try:
        state = bridge.detect_coordination()
        if not state.get("COORDINATOR_AVAILABLE") or not state.get("http_url"):
            return []
        response = bridge._http_request(
            method="GET",
            path="/discovery/agents",
            payload=None,
            http_url=state["http_url"],
            api_key=bridge._resolve_api_key(None),
        )
        data = response.get("data") if response.get("status_code") == 200 else None
        agents = data.get("agents") if isinstance(data, dict) else None
        return [a for a in agents if isinstance(a, dict)] if isinstance(agents, list) else []
    except Exception:
        return []


def _change_id_from_dir(path: Path) -> str:
    name = path.parent.name
    m = _ARCHIVE_PREFIX_RE.match(name)
    return m.group(1) if m and path.parent.parent.name == "archive" else name


def load_loop_states(repo_root: Path | None) -> dict[str, dict[str, Any]]:
    """Every ``openspec/changes/**/loop-state.json``, archive included, keyed by change id."""
    out: dict[str, dict[str, Any]] = {}
    if repo_root is None:
        return out
    changes = Path(repo_root) / "openspec" / "changes"
    if not changes.is_dir():
        return out
    for path in sorted(changes.rglob("loop-state.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        change_id = str(data.get("change_id") or _change_id_from_dir(path))
        out.setdefault(change_id, data)
    return out


# --- entry normalisation ----------------------------------------------------------


def _extract_change_id(entry: dict[str, Any]) -> str | None:
    details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    direct = details.get("change_id")
    if isinstance(direct, str) and direct:
        return direct
    tagged = _extract_tag(entry.get("tags", []) or [], "change_id")
    if tagged:
        return tagged
    haystack = " ".join(
        [str(v) for v in details.values() if isinstance(v, str)] + [str(entry.get("summary") or "")]
    )
    m = _CHANGE_PATH_RE.search(haystack)
    return m.group(1) if m else None


def _flatten(entry: dict[str, Any]) -> dict[str, Any]:
    details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    flat = normalize_memory_entries([entry])[0]
    flat.update(
        {
            "id": entry.get("id"),
            "created_at": entry.get("created_at"),
            "agent_id": entry.get("agent_id") or details.get("agent_id"),
            "agent_type": entry.get("agent_type") or details.get("agent_type"),
            "change_id": _extract_change_id(entry),
        }
    )
    if flat.get("session_id") in (None, "unknown"):
        flat["session_id"] = details.get("session_id") or entry.get("session_id") or "unknown"
    return flat


def entries_for_skill(
    entries: list[dict[str, Any]],
    skill: str,
    *,
    window_days: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Flatten, filter to ``affected_skill:<skill>`` in the window, and deduplicate."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=window_days)
    kept: list[dict[str, Any]] = []
    for entry in entries:
        tags = entry.get("tags", []) or []
        if skill not in _extract_all_tags(tags, "affected_skill"):
            continue
        created = parse_ts(entry.get("created_at"))
        if created is not None and created < cutoff:
            continue
        flat = _flatten(entry)
        flat["affected_skill"] = skill
        kept.append(flat)
    return deduplicate_findings(kept)


# --- attribution --------------------------------------------------------------------


def _archetype_from_loop_state(state: dict[str, Any], created: datetime | None, mapping: dict[str, Any]) -> str | None:
    history = state.get("phase_history") if isinstance(state.get("phase_history"), list) else []
    best: dict[str, Any] | None = None
    if created is not None:
        best_delta: timedelta | None = None
        for item in history:
            if not isinstance(item, dict):
                continue
            at = parse_ts(item.get("at"))
            if at is None:
                continue
            delta = abs(at - created)
            if best_delta is None or delta < best_delta:
                best, best_delta = item, delta
    if best is not None:
        explicit = best.get("phase_archetype")
        if isinstance(explicit, str) and explicit:
            return explicit
        spec = mapping.get(str(best.get("phase")))
        if isinstance(spec, dict) and isinstance(spec.get("archetype"), str):
            return spec["archetype"]
    scalar = state.get("phase_archetype")
    return scalar if isinstance(scalar, str) and scalar else None


def _archetype_from_discovery(entry: dict[str, Any], sessions: list[dict[str, Any]], created: datetime | None) -> str | None:
    agent_id = entry.get("agent_id")
    if not agent_id or created is None:
        return None
    for session in sessions:
        if session.get("agent_id") != agent_id:
            continue
        archetype = session.get("phase_archetype")
        if not isinstance(archetype, str) or not archetype:
            continue
        started = parse_ts(session.get("started_at"))
        last = parse_ts(session.get("last_heartbeat"))
        if last is None:
            continue
        if (started is None or started <= created) and created <= last:
            return archetype
    return None


def attribute(
    entry: dict[str, Any],
    *,
    loop_states: dict[str, dict[str, Any]],
    sessions: list[dict[str, Any]],
    mapping: dict[str, Any],
) -> tuple[str, str]:
    """Return ``(archetype, attributed_by)``; ``("unknown", "unknown")`` when nothing matches."""
    created = parse_ts(entry.get("created_at"))
    change_id = entry.get("change_id")
    if change_id and change_id in loop_states:
        archetype = _archetype_from_loop_state(loop_states[change_id], created, mapping)
        if archetype:
            return archetype, "loop-state"
    archetype = _archetype_from_discovery(entry, sessions, created)
    if archetype:
        return archetype, "discovery"
    return "unknown", "unknown"


def _severity(value: Any) -> str:
    text = str(value or "low").lower()
    return text if text in SEVERITIES else "low"


# --- join ------------------------------------------------------------------------------


def join_evidence(
    skill: str,
    deduped: list[dict[str, Any]],
    *,
    loop_states: dict[str, dict[str, Any]],
    sessions: list[dict[str, Any]],
    roster_path: Path | None = None,
) -> EvidenceResult:
    mapping = phase_mapping(roster_path)
    archetypes = load_archetypes_raw(str(roster_path) if roster_path else None).get("archetypes") or {}
    aliases = model_aliases(roster_path)

    groups: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    for entry in deduped:
        archetype, attributed_by = attribute(entry, loop_states=loop_states, sessions=sessions, mapping=mapping)
        provider = entry.get("agent_type") if entry.get("agent_type") in aliases else "unknown"
        model: str | None = None
        thinking: str | None = None
        if archetype != "unknown" and provider != "unknown":
            tier = str((archetypes.get(archetype) or {}).get("model") or "standard")
            model, thinking = resolve_tier_for_provider(str(provider), tier, path=roster_path)
        key = (archetype, str(provider), model or "unknown", thinking)
        group = groups.setdefault(
            key,
            {
                "archetype": archetype,
                "provider": str(provider),
                "model": model or "unknown",
                "thinking": thinking,
                "count": 0,
                "_sessions": set(),
                "_severity": 0,
                "_sources": set(),
                "attributed_by": attributed_by,
            },
        )
        group["count"] += 1
        group["_sessions"].add(str(entry.get("session_id") or "unknown"))
        group["_severity"] = max(group["_severity"], SEVERITY_WEIGHTS.get(_severity(entry.get("severity")), 1))
        group["_sources"].update(s for s in entry.get("sources", []) if s in KNOWN_SOURCES)
        if ATTRIBUTION_RANK[attributed_by] < ATTRIBUTION_RANK[group["attributed_by"]]:
            group["attributed_by"] = attributed_by

    rows: list[dict[str, Any]] = []
    for group in groups.values():
        rows.append(
            {
                "archetype": group["archetype"],
                "provider": group["provider"],
                "model": group["model"],
                "thinking": group["thinking"],
                "count": group["count"],
                "sessions": max(1, len(group["_sessions"])),
                "max_severity": SEVERITIES[max(group["_severity"], 1) - 1],
                "sources": sorted(group["_sources"]),
                "attributed_by": group["attributed_by"],
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["archetype"], r["provider"], r["model"], r["thinking"] or ""))

    total = len(deduped)
    multi = sum(1 for e in deduped if len(e.get("sources", [])) >= 2)
    findings: list[Finding] = []
    for row in rows:
        if total and row["count"] / total >= CONCENTRATION_SHARE and row["sessions"] >= CONCENTRATION_SESSIONS:
            tier = f"({row['provider']}, {row['model']}, {row['thinking'] or 'null'})"
            findings.append(
                Finding(
                    kind="tier_concentrated_failure",
                    layer="procedure",
                    section_id="SKILL.md",
                    remediation="add_probe",
                    rationale=(
                        f"{row['count']} of {total} failures for {skill} across {row['sessions']} sessions "
                        f"ran at archetype {row['archetype']} on {tier}."
                    ),
                    evidence={"tier": tier, "count": f"{row['count']}/{total}"},
                )
            )
    return EvidenceResult(
        status="available",
        tier_rows=rows,
        multi_source_fraction=(multi / total) if total else 0.0,
        total=total,
        multi_source_count=multi,
        findings=findings,
    )


def collect_evidence(
    skill: str,
    *,
    window_days: int,
    bridge: Any | None = None,
    entries: list[dict[str, Any]] | None = None,
    sessions: list[dict[str, Any]] | None = None,
    loop_states: dict[str, dict[str, Any]] | None = None,
    repo_root: Path | None = None,
    roster_path: Path | None = None,
    now: datetime | None = None,
) -> EvidenceResult:
    """End-to-end join for one skill; never raises, degrades to ``unavailable``."""
    if bridge is None and entries is None:
        bridge = load_bridge()
    if entries is None:
        entries, reason = fetch_memory_entries(bridge, window_days=window_days)
        if entries is None:
            return EvidenceResult(status="unavailable", reason=reason or "coordinator_unreachable")
    if sessions is None:
        sessions = fetch_discovery_sessions(bridge)
    if loop_states is None:
        loop_states = load_loop_states(repo_root)
    try:
        deduped = entries_for_skill(entries, skill, window_days=window_days, now=now)
        return join_evidence(skill, deduped, loop_states=loop_states, sessions=sessions, roster_path=roster_path)
    except Exception as exc:
        return EvidenceResult(status="unavailable", reason=f"join_error: {type(exc).__name__}: {exc}")


__all__ = [
    "AGENT_ID",
    "EvidenceResult",
    "attribute",
    "collect_evidence",
    "entries_for_skill",
    "fetch_discovery_sessions",
    "fetch_memory_entries",
    "join_evidence",
    "load_loop_states",
    "parse_ts",
]
