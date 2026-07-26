"""Naming-level invariants and deprecation aliases for the descriptor models.

Spec scenarios:
  - gen-eval-framework.element-and-document-types-are-distinguishable-by-name
  - gen-eval-framework.a-renamed-element-type-is-reachable-under-its-new-name
  - gen-eval-framework.an-old-name-still-resolves-and-warns
  - gen-eval-framework.an-alias-that-does-not-warn-fails-the-gate

Design decisions: D1, D2, D4

This is the ONE test module permitted to reference the pre-rename names — it
exists to test them. Every other test file is scanned by a verification gate
that fails on any pre-rename name, and the suite is additionally run under
``-W error::DeprecationWarning`` with this file excluded. Both exclusions are
what make those gates satisfiable rather than self-contradictory.
"""

from __future__ import annotations

import warnings

import pytest
from pydantic import BaseModel

import gen_eval
from gen_eval import descriptor as descriptor_module

#: old name -> the renamed type it must alias.
ALIASES: dict[str, str] = {
    "EndpointDescriptor": "EndpointSpec",
    "ToolDescriptor": "McpToolSpec",
    "CommandDescriptor": "CommandSpec",
    "ServiceDescriptor": "ServiceSpec",
}

#: renamed type -> a field it carried before the rename. Asserting a *specific*
#: field rather than "some fields" is what distinguishes a real rename from a
#: fresh empty class that merely occupies the new name.
PRE_RENAME_FIELDS: dict[str, str] = {
    "EndpointSpec": "path",
    "McpToolSpec": "input_schema",
    "CommandSpec": "subcommands",
    "ServiceSpec": "endpoints",
}


class TestNewNames:
    """D1 — the renamed types are reachable and intact."""

    @pytest.mark.parametrize("new_name", sorted(ALIASES.values()))
    def test_reachable_on_the_defining_module(self, new_name: str) -> None:
        assert isinstance(getattr(descriptor_module, new_name), type)

    @pytest.mark.parametrize("new_name", sorted(ALIASES.values()))
    def test_reachable_on_the_package(self, new_name: str) -> None:
        """Consumers import from ``gen_eval``, not ``gen_eval.descriptor``."""
        assert getattr(gen_eval, new_name) is getattr(descriptor_module, new_name)

    @pytest.mark.parametrize("new_name", sorted(ALIASES.values()))
    def test_is_exported(self, new_name: str) -> None:
        assert new_name in gen_eval.__all__

    @pytest.mark.parametrize(("new_name", "field"), sorted(PRE_RENAME_FIELDS.items()))
    def test_carries_its_pre_rename_field(self, new_name: str, field: str) -> None:
        model = getattr(descriptor_module, new_name)
        assert field in model.model_fields

    def test_accessing_a_new_name_does_not_warn(self) -> None:
        """The replacements are not themselves deprecated.

        Without this, an implementation that warns on *every* attribute access
        would satisfy the alias tests below while making the package unusable
        under ``-W error::DeprecationWarning``.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for new_name in ALIASES.values():
                getattr(gen_eval, new_name)
                getattr(descriptor_module, new_name)
        assert [str(w.message) for w in caught] == []


class TestDeprecationAliases:
    """D4 — each alias must resolve AND warn. Both halves, every time."""

    @pytest.mark.parametrize(("old_name", "new_name"), sorted(ALIASES.items()))
    def test_alias_resolves_to_the_renamed_type(self, old_name: str, new_name: str) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            aliased = getattr(descriptor_module, old_name)
        assert aliased is getattr(descriptor_module, new_name)

    @pytest.mark.parametrize("old_name", sorted(ALIASES))
    def test_alias_resolves_on_the_package_too(self, old_name: str) -> None:
        """``ServiceDescriptor`` was a package-level export; all four must be."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert getattr(gen_eval, old_name) is getattr(descriptor_module, old_name)

    @pytest.mark.parametrize(("old_name", "new_name"), sorted(ALIASES.items()))
    def test_alias_warns_and_names_the_replacement(self, old_name: str, new_name: str) -> None:
        """The spec requires the warning to name the replacement, not just fire.

        A bare "deprecated" warning leaves the consumer to guess what to migrate
        to, which is the entire value of warning rather than removing.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            getattr(descriptor_module, old_name)

        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecations, f"{old_name} resolved without a DeprecationWarning"
        message = str(deprecations[0].message)
        assert old_name in message
        assert new_name in message

    @pytest.mark.parametrize("old_name", sorted(ALIASES))
    def test_alias_warns_on_the_package_too(self, old_name: str) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            getattr(gen_eval, old_name)
        assert any(issubclass(w.category, DeprecationWarning) for w in caught), (
            f"gen_eval.{old_name} resolved without a DeprecationWarning"
        )

    @pytest.mark.parametrize("old_name", sorted(ALIASES))
    def test_alias_warns_on_every_access_not_just_the_first(self, old_name: str) -> None:
        """An implementation that caches the alias into the module dict warns once.

        The second consumer to touch the name then gets silence, which defeats
        the deprecation. Access twice and require two warnings.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            getattr(descriptor_module, old_name)
            getattr(descriptor_module, old_name)
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecations) == 2, (
            f"{old_name} warned {len(deprecations)}x across 2 accesses — "
            "the alias is being cached into the module namespace"
        )

    @pytest.mark.parametrize("old_name", sorted(ALIASES))
    def test_alias_is_not_advertised_for_new_use(self, old_name: str) -> None:
        """Deprecated names stay importable but leave ``__all__``.

        ``from gen_eval import *`` should hand a new consumer only names that
        are not on their way out.
        """
        assert old_name not in gen_eval.__all__

    def test_an_unknown_attribute_still_raises_attribute_error(self) -> None:
        """The alias hook must not swallow genuine typos into a warning."""
        with pytest.raises(AttributeError):
            descriptor_module.NoSuchDescriptor  # type: ignore[attr-defined]
        with pytest.raises(AttributeError):
            gen_eval.NoSuchDescriptor  # type: ignore[attr-defined]


class TestNamingLevels:
    """D1 — no single suffix denotes both an element and a document."""

    @staticmethod
    def _defined_models() -> dict[str, type[BaseModel]]:
        """Models *defined* in the module, excluding lazily-resolved aliases.

        Reading ``vars()`` rather than ``dir()``/``getmembers`` is deliberate:
        PEP 562 aliases are not in the module dict, so this sees the real
        declarations and cannot be fooled by a back-compat shim.
        """
        return {
            name: obj
            for name, obj in vars(descriptor_module).items()
            if isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj.__module__ == descriptor_module.__name__
        }

    def test_descriptor_suffix_names_only_the_document(self) -> None:
        named = {n for n in self._defined_models() if n.endswith("Descriptor")}
        assert named == {"InterfaceDescriptor"}, (
            f"'Descriptor' must denote the document level only; also found: "
            f"{sorted(named - {'InterfaceDescriptor'})}"
        )

    def test_every_element_and_container_type_uses_the_spec_suffix(self) -> None:
        defined = self._defined_models()
        for new_name in ALIASES.values():
            assert new_name in defined, f"{new_name} is not defined in descriptor.py"
            assert new_name.endswith("Spec")

    def test_the_document_type_composes_the_spec_types(self) -> None:
        """The level split must hold in the model graph, not only in the names."""
        assert "services" in descriptor_module.InterfaceDescriptor.model_fields
        service_spec = descriptor_module.ServiceSpec
        for field in ("endpoints", "tools", "commands"):
            assert field in service_spec.model_fields
