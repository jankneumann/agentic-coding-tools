"""Synthesize the behavior handbook from deterministic seeds (design D2/D4).

Synthesis is an *event*, not part of every refresh: it may involve a
nondeterministic structuring backend, so its output is reviewed and committed
like source, while ``architecture-refresh`` only re-verifies the committed
result. That split preserves the pipeline's byte-identical-repeat-refresh
invariant.

The assembler is deliberately paranoid about the backend. Membership comes from
:mod:`behavior_seeder` alone; any node the backend invents is dropped, and any
narrative that cannot be grounded in at least one resolvable locator is
discarded rather than published. A handbook that says something it cannot prove
is worse than one that says less.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Protocol

from arch_utils.determinism import generated_at_iso
from arch_utils.graph_io import load_graph, save_json
from arch_utils.provenance import analyzed_revision, deterministic_epoch
from behavior_seeder import seed_behaviors
from handbook_schema import compute_budget_estimate, validate_handbook
from source_roots import parse_source_roots, resolve_node_path
from verify_locators import normalized_span_digest

logger = logging.getLogger(__name__)

HANDBOOK_VERSION = "1.0.0"


class StructuringError(RuntimeError):
    """Raised when the structuring backend fails to produce usable output."""


class StructuringBackend(Protocol):
    """Names, groups, and narrates seed clusters. Must not widen membership.

    A backend may return either shape (:func:`_normalize_structuring` accepts
    both): the legacy 1:1 ``{cluster_id: {title, ...}}`` (what
    :class:`OfflineBackend` emits), or a grouping
    ``{"units": [{"seed_ids": [...], title, ...}]}`` that merges/splits clusters.
    Members always come from the referenced seeds; invented ids are dropped.
    """

    name: str
    model_id: str
    prompt_hash: str

    def structure(self, seeds: dict[str, Any]) -> dict[str, Any]:
        """Return a legacy 1:1 dict or a ``{"units": [...]}`` grouping."""


#: Level 1 is a *system* overview, not an index of every entrypoint. Flows are
#: grouped by the module a request enters through, and only the largest groups
#: are named individually — the rest are counted. Without this, a repo with 96
#: entrypoints produces a 4000-token "overview" that no one can read and no
#: agent should pay for.
L1_MAX_FLOWS = 12
L1_MAX_STAGES = 6


def _titleize(slug: str) -> str:
    return slug.replace("-", " ").strip().capitalize() or "Unnamed behavior"


def _module_of(node_id: str) -> str:
    """Return the module segment of a canonical node id.

    ``py:coordination_api.create_coordination_api.acquire_lock`` -> ``coordination_api``
    """
    tail = str(node_id).split(":", 1)[-1]
    return tail.split(".", 1)[0] or tail


def _build_system_flows(
    clusters: list[dict[str, Any]], titles: dict[str, str]
) -> tuple[list[dict[str, Any]], int]:
    """Group clusters into per-entry-module flows for Level 1.

    Returns ``(flows, omitted_count)``.
    """
    groups: dict[str, dict[str, Any]] = {}
    for cluster in clusters:
        module = _module_of(cluster["root"])
        group = groups.setdefault(
            module,
            {"module": module, "behaviors": [], "stages": set(), "entries": []},
        )
        group["behaviors"].append(titles.get(cluster["id"], cluster["id"]))
        group["entries"].append(cluster["root"])
        for node in cluster["member_nodes"]:
            group["stages"].add(_module_of(node))

    ordered = sorted(
        groups.values(), key=lambda g: (-len(g["behaviors"]), str(g["module"]))
    )
    kept, omitted = ordered[:L1_MAX_FLOWS], ordered[L1_MAX_FLOWS:]

    flows = [
        {
            "id": f"fl:{g['module'].replace('_', '-')}",
            "title": _titleize(g["module"].replace("_", "-")),
            "entry": sorted(g["entries"])[0],
            "stages": sorted(g["stages"])[:L1_MAX_STAGES],
            "state_handoffs": [],
            "terminal_actions": [],
            "behavior_count": len(g["behaviors"]),
        }
        for g in kept
    ]
    return flows, sum(len(g["behaviors"]) for g in omitted)


class OfflineBackend:
    """Deterministic, LLM-free structuring used in tests and CI.

    Produces serviceable-but-plain naming derived from the seed skeleton. It
    exists so the whole pipeline — synthesis included — can run without network
    or API credentials, and so determinism tests have a stable path to assert on.
    """

    name = "offline"
    model_id = "none"
    prompt_hash = "sha256:offline"

    def structure(self, seeds: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for cluster in seeds.get("clusters") or []:
            slug = cluster["id"].split(":", 1)[-1]
            exec_paths = [
                {
                    "summary": f"Primary flow from {cluster['root']}",
                    "evidence_nodes": cluster["member_nodes"][:3],
                }
            ]
            exc_paths = [
                {
                    "summary": f"{p.get('exception_type', 'Exception')} handled in "
                               f"{p.get('file')}",
                    "evidence_nodes": [p["node_id"]] if p.get("node_id") else [],
                }
                for p in cluster.get("exception_patterns") or []
            ]
            out[cluster["id"]] = {
                "title": _titleize(slug),
                "responsibility": f"Behavior rooted at {cluster['root']}.",
                "inputs": [],
                "outputs": [],
                "triggers": [cluster["root"]],
                "state_changes": [],
                "execution_paths": exec_paths,
                "exception_paths": exc_paths,
            }
        return out


# --------------------------------------------------------------------------- #
# LLM structuring backend
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object out of a model response.

    Tolerates the common wrappers a chat model adds — code fences and
    surrounding prose — by slicing from the first ``{`` to the last ``}``.
    Raises ``ValueError`` if no JSON object is present (e.g. a refusal),
    which :func:`synthesize` turns into a :class:`StructuringError`.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in structuring response")
    return json.loads(text[start : end + 1])


#: The structuring instruction. Its hash is recorded in the handbook snapshot so
#: a change in prompting is visible in provenance and diffs.
_CLAUDE_SYSTEM_PROMPT = (
    "You are a software-architecture analyst. You are given deterministic "
    "clusters of code, each rooted at an entrypoint. Group them into a small "
    "number of coherent, human-meaningful behavior units and describe each.\n"
    "Rules:\n"
    "- Reference clusters only by the seed_ids provided; never invent one.\n"
    "- A cluster belongs to at most one unit.\n"
    "- evidence_nodes must be node ids drawn only from the provided member "
    "nodes; never invent a node id.\n"
    "- Merge trivial clusters into a larger behavior; split a sprawling "
    "cluster only if it clearly serves two behaviors.\n"
    'Return only JSON: {"units": [{"seed_ids": [...], "title": "...", '
    '"responsibility": "...", "inputs": [...], "outputs": [...], '
    '"triggers": [...], "state_changes": [...], '
    '"execution_paths": [{"summary": "...", "evidence_nodes": [...]}], '
    '"exception_paths": [{"summary": "...", "evidence_nodes": [...]}]}]}'
)

_CLAUDE_PROMPT_VERSION = "1"


class ClaudeStructuringBackend:
    """LLM structuring backend (deferred #1) — merges/splits seed clusters.

    Unlike :class:`OfflineBackend`, this can regroup clusters into
    human-meaningful behavior units, which is what the localization benchmark
    needs (the offline path's 1:1 renaming leaves granularity unchanged).

    The API call is injectable via ``complete`` so the whole pipeline is
    testable without network or credentials. The default completion function
    uses the Anthropic SDK and Claude Opus 5; it has NOT been exercised against
    a live model in the build sandbox (egress is restricted), so treat it as
    best-effort until run in an environment with API access.
    """

    name = "claude"

    def __init__(
        self,
        *,
        model: str = "claude-opus-5",
        complete: Callable[[str], str] | None = None,
        chunk_size: int = 20,
        effort: str = "high",
    ) -> None:
        self.model_id = model
        self.effort = effort
        self.chunk_size = max(1, chunk_size)
        self._complete = complete or self._default_complete
        self.prompt_hash = _prompt_hash(
            f"{_CLAUDE_PROMPT_VERSION}\n{_CLAUDE_SYSTEM_PROMPT}"
        )

    def _cluster_view(self, cluster: dict[str, Any]) -> dict[str, Any]:
        """The projection of a cluster the model is allowed to reason over."""
        return {
            "seed_id": cluster["id"],
            "root": cluster["root"],
            "member_nodes": cluster.get("member_nodes") or [],
            "files": cluster.get("member_files") or [],
            "hubs": cluster.get("hubs") or [],
            "exception_patterns": [
                {"node_id": p.get("node_id"), "file": p.get("file"),
                 "type": p.get("exception_type")}
                for p in cluster.get("exception_patterns") or []
            ],
        }

    def _user_prompt(self, clusters: list[dict[str, Any]]) -> str:
        views = [self._cluster_view(c) for c in clusters]
        return "Clusters:\n" + json.dumps(views, indent=2, sort_keys=True)

    def structure(self, seeds: dict[str, Any]) -> dict[str, Any]:
        clusters = sorted(
            seeds.get("clusters") or [], key=lambda c: str(c.get("id"))
        )
        units: list[dict[str, Any]] = []
        for i in range(0, len(clusters), self.chunk_size):
            chunk = clusters[i : i + self.chunk_size]
            parsed = _extract_json(self._complete(self._user_prompt(chunk)))
            chunk_units = parsed.get("units")
            if not isinstance(chunk_units, list):
                raise ValueError("structuring response has no 'units' list")
            units.extend(u for u in chunk_units if isinstance(u, dict))
        return {"units": units}

    def _default_complete(self, prompt: str) -> str:  # pragma: no cover - needs network
        """Call Claude via the Anthropic SDK. Unverified in the build sandbox."""
        import anthropic  # lazy: only needed when actually synthesizing

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model_id,
            max_tokens=16000,
            system=_CLAUDE_SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": prompt}],
        )
        if getattr(response, "stop_reason", None) == "refusal":
            raise ValueError("structuring request was refused by the model")
        return "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        )


def _normalize_structuring(
    structured: Any, seeds: dict[str, Any]
) -> list[dict[str, Any]]:
    """Turn either backend shape into an ordered list of unit specs.

    A *spec* is a grouping of one or more seed clusters into a single behavior
    unit: ``{unit_id, cluster_ids, member_nodes, hubs, root, content}``. The
    legacy 1:1 dict shape yields one spec per cluster (preserving byte-identical
    offline output); the grouping shape merges clusters, drops invented
    ``seed_ids``, assigns each cluster to at most one unit (first-wins), and
    gives any unclaimed cluster its own unit so no entrypoint coverage is lost.
    """
    clusters = seeds.get("clusters") or []
    by_id = {c["id"]: c for c in clusters}

    def make_spec(cluster_ids: list[str], content: Any) -> dict[str, Any]:
        cluster_ids = sorted(cid for cid in cluster_ids if cid in by_id)
        members: set[str] = set()
        hubs: set[str] = set()
        roots: list[str] = []
        for cid in cluster_ids:
            cluster = by_id[cid]
            members.update(cluster.get("member_nodes") or [])
            hubs.update(cluster.get("hubs") or [])
            roots.append(cluster["root"])
        slug = cluster_ids[0].split(":", 1)[-1]
        return {
            "unit_id": f"bh:{slug}",
            "cluster_ids": cluster_ids,
            "member_nodes": sorted(members),
            "hubs": sorted(hubs),
            "root": sorted(roots)[0] if roots else None,
            "content": content if isinstance(content, dict) else {},
        }

    specs: list[dict[str, Any]] = []

    if isinstance(structured, dict) and isinstance(structured.get("units"), list):
        claimed: set[str] = set()
        for unit in structured["units"]:
            if not isinstance(unit, dict):
                continue
            seed_ids = [
                s for s in (unit.get("seed_ids") or [])
                if s in by_id and s not in claimed
            ]
            if not seed_ids:
                continue
            claimed.update(seed_ids)
            specs.append(make_spec(seed_ids, unit))
        for cluster in clusters:
            if cluster["id"] not in claimed:
                specs.append(make_spec([cluster["id"]], {}))
    else:
        for cluster in clusters:
            content = structured.get(cluster["id"]) if isinstance(structured, dict) else None
            specs.append(make_spec([cluster["id"]], content))

    specs.sort(key=lambda s: s["unit_id"])
    return specs


def _stamp_locator(
    node_id: str,
    nodes: dict[str, dict[str, Any]],
    repo_root: Path,
    role: str,
    source_roots: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Build a verified locator for *node_id*, or ``None`` if not groundable.

    The stamped ``file`` is repo-relative so a reviewer can open it and
    ``verify_locators`` can re-read it from the repository root.
    """
    node = nodes.get(node_id)
    if node is None:
        return None
    rel = resolve_node_path(node, source_roots)
    span = node.get("span") or {}
    start, end = span.get("start"), span.get("end")
    if not rel or start is None or end is None:
        return None
    try:
        digest = normalized_span_digest(repo_root / rel, int(start), int(end))
    except (OSError, ValueError, TypeError):
        return None
    return {
        "node_id": node_id,
        "file": rel,
        "span": {"start": int(start), "end": int(end)},
        "content_digest": digest,
        "role": role,
    }


def _ground_paths(
    raw_paths: Any,
    member_nodes: set[str],
    nodes: dict[str, dict[str, Any]],
    repo_root: Path,
    role: str,
    source_roots: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Keep only narrative paths grounded in at least one resolvable locator."""
    grounded: list[dict[str, Any]] = []
    for path in raw_paths or []:
        if not isinstance(path, dict):
            continue
        evidence: list[dict[str, Any]] = []
        for node_id in path.get("evidence_nodes") or []:
            if node_id not in member_nodes:
                continue  # the backend may not reach outside the skeleton
            locator = _stamp_locator(node_id, nodes, repo_root, role, source_roots)
            if locator is not None:
                evidence.append(locator)
        if not evidence:
            continue  # ungrounded narrative is dropped, never published
        grounded.append({"summary": str(path.get("summary", "")), "evidence": evidence})
    return grounded


def synthesize(
    graph: dict[str, Any],
    repo_root: Path | str,
    *,
    backend: StructuringBackend | None = None,
    high_impact: dict[str, Any] | None = None,
    enrichment: dict[str, Any] | None = None,
    scope: list[str] | None = None,
    git_sha: str | None = None,
    source_roots: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a complete handbook document for *graph*."""
    repo_root = Path(repo_root)
    backend = backend or OfflineBackend()

    seeds = seed_behaviors(
        graph,
        high_impact=high_impact,
        enrichment=enrichment,
        scope=scope,
        source_roots=source_roots,
    )
    nodes = {
        n["id"]: n for n in graph.get("nodes") or [] if isinstance(n, dict) and "id" in n
    }

    try:
        structured = backend.structure(seeds) or {}
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed error
        raise StructuringError(f"structuring backend {backend.name!r} failed: {exc}") from exc
    if not isinstance(structured, dict):
        raise StructuringError("structuring backend returned a non-object payload")

    behavior_units: list[dict[str, Any]] = []
    unit_details: dict[str, Any] = {}
    cluster_title: dict[str, str] = {}

    # Membership comes from the seed skeleton, never the backend: each spec is a
    # grouping of one or more clusters, and its member nodes are their union.
    for spec in _normalize_structuring(structured, seeds):
        content = spec["content"]
        unit_id = spec["unit_id"]
        slug = unit_id.split(":", 1)[-1]
        member_nodes = set(spec["member_nodes"])
        title = str(content.get("title") or _titleize(slug))

        behavior_units.append(
            {
                "id": unit_id,
                "title": title,
                "responsibility": str(
                    content.get("responsibility") or f"Behavior rooted at {spec['root']}."
                ),
                "inputs": [str(x) for x in content.get("inputs") or []],
                "outputs": [str(x) for x in content.get("outputs") or []],
                "depends_on": [],
                "member_nodes": spec["member_nodes"],  # skeleton is authoritative
            }
        )

        evidence = [
            loc
            for loc in (
                _stamp_locator(n, nodes, repo_root, "member", source_roots)
                for n in spec["hubs"]
            )
            if loc is not None
        ]
        if not evidence:
            # Fall back to the unit's own entrypoint, then to any groundable
            # member, so every unit carries at least one verifiable locator.
            for candidate in [spec["root"], *spec["member_nodes"]]:
                root_locator = _stamp_locator(
                    candidate, nodes, repo_root, "member", source_roots
                )
                if root_locator is not None:
                    evidence = [root_locator]
                    break

        unit_details[unit_id] = {
            "triggers": [str(x) for x in content.get("triggers") or []],
            "state_changes": [str(x) for x in content.get("state_changes") or []],
            "execution_paths": _ground_paths(
                content.get("execution_paths"), member_nodes, nodes, repo_root,
                "execution_path", source_roots,
            ),
            "exception_paths": _ground_paths(
                content.get("exception_paths"), member_nodes, nodes, repo_root,
                "exception_path", source_roots,
            ),
            "evidence": evidence,
        }

        for cluster_id in spec["cluster_ids"]:
            cluster_title[cluster_id] = title

    system_flows, omitted_flows = _build_system_flows(
        seeds["clusters"], cluster_title
    )

    handbook: dict[str, Any] = {
        "snapshot": {
            "generated_at": generated_at_iso(),
            "git_sha": git_sha or os.environ.get("ARCH_GIT_SHA", "unknown"),
            "handbook_version": HANDBOOK_VERSION,
            "backend": backend.name,
            "model_id": backend.model_id,
            "prompt_hash": backend.prompt_hash,
            "scope": scope or [],
        },
        "system_flows": system_flows,
        "behavior_units": behavior_units,
        "unit_details": unit_details,
        "uncovered": seeds["uncovered"],
        "seed_summary": {**seeds["summary"], "flows_omitted_from_l1": omitted_flows},
    }
    handbook["budget_estimate"] = compute_budget_estimate(handbook)
    return handbook


def write_handbook(
    handbook: dict[str, Any], graph: dict[str, Any], output_path: Path | str
) -> int:
    """Validate then atomically publish *handbook*; preserve prior on failure.

    A synthesis that produces an invalid document must never clobber the
    last known-good committed artifact (R3).
    """
    output_path = Path(output_path)
    dc = validate_handbook(handbook, graph)
    if dc.exit_code != 0:
        for item in dc.errors:
            logger.error("[%s] %s", item.code, item.message)
        logger.error("handbook failed validation — existing artifact left untouched")
        return 1

    staged = output_path.with_suffix(output_path.suffix + ".staged")
    save_json(staged, handbook)
    staged.replace(output_path)
    return 0


def _prompt_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthesize architecture.behaviors.json")
    parser.add_argument("--graph", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--high-impact")
    parser.add_argument("--enrichment")
    parser.add_argument("--scope", action="append", default=None)
    parser.add_argument(
        "--source-root",
        action="append",
        default=None,
        metavar="LANG=PATH",
        help="Override an analyzer source root (repeatable), e.g. python=src",
    )
    parser.add_argument("--git-sha")
    parser.add_argument(
        "--backend",
        default="offline",
        choices=["offline", "claude"],
        help="Structuring backend: 'offline' is deterministic and credential-free "
        "(the default and CI path); 'claude' calls the Anthropic API to merge and "
        "narrate clusters (requires ANTHROPIC_API_KEY; output is committed and "
        "reviewed like source).",
    )
    parser.add_argument(
        "--model",
        default="claude-opus-5",
        help="Model id for --backend claude (default: claude-opus-5)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    graph = load_graph(Path(args.graph))
    if not graph:
        logger.error("graph not found or empty: %s", args.graph)
        return 1

    # Two syntheses of one revision must be byte-identical. The staged refresh
    # runner exports SOURCE_DATE_EPOCH; when this target is invoked directly we
    # derive the same value from the analyzed commit rather than the wall clock.
    if not os.environ.get("SOURCE_DATE_EPOCH"):
        revision = args.git_sha or analyzed_revision(args.repo_root)
        os.environ["SOURCE_DATE_EPOCH"] = str(
            deterministic_epoch(args.repo_root, revision)
        )

    backend: StructuringBackend = (
        ClaudeStructuringBackend(model=args.model)
        if args.backend == "claude"
        else OfflineBackend()
    )

    try:
        handbook = synthesize(
            graph,
            args.repo_root,
            backend=backend,
            high_impact=load_graph(Path(args.high_impact), quiet=True) if args.high_impact else None,
            enrichment=load_graph(Path(args.enrichment), quiet=True) if args.enrichment else None,
            scope=args.scope,
            git_sha=args.git_sha,
            source_roots=parse_source_roots(args.source_root),
        )
    except StructuringError as exc:
        logger.error("%s", exc)
        return 1

    rc = write_handbook(handbook, graph, Path(args.output))
    if rc == 0:
        logger.info(
            "Handbook written: %d unit(s), %d uncovered entrypoint(s) -> %s",
            len(handbook["behavior_units"]),
            len(handbook["uncovered"]),
            args.output,
        )
    return rc


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
