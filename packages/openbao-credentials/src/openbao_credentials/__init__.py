"""Shared, typed OpenBao credentials boundary."""

from .adapter import (
    BaoCredentialError,
    BootstrapPaths,
    ErrorCode,
    OpenBaoClient,
    PrincipalOpenBaoConfig,
    SecretPayload,
    Session,
    bootstrap_paths,
)
from .topology import (
    Principal,
    PrincipalTopology,
    ProjectionError,
    agent_principal_id,
    project_principals,
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
    "SecretPayload",
    "bootstrap_paths",
]
