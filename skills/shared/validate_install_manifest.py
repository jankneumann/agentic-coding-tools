#!/usr/bin/env python3
"""Validate the standalone skill-install payload contract.

The validator is dependency-free so ``skills/install.sh`` can run it before
copying anything. It validates catalogue completeness, declared smoke targets,
and repo-owned references that would escape a consumer installation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

_LINK_RE = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
_SOURCE_IMPORT_RE = re.compile(r"\b(?:from\s+src\.|import\s+src(?:\.|\b))")
_COORDINATOR_PATH_RE = re.compile(
    r"(?:sys\.path|parents?\[[^]]+\])[^\n]*agent-coordinator"
    r"|agent-coordinator[^\n]*(?:sys\.path|parents?\[[^]]+\])"
)
_CANONICAL_COMMAND_RE = re.compile(
    r"(?<!\.claude/)(?<!\.agents/)skills/(?:"
    r"\.venv(?:/|\b)|install\.sh\b|shared/[A-Za-z0-9_.-]+|"
    r"[a-z0-9][a-z0-9-]*/scripts(?:/|\b))"
)
_BARE_SCRIPT_COMMAND_RE = re.compile(r"\b(?:python3?|bash|sh)\s+[\"']?scripts/")
_SIBLING_REFERENCE_RE = re.compile(r"<skill-base-dir>/\.\./([a-z0-9][a-z0-9-]+)")
_SCANNED_SUFFIXES = {".py", ".sh", ".bash", ".zsh", ".md", ".json", ".yaml", ".yml"}


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("install manifest must contain a JSON object")
    return data


def discover_skills(skills_root: Path) -> set[str]:
    return {
        child.name
        for child in skills_root.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    }


#: Directory components install.sh's mirror_tree excludes from the payload.
#: Keep in lockstep with the --exclude flags in skills/install.sh; the pairing
#: is pinned by tests/shared/test_validate_install_manifest_excludes.py.
_EXCLUDED_PAYLOAD_DIRS = frozenset({"tests", "__pycache__", "node_modules"})


def _iter_payload_files(skills_root: Path, skill_names: Iterable[str], libraries: Iterable[str]) -> Iterable[Path]:
    for name in [*skill_names, *libraries]:
        base = skills_root / name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _SCANNED_SUFFIXES:
                continue
            rel_parts = path.relative_to(base).parts
            # Must exclude exactly what install.sh's mirror_tree excludes: this
            # validates the payload that actually ships, so scanning a directory
            # the installer skips reports failures about files no consumer ever
            # receives. node_modules is on-demand runtime output (refresh-
            # architecture npm-installs ts-morph itself and degrades when it is
            # absent), never a committed dependency — its vendored READMEs carry
            # upstream-relative links that can never resolve inside the payload.
            if any(part in _EXCLUDED_PAYLOAD_DIRS for part in rel_parts):
                continue
            if "__pycache__" in path.parts:
                continue
            if path.name == "validate_install_manifest.py":
                continue
            yield path


def _local_markdown_link_errors(path: Path, skills_root: Path) -> list[str]:
    errors: list[str] = []
    if path.suffix.lower() != ".md":
        return errors
    in_fence = False
    visible_lines: list[str] = []
    for line in path.read_text(errors="replace").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            visible_lines.append(line)
    for match in _LINK_RE.finditer("\n".join(visible_lines)):
        raw_target = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
        target = raw_target.split("#", 1)[0]
        if not target or target in {"url", "path", "file"} or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if any(token in target for token in ("<", ">", "$", "*")):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(skills_root.resolve())
        except ValueError:
            errors.append(f"{path}: Markdown link escapes installed payload: {raw_target}")
            continue
        if not resolved.exists():
            errors.append(f"{path}: Markdown link target is not shipped: {raw_target}")
    return errors


def _runtime_line_reason(path: Path, line: str, *, markdown_fence: bool) -> str | None:
    suffix = path.suffix.lower()
    stripped = line.strip()
    if "source-contribution-only" in line:
        return None
    if suffix == ".py":
        if _SOURCE_IMPORT_RE.search(line):
            return "private coordinator src import"
        if _COORDINATOR_PATH_RE.search(line):
            return "coordinator source path injection"
        if _CANONICAL_COMMAND_RE.search(line) and re.search(
            r"\b(?:subprocess|command|cmd|runner|hook)\b", line, re.IGNORECASE
        ):
            return "canonical skills runtime path"
        return None

    if suffix in {".sh", ".bash", ".zsh"}:
        if not stripped or stripped.startswith("#"):
            return None
        if _COORDINATOR_PATH_RE.search(line):
            return "coordinator source path injection"
        if _CANONICAL_COMMAND_RE.search(line):
            return "canonical skills runtime path"
        if _BARE_SCRIPT_COMMAND_RE.search(line) and "<project-root>" not in line and "<skill-base-dir>" not in line:
            return "ambiguous bare scripts runtime path"
        return None

    if suffix == ".md":
        if re.search(r"\b(?:must not|do not|never)\b", line, re.IGNORECASE):
            return None
        canonical_match = _CANONICAL_COMMAND_RE.search(line)
        command_starts_line = bool(
            re.match(r"^\s*(?:[$>]\s*)?(?:python3?|bash|sh|eval|skills/)", line)
        )
        verb_precedes_path = bool(
            canonical_match
            and re.search(
                r"\b(?:run|invoke|execute|command|via|use)\b[^\n]{0,40}$",
                line[: canonical_match.start()],
                re.IGNORECASE,
            )
        )
        table_command = bool(re.match(r"^\s*\|\s*`?(?:python3?|bash|sh|skills/)", line))
        executable_context = markdown_fence or command_starts_line or verb_precedes_path or table_command
        if not executable_context:
            return None
        if _SOURCE_IMPORT_RE.search(line):
            return "private coordinator src import"
        if _COORDINATOR_PATH_RE.search(line):
            return "coordinator source path injection"
        if _CANONICAL_COMMAND_RE.search(line):
            return "canonical skills runtime path"
        if _BARE_SCRIPT_COMMAND_RE.search(line) and "<project-root>" not in line and "<skill-base-dir>" not in line:
            return "ambiguous bare scripts runtime path"
        return None

    if suffix in {".json", ".yaml", ".yml"}:
        if not re.search(r"\b(?:command|cmd|hook|runner)\b", line, re.IGNORECASE):
            return None
        if _SOURCE_IMPORT_RE.search(line):
            return "private coordinator src import"
        if _COORDINATOR_PATH_RE.search(line):
            return "coordinator source path injection"
        if _CANONICAL_COMMAND_RE.search(line):
            return "canonical skills runtime path"
    return None


def validate_manifest(skills_root: Path, manifest: dict[str, Any], *, scan: bool = True) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    declared = manifest.get("skills")
    if not isinstance(declared, dict):
        return [*errors, "skills must be an object keyed by skill name"]

    discovered = discover_skills(skills_root)
    declared_names = set(declared)
    for name in sorted(discovered - declared_names):
        errors.append(f"skill has no distribution classification: {name}")
    for name in sorted(declared_names - discovered):
        errors.append(f"manifest declares missing skill: {name}")
    for name, entry in sorted(declared.items()):
        if not isinstance(entry, dict) or entry.get("distribution") not in {"portable", "repository-scoped"}:
            errors.append(f"skill has invalid distribution classification: {name}")
        if isinstance(entry, dict) and entry.get("distribution") == "repository-scoped" and not entry.get("reason"):
            errors.append(f"repository-scoped skill requires a reason: {name}")

    libraries = manifest.get("shared_libraries", [])
    if not isinstance(libraries, list) or not all(isinstance(item, str) for item in libraries):
        errors.append("shared_libraries must be a list of directory names")
        libraries = []
    for name in libraries:
        if not (skills_root / name).is_dir():
            errors.append(f"shared library is not present: {name}")

    runtime_globs = manifest.get("runtime_globs", [])
    if not isinstance(runtime_globs, list) or not runtime_globs:
        errors.append("runtime_globs must declare the installed runtime surface")

    installed_assets = manifest.get("installed_assets", [])
    if not isinstance(installed_assets, list):
        errors.append("installed_assets must be a list")
    else:
        for asset in installed_assets:
            if not isinstance(asset, dict) or not isinstance(asset.get("source_glob"), str):
                errors.append("installed_assets entries require source_glob and destination")
                continue
            if not isinstance(asset.get("destination"), str):
                errors.append("installed_assets entries require source_glob and destination")
            if not any(skills_root.glob(asset["source_glob"])):
                errors.append(f"installed asset source_glob matches nothing: {asset['source_glob']}")

    dependencies = manifest.get("cross_skill_dependencies", {})
    if not isinstance(dependencies, dict):
        errors.append("cross_skill_dependencies must be an object")
        dependencies = {}
    valid_dependency_targets = discovered | set(libraries)
    for source, targets in dependencies.items():
        if source not in discovered:
            errors.append(f"cross-skill dependency source is missing: {source}")
        if not isinstance(targets, list):
            errors.append(f"cross-skill dependencies must be a list: {source}")
            continue
        for target in targets:
            if target not in valid_dependency_targets:
                errors.append(f"cross-skill dependency target is missing: {source} -> {target}")

    for probe in manifest.get("smoke_entrypoints", []):
        if not isinstance(probe, dict) or not isinstance(probe.get("path"), str):
            errors.append("smoke_entrypoints entries require a path")
            continue
        target = (skills_root / probe["path"]).resolve()
        try:
            target.relative_to(skills_root.resolve())
        except ValueError:
            errors.append(f"smoke entrypoint escapes payload: {probe['path']}")
            continue
        if not target.is_file():
            errors.append(f"smoke entrypoint is not shipped: {probe['path']}")

    if not scan:
        return errors

    portable = [
        name
        for name, entry in declared.items()
        if isinstance(entry, dict) and entry.get("distribution") == "portable" and name in discovered
    ]
    observed_dependencies: set[tuple[str, str]] = set()
    for path in _iter_payload_files(skills_root, portable, libraries):
        text = path.read_text(errors="replace")
        rel = path.relative_to(skills_root)
        source_skill = rel.parts[0]
        for match in _SIBLING_REFERENCE_RE.finditer(text):
            target = match.group(1)
            if source_skill in portable and target != source_skill:
                observed_dependencies.add((source_skill, target))
        markdown_fence = False
        for line_no, line in enumerate(text.splitlines(), start=1):
            if path.suffix.lower() == ".md" and line.lstrip().startswith("```"):
                markdown_fence = not markdown_fence
                continue
            reason = _runtime_line_reason(path, line, markdown_fence=markdown_fence)
            if reason:
                errors.append(f"{rel}:{line_no}: {reason}: {line.strip()}")
        errors.extend(_local_markdown_link_errors(path, skills_root))
    for source, target in sorted(observed_dependencies):
        declared_targets = dependencies.get(source, [])
        if not isinstance(declared_targets, list) or target not in declared_targets:
            errors.append(f"cross-skill dependency is not declared: {source} -> {target}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--catalog-only", action="store_true")
    args = parser.parse_args(argv)
    manifest_path = args.manifest or args.skills_root / "install-manifest.json"
    errors = validate_manifest(
        args.skills_root.resolve(), load_manifest(manifest_path), scan=not args.catalog_only
    )
    if errors:
        print("Skill install portability validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Skill install portability validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
