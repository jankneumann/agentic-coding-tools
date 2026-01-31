#!/usr/bin/env python3
"""Check whether a PR's changes are still relevant against current main.

Staleness levels:
  - fresh: No overlapping file changes on main since PR creation
  - stale: Same files modified on main, changes may conflict
  - obsolete: The fix the PR applies is no longer needed (code pattern gone)

Usage:
  python check_staleness.py <pr_number> [--origin <type>] [--dry-run]

Output: JSON object with staleness assessment to stdout.
"""

import json
import re
import subprocess
import sys

from shared import (
    GH_TIMEOUT,
    GIT_TIMEOUT,
    check_gh,
    parse_pr_number,
    run_cmd,
    run_gh,
)


def fetch_origin_main(base_branch: str = "main"):
    """Fetch latest remote state so staleness checks use up-to-date data."""
    run_cmd(["git", "fetch", "origin", base_branch], check=False)


def get_pr_info(pr_number: int) -> dict:
    try:
        raw = run_gh([
            "pr", "view", str(pr_number), "--json",
            "headRefName,baseRefName,createdAt,files,body,title",
        ], timeout=GH_TIMEOUT)
    except RuntimeError as e:
        print(f"Error: Could not fetch PR #{pr_number}: {e}", file=sys.stderr)
        sys.exit(1)
    return json.loads(raw)


def get_pr_changed_files(pr_number: int) -> list[str]:
    try:
        raw = run_gh([
            "pr", "view", str(pr_number), "--json", "files",
        ], timeout=GH_TIMEOUT)
    except RuntimeError as e:
        print(f"Error: Could not fetch files for PR #{pr_number}: {e}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(raw)
    return [f["path"] for f in data.get("files", [])]


def get_main_changes_since(since_date: str, base_branch: str = "main") -> list[str]:
    """Get files changed on remote base branch since the given ISO date."""
    result = subprocess.run(
        ["git", "log", f"--since={since_date}", "--name-only", "--pretty=format:",
         f"origin/{base_branch}"],
        capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT,
    )
    files = set()
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            files.add(line)
    return sorted(files)


def get_pr_diff_content(pr_number: int) -> str:
    """Get the actual diff of the PR to check if target code patterns still exist."""
    return run_cmd(["gh", "pr", "diff", str(pr_number)],
                   check=False, timeout=GH_TIMEOUT)


def normalize_pattern(s: str) -> str:
    """Normalize a code pattern for fuzzy comparison.

    Collapses whitespace so that reformatted code still matches.
    """
    return re.sub(r"\s+", " ", s).strip()


def parse_diff_file_path(diff_line: str) -> str | None:
    """Parse file path from a 'diff --git a/X b/Y' line.

    Uses the b/ prefix from the end to handle paths containing spaces or ' b/'.
    """
    # Format: diff --git a/<path> b/<path>
    # The b/ path is always the last segment
    prefix = "diff --git "
    if not diff_line.startswith(prefix):
        return None
    rest = diff_line[len(prefix):]
    # Find ' b/' scanning from right to handle paths containing ' b/'
    idx = rest.rfind(" b/")
    if idx == -1:
        return None
    return rest[idx + 3:]  # everything after ' b/'


def _is_significant_line(stripped: str) -> bool:
    """Check if a diff line is significant enough to use as a pattern."""
    return (
        bool(stripped)
        and len(stripped) > 10
        and not re.match(r"^[\s{}()\[\];,]*$", stripped)
    )


def _parse_diff_lines(diff_text: str) -> tuple[list[dict], list[dict]]:
    """Parse a diff into lists of significant removed and added lines."""
    removed_lines = []
    added_lines = []
    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            current_file = parse_diff_file_path(line)
        elif line.startswith("-") and not line.startswith("---"):
            stripped = line[1:].strip()
            if _is_significant_line(stripped):
                removed_lines.append({"file": current_file, "pattern": stripped})
        elif line.startswith("+") and not line.startswith("+++"):
            stripped = line[1:].strip()
            if _is_significant_line(stripped):
                added_lines.append({"file": current_file, "pattern": stripped})

    return removed_lines, added_lines


def _sample_patterns(lines: list[dict], max_samples: int = 8) -> list[dict]:
    """Sample up to max_samples significant patterns spread across files."""
    seen_files: set[str] = set()
    samples = []
    for item in lines:
        if len(samples) >= max_samples:
            break
        if item["file"] not in seen_files or len(samples) < 4:
            samples.append(item)
            seen_files.add(item["file"])
    return samples


def _read_file_from_ref(ref: str, path: str) -> str | None:
    """Read a file from a git ref, returns None if file doesn't exist."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _normalized_line_search(normalized_pattern: str, file_content: str) -> bool:
    """Search for a normalized pattern line-by-line to avoid normalizing entire file."""
    for file_line in file_content.splitlines():
        if normalized_pattern in normalize_pattern(file_line):
            return True
    return False


def _check_pattern_in_file(
    sample: dict, base_branch: str,
) -> dict:
    """Check if a single pattern still exists in its file on the base branch."""
    if not sample["file"]:
        return {
            "file": sample["file"],
            "pattern": sample["pattern"][:80],
            "found": False,
            "reason": "no_file",
        }

    file_content = _read_file_from_ref(
        f"origin/{base_branch}", sample["file"],
    )
    if file_content is None:
        return {
            "file": sample["file"],
            "pattern": sample["pattern"][:80],
            "found": False,
            "reason": "file_deleted",
        }

    # Try exact match first
    if sample["pattern"] in file_content:
        return {
            "file": sample["file"],
            "pattern": sample["pattern"][:80],
            "found": True,
            "match": "exact",
        }

    # Try normalized line-by-line match
    if _normalized_line_search(normalize_pattern(sample["pattern"]), file_content):
        return {
            "file": sample["file"],
            "pattern": sample["pattern"][:80],
            "found": True,
            "match": "normalized",
        }

    return {
        "file": sample["file"],
        "pattern": sample["pattern"][:80],
        "found": False,
        "reason": "pattern_gone",
    }


def check_pattern_exists_on_main(
    diff_text: str, base_branch: str = "main",
) -> dict:
    """Check if the 'before' state of the PR's changes still exists on main.

    Looks at removed lines (prefixed with -) to see if those code patterns
    are still present in the current base branch. Uses normalized whitespace
    comparison to handle reformatted code.

    For add-only PRs (no removals), checks if the added content already
    exists on main — if so, the PR is redundant.
    """
    removed_lines, added_lines = _parse_diff_lines(diff_text)

    # For add-only PRs: check if the additions already exist on main
    if not removed_lines and added_lines:
        return _check_additions_already_present(added_lines, base_branch)

    if not removed_lines:
        return {"patterns_found": True, "details": "No removals to check"}

    samples = _sample_patterns(removed_lines)
    checked = [_check_pattern_in_file(s, base_branch) for s in samples]
    patterns_still_present = sum(1 for c in checked if c["found"])

    return {
        "patterns_found": patterns_still_present > 0,
        "checked": len(checked),
        "present": patterns_still_present,
        "details": checked,
    }


def _check_additions_already_present(
    added_lines: list[dict], base_branch: str,
) -> dict:
    """For add-only PRs, check if the added content already exists on main."""
    samples = _sample_patterns(added_lines)
    checked = []

    for sample in samples:
        result = _check_pattern_in_file(sample, base_branch)
        # Remap reasons for add-only context
        if not result["found"] and result.get("reason") == "file_deleted":
            result["reason"] = "file_not_on_main"
        elif not result["found"] and result.get("reason") == "pattern_gone":
            result["reason"] = "not_yet_present"
        checked.append(result)

    all_present = (
        all(c["found"] for c in checked) and len(checked) > 0
    )
    return {
        "patterns_found": not all_present,
        "add_only": True,
        "checked": len(checked),
        "already_present": sum(1 for c in checked if c["found"]),
        "details": checked,
    }


def check_staleness(pr_number: int, origin: str = "other") -> dict:
    pr_info = get_pr_info(pr_number)
    created_at = pr_info.get("createdAt", "")
    base_branch = pr_info.get("baseRefName", "main")

    # Ensure we have fresh remote state
    fetch_origin_main(base_branch)

    pr_files = get_pr_changed_files(pr_number)
    main_files = get_main_changes_since(created_at, base_branch)

    overlapping = sorted(set(pr_files) & set(main_files))

    result = {
        "pr_number": pr_number,
        "created_at": created_at,
        "base_branch": base_branch,
        "pr_files": pr_files,
        "pr_file_count": len(pr_files),
        "main_changes_since": len(main_files),
        "overlapping_files": overlapping,
        "overlap_count": len(overlapping),
    }

    if not overlapping:
        result["staleness"] = "fresh"
        result["summary"] = "No overlapping changes — safe to merge."
        return result

    # For Jules automation PRs, check if the fix is still needed
    if origin in ("sentinel", "bolt", "palette"):
        diff_text = get_pr_diff_content(pr_number)
        pattern_check = check_pattern_exists_on_main(diff_text, base_branch)
        result["pattern_check"] = pattern_check

        if not pattern_check["patterns_found"]:
            result["staleness"] = "obsolete"
            reason = "code patterns this PR fixes no longer exist"
            if pattern_check.get("add_only"):
                reason = "additions in this PR are already present"
            result["summary"] = (
                f"Jules/{origin} fix is obsolete — {reason} "
                f"on {base_branch}."
            )
            return result

    result["staleness"] = "stale"
    result["summary"] = (
        f"{len(overlapping)} file(s) modified on {base_branch} since PR creation. "
        f"Review overlapping changes before merging."
    )
    return result


def main():
    check_gh()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = sys.argv[1:]

    if not args:
        print("Usage: check_staleness.py <pr_number> [--origin <type>] [--dry-run]",
              file=sys.stderr)
        sys.exit(1)

    pr_number = parse_pr_number(args[0])
    origin = "other"
    if "--origin" in flags:
        idx = flags.index("--origin")
        if idx + 1 < len(flags):
            origin = flags[idx + 1]

    dry_run = "--dry-run" in flags
    result = check_staleness(pr_number, origin)

    if dry_run:
        result["dry_run"] = True
        print(f"# Dry-run: Staleness check for PR #{pr_number}: {result['staleness']}",
              file=sys.stderr)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
