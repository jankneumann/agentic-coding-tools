# Implementation Findings: add-bug-scrub-skill

## Iteration 1

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | bug | high | `collect_ruff.py` version pre-check only catches `FileNotFoundError`, not `SubprocessError` from partial install | Fixed: catch `(FileNotFoundError, subprocess.SubprocessError)` |
| 2 | bug | high | `execute_auto.py` imports `json` inside function body, making the module-level exception handler reference `json.JSONDecodeError` before import | Fixed: moved `import json` to module top level |
| 3 | edge-case | high | `collect_mypy.py` hardcodes `mypy src/` — projects without `src/` directory silently report zero findings | Fixed: changed to `mypy .` to respect pyproject.toml config |
| 4 | edge-case | medium | `collect_markers.py` only scans `**/*.py` but misses `.pyi` type stub files which are also Python | Fixed: added `**/*.pyi` to glob pattern |
| 5 | bug | medium | `fix_models.py` uses `assert` for importlib spec validation — assertions disabled with `-O` flag | Fixed: replaced with explicit `if/raise ImportError` |
| 6 | consistency | medium | `verify.py` mypy command used `src/` but should match the collector change to `.` | Fixed: updated to `mypy .` |
