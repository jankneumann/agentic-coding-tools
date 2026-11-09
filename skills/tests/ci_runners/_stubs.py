"""Command stubs for the runner-kit and tooling tests (no network, no host mutation)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

CURL_STUB = r"""#!/usr/bin/env python3
import json, os, re, sys

args = sys.argv[1:]
method, url, hdr, out, fmt, data = None, None, None, None, "", None
i = 0
while i < len(args):
    a = args[i]
    if a == "-X": method = args[i + 1]; i += 2; continue
    if a == "-D": hdr = args[i + 1]; i += 2; continue
    if a == "-o": out = args[i + 1]; i += 2; continue
    if a == "-w": fmt = args[i + 1]; i += 2; continue
    if a == "-d": data = args[i + 1]; i += 2; continue
    if a in ("-H", "--max-time"): i += 2; continue
    if a.startswith("-"): i += 1; continue
    url = a; i += 1
method = method or ("POST" if data is not None else "GET")
cfg = json.load(open(os.environ["STUB_CONFIG"]))
log = open(os.environ["STUB_LOG"], "a")
log.write(json.dumps({"method": method, "url": url, "data": data, "argv": args}) + "\n")
log.close()
state_path = os.environ["STUB_CONFIG"] + ".state"
state = json.load(open(state_path)) if os.path.exists(state_path) else {}
chosen = None
for idx, route in enumerate(cfg["routes"]):
    if route["method"] != method or not re.search(route["pattern"], url):
        continue
    used = state.get(str(idx), 0)
    if "times" in route and used >= route["times"]:
        continue
    state[str(idx)] = used + 1
    chosen = route
    break
json.dump(state, open(state_path, "w"))
if chosen is None:
    chosen = {"status": 404, "body": {}, "headers": {}}
if hdr:
    with open(hdr, "w") as fh:
        fh.write("HTTP/2 %d\r\n" % chosen["status"])
        for k, v in chosen.get("headers", {}).items():
            fh.write("%s: %s\r\n" % (k, v))
if out:
    with open(out, "w") as fh:
        json.dump(chosen.get("body", {}), fh)
if "http_code" in fmt:
    sys.stdout.write(str(chosen["status"]))
"""


def install_curl_stub(bin_dir: Path, config: dict, tmp: Path) -> tuple[dict[str, str], Path]:
    """Write a stub ``curl`` into ``bin_dir``; return (env additions, call-log path)."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "curl"
    stub.write_text(CURL_STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    cfg = tmp / "stub-config.json"
    cfg.write_text(json.dumps(config))
    log = tmp / "stub-calls.jsonl"
    log.write_text("")
    env = {"STUB_CONFIG": str(cfg), "STUB_LOG": str(log)}
    return env, log


def read_calls(log: Path) -> list[dict]:
    return [json.loads(x) for x in log.read_text().splitlines() if x.strip()]


def path_with(bin_dir: Path) -> str:
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


GH_STUB = r"""#!/usr/bin/env python3
import json, os, re, sys
from urllib.parse import parse_qs, urlparse

argv = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": argv}) + "\n")
cfg = json.load(open(os.environ["STUB_GH_CONFIG"]))
if not argv or argv[0] != "api":
    sys.stderr.write("stub gh: only 'gh api' is supported\n"); sys.exit(2)
url = [a for a in argv[1:] if a.startswith("repos/")][-1]
u = urlparse(url)
q = {k: v[0] for k, v in parse_qs(u.query).items()}
p = u.path
if re.search(r"/actions/workflows/[^/]+/runs$", p):
    per, page = int(q.get("per_page", 30)), int(q.get("page", 1))
    total = cfg["total_runs"]
    ids = list(range(1, total + 1))[(page - 1) * per: page * per]
    runs = [{"id": i, "conclusion": "success", "status": "completed", "head_sha": q.get("head_sha", "sha1"),
             "event": q.get("event", "push"), "run_started_at": "2026-01-01T00:00:00Z",
             "updated_at": "2026-01-01T00:10:00Z"} for i in ids]
    out = {"total_count": total, "workflow_runs": runs}
elif re.search(r"/actions/runs/(\d+)/jobs$", p):
    rid = re.search(r"/runs/(\d+)/jobs", p).group(1)
    out = {"jobs": cfg.get("jobs_by_run", {}).get(rid, cfg.get("default_jobs", []))}
elif re.search(r"/actions/runs/(\d+)$", p):
    out = cfg["run"]
elif "/contents/" in p:
    sys.stdout.write(cfg["workflow_text"]); sys.exit(0)
else:
    sys.stderr.write("stub gh: unhandled " + url + "\n"); sys.exit(1)
sys.stdout.write(json.dumps(out))
"""


def install_gh_stub(bin_dir: Path, config: dict, tmp: Path) -> tuple[dict[str, str], Path]:
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "gh"
    stub.write_text(GH_STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    cfg = tmp / "gh-config.json"
    cfg.write_text(json.dumps(config))
    log = tmp / "gh-calls.jsonl"
    log.write_text("")
    return {"STUB_GH_CONFIG": str(cfg), "STUB_LOG": str(log)}, log
