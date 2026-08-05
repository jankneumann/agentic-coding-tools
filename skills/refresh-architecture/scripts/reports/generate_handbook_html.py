"""Render the behavior handbook as a three-level HTML drill-down (design D6).

One map, four entry points. Rather than forking a document per audience — which
drifts and triples the refresh cost — the same handbook data is served with
different *entry levels and traversal orders*:

``newcomer``  L1 first, breadth-first through the system flows
``reviewer``  L2 filtered to the files a diff touched
``planner``   behavior search, then straight to one L3 unit
``auditor``   L3 exception paths only

The page embeds the handbook as a JSON island and does all navigation locally,
so it works offline, from ``file://``, and inside a strict CSP.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from html import escape
from pathlib import Path
from typing import Any

# Executed as a script from the Makefile, so make the scripts/ package root
# importable the same way the sibling report generator does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arch_utils.graph_io import load_graph  # noqa: E402
from handbook_schema import validate_handbook  # noqa: E402

logger = logging.getLogger(__name__)

_STYLES = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #5c6370; --line: #e3e6ea;
  --panel: #f7f8fa; --accent: #2f6feb; --ok: #1a7f37; --warn: #9a6700;
  --err: #cf222e; --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #30363d;
    --panel: #161b22; --accent: #4493f8; --ok: #3fb950; --warn: #d29922;
    --err: #f85149;
  }
}
:root[data-theme="dark"] {
  --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #30363d;
  --panel: #161b22; --accent: #4493f8; --ok: #3fb950; --warn: #d29922;
  --err: #f85149;
}
:root[data-theme="light"] {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #5c6370; --line: #e3e6ea;
  --panel: #f7f8fa; --accent: #2f6feb; --ok: #1a7f37; --warn: #9a6700;
  --err: #cf222e;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
header h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
.sub { color: var(--muted); font-size: .875rem; margin-bottom: 1.5rem; }
.personas { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1.5rem; }
.persona {
  border: 1px solid var(--line); background: var(--panel); color: var(--fg);
  border-radius: 999px; padding: .35rem .9rem; font-size: .8125rem; cursor: pointer;
}
.persona[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
.persona .hint { color: var(--muted); margin-left: .4rem; }
h2 {
  font-size: .8125rem; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); margin: 2rem 0 .75rem; border-bottom: 1px solid var(--line);
  padding-bottom: .4rem;
}
.flow, .card {
  border: 1px solid var(--line); border-radius: 8px; background: var(--panel);
  padding: .85rem 1rem; margin-bottom: .6rem;
}
.flow-title, .card-title { font-weight: 600; }
.stages { color: var(--muted); font-size: .8125rem; margin-top: .3rem; }
.card { cursor: pointer; }
.card[hidden], .flow[hidden], .unc[hidden] { display: none; }
.card-meta { color: var(--muted); font-size: .8125rem; margin-top: .3rem; }
.detail { margin-top: .85rem; padding-top: .85rem; border-top: 1px dashed var(--line); }
.detail h3 {
  font-size: .75rem; text-transform: uppercase; letter-spacing: .05em;
  color: var(--muted); margin: .9rem 0 .35rem;
}
.detail ul { margin: 0; padding-left: 1.1rem; }
.ev { font-family: var(--mono); font-size: .75rem; color: var(--muted); }
.badge {
  display: inline-block; font-size: .6875rem; padding: 0 .4rem; border-radius: 4px;
  border: 1px solid var(--line); margin-left: .4rem;
}
.badge.member { color: var(--ok); }
.badge.exception_path { color: var(--warn); }
.unc { font-family: var(--mono); font-size: .8125rem; color: var(--muted); }
.empty { color: var(--muted); font-style: italic; }
.filter {
  width: 100%; padding: .5rem .7rem; border: 1px solid var(--line);
  border-radius: 6px; background: var(--bg); color: var(--fg); margin-bottom: .75rem;
}
.scroll { overflow-x: auto; }
footer { color: var(--muted); font-size: .75rem; margin-top: 3rem; }
"""

_SCRIPT = """
const DATA = JSON.parse(document.getElementById('handbook-data').textContent);
const PERSONAS = {
  newcomer: { l1: true, cards: true, autoOpen: false, exceptionsOnly: false },
  reviewer: { l1: false, cards: true, autoOpen: false, exceptionsOnly: false },
  planner:  { l1: false, cards: true, autoOpen: false, exceptionsOnly: false },
  auditor:  { l1: false, cards: true, autoOpen: true,  exceptionsOnly: true  },
};
let current = 'newcomer';

function applyPersona(name) {
  current = PERSONAS[name] ? name : 'newcomer';
  const cfg = PERSONAS[current];
  document.querySelectorAll('.persona').forEach(function (b) {
    b.setAttribute('aria-pressed', String(b.dataset.persona === current));
  });
  document.getElementById('l1').hidden = !cfg.l1;
  document.querySelectorAll('.detail').forEach(function (d) {
    d.hidden = !cfg.autoOpen;
  });
  document.querySelectorAll('[data-section]').forEach(function (s) {
    s.hidden = cfg.exceptionsOnly && s.dataset.section !== 'exception_paths';
  });
  location.hash = current;
}

function applyFilter(term) {
  const q = term.trim().toLowerCase();
  document.querySelectorAll('.card').forEach(function (card) {
    card.hidden = q !== '' && card.dataset.haystack.indexOf(q) === -1;
  });
}

document.querySelectorAll('.persona').forEach(function (b) {
  b.addEventListener('click', function () { applyPersona(b.dataset.persona); });
});
document.querySelectorAll('.card-title').forEach(function (t) {
  t.addEventListener('click', function (ev) {
    ev.stopPropagation();
    const d = t.closest('.card').querySelector('.detail');
    if (d) { d.hidden = !d.hidden; }
  });
});
document.getElementById('filter').addEventListener('input', function (e) {
  applyFilter(e.target.value);
});
applyPersona((location.hash || '#newcomer').slice(1));
"""


def _esc(value: Any) -> str:
    return escape(str(value), quote=True)


def _list_block(title: str, items: list[Any], section: str) -> str:
    if not items:
        return ""
        # An absent section is simply omitted; empty <ul> is noise.
    rows = "".join(f"<li>{_esc(i)}</li>" for i in items)
    return (
        f'<div data-section="{_esc(section)}"><h3>{_esc(title)}</h3>'
        f"<ul>{rows}</ul></div>"
    )


def _evidence_block(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return ""
    rows = []
    for entry in entries:
        span = entry.get("span") or {}
        role = str(entry.get("role") or "member")
        rows.append(
            f'<li class="ev">{_esc(entry.get("file"))}:'
            f'{_esc(span.get("start"))}-{_esc(span.get("end"))}'
            f' <span class="badge {_esc(role)}">{_esc(role)}</span></li>'
        )
    return f'<ul>{"".join(rows)}</ul>'


def _paths_block(title: str, paths: list[dict[str, Any]], section: str) -> str:
    if not paths:
        return ""
    rows = []
    for path in paths:
        rows.append(
            f'<li>{_esc(path.get("summary"))}'
            f'{_evidence_block(path.get("evidence") or [])}</li>'
        )
    return (
        f'<div data-section="{_esc(section)}"><h3>{_esc(title)}</h3>'
        f'<ul>{"".join(rows)}</ul></div>'
    )


def render_handbook_html(handbook: dict[str, Any], graph: dict[str, Any]) -> str:
    """Return a complete, self-contained HTML page for *handbook*."""
    snapshot = handbook.get("snapshot") or {}
    flows = handbook.get("system_flows") or []
    units = handbook.get("behavior_units") or []
    details = handbook.get("unit_details") or {}
    uncovered = handbook.get("uncovered") or []

    flow_html = "".join(
        f'<div class="flow"><div class="flow-title">{_esc(f.get("title"))} '
        f'<span class="ev">{_esc(f.get("id"))}</span></div>'
        f'<div class="stages">entry: {_esc(f.get("entry"))}'
        + (f' &middot; stages: {_esc(" -> ".join(map(str, f.get("stages") or [])))}'
           if f.get("stages") else "")
        + "</div></div>"
        for f in flows
    ) or '<p class="empty">No system flows recorded.</p>'

    card_html = []
    for unit in units:
        unit_id = str(unit.get("id"))
        detail = details.get(unit_id) or {}
        haystack = _esc(
            json.dumps(
                {"u": unit, "d": detail}, ensure_ascii=False, sort_keys=True
            ).lower()
        )
        body = "".join(
            [
                _list_block("Triggers", detail.get("triggers") or [], "triggers"),
                _list_block(
                    "State changes", detail.get("state_changes") or [], "state_changes"
                ),
                _paths_block(
                    "Execution paths", detail.get("execution_paths") or [],
                    "execution_paths",
                ),
                _paths_block(
                    "Exception paths", detail.get("exception_paths") or [],
                    "exception_paths",
                ),
                (
                    f'<div data-section="evidence"><h3>Evidence</h3>'
                    f'{_evidence_block(detail.get("evidence") or [])}</div>'
                    if detail.get("evidence") else ""
                ),
            ]
        )
        card_html.append(
            f'<div class="card" data-unit="{_esc(unit_id)}" data-haystack="{haystack}">'
            f'<div class="card-title">{_esc(unit.get("title"))} '
            f'<span class="ev">{_esc(unit_id)}</span></div>'
            f'<div class="card-meta">{_esc(unit.get("responsibility"))}</div>'
            f'<div class="card-meta">{_esc(len(unit.get("member_nodes") or []))} '
            f"member node(s)</div>"
            f'<div class="detail" hidden>{body}</div></div>'
        )
    cards = "".join(card_html) or '<p class="empty">No behavior units recorded.</p>'

    uncovered_html = "".join(
        f'<div class="unc">{_esc(u.get("node_id"))} &mdash; {_esc(u.get("reason"))}</div>'
        for u in uncovered
    ) or '<p class="empty">Every entrypoint is covered by a behavior unit.</p>'

    island = json.dumps(handbook, ensure_ascii=False, sort_keys=True).replace(
        "</", "<\\/"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Behavior Handbook</title>
<style>{_STYLES}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Behavior Handbook</h1>
  <div class="sub">
    {_esc(len(units))} behavior unit(s) &middot; {_esc(len(flows))} system flow(s)
    &middot; {_esc(len(uncovered))} uncovered entrypoint(s)
    &middot; revision {_esc(snapshot.get("git_sha"))}
    &middot; generated {_esc(snapshot.get("generated_at"))}
  </div>
</header>

<div class="personas" role="group" aria-label="Persona entry points">
  <button class="persona" data-persona="newcomer" aria-pressed="true">
    Newcomer<span class="hint">start at the system flow</span></button>
  <button class="persona" data-persona="reviewer" aria-pressed="false">
    Reviewer<span class="hint">filter units by what changed</span></button>
  <button class="persona" data-persona="planner" aria-pressed="false">
    Planner<span class="hint">search, then open one unit</span></button>
  <button class="persona" data-persona="auditor" aria-pressed="false">
    Auditor<span class="hint">exception paths only</span></button>
</div>

<section id="l1">
  <h2>Level 1 &mdash; system flow</h2>
  <div class="scroll">{flow_html}</div>
</section>

<section id="l2">
  <h2>Level 2 &mdash; behavior units</h2>
  <input id="filter" class="filter" type="search"
         placeholder="Filter behaviors (file path, trigger, or description)&hellip;">
  <div class="scroll">{cards}</div>
</section>

<section id="uncovered">
  <h2>Uncovered entrypoints</h2>
  <div class="scroll">{uncovered_html}</div>
</section>

<footer>
  Synthesized by the {_esc(snapshot.get("backend"))} backend
  (model {_esc(snapshot.get("model_id"))}, prompt {_esc(snapshot.get("prompt_hash"))}).
  Evidence locators are verified by <code>make architecture-check</code>.
</footer>
</div>
<script id="handbook-data" type="application/json">{island}</script>
<script>{_SCRIPT}</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the behavior handbook drill-down")
    parser.add_argument("--handbook", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    handbook_path = Path(args.handbook)
    if not handbook_path.is_file():
        logger.error("handbook not found: %s", handbook_path)
        return 1

    handbook = json.loads(handbook_path.read_text(encoding="utf-8"))
    graph = load_graph(Path(args.graph), quiet=True)

    dc = validate_handbook(handbook, graph)
    if dc.exit_code != 0:
        for item in dc.errors:
            logger.error("[%s] %s", item.code, item.message)
        logger.error("refusing to render an invalid handbook")
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_handbook_html(handbook, graph), encoding="utf-8")
    logger.info("Handbook drill-down written to %s", out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
