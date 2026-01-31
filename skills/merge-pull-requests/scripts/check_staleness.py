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

GH_TIMEOUT = 30
GIT_TIMEOUT = 60


def check_gh():
    try:
        subprocess.run(
            ["gh", "--version"], capture_output=True, text=True,
            check=True, timeout=GH_TIMEOUT,
        )
    except FileNotFoundError:
        print("Error: 'gh' CLI is not installed or not on PATH.", file=sys.stderr)
        sys.exit(1)


def run(cmd: list[str], check: bool = True, timeout: int = GIT_TIMEOUT) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=check, timeout=timeout,
    )
    return result.stdout.strip()


def fetch_origin_main(base_branch: str = "main"):
    """Fetch latest remote state so staleness checks use up-to-date data."""
    run(["git", "fetch", "origin", base_branch], check=False)


def get_pr_info(pr_number: int) -> dict:
    raw = run([
        "gh", "pr", "view", str(pr_number), "--json",
        "headRefName,baseRefName,createdAt,files,body,title",
    ], timeout=GH_TIMEOUT)
    return json.loads(raw)


def get_pr_changed_files(pr_number: int) -> list[str]:
    raw = run([
        "gh", "pr", "view", str(pr_number), "--json", "files",
    ], timeout=GH_TIMEOUT)
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
    return run(["gh", "pr", "diff", str(pr_number)],
               check=False, timeout=GH_TIMEOUT)


def normalize_pattern(s: str) -> str:
    """Normalize a code pattern for fuzzy comparison.

    Collapses whitespace so that reformatted code still matches.
    """
    return re.sub(r"\s+", " ", s).strip()


def check_pattern_exists_on_main(
    diff_text: str, base_branch: str = "main",
) -> dict:
    """Check if the 'before' state of the PR's changes still exists on main.

    Looks at removed lines (prefixed with -) to see if those code patterns
    are still present in the current base branch. Uses normalized whitespace
    comparison to handle reformatted code.
    """
    removed_lines = []
    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" b/")
            if len(parts) == 2:
                current_file = parts[1]
        elif line.startswith("-") and not line.startswith("---"):
            stripped = line[1:].strip()
            # Skip empty or trivial lines (imports, braces, blank)
            if stripped and len(stripped) > 10 and not re.match(
                r"^[\s{}()\[\];,]*$", stripped
            ):
                removed_lines.append({
                    "file": current_file,
                    "pattern": stripped,
                })

    if not removed_lines:
        return {"patterns_found": True, "details": "No removals to check"}

    # Sample up to 8 significant removed patterns spread across files
    seen_files: set[str] = set()
    samples = []
    for item in removed_lines:
        if len(samples) >= 8:
            break
        # Prefer variety across files
        if item["file"] not in seen_files or len(samples) < 4:
            samples.append(item)
            seen_files.add(item["file"])

    patterns_still_present = 0
    checked = []

    for sample in samples:
        if not sample["file"]:
            continue
        result = subprocess.run(
            ["git", "show", f"origin/{base_branch}:{sample['file']}"],
            capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT,
        )
        if result.returncode != 0:
            checked.append({
                "file": sample["file"],
                "pattern": sample["pattern"][:80],
                "found": False,
                "reason": "file_deleted",
            })
            continue

        file_content = result.stdout
        normalized_pattern = normalize_pattern(sample["pattern"])

        # Try exact match first
        if sample["pattern"] in file_content:
            patterns_still_present += 1
            checked.append({
                "file": sample["file"],
                "pattern": sample["pattern"][:80],
                "found": True,
                "match": "exact",
            })
        # Try normalized (whitespace-insensitive) match
        elif normalized_pattern in normalize_pattern(file_content):
            patterns_still_present += 1
            checked.append({
                "file": sample["file"],
                "pattern": sample["pattern"][:80],
                "found": True,
                "match": "normalized",
            })
        else:
            checked.append({
                "file": sample["file"],
                "pattern": sample["pattern"][:80],
                "found": False,
                "reason": "pattern_gone",
            })

    return {
        "patterns_found": patterns_still_present > 0,
        "checked": len(checked),
        "present": patterns_still_present,
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
            result["summary"] = (
                f"Jules/{origin} fix is obsolete — the code patterns this PR "
                f"fixes no longer exist on {base_branch}."
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

    pr_number = int(args[0])
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
