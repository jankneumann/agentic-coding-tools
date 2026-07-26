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

A **reclaimed** name is outside that rule. Once a name denotes a current type
rather than a superseded one, using it is not a migration debt, so other
modules may spell it freely — ``ToolDescriptor`` in ``test_tool_descriptor.py``
is the first case. ``RECLAIMED`` below is the list; anything still in
``ALIASES`` remains confined to this file.
"""

from __future__ import annotations

import json
import warnings

import pytest
from pydantic import BaseModel

import gen_eval
from gen_eval import descriptor as descriptor_module
from gen_eval.contracts import load_schema

#: old name -> the type it was renamed to. All four renames, whether or not
#: the old name has since been reclaimed — the schema-level facts below hold
#: either way.
RENAMED: dict[str, str] = {
    "EndpointDescriptor": "EndpointSpec",
    "ToolDescriptor": "McpToolSpec",
    "CommandDescriptor": "CommandSpec",
    "ServiceDescriptor": "ServiceSpec",
}

#: Old names that no longer alias anything, because a *new* type has taken
#: them. ``ToolDescriptor`` is now the document-level tool archetype rather
#: than one MCP tool. A reclaimed name resolves successfully while meaning
#: something different from one release ago, which a deprecation warning
#: cannot express — hence the separate expectations in
#: :class:`TestReclaimedNames`.
RECLAIMED: frozenset[str] = frozenset({"ToolDescriptor"})

#: old name -> the renamed type it must still alias.
ALIASES: dict[str, str] = {k: v for k, v in RENAMED.items() if k not in RECLAIMED}

#: Every model in ``descriptor.py`` allowed to carry the ``Descriptor``
#: suffix. The suffix denotes the *document* level; these are documents.
DOCUMENT_TYPES: frozenset[str] = frozenset({"InterfaceDescriptor", "ToolDescriptor"})

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

    @pytest.mark.parametrize("new_name", sorted(RENAMED.values()))
    def test_reachable_on_the_defining_module(self, new_name: str) -> None:
        assert isinstance(getattr(descriptor_module, new_name), type)

    @pytest.mark.parametrize("new_name", sorted(RENAMED.values()))
    def test_reachable_on_the_package(self, new_name: str) -> None:
        """Consumers import from ``gen_eval``, not ``gen_eval.descriptor``."""
        assert getattr(gen_eval, new_name) is getattr(descriptor_module, new_name)

    @pytest.mark.parametrize("new_name", sorted(RENAMED.values()))
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
            for new_name in RENAMED.values():
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


class TestReclaimedNames:
    """A reclaimed name denotes the new type, and says so by not warning.

    Leaving a reclaimed name in the alias table would be worse than either
    outcome on its own: the module would warn "use McpToolSpec instead" while
    handing back something that is not McpToolSpec.
    """

    @pytest.mark.parametrize("old_name", sorted(RECLAIMED))
    def test_is_defined_rather_than_aliased(self, old_name: str) -> None:
        assert old_name not in descriptor_module._DEPRECATED_ALIASES
        assert old_name in vars(descriptor_module), (
            f"{old_name} is neither aliased nor defined — it resolves to nothing"
        )

    @pytest.mark.parametrize("old_name", sorted(RECLAIMED))
    def test_no_longer_resolves_to_the_type_it_used_to_alias(self, old_name: str) -> None:
        superseded = getattr(descriptor_module, RENAMED[old_name])
        assert getattr(descriptor_module, old_name) is not superseded

    @pytest.mark.parametrize("old_name", sorted(RECLAIMED))
    def test_does_not_warn(self, old_name: str) -> None:
        """It is not deprecated — it is a live name for a current type."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            getattr(descriptor_module, old_name)
        assert [str(w.message) for w in caught] == []


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

    def test_descriptor_suffix_names_only_documents(self) -> None:
        """The suffix marks the document level — and only the document level.

        ``ToolDescriptor`` joins the set as a document archetype, not as a
        loosening: it describes a whole tool, the way ``InterfaceDescriptor``
        describes a whole project. An *element* type taking the suffix (one
        endpoint, one MCP tool, one command) is still the failure this guards.
        """
        named = {n for n in self._defined_models() if n.endswith("Descriptor")}
        assert named == DOCUMENT_TYPES, (
            f"'Descriptor' must denote the document level only; unexpected: "
            f"{sorted(named - DOCUMENT_TYPES)}; missing: {sorted(DOCUMENT_TYPES - named)}"
        )

    def test_every_element_and_container_type_uses_the_spec_suffix(self) -> None:
        defined = self._defined_models()
        for new_name in RENAMED.values():
            assert new_name in defined, f"{new_name} is not defined in descriptor.py"
            assert new_name.endswith("Spec")

    def test_the_document_type_composes_the_spec_types(self) -> None:
        """The level split must hold in the model graph, not only in the names."""
        assert "services" in descriptor_module.InterfaceDescriptor.model_fields
        service_spec = descriptor_module.ServiceSpec
        for field in ("endpoints", "tools", "commands"):
            assert field in service_spec.model_fields


class TestPublishedSchemaNaming:
    """The rename must reach the published schema, not stop at the Python names.

    These live here rather than in ``test_contract_schemas.py`` because they
    must spell the pre-rename names in order to assert their absence, and every
    test file except this one is scanned by a gate that fails on those literals.
    """

    @staticmethod
    def _descriptor_defs() -> dict[str, dict]:
        defs: dict[str, dict] = load_schema("interface-descriptor")["$defs"]
        return defs

    @pytest.mark.parametrize("new_name", sorted(RENAMED.values()))
    def test_defs_use_the_new_names(self, new_name: str) -> None:
        assert new_name in self._descriptor_defs()

    @pytest.mark.parametrize("old_name", sorted(RENAMED))
    def test_defs_do_not_use_the_pre_rename_names(self, old_name: str) -> None:
        assert old_name not in self._descriptor_defs()

    @pytest.mark.parametrize(("old_name", "new_name"), sorted(RENAMED.items()))
    def test_def_titles_follow_the_key(self, old_name: str, new_name: str) -> None:
        """pydantic writes both a ``$defs`` key and a ``title``; both must move.

        A stale title is the kind of thing a key-only check misses and a
        consumer generating client types from the schema then inherits.
        """
        assert self._descriptor_defs()[new_name].get("title") == new_name

    def test_no_dangling_ref_to_a_pre_rename_name(self) -> None:
        """A renamed ``$defs`` key with an unrenamed ``$ref`` is an unresolvable schema."""
        raw = json.dumps(load_schema("interface-descriptor"))
        stale = sorted(old for old in RENAMED if f'#/$defs/{old}"' in raw)
        assert not stale, f"schema still references pre-rename $defs: {stale}"
