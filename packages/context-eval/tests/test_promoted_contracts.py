"""The three ri-13 evaluation contracts are the fail-closed mechanism itself.

Design decision D3 puts the load-bearing constraint in the schema rather than in
prose: ``verdict`` has exactly two members, ``gates[].required`` is
``{"const": true}``, and there is no waiver field anywhere in any document. The
report this change replaces —
``openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/spike-report.md:9-19``,
"BLOCKED (environment) -> WAIVED (operator decision)" — must be *unwritable*
under these contracts. This module is what makes that a test rather than an
intention.

Every schema exists in two live locations:

* ``openspec/changes/gate-semantic-context-default-enablement/contracts/schemas/``
  — the in-flight authoring copy, which archival will move.
* ``openspec/contracts/semantic-context-evaluation/schemas/`` — the stable,
  capability-scoped home described in ``openspec/contracts/README.md``.

Tests, the Makefile target, and CI load the promoted copy, never the change-local
one. Two copies can silently diverge, which is exactly the archive-drift the
promoted location exists to prevent, so the byte-compare below pins them
together — and ``$id`` must name the *promoted* path, because a change-local
``$id`` is the class of defect that made the D9 evaluation unreproducible
(``run_eval.py:31``: ``REPO_ROOT = HERE.parents[3]``, correct only until archival
added a path segment).

The closed-enum tests derive their expectations from the change's
``contracts/README.md`` rather than restating the member lists here. A count in
prose that has drifted from the schema misleads every later reader, and a second
hand-typed copy of an enum in a test file is a third thing to keep in sync. This
follows ri-12's ``test_semantic_context_schemas.py`` technique.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]

CHANGE_ID = "gate-semantic-context-default-enablement"
CAPABILITY = "semantic-context-evaluation"

CHANGE_LOCAL = REPO_ROOT / "openspec/changes" / CHANGE_ID / "contracts/schemas"
PROMOTED = REPO_ROOT / "openspec/contracts" / CAPABILITY / "schemas"

CHANGE_README = REPO_ROOT / "openspec/changes" / CHANGE_ID / "contracts/README.md"
CONTRACTS_README = REPO_ROOT / "openspec/contracts/README.md"

#: ri-12's promoted input contract (design D4). The report mirrors three of its
#: enums, and mirrored enums drift; cross-checking against the real schema turns
#: that drift into a failure here instead of a silent disagreement in a report.
RI12_SECTION = (
    REPO_ROOT
    / "openspec/contracts/code-search/schemas/semantic-context-section.schema.json"
)

REPORT = "context-eval-report.schema.json"
CORPUS = "context-eval-corpus.schema.json"
CASE = "context-eval-case.schema.json"

SCHEMA_NAMES = (REPORT, CORPUS, CASE)

#: The promoted ``$id`` prefix. ri-12's schemas use this host, and a relative
#: ``$ref`` resolves against ``$id``, so the suffix has to be the promoted
#: directory or a sibling reference would point into the archived tree.
ID_PREFIX = f"https://agentic-coding-tools/openspec/contracts/{CAPABILITY}/schemas/"

#: A property name matching any of these would re-open the escape hatch D3
#: closes. ``unmeasured`` appears here as a *name* pattern only: it is a
#: legitimate ``fail_reasons`` enum *value*, and
#: ``test_unmeasured_is_a_permitted_fail_reason_value`` pins that distinction so
#: nobody "fixes" this pattern by deleting the value the contract needs.
WAIVER_NAME_PATTERN = re.compile(
    r"waiv|override|blocked|skip|unmeasured|exempt|bypass", re.IGNORECASE
)

#: JSON Schema keywords whose contents are values, never property names. The
#: walk must not descend into them, or ``fail_reasons``' ``unmeasured`` member
#: would read as a waiver-shaped field.
VALUE_KEYWORDS = frozenset({"enum", "const", "examples", "default"})

#: Keywords whose subschemas are *predicates over a document*, not declarations
#: of what a property may hold. ``{"if": {"properties": {"verdict": {"const":
#: "fail"}}}}`` asks "is this the failing branch?"; it does not declare the
#: verdict vocabulary, and reading it as one would make every conditional look
#: like an unclosed enum. The waiver walk deliberately does *not* skip these — a
#: waiver-shaped name is disqualifying wherever it appears, including in a
#: predicate.
PREDICATE_KEYWORDS = frozenset({"if", "not"})

#: JSON Schema keywords whose *keys* are property names.
NAME_BEARING_KEYWORDS = (
    "properties",
    "patternProperties",
    "dependentSchemas",
    "dependentRequired",
    "$defs",
    "definitions",
)

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

#: README enum label -> (schema file, JSON pointer to the enum). The pointer is
#: data so a failure names the exact location rather than raising a KeyError from
#: inside a lambda.
ENUM_LOCATIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "verdict": (REPORT, ("$defs", "Verdict", "enum")),
    "fail_reasons[]": (REPORT, ("properties", "fail_reasons", "items", "enum")),
    "gates[].kind": (REPORT, ("$defs", "GateResult", "properties", "kind", "enum")),
    "index.tier": (REPORT, ("properties", "index", "properties", "tier", "enum")),
    "cases[].unscored_reason": (
        REPORT,
        ("$defs", "CaseResult", "properties", "unscored_reason", "enum"),
    ),
    "category": (CASE, ("properties", "category", "enum")),
}

#: ri-12 enum pointer -> the pointers in this change's schemas that mirror it.
MIRRORED_RI12_ENUMS: dict[tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]] = {
    ("properties", "status", "enum"): (
        (REPORT, ("$defs", "ArmResult", "properties", "status", "enum")),
        (CASE, ("properties", "expectation", "properties", "status", "enum")),
    ),
    ("properties", "fallback", "properties", "trigger", "enum"): (
        (REPORT, ("$defs", "ArmResult", "properties", "fallback_trigger", "enum")),
        (CASE, ("properties", "expectation", "properties", "trigger", "enum")),
    ),
    ("properties", "fallback", "properties", "reason", "enum"): (
        (REPORT, ("$defs", "ArmResult", "properties", "fallback_reason", "enum")),
        (CASE, ("properties", "expectation", "properties", "reason", "enum")),
    ),
    ("properties", "fallback", "properties", "service_state", "enum"): (
        (
            CASE,
            ("properties", "recorded_response", "properties", "service_state", "enum"),
        ),
    ),
}


# --------------------------------------------------------------------------
# Loading, with failures that name the missing thing
# --------------------------------------------------------------------------


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        pytest.fail(
            f"{path.relative_to(REPO_ROOT)} does not exist. "
            "All three evaluation schemas must be authored under the change's "
            "contracts/schemas/ and promoted to "
            f"openspec/contracts/{CAPABILITY}/schemas/ before archival."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def promoted(name: str) -> dict[str, Any]:
    return _read(PROMOTED / name)


def change_local(name: str) -> dict[str, Any]:
    return _read(CHANGE_LOCAL / name)


def dig(document: dict[str, Any], pointer: tuple[str, ...], origin: str) -> Any:
    """Resolve ``pointer`` or fail naming the path, never raise ``KeyError``.

    Same-document ``$ref``s are followed at every step, so a schema is free to
    factor a repeated definition into ``$defs`` without every pointer here having
    to know it did. That matters: a single shared definition is a stronger
    guarantee than three identical literals, and the tests should not push the
    contract toward the weaker shape.
    """
    node: Any = resolve_local_ref(document, document)
    for index, key in enumerate(pointer):
        if not isinstance(node, dict) or key not in node:
            pytest.fail(
                f"{origin} has no {'/'.join(pointer)}; resolution stopped at "
                f"{'/'.join(pointer[:index]) or '<root>'}."
            )
        node = resolve_local_ref(document, node[key])
    return node


def readme_text() -> str:
    return _read_text(CHANGE_README)


def _read_text(path: Path) -> str:
    if not path.is_file():
        pytest.fail(f"{path.relative_to(REPO_ROOT)} does not exist.")
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Parsing the README's closed-enum declarations
# --------------------------------------------------------------------------

#: A closed-enum paragraph: a backticked label, an em dash, a comma-separated
#: run of backticked members terminated by a period, and somewhere after it a
#: "<word> values" count.
_PARAGRAPH = re.compile(r"^`(?P<label>[^`\n]+)`\s+—\s+(?P<rest>.*?)(?=\n\n|\Z)", re.S | re.M)
_MEMBER_LIST = re.compile(r"^(?P<list>`[^`\n]+`(?:\s*,\s*`[^`\n]+`)*)\.")
_COUNT = re.compile(r"\b(?P<word>[A-Za-z]+) values\b")


def closed_enum_section() -> str:
    text = readme_text()
    if "## Closed enums" not in text:
        pytest.fail(
            f"{CHANGE_README.relative_to(REPO_ROOT)} has no '## Closed enums' "
            "section; the enum expectations are derived from it."
        )
    return text.split("## Closed enums", 1)[1].split("\n## ", 1)[0]


def readme_declarations() -> dict[str, tuple[list[str], int]]:
    """label -> (declared members, declared count), from the README prose."""
    declarations: dict[str, tuple[list[str], int]] = {}
    for match in _PARAGRAPH.finditer(closed_enum_section()):
        rest = match.group("rest")
        members = _MEMBER_LIST.match(rest)
        count = _COUNT.search(rest)
        if not members or not count:
            # e.g. `per_consumer[].utility_applicable`, which is a required
            # boolean rather than an enum. Not a closed-enum declaration.
            continue
        word = count.group("word").lower()
        if word not in NUMBER_WORDS:
            pytest.fail(
                f"the README states the count for `{match.group('label')}` as "
                f"{count.group('word')!r}, which is not a number word this test "
                "can read. Spell it out (e.g. 'Twelve values.')."
            )
        declarations[match.group("label")] = (
            re.findall(r"`([^`\n]+)`", members.group("list")),
            NUMBER_WORDS[word],
        )
    return declarations


# --------------------------------------------------------------------------
# Property-name walk
# --------------------------------------------------------------------------


def property_names(node: Any, pointer: str = "") -> Iterator[tuple[str, str]]:
    """Yield ``(pointer, name)`` for every property-name position in ``node``.

    Only positions where JSON Schema puts a *property name* are yielded, so an
    enum value that happens to look waiver-shaped is never mistaken for a field.
    """
    if isinstance(node, dict):
        for keyword in NAME_BEARING_KEYWORDS:
            block = node.get(keyword)
            if isinstance(block, dict):
                for name in block:
                    yield f"{pointer}/{keyword}", name
        required = node.get("required")
        if isinstance(required, list):
            for name in required:
                if isinstance(name, str):
                    yield f"{pointer}/required", name
        for key, value in node.items():
            if key in VALUE_KEYWORDS:
                continue
            yield from property_names(value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from property_names(item, f"{pointer}/{index}")


def resolve_local_ref(document: dict[str, Any], schema: Any) -> Any:
    """Follow a same-document ``$ref`` so a factored definition is inspectable.

    These schemas are self-contained by necessity — the verification commands
    build a bare validator with no registry — so every ``$ref`` in them is a
    local ``#/$defs/...`` pointer. Following it here is what lets the tests read
    a shared definition instead of forcing the schemas to repeat themselves.
    """
    seen: set[str] = set()
    while isinstance(schema, dict) and isinstance(schema.get("$ref"), str):
        ref = schema["$ref"]
        if not ref.startswith("#/") or ref in seen:
            return schema
        seen.add(ref)
        node: Any = document
        for part in ref[2:].split("/"):
            if not isinstance(node, dict) or part not in node:
                return schema
            node = node[part]
        schema = node
    return schema


def verdict_enums(
    document: dict[str, Any], node: Any = None, pointer: str = ""
) -> Iterator[tuple[str, Any]]:
    """Yield every ``verdict`` property schema found anywhere in ``document``.

    Local ``$ref``s are resolved, so factoring the verdict into one ``$defs``
    entry — a stronger guarantee than three identical literals — is visible to
    the assertion rather than invisible to it.
    """
    if node is None:
        node = document
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict) and "verdict" in properties:
            yield (
                f"{pointer}/properties/verdict",
                resolve_local_ref(document, properties["verdict"]),
            )
        for key, value in node.items():
            if key in VALUE_KEYWORDS or key in PREDICATE_KEYWORDS:
                continue
            yield from verdict_enums(document, value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from verdict_enums(document, item, f"{pointer}/{index}")


# --------------------------------------------------------------------------
# Promotion, drift, and identity
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_change_local_schema_exists(name: str) -> None:
    """Every schema this module guards is actually authored in the change."""
    assert (CHANGE_LOCAL / name).is_file(), (
        f"{name} is missing from {CHANGE_LOCAL.relative_to(REPO_ROOT)}."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_promoted_schema_exists(name: str) -> None:
    """Promote-before-archive is a hard repository rule, not bookkeeping."""
    assert (PROMOTED / name).is_file(), (
        f"{name} is missing from {PROMOTED.relative_to(REPO_ROOT)}. Promote it "
        "(see openspec/contracts/README.md) so the contract keeps a path that "
        "does not move when this change is archived."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_promoted_schema_is_byte_identical(name: str) -> None:
    """A byte of drift is a second contract nobody knows they are validating."""
    local = CHANGE_LOCAL / name
    stable = PROMOTED / name
    for path in (local, stable):
        if not path.is_file():
            pytest.fail(f"{path.relative_to(REPO_ROOT)} does not exist.")
    assert local.read_bytes() == stable.read_bytes(), (
        f"{name} differs between {CHANGE_LOCAL.relative_to(REPO_ROOT)} and "
        f"{PROMOTED.relative_to(REPO_ROOT)}. Change both in the same commit."
    )


def test_no_authored_schema_is_left_unpromoted() -> None:
    """A schema authored but never promoted is lost on archival.

    Globbing both directories rather than trusting ``SCHEMA_NAMES`` is what makes
    this catch a *fourth* schema: adding one to either tree without adding it
    here fails, instead of quietly escaping every test in this module.
    """
    authored = {path.name for path in CHANGE_LOCAL.glob("*.schema.json")}
    stable = {path.name for path in PROMOTED.glob("*.schema.json")}
    assert authored == set(SCHEMA_NAMES), (
        f"{CHANGE_LOCAL.relative_to(REPO_ROOT)} holds {sorted(authored)}; this "
        f"module guards {sorted(SCHEMA_NAMES)}. Update SCHEMA_NAMES and the "
        "openspec/contracts/README.md table."
    )
    assert authored == stable, (
        f"unpromoted: {sorted(authored - stable)}; promoted but not authored: "
        f"{sorted(stable - authored)}."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_id_names_the_promoted_location(name: str) -> None:
    """A change-local ``$id`` is the D9 defect in contract form.

    ``$id`` is the base every relative reference resolves against, so an ``$id``
    naming ``openspec/changes/<id>/`` points consumers at a directory archival
    moves.
    """
    schema_id = promoted(name).get("$id")
    assert schema_id == f"{ID_PREFIX}{name}", (
        f"{name} declares $id {schema_id!r}; expected {ID_PREFIX}{name!r}."
    )
    assert "openspec/changes" not in str(schema_id), (
        f"{name}'s $id names a change-local path, which archival moves."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_a_valid_draft_2020_12_schema(name: str) -> None:
    document = promoted(name)
    assert document.get("$schema") == "https://json-schema.org/draft/2020-12/schema", (
        f"{name} declares $schema {document.get('$schema')!r}."
    )
    Draft202012Validator.check_schema(document)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_closed_at_the_top_level(name: str) -> None:
    """An open contract cannot be relied on: unknown fields pass review."""
    assert promoted(name).get("additionalProperties") is False


def test_contracts_readme_lists_the_capability() -> None:
    """The stable directory's index is how a later reader finds these at all."""
    text = _read_text(CONTRACTS_README)
    assert f"`{CAPABILITY}`" in text, (
        f"openspec/contracts/README.md has no row for `{CAPABILITY}`."
    )
    for name in SCHEMA_NAMES:
        assert f"`{name}`" in text, (
            f"openspec/contracts/README.md's contents table does not name {name}."
        )


# --------------------------------------------------------------------------
# D3 mechanism 1 — the verdict enum has exactly two members
# --------------------------------------------------------------------------


def test_verdict_enum_has_exactly_pass_and_fail() -> None:
    """The change's whole thesis, as one assertion.

    Asserted as an exact set rather than a subset, so adding a third member —
    ``waived``, ``blocked``, ``skip``, ``partial``, ``unmeasured``, ``n/a`` —
    fails here. ``BLOCKED (environment) -> WAIVED (operator decision)`` has to be
    unwritable, and "could not measure" representable only as
    ``{"verdict": "fail", "fail_reasons": ["unmeasured"]}``.
    """
    schema = promoted(REPORT)
    enum = resolve_local_ref(
        schema, dig(schema, ("properties", "verdict"), REPORT)
    ).get("enum")
    assert enum is not None, f"{REPORT}'s top-level verdict is not a closed enum."
    assert set(enum) == {"pass", "fail"}, (
        f"the report verdict enum is {enum}; it must be exactly "
        "['pass', 'fail'] (design D3)."
    )
    assert len(enum) == 2, f"the verdict enum has duplicate members: {enum}."


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_every_nested_verdict_is_the_same_closed_pair(name: str) -> None:
    """Gate and per-consumer verdicts are not a loophole in the top-level one.

    A ``gates[].verdict`` enum admitting ``skip`` would let a run report a
    passing composed verdict over gates that never decided anything.
    """
    document = promoted(name)
    for pointer, schema in verdict_enums(document):
        enum = schema.get("enum")
        assert enum is not None, (
            f"{name}{pointer} is not a closed enum; every verdict in these "
            "contracts must be enum: ['pass', 'fail']."
        )
        assert set(enum) == {"pass", "fail"}, (
            f"{name}{pointer} admits {sorted(set(enum) - {'pass', 'fail'})}."
        )


def test_fail_reasons_is_required_by_a_failing_verdict() -> None:
    """A failure that does not say which clause failed is a waiver in disguise."""
    schema = promoted(REPORT)
    conditionals = schema.get("allOf")
    assert isinstance(conditionals, list) and conditionals, (
        f"{REPORT} declares no allOf; the verdict/fail_reasons implication is "
        "what makes a failure explain itself."
    )
    requires_reasons = [
        block
        for block in conditionals
        if _asserts_const(block.get("if"), "verdict", "fail")
        and "fail_reasons" in (block.get("then", {}).get("required") or [])
    ]
    assert requires_reasons, (
        "no allOf branch requires fail_reasons when verdict is 'fail'."
    )
    forbids_reasons = [
        block
        for block in conditionals
        if _asserts_const(block.get("if"), "verdict", "pass")
        and "fail_reasons" in ((block.get("then", {}).get("not") or {}).get("required") or [])
    ]
    assert forbids_reasons, (
        "no allOf branch forbids fail_reasons when verdict is 'pass'. A passing "
        "report carrying failure reasons is two claims about one run."
    )


def _asserts_const(condition: Any, field: str, value: str) -> bool:
    if not isinstance(condition, dict):
        return False
    properties = condition.get("properties")
    if not isinstance(properties, dict) or field not in properties:
        return False
    return properties[field].get("const") == value


def test_fail_reasons_cannot_be_an_empty_or_repeated_list() -> None:
    """``fail_reasons: []`` would be a fail that names nothing."""
    reasons = dig(promoted(REPORT), ("properties", "fail_reasons"), REPORT)
    assert reasons.get("minItems") == 1
    assert reasons.get("uniqueItems") is True


def test_unmeasured_is_a_permitted_fail_reason_value() -> None:
    """The one place ``unmeasured`` legitimately appears: as a *value*.

    ``WAIVER_NAME_PATTERN`` bans it as a property *name*. The distinction is the
    whole point — the contract must be able to say "we could not measure", and
    must not be able to say "we waived it".
    """
    enum = dig(
        promoted(REPORT), ("properties", "fail_reasons", "items", "enum"), REPORT
    )
    assert "unmeasured" in enum


# --------------------------------------------------------------------------
# D3 mechanism 3 — no optional gate is authorable
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "pointer"),
    [
        (REPORT, ("$defs", "GateResult", "properties", "required")),
        (CORPUS, ("properties", "gates", "items", "properties", "required")),
    ],
    ids=["report", "corpus"],
)
def test_gate_required_flag_is_const_true(name: str, pointer: tuple[str, ...]) -> None:
    """"We didn't gate on that one" must not be expressible.

    ``{"const": true}`` rather than ``{"type": "boolean"}``: a boolean would let
    a run author an optional gate and then not run it.
    """
    schema = dig(promoted(name), pointer, name)
    assert schema == {"const": True} or schema.get("const") is True, (
        f"{name}{'/'.join(pointer)} is {schema!r}; it must be a const true."
    )
    assert "enum" not in schema, (
        f"{name} declares gates[].required as an enum, which could admit false."
    )


@pytest.mark.parametrize(
    ("name", "pointer"),
    [
        (REPORT, ("$defs", "GateResult", "required")),
        (CORPUS, ("properties", "gates", "items", "required")),
    ],
    ids=["report", "corpus"],
)
def test_gate_required_flag_is_itself_a_required_property(
    name: str, pointer: tuple[str, ...]
) -> None:
    """A ``const: true`` that may be omitted constrains nothing."""
    assert "required" in dig(promoted(name), pointer, name)


# --------------------------------------------------------------------------
# D3 mechanism 2 — the denominator is declared, not derived
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["cases_declared", "cases_scored"])
def test_corpus_block_requires_both_denominator_fields(field: str) -> None:
    """The composer needs two numbers to compare; one of them is not enough.

    This is the direct structural fix for the gen-eval failure mode of design D2,
    where an invalid scenario, a malformed file, a gather-exception, and an
    exhausted budget all vanished from the results without lowering the pass
    rate.
    """
    corpus = dig(promoted(REPORT), ("properties", "corpus"), REPORT)
    assert field in (corpus.get("required") or []), (
        f"{REPORT}'s corpus block does not require {field!r}."
    )
    assert field in corpus.get("properties", {}), (
        f"{REPORT}'s corpus block declares no {field!r} property."
    )


def test_steps_to_evidence_is_never_nullable() -> None:
    """A null read-cost would be a silent skip, which D3 forbids.

    When no rendered hit intersects labeled evidence the value is censored to
    ``max_files + 1`` (design D7), so the mean stays computable over every case.
    """
    schema = dig(
        promoted(REPORT),
        ("$defs", "ArmResult", "properties", "steps_to_evidence"),
        REPORT,
    )
    assert schema.get("type") == "integer", (
        f"steps_to_evidence declares type {schema.get('type')!r}; a union with "
        "'null' would let an unmeasured case drop out of the mean."
    )
    assert schema.get("minimum") == 1


def test_utility_applicable_is_a_required_boolean() -> None:
    """Declared absence is auditable; silent absence is not.

    ``quick-task`` has no declared read scope and therefore no utility slice. It
    must say so, in the contract, rather than simply having no cases.
    """
    consumer = dig(promoted(REPORT), ("$defs", "ConsumerResult"), REPORT)
    assert "utility_applicable" in (consumer.get("required") or [])
    assert consumer["properties"]["utility_applicable"].get("type") == "boolean"

    corpus_consumer = dig(
        promoted(CORPUS), ("properties", "consumers", "items"), CORPUS
    )
    assert "utility_applicable" in (corpus_consumer.get("required") or [])
    assert corpus_consumer["properties"]["utility_applicable"].get("type") == "boolean"


# --------------------------------------------------------------------------
# D3 mechanism 4 — there is no waiver field
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_no_waiver_shaped_property_name_exists(name: str) -> None:
    """Recursively: no field a machine could read as permission to not measure.

    The walk covers ``properties``, ``patternProperties``, ``$defs``,
    ``required``, and the dependent-keyword maps, at every depth including inside
    ``if``/``then``/``allOf``. It deliberately does *not* descend into ``enum``
    or ``const``, because ``fail_reasons`` legitimately contains the *value*
    ``unmeasured``.
    """
    offenders = [
        (pointer, field)
        for pointer, field in property_names(promoted(name))
        if WAIVER_NAME_PATTERN.search(field)
    ]
    assert not offenders, (
        f"{name} declares waiver-shaped field name(s): {offenders}. Design D3: "
        "an operator who thinks a threshold is wrong changes the threshold in "
        "the corpus manifest, which is a reviewable diff the corpus digest "
        "invalidates the existing report against."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_the_property_name_walk_is_not_vacuous(name: str) -> None:
    """A walk that finds nothing would make the test above always pass."""
    names = {field for _, field in property_names(promoted(name))}
    assert "schema_version" in names, (
        f"the property-name walk over {name} found {len(names)} names and not "
        "'schema_version'; it is not reaching the document."
    )


def test_the_waiver_detector_catches_a_waiver_field() -> None:
    """Mutation proof: the detector fails on a document that deserves it.

    Without this, a walk broken in some future refactor would report a clean bill
    of health for every schema, and the D3 guarantee would become decoration.
    """
    planted = {
        "type": "object",
        "properties": {
            "verdict": {"enum": ["pass", "fail"]},
            "waived_by": {"type": "string"},
        },
        "$defs": {
            "Nested": {
                "properties": {"skip_reason": {"type": "string"}},
                "required": ["skip_reason"],
            }
        },
    }
    caught = {field for _, field in property_names(planted) if WAIVER_NAME_PATTERN.search(field)}
    assert caught == {"waived_by", "skip_reason"}


def test_the_waiver_detector_ignores_enum_values() -> None:
    """The precision half of the same proof.

    A detector that flagged enum values would force ``fail_reasons`` to drop
    ``unmeasured`` — deleting the vocabulary for "could not measure", which is
    the exact outcome D3 needs the contract to be able to record.
    """
    planted = {
        "properties": {
            "fail_reasons": {
                "type": "array",
                "items": {"enum": ["unmeasured", "apparatus_failure"]},
            }
        }
    }
    caught = {field for _, field in property_names(planted) if WAIVER_NAME_PATTERN.search(field)}
    assert caught == set()


# --------------------------------------------------------------------------
# Closed enums: the README and the schema agree, and neither is retyped here
# --------------------------------------------------------------------------


def test_readme_declares_every_enum_this_module_locates() -> None:
    """The label table and the README prose describe the same set of enums.

    Derived both ways: a README paragraph with no ``ENUM_LOCATIONS`` entry is an
    enum nothing checks, and an entry with no paragraph is an undocumented enum.
    """
    declared = set(readme_declarations())
    assert declared == set(ENUM_LOCATIONS), (
        f"README declares {sorted(declared)}; ENUM_LOCATIONS covers "
        f"{sorted(ENUM_LOCATIONS)}."
    )


@pytest.mark.parametrize("label", sorted(ENUM_LOCATIONS))
def test_readme_enum_members_match_the_schema(label: str) -> None:
    """Member-for-member, with the expectation read out of the README.

    Retyping the lists here would create a third copy to keep in sync; the point
    is that the prose a reviewer reads and the schema a machine enforces are the
    same contract.
    """
    declarations = readme_declarations()
    if label not in declarations:
        pytest.fail(f"the README's closed-enum section does not declare `{label}`.")
    members, claimed_count = declarations[label]
    name, pointer = ENUM_LOCATIONS[label]
    enum = dig(promoted(name), pointer, name)

    assert set(members) == set(enum), (
        f"`{label}`: the README lists {sorted(members)}; {name} defines "
        f"{sorted(enum)}."
    )
    assert claimed_count == len(enum), (
        f"`{label}`: the README says {claimed_count} values; {name} defines "
        f"{len(enum)}: {enum}."
    )
    assert len(enum) == len(set(enum)), f"`{label}` has duplicate members: {enum}."
    assert len(members) == claimed_count, (
        f"`{label}`: the README lists {len(members)} members but claims "
        f"{claimed_count} values."
    )


# --------------------------------------------------------------------------
# Mirrored ri-12 enums (design D4) do not drift from their source
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source, targets in MIRRORED_RI12_ENUMS.items()
        for target in targets
    ],
    ids=[
        f"{'.'.join(source)}->{target[0]}"
        for source, targets in MIRRORED_RI12_ENUMS.items()
        for target in targets
    ],
)
def test_mirrored_ri12_enum_matches_its_source(
    source: tuple[str, ...], target: tuple[str, tuple[str, ...]]
) -> None:
    """ri-12's section schema is this harness's input contract, not a copy.

    These three vocabularies are duplicated rather than ``$ref``-ed because the
    report must validate with no registry and no network (the verification
    commands in ``work-packages.yaml`` construct a bare
    ``Draft202012Validator``). Duplication without a cross-check is drift, so the
    check lives here: widening ri-12's fallback vocabulary without widening the
    report's fails, instead of producing reports that cannot name what happened.
    """
    ri12 = _read(RI12_SECTION)
    expected = dig(ri12, source, RI12_SECTION.name)
    name, pointer = target
    actual = dig(promoted(name), pointer, name)
    assert set(actual) == set(expected), (
        f"{name}{'/'.join(pointer)} is {sorted(actual)}; ri-12's "
        f"{'/'.join(source)} is {sorted(expected)}."
    )
