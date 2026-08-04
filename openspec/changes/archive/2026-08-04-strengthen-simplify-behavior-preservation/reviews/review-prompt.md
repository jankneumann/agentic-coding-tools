# Implementation review: strengthen-simplify-behavior-preservation (whole-branch)

You are reviewing the implementation of OpenSpec change `strengthen-simplify-behavior-preservation`.

## Context

This change strengthens the `/simplify` skill with:
1. Coverage gate + characterization tests when surface unpinned
2. Dual-run verification (baseline + HEAD)
3. Scripts: check_scope.py, check_test_contract.py, verify_behavior_preservation.py
4. Expanded patterns (isomorphic extract, dead code, redundant intermediate)
5. Ecosystem hooks: tech-debt routing, optional implement/iterate polish
6. Manual invocation only; keep /simplify

Spec requirements: openspec/changes/strengthen-simplify-behavior-preservation/specs/skill-workflow/spec.md
Proposal: openspec/changes/strengthen-simplify-behavior-preservation/proposal.md

## Diff

Run: `git diff origin/main...HEAD`

Key paths:
- skills/simplify/SKILL.md
- skills/simplify/scripts/*.py
- skills/tests/simplify/*
- skills/tech-debt-analysis/SKILL.md
- skills/implement-feature/SKILL.md
- skills/iterate-on-implementation/SKILL.md
- docs/skills-catalogue.md
- docs/skill-flow/README.md
- openspec/changes/strengthen-simplify-behavior-preservation/**

## Your task

Produce ONLY valid JSON conforming to review-findings.schema.json with:
- review_type: "implementation"
- target: "whole-branch"
- reviewer_vendor: your vendor id
- findings: array of findings with required fields: id, type, criticality, description, disposition, axis, severity
- description MUST start with Critical:/Nit:/Optional:/FYI:/none: matching severity
- Include package_id: "whole-branch" on each finding
- Include file_path and line_range when citing code
- Cover multiple axes (correctness, readability, architecture, security, performance as applicable)
- At least one positive observation (severity: none) if the implementation is sound in some respect
- Focus: bugs in scripts, incomplete spec coverage, test gaps, path resolution, shell injection in verify_behavior_preservation, weak assertion detection, missing edge cases

Do not modify any files. Output ONLY the JSON object.
