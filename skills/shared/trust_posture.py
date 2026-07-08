"""Trust posture contract loader and validator.

The *trust posture contract* is a repo-owned governance file that turns the
autopilot/roadmap human gates from prose instructions into machine-readable
policy objects. For each named gate it declares a *disposition*:

- ``auto``                — proceed without a human, log the decision.
- ``notify_with_timeout`` — file an approval, notify, poll until ``timeout_seconds``
                            elapses, then apply ``default_action`` (``proceed`` | ``block``).
- ``block``               — park the loop and wait for a human (today's behavior).

The active contract lives at ``<repo_root>/TRUST_POSTURE.md`` as a YAML
front-matter block (fenced with ``---``) followed by human-readable prose. A
documented starter lives at ``<repo_root>/TRUST_POSTURE.template.md``; operators
opt in by copying it to ``TRUST_POSTURE.md`` and flipping gates.

Backward-compatibility guarantee (the critical invariant this module protects):
when the contract file is **absent**, every gate resolves to ``block`` — byte
-identical to the pre-contract behavior. A gate that is present in the file but
omits an entry also resolves to ``block`` (fail-closed). Only a *typo* — an
unknown gate name or an unknown disposition — is treated as an error and fails
validation loudly, so operators cannot silently mis-spell their way past a gate.

This module is the loader/validator that the ri-05 *approval gate service*
(``skills/shared/approval_gate.py``) builds on. Its public surface is deliberately
small and side-effect-free::

    from shared.trust_posture import load_posture, Gate, Disposition

    posture = load_posture()                     # reads TRUST_POSTURE.md fresh each call
    gd = posture.disposition_for(Gate.MERGE)     # -> GateDisposition
    if gd.disposition is Disposition.AUTO:
        proceed()
    elif gd.disposition is Disposition.NOTIFY_WITH_TIMEOUT:
        wait(gd.timeout_seconds); apply(gd.default_action)
    else:  # BLOCK
        park()

``load_posture`` re-reads the file on every call (no caching), so editing the
contract is picked up on the next gate evaluation — the "hot-reloadable" property.

CLI (skills shell out from markdown)::

    python -m shared.trust_posture validate [PATH]   # exit 0 valid, 2 invalid, 1 io error
    python -m shared.trust_posture show [PATH]        # print resolved dispositions
"""
from __future__ import annotations

import enum
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union

try:  # PyYAML ships in skills/.venv; guarded so import errors are actionable.
    import yaml
except ImportError as exc:  # pragma: no cover - environment guard
    raise ImportError(
        "trust_posture requires PyYAML; install it into the skills venv"
    ) from exc

DEFAULT_CONTRACT_FILENAME = "TRUST_POSTURE.md"
TEMPLATE_FILENAME = "TRUST_POSTURE.template.md"
SCHEMA_VERSION = 1


class Gate(str, enum.Enum):
    """The eight human gates governed by the contract.

    Canonical (snake_case) names are the on-disk keys. The comment after each is
    the prose gate name used in the always-on-automation proposal / SKILL.md.
    """

    GATEKEEPER_ESCALATION = "gatekeeper_escalation"          # GATEKEEPER escalation
    PROPOSAL_APPROVAL = "proposal_approval"                  # proposal approval
    PLAN_REVIEW_CONVERGENCE_FAILURE = "plan_review_convergence_failure"  # plan-review convergence failure
    VALIDATION_FAILURE = "validation_failure"               # validation failure
    ESCALATE_RESUME = "escalate_resume"                     # ESCALATE resume
    REPLAN_REQUIRED = "replan_required"                     # replan_required
    PR_CREATION = "pr_creation"                             # PR creation
    MERGE = "merge"                                         # merge


class Disposition(str, enum.Enum):
    AUTO = "auto"
    NOTIFY_WITH_TIMEOUT = "notify_with_timeout"
    BLOCK = "block"


class DefaultAction(str, enum.Enum):
    """Action applied when a ``notify_with_timeout`` gate's timer expires."""

    PROCEED = "proceed"
    BLOCK = "block"


class PostureValidationError(ValueError):
    """Raised when a contract file is present but malformed or invalid.

    ``errors`` holds every problem found in one pass so operators can fix them
    all at once rather than one per run.
    """

    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors) or "invalid trust posture contract")


@dataclass(frozen=True)
class GateDisposition:
    """Resolved policy for a single gate.

    ``timeout_seconds`` and ``default_action`` are populated only for
    ``notify_with_timeout``; they are ``None`` for ``auto`` and ``block``.
    """

    disposition: Disposition
    timeout_seconds: Optional[int] = None
    default_action: Optional[DefaultAction] = None

    @property
    def is_block(self) -> bool:
        return self.disposition is Disposition.BLOCK

    @property
    def is_auto(self) -> bool:
        return self.disposition is Disposition.AUTO


# The fail-closed default: applied to every gate when the file is absent, and to
# any individual gate the file does not configure. This single constant is the
# structural anchor of the backward-compatibility guarantee.
BLOCK = GateDisposition(disposition=Disposition.BLOCK)


@dataclass(frozen=True)
class TrustPosture:
    """A resolved trust posture. ``present`` distinguishes a loaded file from the
    absent-file (all-block) default so callers can log which authorized them."""

    gates: dict
    present: bool = False
    source_path: Optional[Path] = None

    def disposition_for(self, gate: Union[Gate, str]) -> GateDisposition:
        """Return the resolved disposition for ``gate``.

        Unknown gate names raise ``ValueError`` (gates are a closed set — a typo
        must not silently resolve to anything). Known-but-unconfigured gates and
        the absent-file case both return :data:`BLOCK`.
        """
        return self.gates.get(_coerce_gate(gate), BLOCK)

    def is_present(self) -> bool:
        return self.present


def _coerce_gate(gate: Union[Gate, str]) -> Gate:
    if isinstance(gate, Gate):
        return gate
    try:
        return Gate(gate)
    except ValueError:
        known = ", ".join(g.value for g in Gate)
        raise ValueError(f"unknown gate {gate!r}; known gates: {known}") from None


def default_contract_path(repo_root: Optional[Union[str, Path]] = None) -> Path:
    """Resolve the active contract path (``<repo_root>/TRUST_POSTURE.md``)."""
    root = Path(repo_root) if repo_root is not None else _find_repo_root()
    return root / DEFAULT_CONTRACT_FILENAME


def _find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk up from ``start`` (or cwd) looking for a ``.git`` marker; fall back to cwd."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return here


# --------------------------------------------------------------------------- #
# Parsing + validation
# --------------------------------------------------------------------------- #

def _parse_front_matter(text: str) -> dict:
    """Extract and parse the leading ``---`` fenced YAML block into a mapping."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PostureValidationError(
            ["contract file must begin with a YAML front-matter fence '---'"]
        )
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            raw = "\n".join(lines[1:idx])
            try:
                data = yaml.safe_load(raw)
            except yaml.YAMLError as exc:
                raise PostureValidationError([f"front matter is not valid YAML: {exc}"]) from None
            if data is None:
                data = {}
            if not isinstance(data, dict):
                raise PostureValidationError(["front matter must be a YAML mapping"])
            return data
    raise PostureValidationError(
        ["unterminated YAML front matter (missing closing '---')"]
    )


def _build_gate_disposition(name: str, cfg: dict) -> tuple[Optional[GateDisposition], list]:
    errors: list = []
    disp_raw = cfg.get("disposition")
    if disp_raw is None:
        return None, [f"gate {name!r}: missing required 'disposition'"]
    try:
        disposition = Disposition(disp_raw)
    except ValueError:
        known = ", ".join(d.value for d in Disposition)
        return None, [f"gate {name!r}: unknown disposition {disp_raw!r} (expected one of: {known})"]

    timeout = cfg.get("timeout_seconds")
    default_action_raw = cfg.get("default_action")

    if disposition is Disposition.NOTIFY_WITH_TIMEOUT:
        if timeout is None:
            errors.append(f"gate {name!r}: notify_with_timeout requires 'timeout_seconds'")
        elif isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            errors.append(
                f"gate {name!r}: 'timeout_seconds' must be a positive integer, got {timeout!r}"
            )
        default_action: Optional[DefaultAction] = None
        if default_action_raw is None:
            errors.append(f"gate {name!r}: notify_with_timeout requires 'default_action'")
        else:
            try:
                default_action = DefaultAction(default_action_raw)
            except ValueError:
                known = ", ".join(a.value for a in DefaultAction)
                errors.append(
                    f"gate {name!r}: unknown default_action {default_action_raw!r} (expected one of: {known})"
                )
        if errors:
            return None, errors
        return GateDisposition(
            disposition=disposition,
            timeout_seconds=int(timeout),
            default_action=default_action,
        ), errors

    # auto / block: timeout_seconds and default_action are not applicable. Reject
    # them if present so a mis-placed timeout can't hide behind an auto gate.
    if timeout is not None:
        errors.append(
            f"gate {name!r}: 'timeout_seconds' is only valid for notify_with_timeout"
        )
    if default_action_raw is not None:
        errors.append(
            f"gate {name!r}: 'default_action' is only valid for notify_with_timeout"
        )
    if errors:
        return None, errors
    return GateDisposition(disposition=disposition), errors


def _build_posture(data: dict, source_path: Optional[Path]) -> TrustPosture:
    errors: list = []

    schema_version = data.get("schema_version")
    if schema_version is None:
        errors.append("missing required field 'schema_version'")
    elif schema_version != SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version {schema_version!r} (expected {SCHEMA_VERSION})"
        )

    gates_raw = data.get("gates")
    if gates_raw is None:
        errors.append("missing required field 'gates'")
        gates_raw = {}
    elif not isinstance(gates_raw, dict):
        errors.append("'gates' must be a mapping of gate name -> config")
        gates_raw = {}

    resolved: dict = {}
    for name, cfg in gates_raw.items():
        try:
            gate = Gate(name)
        except ValueError:
            known = ", ".join(g.value for g in Gate)
            errors.append(f"unknown gate {name!r} (known gates: {known})")
            continue
        if not isinstance(cfg, dict):
            errors.append(f"gate {name!r}: config must be a mapping, got {type(cfg).__name__}")
            continue
        gd, gate_errors = _build_gate_disposition(name, cfg)
        errors.extend(gate_errors)
        if gd is not None:
            resolved[gate] = gd

    if errors:
        raise PostureValidationError(errors)
    return TrustPosture(gates=resolved, present=True, source_path=source_path)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def load_posture(
    repo_root: Optional[Union[str, Path]] = None,
    *,
    path: Optional[Union[str, Path]] = None,
) -> TrustPosture:
    """Load the active trust posture.

    Resolution order: explicit ``path`` if given, else ``<repo_root>/TRUST_POSTURE.md``
    (``repo_root`` defaults to the git root discovered from cwd).

    When the file is **absent**, returns an empty, ``present=False`` posture whose
    ``disposition_for`` returns :data:`BLOCK` for every gate — the backward-compat
    default. When the file is present but invalid, raises
    :class:`PostureValidationError`.
    """
    contract_path = Path(path) if path is not None else default_contract_path(repo_root)
    if not contract_path.exists():
        return TrustPosture(gates={}, present=False, source_path=None)
    text = contract_path.read_text(encoding="utf-8")
    data = _parse_front_matter(text)
    return _build_posture(data, source_path=contract_path)


def validate_posture_file(path: Union[str, Path]) -> list:
    """Validate a contract file. Returns a list of error strings (empty == valid).

    Unlike :func:`load_posture`, this never raises for *validation* problems — it
    collects them — so callers (CLI, CI, ri-05 preflight) can report all at once.
    A missing file is reported as a single error (validation targets a real file);
    use :func:`load_posture` for the absent-file-is-fine path.
    """
    p = Path(path)
    if not p.exists():
        return [f"contract file not found: {p}"]
    try:
        data = _parse_front_matter(p.read_text(encoding="utf-8"))
        _build_posture(data, source_path=p)
    except PostureValidationError as exc:
        return list(exc.errors)
    return []


def _main(argv: list) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    command = argv[0]
    target = Path(argv[1]) if len(argv) > 1 else default_contract_path()
    if command == "validate":
        if not target.exists():
            print(f"absent: {target} (all gates resolve to block — valid by default)")
            return 0
        errors = validate_posture_file(target)
        if errors:
            for err in errors:
                print(f"error: {err}", file=sys.stderr)
            return 2
        print(f"valid: {target}")
        return 0
    if command == "show":
        posture = load_posture(path=target if target.exists() else None)
        print(f"present: {posture.present}")
        for gate in Gate:
            gd = posture.disposition_for(gate)
            extra = ""
            if gd.disposition is Disposition.NOTIFY_WITH_TIMEOUT:
                extra = f" timeout={gd.timeout_seconds}s default={gd.default_action.value}"
            print(f"  {gate.value}: {gd.disposition.value}{extra}")
        return 0
    print(f"unknown command {command!r}; use validate|show", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main(sys.argv[1:]))
