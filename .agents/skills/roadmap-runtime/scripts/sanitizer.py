"""Sanitization utilities for roadmap artifacts.

Prevents secret exposure in persisted state by detecting and redacting
credentials, tokens, raw prompts, and environment variable values.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate sensitive content
_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"(?:api[_-]?key|apikey)\s*[:=]\s*\S+", re.IGNORECASE)),
    ("token", re.compile(r"(?:token|bearer)\s*[:=]\s*\S+", re.IGNORECASE)),
    ("password", re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE)),
    ("secret", re.compile(r"(?:secret|private[_-]?key)\s*[:=]\s*\S+", re.IGNORECASE)),
    ("env_var", re.compile(r"\$\{[A-Z_]+\}", re.IGNORECASE)),
    ("base64_key", re.compile(r"[A-Za-z0-9+/]{40,}={1,2}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")),
]

# Fields that should never contain raw content
_PROHIBITED_FIELDS = {
    "raw_prompt",
    "raw_response",
    "auth_header",
    "session_token",
    "credentials",
    "env_value",
}


def sanitize_string(text: str) -> str:
    """Redact sensitive patterns from a string."""
    result = text
    for name, pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub(f"[REDACTED:{name}]", result)
    return result


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitize a dictionary, removing prohibited fields and redacting values."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key in _PROHIBITED_FIELDS:
            result[key] = f"[REDACTED:{key}]"
        elif isinstance(value, str):
            result[key] = sanitize_string(value)
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize_dict(v) if isinstance(v, dict)
                else sanitize_string(v) if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result


def validate_no_secrets(data: dict[str, Any]) -> list[str]:
    """Check for potential secrets in a dictionary. Returns list of warnings."""
    warnings: list[str] = []
    _check_recursive(data, "", warnings)
    return warnings


def _check_recursive(data: Any, path: str, warnings: list[str]) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if key in _PROHIBITED_FIELDS:
                warnings.append(f"Prohibited field at {current_path}")
            _check_recursive(value, current_path, warnings)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _check_recursive(item, f"{path}[{i}]", warnings)
    elif isinstance(data, str):
        for name, pattern in _SENSITIVE_PATTERNS:
            if pattern.search(data):
                warnings.append(f"Potential {name} at {path}")
                break
