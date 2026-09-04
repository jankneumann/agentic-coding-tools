"""Single trust-level resolver shared by every enforcement path.

There used to be two resolvers: the fail-loud one in :mod:`src.coordination_api`
(HTTP write endpoints) and a verbatim pre-change copy inside
``WorkQueueService`` (claim / complete / submit guardrails). The copy failed
open — no registry check, no ``enabled`` check, ``except Exception`` →
default trust — so the same broken projection produced a 500 on one path and a
silent grant of trust 2 on the other. This module is the one implementation
both now call.
"""

from __future__ import annotations

from fastapi import HTTPException

from .config import get_config

#: ``ProfileResult.source`` value meaning "an explicit
#: ``agent_profile_assignments`` row pointed this agent at this profile", as
#: opposed to ``'default'`` (the ``agent_type`` fallback inside
#: ``get_agent_profile()``, which serves the oldest enabled row of the type).
#:
#: This is the *only* provenance that credits a non-registry principal below;
#: anything else — including ``None`` and any value this module does not know —
#: yields the default trust level. ``ProfilesService`` caches provenance
#: alongside the profile precisely so that a cache hit still carries it: it
#: used to report ``source="cache"`` on every hit, which made every cached
#: lookup of an assigned profile fall through to the default. Do not "fix" a
#: future variant of that by widening this set; widening it re-admits the
#: type-fallback escalation the gate below exists to close.
ASSIGNMENT_SOURCE = "assignment"


class TrustResolutionError(HTTPException):
    """A registry-declared agent has no usable profile row (design D3).

    Surfaced as a 500-class response, not a 403: the caller did nothing wrong.
    The registry projection — which startup sync is supposed to materialize —
    is broken, which is a coordinator configuration fault.
    """

    def __init__(self, agent_id: str, agent_type: str, reason: str) -> None:
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.reason = reason
        super().__init__(
            status_code=500,
            detail=(
                f"Trust level unresolvable for registry-declared agent "
                f"'{agent_id}' (type '{agent_type}'): {reason}. The "
                f"agent_profiles projection of agents.yaml is broken; "
                f"restart the coordinator to re-run profile sync."
            ),
        )


async def _audit_trust_resolution_failure(
    agent_id: str, agent_type: str, reason: str
) -> None:
    """Record a failed trust resolution; never masks the original fault."""
    try:
        from .audit import get_audit_service

        await get_audit_service().log_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="trust_resolution_failed",
            parameters={"agent_id": agent_id, "agent_type": agent_type},
            result={"reason": reason},
            success=False,
            error_message=reason,
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "Could not audit trust resolution failure for '%s'",
            agent_id,
            exc_info=True,
        )


async def resolve_trust_level(agent_id: str, agent_type: str) -> int:
    """Resolve effective trust level for guardrail evaluation.

    Fail-loud is scoped to *registry-declared* agents (design D3):

    - a principal absent from ``agents.yaml`` (env-var-configured externals,
      tests) falls back to the configured default trust level, because the
      registry cannot be authoritative for principals it does not name;
    - a registry-declared agent whose profile row is missing, disabled, or is
      **not the profile the registry declared** raises
      :class:`TrustResolutionError` and emits an audit event. Returning a
      default trust level there would be the fail-open drift this change
      exists to remove — the projection machinery itself has failed.

    Two properties matter more than they look:

    ``name`` equality, not "some profile resolved"
        ``get_agent_profile()`` falls back to the oldest enabled row of the
        agent's *type* when the agent has no assignment row. A registry agent
        that lands on a sibling profile therefore silently inherits that
        sibling's trust level. Comparing the resolved ``profile.name`` to
        ``registry_entry.profile`` is what makes the projection actually
        enforced rather than merely assumed. ``source == 'assignment'`` is
        deliberately *not* additionally required: with
        ``PROFILE_SYNC_ENABLED=false``, or before the first sync, there are no
        assignment rows, and a correct name match via the type fallback is
        still correct.

    ``source`` gating for non-registry principals
        Retiring an agent from ``agents.yaml`` disables its profile *and*
        deletes its assignment row. The principal is then unknown to the
        registry, has no assignment, and the type fallback happily hands it a
        *sibling* profile — which may sit above ``MIN_ADMIN_TRUST``.
        Decommissioning would promote. So an unknown principal is credited
        with a profile's trust level only when an explicit assignment binds it
        there; a type-fallback match yields the default trust level.
    """
    from .agents_config import get_agent_config
    from .profiles import get_profiles_service

    registry_entry = get_agent_config(agent_id)
    default_trust_level = get_config().profiles.default_trust_level

    try:
        profile_result = await get_profiles_service().get_profile(
            agent_id=agent_id,
            agent_type=agent_type,
        )
    except Exception as exc:
        if registry_entry is None:
            return default_trust_level
        reason = f"profile lookup failed: {exc}"
        await _audit_trust_resolution_failure(agent_id, agent_type, reason)
        raise TrustResolutionError(agent_id, agent_type, reason) from exc

    profile = profile_result.profile
    if not profile_result.success:
        profile = None

    if registry_entry is None:
        if (
            profile is not None
            and profile.enabled
            and profile_result.source == ASSIGNMENT_SOURCE
        ):
            return profile.trust_level
        return default_trust_level

    if profile is None:
        reason = f"no profile row named '{registry_entry.profile}'"
    elif not profile.enabled:
        reason = "profile row is disabled"
    elif profile.name != registry_entry.profile:
        reason = (
            f"resolved profile '{profile.name}' is not the registry-declared "
            f"profile '{registry_entry.profile}'"
        )
    else:
        return profile.trust_level

    await _audit_trust_resolution_failure(agent_id, agent_type, reason)
    raise TrustResolutionError(agent_id, agent_type, reason)
