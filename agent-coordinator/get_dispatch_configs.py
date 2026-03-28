#!/usr/bin/env python3
"""Print agent dispatch configs as JSON. Works from any working directory.

Usage:
    python get_dispatch_configs.py                # use default agents.yaml
    python get_dispatch_configs.py /path/to.yaml  # use explicit agents.yaml
"""
import json
import os
import sys
from pathlib import Path

# Ensure the agent-coordinator package is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agents_config import get_dispatch_configs, load_agents_config

if __name__ == "__main__":
    agents = None
    if len(sys.argv) > 1:
        agents = load_agents_config(Path(sys.argv[1]))
    print(json.dumps(get_dispatch_configs(agents)))
