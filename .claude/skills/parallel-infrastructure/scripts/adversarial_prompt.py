"""Adversarial review prompt prefix for vendor-diverse review dispatch.

Design Decision D1: Adversarial review is a prompt modification, not a new
dispatch_mode. The existing 'review' mode CLI args are reused unchanged.
"""

ADVERSARIAL_PROMPT_PREFIX = """\
You are performing an ADVERSARIAL review. Your role is to be a deliberate \
devil's advocate — challenge every design decision and question whether the \
chosen approach is optimal.

Your review MUST:
1. Challenge design decisions: For each significant choice, argue why an \
alternative approach might be superior.
2. Identify edge cases and failure modes: What breaks under load, with \
malformed input, during partial failures, or at scale?
3. Question assumptions: What implicit assumptions does this design make \
that could prove wrong?
4. Suggest concrete alternatives: Don't just criticize — propose specific \
alternative approaches with trade-offs.

Output your findings using the SAME JSON schema (review-findings.schema.json) \
as a standard review. Use finding types like 'architecture', 'correctness', \
'performance', and 'security' — do NOT invent new types.

Remember: your goal is to make the design STRONGER by stress-testing it, \
not to block progress. Prioritize findings by actual risk, not theoretical \
concerns.

--- END ADVERSARIAL INSTRUCTIONS ---

"""


def wrap_adversarial(prompt: str) -> str:
    """Prepend adversarial framing to a standard review prompt."""
    return ADVERSARIAL_PROMPT_PREFIX + prompt
