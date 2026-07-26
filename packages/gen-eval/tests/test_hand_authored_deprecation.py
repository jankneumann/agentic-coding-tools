"""A descriptor that declares no contract is on the deprecated path (task 5.1).

Spec scenarios:
  - gen-eval-framework.service-and-tool-descriptor-archetypes
      · a hand-authored descriptor still loads

Design decisions: D6 (additive migration with a populated legacy field).

D6 chose not to cut over. ACA, agentic-assistant and the coordinator all read
the current shape, and a hard break would block on a coordinator OpenAPI
contract that does not exist yet. So the hand-authored descriptor keeps
loading, keeps producing the flat fields, and keeps working.

What it stops doing is doing so *silently*. The whole change rests on D1 — the
contract is the declared surface — and a descriptor with no ``contract:`` has
no source of truth behind its surface: whatever someone typed is what gets
measured, and drift between it and the implementation is undetectable by
construction. The warning is how a consumer learns their descriptor is in that
state before the removal that eventually follows.

The negative case carries the weight here. A warning that also fires on derived
descriptors trains everyone to filter it, which is worse than no warning: the
signal is gone and the noise remains.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
import yaml

from gen_eval.descriptor import ToolDescriptor, load_descriptor
from gen_eval.service_descriptor import ServiceDescriptor
from tests.test_service_descriptor import CONTRACT_PATH as SERVICE_CONTRACT
from tests.test_tool_descriptor import CONTRACT_PATH as CLI_CONTRACT


def write(tmp_path: Path, name: str, document: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    return path


def hand_authored_tool(tmp_path: Path) -> Path:
    """A tool descriptor someone typed out, with no contract behind it."""
    return write(
        tmp_path,
        "tool.yaml",
        {
            "project": "typed-by-hand",
            "version": "1",
            "executable": "typed-by-hand",
            "services": [],
            "commands": [
                {"name": "", "flags": [{"name": "--verbose", "type": "boolean"}]}
            ],
        },
    )


def hand_authored_flat(tmp_path: Path) -> Path:
    """The legacy shape: services, no archetype marker, no contract."""
    return write(
        tmp_path,
        "flat.yaml",
        {
            "project": "legacy",
            "version": "1",
            "services": [
                {
                    "name": "legacy-cli",
                    "type": "cli",
                    "command": "legacy",
                    "commands": [{"name": "run"}],
                }
            ],
        },
    )


def derived_tool(tmp_path: Path) -> Path:
    """A descriptor that names the contract it came from."""
    descriptor = ToolDescriptor.from_contract(CLI_CONTRACT)
    return write(tmp_path, "derived-tool.yaml", descriptor.model_dump(mode="json"))


def derived_service(tmp_path: Path) -> Path:
    descriptor = ServiceDescriptor.from_contract(SERVICE_CONTRACT)
    return write(tmp_path, "derived-service.yaml", descriptor.model_dump(mode="json"))


class TestTheHandAuthoredPathWarns:
    """No ``contract:`` means no source of truth behind the declared surface."""

    def test_a_hand_authored_tool_descriptor_warns(self, tmp_path: Path) -> None:
        with pytest.warns(DeprecationWarning):
            load_descriptor(hand_authored_tool(tmp_path))

    def test_a_legacy_flat_descriptor_warns(self, tmp_path: Path) -> None:
        with pytest.warns(DeprecationWarning):
            load_descriptor(hand_authored_flat(tmp_path))

    def test_the_message_names_the_file(self, tmp_path: Path) -> None:
        """A consumer with several descriptors needs to know which one."""
        path = hand_authored_tool(tmp_path)
        with pytest.warns(DeprecationWarning, match=path.name):
            load_descriptor(path)

    def test_the_message_names_the_field_to_add(self, tmp_path: Path) -> None:
        with pytest.warns(DeprecationWarning, match="contract"):
            load_descriptor(hand_authored_tool(tmp_path))

    def test_the_descriptor_still_loads_intact(self, tmp_path: Path) -> None:
        """D6 deprecates the path; it does not break it."""
        with pytest.warns(DeprecationWarning):
            descriptor = load_descriptor(hand_authored_tool(tmp_path))
        assert descriptor.all_interfaces() == ["cli:--verbose"]

    def test_the_legacy_descriptor_still_loads_intact(self, tmp_path: Path) -> None:
        with pytest.warns(DeprecationWarning):
            descriptor = load_descriptor(hand_authored_flat(tmp_path))
        assert descriptor.all_interfaces() == ["cli:run"]


class TestTheDerivedPathIsSilent:
    """A warning that fires on everything trains people to filter it."""

    def test_a_derived_tool_descriptor_does_not_warn(self, tmp_path: Path) -> None:
        path = derived_tool(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            assert load_descriptor(path).all_interfaces()

    def test_a_derived_service_descriptor_does_not_warn(self, tmp_path: Path) -> None:
        path = derived_service(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            assert load_descriptor(path).all_interfaces()


class TestTheWarningIsSuppressible:
    """Consumers mid-migration must be able to silence it deliberately."""

    def test_the_category_is_deprecationwarning(self, tmp_path: Path) -> None:
        """Not UserWarning — the category is how a filter targets it."""
        path = hand_authored_tool(tmp_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            load_descriptor(path)
        assert [w.category for w in caught] == [DeprecationWarning]

    def test_it_can_be_filtered_out(self, tmp_path: Path) -> None:
        path = hand_authored_tool(tmp_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("ignore", DeprecationWarning)
            load_descriptor(path)
        assert caught == []
