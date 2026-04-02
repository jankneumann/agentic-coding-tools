---
name: changelog-version
description: Generate changelog entries and suggest semantic version bumps from git history
category: Git Workflow
tags: [changelog, versioning, semver, release]
triggers:
  - "update changelog"
  - "changelog"
  - "version bump"
  - "what version"
  - "release version"
  - "suggest version"
---

# Changelog & Version

Generate changelog entries from git history and suggest semantic version bumps based on conventional commit types.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--since <ref>` (git ref or tag to start from; default: last changelog update or all commits)
- `--bump` (apply the suggested version bump to VERSION and CHANGELOG.md)
- `--dry-run` (show what would change without modifying files; default when no flags given)
- `--format <keep-a-changelog|simple>` (changelog format; default: keep-a-changelog)

## Prerequisites

- Python 3.12+
- Git repository with conventional commit messages (`type(scope): message`)
- `VERSION` file in project root (created automatically if missing)
- `CHANGELOG.md` in project root (created automatically if missing)

## Version Bump Rules

The script analyzes commits since the last version tag or changelog entry and suggests a bump level:

| Commit Prefix | SemVer Impact | Examples |
|---------------|---------------|----------|
| `feat` | **MINOR** bump | New skill, new capability, new API endpoint |
| `fix` | **PATCH** bump | Bug fixes, corrections |
| `docs` | **PATCH** bump | Documentation-only changes |
| `refactor` | **PATCH** bump | Code restructuring without behavior change |
| `chore` | **PATCH** bump | Maintenance, dependency updates, archiving |
| `test` | **PATCH** bump | Test additions or fixes |
| `perf` | **PATCH** bump | Performance improvements |
| `BREAKING CHANGE` | **MAJOR** bump | Footer or `!` after type signals breaking change |

The highest-impact commit determines the suggestion. For example, if there are 5 `fix` commits and 1 `feat` commit, the suggestion is MINOR.

## Steps

### 1. Analyze Git History

Run the changelog analysis script to scan commits and categorize changes:

```bash
python3 <agent-skills-dir>/changelog-version/scripts/changelog.py analyze \
  --repo-root <project-root> \
  --since <ref-or-tag>
```

This outputs:
- Categorized commit list (Added, Changed, Fixed, etc.)
- Suggested version bump level (MAJOR, MINOR, or PATCH)
- Current version from `VERSION` file
- Proposed next version

### 2. Review Suggestions

Present the analysis to the user:

1. **Current version** from `VERSION`
2. **Suggested bump** with rationale (which commits drive the suggestion)
3. **Changelog preview** in Keep a Changelog format
4. **Key commits** that influence the version decision

Ask the user to confirm or override the suggested bump level before applying.

### 3. Apply Changes (if --bump or user confirms)

```bash
python3 <agent-skills-dir>/changelog-version/scripts/changelog.py apply \
  --repo-root <project-root> \
  --bump <major|minor|patch> \
  --date <YYYY-MM-DD>
```

This will:
1. Update `VERSION` with the new version number
2. Move `[Unreleased]` entries in `CHANGELOG.md` under a new version heading
3. Add a fresh `[Unreleased]` section

### 4. Commit Version Bump

After applying, commit both files:

```bash
git add VERSION CHANGELOG.md
git commit -m "chore(release): bump version to <new-version>"
```

### 5. Integration with Feature Workflow

This skill is designed to be invoked:
- **After `/implement-feature`** — to preview what version bump the new feature warrants
- **Before `/cleanup-feature`** — to include the changelog entry in the merge PR
- **Standalone** — for periodic changelog updates or release preparation

When invoked after implementing a feature, the script automatically detects the OpenSpec change-id from the branch name and highlights commits related to that change.
