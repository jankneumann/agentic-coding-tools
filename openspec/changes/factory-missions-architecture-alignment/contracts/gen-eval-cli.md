# gen-eval CLI: `--openspec-change` flag specification

## Flag

```
--openspec-change <change-id>
```

**Type.** Optional string. Default: unset.

**Valid values.** Any directory name under `openspec/changes/` that contains a `specs/` subdirectory. The flag's value MUST NOT contain path separators or shell metacharacters.

**Effective only in.** `--mode cli-augmented`. When passed in `--mode template-only` or `--mode sdk-only`, gen-eval MUST log a warning naming the mode mismatch and ignore the flag.

## Behavior

When set in `cli-augmented` mode, gen-eval:

1. Resolves the change directory: `openspec/changes/<change-id>/specs/`.
2. Walks the directory recursively, reading every `*.md` file.
3. Parses each file for `### Requirement: <name>` blocks and the `#### Scenario: <name>` blocks nested under them.
4. Captures each scenario's source location as `<path>:<line-start>-<line-end>` where `<line-start>` is the line of the `#### Scenario:` heading and `<line-end>` is the line of the last AND/THEN bullet for that scenario.
5. Passes the parsed scenarios into the cli-augmented prompt under a `# OpenSpec Scenarios (constraints)` section, with each scenario tagged by source location.

## Emitted Scenario Object Augmentation

Generated `Scenario` Pydantic objects gain an optional `source.openspec_scenario` field:

```python
class ScenarioSource(BaseModel):
    template_path: str | None = None
    cli_seed: str | None = None
    openspec_scenario: str | None = None  # e.g., "openspec/changes/foo/specs/api/spec.md:42-50"
```

When the field is populated, downstream consumers (notably the `findings-gen-eval.json` emitter introduced by WP5) MUST use this value as the finding's `location` reference rather than the gen-eval scenario YAML.

## Backward Compatibility

When the flag is not passed:
- The cli-augmented prompt MUST NOT include any OpenSpec content.
- Generated Scenario objects MUST NOT include a populated `source.openspec_scenario` field.
- The behavior MUST be byte-identical to the pre-change cli-augmented mode.

## Failure Modes

| Condition | Behavior |
|---|---|
| `<change-id>` directory does not exist | Log warning naming the missing path, proceed as if flag was not passed |
| `specs/` subdirectory missing | Log warning, proceed as if flag was not passed |
| `specs/` exists but contains no `### Requirement:` blocks | Log info "no OpenSpec requirements found", proceed with empty constraint list |
| Parse error in a spec file | Log warning naming the file and line, skip that file, continue with others |
| Mode mismatch (flag passed in template-only or sdk-only) | Log warning, ignore flag |

In no case does this flag's failure halt scenario generation.
