"""Load, validate, and digest the evaluation corpus.

Three responsibilities, in this order, and the order matters:

1. **Validate against the promoted contracts.** The manifest and every case are
   checked against ``openspec/contracts/semantic-context-evaluation/schemas/``
   before anything is built from them. A corpus that does not validate does not
   load — there is no partially-loaded corpus, because a run over a partial
   corpus would compute a pass rate over whatever happened to survive, which is
   the shrinking-denominator failure this whole change exists to make
   impossible (design D3).

2. **Check the things JSON Schema cannot say.** Every case id a consumer slice
   names must resolve to a listed case file whose own ``consumer`` field agrees,
   every case must be claimed by exactly one slice, and every recorded response a
   case names must exist. These are sibling comparisons across documents; a
   schema can only see one document at a time.

3. **Digest.** The digest is over the *bytes* of the manifest, every listed case
   file, and every referenced response file, keyed by corpus-relative path and
   sorted. Bytes rather than parsed content, deliberately: reformatting a case
   file moves the digest, which is conservative in the only direction that is
   safe — a report is invalidated when it might not describe the current corpus,
   never kept when it might not. Nothing here reads a clock, a random source, or
   an unordered set, so two loads in two processes agree (design D12, D16).

**No threshold value appears in this module, or anywhere else under ``src/``.**
Every number the gates judge against lives in ``corpus/manifest.yaml`` and is
carried through as data.
``test_thresholds_are_not_readable_from_the_scoring_modules`` fails if one
reappears here as a literal, which is the executable form of the defect at
``run_eval.py:159-161`` (design D6).

The repository root is never derived here. ``PACKAGE_ROOT`` is resolved by
walking named parents rather than by index, so this module has no positional
path arithmetic of the kind that made the archived evaluation unreproducible
(``run_eval.py:31``: ``REPO_ROOT = HERE.parents[3]``, correct until archival
added a path segment). Callers that need a different corpus pass one in.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .models import (
    Budget,
    Case,
    CaseLabels,
    ConsumerSlice,
    Corpus,
    EvidenceSpan,
    ExactSearchBaseline,
    Expectation,
    GateDeclaration,
    Provenance,
    RecordedResponse,
    Scope,
    freeze_thresholds,
)

#: ``packages/context-eval``. ``.parent`` three times, not ``parents[3]``: the
#: index form is exactly what broke when archival added a path segment, and the
#: named form at least fails loudly rather than resolving to a plausible wrong
#: directory.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_CORPUS_ROOT = PACKAGE_ROOT / "corpus"

#: The promoted contracts. The change-local authoring copies are deliberately
#: not consulted: they move when the change is archived, and a validator that
#: followed them would stop working on exactly the day the corpus most needs to
#: still be loadable.
DEFAULT_SCHEMA_DIR = (
    PACKAGE_ROOT.parent.parent
    / "openspec"
    / "contracts"
    / "semantic-context-evaluation"
    / "schemas"
)

MANIFEST_NAME = "manifest.yaml"
CORPUS_SCHEMA_NAME = "context-eval-corpus.schema.json"
CASE_SCHEMA_NAME = "context-eval-case.schema.json"

_DIGEST_FIELD_SEPARATOR = "\x00"
_DIGEST_RECORD_SEPARATOR = "\n"


class CorpusError(Exception):
    """The corpus is unusable. Never raised for anything recoverable."""


def load_corpus(
    corpus_root: Path | str | None = None,
    *,
    schema_dir: Path | str | None = None,
) -> Corpus:
    """Load and fully validate the corpus rooted at *corpus_root*.

    Args:
        corpus_root: Directory holding ``manifest.yaml``. Injected rather than
            discovered, so a caller can load a copy — the mutation the digest
            test relies on, and the shape a future harness needs to compare two
            corpora.
        schema_dir: Directory holding the promoted schemas.

    Raises:
        CorpusError: for a missing, unparseable, schema-invalid, or internally
            inconsistent corpus. Every one of those is fatal by design.
    """
    root = Path(corpus_root) if corpus_root is not None else DEFAULT_CORPUS_ROOT
    schemas = Path(schema_dir) if schema_dir is not None else DEFAULT_SCHEMA_DIR

    manifest_path = root / MANIFEST_NAME
    manifest = _read_yaml(manifest_path)
    _validate(manifest, schemas / CORPUS_SCHEMA_NAME, str(manifest_path))

    case_validator = _validator(schemas / CASE_SCHEMA_NAME)
    cases: list[Case] = []
    digest_inputs: list[Path] = [manifest_path]

    for relative in manifest["cases"]:
        case_path = root / relative
        document = _read_yaml(case_path)
        _validate(document, schemas / CASE_SCHEMA_NAME, str(case_path), case_validator)
        case = _build_case(document, relative)
        cases.append(case)
        digest_inputs.append(case_path)
        if case.recorded_response is not None:
            response_path = root / case.recorded_response.path
            _check_recorded_response(response_path)
            digest_inputs.append(response_path)

    consumers = tuple(_build_slice(entry) for entry in manifest["consumers"])
    _check_cross_references(cases, consumers)

    return Corpus(
        corpus_id=manifest["corpus_id"],
        description=manifest.get("description"),
        k=manifest["k"],
        budget=Budget(**manifest["budget"]),
        consumers=consumers,
        gates=tuple(_build_gate(entry) for entry in manifest["gates"]),
        cases=tuple(cases),
        digest=_digest(root, digest_inputs),
        root=root,
    )


def corpus_digest(
    corpus_root: Path | str | None = None,
    *,
    schema_dir: Path | str | None = None,
) -> str:
    """The digest of a corpus that has been proven loadable.

    Deliberately routed through :func:`load_corpus` rather than hashing the
    directory directly. A digest of an unvalidated corpus would be a stable
    identifier for something that cannot be measured, and the enablement gate
    would compare it happily.
    """
    return load_corpus(corpus_root, schema_dir=schema_dir).digest


# ---------------------------------------------------------------------------
# reading and validation
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CorpusError(f"corpus file is missing: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CorpusError(f"corpus file is not valid YAML: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise CorpusError(f"corpus file is not a mapping: {path}")
    return document


def _check_recorded_response(path: Path) -> None:
    """Prove a recorded response exists and parses. Its content is not read here.

    Parsing it and throwing the result away is the point: the loader's job is to
    refuse a corpus that references a body nobody can read, and interpreting that
    body belongs to the scorer that drives the case. A loader that also decoded
    it would be the second place that knows the response shape.
    """
    if not path.is_file():
        raise CorpusError(f"recorded response is missing: {path}")
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"recorded response is not valid JSON: {path}: {exc}") from exc


def _validator(schema_path: Path) -> Draft202012Validator:
    if not schema_path.is_file():
        raise CorpusError(f"promoted schema is missing: {schema_path}")
    return Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))


def _validate(
    document: Mapping[str, Any],
    schema_path: Path,
    label: str,
    validator: Draft202012Validator | None = None,
) -> None:
    checker = validator if validator is not None else _validator(schema_path)
    errors = sorted(checker.iter_errors(document), key=lambda err: list(err.absolute_path))
    if errors:
        detail = "; ".join(f"{list(err.absolute_path)}: {err.message}" for err in errors)
        raise CorpusError(f"{label} does not satisfy {schema_path.name}: {detail}")


# ---------------------------------------------------------------------------
# document -> model
# ---------------------------------------------------------------------------


def _build_case(document: Mapping[str, Any], source_path: str) -> Case:
    labels = document["labels"]
    expectation = document.get("expectation")
    recorded = document.get("recorded_response")
    baseline = document.get("exact_search_baseline")
    provenance = document.get("provenance")

    return Case(
        case_id=document["case_id"],
        consumer=document["consumer"],
        query=document["query"],
        category=document["category"],
        scope=Scope(
            read_allow=tuple(document["scope"]["read_allow"]),
            deny=tuple(document["scope"]["deny"]),
        ),
        labels=CaseLabels(
            expected_files=tuple(labels["expected_files"]),
            must_touch=tuple(labels["must_touch"]),
            evidence_spans=tuple(
                EvidenceSpan(
                    file_path=span["file_path"],
                    start_line=span["start_line"],
                    end_line=span["end_line"],
                )
                for span in labels["evidence_spans"]
            ),
        ),
        rationale=document["rationale"],
        source_path=source_path,
        expectation=(
            Expectation(
                status=expectation["status"],
                trigger=expectation.get("trigger"),
                reason=expectation.get("reason"),
                rendered_hits=expectation.get("rendered_hits"),
            )
            if expectation is not None
            else None
        ),
        recorded_response=(
            RecordedResponse(
                path=recorded["path"],
                service_state=recorded.get("service_state"),
                adversarial=bool(recorded.get("adversarial", False)),
            )
            if recorded is not None
            else None
        ),
        exact_search_baseline=(
            ExactSearchBaseline(
                ripgrep_baseline=baseline["ripgrep_baseline"],
                recorded_at_revision=baseline.get("recorded_at_revision"),
            )
            if baseline is not None
            else None
        ),
        provenance=(
            Provenance(
                rescued_from=provenance["rescued_from"],
                original_case_id=provenance.get("original_case_id"),
                notes=provenance.get("notes"),
            )
            if provenance is not None
            else None
        ),
    )


def _build_slice(entry: Mapping[str, Any]) -> ConsumerSlice:
    return ConsumerSlice(
        consumer=entry["consumer"],
        utility_applicable=entry["utility_applicable"],
        cases=tuple(entry["cases"]),
        utility_not_applicable_reason=entry.get("utility_not_applicable_reason"),
    )


def _build_gate(entry: Mapping[str, Any]) -> GateDeclaration:
    return GateDeclaration(
        id=entry["id"],
        kind=entry["kind"],
        required=entry["required"],
        min_index_tier=entry["min_index_tier"],
        thresholds=freeze_thresholds(entry["thresholds"]),
        description=entry.get("description"),
    )


# ---------------------------------------------------------------------------
# cross-document checks JSON Schema cannot express
# ---------------------------------------------------------------------------


def _check_cross_references(
    cases: Iterable[Case],
    consumers: Iterable[ConsumerSlice],
) -> None:
    case_list = list(cases)
    slice_list = list(consumers)

    by_id: dict[str, Case] = {}
    duplicates = []
    for case in case_list:
        if case.case_id in by_id:
            duplicates.append(case.case_id)
        by_id[case.case_id] = case
    if duplicates:
        raise CorpusError(f"duplicate case ids: {sorted(set(duplicates))}")

    claims: dict[str, list[str]] = {}
    for slice_ in slice_list:
        for case_id in slice_.cases:
            claims.setdefault(case_id, []).append(slice_.consumer)

    problems: list[str] = []

    for case_id, owners in sorted(claims.items()):
        claimed = by_id.get(case_id)
        if claimed is None:
            problems.append(f"consumer slice names {case_id}, which has no case file")
            continue
        if len(owners) != 1:
            problems.append(f"{case_id} is claimed by {len(owners)} consumer slices: {owners}")
        elif claimed.consumer != owners[0]:
            problems.append(
                f"{case_id} declares consumer={claimed.consumer} "
                f"but is claimed by {owners[0]}"
            )

    for case in case_list:
        if case.case_id not in claims:
            problems.append(f"{case.case_id} is claimed by no consumer slice")

    if problems:
        raise CorpusError("; ".join(problems))


# ---------------------------------------------------------------------------
# digest
# ---------------------------------------------------------------------------


def _digest(root: Path, paths: Iterable[Path]) -> str:
    """Hash the corpus's own bytes, keyed by corpus-relative path and sorted.

    Sorted, so the order the manifest happens to list files in cannot change the
    result; keyed by path, so moving a case's content into a differently-named
    file does change it. Both matter: the first would make the digest depend on
    editing order, the second would let a rename pass as the same evidence.
    """
    records = sorted(
        _DIGEST_FIELD_SEPARATOR.join(
            (path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
        )
        for path in set(paths)
    )
    stream = _DIGEST_RECORD_SEPARATOR.join(records)
    return hashlib.sha256(stream.encode("utf-8")).hexdigest()
