#!/usr/bin/env python3
"""Controlled subprocess used by real SRT behavioral probes."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.request import urlopen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("read", "write", "fetch", "env", "version"))
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    if args.action == "version":
        print("sandbox-vendor-fixture 1")
    elif args.action == "read":
        print(Path(args.value).read_text())
    elif args.action == "write":
        Path(args.value).write_text("sandbox-write\n")
    elif args.action == "fetch":
        print(urlopen(args.value, timeout=5).status)
    elif args.action == "env":
        print(os.environ.get(args.value, "<missing>"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
