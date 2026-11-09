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
from types import ModuleType
from typing import Any, Callable

import file_selection

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name, so a monkeypatched `decide` attribute is
# what this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "fact_check_system.md").read_text(encoding="utf-8")
USER_PROMPT_TEMPLATE = (PROMPTS_DIR / "fact_check_user.md").read_text(encoding="utf-8")

SCHEMA_VERSION = 1
GROUND_A = "A_absent_from_subject_diff"
GROUND_B = "B_contradicted_by_diff_line"
_GROUNDS = {GROUND_A, GROUND_B}

DEFAULT_GROUND_SCREEN_CONFIDENCE_FLOOR = 0.5
_FACT_CHECK_JUDGMENT_CONFIG_PATH = Path(__file__).parent / "fact-check-judgment.json"

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


def _evidence_line_in_subject_diff(
    evidence_line: str, file_path: str | None, packet_diff: str,
) -> bool:
    """Whether *evidence_line* literally appears in *file_path*'s diff hunk.

    Ground B's whole premise is a diff line that contradicts the finding —
    a fabricated or misquoted line proves nothing, so the line is checked
    against the actual diff before it can justify a removal. Scoped to the
    finding's own subject file when that file's diff can be located; falls
    back to the full packet diff when it cannot (a missing/renamed
    file_path should not make an otherwise-real citation unverifiable).
    """
    line = evidence_line.strip()
    if not line:
        return False
    if file_path:
        for file_diff in file_selection.parse_diff_files(packet_diff):
            if file_diff.path == file_path or file_diff.old_path == file_path:
                return line in file_diff.body
    return line in packet_diff


def load_ground_screen_confidence_floor(config_path: Path | None = None) -> float:
    """Read the optional sidecar JSON, falling back to the module default.

    Mirrors gatekeeper_shadow/triage/implementation_strategy_selector/
    vendor_review's threshold-loading precedent: a malformed or missing
    sidecar degrades to the default rather than raising.
    """
    path = config_path or _FACT_CHECK_JUDGMENT_CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_GROUND_SCREEN_CONFIDENCE_FLOOR
    if not isinstance(raw, dict):
        return DEFAULT_GROUND_SCREEN_CONFIDENCE_FLOOR
    try:
        return float(raw.get("confidence_floor", DEFAULT_GROUND_SCREEN_CONFIDENCE_FLOOR))
    except (TypeError, ValueError):
        return DEFAULT_GROUND_SCREEN_CONFIDENCE_FLOOR


def _answer_field(answer: Any, name: str, default: Any = None) -> Any:
    """Read a field off a real SDK answer object or a plain dict/mapping."""
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def _screen_findings(
    findings: list[dict[str, Any]],
    packet_diff: str,
    dry_run: bool = False,
) -> dict[str, dict[str, float]] | None:
    """Ask one batched judgment screening every *finding* on both grounds.

    One `decide()` call for the whole batch (docs/proposals/
    jev-system-one-integration-assessment.md A5's "batched as many
    questions... as state" shape), with two `Noul` questions per finding —
    `ground_a_<id>` ("the code this finding describes is not in the
    subject file's diff") and `ground_b_<id>` (a screen for "a line in
    this diff directly contradicts the finding's central claim").

    Returns `None` on any unavailability (module missing, `decide()`
    returns no usable answer) — never raises. Callers fall back to sending
    every finding through the existing (unmodified) stage-two prompt,
    exactly as before this function existed. Never called for a finding
    `protected_subject()` already vetoes (D2) — a verdict from either
    ground can never override that veto, so no call is worth spending on
    one.
    """
    if system_one_decisions is None:
        return None
    if not findings:
        return None

    questions: dict[str, Any] = {}
    for f in findings:
        fid = str(f.get("id"))
        questions[f"ground_a_{fid}"] = {
            "type": "noul",
            "instructions": (
                "The code this finding describes is not present in the "
                "subject file's diff."
            ),
            "criteria": {
                "true": "The diff contains no such code -- the finding's premise is absent.",
                "false": "The diff does contain code matching the finding's premise.",
            },
        }
        questions[f"ground_b_{fid}"] = {
            "type": "noul",
            "instructions": (
                "A line in this diff directly contradicts this finding's "
                "central claim."
            ),
            "criteria": {
                "true": "A specific diff line plausibly contradicts the claim -- worth the full evidence-checked pass.",
                "false": "No diff line looks like it contradicts the claim.",
            },
        }

    state: dict[str, Any] = {
        "packet_diff": packet_diff,
        "findings": [
            {
                "id": str(f.get("id")),
                "file_path": f.get("file_path"),
                "description": f.get("description"),
            }
            for f in findings
        ],
    }

    answers = system_one_decisions.decide(
        state, questions, site="parallel-infrastructure.fact_check",
        dry_run=dry_run,
    )
    if not answers:
        return None

    screen: dict[str, dict[str, float]] = {}
    for f in findings:
        fid = str(f.get("id"))
        entry: dict[str, float] = {}
        for ground_key, answer_key in (("ground_a", f"ground_a_{fid}"), ("ground_b", f"ground_b_{fid}")):
            answer = answers.get(answer_key) if hasattr(answers, "get") else None
            if answer is None:
                continue
            noul = _answer_field(answer, "noul")
            if isinstance(noul, (int, float)):
                entry[ground_key] = noul
        screen[fid] = entry
    return screen


def run(
    *,
    vendor: str,
    round_num: int,
    findings: list[dict[str, Any]],
    packet_diff: str,
    caller: Caller | None,
    model: str | None = None,
    enabled: bool = True,
    dry_run: bool = False,
) -> FactCheckOutcome:
    """Run the fact-check pass for one vendor's already-validated findings.

    Never raises: a disabled pass, no findings, no caller, a caller failure,
    or an unparsable response all result in ``status`` naming why and every
    finding kept. The protected-subject veto runs regardless of the verdict.

    Stage one (judged, optional): screens every non-protected finding on
    both grounds before stage two runs (D1). A confident Ground-A screen
    removes the finding directly -- Ground A needs no quoted evidence line,
    unlike Ground B. A confident Ground-B screen sends only that finding on
    to stage two, where the existing evidence-line check still gates any
    removal. A finding clearing neither ground is kept without ever
    reaching stage two. When stage one is unavailable (module missing, no
    usable answer), every finding falls through to stage two unmodified --
    exactly this function's behavior before this screen existed. Protected
    findings (D2) never enter stage one; they always reach stage two
    unchanged, where the existing post-verdict veto protects them exactly
    as before.
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

    protected_findings = [f for f in findings if protected_subject(f) is not None]
    screenable_findings = [f for f in findings if protected_subject(f) is None]
    screen = _screen_findings(screenable_findings, packet_diff, dry_run=dry_run)

    stage_one_decisions: dict[str, Decision] = {}
    stage_two_findings = findings
    if screen is not None:
        floor = load_ground_screen_confidence_floor()
        stage_two_screenable: list[dict[str, Any]] = []
        for f in screenable_findings:
            fid = str(f.get("id"))
            entry = screen.get(fid, {})
            ground_a = entry.get("ground_a")
            ground_b = entry.get("ground_b")
            has_a = isinstance(ground_a, (int, float))
            has_b = isinstance(ground_b, (int, float))
            if has_a and ground_a >= floor:
                stage_one_decisions[fid] = Decision(
                    finding_id=fid, verdict="removed", ground=GROUND_A,
                )
            elif has_b and ground_b >= floor:
                stage_two_screenable.append(f)
            elif has_a and has_b:
                # Both grounds answered and both confidently below the
                # floor -- only then is skipping stage two justified.
                stage_one_decisions[fid] = Decision(finding_id=fid, verdict="kept")
            else:
                # A partial or malformed per-finding answer (one or both
                # grounds missing/non-numeric) is treated as unavailable
                # for THIS finding -- fail safe to stage two rather than
                # silently keep a finding that was never actually screened.
                stage_two_screenable.append(f)
        stage_two_findings = protected_findings + stage_two_screenable

    to_remove: dict[str, dict[str, Any]] = {}
    if stage_two_findings:
        system_prompt, user_prompt = render_prompts(stage_two_findings, packet_diff)
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

        by_id = {str(f.get("id")): f for f in stage_two_findings}
        if tool == "report_incorrect_comments":
            for item in items:
                fid = str(item.get("finding_id", ""))
                ground = item.get("ground")
                if fid not in by_id or ground not in _GROUNDS:
                    continue
                evidence_line = item.get("evidence_line")
                if ground == GROUND_B:
                    # The contracted evidence field is what makes a Ground B
                    # verdict falsifiable at all — a missing or fabricated line
                    # would let a malformed or hallucinated response silently
                    # discard a valid finding, so it is required and checked
                    # against the subject file's actual diff before removal.
                    if not isinstance(evidence_line, str):
                        continue
                    if not _evidence_line_in_subject_diff(
                        evidence_line, by_id[fid].get("file_path"), packet_diff,
                    ):
                        continue
                to_remove[fid] = item

    decisions: list[Decision] = []
    kept: list[dict[str, Any]] = []
    for f in findings:
        fid = str(f.get("id"))
        if fid in stage_one_decisions:
            decision = stage_one_decisions[fid]
            decisions.append(decision)
            if decision.verdict != "removed":
                kept.append(f)
            continue
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
    ``--json-schema``), the wrong shape for a fact-check verdict. Every
    vendor in agents.yaml already declares an ``alternative`` dispatch mode
    with the flags its own CLI needs for a plain, non-schema-constrained
    prompt (``--print`` for claude, ``exec -s workspace-write`` for codex,
    ``--prompt-file /dev/stdin`` for grok, and so on) — using a single
    hard-coded Claude flag set (``--print --allowedTools``) here made the
    pass silently no-op for every other vendor, since those flags mean
    nothing to their CLIs. This reads that per-vendor mode instead. Returns
    ``None`` (never raises) when the binary is not on PATH, or when the
    vendor declares no synchronous ``alternative``/``quick`` mode to build
    the command from — callers pass that straight to :func:`run` as
    ``caller=None``, which skips gracefully rather than guessing flags.

    Read-only-ness is a property of the fact-check prompt (it only ever
    asks for a verdict, never invites an edit), not of the CLI's own
    tool-permission flags — the same design already used for grok/agy/pi's
    review-mode dispatch (see agents.yaml's comments on those vendors).
    """
    import shutil
    import subprocess

    command = getattr(cli_config, "command", None)
    if not command or shutil.which(command) is None:
        return None
    dispatch_modes = getattr(cli_config, "dispatch_modes", None) or {}
    mode_config = dispatch_modes.get("alternative") or dispatch_modes.get("quick")
    if mode_config is None or getattr(mode_config, "async_dispatch", False):
        return None
    mode_args = list(getattr(mode_config, "args", None) or [])
    model = resolve_economy_model(vendor)
    model_flag = getattr(cli_config, "model_flag", None)
    prompt_via_stdin = getattr(cli_config, "prompt_via_stdin", True)

    def _caller(system_prompt: str, user_prompt: str) -> str:
        full_prompt = system_prompt + "\n\n" + user_prompt
        cmd = [command, *mode_args]
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
