"""Verify that an implementation exposes no surface its contract omits (D1).

The contract is the declared surface and introspection may not populate it —
that is what makes an unreachable implementation unable to shrink the surface
coverage is measured against. Introspection still has one job, and it runs in
one direction only: the implementation must be a **subset** of the contract.

Excess is a contract violation. A route, tool or flag a user can reach that
nothing documents is a defect in the contract, the implementation, or both, and
no other check in the framework can see it — the drift guards only prove the
generator agrees with the contract, which stays true while the contract rots
into a subset of reality.

Omission is **not** reported here. A contracted element the implementation
never grew is a coverage gap, and the coverage model already names it. Emitting
it from both places would deliver one defect twice under two names, and the
count would look like two problems.

Each verifier takes the live artifact and a descriptor, and returns violations:

    verify_argparse(parser, descriptor)  # CLI

None of them import the framework being introspected. FastAPI and the MCP SDK
are consumer dependencies, not gen-eval's; taking the already-materialised
document or listing keeps it that way.
"""

from __future__ import annotations

from gen_eval.verify.model import Violation, declared_elements
from gen_eval.verify.surfaces import verify_argparse

__all__ = [
    "Violation",
    "declared_elements",
    "verify_argparse",
]
