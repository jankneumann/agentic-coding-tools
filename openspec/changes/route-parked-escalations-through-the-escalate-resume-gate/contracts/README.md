# Contracts

This change adds no new wire, database, or event schema. It composes the existing supervised-dispatch result, delegated-attempt, gate-decision, and supervisor-record contracts. The observable Python return value adds a bounded `escalation_resolutions` list while preserving existing keys.
