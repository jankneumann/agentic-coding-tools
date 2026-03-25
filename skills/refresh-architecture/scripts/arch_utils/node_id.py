"""Node ID creation, parsing, and format conversion.

All scripts should use these helpers rather than constructing IDs by hand.
"""

from __future__ import annotations

import re


def _sanitize_qualified_name(name: str) -> str:
    """Normalise a qualified name: strip, collapse whitespace to underscores."""
    return re.sub(r"\s+", "_", name.strip())


def make_node_id(prefix: str, qualified_name: str) -> str:
    """Build a stable node ID: ``{prefix}:{sanitized_name}``.

    >>> make_node_id("py", "app.service.get_users")
    'py:app.service.get_users'
    >>> make_node_id("pg", "public.users")
    'pg:public.users'
    """
    return f"{prefix}:{_sanitize_qualified_name(qualified_name)}"


def parse_node_id(node_id: str) -> tuple[str, str]:
    """Split a node ID into ``(prefix, qualified_name)``.

    >>> parse_node_id("py:app.service.get_users")
    ('py', 'app.service.get_users')
    """
    prefix, _, qualified = node_id.partition(":")
    return prefix, qualified


def mermaid_id(raw: str) -> str:
    """Convert an arbitrary string into a collision-resistant Mermaid identifier.

    Uses deterministic replacements so names that differ only in separator
    characters (e.g. ``a-b.c`` vs ``a.b.c``) produce distinct IDs.

    >>> mermaid_id("py:agent-coordinator.locks")
    'py_c_agent_h_coordinator__locks'
    >>> mermaid_id("py:agent.coordinator.locks")
    'py_c_agent__coordinator__locks'
    """
    out: list[str] = []
    for ch in raw:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        elif ch == ".":
            out.append("__")
        elif ch == "-":
            out.append("_h_")
        elif ch == "/":
            out.append("_s_")
        elif ch == ":":
            out.append("_c_")
        else:
            out.append("_")
    return "".join(out)
