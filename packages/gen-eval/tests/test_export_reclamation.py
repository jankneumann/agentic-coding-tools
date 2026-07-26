"""``gen_eval.ServiceDescriptor`` denotes the archetype, not the element (task 5.8).

Spec scenarios:
  - gen-eval-framework.descriptor-reclamation-is-announced
      · a reclaimed name is announced rather than silently rebound

Design decisions: D6.

This is a **reclamation**, not a deprecation. Both names resolve successfully
while denoting something different from one release ago, and a deprecation
warning cannot express that: it says "this name is going away", when the truth
is "this name stayed and changed meaning". Code written against the old
meaning keeps importing, keeps type-checking, and starts being wrong.

The specific disagreement this closes: after the prerequisite rename,
``gen_eval.ServiceDescriptor`` resolved through the alias table to
``ServiceSpec`` — *one testable service* — while
``gen_eval.service_descriptor.ServiceDescriptor`` was the document archetype.
Two importable spellings of one name, denoting a container and one of its
elements, with a warning on the wrong one.

``ServiceDescriptor`` cannot be a module global in ``descriptor.py`` the way
``ToolDescriptor`` is: ``service_descriptor`` imports ``descriptor``, so a
top-level import there would cycle. It resolves lazily instead, which is the
same technique ``load_descriptor`` already uses. The tests below therefore
assert what the name *resolves to*, not where it is stored — the storage is an
artifact of the import graph and the meaning is what consumers depend on.
"""

from __future__ import annotations

import warnings

import pytest

import gen_eval
from gen_eval import descriptor as descriptor_module
from gen_eval import service_descriptor as service_module

#: package-level name -> the type it must now denote.
RECLAIMED_EXPORTS = {
    "ServiceDescriptor": service_module.ServiceDescriptor,
    "ToolDescriptor": descriptor_module.ToolDescriptor,
}

#: package-level name -> the element type it used to denote.
SUPERSEDED = {
    "ServiceDescriptor": "ServiceSpec",
    "ToolDescriptor": "McpToolSpec",
}


class TestTheReclaimedNamesDenoteTheArchetypes:
    @pytest.mark.parametrize(("name", "expected"), sorted(RECLAIMED_EXPORTS.items()))
    def test_the_package_export_is_the_archetype(self, name: str, expected: type) -> None:
        assert getattr(gen_eval, name) is expected

    @pytest.mark.parametrize("name", sorted(RECLAIMED_EXPORTS))
    def test_it_is_no_longer_the_element_type(self, name: str) -> None:
        """The failure this closes: the name resolving to one of its own parts."""
        superseded = getattr(descriptor_module, SUPERSEDED[name])
        assert getattr(gen_eval, name) is not superseded

    @pytest.mark.parametrize("name", sorted(RECLAIMED_EXPORTS))
    def test_it_is_in_dunder_all(self, name: str) -> None:
        """A live name for a current type belongs in ``import *``."""
        assert name in gen_eval.__all__

    @pytest.mark.parametrize("name", sorted(RECLAIMED_EXPORTS))
    def test_it_does_not_warn(self, name: str) -> None:
        """Not deprecated — a warning here would say the opposite of the truth."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            getattr(gen_eval, name)
        assert [str(w.message) for w in caught] == []

    @pytest.mark.parametrize("name", sorted(RECLAIMED_EXPORTS))
    def test_it_is_not_in_the_alias_table(self, name: str) -> None:
        """Aliasing a reclaimed name warns 'use X' while handing back not-X."""
        assert name not in descriptor_module._DEPRECATED_ALIASES


class TestTheModulePathsAgree:
    """Two spellings of one name must not denote different things."""

    def test_the_package_and_module_service_descriptor_agree(self) -> None:
        assert gen_eval.ServiceDescriptor is service_module.ServiceDescriptor

    def test_the_descriptor_module_no_longer_answers_with_the_element(self) -> None:
        """``descriptor.ServiceDescriptor`` resolved to ``ServiceSpec``."""
        resolved = getattr(descriptor_module, "ServiceDescriptor", None)
        assert resolved is not descriptor_module.ServiceSpec

    def test_the_package_and_module_tool_descriptor_agree(self) -> None:
        assert gen_eval.ToolDescriptor is descriptor_module.ToolDescriptor


class TestTheSupersededNamesSurvive:
    """Rule 4 — reclamation renames nothing; the element types keep their names."""

    @pytest.mark.parametrize("name", sorted(set(SUPERSEDED.values())))
    def test_the_element_type_is_still_exported(self, name: str) -> None:
        assert name in gen_eval.__all__
        assert getattr(gen_eval, name) is getattr(descriptor_module, name)

    def test_the_archetype_and_the_element_are_distinct_types(self) -> None:
        assert gen_eval.ServiceDescriptor is not gen_eval.ServiceSpec
        assert gen_eval.ToolDescriptor is not gen_eval.McpToolSpec

    def test_the_remaining_aliases_still_warn(self) -> None:
        """The genuine deprecations are untouched by the reclamation."""
        assert descriptor_module._DEPRECATED_ALIASES
        for old_name in descriptor_module._DEPRECATED_ALIASES:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                getattr(descriptor_module, old_name)
            assert caught, f"{old_name} resolved without a DeprecationWarning"
