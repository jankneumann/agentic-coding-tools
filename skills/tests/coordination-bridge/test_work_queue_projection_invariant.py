"""Guard test: the work queue is a projection, never a source of phase truth.

Contract (see docs/guides/work-queue-truth-projection.md and
skills/coordination-bridge/SKILL.md -> "Work-Queue Truth / Projection
Contract"): ``openspec/changes/<id>/loop-state.json`` (``LoopState`` in
``skills/autopilot/scripts/autopilot.py``) is the authoritative execution
state. The coordinator work queue (``/work/claim`` / ``get_work``) is a derived
distribution/claim mechanism. Truth flows loop-state -> queue, never the
reverse. In the guide's words: *"a run's current phase, iteration, and package
status are read from loop-state, and only from loop-state."*

This test FAILS if any skill source reads one of those authoritative fields
back out of a claim result. That is the direction-of-truth inversion the
contract forbids.

If a legitimate future need arises (there is none today — autopilot does not use
the queue for dispatch), do not weaken this guard: implement the projection per
the three enforcement rules in the guide, which keep ``current_phase`` sourced
from loop-state, not from the claim result.

Why AST and not grep
--------------------
This guard used to be a proximity regex: a claim token within 200 characters of
the literal symbols ``current_phase`` / ``loop_state`` / ``LoopState``. That
only fired when the *variable name* happened to be one of those three, so the
realistic inversion walked straight past it (issue #387):

    claim = get_work()
    phase = claim["input_data"]["phase"]   # undetected by the old regex
    dispatch(phase)

The mechanism was checking spelling, not dataflow. The AST check below tracks
the name a claim result is bound to and flags any subscript chain off it that
extracts an authoritative field — whatever the variable is called. The two
false negatives from #387 are pinned as mutation cases in
``TestDetectorCatchesRealisticInversions``.

Known limit: this reads Python source. A skill that emits claim-consuming code
as a *string* (a template, a generated snippet) is invisible to it, as it was
to the regex.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# What counts as a claim
# ---------------------------------------------------------------------------
# The bridge helpers and the raw endpoint they wrap. `http_post("/work/claim")`
# and friends are covered by the endpoint-literal rule below, so a caller that
# skips the helper is still caught.
_CLAIM_FUNCS = frozenset({"try_get_work", "get_work"})
_CLAIM_ENDPOINTS = ("/work/claim", "work/claim")

# ---------------------------------------------------------------------------
# What counts as authoritative
# ---------------------------------------------------------------------------
# Exactly the three things the guide reserves to loop-state — "a run's current
# phase, iteration, and package status" — under both their LoopState field
# names and their queue-side spellings (a queue entry carries the projection
# key `(change_id, phase, iteration)` in `input_data`, so the phase arrives
# there as a bare "phase").
#
# `task_type` is included because in the projection design the queue entry's
# task_type is *derived from* the phase; reading it back to decide what to run
# next re-derives the phase from the queue, which is the same inversion wearing
# different clothes.
#
# `change_id` is deliberately NOT here. A claim result must be allowed to say
# which change it belongs to — that is how a worker finds the loop-state file
# to read the truth *from*. Flagging it would make the guard obstructive
# without protecting the invariant.
#
# test_authority_keys_track_loopstate keeps this list honest against the real
# dataclass.
_AUTHORITY_KEYS = frozenset(
    {
        "phase",
        "current_phase",
        "previous_phase",
        "phase_history",
        "iteration",
        "total_iterations",
        "packages_status",
        "package_status",
        "task_type",
    }
)

# Assignment targets that *are* loop-state. Writing any claim-derived value
# into one of these inverts the arrow regardless of which key was read.
_AUTHORITY_SINKS = _AUTHORITY_KEYS | {"loop_state", "loopstate"}


def _skills_root() -> Path:
    # tests/coordination-bridge/<this file> -> skills/
    return Path(__file__).resolve().parents[2]


def _collect_skill_sources() -> list[Path]:
    """All skill ``.py`` sources, excluding test trees (tests legitimately
    construct synthetic violation snippets)."""
    root = _skills_root()
    files: list[Path] = []
    for path in root.rglob("*.py"):
        parts = set(path.parts)
        if "tests" in parts or "test" in parts:
            continue
        if path.name.startswith("test_"):
            continue
        if ".venv" in parts:
            continue
        files.append(path)
    return files


# ---------------------------------------------------------------------------
# The detector
# ---------------------------------------------------------------------------


def _callee_name(node: ast.Call) -> str | None:
    """Return the called function's bare name (``a.b.claim`` -> ``claim``)."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_claim_call(node: ast.AST) -> bool:
    """True for a call that claims work off the queue.

    Either a call to one of the bridge helpers, or any call carrying the raw
    claim endpoint as a string literal — the latter catches a caller that goes
    straight to HTTP instead of through ``coordination_bridge``.
    """
    if not isinstance(node, ast.Call):
        return False
    if _callee_name(node) in _CLAIM_FUNCS:
        return True
    for arg in [*node.args, *(kw.value for kw in node.keywords)]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if any(ep in arg.value for ep in _CLAIM_ENDPOINTS):
                return True
    return False


def _subscript_key(node: ast.Subscript) -> str | None:
    """Return a string subscript key, or None for non-literal subscripts."""
    sl = node.slice
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
        return sl.value
    return None


def _sink_name(target: ast.AST) -> str | None:
    """Bare name of an assignment target (``state.current_phase`` -> the attr)."""
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Subscript):
        return _subscript_key(target)
    return None


class _ProjectionInversionDetector(ast.NodeVisitor):
    """Flags reads of authoritative loop-state fields out of a claim result.

    Two passes over the tree: the first records which names a claim result (or
    anything derived from one) is bound to, so a binding that appears after its
    use — a loop body, a nested function — is still known; the second reports.
    """

    def __init__(self) -> None:
        self.claim_names: set[str] = set()
        self.violations: list[tuple[int, str]] = []

    # -- pass 1: binding propagation ---------------------------------------

    def _bind(self, targets: list[ast.expr]) -> None:
        for target in targets:
            for node in ast.walk(target):
                if isinstance(node, ast.Name):
                    self.claim_names.add(node.id)

    def collect_bindings(self, tree: ast.AST) -> None:
        # Iterate to a fixed point: `a = claim()`, `b = a["input_data"]`,
        # `c = b["x"]` needs one round per link in the chain.
        for _ in range(10):
            before = len(self.claim_names)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and self._derives_from_claim(node.value):
                    self._bind(node.targets)
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    if self._derives_from_claim(node.value):
                        self._bind([node.target])
                elif isinstance(node, ast.NamedExpr) and self._derives_from_claim(node.value):
                    self._bind([node.target])
                elif isinstance(node, (ast.For, ast.AsyncFor)) and self._derives_from_claim(node.iter):
                    self._bind([node.target])
                elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                    if self._derives_from_claim(node.context_expr):
                        self._bind([node.optional_vars])
            if len(self.claim_names) == before:
                break

    def _derives_from_claim(self, node: ast.AST | None) -> bool:
        """True when *node* evaluates to a claim result or a piece of one."""
        if node is None:
            return False
        if _is_claim_call(node):
            return True
        if isinstance(node, ast.Name):
            return node.id in self.claim_names
        if isinstance(node, (ast.Subscript, ast.Attribute, ast.Await, ast.Starred)):
            return self._derives_from_claim(node.value)
        if isinstance(node, ast.Call):
            # `dict(claim)`, `json.loads(claim["body"])` — the payload flows on.
            return any(self._derives_from_claim(a) for a in node.args)
        return False

    # -- pass 2: detection --------------------------------------------------

    def visit_Subscript(self, node: ast.Subscript) -> None:
        key = _subscript_key(node)
        if key in _AUTHORITY_KEYS and self._derives_from_claim(node.value):
            self.violations.append(
                (node.lineno, f"reads {key!r} out of a work-queue claim result")
            )
        self.generic_visit(node)

    def _check_sink(self, targets: list[ast.expr], value: ast.expr, lineno: int) -> None:
        if not self._derives_from_claim(value):
            return
        for target in targets:
            name = _sink_name(target)
            if name in _AUTHORITY_SINKS:
                self.violations.append(
                    (lineno, f"assigns a claim result into authoritative {name!r}")
                )

    def visit_Assign(self, node: ast.Assign) -> None:
        self._check_sink(node.targets, node.value, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._check_sink([node.target], node.value, node.lineno)
        self.generic_visit(node)


def find_violations(source: str) -> list[tuple[int, str]]:
    """Return ``(lineno, reason)`` for every projection inversion in *source*."""
    tree = ast.parse(source)
    detector = _ProjectionInversionDetector()
    detector.collect_bindings(tree)
    detector.visit(tree)
    return detector.violations


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------


def test_no_skill_sources_current_phase_from_work_queue():
    """No skill source may read the run's phase/iteration/package status out of
    a ``work/claim`` / ``get_work`` result. See module docstring."""
    offenders: list[tuple[Path, int, str]] = []
    for path in _collect_skill_sources():
        try:
            src = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            found = find_violations(src)
        except SyntaxError:
            continue
        for lineno, reason in found:
            offenders.append((path, lineno, reason))

    if offenders:
        root = _skills_root()
        msg = [
            "Work-queue truth/projection contract violated: a skill source "
            "derives authoritative loop-state (phase / iteration / package "
            "status) from a work-queue claim.",
            "loop-state.json is the source of truth; the queue is a derived "
            "projection. See docs/guides/work-queue-truth-projection.md.",
            "Offenders:",
        ]
        for path, lineno, reason in offenders:
            msg.append(f"  {path.relative_to(root)}:{lineno}: {reason}")
        pytest.fail("\n".join(msg))


# ---------------------------------------------------------------------------
# Mutation cases — the detector must catch the forms it exists to catch
# ---------------------------------------------------------------------------


class TestDetectorCatchesRealisticInversions:
    """The old regex passed its own synthetic cases and missed the real ones.

    Each case below is written the way someone would actually write it, not the
    way the detector is implemented. The first two are the verified false
    negatives from issue #387.
    """

    def test_bound_claim_then_nested_phase_read(self):
        """#387 row 2 — the form the guard exists to prevent."""
        src = (
            "claim = get_work()\n"
            "phase = claim['input_data']['phase']\n"
            "dispatch(phase)\n"
        )
        assert find_violations(src), "nested phase read off a bound claim missed"

    def test_bound_claim_then_task_type_read(self):
        """#387 row 3 — task_type is the phase in queue-side clothing."""
        src = (
            "task = try_get_work(agent_id=a)\n"
            "next_step = task['task_type']\n"
        )
        assert find_violations(src), "task_type read off a bound claim missed"

    def test_single_line_coupling(self):
        src = 'current_phase = try_get_work(agent_id="x")["phase"]'
        assert find_violations(src)

    def test_endpoint_form_without_the_helper(self):
        src = 'phase = http_post("/work/claim")["current_phase"]'
        assert find_violations(src)

    def test_detection_survives_renaming_every_variable(self):
        """Nothing here is spelled ``phase`` or ``claim`` — dataflow still tells."""
        src = (
            "blob = try_get_work(agent_id=aid)\n"
            "payload = blob['input_data']\n"
            "step = payload['phase']\n"
            "run(step)\n"
        )
        assert find_violations(src), "renamed inversion missed"

    def test_iteration_read_is_an_inversion_too(self):
        src = "c = get_work()\nn = c['iteration']\n"
        assert find_violations(src)

    def test_package_status_read_is_an_inversion_too(self):
        src = "c = get_work()\ns = c['packages_status']\n"
        assert find_violations(src)

    def test_claim_written_into_loop_state_is_flagged_whatever_the_key(self):
        """Assigning a claim result into loop-state inverts the arrow directly."""
        src = "c = get_work()\nstate.current_phase = c['anything_at_all']\n"
        assert find_violations(src)

    def test_attribute_access_on_the_bridge_module_is_still_a_claim(self):
        src = "c = coordination_bridge.try_get_work(agent_id=a)\np = c['phase']\n"
        assert find_violations(src)

    def test_claim_in_a_loop_is_flagged(self):
        src = "for item in get_work(task_types=['plan']):\n    go(item['phase'])\n"
        assert find_violations(src)


class TestDetectorAllowsLegitimateUsage:
    """A guard that flags correct code gets disabled, so the false-positive
    surface is pinned as tightly as the detection surface."""

    def test_claim_without_reading_authority_is_fine(self):
        src = "task = try_get_work(agent_id=aid, agent_type=at)\nexecute(task)\n"
        assert find_violations(src) == []

    def test_loop_state_read_without_a_claim_is_fine(self):
        src = "state.current_phase = transition(state, outcome)"
        assert find_violations(src) == []

    def test_change_id_off_a_claim_is_fine(self):
        """A worker must be able to learn which change it is working on.

        That is how it finds the loop-state file to read the truth *from* —
        the opposite of an inversion.
        """
        src = "c = get_work()\ncid = c['change_id']\nstate = load_state(cid)\n"
        assert find_violations(src) == []

    def test_projecting_loop_state_into_the_queue_is_the_allowed_direction(self):
        """Rule (a) of the contract, written out — must not trip the guard."""
        src = (
            "submit_work(\n"
            "    task_type='implement',\n"
            "    input_data={'change_id': state.change_id,\n"
            "                'phase': state.current_phase,\n"
            "                'iteration': state.iteration},\n"
            ")\n"
        )
        assert find_violations(src) == []

    def test_prose_naming_both_sides_is_not_code(self):
        """The old regex needed comment-stripping to avoid flagging the guide.

        The AST never sees comments or docstrings, so the contract can be
        described in full inside a skill source without tripping it.
        """
        src = (
            '"""current_phase comes from loop-state, never from get_work()."""\n'
            "# do not set current_phase from a /work/claim result\n"
            "x = 1\n"
        )
        assert find_violations(src) == []

    def test_unrelated_dict_named_task_is_fine(self):
        src = "task = build_task()\nnext_step = task['task_type']\n"
        assert find_violations(src) == []


# ---------------------------------------------------------------------------
# The authority list must track the real dataclass
# ---------------------------------------------------------------------------


def _loopstate_fields() -> set[str]:
    """LoopState's field names, read from autopilot.py's AST.

    Parsed rather than imported: importing autopilot pulls in its whole runtime
    for three strings.
    """
    autopilot = _skills_root() / "autopilot" / "scripts" / "autopilot.py"
    tree = ast.parse(autopilot.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "LoopState":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError("LoopState not found in autopilot.py")


def test_authority_keys_track_loopstate():
    """Every authority key must be a LoopState field or a known queue spelling.

    Without this, renaming ``current_phase`` in the dataclass would leave the
    guard watching a field that no longer exists — passing while guarding
    nothing.
    """
    fields = _loopstate_fields()
    # Queue-side spellings: `input_data` carries the projection key
    # `(change_id, phase, iteration)`, and task_type is derived from the phase.
    queue_side = {"phase": "current_phase", "package_status": "packages_status",
                  "task_type": "current_phase"}

    unbacked = {
        key
        for key in _AUTHORITY_KEYS
        if key not in fields and queue_side.get(key) not in fields
    }
    assert unbacked == set(), (
        f"authority keys with no backing LoopState field: {sorted(unbacked)} — "
        f"the dataclass changed and this guard was not updated"
    )


def test_guard_actually_runs():
    """Sanity: the scan examines a non-empty set of skill sources."""
    files = _collect_skill_sources()
    assert files, "No skill .py sources found — guard is a no-op"
