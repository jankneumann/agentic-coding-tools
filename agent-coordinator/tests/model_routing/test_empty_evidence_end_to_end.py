"""End to end: with no routing evidence, enabling the router changes no phase.

retain-static-model-until-routing-evidence, task 5.3 (spec agent-archetypes.6).
The catalog is built exactly as production builds it — ``ConfiguredCatalogSync``
over the real ``agents.yaml`` and ``archetypes.yaml`` — and, like the live
catalog today, carries no priors, prices, latencies or posterior samples. Every
phase is resolved for every provider with ``ROUTING_ADAPTIVE`` on, through an
in-process ``RoutingService``, and compared with its static resolution.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents_config import (
    get_phase_mapping,
    load_archetypes_config,
    reset_archetypes_config,
    resolve_archetype_for_phase,
)
from src.model_routing.api import RoutingService, SelectModelRequest
from src.model_routing.configured_catalog import ConfiguredCatalogSync
from src.model_routing.resolver import CandidateInput

_ARCHETYPES = Path(__file__).resolve().parents[2] / "archetypes.yaml"
_PROVIDERS = [None, "claude_code", "codex", "antigravity", "grok", "pi"]


@pytest.fixture(autouse=True)
def _real_archetypes() -> None:
    reset_archetypes_config()
    load_archetypes_config(_ARCHETYPES)
    yield
    reset_archetypes_config()


def _evidence_free_catalog() -> list[CandidateInput]:
    rows: list[Any] = []
    fake = AsyncMock()
    fake.list_entries.return_value = []
    fake.upsert.side_effect = lambda entry: rows.append(entry)
    asyncio.run(ConfiguredCatalogSync(catalog=fake).sync())
    assert rows, "configured catalog produced no rows"
    return [
        CandidateInput(
            vendor=row.vendor,
            model=row.model,
            endpoint_kind=row.endpoint_kind,
            base_url=row.base_url,
        )
        for row in rows
    ]


def _wire_in_process_router(monkeypatch: pytest.MonkeyPatch, catalog: list[CandidateInput]):
    store = AsyncMock()
    store.list_candidates.return_value = catalog
    store.record_decision.return_value = {}
    ledger = AsyncMock()
    ledger.usage_summary.return_value = {}
    service = RoutingService(catalog=store, ledger=ledger)

    def _seam(*, task_signals, static_model, provider, timeout_seconds, incumbent=None):
        body: dict[str, Any] = {"task_signals": task_signals}
        if incumbent is not None:
            body["incumbent"] = incumbent
        return asyncio.run(service.select_model(SelectModelRequest.model_validate(body)))

    monkeypatch.setattr("src.model_routing.api.resolve_phase_model", _seam)
    monkeypatch.setenv("ROUTING_ADAPTIVE_TIMEOUT_SECONDS", "2")
    return service, store


def test_every_phase_equals_static_with_the_router_on(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    catalog = _evidence_free_catalog()
    phases = sorted(get_phase_mapping())
    assert phases

    monkeypatch.setenv("ROUTING_ADAPTIVE", "off")
    static = {
        (phase, provider): resolve_archetype_for_phase(phase, {}, provider=provider)
        for phase in phases
        for provider in _PROVIDERS
    }

    _service, store = _wire_in_process_router(monkeypatch, catalog)
    monkeypatch.setenv("ROUTING_ADAPTIVE", "on")
    caplog.set_level(logging.WARNING, logger="src.agents_config")
    differing = [
        key
        for key, expected in static.items()
        if resolve_archetype_for_phase(key[0], {}, provider=key[1]) != expected
    ]

    assert differing == [], f"{len(differing)} of {len(static)} resolutions changed"
    # Not vacuous via the D2 error path: the router answered every call, and
    # every answer was a recorded retention.
    assert "Adaptive model routing failed" not in caplog.text
    decisions = [call.args[0] for call in store.record_decision.await_args_list]
    assert len(decisions) == len(static)
    assert all(d["retention"]["retained"] for d in decisions)


def test_control_the_same_catalog_without_an_incumbent_ignores_the_task() -> None:
    # Guards the test above against passing vacuously: before this change, the
    # identical evidence-free catalog produced one pick for every task — the
    # first tied row (catalog order here; agent/vendor order on the assignment
    # path) — whatever the archetype's static tier was.
    catalog = _evidence_free_catalog()
    store = AsyncMock()
    store.list_candidates.return_value = catalog
    store.record_decision.return_value = {}
    service = RoutingService(catalog=store, ledger=AsyncMock())

    picks = {
        archetype: asyncio.run(
            service.select_model(
                SelectModelRequest(task_signals={"archetype": archetype}, allow_exploration=False)
            )
        )["selected"]
        for archetype in ("architect", "implementer", "runner")
    }

    assert len({c.vendor for c in catalog}) > 1
    assert len({(p["vendor"], p["model"]) for p in picks.values()}) == 1
    assert (picks["architect"]["vendor"], picks["architect"]["model"]) == (
        catalog[0].vendor,
        catalog[0].model,
    )
