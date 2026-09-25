"""Shared, typed OpenBao credentials boundary."""

from .topology import (
    Principal,
    PrincipalTopology,
    ProjectionError,
    agent_principal_id,
    project_principals,
)
from .adapter import (
    BaoCredentialError,
    BootstrapPaths,
    ErrorCode,
    OpenBaoClient,
    PrincipalOpenBaoConfig,
    Session,
    bootstrap_paths,
)

__all__ = [
    "Principal",
    "PrincipalTopology",
    "ProjectionError",
    "agent_principal_id",
    "project_principals",
    "BaoCredentialError",
    "BootstrapPaths",
    "ErrorCode",
    "OpenBaoClient",
    "PrincipalOpenBaoConfig",
    "Session",
    "bootstrap_paths",
]
