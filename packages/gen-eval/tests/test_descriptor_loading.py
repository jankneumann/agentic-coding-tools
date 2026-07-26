"""The runtime must load a derived descriptor AS its archetype.

Round-7 review, blocking finding (codex-001 / grok-1, confirmed by direct
execution). ``__main__`` loaded every descriptor with
``InterfaceDescriptor.from_yaml()``. Pydantic drops fields the model does not
declare, so ``ServiceDescriptor.operations`` and
``ToolDescriptor.commands``/``executable``/``contract`` were discarded at the
one seam that matters — the CLI path. The same generated file yielded 17
interfaces as a ``ToolDescriptor`` and 0 as the base model.

No unit test could see this, because every other test constructs its descriptor
by calling the derived class directly. The defect lived exclusively in the
loader, and the loader had no test.

These tests are written against ``load_descriptor``, the archetype-aware entry
point. They assert the *observable* consequence — the declared surface and the
coverage path — rather than the returned type alone, because returning the
right class while losing the fields would satisfy a type assertion and still
ship the defect.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from gen_eval.descriptor import InterfaceDescriptor, ToolDescriptor
from gen_eval.reports import build_operation_coverage
from gen_eval.service_descriptor import ServiceDescriptor

from tests.test_service_descriptor import CONTRACT_PATH as SERVICE_CONTRACT
from tests.test_tool_descriptor import CONTRACT_PATH as CLI_CONTRACT

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _load_descriptor() -> Any:
    """Import the loader under test, failing loudly while task 4.9 is open."""
    try:
        from gen_eval.descriptor import load_descriptor
    except ImportError:  # pragma: no cover - the RED state
        pytest.fail(
            "gen_eval.descriptor.load_descriptor does not exist — task 4.9 "
            "implements archetype-aware loading"
        )
    return load_descriptor


def generate_tool_descriptor(tmp_path: Path) -> Path:
    """Run the real generator, so the fixture is the artifact users get."""
    out = tmp_path / "tool-descriptor.yaml"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE_ROOT / "scripts" / "generate_tool_descriptor.py"),
            "--contract",
            str(CLI_CONTRACT),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"generate_tool_descriptor.py failed: {result.stderr}")
    return out


def write_service_descriptor(tmp_path: Path) -> Path:
    """Derive a service descriptor and round-trip it through YAML."""
    descriptor = ServiceDescriptor.from_contract(SERVICE_CONTRACT)
    out = tmp_path / "service-descriptor.yaml"
    out.write_text(yaml.safe_dump(descriptor.model_dump(mode="json")))
    return out


class TestToolDescriptorSurvivesTheLoader:
    """A derived tool descriptor must not lose its commands on load."""

    def test_the_loader_returns_the_tool_archetype(self, tmp_path: Path) -> None:
        path = generate_tool_descriptor(tmp_path)
        assert isinstance(_load_descriptor()(path), ToolDescriptor)

    def test_the_declared_surface_matches_the_direct_load(self, tmp_path: Path) -> None:
        """The exact defect: 17 as a ToolDescriptor, 0 as the base model."""
        path = generate_tool_descriptor(tmp_path)
        direct = ToolDescriptor.from_yaml(path)
        loaded = _load_descriptor()(path)
        assert sorted(loaded.all_interfaces()) == sorted(direct.all_interfaces())

    def test_the_declared_surface_is_not_empty(self, tmp_path: Path) -> None:
        """A vacuous surface reports full coverage of nothing (D3)."""
        loaded = _load_descriptor()(generate_tool_descriptor(tmp_path))
        assert loaded.all_interfaces(), (
            "a derived tool descriptor loaded to an empty declared surface — "
            "the base model discarded `commands`"
        )

    def test_the_contract_reference_survives(self, tmp_path: Path) -> None:
        """5.2 warns when a descriptor declares no contract; it must see one."""
        loaded = _load_descriptor()(generate_tool_descriptor(tmp_path))
        assert getattr(loaded, "contract", None) is not None

    def test_the_executable_survives(self, tmp_path: Path) -> None:
        loaded = _load_descriptor()(generate_tool_descriptor(tmp_path))
        assert getattr(loaded, "executable", None)


class TestServiceDescriptorSurvivesTheLoader:
    """A derived service descriptor must keep the operation model (D4)."""

    def test_the_loader_returns_the_service_archetype(self, tmp_path: Path) -> None:
        path = write_service_descriptor(tmp_path)
        assert isinstance(_load_descriptor()(path), ServiceDescriptor)

    def test_operations_survive(self, tmp_path: Path) -> None:
        path = write_service_descriptor(tmp_path)
        loaded = _load_descriptor()(path)
        assert getattr(loaded, "operations", None), (
            "the loaded descriptor has no operations — build_operation_coverage "
            "will take the _from_element fallback and D4 never engages"
        )

    def test_coverage_takes_the_operation_path_not_the_fallback(
        self, tmp_path: Path
    ) -> None:
        """The consequence, not the field.

        With operations present, coverage is keyed on the operation, so the
        number of coverage records equals the number of operations. Under the
        ``_from_element`` fallback it equals the number of *elements*, which is
        larger for any operation published on more than one surface.
        """
        path = write_service_descriptor(tmp_path)
        loaded = _load_descriptor()(path)
        coverage = build_operation_coverage(loaded, set())
        assert len(coverage) == len(loaded.operations)

    def test_fan_in_is_preserved(self, tmp_path: Path) -> None:
        """One MCP element serving two operations must still cover both (D7)."""
        path = write_service_descriptor(tmp_path)
        loaded = _load_descriptor()(path)
        direct = ServiceDescriptor.from_contract(SERVICE_CONTRACT)
        assert sorted(op.operation_id for op in loaded.operations) == sorted(
            op.operation_id for op in direct.operations
        )


class TestHandAuthoredDescriptorsStillLoad:
    """Rule 4 — the loader must not change behaviour for existing files."""

    def test_a_descriptor_with_no_archetype_marker_loads_as_the_base(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "hand-authored.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "project": "legacy",
                    "version": "1.0.0",
                    "services": [
                        {
                            "name": "api",
                            "type": "http",
                            "base_url": "http://localhost:8000",
                            "endpoints": [{"method": "GET", "path": "/health"}],
                        }
                    ],
                }
            )
        )
        loaded = _load_descriptor()(path)
        assert type(loaded) is InterfaceDescriptor
        assert loaded.all_interfaces() == ["GET /health"]

    def test_the_real_dogfood_descriptor_still_loads(self) -> None:
        """`evaluation/descriptor.yaml` is hand-authored until task 5.3."""
        path = PACKAGE_ROOT / "evaluation" / "descriptor.yaml"
        if not path.is_file():
            pytest.skip("dogfood descriptor not present")
        assert _load_descriptor()(path) is not None


class TestTheRuntimeEntrypointUsesTheLoader:
    """The defect was in __main__, so __main__ is what must change."""

    def test_main_does_not_load_through_the_base_model(self) -> None:
        source = (PACKAGE_ROOT / "src" / "gen_eval" / "__main__.py").read_text()
        assert "InterfaceDescriptor.from_yaml(" not in source, (
            "__main__ still loads through the base model — every derived "
            "descriptor silently loses the fields that make it derived"
        )

    def test_main_calls_the_archetype_aware_loader(self) -> None:
        source = (PACKAGE_ROOT / "src" / "gen_eval" / "__main__.py").read_text()
        assert "load_descriptor(" in source
