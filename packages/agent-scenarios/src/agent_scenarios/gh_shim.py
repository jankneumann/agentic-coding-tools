"""A tiny local ``gh`` stand-in so live runs never reach GitHub (design D5).

:func:`install_gh_shim` writes an executable ``gh`` into ``<workdir>.bin/`` (outside the
workspace) plus a JSON state file seeded from the fixture's ``prs`` list. The shim serves a
deliberately small surface against the fixture's local bare ``origin``; any other call exits
1 and is appended to ``gh-unsupported.log`` so the executor can force an ``error`` verdict.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

from .models import AgentScenario

STATE_FILE = "gh-state.json"
UNSUPPORTED_LOG = "gh-unsupported.log"

# Stdlib-only script body; runs under the harness interpreter (shebang is filled at install).
SHIM_SOURCE = r'''
import json, os, subprocess, sys, tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "gh-state.json")
LOG = os.path.join(HERE, "gh-unsupported.log")


def load():
    with open(STATE, encoding="utf-8") as fh:
        return json.load(fh)


def save(st):
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(st, fh)


def unsupported(argv):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write("gh " + " ".join(argv) + "\n")
    sys.stderr.write("gh shim: unsupported call: gh " + " ".join(argv) + "\n")
    sys.exit(1)


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def git(*args, cwd=None, check=True):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        fail("git " + " ".join(args) + " failed: " + (proc.stderr.strip() or proc.stdout.strip()))
    return proc


def opt(argv, *names):
    """Return the value of the first of ``names`` present in argv, else None."""
    for i, a in enumerate(argv):
        for n in names:
            if a == n and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith(n + "="):
                return a.split("=", 1)[1]
    return None


def positional(argv, value_flags):
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in value_flags:
            skip = True
            continue
        if a.startswith("-"):
            continue
        out.append(a)
    return out


def pr_view(st, pr):
    repo = st["repo"]
    merged = pr["state"] == "MERGED"
    return {
        "number": pr["number"],
        "url": "https://github.invalid/%s/pull/%d" % (repo, pr["number"]),
        "title": pr["title"],
        "body": pr.get("body", ""),
        "state": pr["state"],
        "headRefName": pr["head"],
        "baseRefName": pr["base"],
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "mergedAt": pr.get("mergedAt") if merged else None,
        "author": {"login": "fixture"},
        "labels": [],
        "reviewDecision": "",
        "statusCheckRollup": [],
    }


def emit(obj, fields):
    if fields:
        keys = [f for f in fields.split(",") if f]
        obj = [{k: o.get(k) for k in keys} for o in obj] if isinstance(obj, list) else {
            k: obj.get(k) for k in keys
        }
    print(json.dumps(obj))


def current_branch():
    proc = git("rev-parse", "--abbrev-ref", "HEAD", check=False)
    return proc.stdout.strip()


def find_pr(st, ref):
    if ref is None:
        ref = current_branch()
    for pr in st["prs"]:
        if ref.isdigit() and pr["number"] == int(ref):
            return pr
        if not ref.isdigit() and pr["head"] == ref and pr["state"] == "OPEN":
            return pr
    for pr in st["prs"]:
        if not ref.isdigit() and pr["head"] == ref:
            return pr
    return None


def merge_pr(st, pr, argv):
    origin, base, head = st["origin"], pr["base"], pr["head"]
    if "--squash" in argv or "-s" in argv:
        mode = "squash"
    elif "--rebase" in argv or "-r" in argv:
        mode = "rebase"
    else:
        mode = "merge"
    tmp = tempfile.mkdtemp(prefix="gh-shim-")
    work = os.path.join(tmp, "r")
    git("clone", "-q", origin, work)
    git("config", "user.email", "gh-shim@agent-scenarios.local", cwd=work)
    git("config", "user.name", "gh-shim", cwd=work)
    git("checkout", "-q", base, cwd=work)
    if mode == "merge":
        git("merge", "--no-ff", "-q", "-m", "Merge pull request #%d from %s" % (pr["number"], head),
            "origin/" + head, cwd=work)
    elif mode == "squash":
        git("merge", "--squash", "origin/" + head, cwd=work)
        git("commit", "-q", "-m", "%s (#%d)" % (pr["title"] or head, pr["number"]), cwd=work)
    else:
        git("checkout", "-q", "-b", "shim-rebase", "origin/" + head, cwd=work)
        git("rebase", "-q", base, cwd=work)
        git("checkout", "-q", base, cwd=work)
        git("merge", "--ff-only", "-q", "shim-rebase", cwd=work)
    git("push", "-q", "origin", base, cwd=work)
    if "--delete-branch" in argv or "-d" in argv:
        git("push", "-q", "origin", "--delete", head, cwd=work, check=False)
    pr["state"] = "MERGED"
    pr["mergedAt"] = datetime.now(timezone.utc).isoformat()
    save(st)


def main(argv):
    st = load()
    cmd = argv[:2]
    rest = argv[2:]
    if argv[:2] == ["auth", "status"]:
        print("github.invalid\n  Logged in to github.invalid (gh shim)")
        return
    if argv[:2] == ["repo", "view"]:
        repo = st["repo"]
        owner, name = repo.split("/", 1)
        data = {
            "nameWithOwner": repo, "name": name, "owner": {"login": owner},
            "defaultBranchRef": {"name": st["base"]}, "url": "https://github.invalid/" + repo,
            "viewerPermission": "ADMIN",
        }
        fields = opt(rest, "--json")
        if fields:
            emit(data, fields)
        else:
            print(repo)
        return
    if cmd == ["pr", "list"]:
        state = (opt(rest, "--state", "-s") or "open").upper()
        head = opt(rest, "--head", "-H")
        base = opt(rest, "--base", "-B")
        prs = [p for p in st["prs"] if state == "ALL" or p["state"] == state]
        prs = [p for p in prs if (not head or p["head"] == head) and (not base or p["base"] == base)]
        emit([pr_view(st, p) for p in prs], opt(rest, "--json") or "number,title,headRefName")
        return
    if cmd == ["pr", "view"]:
        ref = (positional(rest, {"--json", "--jq", "-q", "--repo", "-R"}) or [None])[0]
        pr = find_pr(st, ref)
        if pr is None:
            fail("no pull requests found")
        fields = opt(rest, "--json")
        if fields:
            emit(pr_view(st, pr), fields)
        else:
            print("title:\t%s\nstate:\t%s\nnumber:\t%d" % (pr["title"], pr["state"], pr["number"]))
        return
    if cmd == ["pr", "status"]:
        cur = [p for p in st["prs"] if p["head"] == current_branch() and p["state"] == "OPEN"]
        emit({
            "currentBranch": pr_view(st, cur[0]) if cur else None,
            "createdBy": [pr_view(st, p) for p in st["prs"] if p["state"] == "OPEN"],
            "needsReview": [],
        }, opt(rest, "--json"))
        return
    if cmd == ["pr", "create"]:
        head = opt(rest, "--head", "-H") or current_branch()
        base = opt(rest, "--base", "-B") or st["base"]
        title = opt(rest, "--title", "-t") or head
        ls = git("ls-remote", "--heads", st["origin"], head, check=False)
        if ls.returncode != 0 or not ls.stdout.strip():
            fail("pull request create failed: head branch %r not pushed to origin" % head)
        number = max([p["number"] for p in st["prs"]] + [0]) + 1
        st["prs"].append({"number": number, "head": head, "base": base, "title": title,
                          "body": opt(rest, "--body", "-b") or "", "state": "OPEN"})
        save(st)
        print("https://github.invalid/%s/pull/%d" % (st["repo"], number))
        return
    if cmd == ["pr", "merge"]:
        ref = (positional(rest, {"--json", "--jq", "-q", "--repo", "-R", "--subject", "-t",
                                 "--body", "-b"}) or [None])[0]
        pr = find_pr(st, ref)
        if pr is None:
            fail("no pull requests found")
        if pr["state"] != "OPEN":
            fail("Pull request #%d is already %s" % (pr["number"], pr["state"].lower()))
        merge_pr(st, pr, rest)
        print("Merged pull request #%d" % pr["number"])
        return
    if argv[:1] == ["api"] and len(argv) >= 2:
        endpoint = argv[1].lstrip("/")
        parts = endpoint.split("/")
        repo = st["repo"]
        if parts[0] == "repos" and len(parts) == 3:
            print(json.dumps({"full_name": repo, "default_branch": st["base"],
                              "permissions": {"admin": True, "push": True, "pull": True}}))
            return
        if parts[0] == "repos" and len(parts) >= 6 and parts[-1] == "protection":
            sys.stderr.write("gh: Branch not protected (HTTP 404)\n")
            sys.exit(1)
    unsupported(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
'''


def install_gh_shim(scenario: AgentScenario, workdir: Path, origin_path: Path) -> Path:
    """Write the shim + seeded state into ``<workdir>.bin/`` and return that directory."""
    bin_dir = workdir.parent / f"{workdir.name}.bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    base = scenario.fixture.base_branch
    state = {
        "repo": "local/fixture",
        "origin": str(origin_path),
        "base": base,
        "prs": [
            {
                "number": pr.number,
                "head": pr.head,
                "base": pr.base or base,
                "title": pr.title or pr.head,
                "body": "",
                "state": "OPEN",
            }
            for pr in scenario.fixture.prs
        ],
    }
    (bin_dir / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
    (bin_dir / UNSUPPORTED_LOG).write_text("", encoding="utf-8")
    shim = bin_dir / "gh"
    shim.write_text(f"#!{sys.executable}\n{SHIM_SOURCE}", encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def bin_dir_for(workdir: Path) -> Path:
    return workdir.parent / f"{workdir.name}.bin"


def origin_path_for(workdir: Path) -> Path:
    return workdir.parent / f"{workdir.name}.origin.git"


def unsupported_calls(bin_dir: Path) -> list[str]:
    log = bin_dir / UNSUPPORTED_LOG
    if not log.is_file():
        return []
    return [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]


__all__ = [
    "SHIM_SOURCE",
    "STATE_FILE",
    "UNSUPPORTED_LOG",
    "bin_dir_for",
    "install_gh_shim",
    "origin_path_for",
    "unsupported_calls",
]
