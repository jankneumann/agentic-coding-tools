#!/usr/bin/env python3
"""Sanitize session log content to remove secrets and sensitive information.

Reads a session-log markdown file, detects and redacts secrets, high-entropy
strings, and environment-specific paths, then writes the sanitized output.

Exit codes:
  0 — Success (no secrets found, or all successfully redacted)
  1 — Sanitization error (content may still contain secrets)
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

# --- Secret detection patterns ---

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Specific vendor patterns first (before generic ones)
    ("aws-access-key", re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])")),
    ("aws-secret-key", re.compile(
        r"(?i)(?:aws_secret_access_key|aws_secret)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"
    )),
    ("github-token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("private-key", re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    )),
    ("connection-string", re.compile(
        r"(?i)(?:postgres(?:ql)?|mysql|mongodb|redis|amqp)://\S+"
    )),
    # Generic patterns last
    ("api-key", re.compile(
        r"(?i)(?:api[_-]?key|apikey)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?"
    )),
    ("bearer-token", re.compile(
        r"(?i)(?:bearer|token|authorization)\s*[=:]\s*['\"]?([A-Za-z0-9_\-.]{20,})['\"]?"
    )),
    ("password", re.compile(
        r"(?i)(?:password|passwd|pwd)\s*[=:]\s*['\"]?(\S{8,})['\"]?"
    )),
    ("generic-secret", re.compile(
        r"(?i)(?:secret|credential|auth_token)\s*[=:]\s*['\"]?(\S{8,})['\"]?"
    )),
    ("env-var-value", re.compile(
        r"(?i)(?:export\s+)?[A-Z_]{2,}(?:_KEY|_SECRET|_TOKEN|_PASSWORD|_CREDENTIAL)\s*=\s*['\"]?(\S+)['\"]?"
    )),
]

# Patterns that should NOT be redacted (common development identifiers)
ALLOWLIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^[0-9a-f]{7,40}$"),  # git SHAs
    re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE),  # UUIDs
    re.compile(r"^openspec/"),  # OpenSpec paths
    re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,50}[a-z0-9])?$"),  # kebab-case identifiers (change-ids, max 52 chars)
]

# Home directory patterns to normalize
HOME_DIR_PATTERN = re.compile(r"/(?:home|Users)/[a-zA-Z0-9_.-]+/")
HOSTNAME_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9./:-])(?:[a-zA-Z0-9-]+\.)+(?:internal|local|corp|lan|private|company)\b"
)


def shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string in bits per character."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )


def is_allowlisted(s: str) -> bool:
    """Check if a string matches known safe patterns."""
    return any(p.match(s) for p in ALLOWLIST_PATTERNS)


def redact_secrets(content: str) -> tuple[str, list[dict[str, str]]]:
    """Detect and redact known secret patterns.

    Returns:
        Tuple of (sanitized content, list of redaction records).
    """
    redactions: list[dict[str, str]] = []
    result = content

    for secret_type, pattern in SECRET_PATTERNS:
        def replace_match(m: re.Match[str], st: str = secret_type) -> str:
            redactions.append({"type": st, "position": str(m.start())})
            return f"[REDACTED:{st}]"

        result = pattern.sub(replace_match, result)

    return result, redactions


def redact_high_entropy(content: str) -> tuple[str, list[dict[str, str]]]:
    """Detect and redact high-entropy strings that may be secrets.

    Targets strings >20 chars with entropy >4.5 bits/char that aren't
    known safe patterns (UUIDs, SHAs, change-ids).
    """
    redactions: list[dict[str, str]] = []

    # Match quoted strings or long non-whitespace tokens
    token_pattern = re.compile(r"""(?:['"]([^'"]{21,})['"])|(?:(?<!\w)([A-Za-z0-9/+=_\-]{21,})(?!\w))""")

    def check_and_redact(m: re.Match[str]) -> str:
        token = m.group(1) or m.group(2)
        if token is None:
            return m.group(0)
        if is_allowlisted(token):
            return m.group(0)
        entropy = shannon_entropy(token)
        if entropy > 4.5:
            redactions.append({
                "type": "high-entropy",
                "entropy": f"{entropy:.2f}",
                "position": str(m.start()),
            })
            return "[REDACTED:high-entropy]"
        return m.group(0)

    result = token_pattern.sub(check_and_redact, content)
    return result, redactions


def normalize_paths(content: str) -> str:
    """Normalize environment-specific paths."""
    result = HOME_DIR_PATTERN.sub("~/", content)
    result = HOSTNAME_PATTERN.sub("[HOST]", result)
    return result


def sanitize(content: str) -> tuple[str, list[dict[str, str]]]:
    """Run the full sanitization pipeline.

    Returns:
        Tuple of (sanitized content, all redaction records).
    """
    all_redactions: list[dict[str, str]] = []

    # Step 1: Redact known secret patterns
    content, redactions = redact_secrets(content)
    all_redactions.extend(redactions)

    # Step 2: Redact high-entropy strings
    content, redactions = redact_high_entropy(content)
    all_redactions.extend(redactions)

    # Step 3: Normalize paths
    content = normalize_paths(content)

    return content, all_redactions


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize session log to remove secrets and sensitive information."
    )
    parser.add_argument("input", help="Input session-log file path")
    parser.add_argument("output", help="Output sanitized file path")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print redaction summary without writing output"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        content = input_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        return 1

    try:
        sanitized, redactions = sanitize(content)
    except Exception as e:
        print(f"Error during sanitization: {e}", file=sys.stderr)
        return 1

    if redactions:
        print(f"Sanitization: {len(redactions)} redaction(s) applied", file=sys.stderr)
        by_type: dict[str, int] = {}
        for r in redactions:
            t = r["type"]
            by_type[t] = by_type.get(t, 0) + 1
        for t, count in sorted(by_type.items()):
            print(f"  - {t}: {count}", file=sys.stderr)
    else:
        print("Sanitization: no secrets detected", file=sys.stderr)

    if args.dry_run:
        return 0

    output_path = Path(args.output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(sanitized, encoding="utf-8")
    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
