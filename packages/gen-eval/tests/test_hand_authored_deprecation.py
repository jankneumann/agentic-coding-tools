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


class TestDeclaringAContractIsAClaim:
    """Round-8 M1/M2: the key's presence is what silences the warning.

    The warning above fires on falsy ``contract``. So the two cheapest ways to
    look migrated without being migrated are to point ``contract:`` at nothing,
    or to declare it on a document with no archetype marker — where pydantic's
    ``extra: ignore`` then discards ``contract`` itself. Both leave the surface
    as whatever was typed, with the warning silent: strictly worse than not
    declaring one, because the signal is gone AND the state is unchanged.

    Both now raise. Note what is NOT asserted here: that the contract's
    contents match the descriptor. That is the subset verifier's job. This only
    establishes that a declared source of truth exists and was dispatched on.
    """

    def test_an_unresolvable_contract_path_raises(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            "tool.yaml",
            {
                "project": "claims-a-contract",
                "version": "1",
                "contract": "does-not-exist.yaml",
                "executable": "claims-a-contract",
                "services": [],
                "commands": [
                    {"name": "", "flags": [{"name": "--a", "type": "boolean"}]}
                ],
            },
        )
        with pytest.raises(ValueError, match="does not resolve to a readable file"):
            load_descriptor(path)

    def test_the_message_names_the_path_it_looked_at(self, tmp_path: Path) -> None:
        """Relative paths resolve against the descriptor, not the cwd."""
        path = write(
            tmp_path,
            "tool.yaml",
            {
                "project": "claims-a-contract",
                "version": "1",
                "contract": "sub/dir/contract.yaml",
                "executable": "x",
                "services": [],
                "commands": [],
            },
        )
        with pytest.raises(ValueError) as excinfo:
            load_descriptor(path)
        assert str(tmp_path / "sub" / "dir" / "contract.yaml") in str(excinfo.value)

    def test_a_contract_with_no_archetype_marker_raises(self, tmp_path: Path) -> None:
        """The narrow shape of round-7's blocker.

        Previously this loaded on the base model, silently dropping
        ``contract`` and every derived field, and failed three layers later
        with "no scenarios were evaluated" — which sends the reader to the
        scenario directory instead of the descriptor.
        """
        contract = tmp_path / "contract.yaml"
        contract.write_text("openapi: 3.1.0\n")
        path = write(
            tmp_path,
            "markerless.yaml",
            {
                "project": "markerless",
                "version": "1",
                "contract": "contract.yaml",
                "services": [
                    {"name": "s", "type": "cli", "command": "x", "commands": []}
                ],
            },
        )
        with pytest.raises(ValueError, match="no recognisable archetype payload"):
            load_descriptor(path)

    def test_an_empty_operations_list_is_not_a_marker(self, tmp_path: Path) -> None:
        """``operations: []`` is falsy, so it fell through to the base model."""
        contract = tmp_path / "contract.yaml"
        contract.write_text("openapi: 3.1.0\n")
        path = write(
            tmp_path,
            "empty-ops.yaml",
            {
                "project": "empty-ops",
                "version": "1",
                "contract": "contract.yaml",
                "operations": [],
                "services": [],
            },
        )
        with pytest.raises(ValueError, match="no recognisable archetype payload"):
            load_descriptor(path)

    def test_a_descriptor_without_a_contract_is_untouched(
        self, tmp_path: Path
    ) -> None:
        """Rule 4. Every refusal above is gated on ``contract:`` being set.

        The legacy flat shape declares none, so it still loads, still warns,
        and still produces its flat fields — the D6 promise this change made
        to ACA and the coordinator.
        """
        path = hand_authored_flat(tmp_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            descriptor = load_descriptor(path)
        assert descriptor.project == "legacy"
        assert [w.category for w in caught] == [DeprecationWarning]

    def test_a_resolvable_contract_still_loads(self, tmp_path: Path) -> None:
        """The happy path is unaffected — proven on a real derived descriptor."""
        path = derived_tool(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            assert load_descriptor(path).all_interfaces()
