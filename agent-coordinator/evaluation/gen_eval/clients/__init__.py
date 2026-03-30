"""Transport clients for executing scenario steps against live services.

Each client implements the TransportClient protocol and handles a specific
transport type (HTTP, MCP, CLI, DB, wait). The TransportClientRegistry
maps transport names to client instances for the evaluator.
"""

from __future__ import annotations

from .base import StepContext, StepResult, TransportClient, TransportClientRegistry
from .cli_client import CliClient
from .db_client import DbClient
from .http_client import HttpClient
from .mcp_client import McpClient
from .wait_client import WaitClient

__all__ = [
    "CliClient",
    "DbClient",
    "HttpClient",
    "McpClient",
    "StepContext",
    "StepResult",
    "TransportClient",
    "TransportClientRegistry",
    "WaitClient",
]
