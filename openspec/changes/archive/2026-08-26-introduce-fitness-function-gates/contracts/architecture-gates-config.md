# Contract: architecture gate config + gate statuses

## `architecture.config.yaml` — `gates` section (new)

```yaml
gates:
  architecture:
    mode: advisory            # "advisory" | "blocking"; default advisory when absent
    block_on:
      new_dependency_cycles: true
    clean_runs_before_flip: 3 # documentation of the ratchet criterion, not enforced
    severity_thresholds:      # gate vocabulary: {critical, major, minor}
      new_cycle: critical
      cross_layer_violation: major
      file_size: minor

health:
  severity_thresholds: {}     # belongs to the architecture report — graded
                              # {error, warning, info}. NOT the gate's namespace.
```

**Namespace separation (required).** The gate's thresholds live under
`gates.architecture.severity_thresholds`, never under `health.severity_thresholds`.
The two keys are read by different consumers grading on different vocabularies —
`gate_logic.py` on `{critical, major, minor}`, `architecture_report.py` on
`{error, warning, info}`. A category graded in the wrong vocabulary resolves to
`min_level = 0` and filters nothing, i.e. a threshold that silently does nothing.
`gate_logic.py` still reads `health.severity_thresholds` as a fallback for configs
written before the gate namespace existed.

Loader rules: file remains optional (per `report-configuration` spec — absent file ⇒
built-in defaults, `mode: advisory`); unknown keys warn, never error.

`gate_logic.py` behavior:

- `mode: advisory` → Architecture phase NOT in `REQUIRED_PHASES`; findings still render.
- `mode: blocking` → `"Architecture"` added to `REQUIRED_PHASES`; a `new_cycle` finding
  maps to `critical` and fails `hard_gate()`.

## Gate status vocabulary (validation-report.md phase table)

| Status | Meaning | soft_gate | hard_gate |
|---|---|---|---|
| `PASS` | Checked, passed | continue | continue |
| `FAIL` | Checked, failed | warn+continue | block |
| `SKIP` | Intentionally not run (phase selector) | continue | continue if not required |
| `DEGRADED` | **Could not be checked** — checker unavailable, <2 vendors, degraded scan | warn loudly | block if phase required, unless `--accept-degraded <phase>` (override echoed in gate summary) |

Every producer that currently fails open MUST write `DEGRADED` plus a one-line "what
was not checked and why".
