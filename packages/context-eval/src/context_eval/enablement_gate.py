"""The Enablement Consistency Gate: a declared default, and the evidence for it.

One question, asked at build time and nowhere else: **is the injection default
this tree declares authorized by the evidence this tree carries?**

    0  authorized, or nothing is claimed (the default is disabled)
    1  apparatus failure — the gate could not read what it needed to decide
    2  the evidence is current and schema-valid, and its verdict is not a pass
    3  the evidence is absent or has expired

**This gate adds nothing at runtime, deliberately.** ri-12 already fails closed
per request: ``STATE_FALLBACKS`` maps every non-ready service state to an
explicit exact-search fallback, ``UNKNOWN_STATE_FALLBACK`` makes that mapping
total over states nobody has invented yet, and ``collect_semantic_context``
returns a fallback rather than raising. A second runtime path that re-disabled
injection from a report's contents would be a second authority for one decision,
which is exactly what design decision D12 rejects. What ri-12 *cannot* notice is
that the justification for the default has gone stale — a corpus that moved, a
threshold someone edited, an embedder that was swapped, an index built from a
revision this tree does not descend from. That is the whole of this module's
job, and it is a comparison between two committed artifacts.

**It short-circuits when the default is disabled, and that is the mechanism.**
D12 reads "any of these ⇒ the gate requires ``INJECTION_DEFAULT_ENABLED`` is
``False``", and the spec's expiry scenario says disabling the default restores
the check to passing. So a disabled default claims nothing, needs no evidence,
and passes. The corollary is that this gate is correctly green on a tree where
nobody enabled anything, and cannot be watched failing there — which is why
``tests/test_enablement_gate_mutation.py`` exists and why it is not optional.

**A failure always names the condition.** "Enablement not authorized" with no
reason is a gate people learn to route around; every unmet condition is printed
with its id and the values that disagreed.

The declared default is read by parsing the source, not by importing it. Two
reasons, and the second is the load-bearing one: importing would run ri-12's
module in the gate's process for a single boolean, and parsing lets the gate
require that the constant is assigned **exactly once**, at module level, from a
literal. The spec asks for "a single machine-readable declaration"; a default
that could be reassigned in a branch, or computed from an environment lookup,
would be back to being inferred rather than declared.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import report
from .__main__ import EXIT_APPARATUS, EXIT_GATE_FAILURE, EXIT_PASS, EXIT_REPORT_UNUSABLE
from .loader import CorpusError, corpus_digest

#: The one declaration the whole gate reads (design D11).
DEFAULT_CONSTANT = "INJECTION_DEFAULT_ENABLED"

#: Locations relative to the repository root. Defaults, never discovery: each is
#: overridable on the command line, and the root itself is always supplied.
SEMANTIC_CONTEXT_RELATIVE = Path("skills/context-engineering/scripts/semantic_context.py")
REPORT_RELATIVE = Path("docs/evaluation/semantic-context/report.json")
CORPUS_RELATIVE = Path("packages/context-eval/corpus")

PASS_VERDICT = "pass"

#: A git probe must not be able to hang a build.
GIT_TIMEOUT_SECONDS = 15

#: Design D12's six expiry conditions, in the order D12 states them. Any one of
#: them renders the evidence absent, and absent evidence authorizes nothing.
CORPUS_DIGEST_CURRENT = "corpus_digest_current"
HARNESS_VERSION_CURRENT = "harness_version_current"
EMBEDDER_FINGERPRINT_CURRENT = "embedder_fingerprint_current"
INDEXED_REVISION_REACHABLE = "indexed_revision_reachable"
SCHEMA_VALID = "schema_valid"
VERDICT_PASS = "verdict_pass"

EXPIRY_CONDITIONS: tuple[str, ...] = (
    CORPUS_DIGEST_CURRENT,
    HARNESS_VERSION_CURRENT,
    EMBEDDER_FINGERPRINT_CURRENT,
    INDEXED_REVISION_REACHABLE,
    SCHEMA_VALID,
    VERDICT_PASS,
)

#: The base case D12 does not number because it is the state the others reduce
#: to: there is no report at all.
REPORT_PRESENT = "report_present"

CONDITIONS: tuple[str, ...] = (REPORT_PRESENT, *EXPIRY_CONDITIONS)

#: Every condition except the verdict describes evidence that is missing rather
#: than evidence that speaks against enablement. The distinction is the same one
#: the CLI's exit codes draw, and it is the one the July 2026 waiver blurred:
#: "we have no measurement" and "we measured and it failed" are different facts.
EVIDENCE_ABSENT_CONDITIONS: tuple[str, ...] = tuple(
    condition for condition in CONDITIONS if condition != VERDICT_PASS
)


class EnablementGateError(Exception):
    """The gate could not read what it needs to decide. Never a verdict."""


@dataclass(frozen=True)
class Condition:
    """One expiry condition, and why it holds or does not."""

    condition: str
    met: bool
    detail: str

    def __str__(self) -> str:
        return f"{self.condition}: {self.detail}"


@dataclass(frozen=True)
class Outcome:
    """What the gate decided, and every condition it decided it from."""

    default_enabled: bool
    conditions: tuple[Condition, ...]

    @property
    def unmet(self) -> tuple[Condition, ...]:
        return tuple(condition for condition in self.conditions if not condition.met)

    @property
    def authorized(self) -> bool:
        """A disabled default claims nothing and is therefore always authorized."""
        return not self.default_enabled or not self.unmet

    @property
    def evidence_absent(self) -> bool:
        return any(condition.condition in EVIDENCE_ABSENT_CONDITIONS for condition in self.unmet)


# ---------------------------------------------------------------------------
# the declared default
# ---------------------------------------------------------------------------


def declared_default(module_path: Path) -> bool:
    """The value of :data:`DEFAULT_CONSTANT` in *module_path*, read by parsing.

    Requires exactly one module-level assignment from a literal ``bool``. A
    second assignment, an assignment inside a branch, or a value computed from
    anything at all is an error rather than a reading: the requirement is that
    the effective default is *one declaration*, and a gate that quietly took the
    last of several would let the declaration stop being the decision.
    """
    try:
        source = module_path.read_text(encoding="utf-8")
    except OSError as error:
        raise EnablementGateError(f"cannot read the declared default from {module_path}") from error
    try:
        tree = ast.parse(source, filename=str(module_path))
    except SyntaxError as error:
        raise EnablementGateError(f"{module_path} does not parse: {error}") from error

    values: list[ast.expr] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            if _names_the_constant(node.target) and node.value is not None:
                values.append(node.value)
        elif isinstance(node, ast.Assign):
            if any(_names_the_constant(target) for target in node.targets):
                values.append(node.value)

    nested = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and node not in tree.body
        and _assigns_the_constant(node)
    ]
    if nested:
        raise EnablementGateError(
            f"{DEFAULT_CONSTANT} is assigned somewhere other than module level in "
            f"{module_path} (line {nested[0].lineno}); the effective default must be "
            f"one declaration, not the outcome of a branch"
        )
    if len(values) != 1:
        raise EnablementGateError(
            f"{DEFAULT_CONSTANT} is declared {len(values)} times at module level in "
            f"{module_path}; exactly one declaration is required"
        )
    value = values[0]
    if not isinstance(value, ast.Constant) or not isinstance(value.value, bool):
        raise EnablementGateError(
            f"{DEFAULT_CONSTANT} in {module_path} is not a literal bool; a default "
            f"computed at import time is inferred rather than declared"
        )
    return value.value


def _names_the_constant(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == DEFAULT_CONSTANT


def _assigns_the_constant(node: ast.Assign | ast.AnnAssign | ast.AugAssign) -> bool:
    if isinstance(node, ast.Assign):
        return any(_names_the_constant(target) for target in node.targets)
    return _names_the_constant(node.target)


# ---------------------------------------------------------------------------
# the six expiry conditions
# ---------------------------------------------------------------------------


def _verdict_condition(document: dict[str, Any]) -> Condition:
    verdict = document.get("verdict")
    if verdict == PASS_VERDICT:
        return Condition(VERDICT_PASS, True, "the recorded verdict is a pass")
    reasons = ", ".join(str(reason) for reason in document.get("fail_reasons", [])) or "none given"
    return Condition(
        VERDICT_PASS,
        False,
        f"the recorded verdict is {verdict!r} ({reasons}); it never authorized anything",
    )


def _corpus_digest_condition(document: dict[str, Any], corpus_root: Path) -> Condition:
    try:
        current = corpus_digest(corpus_root)
    except CorpusError as error:
        raise EnablementGateError(f"the corpus at {corpus_root} does not load: {error}") from error
    recorded = document.get("harness", {}).get("corpus_digest")
    if recorded == current:
        return Condition(CORPUS_DIGEST_CURRENT, True, f"the corpus digest is still {current}")
    return Condition(
        CORPUS_DIGEST_CURRENT,
        False,
        f"the report was judged against corpus {recorded}, and {corpus_root} now "
        f"digests to {current}: a case or a threshold changed",
    )


def _harness_version_condition(document: dict[str, Any], expected: str | None) -> Condition:
    try:
        current = report.installed_version() if expected is None else expected
    except report.ReportError as error:
        raise EnablementGateError(str(error)) from error
    recorded = document.get("harness", {}).get("version")
    if recorded == current:
        return Condition(HARNESS_VERSION_CURRENT, True, f"the harness is still {current}")
    return Condition(
        HARNESS_VERSION_CURRENT,
        False,
        f"the report was produced by harness {recorded}, and the installed harness "
        f"is {current}: the software that measured this is not the software here",
    )


def _embedder_fingerprint_condition(
    document: dict[str, Any], contract_path: Path | None
) -> Condition:
    recorded = document.get("index", {}).get("embedder", {}).get("fingerprint")
    if contract_path is None:
        return Condition(
            EMBEDDER_FINGERPRINT_CURRENT,
            False,
            f"the report records embedder fingerprint {recorded}, and no configured "
            f"embedding contract was supplied (--embedding-contract) to compare it "
            f"against; an unchecked fingerprint is not a matching one",
        )
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EnablementGateError(
            f"the embedding contract at {contract_path} is unreadable: {error}"
        ) from error
    current = contract.get("fingerprint") if isinstance(contract, dict) else None
    if current is None:
        raise EnablementGateError(
            f"the embedding contract at {contract_path} declares no fingerprint"
        )
    if recorded == current:
        return Condition(
            EMBEDDER_FINGERPRINT_CURRENT, True, f"the embedding fingerprint is still {current}"
        )
    return Condition(
        EMBEDDER_FINGERPRINT_CURRENT,
        False,
        f"the report was measured through embedder {recorded}, and the configured "
        f"contract fingerprints to {current}: a matching model name alone does not "
        f"restore the evidence",
    )


def _indexed_revision_condition(document: dict[str, Any], repository_root: Path) -> Condition:
    revision = document.get("index", {}).get("indexed_revision")
    if not revision:
        return Condition(
            INDEXED_REVISION_REACHABLE,
            False,
            "the report records no indexed revision, so nothing ties the measurement "
            "to a tree this one descends from",
        )
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "merge-base", "--is-ancestor", revision, "HEAD"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise EnablementGateError(
            f"cannot ask git whether {revision} is reachable from {repository_root}: {error}"
        ) from error
    if completed.returncode == 0:
        return Condition(
            INDEXED_REVISION_REACHABLE, True, f"{revision} is an ancestor of the evaluated tree"
        )
    return Condition(
        INDEXED_REVISION_REACHABLE,
        False,
        f"{revision} is not reachable from HEAD in {repository_root}: the measurement "
        f"describes a tree this one does not descend from",
    )


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------


def evaluate(
    *,
    repository_root: Path,
    semantic_context: Path,
    report_path: Path,
    corpus_root: Path,
    embedding_contract: Path | None = None,
    harness_version: str | None = None,
) -> Outcome:
    """Decide whether the declared default is authorized by the recorded evidence."""
    enabled = declared_default(semantic_context)
    if not enabled:
        return Outcome(default_enabled=False, conditions=())

    try:
        document = report.read_report(report_path)
    except report.ReportError as error:
        return Outcome(True, (Condition(REPORT_PRESENT, False, str(error)),))
    present = Condition(REPORT_PRESENT, True, f"a report is readable at {report_path}")

    try:
        report.validate_report(document)
    except report.ReportError as error:
        # Nothing below can be read from a document that is not a report: every
        # field the remaining conditions compare is a field the schema is what
        # guarantees the shape of.
        return Outcome(True, (present, Condition(SCHEMA_VALID, False, str(error))))
    valid = Condition(SCHEMA_VALID, True, "the report satisfies its published contract")

    return Outcome(
        True,
        (
            present,
            valid,
            _corpus_digest_condition(document, corpus_root),
            _harness_version_condition(document, harness_version),
            _embedder_fingerprint_condition(document, embedding_contract),
            _indexed_revision_condition(document, repository_root),
            _verdict_condition(document),
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate. Returns the process exit code."""
    args = _parser().parse_args(list(argv) if argv is not None else None)
    root: Path = args.repository_root
    semantic_context: Path = args.semantic_context or root / SEMANTIC_CONTEXT_RELATIVE
    report_path: Path = args.report or root / REPORT_RELATIVE
    corpus_root: Path = args.corpus or root / CORPUS_RELATIVE

    try:
        outcome = evaluate(
            repository_root=root,
            semantic_context=semantic_context,
            report_path=report_path,
            corpus_root=corpus_root,
            embedding_contract=args.embedding_contract,
            harness_version=args.harness_version,
        )
    except EnablementGateError as error:
        print(f"apparatus failure: {error}", file=sys.stderr)
        return EXIT_APPARATUS

    if not outcome.default_enabled:
        print(
            f"{DEFAULT_CONSTANT} is False in {semantic_context}: semantic context "
            f"injection is off by default, so no evidence is required."
        )
        return EXIT_PASS

    if outcome.authorized:
        print(f"{DEFAULT_CONSTANT} is True, authorized by {report_path}:")
        for condition in outcome.conditions:
            print(f"  met: {condition}")
        return EXIT_PASS

    print(
        f"{DEFAULT_CONSTANT} is True in {semantic_context}, and the evidence at "
        f"{report_path} does not authorize it.",
        file=sys.stderr,
    )
    for condition in outcome.unmet:
        print(f"  unmet condition: {condition}", file=sys.stderr)
    print(
        "Enablement is authorized only by a current, schema-valid, passing report. "
        f"Either retake the measurement or restore {DEFAULT_CONSTANT} to False.",
        file=sys.stderr,
    )
    return EXIT_REPORT_UNUSABLE if outcome.evidence_absent else EXIT_GATE_FAILURE


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-eval-enablement-gate",
        description=(
            "Check the declared semantic-context injection default against the "
            "evaluation report that authorizes it."
        ),
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        required=True,
        help="The tree under test. Every other location defaults relative to it.",
    )
    parser.add_argument("--semantic-context", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument(
        "--embedding-contract",
        type=Path,
        default=None,
        help="JSON holding the configured EmbeddingContract. Without it the "
        "embedding fingerprint cannot be compared, which is an unmet condition.",
    )
    parser.add_argument(
        "--harness-version",
        default=None,
        help="Override the installed harness version the report is compared against.",
    )
    return parser


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
