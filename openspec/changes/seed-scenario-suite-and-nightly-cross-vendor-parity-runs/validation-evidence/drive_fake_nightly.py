import sys
from pathlib import Path
sys.path.insert(0, ".")
from agent_scenarios import FakeExecutor, load_scenarios
from agent_scenarios.nightly import run_nightly
from agent_scenarios.__main__ import main
from tests.test_nightly_config import write_config
from tests.test_seed_outcomes import outcome_module
from tests.conftest import SCENARIOS_DIR

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
cfg = write_config(root, scenarios_dir=str(SCENARIOS_DIR))
print("== dry-run")
print("rc", main(["nightly", "--dry-run", "--config", str(cfg)]))


def fac(c):
    return FakeExecutor({s.id: outcome_module(s.id).golden for s in load_scenarios(SCENARIOS_DIR)})


print("== run rc", run_nightly(cfg, executor_factory=fac))
st = str(root / "state" / "results.jsonl")
for sub in (["trend", "--group-by", "vendor,skill"], ["latest"], ["query"]):
    print("== results", sub)
    print("rc", main(["results", sub[0], "--store", st, *sub[1:]]))
