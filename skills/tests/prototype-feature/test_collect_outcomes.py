"""Unit tests for collect_outcomes.

Covered tasks:
  4.5 — prototype-findings.md production: schema conformance,
        human-picks recorded.

Spec scenarios:
- skill-workflow.PrototypeFindingsArtifact.findings-artifact-produced
- skill-workflow.PrototypeFindingsArtifact.human-pick-and-choose
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "prototype-feature"
    / "scripts"
)
PARALLEL_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "parallel-infrastructure"
    / "scripts"
)
for p in (PARALLEL_SCRIPTS, SKILL_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from collect_outcomes import (
    build_descriptor,
    render_findings_markdown,
    write_findings_file,
)
from variant_descriptor import VariantDescriptor

CHANGE_DIR = (
    Path(__file__).resolve().parents[3]
    / "openspec"
    / "changes"
    / "add-prototyping-stage"
)
SCHEMA_DIR = CHANGE_DIR / "contracts" / "schemas"


@pytest.fixture(scope="module")
def variant_descriptor_schema() -> dict:
    return json.loads(
        (SCHEMA_DIR / "variant-descriptor.schema.json").read_text()
    )


def _scoring_payload(passed: bool = True, covered: int = 5, total: int = 5) -> dict:
    """Stand-in for a /validate-feature smoke+spec result."""
    return {
        "smoke": {"pass": passed, "report": "scoring stub"},
        "spec": {
            "covered": covered,
            "total": total,
            "missing": [] if covered == total else ["scenario-3"],
        },
    }


class TestBuildDescriptor:
    """build_descriptor combines plan + scoring + human picks into a VariantDescriptor."""

    def test_builds_with_full_inputs(
        self, variant_descriptor_schema: dict
    ) -> None:
        descriptor = build_descriptor(
            variant_id="v1",
            angle="simplest",
            vendor="claude-opus-4-7",
            change_id="add-foo",
            scoring=_scoring_payload(),
            human_picks={
                "data_model": True,
                "api": False,
                "tests": True,
                "layout": False,
            },
            vendor_fallback=False,
            synthesis_hint="prefer this data model",
        )
        assert isinstance(descriptor, VariantDescriptor)
        # Schema-validate the dict form to catch any drift between the
        # builder and the published schema.
        jsonschema.validate(descriptor.to_dict(), variant_descriptor_schema)

    def test_branch_derived_from_change_and_variant(self) -> None:
        descriptor = build_descriptor(
            variant_id="v2",
            angle="extensible",
            vendor="codex",
            change_id="add-foo",
            scoring=_scoring_payload(),
            human_picks={
                "data_model": False,
                "api": True,
                "tests": False,
                "layout": False,
            },
        )
        assert descriptor.branch == "prototype/add-foo/v2"

    def test_smoke_failure_recorded_not_raised(
        self, variant_descriptor_schema: dict
    ) -> None:
        # Spec: VariantScoring.skeleton-fails-to-deploy — failure is data,
        # not an exception.
        descriptor = build_descriptor(
            variant_id="v1",
            angle="simplest",
            vendor="claude-opus-4-7",
            change_id="add-foo",
            scoring=_scoring_payload(passed=False, covered=2, total=5),
            human_picks={
                "data_model": True,
                "api": False,
                "tests": False,
                "layout": False,
            },
        )
        assert descriptor.automated_scores.smoke_pass is False
        jsonschema.validate(descriptor.to_dict(), variant_descriptor_schema)


class TestFindingsMarkdownRendering:
    """render_findings_markdown produces a single readable doc."""

    def test_includes_one_section_per_variant(self) -> None:
        descriptors = [
            build_descriptor(
                variant_id="v1",
                angle="simplest",
                vendor="claude-opus-4-7",
                change_id="add-foo",
                scoring=_scoring_payload(),
                human_picks={
                    "data_model": True,
                    "api": False,
                    "tests": True,
                    "layout": False,
                },
            ),
            build_descriptor(
                variant_id="v2",
                angle="extensible",
                vendor="codex",
                change_id="add-foo",
                scoring=_scoring_payload(covered=4),
                human_picks={
                    "data_model": False,
                    "api": True,
                    "tests": False,
                    "layout": True,
                },
            ),
        ]
        markdown = render_findings_markdown(
            change_id="add-foo", descriptors=descriptors
        )
        assert "# Prototype Findings — add-foo" in markdown
        # Each variant gets a section
        assert "## Variant v1" in markdown
        assert "## Variant v2" in markdown
        # Vendor is captured in the section
        assert "claude-opus-4-7" in markdown
        assert "codex" in markdown


class TestWriteFindingsFile:
    """write_findings_file persists prototype-findings.md to the change dir."""

    def test_writes_file_to_change_directory(
        self, tmp_path: Path, variant_descriptor_schema: dict
    ) -> None:
        change_dir = tmp_path / "openspec" / "changes" / "add-foo"
        change_dir.mkdir(parents=True)

        descriptors = [
            build_descriptor(
                variant_id="v1",
                angle="simplest",
                vendor="claude-opus-4-7",
                change_id="add-foo",
                scoring=_scoring_payload(),
                human_picks={
                    "data_model": True,
                    "api": False,
                    "tests": False,
                    "layout": False,
                },
            ),
        ]

        write_findings_file(change_dir=change_dir, descriptors=descriptors)
        out = change_dir / "prototype-findings.md"
        assert out.is_file()
        content = out.read_text()
        assert "# Prototype Findings" in content

    def test_descriptors_serialize_to_schema_compliant_json_block(
        self,
        tmp_path: Path,
        variant_descriptor_schema: dict,
    ) -> None:
        # The findings file embeds the structured VariantDescriptor JSON
        # so iterate-on-plan can parse it programmatically. Each block
        # must validate against the schema.
        change_dir = tmp_path / "openspec" / "changes" / "add-foo"
        change_dir.mkdir(parents=True)

        descriptors = [
            build_descriptor(
                variant_id="v1",
                angle="simplest",
                vendor="claude-opus-4-7",
                change_id="add-foo",
                scoring=_scoring_payload(),
                human_picks={
                    "data_model": True,
                    "api": False,
                    "tests": False,
                    "layout": False,
                },
            ),
        ]
        write_findings_file(change_dir=change_dir, descriptors=descriptors)
        content = (change_dir / "prototype-findings.md").read_text()

        # Extract JSON blocks and validate each.
        in_block = False
        block_lines: list[str] = []
        block_count = 0
        for line in content.splitlines():
            if line.strip() == "```json":
                in_block = True
                block_lines = []
                continue
            if line.strip() == "```" and in_block:
                payload = json.loads("\n".join(block_lines))
                jsonschema.validate(payload, variant_descriptor_schema)
                in_block = False
                block_count += 1
                continue
            if in_block:
                block_lines.append(line)
        assert block_count == len(descriptors), (
            f"expected {len(descriptors)} JSON blocks, found {block_count}"
        )
