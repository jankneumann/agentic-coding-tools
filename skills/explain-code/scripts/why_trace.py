"""Assemble the evidence chain behind one line of code, read-only.

Given ``<path>:<line>``, emit one JSON document describing the chain

    blame -> commit -> PR -> change-id -> decisions

for that line. The script assembles records and pointers only; it never
assigns an evidence tier. Tiering a claim is a judgement made in the reply,
and the pointers plus the per-decision ``mentions_target`` flag are what make
that judgement checkable.

Decision bullets are parsed only by the decision-index owner in the
co-installed sibling skill at ``<skill-base-dir>/../explore-feature/scripts``
(``decision_index.extract_decisions`` and its supersession resolver). This
module contains no second session-log parser.

Read-only: it runs only ``git blame``, ``show``, ``log``, ``rev-parse`` and
``ls-files``, writes no file (bytecode writes are disabled before the sibling
import) and makes no network call.

Exit codes: 0 a trace was produced (null results included), 1 git failure,
2 invalid input.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
from collections import defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402

_OWNER_SCRIPTS = Path(__file__).resolve().parents[2] / "explore-feature" / "scripts"
if str(_OWNER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_OWNER_SCRIPTS))

from decision_index import (  # noqa: E402
    TaggedDecision,
    _build_supersession_map,
    _phase_slug,
    extract_decisions,
)

# The owner warns on unknown or ambiguous refs; that is index-maintenance
# noise, not part of a trace.
logging.getLogger("decision_index").setLevel(logging.ERROR)

SCHEMA_VERSION = 1
_ZERO_SHA = "0" * 40

_TARGET_RE = re.compile(r"^(.+):([1-9]\d*)$")
_SUBJECT_PR_RE = re.compile(r"\(#(\d+)\)\s*$")
_MERGE_PR_RE = re.compile(r"^Merge pull request #(\d+)")
_ARCHIVE_PATH_RE = re.compile(r"^openspec/changes/archive/\d{4}-\d{2}-\d{2}-([^/]+)/")
_ACTIVE_PATH_RE = re.compile(r"^openspec/changes/(?!archive/)([^/]+)/")
_BRANCH_RE = re.compile(r"openspec/([a-z0-9][a-z0-9-]*)(?![A-Za-z0-9/_-])")
_ARCHIVE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")
_NOT_CHANGE_IDS = frozenset({"changes", "specs", "schemas", "roadmaps", "archive", "project"})


class GitError(Exception):
    """git could not be spawned or a required git call failed (exit 1)."""


class InputError(Exception):
    """The target is malformed, untracked or out of range (exit 2)."""


# ── git ─────────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path) -> str:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    cmd = ["git", "--literal-pathspecs", "-c", "core.quotepath=off", *args]
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), env=env, capture_output=True, check=False
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise GitError(f"cannot run git: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GitError(f"git {args[0]} failed: {detail[0] if detail else proc.returncode}")
    return proc.stdout.decode("utf-8", "replace")


def _repo_root(cwd: Path) -> Path:
    try:
        out = _git(["rev-parse", "--show-toplevel"], cwd)
    except GitError as exc:
        raise GitError(f"not a git repository: {cwd}") from exc
    return Path(out.strip())


# ── target ──────────────────────────────────────────────────────────


def _resolve_target(target: str, cwd: Path, root: Path) -> tuple[str, int]:
    m = _TARGET_RE.match(target)
    if not m:
        raise InputError(f"target must be <path>:<positive line>, got {target!r}")
    raw_path, line = m.group(1), int(m.group(2))
    abs_path = Path(os.path.realpath(cwd / raw_path))
    real_root = Path(os.path.realpath(root))
    try:
        rel = abs_path.relative_to(real_root).as_posix()
    except ValueError as exc:
        raise InputError(f"path is outside the repository: {raw_path}") from exc
    try:
        _git(["ls-files", "--error-unmatch", "--", rel], root)
    except GitError as exc:
        raise InputError(f"path is not tracked by git: {rel}") from exc
    if not abs_path.is_file():
        raise InputError(f"path is not a file in the working tree: {rel}")
    try:
        data = abs_path.read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read {rel}: {exc.strerror or exc}") from exc
    n_lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    if line > n_lines:
        raise InputError(f"line {line} is beyond the end of {rel} ({n_lines} lines)")
    return rel, line


# ── chain links ─────────────────────────────────────────────────────


def _has_head(root: Path) -> bool:
    try:
        _git(["rev-parse", "--verify", "-q", "HEAD"], root)
    except GitError:
        return False
    return True


def _blame(rel: str, line: int, root: Path) -> dict:
    if not _has_head(root):
        # Unborn HEAD: nothing is committed yet, so the line is uncommitted.
        return {
            "sha": _ZERO_SHA,
            "orig_line": line,
            "orig_path": rel,
            "author": None,
            "author_time": None,
            "summary": None,
            "pointer": f"git:{_ZERO_SHA}",
        }
    out = _git(["blame", "--porcelain", "-w", "-M", "-L", f"{line},{line}", "--", rel], root)
    lines = out.splitlines()
    head = lines[0].split()
    record = {
        "sha": head[0],
        "orig_line": int(head[1]),
        "orig_path": rel,
        "author": None,
        "author_time": None,
        "summary": None,
        "pointer": f"git:{head[0]}",
    }
    for entry in lines[1:]:
        if entry.startswith("\t"):
            break
        key, _, value = entry.partition(" ")
        if key == "author":
            record["author"] = value
        elif key == "author-time":
            record["author_time"] = int(value)
        elif key == "summary":
            record["summary"] = value
        elif key == "filename":
            record["orig_path"] = value
    return record


def _commit(sha: str, root: Path) -> dict:
    out = _git(["show", "-s", "--format=%H%x00%P%x00%an%x00%aI%x00%s%x00%b", sha], root)
    full, parents, author, date, subject, body = out.split("\x00", 5)
    names = _git(["show", "--name-only", "-z", "--format=", sha], root)
    files = sorted({n.strip("\n") for n in names.split("\x00") if n.strip("\n")})
    return {
        "sha": full,
        "parents": parents.split(),
        "author": author,
        "date": date,
        "subject": subject,
        "body": body.strip("\n"),
        "files": files,
        "pointer": f"git:{full}",
    }


def _pr(commit: dict, root: Path) -> tuple[dict | None, str | None, str]:
    """Return ``(pr, pr_reason, pr_merge_message)``."""
    m = _SUBJECT_PR_RE.search(commit["subject"])
    if m:
        return _pr_record(m, "subject_suffix", commit), None, ""
    m = _MERGE_PR_RE.match(commit["subject"])
    if m:
        return _pr_record(m, "merge_subject", commit), None, ""
    out = _git(
        ["log", "--ancestry-path", "--merges", "--format=%H%x00%P%x00%s%x00%b%x1e",
         f"{commit['sha']}..HEAD"],
        root,
    )
    merges = [rec.strip("\n") for rec in out.split("\x1e") if rec.strip("\n")]
    for rec in reversed(merges):  # oldest first
        sha, parents, subject, body = rec.split("\x00", 3)
        m = _MERGE_PR_RE.match(subject) or _SUBJECT_PR_RE.search(subject)
        if not m or not _introduced_by(commit["sha"], parents.split(), root):
            continue
        merge = {"sha": sha, "subject": subject}
        return _pr_record(m, "merge_commit", merge), None, f"{subject}\n{body}"
    return None, "no PR marker in the commit subject or in a merge commit that introduced it", ""


def _introduced_by(sha: str, merge_parents: list[str], root: Path) -> bool:
    """True when ``sha`` is not already reachable from the merge's first parent."""
    if not merge_parents:
        return False
    return bool(_git(["log", "-1", "--format=%H", f"{merge_parents[0]}..{sha}"], root).strip())


def _pr_record(match: re.Match, source: str, commit: dict) -> dict:
    return {
        "number": int(match.group(1)),
        "source": source,
        "sha": commit["sha"],
        "subject": commit["subject"],
        "pointer": f"git:{commit['sha']}",
    }


def _ids_from_text(text: str) -> list[str]:
    ids = []
    for m in _BRANCH_RE.finditer(text):
        cid = re.sub(r"--.*$", "", m.group(1))
        if cid and cid not in _NOT_CHANGE_IDS:
            ids.append(cid)
    return ids


def _change_ids(commit: dict, pr_merge_message: str, root: Path) -> list[dict]:
    tiers = []
    path_ids = []
    for f in commit["files"]:
        m = _ARCHIVE_PATH_RE.match(f) or _ACTIVE_PATH_RE.match(f)
        if m and m.group(1) not in _NOT_CHANGE_IDS:
            path_ids.append(m.group(1))
    tiers.append(("commit_paths", path_ids))
    tiers.append(("commit_message", _ids_from_text(f"{commit['subject']}\n{commit['body']}")))
    tiers.append(("pr_merge_message", _ids_from_text(pr_merge_message)))
    for source, ids in tiers:
        if ids:
            seen: list[str] = []
            for cid in ids:
                if cid not in seen:
                    seen.append(cid)
            return [
                {"change_id": cid, "source": source, "change_dir": _change_dir(cid, root)}
                for cid in seen
            ]
    return []


def _change_dir(cid: str, root: Path) -> str | None:
    active = root / "openspec" / "changes" / cid
    if active.is_dir():
        return f"openspec/changes/{cid}"
    archive = root / "openspec" / "changes" / "archive"
    if not archive.is_dir():
        return None
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-" + re.escape(cid) + r"$")
    names = sorted(p.name for p in archive.iterdir() if p.is_dir() and pattern.match(p.name))
    return f"openspec/changes/archive/{names[-1]}" if names else None


# ── decisions ───────────────────────────────────────────────────────


def _canonical_id(session_log: Path) -> str:
    name = session_log.parent.name
    if session_log.parent.parent.name == "archive":
        m = _ARCHIVE_DIR_RE.match(name)
        if m:
            return m.group(1)
    return name


def _supersession(root: Path) -> list[dict[tuple[str, str, int], TaggedDecision]]:
    """Supersession maps over every session log, by dir-name id and by canonical id."""
    raw: dict[str, list[TaggedDecision]] = defaultdict(list)
    canon: dict[str, list[TaggedDecision]] = defaultdict(list)
    changes = root / "openspec" / "changes"
    for log in sorted(changes.glob("**/session-log.md")) if changes.is_dir() else []:
        cid = _canonical_id(log)
        for d in extract_decisions(log):
            raw[d.capability].append(d)
            canon[d.capability].append(dataclasses.replace(d, change_id=cid))
    return [_build_supersession_map(raw), _build_supersession_map(canon)]


def _decision_ref(d: TaggedDecision) -> str:
    cid = _ARCHIVE_DIR_RE.match(d.change_id)
    cid_s = cid.group(1) if cid else d.change_id
    return f"{cid_s}#{_phase_slug(d.phase_name)}/D{d.decision_index_in_phase}"


def _decisions(change_ids: list[dict], rel: str, symbol: str | None, root: Path) -> list[dict]:
    needles = [rel, Path(rel).name] + ([symbol] if symbol else [])
    maps: list[dict] | None = None
    out = []
    for entry in change_ids:
        if not entry["change_dir"]:
            continue
        log_rel = f"{entry['change_dir']}/session-log.md"
        found = extract_decisions(root / log_rel)
        if not found:
            continue
        if maps is None:
            maps = _supersession(root)
        dir_id = Path(entry["change_dir"]).name
        for d in found:
            slug = _phase_slug(d.phase_name)
            idx = d.decision_index_in_phase
            sup = None
            for mapping in maps:
                for key_id in (dir_id, entry["change_id"]):
                    sup = sup or mapping.get((key_id, slug, idx))
            text = f"{d.title}\n{d.rationale}"
            index_path = f"docs/decisions/{d.capability}.md"
            out.append({
                "change_id": entry["change_id"],
                "capability": d.capability,
                "phase": d.phase_name,
                "date": d.phase_date.isoformat(),
                "index": idx,
                "title": d.title,
                "rationale": d.rationale,
                "supersedes": d.supersedes,
                "superseded_by": _decision_ref(sup) if sup else None,
                "pointer": f"{log_rel}#{slug}/D{idx}",
                "index_path": index_path if (root / index_path).is_file() else None,
                "mentions_target": any(n and n in text for n in needles),
                "_offset": d.source_offset,
            })
    out.sort(key=lambda r: (r["change_id"], r["date"], r["index"], r["_offset"]))
    for r in out:
        del r["_offset"]
    return out


# ── assembly ────────────────────────────────────────────────────────


def trace(target: str, symbol: str | None, cwd: Path) -> dict:
    root = _repo_root(cwd)
    rel, line = _resolve_target(target, cwd, root)
    doc: dict = {
        "schema_version": SCHEMA_VERSION,
        "target": {"path": rel, "line": line, "symbol": symbol},
        "status": None,
        "blame": _blame(rel, line, root),
        "commit": None,
        "pr": None,
        "pr_reason": None,
        "change_ids": [],
        "decisions": [],
        "null_result": None,
    }
    where = f"{rel}:{line}"
    if doc["blame"]["sha"] == _ZERO_SHA:
        doc["pr_reason"] = "the line is not committed"
        return _null(doc, "uncommitted", f"{where} has not been committed; there is no commit to trace")

    commit = _commit(doc["blame"]["sha"], root)
    doc["commit"] = commit
    doc["pr"], doc["pr_reason"], merge_message = _pr(commit, root)
    doc["change_ids"] = _change_ids(commit, merge_message, root)
    short = commit["sha"][:12]
    if not doc["change_ids"]:
        return _null(doc, "no_change_id", (
            f"commit {short} touches no openspec/changes/ path and neither it nor a PR "
            "merge commit names an openspec/<id> branch"
        ))
    doc["decisions"] = _decisions(doc["change_ids"], rel, symbol, root)
    if not doc["decisions"]:
        ids = ", ".join(e["change_id"] for e in doc["change_ids"])
        return _null(doc, "no_decision_record", (
            f"change {ids} has no architectural:-tagged Decision bullet in a session-log.md"
        ))
    doc["status"] = "traced"
    return doc


def _null(doc: dict, reason: str, message: str) -> dict:
    doc["status"] = reason
    doc["null_result"] = {"reason": reason, "message": message}
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="<path>:<line>, path relative to the current directory")
    parser.add_argument("--symbol", default=None, help="symbol name for the mentions_target check")
    args = parser.parse_args(argv)
    try:
        doc = trace(args.target, args.symbol, Path.cwd())
    except InputError as exc:
        print(f"why_trace: {exc}", file=sys.stderr)
        return 2
    except GitError as exc:
        print(f"why_trace: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(doc, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
