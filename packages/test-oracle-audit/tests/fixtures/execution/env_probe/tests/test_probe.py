import json
import os
from pathlib import Path


def test_report_environment(tmp_path):
    home = Path.home()
    home.mkdir(parents=True, exist_ok=True)
    (home / ".probe-marker").write_text("written by the audited test")
    report = {
        "home": str(home),
        "tmpdir": os.environ.get("TMPDIR"),
        "xdg_cache_home": os.environ.get("XDG_CACHE_HOME"),
        "tmp_path": str(tmp_path),
    }
    print("PROBE" + json.dumps(report))
