# Contract: architecture gate config + gate statuses

## `architecture.config.yaml` — `gates` section (new)

```yaml
gates:
  architecture:
    mode: advisory            # "advisory" | "blocking"; default advisory when absent
    block_on:
      new_dependency_cycles: true
    clean_runs_before_flip: 3 # documentation of the ratchet criterion, not enforced

health:
  severity_thresholds:        # non-empty after this change
    new_cycle: critical
    cross_layer_violation: major
    file_size: minor
```

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
