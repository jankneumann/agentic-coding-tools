"""Shared, typed OpenBao credentials boundary."""

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
]
