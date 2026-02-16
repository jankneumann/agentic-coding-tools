## 1. Layer 1 — Standardize Analyzer Outputs

- [ ] 1.1 Fix TS analyzer missing `<directory>` positional argument in `refresh_architecture.sh` and `Makefile`
- [ ] 1.2 Fix `api_calls` → `api_call_sites` key mismatch in `compile_architecture_graph.py`
- [ ] 1.3 Fix double schema prefix (`pg:public.public.users`) in FK edge construction
- [ ] 1.4 Fix `functions` → `stored_functions` key mismatch for Postgres stored function ingestion
- [ ] 1.5 Add Layer 1 output JSON schema documentation to `.architecture/README.md`

## 2. Layer 2 — Extract Insight Modules

- [ ] 2.1 Create `scripts/insights/` directory with `__init__.py`
- [ ] 2.2 Extract `graph_builder.py` — canonical graph construction from Layer 1 outputs (ingestion of Python, TS, Postgres data into nodes/edges/entrypoints)
- [ ] 2.3 Extract `cross_layer_linker.py` — frontend-to-backend URL matching (3-pass linking with confidence levels)
- [ ] 2.4 Extract `db_linker.py` — backend-to-database linking (ORM model usage → table edges)
- [ ] 2.5 Extract `flow_tracer.py` — cross-layer flow inference (BFS from API endpoints through service calls to DB tables)
- [ ] 2.6 Extract `impact_ranker.py` — high-impact node detection (most dependents, most edges)
- [ ] 2.7 Refactor `validate_flows.py` → `insights/flow_validator.py` (consistent module interface)
- [ ] 2.8 Refactor `parallel_zones.py` → `insights/parallel_zones.py` (consistent module interface)
- [ ] 2.9 Update `compile_architecture_graph.py` to delegate to extracted modules (thin orchestrator)

## 3. Layer 3 — Report Aggregator

- [ ] 3.1 Create `scripts/reports/` directory
- [ ] 3.2 Create `scripts/reports/architecture_report.py` — reads all Layer 2 outputs, produces `architecture.report.md`
- [ ] 3.3 Refactor `generate_views.py` to produce Mermaid fragments consumable by report aggregator
- [ ] 3.4 Define report sections: Summary, Cross-Layer Flows, Diagnostics, Impact Analysis, Parallel Zones, Mermaid Diagrams

## 4. Orchestration and Integration

- [ ] 4.1 Update `refresh_architecture.sh` with explicit 3-stage pipeline (Layer 1 → Layer 2 → Layer 3)
- [ ] 4.2 Update `Makefile` targets to reflect new module structure
- [ ] 4.3 Verify output artifact backward compatibility (diff `architecture.graph.json` and `architecture.summary.json` against baseline)

## 5. Testing

- [ ] 5.1 Add fixture JSON files for Layer 1 outputs (sample `python_analysis.json`, `ts_analysis.json`, `postgres_analysis.json`)
- [ ] 5.2 Add unit tests for each Layer 2 insight module using fixtures
- [ ] 5.3 Add integration test that runs full 3-layer pipeline and validates output schema
