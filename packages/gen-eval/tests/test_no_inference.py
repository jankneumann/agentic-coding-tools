"""No citation is ever inferred (task 2.3) — the load-bearing negative.

Spec scenarios:
  - Contracted Operations Cite The Requirements They Serve
      · an operation declares its citations

Design decisions: D1.

Give an operation (or a CLI flag) a name and path that match a requirement
heading almost exactly and assert it still cites nothing. Without this test,
a later "helpful" fuzzy matcher lands with every other test still green — it
is the one change that would silently make the whole gate worthless.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from gen_eval.descriptor import FlagSpec
from gen_eval.service_descriptor import ServiceDescriptor


def test_an_operation_matching_a_requirement_heading_almost_exactly_cites_nothing(
    tmp_path: Path,
) -> None:
    """Real requirement: agent-coordinator "File Locking" —
    "The system SHALL provide exclusive file locking to prevent merge
    conflicts...". An operation whose id, path and summary echo that
    heading almost word for word must still parse with no traceability,
    because nothing declared one.
    """
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "agent-coordinator", "version": "1"},
        "paths": {
            "/locks/file-locking": {
                "post": {
                    "operationId": "file_locking",
                    "summary": "File Locking",
                    "description": (
                        "Provide exclusive file locking to prevent merge conflicts "
                        "when multiple agents edit files concurrently."
                    ),
                }
            }
        },
    }
    contract = tmp_path / "agent-coordinator.yaml"
    contract.write_text(yaml.safe_dump(doc), encoding="utf-8")
    descriptor = ServiceDescriptor.from_contract(contract)
    operation = descriptor.operation("file_locking")

    assert operation.traceability is None, (
        "an operation whose name/path/summary nearly duplicate a real "
        "requirement heading must still cite nothing — D1 forbids inference "
        "from names, paths, or prose similarity"
    )


def test_a_flag_matching_a_requirement_heading_almost_exactly_cites_nothing() -> None:
    """Same principle, CLI archetype. Real requirement:
    gen-eval-framework "Requirement identifiers are stable and fail closed"
    (this very change's own delta) — a flag echoing that title must not
    acquire a citation from the name alone.
    """
    flag = FlagSpec(
        name="--requirement-identifiers-are-stable",
        type="boolean",
        description="Requirement identifiers are stable and fail closed.",
    )
    assert flag.traceability is None


def test_operation_id_matching_capability_dot_slug_pattern_cites_nothing(
    tmp_path: Path,
) -> None:
    """Belt and suspenders: even an operationId that IS a well-formed
    citation string (`<capability>.<slug>`) must not be treated as one —
    the only route to a citation is an explicit `x-traceability` block.
    """
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "widget", "version": "1"},
        "paths": {
            "/widgets": {
                "get": {
                    "operationId": "widget-capability.list-widgets",
                }
            }
        },
    }
    contract = tmp_path / "widget.yaml"
    contract.write_text(yaml.safe_dump(doc), encoding="utf-8")
    descriptor = ServiceDescriptor.from_contract(contract)
    operation = descriptor.operation("widget-capability.list-widgets")
    assert operation.traceability is None
