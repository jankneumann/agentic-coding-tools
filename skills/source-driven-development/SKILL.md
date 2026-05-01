---
name: source-driven-development
description: |
  Grounds every framework-specific implementation decision in official documentation.
  Loaded by orchestrator skills (plan-feature, implement-feature, parallel-review-*)
  when a worker is about to write code that depends on a specific library or framework
  version. Encodes the DETECT -> FETCH -> IMPLEMENT -> CITE flow, the 4-tier source
  hierarchy (official docs > official blog/changelog > MDN/web standards > caniuse),
  stack-detection from dependency files (package.json, pyproject.toml, requirements.txt,
  go.mod, Cargo.toml, Gemfile), and the mandatory full-URL citation rule. Defers to the
  vendor-specific authority skills (langfuse, neon-postgres, use-railway,
  supabase-postgres-best-practices, claimable-postgres) when the code touches their
  domain.
category: Methodology
tags: [methodology, documentation, citation, framework, versions, authority]
triggers:
  - "source-driven development"
  - "verify documentation"
  - "fetch official docs"
  - "cite sources"
  - "framework-specific code"
user_invocable: false
related:
  - langfuse
  - neon-postgres
  - use-railway
  - supabase-postgres-best-practices
  - claimable-postgres
---

# Source-Driven Development

## Overview

Every framework-specific code decision must be backed by official documentation. Don't
implement from memory — verify, cite, and let the user see your sources. Training data
goes stale, APIs get deprecated, best practices evolve. This skill ensures the user gets
code they can trust because every pattern traces back to an authoritative source they
can check.

This skill is **orchestrator-loaded**, not a slash command. `plan-feature`,
`implement-feature`, and the parallel-review skills consult it when a worker is about
to write framework-specific code. For known third-party domains, defer to the vendor
authority skill before fetching general docs:

| Domain | Authority skill | Defer to it for |
|---|---|---|
| Langfuse SDK / API | `langfuse` | Tracing, prompts, datasets, scores, sessions |
| Neon Serverless Postgres | `neon-postgres` | Connection strings, branching, autoscaling, Neon CLI |
| Railway infrastructure | `use-railway` | Project/service/env management, deploys, domains |
| Supabase / general Postgres patterns | `supabase-postgres-best-practices` | Query design, indexing, RLS, schema |
| Claimable Postgres (neon.new) | `claimable-postgres` | Throwaway DBs, no-signup provisioning |

If the task falls in one of those domains, the related skill is the authority — its
SKILL.md and references are the FETCH step. For everything else, follow the flow below.

## When to Use

- Writing code that depends on a specific framework or library version
- Building boilerplate, starter code, or patterns that will be copied across a project
- The user explicitly asks for documented, verified, or "correct" implementation
- Implementing features where the framework's recommended approach matters (forms,
  routing, data fetching, state management, auth, retries, transports)
- Reviewing or improving code that uses framework-specific patterns
- Any time you are about to write framework-specific code from memory

**When NOT to use:**

- Correctness does not depend on a specific version (renaming variables, fixing typos,
  moving files)
- Pure logic that works the same across all versions (loops, conditionals, data
  structures)
- The user explicitly wants speed over verification ("just do it quickly")

## The Process

```
DETECT --> FETCH --> IMPLEMENT --> CITE
  |          |           |            |
  v          v           v            v
 What       Get the    Follow the   Show your
 stack?     relevant   documented   sources
            docs       patterns
```

### Step 1: Detect Stack and Versions

Read the project's dependency file to identify exact versions:

| File | Ecosystem |
|---|---|
| `package.json`, `package-lock.json`, `pnpm-lock.yaml` | Node / React / Vue / Angular / Svelte |
| `pyproject.toml`, `uv.lock`, `requirements.txt`, `Pipfile` | Python / Django / Flask / FastAPI |
| `composer.json`, `composer.lock` | PHP / Symfony / Laravel |
| `go.mod`, `go.sum` | Go |
| `Cargo.toml`, `Cargo.lock` | Rust |
| `Gemfile`, `Gemfile.lock` | Ruby / Rails |
| `pubspec.yaml` | Dart / Flutter |
| `*.csproj`, `packages.lock.json` | .NET |

State what you found explicitly:

```
STACK DETECTED:
- React 19.1.0 (from package.json)
- Vite 6.2.0
- Tailwind CSS 4.0.3
-> Fetching official docs for the relevant patterns.
```

Or for a Python project:

```
STACK DETECTED:
- httpx 0.28.1 (from pyproject.toml)
- tenacity 9.0.0
- Python 3.12
-> Fetching official docs for httpx transports + tenacity retry patterns.
```

If versions are missing or ambiguous, **ask the user**. Don't guess — the version
determines which patterns are correct.

### Step 2: Fetch Official Documentation

Fetch the specific documentation page for the feature you're implementing. Not the
homepage, not the full docs — the relevant page.

**Source hierarchy (in order of authority):**

| Priority | Source | Example |
|----------|--------|---------|
| 1 | Official documentation | react.dev, docs.djangoproject.com, www.python-httpx.org, docs.python.org |
| 2 | Official blog / changelog / release notes | react.dev/blog, nextjs.org/blog, github.com/encode/httpx/releases |
| 3 | Web standards references | MDN, web.dev, html.spec.whatwg.org, peps.python.org |
| 4 | Browser/runtime compatibility | caniuse.com, node.green, pythontest.org, packaging.python.org |

**Not authoritative — never cite as primary sources:**

- Stack Overflow answers
- Blog posts or tutorials (even popular ones)
- AI-generated documentation or summaries
- Your own training data (that is the whole point — verify it)

**Be precise with what you fetch:**

```
BAD:  Fetch the React homepage
GOOD: Fetch react.dev/reference/react/useActionState

BAD:  Fetch the httpx homepage
GOOD: Fetch www.python-httpx.org/advanced/transports/#retries

BAD:  Search "django authentication best practices"
GOOD: Fetch docs.djangoproject.com/en/6.0/topics/auth/
```

After fetching, extract the key patterns and note any deprecation warnings or
migration guidance.

When official sources conflict with each other (e.g. a migration guide contradicts the
API reference), surface the discrepancy to the user and verify which pattern actually
works against the detected version.

### Step 3: Implement Following Documented Patterns

Write code that matches what the documentation shows:

- Use the API signatures from the docs, not from memory
- If the docs show a new way to do something, use the new way
- If the docs deprecate a pattern, don't use the deprecated version
- If the docs don't cover something, flag it as unverified

**When docs conflict with existing project code:**

```
CONFLICT DETECTED:
The existing codebase uses useState for form loading state,
but React 19 docs recommend useActionState for this pattern.
(Source: https://react.dev/reference/react/useActionState)

Options:
A) Use the modern pattern (useActionState) — consistent with current docs
B) Match existing code (useState) — consistent with codebase
-> Which approach do you prefer?
```

Surface the conflict. Don't silently pick one.

### Step 4: Cite Your Sources

Every framework-specific pattern gets a citation. The user must be able to verify every
decision.

**In code comments (TypeScript / React example):**

```typescript
// React 19 form handling with useActionState
// Source: https://react.dev/reference/react/useActionState#usage
const [state, formAction, isPending] = useActionState(submitOrder, initialState);
```

**In code comments (Python / httpx example):**

```python
# httpx retry transport with exponential backoff
# Source: https://www.python-httpx.org/advanced/transports/#retries
import httpx

transport = httpx.AsyncHTTPTransport(retries=3)
client = httpx.AsyncClient(transport=transport, timeout=10.0)
```

**In conversation:**

```
I'm using useActionState instead of manual useState for the
form submission state. React 19 replaced the manual
isPending/setIsPending pattern with this hook.

Source: https://react.dev/blog/2024/12/05/react-19#actions
"useTransition now supports async functions [...] to handle
pending states automatically"
```

**Citation rules:**

- Full URLs, not shortened
- Prefer deep links with anchors where possible
  (e.g. `/useActionState#usage` over `/useActionState`) — anchors survive doc
  restructuring better than top-level pages
- Quote the relevant passage when it supports a non-obvious decision
- Include browser/runtime support data when recommending platform features
- If you cannot find documentation for a pattern, say so explicitly:

```
UNVERIFIED: I could not find official documentation for this
pattern. This is based on training data and may be outdated.
Verify before using in production.
```

Honesty about what you couldn't verify is more valuable than false confidence.

## Worked Example: Async Retry on an httpx Client

End-to-end run of the four steps for the scenario "I need to add async retry logic to
an httpx client":

### DETECT

Read `pyproject.toml` (or `uv.lock`) and confirm the version:

```toml
# pyproject.toml
[project]
dependencies = [
  "httpx>=0.28,<0.29",
  "tenacity>=9.0",
]
```

State the finding:

```
STACK DETECTED:
- httpx 0.28.x (from pyproject.toml [project.dependencies])
- tenacity 9.x (available for retry decoration)
- Python 3.12
-> Fetching httpx transport docs and tenacity README.
```

### FETCH

Fetch the specific page:

- Primary: `https://www.python-httpx.org/advanced/transports/#retries` — this is where
  the `httpx.AsyncHTTPTransport(retries=N)` pattern lives.
- Secondary: `https://github.com/jd/tenacity#retrying-library-for-python` — for
  jitter-aware exponential backoff if the transport-level retry is not sufficient
  (e.g. you need to retry on application-level errors, not just connection errors).

Read both. Note that the httpx `retries` parameter only retries connection errors, not
HTTP status codes — that is a deprecation-style gotcha worth quoting.

### IMPLEMENT

Write code that matches what the docs show:

```python
"""Async retry pattern for an httpx client.

Connection-level retries handled by httpx.AsyncHTTPTransport(retries=N).
Application-level retries (5xx responses) layered on top with tenacity.
"""
from __future__ import annotations

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


def make_client() -> httpx.AsyncClient:
    # Connection-level retry: only retries on connection errors, NOT on 5xx.
    # Source: https://www.python-httpx.org/advanced/transports/#retries
    transport = httpx.AsyncHTTPTransport(retries=3)
    return httpx.AsyncClient(transport=transport, timeout=10.0)


async def fetch_with_retry(client: httpx.AsyncClient, url: str) -> httpx.Response:
    # Application-level retry on 5xx + transient httpx errors.
    # Source: https://tenacity.readthedocs.io/en/latest/#retrying-code-block
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=0.5, max=8.0),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        reraise=True,
    ):
        with attempt:
            response = await client.get(url)
            response.raise_for_status()
            return response
    raise RuntimeError("unreachable")  # tenacity reraises before getting here
```

### CITE

Every non-obvious decision is cited inline as a code comment with a full URL. In the
PR description or chat, the worker also surfaces the gotcha:

```
Note: httpx's transport-level `retries=3` only covers connection failures
(per https://www.python-httpx.org/advanced/transports/#retries).
For 5xx responses, we layer tenacity's AsyncRetrying on top —
otherwise the client retries connection drops but immediately
surfaces a 503 to the caller.
```

If the user later asks "why two layers?", every claim is grounded in a fetched URL.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I'm confident about this API" | Confidence is not evidence. Training data contains outdated patterns that look correct but break against current versions. Verify. |
| "Fetching docs wastes tokens" | Hallucinating an API wastes more. The user debugs for an hour, then discovers the function signature changed. One fetch prevents hours of rework. |
| "The docs won't have what I need" | If the docs don't cover it, that's valuable information — the pattern may not be officially recommended. |
| "I'll just mention it might be outdated" | A disclaimer doesn't help. Either verify and cite, or clearly flag it as unverified. Hedging is the worst option. |
| "This is a simple task, no need to check" | Simple tasks with wrong patterns become templates. The user copies your deprecated form handler into ten components before discovering the modern approach exists. |

## Red Flags

- Writing framework-specific code without checking the docs for that version
- Using "I believe" or "I think" about an API instead of citing the source
- Implementing a pattern without knowing which version it applies to
- Citing Stack Overflow or blog posts instead of official documentation
- Using deprecated APIs because they appear in training data
- Not reading `package.json` / `pyproject.toml` / equivalent before implementing
- Delivering code without source citations for framework-specific decisions
- Fetching an entire docs site when only one page is relevant
- Bypassing a vendor authority skill (e.g. answering a Langfuse question from training
  data instead of consulting the `langfuse` skill)

## Verification

After implementing with source-driven development:

- [ ] Framework and library versions were identified from the dependency file
- [ ] If the task domain matches a vendor authority skill, that skill was consulted first
- [ ] Official documentation was fetched for framework-specific patterns
- [ ] All sources are official documentation, not blog posts or training data
- [ ] Code follows the patterns shown in the current version's documentation
- [ ] Non-trivial decisions include source citations with full URLs
- [ ] No deprecated APIs are used (checked against migration guides)
- [ ] Conflicts between docs and existing code were surfaced to the user
- [ ] Anything that could not be verified is explicitly flagged as unverified
