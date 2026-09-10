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


DEPLOYED_SURFACE_PREFIX = """\
You are performing an ADVERSARIAL review of a DEPLOYED SURFACE — a service that \
is running right now, not a diff. You are given its base URL, its contract, and \
the WHEN/THEN scenarios it claims to satisfy.

Review the SYSTEM, not the source. The scanners already cover what rules can \
express: ZAP checks response headers and common web weaknesses, dependency \
scanners check known CVEs, and the behavioural validator checks that the \
declared scenarios pass. Repeating those wastes the one thing you can do that \
they cannot, which is REASON ABOUT INTENT.

Concentrate on:
1. Authorization boundaries: can one principal reach another's data by changing \
an identifier? Does every write check the same tenant the read checked?
2. Business-logic flaws: a sequence of individually-legal calls that reaches an \
illegal state — double-spend, replay, an approval that approves itself.
3. State and concurrency: what does a partial failure leave behind? What happens \
when two callers race the same transition?
4. Contract-vs-behaviour gaps: something the contract permits that the scenarios \
never exercise, and that would be dangerous if a client did it.
5. Trust assumptions: what does this surface believe about its caller, its \
network position, or its own configuration that an attacker could falsify?

Say what you would DO to demonstrate each finding — the request sequence, the \
state it would leave. A finding nobody can reproduce is a hypothesis, and \
labelling it as such is more useful than overstating it.

Your findings are ADVISORY. They are ranked and read by a human; they do not \
block a merge, because a non-reproducible verdict cannot be a gate. That is \
freedom, not demotion: report the thing you are 60% sure about and say you are \
60% sure, rather than suppressing it or dressing it up as certainty.

Output your findings using the SAME JSON schema (review-findings.schema.json) \
as a standard review. Use existing finding types — 'security', 'correctness', \
'resilience', 'architecture' — and do NOT invent new ones.

--- END DEPLOYED-SURFACE ADVERSARIAL INSTRUCTIONS ---

"""


def wrap_deployed_surface(
    prompt: str,
    *,
    base_url: str,
    contract_excerpt: str = "",
    scenario_excerpt: str = "",
) -> str:
    """Frame a review of a running service rather than of a diff.

    The evidence class is NOT set here, and deliberately so. It is declared at
    ingest by the caller that chose this reviewer
    (``consensus_synthesizer --judgment-vendor``), because a model asked to
    label its own findings non-blocking has every incentive to do the opposite.
    The prompt tells the model its findings are advisory so that it reports
    honest uncertainty; the guarantee lives elsewhere.
    """
    context = [f"TARGET: {base_url}"]
    if contract_excerpt:
        context.append(f"\nCONTRACT:\n{contract_excerpt}")
    if scenario_excerpt:
        context.append(f"\nDECLARED SCENARIOS:\n{scenario_excerpt}")
    return DEPLOYED_SURFACE_PREFIX + "\n".join(context) + "\n\n" + prompt

