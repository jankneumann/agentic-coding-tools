"""External benchmark adapters.

Thin adapters that convert external benchmark task formats
into the internal EvalTask format for use with the harness.
"""

from .contextbench import ContextBenchAdapter
from .marble import MARBLEAdapter
from .swebench import SWEBenchAdapter

__all__ = ["ContextBenchAdapter", "MARBLEAdapter", "SWEBenchAdapter"]
