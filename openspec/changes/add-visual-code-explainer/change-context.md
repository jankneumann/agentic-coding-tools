# Change Context: add-visual-code-explainer

<!-- Phase 1 (pre-implementation) skeleton. Contract Ref via generate_contract_refs.py. -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|-------------|-------------|--------------|-----------------|---------------|---------|----------|
| codebase-analysis.1 | specs/codebase-analysis/spec.md | Atlas Symbol Tree Export — `skills/codebase-atlas/scripts/build_atlas.py` SHALL accept `--tree <target>` with optional ` | --- | D3, D4, D8 | skills/codebase-atlas/SKILL.md, skills/codebase-atlas/scripts/atlas_tree.py, skills/codebase-atlas/scripts/build_atlas.py, skills/tests/codebase-atlas/test_atlas_tree.py, skills/tests/codebase-atlas/test_skill_md.py | skills/tests/codebase-atlas/test_atlas_tree.py | pass 11b3c9c1 |
| skill-workflow.1 | specs/skill-workflow/spec.md | Visual Code Explainer Skill — The repository SHALL provide a user-invocable, prompt-only skill `explain-code` that answe | --- | D1, D6, D9 | skills/explain-code/SKILL.md, skills/explain-code/references/call-tree.md, skills/explain-code/references/component-tree.md, skills/explain-code/references/file-tree.md, skills/explain-code/references/grounding.md, skills/explain-code/references/sequence.md, skills/explain-code/references/structural-diff.md, skills/install-manifest.json, skills/pyproject.toml, skills/tests/explain-code/test_behaviour.py, skills/tests/explain-code/test_skill_md.py | skills/tests/explain-code/test_skill_md.py; test_behaviour.py | pass 11b3c9c1 |
| skill-workflow.2 | specs/skill-workflow/spec.md | Explainer Grounding and Coverage Disclosure — Before sketching a call tree, the skill SHALL determine graph freshness by | --- | D2, D5, D9 | skills/explain-code/SKILL.md, skills/explain-code/references/call-tree.md, skills/explain-code/references/component-tree.md, skills/explain-code/references/file-tree.md, skills/explain-code/references/grounding.md, skills/explain-code/references/sequence.md, skills/explain-code/references/structural-diff.md, skills/install-manifest.json, skills/pyproject.toml, skills/tests/explain-code/test_behaviour.py, skills/tests/explain-code/test_skill_md.py | skills/tests/explain-code/test_behaviour.py | pass 11b3c9c1 |
| skill-workflow.3 | specs/skill-workflow/spec.md | Explainer Frontmatter Without Triggers — The `explain-code` `SKILL.md` frontmatter SHALL declare `name`, `description`,  | --- | D6 | skills/explain-code/SKILL.md, skills/explain-code/references/call-tree.md, skills/explain-code/references/component-tree.md, skills/explain-code/references/file-tree.md, skills/explain-code/references/grounding.md, skills/explain-code/references/sequence.md, skills/explain-code/references/structural-diff.md, skills/install-manifest.json, skills/pyproject.toml, skills/tests/explain-code/test_behaviour.py, skills/tests/explain-code/test_skill_md.py | skills/tests/explain-code/test_skill_md.py | pass 11b3c9c1 |
| skill-workflow.4 | specs/skill-workflow/spec.md | Explainer Distribution Wiring — `skills/install-manifest.json` SHALL declare `"explain-code": {"distribution": "portable | --- | D1 | skills/explain-code/SKILL.md, skills/explain-code/references/call-tree.md, skills/explain-code/references/component-tree.md, skills/explain-code/references/file-tree.md, skills/explain-code/references/grounding.md, skills/explain-code/references/sequence.md, skills/explain-code/references/structural-diff.md, skills/install-manifest.json, skills/pyproject.toml, skills/tests/explain-code/test_behaviour.py, skills/tests/explain-code/test_skill_md.py | skills/tests/explain-code/test_skill_md.py; install.sh --check | pass 11b3c9c1 |

## Design Decision Trace

| Decision | Summary | Requirements |
|----------|---------|--------------|
| D1 | Prompt-only skill; only new code is atlas --tree | skill-workflow.1, skill-workflow.4 |
| D2 | Freshness via run_architecture.py --check exit 0 only | skill-workflow.2 |
| D3 | --tree output format (indent, cycle, hops, footer) | codebase-analysis.1 |
| D4 | Target resolution order; exit 2/3 distinct | codebase-analysis.1 |
| D5 | Grounding disclosure line forms and exemptions | skill-workflow.2 |
| D6 | Frontmatter without triggers; explicit key tests | skill-workflow.1, skill-workflow.3 |
| D7 | Deterministic behavioural tests + optional harness | skill-workflow.2 |
| D8 | atlas_tree.py module layout | codebase-analysis.1 |
| D9 | Skill refuses files/browser/whole-repo | skill-workflow.1, skill-workflow.2 |

## Coverage Summary

| Metric | Count |
|--------|-------|
| Requirements | 5 |
| With tests planned | 5 |
| Implemented (Files Changed filled) | 5 |
| Evidence pass | 5 |

## Review Findings Summary

_Filled after package reviews._
