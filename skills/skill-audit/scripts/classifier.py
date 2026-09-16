"""Layer classifier: deterministic pre-pass first, one batched model call after.

Design D1/D2. The rule table below is the same one ``references/layers.md``
prints; keep the two in step.

    Layer        Pre-pass rule
    contract     frontmatter; fenced_command; contract_table; skill_base_dir
    constraint   prohibition + reason in one paragraph (rule ``constraint``);
                 a bare prohibition is still ``constraint`` under
                 ``prohibition_without_reason`` and feeds the
                 ``constraint_without_reason`` finding
    procedure    ordered list whose items begin with an imperative verb
    teaching     model-labelled only
    unclassified pre-pass undecided and model output invalid or absent

Only sections the pre-pass leaves undecided are sent, in ONE call per skill,
to the model backend. Invalid output labels the whole batch ``unclassified``
and logs one warning naming the skill and the batch size. Nothing is guessed.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from audit_paths import ensure_sibling_paths, load_bridge
from findings import Finding

ensure_sibling_paths()

from archetype_roster import phase_mapping  # noqa: E402

log = logging.getLogger("skill_audit")

LAYER_LABELS = ("contract", "constraint", "procedure", "teaching")
MAX_SECTION_CHARS = 2000

# --- rule table -------------------------------------------------------------

# Fenced blocks whose info string is one of these are prose, not commands.
PROSE_FENCE_INFO = frozenset({"markdown", "md", "mermaid", "diff", "text-prose"})
# Header cells naming any of these make a table a contract table.
CONTRACT_TABLE_KEYWORDS = (
    "exit", "code", "schema", "path", "flag", "file", "option", "argument",
    "field", "env", "variable", "endpoint", "command",
)
PROHIBITION_RE = re.compile(r"\b(never|must not|shall not|do not|don't)\b", re.IGNORECASE)
REASON_RE = re.compile(r"\b(because|so that|otherwise)\b", re.IGNORECASE)
PARENTHETICAL_RE = re.compile(r"\([^()]{12,}\)")
IMPERATIVE_VERBS = frozenset(
    """
    add announce append apply archive ask assess attach audit build call capture check
    choose cite classify clean close collapse collect commit compare compute confirm
    continue copy count create decide declare define delete deploy deregister describe
    detach diff dispatch display do document draft drop edit emit enforce ensure enter
    estimate evaluate execute exit expand explain export extract fetch filter find flag
    follow format gather generate grep group hand identify implement insert inspect
    install invoke iterate join keep label launch lint list load log look map mark
    measure merge migrate move name note obtain open parse pause pick plan prepare
    present print probe prompt propose publish pull push rank read rebase record
    register remove rename render repeat replace report request resolve respond restore
    resume retry return revert review rollback run save scan score search seed select
    set show skip sketch sort spawn start stop summarize summarise synthesize synthesise
    tag test treat unset update use validate verify wait walk write
    """.split()
)
PROBE_RE = re.compile(
    r"\b(verify|verification|assert|expect(?:ed|s)?|exit code|check that|confirm|must (?:print|return|exit)|should (?:see|print|return|exit))\b",
    re.IGNORECASE,
)
DEVIATION_RE = re.compile(r"deviat", re.IGNORECASE)

# Repository-specific citations that keep a teaching section in place.
REPO_TOKEN_PATTERNS = (
    re.compile(r"<skill-base-dir>[\w./-]*"),
    re.compile(
        r"(?<![\w/])(?:docs|openspec|skills|scripts|src|tests|agent-coordinator|references|packages|\.claude|\.agents|\.github)/[\w./-]*"
    ),
    re.compile(r"(?<![\w/])[\w-]+\.(?:py|sh|json|yaml|yml)\b"),
    re.compile(r"(?<![\w/])/[a-z][a-z0-9-]{3,}(?=[\s`.,;:)]|$)"),
    re.compile(r"\b(?:D\d{1,2}|ADR-\d+)\b"),
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```+|~~~+)\s*([\w+-]*)")
_OLIST_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_ULIST_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_BACKTICK_RE = re.compile(r"`([^`\n]{6,})`")


# --- markdown model ---------------------------------------------------------


@dataclass
class Block:
    kind: str  # fence | table | olist | ulist | paragraph
    text: str
    info: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class Section:
    section_id: str
    file: str
    heading: str
    level: int
    raw: str
    blocks: list[Block] = field(default_factory=list)
    is_frontmatter: bool = False

    @property
    def text(self) -> str:
        return self.raw[:MAX_SECTION_CHARS]


@dataclass
class LayerLabel:
    section_id: str
    file: str
    heading: str
    layer: str
    decided_by: str  # pre-pass | model | none
    rule: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "section_id": self.section_id,
            "file": self.file,
            "heading": self.heading,
            "layer": self.layer,
            "decided_by": self.decided_by,
        }
        if self.rule:
            out["rule"] = self.rule
        return out


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40].rstrip("-") or "section"


def parse_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        fence = _FENCE_RE.match(line)
        if fence:
            marker, info = fence.group(1), fence.group(2).lower()
            body: list[str] = []
            i += 1
            while i < n and not lines[i].startswith(marker[0] * 3):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence
            blocks.append(Block("fence", "\n".join(body), info=info))
            continue
        if _TABLE_ROW_RE.match(line):
            rows: list[str] = []
            while i < n and _TABLE_ROW_RE.match(lines[i]):
                rows.append(lines[i])
                i += 1
            blocks.append(Block("table", "\n".join(rows)))
            continue
        if _OLIST_RE.match(line):
            items: list[str] = []
            while i < n and lines[i].strip():
                m = _OLIST_RE.match(lines[i])
                if m:
                    items.append(m.group(2))
                elif items and lines[i].startswith((" ", "\t")):
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            blocks.append(Block("olist", "\n".join(items), items=items))
            continue
        if _ULIST_RE.match(line):
            items = []
            while i < n and lines[i].strip():
                m = _ULIST_RE.match(lines[i])
                if m:
                    items.append(m.group(1))
                elif items and lines[i].startswith((" ", "\t")):
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            blocks.append(Block("ulist", "\n".join(items), items=items))
            continue
        para: list[str] = []
        while i < n and lines[i].strip() and not _FENCE_RE.match(lines[i]) and not _TABLE_ROW_RE.match(lines[i]) and not _HEADING_RE.match(lines[i]):
            para.append(lines[i])
            i += 1
        if para:
            blocks.append(Block("paragraph", "\n".join(para)))
        else:
            i += 1
    return blocks


def parse_sections(text: str, file: str) -> list[Section]:
    """Split one markdown file into frontmatter + heading-delimited sections."""
    sections: list[Section] = []
    body = text
    fm = _FRONTMATTER_RE.match(text)
    if fm:
        sections.append(
            Section(
                section_id=f"{file}#00-frontmatter",
                file=file,
                heading="frontmatter",
                level=0,
                raw=fm.group(0),
                is_frontmatter=True,
            )
        )
        body = text[fm.end():]

    current_heading = "preamble"
    current_level = 0
    current_lines: list[str] = []
    in_fence: str | None = None
    pending: list[tuple[str, int, list[str]]] = []

    for line in body.split("\n"):
        fence = _FENCE_RE.match(line)
        if fence and in_fence is None:
            in_fence = fence.group(1)[0] * 3
        elif in_fence and line.startswith(in_fence):
            in_fence = None
        heading = None if in_fence else _HEADING_RE.match(line)
        if heading:
            pending.append((current_heading, current_level, current_lines))
            current_heading = heading.group(2).strip()
            current_level = len(heading.group(1))
            current_lines = [line]
        else:
            current_lines.append(line)
    pending.append((current_heading, current_level, current_lines))

    index = len(sections)
    for heading, level, lines in pending:
        content = "\n".join(lines)
        if heading == "preamble" and not content.strip():
            continue
        body_lines = lines[1:] if level else lines
        blocks = parse_blocks(body_lines)
        if not blocks:
            # A heading with no body (an H1 title, a "## Steps" umbrella over
            # sub-headings) is structure, not prose; there is nothing to label.
            continue
        sections.append(
            Section(
                section_id=f"{file}#{index:02d}-{_slug(heading)}",
                file=file,
                heading=heading,
                level=level,
                raw=content,
                blocks=blocks,
            )
        )
        index += 1
    return sections


def parse_skill(skill_dir: Path) -> list[Section]:
    """Sections of SKILL.md plus every file one level below references/."""
    sections = parse_sections((skill_dir / "SKILL.md").read_text(encoding="utf-8"), "SKILL.md")
    refs = skill_dir / "references"
    if refs.is_dir():
        for ref in sorted(p for p in refs.iterdir() if p.is_file() and p.suffix == ".md"):
            sections.extend(parse_sections(ref.read_text(encoding="utf-8"), f"references/{ref.name}"))
    return sections


# --- pre-pass ---------------------------------------------------------------


def _is_command_fence(block: Block) -> bool:
    return block.kind == "fence" and block.info not in PROSE_FENCE_INFO


def _is_contract_table(block: Block) -> bool:
    if block.kind != "table":
        return False
    header = block.text.split("\n", 1)[0].lower()
    return any(k in header for k in CONTRACT_TABLE_KEYWORDS)


def _first_word(item: str) -> str:
    cleaned = re.sub(r"[*_`\[\]]", " ", item).strip()
    m = re.match(r"([A-Za-z]+)", cleaned)
    return m.group(1).lower() if m else ""


def _is_procedure_list(block: Block) -> bool:
    if block.kind != "olist" or not block.items:
        return False
    hits = sum(1 for item in block.items if _first_word(item) in IMPERATIVE_VERBS)
    return hits * 2 >= len(block.items)


def prepass(section: Section) -> tuple[str, str] | None:
    """Return ``(layer, rule)`` when a shape rule decides, else ``None``."""
    if section.is_frontmatter:
        return "contract", "frontmatter"
    if any(_is_command_fence(b) for b in section.blocks):
        return "contract", "fenced_command"
    if any(_is_contract_table(b) for b in section.blocks):
        return "contract", "contract_table"
    if "<skill-base-dir>" in section.raw:
        return "contract", "skill_base_dir"
    for block in section.blocks:
        if block.kind != "paragraph":
            continue
        if PROHIBITION_RE.search(block.text):
            if REASON_RE.search(block.text) or PARENTHETICAL_RE.search(block.text):
                return "constraint", "constraint"
            return "constraint", "prohibition_without_reason"
    if any(_is_procedure_list(b) for b in section.blocks):
        return "procedure", "procedure"
    return None


# --- model backend ----------------------------------------------------------


class ModelBackend(Protocol):
    def classify(self, skill: str, sections: list[Section], model: str | None) -> Any:
        """Return ``{section_id: label}`` (dict or JSON text). Anything else is invalid."""


class NullBackend:
    """No model configured: every undecided section stays ``unclassified``."""

    def classify(self, skill: str, sections: list[Section], model: str | None) -> Any:
        return None


class CommandBackend:
    """Pipe the prompt to a shell command (``SKILL_AUDIT_MODEL_CMD``) and read JSON back."""

    def __init__(self, command: str, timeout: float = 120.0) -> None:
        self.command = command
        self.timeout = timeout

    def classify(self, skill: str, sections: list[Section], model: str | None) -> Any:
        env_note = f" (model: {model})" if model else ""
        try:
            proc = subprocess.run(
                self.command,
                shell=True,
                input=build_prompt(skill, sections) + env_note,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("skill-audit: model command failed for %s: %s", skill, exc)
            return None
        return proc.stdout if proc.returncode == 0 else None


def build_prompt(skill: str, sections: list[Section]) -> str:
    lines = [
        f"Classify each section of the skill '{skill}' into exactly one layer.",
        "Layers: contract (another agent depends on it), constraint (operator prohibition with",
        "reason), procedure (ordered steps), teaching (generic competence a strong model holds).",
        "Answer with ONLY a JSON object mapping every section_id below to one layer label.",
        "",
    ]
    for s in sections:
        lines.append(f"### section_id: {s.section_id}")
        lines.append(s.text)
        lines.append("")
    return "\n".join(lines)


def validate_model_output(raw: Any, section_ids: list[str]) -> dict[str, str] | None:
    """Strict ``{section_id: label}`` check: every id present, every label known."""
    data = raw
    if isinstance(raw, (str, bytes)):
        text = raw.decode() if isinstance(raw, bytes) else raw
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    if set(data) != set(section_ids):
        return None
    if not all(isinstance(v, str) and v in LAYER_LABELS for v in data.values()):
        return None
    return {k: data[k] for k in section_ids}


def resolve_analyst(*, bridge: Any | None = None, roster_path: Path | None = None) -> str | None:
    """Model id for the ``analyst`` archetype via the bridge, or ``None``.

    ``try_resolve_archetype_for_phase`` takes a phase, so the first phase that
    ``phase_mapping`` routes to ``analyst`` is used; no such phase, no bridge,
    or any failure means the model is omitted.
    """
    try:
        mapping = phase_mapping(roster_path)
        phase = next(
            (p for p, e in mapping.items() if isinstance(e, dict) and e.get("archetype") == "analyst"),
            None,
        )
        if phase is None:
            return None
        bridge = bridge or load_bridge()
        if bridge is None:
            return None
        data = bridge.try_resolve_archetype_for_phase(phase)
        model = data.get("model") if isinstance(data, dict) else None
        return model if isinstance(model, str) and model else None
    except Exception:
        return None


# --- classification ---------------------------------------------------------


@dataclass
class Classification:
    labels: list[LayerLabel]
    model_calls: int
    batch_size: int
    warnings: list[str] = field(default_factory=list)

    def layer_of(self, section_id: str) -> str:
        for label in self.labels:
            if label.section_id == section_id:
                return label.layer
        return "unclassified"


def classify_sections(
    skill: str,
    sections: list[Section],
    backend: ModelBackend,
    *,
    model: str | None = None,
) -> Classification:
    labels: list[LayerLabel] = []
    undecided: list[Section] = []
    for s in sections:
        decided = prepass(s)
        if decided:
            labels.append(LayerLabel(s.section_id, s.file, s.heading, decided[0], "pre-pass", decided[1]))
        else:
            labels.append(LayerLabel(s.section_id, s.file, s.heading, "unclassified", "none"))
            undecided.append(s)

    calls = 0
    warnings: list[str] = []
    if undecided:
        calls = 1
        raw = backend.classify(skill, undecided, model)
        verdicts = validate_model_output(raw, [s.section_id for s in undecided])
        if verdicts is None:
            msg = (
                f"skill-audit: {skill}: model output invalid or unavailable; "
                f"{len(undecided)} section(s) labelled unclassified"
            )
            log.warning(msg)
            warnings.append(msg)
        else:
            by_id = {label.section_id: label for label in labels}
            for sid, layer in verdicts.items():
                by_id[sid].layer = layer
                by_id[sid].decided_by = "model"
    return Classification(labels=labels, model_calls=calls, batch_size=len(undecided), warnings=warnings)


# --- findings ---------------------------------------------------------------


def repo_specific_tokens(text: str) -> list[str]:
    found: set[str] = set()
    for pattern in REPO_TOKEN_PATTERNS:
        for m in pattern.finditer(text):
            token = m.group(0).rstrip(".,;:)")
            if "://" not in token:
                found.add(token)
    return sorted(found)


def collect_test_texts(skill_dir: Path, skills_root: Path) -> list[str]:
    """Text of every test file that could pin this skill's contract sections."""
    candidates = [
        skills_root / "tests" / skill_dir.name,
        skill_dir / "tests",
        skill_dir / "scripts" / "tests",
    ]
    texts: list[str] = []
    for base in candidates:
        if base.is_dir():
            for path in sorted(base.rglob("*.py")):
                try:
                    texts.append(path.read_text(encoding="utf-8"))
                except OSError:
                    continue
    return texts


def _is_pinned(section: Section, test_texts: list[str]) -> bool:
    if not test_texts:
        return False
    joined = "\n".join(test_texts)
    lowered = joined.lower()
    if section.is_frontmatter:
        return "frontmatter" in lowered
    if len(section.heading) >= 4 and section.heading.lower() in lowered:
        return True
    for token in _BACKTICK_RE.findall(section.raw):
        if token in joined:
            return True
    return False


def _has_probe(section: Section) -> bool:
    if any(b.kind in {"fence", "table"} for b in section.blocks):
        return True
    return bool(PROBE_RE.search(section.raw))


def generate_findings(
    sections: list[Section],
    classification: Classification,
    *,
    test_texts: list[str],
) -> list[Finding]:
    """Layer-driven findings in document order (ids are assigned by the ledger)."""
    out: list[Finding] = []
    rule_by_id = {label.section_id: label.rule for label in classification.labels}
    any_procedure = False
    first_procedure: Section | None = None

    for s in sections:
        layer = classification.layer_of(s.section_id)
        if layer == "teaching":
            tokens = repo_specific_tokens(s.raw)
            if tokens:
                out.append(
                    Finding(
                        kind="teaching_inferable",
                        layer="teaching",
                        section_id=s.section_id,
                        remediation="keep",
                        rationale="Teaching prose, but it cites repository specifics a model cannot infer.",
                        evidence={"repo_specific_tokens": tokens},
                    )
                )
            else:
                out.append(
                    Finding(
                        kind="teaching_inferable",
                        layer="teaching",
                        section_id=s.section_id,
                        remediation="move_to_reference",
                        rationale="Generic competence a frontier model already holds; keep it out of the hot path.",
                        evidence={"repo_specific_tokens": []},
                    )
                )
        elif layer == "procedure":
            any_procedure = True
            first_procedure = first_procedure or s
            if not _has_probe(s):
                out.append(
                    Finding(
                        kind="procedure_without_probe",
                        layer="procedure",
                        section_id=s.section_id,
                        remediation="add_probe",
                        rationale="Ordered steps with no acceptance probe; a goal-directed tier cannot tell when it is done.",
                    )
                )
        elif layer == "constraint" and rule_by_id.get(s.section_id) == "prohibition_without_reason":
            out.append(
                Finding(
                    kind="constraint_without_reason",
                    layer="constraint",
                    section_id=s.section_id,
                    remediation="add_reason",
                    rationale="Prohibition without a stated reason; a strong model argues with a bare rule.",
                )
            )
        elif layer == "contract" and not _is_pinned(s, test_texts):
            out.append(
                Finding(
                    kind="contract_unpinned",
                    layer="contract",
                    section_id=s.section_id,
                    remediation="add_probe",
                    rationale="No test cites this contract section; drift would go unnoticed.",
                )
            )

    if any_procedure and first_procedure is not None:
        if not any(DEVIATION_RE.search(s.raw) for s in sections):
            out.append(
                Finding(
                    kind="missing_deviation_protocol",
                    layer="procedure",
                    section_id=first_procedure.section_id,
                    remediation="add_probe",
                    rationale="The skill has procedure but never says how to record a deviation from it.",
                )
            )
    return out


__all__ = [
    "Block",
    "Classification",
    "CommandBackend",
    "LayerLabel",
    "ModelBackend",
    "NullBackend",
    "Section",
    "build_prompt",
    "classify_sections",
    "collect_test_texts",
    "generate_findings",
    "parse_blocks",
    "parse_sections",
    "parse_skill",
    "prepass",
    "repo_specific_tokens",
    "resolve_analyst",
    "validate_model_output",
]
