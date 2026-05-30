"""Surface test for ``gen_eval.metrics``.

The ``gen_eval.metrics`` module MUST expose exactly one public symbol:
``GenEvalMetrics``. This test pins that surface so future refactors
cannot silently re-import unrelated coordinator-domain metric classes
(``TimingMetric``, ``MetricsCollector``, etc.) back into the package.

The assertion message lists the unexpected names so the failure is
self-diagnosing.

Spec scenario: gen-eval-framework.module-discovery-and-import-boundary
Design decision: D3
"""

from __future__ import annotations


def test_gen_eval_metrics_public_surface_is_exactly_gen_eval_metrics() -> None:
    import gen_eval.metrics

    public_names = {n for n in dir(gen_eval.metrics) if not n.startswith("_")}
    expected = {"GenEvalMetrics"}
    unexpected = public_names - expected
    assert public_names == expected, (
        f"gen_eval.metrics public surface must be exactly {sorted(expected)}; "
        f"unexpected public names: {sorted(unexpected)}"
    )
