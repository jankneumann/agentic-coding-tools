#!/usr/bin/env python3
"""Deterministic half of the cite-requirements walkthrough.

Division of labour (this is the skill's central property, per D1 of
trace-requirements-to-contracts):

- This script prints ONLY verbatim file content and computed status. Every
  requirement body, contract slice, and file:line reference it emits is read
  from disk, unmodified. It never suggests, ranks, or infers a citation.
- Interpretation — the orchestrator's reading, and the multi-model semantic
  annotations — is appended by the orchestrating agent OUTSIDE this script,
  under an explicitly labelled section. Provenance is therefore structural:
  if this script printed it, it is a quote; if not, it is interpretation.
- The DECISION is the operator's alone. `apply` subcommands transcribe a
  decision that has already been made; they validate it (ids resolve, the
  block is well-formed, exactly-one-of citation/exclusion) and journal it.

Runs under the gen-eval project venv so it can reuse the gate's own parsing
(`gen_eval.traceability`) instead of growing a drifting reimplementation:

    uv run --project packages/gen-eval python \
        <skill-base-dir>/scripts/walkthrough.py <command> ...

Pure text-manipulation paths (block location, insertion, card slicing) are
importable with stdlib + pyyaml only, so the skills test suite exercises them
without the gen-eval venv; `gen_eval` is imported lazily where resolution is
genuinely needed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import yaml

# Flags sit at this exact indent in the CLI contract (see
# openspec/contracts/gen-eval-framework/cli/gen-eval.yaml): list items under
# `commands[].flags` are `      - name: --x` (6 spaces), their keys at 8.
FLAG_ITEM_RE = re.compile(r"^      - name: (?P<name>--[a-z0-9][a-z0-9-]*)\s*$")
FLAG_KEY_INDENT = 8

DEFAULT_CAPABILITY = "gen-eval-framework"
DEFAULT_CONTRACT = "openspec/contracts/gen-eval-framework/cli/gen-eval.yaml"
JOURNAL_NAME = "traceability-decisions.yaml"

REQUIREMENT_ID_RE = re.compile(r"^(?P<capability>[a-z0-9][a-z0-9-]*)\.(?P<slug>[a-z0-9][a-z0-9-]*)$")


class WalkthroughError(Exception):
    """Operator-facing error; printed without a traceback."""


# ---------------------------------------------------------------------------
# Contract text manipulation (stdlib-only; unit-tested from skills/.venv)
# ---------------------------------------------------------------------------


def locate_flag_block(lines: list[str], flag: str) -> tuple[int, int]:
    """[start, end) line indices of one flag's list item.

    The block ends at the next flag item or at the first line whose content
    starts left of the flag-key indent (a parent key such as `exit_codes:`).
    Blank lines never terminate a block, but trailing blanks are excluded
    from it so insertions stay tight against the last real key.
    """
    start = None
    for i, line in enumerate(lines):
        m = FLAG_ITEM_RE.match(line)
        if m and m["name"] == flag:
            start = i
            break
    if start is None:
        raise WalkthroughError(f"flag {flag!r} not found as a flags[] item")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if FLAG_ITEM_RE.match(line) or indent < 6:
            end = j
            break
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return start, end


def flag_traceability_span(lines: list[str], start: int, end: int) -> tuple[int, int] | None:
    """[s, e) span of an existing `traceability:` key inside a flag block."""
    for i in range(start + 1, end):
        if lines[i].rstrip("\n") == " " * FLAG_KEY_INDENT + "traceability:":
            e = i + 1
            while e < end:
                nxt = lines[e]
                if nxt.strip() and (len(nxt) - len(nxt.lstrip(" "))) <= FLAG_KEY_INDENT:
                    break
                e += 1
            return i, e
    return None


def _fold_reason(reason: str, indent: int) -> list[str]:
    """A reason as a YAML folded scalar (`>-`), or a JSON-quoted fallback.

    textwrap normalises internal whitespace, which is exactly what makes the
    folded form safe: no produced line can begin with extra indentation (which
    YAML would preserve as a literal break) and no line is empty. Control
    characters fall back to a JSON string, which is valid YAML verbatim.
    """
    if any(ord(c) < 32 and c not in "\n\t " for c in reason):
        return [" " * indent + f"reason: {json.dumps(reason)}\n"]
    wrapped = textwrap.wrap(" ".join(reason.split()), width=max(20, 78 - indent - 2))
    if not wrapped:
        raise WalkthroughError("reason must not be empty (D13: a blank reason is an error)")
    out = [" " * indent + "reason: >-\n"]
    out.extend(" " * (indent + 2) + w + "\n" for w in wrapped)
    return out


def render_citation_block(req_ids: list[str]) -> list[str]:
    pad = " " * FLAG_KEY_INDENT
    out = [f"{pad}traceability:\n", f"{pad}  requirements:\n"]
    out.extend(f"{pad}    - {rid}\n" for rid in req_ids)
    return out


def render_exclusion_block(reason: str) -> list[str]:
    pad = " " * FLAG_KEY_INDENT
    return [f"{pad}traceability:\n", f"{pad}  excluded:\n"] + _fold_reason(
        reason, FLAG_KEY_INDENT + 4
    )


def insert_traceability(
    lines: list[str], flag: str, block: list[str], *, replace: bool = False
) -> list[str]:
    """Return new lines with `block` as the flag's traceability key.

    Fails if the flag already carries one, unless `replace` — the operator
    revisiting a decision must say so explicitly; silent overwrite would
    erase a previously journalled decision without a matching journal entry.
    """
    start, end = locate_flag_block(lines, flag)
    existing = flag_traceability_span(lines, start, end)
    if existing and not replace:
        raise WalkthroughError(
            f"flag {flag!r} already has a traceability block "
            f"(lines {existing[0] + 1}-{existing[1]}); pass --replace to revise"
        )
    if existing:
        s, e = existing
        lines = lines[:s] + lines[e:]
        end -= e - s
    return lines[:end] + block + lines[end:]


def contract_flag_names(lines: list[str]) -> list[str]:
    return [m["name"] for line in lines if (m := FLAG_ITEM_RE.match(line))]


def parse_contract_traceability(text: str) -> dict[str, dict]:
    """flag name -> raw traceability mapping (or {}) from the parsed YAML."""
    doc = yaml.safe_load(text)
    out: dict[str, dict] = {}
    for command in doc.get("commands", []) or []:
        for flag in command.get("flags", []) or []:
            name = flag.get("name")
            if isinstance(name, str) and name.startswith("--"):
                out[name] = flag.get("traceability") or {}
    return out


def validate_contract_text(text: str, flag: str) -> None:
    """Re-parse after an edit; the touched flag must be exactly-one-of."""
    blocks = parse_contract_traceability(text)  # raises on broken YAML
    block = blocks.get(flag)
    if not block:
        raise WalkthroughError(f"post-edit check: flag {flag!r} has no traceability block")
    has_req = "requirements" in block
    has_exc = "excluded" in block
    if has_req == has_exc:
        raise WalkthroughError(
            f"post-edit check: flag {flag!r} must set exactly one of "
            f"requirements/excluded, got {sorted(block)}"
        )
    if has_req and not block["requirements"]:
        raise WalkthroughError(f"post-edit check: flag {flag!r} has an empty requirements list")


# ---------------------------------------------------------------------------
# Effective requirement set (lazy gen_eval import; D11 shadowing reused)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Requirement:
    id: str
    heading: str
    body: str  # verbatim requirement prose, scenarios excluded
    source: str  # "<path> (archive)" or "<path> (delta: ADDED|MODIFIED)"


def effective_requirements(
    repo_root: Path, capability: str, change_id: str | None
) -> list[Requirement]:
    """The effective set with verbatim bodies, archive shadowed by the delta.

    Headings/ordering come from the gate's own ``RequirementResolver`` (the
    single implementation of D11's operation order); bodies are looked up in
    whichever file owns the surviving heading, delta first.
    """
    from gen_eval.traceability import (  # noqa: PLC0415 — lazy by design
        RequirementResolver,
        _split_blocks,
        parse_delta,
        requirement_body_text,
        requirement_id,
    )

    specs_root = repo_root / "openspec" / "specs"
    changes_root = repo_root / "openspec" / "changes"
    resolver = RequirementResolver(specs_root, changes_root)
    effective = resolver.effective_headings(capability, change_id)

    archive_path = specs_root / capability / "spec.md"
    bodies: dict[str, tuple[str, str]] = {}
    if archive_path.is_file():
        rel = archive_path.relative_to(repo_root)
        for heading, block in _split_blocks(archive_path.read_text(encoding="utf-8")):
            bodies[heading] = (requirement_body_text(block), f"{rel} (archive)")
    if change_id is not None:
        delta_path = changes_root / change_id / "specs" / capability / "spec.md"
        if delta_path.is_file():
            rel = delta_path.relative_to(repo_root)
            delta = parse_delta(delta_path.read_text(encoding="utf-8"))
            for op, pairs in (("ADDED", delta.added), ("MODIFIED", delta.modified)):
                for heading, block in pairs:
                    bodies[heading] = (
                        requirement_body_text(block),
                        f"{rel} (delta: {op})",
                    )

    out = []
    for heading in effective.values():
        body, source = bodies.get(heading, ("", "(body not found)"))
        out.append(
            Requirement(
                id=requirement_id(capability, heading), heading=heading, body=body, source=source
            )
        )
    return out


def validate_requirement_ids(
    req_ids: list[str], repo_root: Path, change_id: str | None, known_ids: set[str] | None = None
) -> None:
    """Every cited id must resolve in its own capability's effective set.

    Cross-capability citations are legal (spec: "Citations may name
    requirements in another capability"), so each id is checked against the
    capability its own prefix names — never against a fixed one. `known_ids`
    injects the universe for tests; production resolves via gen_eval.
    """
    caps: dict[str, list[str]] = {}
    for rid in req_ids:
        m = REQUIREMENT_ID_RE.match(rid)
        if not m:
            raise WalkthroughError(f"{rid!r} is not a <capability>.<slug> requirement id")
        caps.setdefault(m["capability"], []).append(rid)
    for capability, ids in caps.items():
        if known_ids is not None:
            universe = known_ids
        else:
            universe = {r.id for r in effective_requirements(repo_root, capability, change_id)}
        for rid in ids:
            if rid not in universe:
                near = sorted(universe)[:5]
                raise WalkthroughError(
                    f"{rid!r} does not resolve in capability {capability!r} "
                    f"(effective set, change={change_id!r}). Nearby ids: {near}"
                )


# ---------------------------------------------------------------------------
# Exclusions file (reverse direction, D13)
# ---------------------------------------------------------------------------


def read_exclusions(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(doc.get("exclusions") or [])


def write_exclusions(path: Path, capability: str, entries: list[dict]) -> None:
    """Deterministic exclusions file: sorted by id, folded reasons.

    The file's EXISTENCE flips reverse enforcement for the capability (D13),
    which is why creation happens only through an explicit apply command.
    """
    lines = [
        "# Reverse-traceability exclusions for " + capability + " (D13).\n",
        "# Every entry is one operator decision; reasons are the artifact.\n",
        "# Managed by skills/cite-requirements — hand edits are fine, the\n",
        "# walkthrough re-reads this file and never overwrites reasons.\n",
        "exclusions:\n",
    ]
    for entry in sorted(entries, key=lambda e: e["requirement"]):
        lines.append(f"  - requirement: {entry['requirement']}\n")
        lines.extend(_fold_reason(str(entry["reason"]), 4))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


def journal_append(change_dir: Path, entry: dict) -> Path:
    path = change_dir / JOURNAL_NAME
    doc = {"decisions": []}
    if path.is_file():
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {"decisions": []}
    entry = {"at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), **entry}
    doc.setdefault("decisions", []).append(entry)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Inventory / status
# ---------------------------------------------------------------------------


def build_inventory(repo_root: Path, capability: str, contract: Path, change_id: str | None) -> dict:
    text = contract.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    blocks = parse_contract_traceability(text)
    flags = []
    for name in contract_flag_names(lines):
        block = blocks.get(name) or {}
        if "requirements" in block:
            state = {"state": "cited", "requirements": block["requirements"]}
        elif "excluded" in block:
            state = {"state": "excluded", "reason": block["excluded"].get("reason")}
        else:
            state = {"state": "undecided"}
        flags.append({"name": name, **state})

    cited: dict[str, list[str]] = {}
    for name, block in blocks.items():
        for rid in block.get("requirements") or []:
            cited.setdefault(rid, []).append(name)

    exclusions_path = repo_root / "openspec" / "contracts" / capability / (
        "traceability-exclusions.yaml"
    )
    excluded_ids = {e["requirement"]: e.get("reason") for e in read_exclusions(exclusions_path)}

    requirements = []
    for req in effective_requirements(repo_root, capability, change_id):
        if req.id in cited:
            state = {"state": "cited", "cited_by": sorted(cited[req.id])}
        elif req.id in excluded_ids:
            state = {"state": "excluded", "reason": excluded_ids[req.id]}
        else:
            state = {"state": "unaccounted"}
        requirements.append({"id": req.id, "heading": req.heading, "source": req.source, **state})

    return {
        "capability": capability,
        "change_id": change_id,
        "contract": str(contract.relative_to(repo_root)),
        "exclusions_file_exists": exclusions_path.is_file(),
        "flags": flags,
        "requirements": requirements,
        "progress": {
            "flags_decided": sum(1 for f in flags if f["state"] != "undecided"),
            "flags_total": len(flags),
            "requirements_accounted": sum(
                1 for r in requirements if r["state"] != "unaccounted"
            ),
            "requirements_total": len(requirements),
        },
    }


# ---------------------------------------------------------------------------
# Cards — verbatim only, by construction
# ---------------------------------------------------------------------------


def render_flag_card(
    repo_root: Path,
    capability: str,
    contract: Path,
    change_id: str | None,
    flag: str,
    *,
    position: str = "",
) -> str:
    lines = contract.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = locate_flag_block(lines, flag)
    rel = contract.relative_to(repo_root)
    slice_text = "".join(lines[start:end])

    reqs = effective_requirements(repo_root, capability, change_id)
    parts = [
        f"# Decision card — flag `{flag}`{position}\n",
        f"## Contract entry (verbatim: {rel}:{start + 1}-{end})\n",
        "```yaml\n" + slice_text.rstrip("\n") + "\n```\n",
        f"## Effective requirements for `{capability}` "
        f"(verbatim; archive shadowed by delta of `{change_id}`)\n",
        "Every body below is quoted unmodified from the named file. "
        "Scenario blocks are omitted; the file paths are given so you can "
        "open the full text.\n",
    ]
    for req in reqs:
        parts.append(f"### `{req.id}` — {req.heading}\n_Source: {req.source}_\n")
        body = req.body or "(no prose body — heading only)"
        parts.append("\n".join("> " + ln for ln in body.splitlines()) + "\n")
    parts.append(
        "---\n*Everything above is verbatim file content produced by "
        "`walkthrough.py`. Anything that follows (candidate annotations, "
        "readings, recommendations) is interpretation added by the "
        "orchestrating agent and its annotation models — it is NOT in any "
        "file.*\n"
    )
    return "\n".join(parts)


def render_requirement_card(
    repo_root: Path,
    capability: str,
    contract: Path,
    change_id: str | None,
    rid: str,
) -> str:
    reqs = {r.id: r for r in effective_requirements(repo_root, capability, change_id)}
    if rid not in reqs:
        raise WalkthroughError(f"{rid!r} is not in the effective set for {capability!r}")
    req = reqs[rid]
    inv = build_inventory(repo_root, capability, contract, change_id)
    undecided = [f["name"] for f in inv["flags"] if f["state"] == "undecided"]
    cited_map = {
        f["name"]: f.get("requirements", []) for f in inv["flags"] if f["state"] == "cited"
    }
    parts = [
        f"# Exclusion-triage card — requirement `{rid}`\n",
        f"## Requirement (verbatim)\n### {req.heading}\n_Source: {req.source}_\n",
        "\n".join("> " + ln for ln in (req.body or "(heading only)").splitlines()) + "\n",
        "## Current contract state (computed from "
        f"{inv['contract']} — citations listed verbatim)\n",
    ]
    if cited_map:
        for name, rids in sorted(cited_map.items()):
            parts.append(f"- `{name}` cites: {', '.join(rids)}")
    else:
        parts.append("- no flag carries citations yet")
    parts.append(f"\nFlags still undecided: {', '.join(undecided) or '(none)'}\n")
    parts.append(
        "---\n*Verbatim/computed content ends here; anything appended below "
        "is interpretation, NOT file content.*\n"
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Annotation cache shape check (interpretation layer, produced by models)
# ---------------------------------------------------------------------------


def validate_annotations(doc: dict) -> list[str]:
    """Shape-check a merged annotations document; returns problems.

    Content is deliberately NOT judged — annotations are interpretation and
    carry their model label so the operator can weigh them. Only structure is
    enforced, so a malformed model reply cannot masquerade as annotations.
    """
    problems = []
    if not isinstance(doc.get("models"), list) or not doc.get("models"):
        problems.append("`models` must be a non-empty list of {label, vendor}")
    flags = doc.get("flags")
    if not isinstance(flags, dict):
        return problems + ["`flags` must be a mapping of flag name -> annotation list"]
    labels = {m.get("label") for m in doc.get("models", []) if isinstance(m, dict)}
    for flag, notes in flags.items():
        if not isinstance(notes, list):
            problems.append(f"{flag}: annotations must be a list")
            continue
        for note in notes:
            if not isinstance(note, dict) or not {"model", "requirement", "note"} <= set(note):
                problems.append(f"{flag}: each annotation needs model/requirement/note")
            elif note["model"] not in labels:
                problems.append(f"{flag}: annotation from undeclared model {note['model']!r}")
    return problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repo-root", type=Path, default=Path("."))
    p.add_argument("--capability", default=DEFAULT_CAPABILITY)
    p.add_argument("--contract", type=Path, default=None, help=f"default: {DEFAULT_CONTRACT}")
    p.add_argument("--change", dest="change_id", default=None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("inventory", "status"):
        _common(sub.add_parser(name))

    p = sub.add_parser("card")
    _common(p)
    p.add_argument("kind", choices=["flag", "requirement"])
    # An option, not a positional: flag subjects all begin with `--`, and
    # argparse's `--` separator would then swallow every later option.
    # `--subject=--mode` parses unambiguously.
    p.add_argument("--subject", required=True)

    p = sub.add_parser("apply-cite")
    _common(p)
    p.add_argument("--flag", required=True)
    p.add_argument("--require", action="append", required=True, dest="requirements")
    p.add_argument("--note", default="", help="operator's reasoning, journalled verbatim")
    p.add_argument("--replace", action="store_true")

    p = sub.add_parser("apply-exclude-flag")
    _common(p)
    p.add_argument("--flag", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--replace", action="store_true")

    p = sub.add_parser("apply-exclude-requirement")
    _common(p)
    p.add_argument("--id", required=True, dest="rid")
    p.add_argument("--reason", required=True)

    p = sub.add_parser("annotations-validate")
    p.add_argument("file", type=Path)

    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except WalkthroughError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    if args.cmd == "annotations-validate":
        problems = validate_annotations(json.loads(args.file.read_text(encoding="utf-8")))
        for problem in problems:
            print(f"ANNOTATIONS: {problem}", file=sys.stderr)
        print("annotations: OK" if not problems else f"annotations: {len(problems)} problem(s)")
        return 0 if not problems else 1

    repo_root = args.repo_root.resolve()
    contract = (repo_root / (args.contract or DEFAULT_CONTRACT)).resolve()
    change_dir = (
        repo_root / "openspec" / "changes" / args.change_id if args.change_id else None
    )

    if args.cmd in ("inventory", "status"):
        inv = build_inventory(repo_root, args.capability, contract, args.change_id)
        if args.cmd == "inventory":
            print(json.dumps(inv, indent=2))
        else:
            p = inv["progress"]
            print(
                f"flags {p['flags_decided']}/{p['flags_total']} decided | "
                f"requirements {p['requirements_accounted']}/"
                f"{p['requirements_total']} accounted | "
                f"reverse switch (exclusions file): "
                f"{'PRESENT — enforcement ON at merge' if inv['exclusions_file_exists'] else 'absent'}"
            )
            for f in inv["flags"]:
                if f["state"] == "undecided":
                    print(f"  undecided flag: {f['name']}")
            for r in inv["requirements"]:
                if r["state"] == "unaccounted":
                    print(f"  unaccounted requirement: {r['id']}")
        return 0

    if args.cmd == "card":
        if args.kind == "flag":
            print(
                render_flag_card(
                    repo_root, args.capability, contract, args.change_id, args.subject
                )
            )
        else:
            print(
                render_requirement_card(
                    repo_root, args.capability, contract, args.change_id, args.subject
                )
            )
        return 0

    if args.cmd in ("apply-cite", "apply-exclude-flag"):
        text = contract.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        if args.cmd == "apply-cite":
            validate_requirement_ids(args.requirements, repo_root, args.change_id)
            block = render_citation_block(args.requirements)
            entry = {
                "kind": "cite",
                "flag": args.flag,
                "requirements": args.requirements,
                "note": args.note,
            }
        else:
            block = render_exclusion_block(args.reason)
            entry = {"kind": "exclude-flag", "flag": args.flag, "reason": args.reason}
        new_lines = insert_traceability(lines, args.flag, block, replace=args.replace)
        new_text = "".join(new_lines)
        validate_contract_text(new_text, args.flag)
        contract.write_text(new_text, encoding="utf-8")
        if change_dir:
            journal_append(change_dir, entry)
        print(f"applied: {entry['kind']} {args.flag}")
        return 0

    if args.cmd == "apply-exclude-requirement":
        if not args.rid.startswith(args.capability + "."):
            raise WalkthroughError(
                f"an exclusions file may only excuse its own capability's "
                f"requirements; {args.rid!r} is not in {args.capability!r}"
            )
        validate_requirement_ids([args.rid], repo_root, args.change_id)
        path = repo_root / "openspec" / "contracts" / args.capability / (
            "traceability-exclusions.yaml"
        )
        entries = read_exclusions(path)
        if any(e["requirement"] == args.rid for e in entries):
            raise WalkthroughError(f"{args.rid!r} is already excluded in {path}")
        creating = not path.is_file()
        entries.append({"requirement": args.rid, "reason": args.reason})
        write_exclusions(path, args.capability, entries)
        if change_dir:
            journal_append(
                change_dir,
                {"kind": "exclude-requirement", "requirement": args.rid, "reason": args.reason},
            )
        print(f"applied: exclude-requirement {args.rid}")
        if creating:
            print(
                "NOTE: exclusions file CREATED — reverse enforcement for "
                f"{args.capability} is now ON (D13). Deleting the file is the "
                "designed retreat if the triage overruns."
            )
        return 0

    raise WalkthroughError(f"unhandled command {args.cmd!r}")


if __name__ == "__main__":
    sys.exit(main())
