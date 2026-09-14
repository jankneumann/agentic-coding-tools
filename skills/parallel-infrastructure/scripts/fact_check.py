"""Diff-grounded fact-check pass for review findings.

Ported from alibaba/open-code-review's REVIEW_FILTER_TASK
(internal/config/template/prompts/review_filter_task_*.md and
internal/agent/agent.go executeGroupReviewFilter, Apache-2.0 License,
https://github.com/alibaba/open-code-review, read 2026-09-14).

Removes only findings a diff *proves* wrong, on two grounds:

- Ground A: the finding's subject file's diff contains no such code.
- Ground B: one diff line literally contradicts the finding's central claim.

Findings on a protected subject (memory safety, concurrency, declaration
consistency, behavioral/compatibility change, an unused parameter) are never
removed, regardless of the model's verdict. Any failure to call the model,
parse its response, or match a finding id removes nothing — see :func:`run`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "fact_check_system.md").read_text(encoding="utf-8")
USER_PROMPT_TEMPLATE = (PROMPTS_DIR / "fact_check_user.md").read_text(encoding="utf-8")

SCHEMA_VERSION = 1
GROUND_A = "A_absent_from_subject_diff"
GROUND_B = "B_contradicted_by_diff_line"
_GROUNDS = {GROUND_A, GROUND_B}

# Caller signature: (system_prompt, user_prompt) -> raw response text.
# May raise on any failure (timeout, network, subprocess error) — run()
# treats every exception as "skip this vendor's pass", never as fatal.
Caller = Callable[[str, str], str]


_PROTECTED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "memory_safety": (
        "buffer overflow", "use-after-free", "use after free",
        "null dereference", "null pointer", "out-of-bounds", "out of bounds",
        "off-by-one", "off by one", "index bound", "allocation size",
        "buffer length", "memory leak", "double free",
    ),
    "concurrency": (
        "race condition", "data race", "deadlock", "mutex", "lock mode",
        "atomic", "thread-safe", "thread safe", "concurrent access",
        "synchroniz",
    ),
    "declaration_consistency": (
        "declaration disagrees", "declaration does not match",
        "linkage", "static keyword", "extern declaration",
        "signature mismatch", "definition disagrees",
    ),
    "behavioral_compatibility": (
        "backward compat", "backwards compat", "breaking change",
        "behavior change", "behavioral change", "no longer produces",
        "no longer returns", "no longer sets", "default changed",
        "status code changed", "error path changed",
    ),
    "unused_parameter": (
        "unused parameter", "parameter is never used",
        "parameter is unused", "never uses the parameter",
        "parameter that is never used",
    ),
}


def protected_subject(finding: dict[str, Any]) -> str | None:
    """Return the protected-subject category *finding* matches, or None.

    A keyword heuristic over description/axis/type — deliberately not a
    model judgment, so the veto in :func:`run` never depends on a call that
    might fail or be wrong.
    """
    haystack = " ".join(
        str(finding.get(key, "") or "") for key in ("description", "axis", "type")
    ).lower()
    for category, keywords in _PROTECTED_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return category
    return None


@dataclass
class Decision:
    finding_id: str
    verdict: str  # "kept" | "removed" | "vetoed"
    ground: str | None = None
    evidence_line: str | None = None
    vetoed: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"finding_id": self.finding_id, "verdict": self.verdict}
        if self.ground:
            out["ground"] = self.ground
        if self.evidence_line:
            out["evidence_line"] = self.evidence_line
        if self.vetoed:
            out["vetoed"] = self.vetoed
        return out


@dataclass
class FactCheckOutcome:
    vendor: str
    round_num: int
    status: str  # "ran" | "skipped" | "disabled"
    kept_findings: list[dict[str, Any]]
    decisions: list[Decision] = field(default_factory=list)
    model: str | None = None
    tokens: int = 0
    skip_reason: str | None = None

    @property
    def removed_count(self) -> int:
        return sum(1 for d in self.decisions if d.verdict == "removed")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "vendor": self.vendor,
            "round": self.round_num,
            "status": self.status,
            "skip_reason": self.skip_reason,
            "model": self.model,
            "tokens": self.tokens,
            "decisions": [d.to_dict() for d in self.decisions],
        }


def render_prompts(findings: list[dict[str, Any]], packet_diff: str) -> tuple[str, str]:
    """Render the fact-check system/user prompts for one vendor's findings."""
    items = [
        {
            "finding_id": f.get("id"),
            "file_path": f.get("file_path"),
            "description": f.get("description"),
            "axis": f.get("axis"),
            "type": f.get("type"),
        }
        for f in findings
    ]
    user = USER_PROMPT_TEMPLATE.replace("{{diff}}", packet_diff or "(empty diff)")
    user = user.replace("{{findings}}", json.dumps(items, indent=2))
    return SYSTEM_PROMPT, user


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) >= 2:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def parse_verdict(raw_text: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse the model's JSON verdict into ``(tool, items)``.

    Raises ``ValueError``/``json.JSONDecodeError`` on anything that is not
    one of the two documented shapes — :func:`run` treats that as "skip",
    never as an implicit approve-all.
    """
    text = _strip_fence(raw_text)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found in fact-check response")
    # raw_decode parses exactly the first complete JSON object starting at
    # `start` and ignores anything after it — handles both leading prose
    # ("Here is my answer: {...}") and nested braces inside the object
    # itself, which a naive rfind("{") slice would mis-split.
    obj, _end = json.JSONDecoder().raw_decode(text, start)
    tool = obj.get("tool")
    if tool == "approve_all_comments":
        return tool, []
    if tool == "report_incorrect_comments":
        items = obj.get("items")
        if not isinstance(items, list):
            raise ValueError("report_incorrect_comments missing 'items' array")
        return tool, items
    raise ValueError(f"unrecognized fact-check tool {tool!r}")


def run(
    *,
    vendor: str,
    round_num: int,
    findings: list[dict[str, Any]],
    packet_diff: str,
    caller: Caller | None,
    model: str | None = None,
    enabled: bool = True,
) -> FactCheckOutcome:
    """Run the fact-check pass for one vendor's already-validated findings.

    Never raises: a disabled pass, no findings, no caller, a caller failure,
    or an unparsable response all result in ``status`` naming why and every
    finding kept. The protected-subject veto runs regardless of the verdict.
    """
    if not enabled:
        return FactCheckOutcome(
            vendor=vendor, round_num=round_num, status="disabled",
            kept_findings=list(findings),
        )
    if not findings:
        return FactCheckOutcome(
            vendor=vendor, round_num=round_num, status="skipped",
            kept_findings=[], skip_reason="no_findings",
        )
    if caller is None:
        return FactCheckOutcome(
            vendor=vendor, round_num=round_num, status="skipped",
            kept_findings=list(findings), skip_reason="no_caller_available",
        )

    system_prompt, user_prompt = render_prompts(findings, packet_diff)
    try:
        raw = caller(system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001 — any caller failure skips, never blocks
        return FactCheckOutcome(
            vendor=vendor, round_num=round_num, status="skipped",
            kept_findings=list(findings),
            skip_reason=f"{type(exc).__name__}: {exc}",
        )

    try:
        tool, items = parse_verdict(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        return FactCheckOutcome(
            vendor=vendor, round_num=round_num, status="skipped",
            kept_findings=list(findings),
            skip_reason=f"unparsable_response: {exc}",
            model=model,
        )

    by_id = {str(f.get("id")): f for f in findings}
    to_remove: dict[str, dict[str, Any]] = {}
    if tool == "report_incorrect_comments":
        for item in items:
            fid = str(item.get("finding_id", ""))
            ground = item.get("ground")
            if fid in by_id and ground in _GROUNDS:
                to_remove[fid] = item

    decisions: list[Decision] = []
    kept: list[dict[str, Any]] = []
    for f in findings:
        fid = str(f.get("id"))
        removal = to_remove.get(fid)
        if removal is None:
            decisions.append(Decision(finding_id=fid, verdict="kept"))
            kept.append(f)
            continue
        category = protected_subject(f)
        if category is not None:
            decisions.append(
                Decision(finding_id=fid, verdict="vetoed", vetoed="protected_subject")
            )
            kept.append(f)
            continue
        decisions.append(
            Decision(
                finding_id=fid,
                verdict="removed",
                ground=removal.get("ground"),
                evidence_line=removal.get("evidence_line"),
            )
        )

    return FactCheckOutcome(
        vendor=vendor, round_num=round_num, status="ran",
        kept_findings=kept, decisions=decisions, model=model,
    )


def write_decision_file(out_dir: Path, outcome: FactCheckOutcome) -> Path:
    """Write ``fact-check-<vendor>.json`` under *out_dir*, return its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"fact-check-{outcome.vendor}.json"
    path.write_text(json.dumps(outcome.to_document(), indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Default (live) caller — optional, degrades to None when unavailable.
# ---------------------------------------------------------------------------

def resolve_economy_model(vendor: str) -> str | None:
    """Resolve the economy-tier model for *vendor* from archetypes.yaml."""
    try:
        from skills.shared import archetype_roster  # type: ignore[import-untyped]
    except ImportError:
        import sys

        shared = Path(__file__).resolve().parents[2] / "shared"
        if str(shared.parent) not in sys.path:
            sys.path.insert(0, str(shared.parent))
        try:
            from skills.shared import archetype_roster  # type: ignore[import-untyped]
        except ImportError:
            return None
    try:
        model, _thinking = archetype_roster.resolve_tier_for_provider(vendor, "economy")
        return model
    except Exception:  # noqa: BLE001 — resolution failure means "no default caller"
        return None


def build_default_caller(
    cli_config: Any,
    vendor: str,
    *,
    cwd: Path,
    timeout_seconds: int = 120,
) -> Caller | None:
    """Build a subprocess-based caller from a vendor's CLI config, or None.

    Deliberately does not reuse ``CliVendorAdapter.dispatch``/``review``
    mode: that mode hard-codes findings-schema output (e.g. grok's
    ``--json-schema``), the wrong shape for a fact-check verdict. This issues
    a minimal, read-only, non-schema-constrained call at the resolved
    economy tier instead. Returns ``None`` (never raises) when the binary is
    not on PATH — callers pass that straight to :func:`run` as
    ``caller=None``, which skips gracefully.
    """
    import shutil
    import subprocess

    command = getattr(cli_config, "command", None)
    if not command or shutil.which(command) is None:
        return None
    model = resolve_economy_model(vendor)
    model_flag = getattr(cli_config, "model_flag", None)
    prompt_via_stdin = getattr(cli_config, "prompt_via_stdin", True)

    def _caller(system_prompt: str, user_prompt: str) -> str:
        full_prompt = system_prompt + "\n\n" + user_prompt
        cmd = [command, "--print", "--allowedTools", "Read,Grep,Glob"]
        if model and model_flag:
            cmd.extend([model_flag, model])
        stdin_text = full_prompt if prompt_via_stdin else None
        if not prompt_via_stdin:
            cmd.append(full_prompt)
        result = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(cwd),
        )
        if result.returncode != 0 and not result.stdout.strip():
            raise RuntimeError(
                f"fact-check caller exited {result.returncode}: {result.stderr[:300]}"
            )
        return result.stdout

    return _caller
