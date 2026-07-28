"""Drive ri-12's own helper to produce the semantic arm.

``packages/`` may not import ``skills/``, and this module is why it does not
have to. ``semantic_context.py`` is loaded through
:func:`importlib.util.spec_from_file_location` with **the path supplied by
configuration**, never derived from this file's ``__file__``. Two properties
follow, and both are load-bearing:

- the harness resolves the helper under an installed skill base
  (``.claude/skills/context-engineering/scripts/``) exactly as it does in a
  source checkout, because in both cases the caller says where it is;
- no import edge from ``packages/`` to ``skills/`` exists at all, so the
  dependency-direction linter has nothing to find.

**A correction to design D4, stated rather than left contradicted.** D4 says
this module is *the only* one that knows ``skills/`` exists. Phase 3 added
``producers/scope_adapter.py``, which also does: measuring D8's apparatus
condition — whether ri-12's non-injectable ``_normalize_read_scope`` resolved or
silently fell back to unnormalized globs — requires attempting the same import
ri-12 attempts, and the alternative was not measuring that condition at all.
There are therefore **two** such modules, both in ``producers/``, and they obey
one rule between them: *the location is supplied by configuration, never derived
from ``__file__``*. :data:`DEFAULT_MODULE_SUBPATH` here and
``scope_adapter.DEFAULT_ADAPTER_SUBPATH`` there are the same idea — a default
*location within a supplied root*, where the caller still has to say which
checkout. That is the property D4 was protecting; "one module" was the shape it
happened to take when D4 was written.

**Determinism, and one deliberate departure from ri-12's runtime.** The git
runner is injected and answers from the *declared* evaluated revision: the
worktree an evaluation runs in is routinely dirty, and ri-12's
``resolve_revision`` would then return ``stale``/``working_tree_dirty`` for every
single case — a correct runtime behaviour that would make the harness measure
the state of the developer's editor rather than the retrieval. The corpus
declares no case asserting ``working_tree_dirty``, so nothing is lost, and the
report records the revision the measurement claims to be about (design D16).
Everything else — the fallback mapping, the scope re-check, dedup, ranking,
budget — is ri-12's, unmodified, because the point is to measure ri-12 rather
than an imitation of it.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from ..models import Budget, Case
from ..scoring.arms import Arm, arm_from_section

#: ``skills/context-engineering/scripts/semantic_context.py`` relative to a
#: repository root. A default *location within a supplied root*, not a derived
#: root: the caller still has to say which checkout, which is the property
#: design D1 is about. Mirrors ``scope_adapter.DEFAULT_ADAPTER_SUBPATH``.
DEFAULT_MODULE_SUBPATH = (
    Path("skills") / "context-engineering" / "scripts" / "semantic_context.py"
)

#: The name the loaded module is registered under. Distinct from the plain
#: module name on purpose: this is a measurement copy loaded from a configured
#: location, and it must never be confused with, or satisfied by, whatever
#: ``import semantic_context`` would find on ``sys.path``.
LOADED_MODULE_NAME = "context_eval._semantic_context_under_measurement"

#: The capability flags ri-12 requires before it will query anything. Supplied
#: rather than detected: the harness is measuring the retrieval path, and a
#: coordination probe that happened to answer differently would silently turn
#: every case into a ``capability_absent`` fallback.
HTTP_TRANSPORT = "http"


class ProducerError(RuntimeError):
    """The semantic producer could not be built or could not measure a case."""


def load_semantic_context(module_path: Path | str) -> ModuleType:
    """Load ri-12's helper from *module_path*. The path is configuration.

    Raises:
        ProducerError: when the path names nothing loadable. Loud rather than
            degrading: a harness that quietly measured a *different* helper than
            the one it names would produce evidence about software nobody ran.
    """
    path = Path(module_path)
    if not path.is_file():
        raise ProducerError(f"no semantic-context helper at {path}")

    spec = importlib.util.spec_from_file_location(LOADED_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise ProducerError(f"{path} is not an importable module")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, and under the distinctive name above.
    # `@dataclass(slots=True)` — which ri-12 uses throughout — rebuilds the class
    # and resolves it through `sys.modules[cls.__module__]`, so a module executed
    # while unregistered fails with an opaque AttributeError. Registering it
    # under `semantic_context` instead would let a later plain import be answered
    # by this measurement copy, which is the silent substitution
    # `scope_adapter._loaded_from` exists to prevent one directory over.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - every load failure is one fact
        del sys.modules[spec.name]
        raise ProducerError(f"{path} did not load: {error!r}") from error
    return module


def module_path_for(repository_root: Path | str) -> Path:
    """Where ``semantic_context.py`` lives inside a supplied checkout."""
    return Path(repository_root) / DEFAULT_MODULE_SUBPATH


@dataclass(frozen=True)
class _ResolvedScope:
    """What ri-12's ``index_scopes`` seam returns: two glob tuples, duck-typed."""

    read_allow: tuple[str, ...]
    deny: tuple[str, ...]


@dataclass
class SemanticRuntimeProducer:
    """Render one case's semantic arm by running ri-12's own decision tree.

    Every seam ri-12 exposes is filled from configuration or from the corpus:
    the search client returns the case's recorded response (or reaches the real
    bridge when *live*), the capability probe reports the transport the report
    records, the scope resolver returns the case's declared globs, and the git
    runner answers from the declared evaluated revision.
    """

    module: ModuleType
    repository_root: Path
    evaluated_revision: str
    budget: Budget
    #: When true, ri-12's real search client is used and the recorded response is
    #: ignored — the live path phase 6 drives. When false, only cases carrying a
    #: recorded response can be measured at all.
    live: bool = False
    #: The last outbound request body ri-12 built, captured at the search seam so
    #: outbound scope fidelity is measurable on the request as well as the result.
    _last_body: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def render(self, case: Case, response: Mapping[str, Any] | None = None) -> Arm:
        """Run ri-12 for *case* and adapt the section it returns into an arm."""
        self._last_body = None
        if not self.live and response is None:
            raise ProducerError(
                f"{case.case_id} has no recorded response and this producer is not live; "
                "an unmeasurable case is recorded as unscored, never as an empty result"
            )

        request = self._request(case)
        runtime = self._runtime(case, response)
        result = self.module.collect_semantic_context(request, runtime)
        return arm_from_section(result.to_dict(), arm="semantic")

    @property
    def last_request_body(self) -> dict[str, Any] | None:
        """The body sent for the most recent :meth:`render`, or ``None``.

        ``None`` is a fact about the case rather than a missing measurement: a
        case whose declared scope is empty short-circuits at
        ``out_of_scope``/``no_declared_scope`` before anything reaches the wire.
        """
        return self._last_body

    # -- ri-12's seams ---------------------------------------------------

    def _request(self, case: Case) -> Any:
        """The request a coding job would have issued for this case.

        A case with no declared read scope is issued with no change or package
        context, which is what ``quick-task`` and ad-hoc debugging actually look
        like: ri-12 then returns ``out_of_scope``/``no_declared_scope`` from its
        own precondition rather than from anything this harness decided.
        """
        packaged = bool(case.scope.read_allow)
        return self.module.SemanticContextRequest(
            repository=self.repository_root,
            query=case.query,
            consumer=case.consumer,
            change_id=case.case_id.lower() if packaged else None,
            package_id=case.consumer if packaged else None,
            budget=self.module.ContextBudget(
                max_hits=self.budget.max_hits,
                max_files=self.budget.max_files,
                max_total_lines=self.budget.max_total_lines,
                max_hit_lines=self.budget.max_hit_lines,
            ),
        )

    def _runtime(self, case: Case, response: Mapping[str, Any] | None) -> Any:
        fields: dict[str, Any] = {
            "detect": lambda: {
                "CAN_CODE_SEARCH": True,
                "COORDINATION_TRANSPORT": HTTP_TRANSPORT,
            },
            "git": self._git,
            "load_package": lambda *args, **kwargs: {"package_id": case.consumer},
            "index_scopes": lambda package: _ResolvedScope(
                read_allow=tuple(case.scope.read_allow), deny=tuple(case.scope.deny)
            ),
            "env": {self.module.INJECTION_FLAG: "1"},
        }
        if not self.live:
            fields["search"] = self._recorded_search(response)
        else:
            fields["search"] = self._recording_search(self.module.DEFAULT_RUNTIME.search)
        return self.module.SemanticContextRuntime(**fields)

    def _recorded_search(self, response: Mapping[str, Any] | None) -> Any:
        def search(body: Mapping[str, Any]) -> dict[str, Any]:
            self._last_body = dict(body)
            return {"status": "ok", "response": dict(response or {})}

        return search

    def _recording_search(self, inner: Any) -> Any:
        def search(body: Mapping[str, Any]) -> Any:
            self._last_body = dict(body)
            return inner(body)

        return search

    def _git(self, repository: Path, args: Sequence[str]) -> str | None:
        """Answer from the declared evaluated revision. See the module docstring."""
        argv = tuple(args)
        if argv[:1] == ("rev-parse",) and "--show-toplevel" in argv:
            return str(self.repository_root)
        if argv == ("rev-parse", "HEAD"):
            return self.evaluated_revision
        if argv[:1] == ("status",):
            return ""
        return None  # pragma: no cover - ri-12 issues no other git command


def recorded_response(corpus_root: Path | str, case: Case) -> dict[str, Any] | None:
    """The recorded service response a case names, decoded, or ``None``."""
    import json

    if case.recorded_response is None:
        return None
    path = Path(corpus_root) / case.recorded_response.path
    if not path.is_file():
        raise ProducerError(f"recorded response is missing: {path}")
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ProducerError(f"recorded response is not an object: {path}")
    return decoded
