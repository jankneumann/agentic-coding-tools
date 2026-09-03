"""Render the atlas view-model into one self-contained HTML file."""

from __future__ import annotations

import json
from typing import Any

from atlas_assets import CSS, JS

_TITLE = "Codebase Atlas"


def _esc(value: Any) -> str:
    """Escape for HTML text and double-quoted attribute contexts."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _embed(payload: dict[str, Any]) -> str:
    """Serialise the payload for safe inlining inside a ``<script>`` element.

    The payload rides in a ``type="application/json"`` block read with
    ``JSON.parse``, so the real hazard is a literal ``</script>`` inside a string
    value terminating the element early. Escaping ``<`` and ``>`` removes it;
    ``JSON.parse`` decodes the escapes back to the original characters. U+2028
    and U+2029 are escaped too, keeping the document free of stray line
    terminators. ``sort_keys`` keeps output byte-stable across runs.
    """
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _coverage_banner(coverage: list[dict[str, Any]]) -> str:
    """Render the coverage disclosure.

    This is deliberately prominent and cannot be dismissed. An atlas built over
    a partial graph looks authoritative, so the page states what the analyzer
    never examined; without this the visualisation would actively mislead.
    """
    if not coverage:
        return ""

    # A language is a gap if *any* disk file is unaccounted for, or if the graph
    # names files that are no longer there. An earlier `percent < 99.0` threshold
    # let 99.0–99.9% coverage — and a graph that matched every current file while
    # still naming obsolete ones — render the success banner, hiding precisely the
    # incompleteness and staleness this banner exists to disclose.
    gaps = [
        c
        for c in coverage
        if c["filesOnDisk"] > 0
        and (c["filesMatched"] < c["filesOnDisk"] or c["filesMissing"] > 0)
    ]
    if not gaps:
        totals = ", ".join(f"{c['language']} {c['filesInGraph']}" for c in coverage)
        return (
            '<div class="coverage ok" role="status">Graph covers all discovered '
            f"source files ({_esc(totals)}).</div>"
        )

    lines = []
    for c in gaps:
        missing = ", ".join(
            f"{_esc(d['dir'])} ({d['files']})" for d in c["uncoveredTopDirs"][:6]
        )
        # A graph naming files that are no longer on disk is stale, not merely
        # narrow — a distinct problem worth calling out separately.
        stale = (
            f" <strong>{c['filesMissing']} file(s) in the graph no longer exist "
            f"on disk</strong> (graph is stale)."
            if c.get("filesMissing")
            else ""
        )
        # Report both numbers. filesMatched is consistent with the directory
        # breakdown below (matched + uncovered = total) but is inflated by
        # basename matching: one graph entry for `__init__.py` accepts every
        # `__init__.py` in the tree. filesInGraph is what the analyzer actually
        # examined. Showing only one of the two would mislead in one direction or
        # the other, so the reader gets the ceiling and the floor.
        lines.append(
            f"<li><strong>{_esc(c['language'])}</strong>: at most "
            f"{c['filesMatched']} of {c['filesOnDisk']} files "
            f"(<strong>&le;{c['percent']}%</strong>), from only "
            f"{c['filesInGraph']} distinct file name(s) the analyzer examined"
            + (f" &mdash; not covered: {missing}" if missing else "")
            + stale
            + "</li>"
        )

    return (
        '<div class="coverage" role="alert">'
        "<strong>Partial coverage.</strong> This atlas shows only what the architecture "
        "analyzer was pointed at, so absence from this page does not mean absence from "
        "the repository."
        f"<ul>{''.join(lines)}</ul>"
        "Widen <code>PYTHON_SRC_DIR</code> / <code>TS_SRC_DIR</code> in the Makefile and "
        "re-run <code>make architecture</code> to close the gap. Matching is by file "
        "name, not full path, so the file count is an upper bound: one graph entry for "
        "<code>__init__.py</code> is credited with every <code>__init__.py</code> in the "
        "tree. The distinct-name count is the honest floor."
        "</div>"
    )


def render_page(payload: dict[str, Any]) -> str:
    """Produce the complete HTML document."""
    meta = payload["meta"]
    sha = meta.get("gitSha") or "unknown"
    generated = meta.get("generatedFrom") or "unknown"

    dangling = meta.get("danglingEdges") or 0
    dangling_note = (
        f'<span title="Edges whose endpoints are missing from the node list">'
        f"{dangling} dangling edge{'s' if dangling != 1 else ''} skipped</span>"
        if dangling
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_TITLE}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{_TITLE}</h1>
  <div class="meta">
    <span>{meta['moduleCount']} files</span>
    <span>{meta['nodeCount']} symbols</span>
    <span>{meta['edgeCount']} edges</span>
    <span title="Commit the source graph was generated from">graph @ {_esc(sha)[:12]}</span>
    <span>generated {_esc(generated)}</span>
    {dangling_note}
  </div>
  <span class="spacer"></span>
  <button class="ghost" id="clear">Clear selection</button>
  <button class="ghost" id="theme">Theme</button>
</header>
{_coverage_banner(payload.get("coverage") or [])}
<main>
  <section class="pane" aria-label="Structure tree">
    <div class="pane-head">Structure</div>
    <div class="filters">
      <input type="search" id="q" placeholder="Filter files and symbols&hellip;"
             aria-label="Filter files and symbols">
      <div class="chips" id="lang-chips" role="group" aria-label="Languages"></div>
      <div class="chips" id="edge-chips" role="group" aria-label="Edge types"></div>
      <div class="row">
        <button class="chip" id="expand-all">Expand all</button>
        <button class="chip" id="collapse-all">Collapse all</button>
      </div>
    </div>
    <div class="pane-body">
      <ul class="tree" id="tree"></ul>
      <p class="empty hidden" id="tree-empty">No files or symbols match this filter.</p>
    </div>
  </section>

  <section class="pane" aria-label="Dependency graph">
    <div class="pane-head">
      Dependencies
      <span class="spacer"></span>
      <label class="row" for="depth">hops <input type="range" id="depth" min="1" max="4"
        step="1" value="1" style="width:70px"><output id="depth-val">1</output></label>
    </div>
    <div class="canvas-wrap">
      <canvas id="graph" aria-label="Force-directed file dependency graph"></canvas>
      <div class="tooltip" id="tip" role="tooltip"></div>
      <div class="legend">
        <div><span class="swatch" style="background:var(--in)"></span> callers (inbound)</div>
        <div><span class="swatch" style="background:var(--out)"></span> dependencies (outbound)</div>
      </div>
    </div>
  </section>

  <section class="pane" aria-label="Selection details">
    <div class="pane-head">Cross-connections</div>
    <div class="pane-body" id="details"></div>
  </section>
</main>
<script id="atlas-data" type="application/json">{_embed(payload)}</script>
<script>
window.__ATLAS__ = JSON.parse(document.getElementById("atlas-data").textContent);
</script>
<script>{JS}</script>
</body>
</html>
"""
