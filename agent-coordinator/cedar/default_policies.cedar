// Default Cedar policies for Agent Coordinator.
//
// These policies implement equivalent behavior to the native engine
// (ProfilesService + NetworkPolicyService) using Cedar's PARC model.
//
// Cedar semantics: default-deny, forbid overrides permit.

// ============================================================
// READ OPERATIONS — Permit for all agents
// ============================================================

permit(
    principal,
    action == Action::"check_locks",
    resource
);

permit(
    principal,
    action == Action::"get_work",
    resource
);

permit(
    principal,
    action == Action::"recall",
    resource
);

permit(
    principal,
    action == Action::"discover_agents",
    resource
);

permit(
    principal,
    action == Action::"read_handoff",
    resource
);

permit(
    principal,
    action == Action::"query_audit",
    resource
);

// ============================================================
// WRITE OPERATIONS — Permit for trust_level >= 2
// ============================================================

permit(
    principal,
    action == Action::"acquire_lock",
    resource
) when {
    principal.trust_level >= 2
};

permit(
    principal,
    action == Action::"release_lock",
    resource
) when {
    principal.trust_level >= 2
};

permit(
    principal,
    action == Action::"complete_work",
    resource
) when {
    principal.trust_level >= 2
};

permit(
    principal,
    action == Action::"submit_work",
    resource
) when {
    principal.trust_level >= 2
};

permit(
    principal,
    action == Action::"remember",
    resource
) when {
    principal.trust_level >= 2
};

permit(
    principal,
    action == Action::"write_handoff",
    resource
) when {
    principal.trust_level >= 2
};

permit(
    principal,
    action == Action::"check_guardrails",
    resource
) when {
    principal.trust_level >= 2
};

// ============================================================
// ADMIN OPERATIONS — Permit for trust_level >= 3
// ============================================================

permit(
    principal,
    action == Action::"force_push",
    resource
) when {
    principal.trust_level >= 3
};

permit(
    principal,
    action == Action::"delete_branch",
    resource
) when {
    principal.trust_level >= 3
};

permit(
    principal,
    action == Action::"cleanup_agents",
    resource
) when {
    principal.trust_level >= 3
};

// ============================================================
// SUSPENDED AGENTS — Forbid all for trust_level 0
// ============================================================

forbid(
    principal,
    action,
    resource
) when {
    principal.trust_level == 0
};

// ============================================================
// NETWORK ACCESS — Allow known package registries
// ============================================================

permit(
    principal,
    action == Action::"network_access",
    resource == Domain::"github.com"
);

permit(
    principal,
    action == Action::"network_access",
    resource == Domain::"registry.npmjs.org"
);

permit(
    principal,
    action == Action::"network_access",
    resource == Domain::"pypi.org"
);

permit(
    principal,
    action == Action::"network_access",
    resource == Domain::"api.github.com"
);

permit(
    principal,
    action == Action::"network_access",
    resource == Domain::"raw.githubusercontent.com"
);
