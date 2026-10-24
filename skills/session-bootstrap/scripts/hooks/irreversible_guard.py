#!/usr/bin/env python3
"""PreToolUse hook: deny or ask on irreversible Bash commands, stay silent otherwise.

Claude Code pipes the PreToolUse payload on stdin. For a Bash call the hook
parses ``tool_input.command`` and answers in one of three ways:

* exit 2 with the reason on stderr: **deny**. History rewrites, remote
  deletion, recursive force-deletes, ``curl | sh``. Denied in every
  permission mode, including Auto.
* exit 0 with a ``permissionDecision: "ask"`` JSON: **ask**. Merges, data
  destruction, deploys, secret writes. The user confirms each one.
* exit 0 with no output: **no opinion**. The normal permission rules apply,
  so everything that is not irreversible runs without a prompt in Auto mode.

The command is split on unquoted ``&&``, ``||``, ``;``, ``|``, ``&`` and
newlines, and each part is normalized before matching: leading ``VAR=…``
assignments, ``env``, ``sudo``, ``timeout``, ``xargs`` and similar wrappers are
dropped, ``sh -c '…'`` / ``eval`` / ``$(…)`` bodies are checked recursively,
and git's global options (``-C <path>``, ``-c k=v``) are skipped. Rules match
on the command word, so ``grep "git push --force" log`` is not a push.

This is a second layer, not a boundary: a script that shells out
(``python x.py`` calling ``git push -f``) is invisible here. The sandbox and
credential scoping come first (docs/proposals/factory-local-cloud-split.md,
Phase 0).

The coordinator's ``FALLBACK_PATTERNS`` in agent-coordinator/src/guardrails.py
is the server-side list for the same classes. The two are kept in step by
``skills/tests/session-bootstrap/test_irreversible_guard.py``, which fails
when guardrails gains a pattern this hook does not cover.

An internal error in the hook asks rather than denies, so a parser bug costs
one prompt instead of disabling Bash for the session. Registration uses
``"onFailure": "block"`` so a hook that cannot start fails closed.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from dataclasses import dataclass

DENY = "deny"
ASK = "ask"


@dataclass(frozen=True)
class Verdict:
    decision: str  # DENY or ASK
    reason: str


# --------------------------------------------------------------------------
# Splitting and normalization
# --------------------------------------------------------------------------

_SEPARATORS = ("&&", "||", ";", "|", "&", "\n")

# Wrappers whose remaining words are themselves a command, with the flags
# that consume a value.
_TRANSPARENT = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-U"},
    "doas": {"-u", "-C"},
    "nice": {"-n"},
    "command": set(),
    "exec": {"-a"},
    "nohup": set(),
    "time": set(),
    "builtin": set(),
}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# Shell grammar that can precede a command word inside one segment.
_KEYWORDS = {"(", "{", "!", "if", "then", "else", "elif", "do", "while", "until"}
_GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_XARGS_WITH_VALUE = {"-n", "-I", "-L", "-P", "-d", "-E", "-s", "-a", "--max-args", "--replace"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
_HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_MAX_DEPTH = 5


def strip_heredocs(command: str) -> str:
    """Drop heredoc bodies: they are data written somewhere, not commands."""
    out: list[str] = []
    pending: list[str] = []
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        out.append(line)
        pending = [m.group(2) for m in _HEREDOC.finditer(line)]
    return "\n".join(out)


def split_compound(command: str) -> list[str]:
    """Split on separators that are not inside quotes or escaped."""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(command):
                buf.append(command[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "\\" and i + 1 < len(command):
            buf.append(command[i : i + 2])
            i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        sep = next((s for s in _SEPARATORS if command.startswith(s, i)), None)
        if sep:
            parts.append("".join(buf))
            parts.append(sep)  # kept so pipelines can be inspected
            buf = []
            i += len(sep)
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:  # unbalanced quotes: fall back to whitespace
        return segment.split()


def _strip_wrappers(words: list[str]) -> list[str]:
    """Drop assignments and wrapper commands until the real command word."""
    while words:
        if words[0] in _KEYWORDS:
            words = words[1:]
            continue
        if words[0].startswith("(") and len(words[0]) > 1:  # (git push -f)
            words = [words[0].lstrip("("), *words[1:]]
        head = os.path.basename(words[0])
        if _ASSIGNMENT.match(words[0]):
            words = words[1:]
        elif head in _TRANSPARENT:
            takes_value = _TRANSPARENT[head]
            words = words[1:]
            while words and words[0].startswith("-"):  # sudo -u x, nice -n 5
                if words.pop(0) in takes_value and words:
                    words.pop(0)
        elif head == "env":
            words = words[1:]
            while words and (words[0].startswith("-") or _ASSIGNMENT.match(words[0])):
                flag = words.pop(0)
                if flag in ("-u", "--unset", "-C", "--chdir", "-S") and words:
                    words.pop(0)
        elif head == "timeout":
            words = words[1:]
            while words and words[0].startswith("-"):
                if words.pop(0) in ("-s", "--signal", "-k", "--kill-after") and words:
                    words.pop(0)
            words = words[1:]  # the duration
        elif head == "xargs":
            words = words[1:]
            while words and words[0].startswith("-"):
                flag = words.pop(0)
                if flag in _XARGS_WITH_VALUE and words:
                    words.pop(0)
        else:
            break
    return words


def _short_flags(words: list[str]) -> set[str]:
    """Letters from single-dash clusters (``-rf`` -> {r, f})."""
    letters: set[str] = set()
    for w in words:
        if w.startswith("-") and not w.startswith("--") and len(w) > 1:
            letters.update(w[1:])
    return letters


# --------------------------------------------------------------------------
# Rules, one function per command word
# --------------------------------------------------------------------------


def _git(args: list[str]) -> Verdict | None:
    while args and args[0].startswith("-"):
        flag = args.pop(0)
        if flag in _GIT_GLOBAL_WITH_VALUE and args:
            args.pop(0)
    if not args:
        return None
    sub, rest = args[0], args[1:]
    flags = _short_flags(rest)
    if sub == "push":
        if any(a == "--force" or a.startswith("--force-with-lease") or a == "--mirror" for a in rest) or "f" in flags:
            return Verdict(DENY, "force push rewrites remote history")
        positional = [a for a in rest if not a.startswith("-")]
        if any(a.startswith("+") for a in positional[1:]):
            return Verdict(DENY, "'+refspec' push is a force push")
        if "--delete" in rest or "d" in flags or any(a.startswith(":") for a in positional[1:]):
            return Verdict(DENY, "deleting a remote branch or tag")
        return None
    if sub == "reset" and "--hard" in rest:
        return Verdict(DENY, "git reset --hard discards uncommitted work")
    if sub == "clean" and ("f" in flags or "--force" in rest):
        return Verdict(DENY, "git clean -f deletes untracked files")
    if sub == "stash" and rest[:1] in (["drop"], ["clear"]):
        return Verdict(DENY, "dropping stashes loses work")
    if sub in ("filter-branch", "filter-repo"):
        return Verdict(ASK, "rewriting repository history")
    return None


def _rm(args: list[str]) -> Verdict | None:
    flags = _short_flags(args)
    recursive = bool(flags & {"r", "R"}) or "--recursive" in args
    force = "f" in flags or "--force" in args
    if recursive and force:
        return Verdict(DENY, "recursive force delete (rm -rf) cannot be undone")
    if _touches_secret(args):
        return Verdict(ASK, "deleting a secrets or credentials file")
    return None


def _find(args: list[str], depth: int) -> Verdict | None:
    if "-delete" in args:
        return Verdict(DENY, "find -delete removes files with no undo")
    for i, a in enumerate(args):
        if a in ("-exec", "-execdir", "-ok", "-okdir"):
            inner = []
            for w in args[i + 1 :]:
                if w in (";", "\\;", "+"):
                    break
                inner.append(w)
            found = _check_words([w for w in inner if w != "{}"], depth + 1)
            if found:
                return found
    return None


def _gh(args: list[str]) -> Verdict | None:
    if args[:2] == ["repo", "delete"]:
        return Verdict(DENY, "gh repo delete is permanent")
    if args[:2] == ["release", "delete"]:
        return Verdict(DENY, "gh release delete is permanent")
    if args[:2] == ["pr", "merge"]:
        if "--admin" in args:
            return Verdict(DENY, "gh pr merge --admin bypasses branch protection")
        return Verdict(ASK, "merging a pull request")
    if args[:1] == ["api"]:
        for i, a in enumerate(args):
            method = None
            if a in ("-X", "--method") and i + 1 < len(args):
                method = args[i + 1]
            elif a.startswith(("-X", "--method=")) and a not in ("-X", "--method"):
                method = a.split("=", 1)[-1] if "=" in a else a[2:]
            if method and method.upper() == "DELETE":
                return Verdict(DENY, "gh api DELETE removes a remote resource")
    return None


_SQL_DESTRUCTIVE = re.compile(r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE)\b", re.IGNORECASE)
_DB_CLIENTS = {"psql", "mysql", "sqlite3", "pgcli", "cockroach", "supabase"}


def _db(word: str, args: list[str]) -> Verdict | None:
    if word in ("dropdb", "dropuser"):
        return Verdict(ASK, f"{word} destroys data")
    if word == "alembic" and args[:1] == ["downgrade"]:
        return Verdict(ASK, "alembic downgrade can drop columns and tables")
    if word in _DB_CLIENTS and _SQL_DESTRUCTIVE.search(" ".join(args)):
        return Verdict(ASK, "DROP/TRUNCATE destroys data")
    return None


def _infra(word: str, args: list[str]) -> Verdict | None:
    sub = args[0] if args else ""
    if word == "railway" and sub in ("up", "down", "delete", "redeploy", "remove"):
        return Verdict(ASK, f"railway {sub} changes a deployed service")
    if word == "kubectl" and sub in ("apply", "delete", "replace"):
        return Verdict(ASK, f"kubectl {sub} changes a cluster")
    if word == "terraform" and sub in ("apply", "destroy"):
        return Verdict(ASK, f"terraform {sub} changes infrastructure")
    if word == "docker" and sub == "push":
        return Verdict(ASK, "docker push publishes an image")
    if word in ("bao", "vault") and sub == "kv" and len(args) > 1:
        if args[1] in ("put", "delete", "destroy", "patch", "metadata"):
            return Verdict(ASK, f"{word} kv {args[1]} changes a stored secret")
    return None


_SECRET_PATH = re.compile(
    r"(^|/)(\.env(\.(?!example$|sample$|template$)[\w.-]+)?"
    r"|[\w.-]*(credentials|secrets|passwords)\.(json|ya?ml|txt)"
    r"|\.netrc|\.git-credentials|id_(rsa|ed25519|ecdsa))$"
)
_WRITERS = {"tee", "cp", "mv", "install", "truncate", "ln", "dd"}


def _touches_secret(args: list[str]) -> bool:
    return any(_SECRET_PATH.search(a) for a in args if not a.startswith("-"))


_REDIRECT = re.compile(r"(?:^|[^<>&0-9])\d*>>?\|?\s*(['\"]?)([^\s'\";&|<>]+)\1")


def _secret_write(segment: str, word: str, args: list[str]) -> Verdict | None:
    for m in _REDIRECT.finditer(segment):
        if _SECRET_PATH.search(m.group(2)):
            return Verdict(ASK, f"writing to {m.group(2)}")
    in_place = word == "sed" and any(a == "-i" or a.startswith(("-i", "--in-place")) for a in args)
    if (word in _WRITERS or in_place) and _touches_secret(args):
        return Verdict(ASK, "writing to a secrets or credentials file")
    return None


_DOWNLOADERS = {"curl", "wget"}


def _command_word(segment: str) -> str:
    words = _strip_wrappers(_words(segment))
    return os.path.basename(words[0]) if words else ""


def _pipes_download_to_shell(parts: list[str]) -> bool:
    """``curl … | sh`` across real pipeline segments, not inside a quoted argument."""
    return any(
        parts[i + 1] == "|"
        and _command_word(parts[i]) in _DOWNLOADERS
        and _command_word(parts[i + 2]) in _SHELLS
        for i in range(0, len(parts) - 2, 2)
    )


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def _check_words(words: list[str], depth: int, segment: str = "") -> Verdict | None:
    words = _strip_wrappers(list(words))
    if not words:
        return None
    word, args = os.path.basename(words[0]), words[1:]

    if word in _SHELLS:
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a and i + 1 < len(args):
                return check(args[i + 1], depth + 1)
        return None
    if word == "eval":
        return check(" ".join(args), depth + 1)
    if word == "git":
        found = _git(args)
    elif word == "rm":
        found = _rm(args)
    elif word == "find":
        found = _find(args, depth)
    elif word == "gh":
        found = _gh(args)
    elif word == "mkfs" or word.startswith("mkfs."):
        found = Verdict(DENY, "formatting a filesystem")
    else:
        found = _db(word, args) or _infra(word, args)
    if word == "dd" and any(a.startswith("of=/dev/") for a in args):
        found = Verdict(DENY, "dd onto a device overwrites it")
    return found or _secret_write(segment, word, args)


def check(command: str, depth: int = 0) -> Verdict | None:
    """Return the strictest verdict for a command string, or None."""
    if depth > _MAX_DEPTH:
        return Verdict(ASK, "command nests shells too deeply to inspect")
    command = strip_heredocs(command)
    verdicts: list[Verdict] = []
    parts = split_compound(command)
    if _pipes_download_to_shell(parts):
        verdicts.append(Verdict(DENY, "piping a download into a shell runs unreviewed code"))
    for m in _SUBSTITUTION.finditer(command):
        inner = check(m.group(1) if m.group(1) is not None else m.group(2), depth + 1)
        if inner:
            verdicts.append(inner)
    for segment in parts:
        if segment in _SEPARATORS or not segment.strip():
            continue
        found = _check_words(_words(segment), depth, segment)
        if found:
            verdicts.append(found)
    if not verdicts:
        return None
    denies = [v for v in verdicts if v.decision == DENY]
    return denies[0] if denies else verdicts[0]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # not a payload we understand; normal rules apply
    if payload.get("tool_name", "Bash") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return 0
    try:
        verdict = check(command)
    except Exception as exc:  # noqa: BLE001 — a parser bug must cost a prompt, not Bash
        verdict = Verdict(ASK, f"irreversible_guard could not parse the command ({exc.__class__.__name__})")
    if verdict is None:
        return 0
    reason = f"irreversible_guard: {verdict.reason}"
    if verdict.decision == DENY:
        print(f"{reason}. Ask the user to run it themselves if it is intended.", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
