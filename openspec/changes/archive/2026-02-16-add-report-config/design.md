# Design: Architecture Report Configuration File

## Architecture Decision

### Config loading strategy

The config file is loaded once in `main()` and threaded through `generate_report()` as a typed dataclass. Section functions receive only the fields they need (not the entire config), keeping their signatures focused.

```
main()
  → load_config(config_path)        # YAML → ReportConfig dataclass
  → generate_report(..., config)    # passes config to section builders
    → _section_system_overview(..., project=config.project)
    → _section_health(..., health=config.health)
    → ...
```

### Config resolution order

For paths, the resolution order is:
1. CLI flag (`--input-dir`, `--output`) — highest priority
2. Config file (`paths.input_dir`, `paths.output_report`)
3. Hardcoded default (`docs/architecture-analysis`)

This means the Makefile can continue passing `--input-dir $(ARCH_DIR)` and it will override the config file.

### Schema validation approach

Use a simple dataclass with `__post_init__` validation rather than a JSON Schema or pydantic model. Reasons:
- No new dependencies (pydantic is available but not needed for this)
- The config is small and flat — a dataclass is sufficient
- Unknown keys produce warnings (logged), not errors — forward-compatible

Actually, since `pydantic` is already a dependency of the project (via fastmcp/fastapi), we CAN use it for concise validation. But the config schema is simple enough that plain dataclasses + manual checks are clearer and avoid coupling the scripts to the agent-coordinator's dependencies.

### Best practices integration

Best practices files are read as raw markdown and included in a dedicated report section. The `sections` list in each best practices entry specifies which markdown headings to extract (via `## Heading` matching). If a section heading is not found, it's silently skipped.

This is intentionally read-only — the config points to documents, the report quotes relevant sections, but no automated rule checking is performed.

### Section registry pattern

Map section names to builder functions:

```python
_SECTION_REGISTRY: dict[str, Callable] = {
    "system_overview": _section_system_overview,
    "module_map": _section_module_map,
    "dependency_layers": _section_dependency_layers,
    ...
}
```

`generate_report()` iterates `config.report.sections` and calls only registered functions. Unknown section names produce a warning.

## Trade-offs

| Decision | Alternative | Why chosen |
|----------|------------|------------|
| YAML format | TOML, JSON | YAML supports comments (critical for documenting "why"), already a dependency |
| Dataclass, not pydantic | Pydantic BaseModel | Keeps scripts/ independent of agent-coordinator deps |
| Warn on unknown keys | Error on unknown keys | Forward-compatible — newer config files work with older report generators |
| Best practices as context | Best practices as automated checks | Automated checks need complex rule engines; context is useful today |
