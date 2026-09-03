"""Inline CSS and JS for the atlas page.

Kept as module constants rather than separate asset files for one reason: the
rendered page must be a single self-contained file that opens from a filesystem
path with no server, no build step, and no network request. That rules out
external stylesheets, CDN libraries, and fetch() for the data payload -- so the
force simulation below is hand-written rather than pulled from d3.

Both constants are plain strings (never f-strings): the CSS contains braces and
the JS contains template literals, and neither should be interpreted by Python.
"""

from __future__ import annotations

CSS = """
:root {
  --bg: #fbfbfd; --panel: #ffffff; --border: #e2e4ea; --text: #1b1d22;
  --muted: #6b7180; --accent: #3b5bdb; --accent-soft: #e7ecfd;
  --in: #c2410c; --out: #0f766e; --warn-bg: #fff8e6; --warn-border: #e8c675;
  --warn-text: #6b4e00; --shadow: 0 1px 3px rgba(20,22,28,.09);
  --py: #3b5bdb; --sql: #b1479c; --ts: #1a7f8c; --unknown: #8b93a3;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a; --panel: #1b1e24; --border: #2c313a; --text: #e6e8ee;
    --muted: #9aa2b1; --accent: #8ea6ff; --accent-soft: #22283a;
    --in: #ff9d66; --out: #4fd1c5; --warn-bg: #2e2617; --warn-border: #6b5a2c;
    --warn-text: #f0d99a; --shadow: 0 1px 3px rgba(0,0,0,.4);
    --py: #8ea6ff; --sql: #e59ad4; --ts: #5fd4e0; --unknown: #7d8595;
  }
}
:root[data-theme="light"] {
  --bg: #fbfbfd; --panel: #ffffff; --border: #e2e4ea; --text: #1b1d22;
  --muted: #6b7180; --accent: #3b5bdb; --accent-soft: #e7ecfd;
  --in: #c2410c; --out: #0f766e; --warn-bg: #fff8e6; --warn-border: #e8c675;
  --warn-text: #6b4e00; --py: #3b5bdb; --sql: #b1479c; --ts: #1a7f8c; --unknown: #8b93a3;
}
:root[data-theme="dark"] {
  --bg: #14161a; --panel: #1b1e24; --border: #2c313a; --text: #e6e8ee;
  --muted: #9aa2b1; --accent: #8ea6ff; --accent-soft: #22283a;
  --in: #ff9d66; --out: #4fd1c5; --warn-bg: #2e2617; --warn-border: #6b5a2c;
  --warn-text: #f0d99a; --py: #8ea6ff; --sql: #e59ad4; --ts: #5fd4e0; --unknown: #7d8595;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.5 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif;
  height: 100vh; display: flex; flex-direction: column; overflow: hidden;
}
button { font: inherit; color: inherit; cursor: pointer; }
code, .mono { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }

/* ---- header ---- */
header {
  padding: 10px 16px; border-bottom: 1px solid var(--border);
  background: var(--panel); display: flex; gap: 16px; align-items: baseline;
  flex-wrap: wrap; flex: none;
}
header h1 { margin: 0; font-size: 15px; font-weight: 650; letter-spacing: -.01em; }
.meta { color: var(--muted); font-size: 12px; display: flex; gap: 12px; flex-wrap: wrap; }
.spacer { flex: 1 1 auto; }
.ghost {
  background: transparent; border: 1px solid var(--border);
  border-radius: 6px; padding: 4px 10px; font-size: 12px;
}
.ghost:hover { border-color: var(--accent); color: var(--accent); }

/* ---- coverage banner ---- */
.coverage {
  background: var(--warn-bg); border-bottom: 1px solid var(--warn-border);
  color: var(--warn-text); padding: 8px 16px; font-size: 12.5px; flex: none;
}
.coverage strong { font-weight: 650; }
.coverage ul { margin: 4px 0 0; padding-left: 18px; }
.coverage.ok { background: transparent; border-bottom-color: var(--border); color: var(--muted); }

/* ---- layout ---- */
main { flex: 1 1 auto; display: grid; grid-template-columns: 310px 1fr 330px; min-height: 0; }
.pane { min-width: 0; min-height: 0; display: flex; flex-direction: column; background: var(--panel); }
.pane + .pane { border-left: 1px solid var(--border); }
.pane-head {
  padding: 8px 12px; border-bottom: 1px solid var(--border); flex: none;
  font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted);
  display: flex; align-items: center; gap: 8px;
}
.pane-body { flex: 1 1 auto; overflow: auto; padding: 8px; }

/* ---- controls ---- */
input[type="search"] {
  width: 100%; padding: 6px 9px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text); font: inherit;
}
input[type="search"]:focus-visible, button:focus-visible, summary:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 1px;
}
.filters { padding: 8px 12px; border-bottom: 1px solid var(--border); flex: none; display: grid; gap: 6px; }
.chips { display: flex; gap: 5px; flex-wrap: wrap; }
.chip {
  border: 1px solid var(--border); background: transparent; border-radius: 999px;
  padding: 2px 9px; font-size: 11.5px; color: var(--muted);
}
.chip[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
.row { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); }
.row input[type="range"] { flex: 1; }

/* ---- foldable tree ---- */
.tree { list-style: none; margin: 0; padding: 0; }
.tree ul { list-style: none; margin: 0; padding-left: 14px; }
.node-row { display: flex; align-items: center; gap: 4px; width: 100%; }
.twisty {
  border: 0; background: transparent; padding: 0; width: 16px; flex: none;
  color: var(--muted); font-size: 10px; line-height: 1; transition: transform .12s ease;
}
.twisty[aria-expanded="true"] { transform: rotate(90deg); }
.twisty.leaf { visibility: hidden; }
.label {
  border: 0; background: transparent; padding: 2px 5px; border-radius: 5px;
  text-align: left; flex: 1 1 auto; min-width: 0; display: flex; gap: 6px;
  align-items: baseline; font-size: 12.5px;
}
.label:hover { background: var(--accent-soft); }
.label[aria-current="true"] { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.label .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.label .ct { color: var(--muted); font-size: 11px; flex: none; }
.kind {
  font-size: 9.5px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--muted); border: 1px solid var(--border); border-radius: 3px;
  padding: 0 3px; flex: none;
}
.dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
.lang-python { background: var(--py); } .lang-sql { background: var(--sql); }
.lang-typescript { background: var(--ts); } .lang-unknown { background: var(--unknown); }
.hidden { display: none !important; }
.empty { color: var(--muted); font-size: 12px; padding: 10px; }

/* ---- graph ---- */
.canvas-wrap { position: relative; flex: 1 1 auto; min-height: 0; }
canvas { display: block; width: 100%; height: 100%; cursor: grab; }
canvas.dragging { cursor: grabbing; }
.tooltip {
  position: absolute; pointer-events: none; background: var(--panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 5px 8px; font-size: 12px;
  box-shadow: var(--shadow); max-width: 260px; opacity: 0; transition: opacity .1s;
}
.tooltip.show { opacity: 1; }
.legend {
  position: absolute; left: 10px; bottom: 10px; background: var(--panel);
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px;
  font-size: 11.5px; color: var(--muted); box-shadow: var(--shadow);
}
.legend div { display: flex; align-items: center; gap: 6px; }
.swatch { width: 16px; height: 3px; border-radius: 2px; }

/* ---- details ---- */
.detail-title { font-size: 14px; font-weight: 650; word-break: break-word; margin: 0 0 2px; }
.detail-sub { color: var(--muted); font-size: 12px; margin: 0 0 10px; word-break: break-word; }
.sec { margin-top: 12px; }
.sec > h3 {
  font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); margin: 0 0 5px; display: flex; align-items: center; gap: 6px;
}
.bar { width: 3px; height: 11px; border-radius: 2px; }
.bar.in { background: var(--in); } .bar.out { background: var(--out); }
/* minmax(0,1fr) + min-width:0 stop the grid track from growing to the widest
   symbol name, which otherwise pushes the file column outside the pane. */
.link-list {
  list-style: none; margin: 0; padding: 0; display: grid; gap: 1px;
  grid-template-columns: minmax(0, 1fr);
}
.link-list > li { min-width: 0; }
.link-list button {
  width: 100%; text-align: left; border: 0; background: transparent; border-radius: 5px;
  padding: 3px 6px; font-size: 12px; display: flex; gap: 8px; align-items: baseline;
  min-width: 0;
}
.link-list button:hover { background: var(--accent-soft); }
/* Both columns must be allowed to shrink, or long symbol names push the file
   column outside the pane instead of ellipsising inside it. */
.link-list button > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.link-list button > span:first-child { flex: 1 1 auto; min-width: 4ch; }
.link-list .where {
  color: var(--muted); font-size: 11px; margin-left: auto;
  flex: 0 1 auto; min-width: 0; max-width: 45%; text-align: right;
}
.tags { display: flex; gap: 4px; flex-wrap: wrap; }
.tag { font-size: 10.5px; background: var(--accent-soft); color: var(--accent); border-radius: 3px; padding: 1px 5px; }
kbd {
  font: 11px ui-monospace, monospace; border: 1px solid var(--border);
  border-bottom-width: 2px; border-radius: 4px; padding: 0 4px; color: var(--muted);
}

@media (max-width: 980px) {
  main { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr auto; }
  .pane + .pane { border-left: 0; border-top: 1px solid var(--border); }
}
"""


JS = """
(function () {
  "use strict";

  var DATA = window.__ATLAS__;
  var M = DATA.modules, ME = DATA.moduleEdges, SY = DATA.symbols, SE = DATA.symbolEdges;

  // ---------------------------------------------------------------- indexes
  var moduleByKey = {}, symbolById = {}, outAdj = {}, inAdj = {}, modOut = {}, modIn = {};
  M.forEach(function (m) { moduleByKey[m.key] = m; });
  SY.forEach(function (s) { symbolById[s.id] = s; });
  SE.forEach(function (e) {
    (outAdj[e.s] || (outAdj[e.s] = [])).push(e);
    (inAdj[e.t] || (inAdj[e.t] = [])).push(e);
  });
  ME.forEach(function (e) {
    (modOut[e.source] || (modOut[e.source] = [])).push(e);
    (modIn[e.target] || (modIn[e.target] = [])).push(e);
  });

  var state = {
    selected: null,          // module key or symbol id
    depth: 1,
    langs: {},               // language -> enabled
    edgeTypes: {},           // edge type -> enabled
    query: "",
    expanded: {},            // tree node key -> bool
  };
  M.forEach(function (m) { state.langs[m.language] = true; });
  ME.forEach(function (e) { state.edgeTypes[e.type] = true; });
  SE.forEach(function (e) { if (!(e.ty in state.edgeTypes)) state.edgeTypes[e.ty] = true; });

  function el(id) { return document.getElementById(id); }
  function isSymbol(id) { return id != null && !!symbolById[id]; }
  function moduleOf(id) { return isSymbol(id) ? symbolById[id].module : id; }
  function langOk(m) { return !!state.langs[m.language]; }

  // ---------------------------------------------------- neighbourhood (BFS)
  // Returns {key: hopDistance} over MODULE nodes, following only enabled edge
  // types and enabled languages. Direction-aware so the UI can colour callers
  // and callees differently.
  function neighbourhood(rootKey, depth, dir) {
    var seen = {}, frontier = [rootKey], hop = 0;
    seen[rootKey] = 0;
    while (hop < depth && frontier.length) {
      var next = [];
      frontier.forEach(function (k) {
        var lists = [];
        if (dir !== "in") lists.push([modOut[k] || [], "target"]);
        if (dir !== "out") lists.push([modIn[k] || [], "source"]);
        lists.forEach(function (pair) {
          pair[0].forEach(function (e) {
            if (!state.edgeTypes[e.type]) return;
            var other = e[pair[1]];
            var om = moduleByKey[other];
            if (!om || !langOk(om) || other in seen) return;
            seen[other] = hop + 1;
            next.push(other);
          });
        });
      });
      frontier = next; hop++;
    }
    return seen;
  }

  function activeSets() {
    var sel = state.selected;
    if (sel == null) return null;
    var root = moduleOf(sel);
    if (!moduleByKey[root]) return null;
    return {
      root: root,
      incoming: neighbourhood(root, state.depth, "in"),
      outgoing: neighbourhood(root, state.depth, "out"),
    };
  }

  // =========================================================== FORCE LAYOUT
  // Hand-rolled velocity-Verlet simulation. At ~80 module nodes the O(n^2)
  // repulsion is ~6k pair computations per tick, comfortably inside a frame,
  // so no Barnes-Hut approximation is needed.
  var canvas = el("graph"), ctx = canvas.getContext("2d");
  var nodes = [], edges = [], nodeByKey = {};
  var view = { x: 0, y: 0, k: 1 };
  var alpha = 1, running = true, fitted = false;
  var hovered = null, dragging = null, panning = null;

  // Deterministic seed from the module key: identical input graph => identical
  // starting layout => stable, diffable, reproducible screenshots.
  function seedHash(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = (h * 16777619) >>> 0; }
    return h;
  }

  function buildGraph() {
    nodes = []; nodeByKey = {};
    M.filter(langOk).forEach(function (m, i) {
      var h = seedHash(m.key);
      var ang = (h % 10000) / 10000 * Math.PI * 2;
      var rad = 120 + ((h >>> 13) % 1000) / 1000 * 220;
      var n = {
        key: m.key, mod: m, deg: 0,
        r: Math.max(5, Math.min(24, 4.5 + Math.sqrt(m.symbolCount) * 2.1)),
        x: Math.cos(ang) * rad, y: Math.sin(ang) * rad, vx: 0, vy: 0, pinned: false,
      };
      nodes.push(n); nodeByKey[m.key] = n;
    });
    edges = ME.filter(function (e) {
      return state.edgeTypes[e.type] && nodeByKey[e.source] && nodeByKey[e.target];
    }).map(function (e) {
      return { s: nodeByKey[e.source], t: nodeByKey[e.target], w: e.weight, type: e.type };
    });
    edges.forEach(function (e) { e.s.deg++; e.t.deg++; });
    alpha = 1; fitted = false;
    prewarm(260);
    fitToView();
    wake();
  }

  // One physics step, separated from painting so the layout can be advanced
  // head-of-time without rendering intermediate frames (see prewarm).
  function step() {
      var i, j, a, b, dx, dy, d2, d, f;
      // Repulsion (Coulomb-like), scaled by node area so big modules push harder.
      for (i = 0; i < nodes.length; i++) {
        a = nodes[i];
        for (j = i + 1; j < nodes.length; j++) {
          b = nodes[j];
          dx = b.x - a.x; dy = b.y - a.y; d2 = dx * dx + dy * dy || 0.01;
          if (d2 > 640000) continue;             // ignore far pairs
          d = Math.sqrt(d2);
          f = (1500 + a.r * b.r * 12) / d2;
          dx = dx / d * f; dy = dy / d * f;
          a.vx -= dx; a.vy -= dy; b.vx += dx; b.vy += dy;
        }
      }
      // Spring attraction along edges; heavier edges pull harder but saturate.
      edges.forEach(function (e) {
        dx = e.t.x - e.s.x; dy = e.t.y - e.s.y;
        d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        var rest = 70 + e.s.r + e.t.r;
        f = (d - rest) * 0.012 * Math.min(3, 1 + Math.log(1 + e.w));
        dx = dx / d * f; dy = dy / d * f;
        e.s.vx += dx; e.s.vy += dy; e.t.vx -= dx; e.t.vy -= dy;
      });
      // Gravity toward origin + integration with damping. Gravity scales with
      // 1/(1+degree): a node with no edges has no spring holding it in, so
      // uniform gravity lets it drift until fit-to-view has to zoom out and
      // squeeze the connected core into a corner. Well-connected nodes are held
      // by their springs and need only a light pull.
      nodes.forEach(function (n) {
        if (n.pinned) { n.vx = n.vy = 0; return; }
        var g = 0.0055 * (1 + 5 / (1 + n.deg));
        n.vx -= n.x * g; n.vy -= n.y * g;
        n.vx *= 0.86; n.vy *= 0.86;
        n.x += n.vx * alpha * 2.2; n.y += n.vy * alpha * 2.2;
      });
      alpha *= 0.986;
  }

  // Advance the layout without painting. Running the bulk of the settle before
  // the first frame means the page opens on a readable, already-framed graph
  // instead of a hairball that slowly expands for several seconds. The
  // remaining alpha animates, so motion still communicates the relaxation.
  function prewarm(steps) {
    for (var i = 0; i < steps && alpha > 0.02; i++) step();
  }

  function tick() {
    if (alpha > 0.005) {
      step();
      draw();
      requestAnimationFrame(tick);
      return;
    }
    // Settled: frame the result once, paint a final frame, then stop the loop so
    // an open tab costs nothing. Any interaction calls wake() to resume.
    if (!fitted) { fitted = true; fitToView(); }
    draw();
    running = false;
  }

  function resize() {
    var dpr = window.devicePixelRatio || 1;
    var r = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(r.width * dpr));
    canvas.height = Math.max(1, Math.round(r.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function draw() {
    var r = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, r.width, r.height);
    ctx.save();
    ctx.translate(r.width / 2 + view.x, r.height / 2 + view.y);
    ctx.scale(view.k, view.k);

    var sets = activeSets();
    var colIn = css("--in"), colOut = css("--out"), colMuted = css("--muted"), colText = css("--text");
    var langCol = { python: css("--py"), sql: css("--sql"), typescript: css("--ts") };

    // Edges first, so nodes sit on top.
    edges.forEach(function (e) {
      var hi = null;
      if (sets) {
        var sIn = e.s.key in sets.incoming, tIn = e.t.key in sets.incoming;
        var sOut = e.s.key in sets.outgoing, tOut = e.t.key in sets.outgoing;
        if (sIn && tIn) hi = "in";
        else if (sOut && tOut) hi = "out";
      }
      ctx.globalAlpha = sets ? (hi ? 0.95 : 0.06) : 0.3;
      ctx.strokeStyle = hi === "in" ? colIn : hi === "out" ? colOut : colMuted;
      ctx.lineWidth = (hi ? 1.5 : 0.8) + Math.min(2.4, Math.log(1 + e.w) * 0.6);
      // Quadratic curve keeps reciprocal edges visually distinct.
      var mx = (e.s.x + e.t.x) / 2, my = (e.s.y + e.t.y) / 2;
      var nx = -(e.t.y - e.s.y) * 0.11, ny = (e.t.x - e.s.x) * 0.11;
      ctx.beginPath();
      ctx.moveTo(e.s.x, e.s.y);
      ctx.quadraticCurveTo(mx + nx, my + ny, e.t.x, e.t.y);
      ctx.stroke();
      if (hi) {
        // Arrowhead showing direction of the call/import.
        var ang = Math.atan2(e.t.y - (my + ny), e.t.x - (mx + nx));
        var tipX = e.t.x - Math.cos(ang) * (e.t.r + 1.5);
        var tipY = e.t.y - Math.sin(ang) * (e.t.r + 1.5);
        ctx.fillStyle = hi === "in" ? colIn : colOut;
        ctx.beginPath();
        ctx.moveTo(tipX, tipY);
        ctx.lineTo(tipX - Math.cos(ang - 0.42) * 7, tipY - Math.sin(ang - 0.42) * 7);
        ctx.lineTo(tipX - Math.cos(ang + 0.42) * 7, tipY - Math.sin(ang + 0.42) * 7);
        ctx.closePath(); ctx.fill();
      }
    });

    var annotated = [];
    nodes.forEach(function (n) {
      var role = null, dist = 0;
      if (sets) {
        if (n.key === sets.root) role = "root";
        else if (n.key in sets.outgoing) { role = "out"; dist = sets.outgoing[n.key]; }
        else if (n.key in sets.incoming) { role = "in"; dist = sets.incoming[n.key]; }
      }
      ctx.globalAlpha = sets ? (role ? 1 : 0.13) : 1;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = langCol[n.mod.language] || css("--unknown");
      ctx.fill();
      if (role === "root" || n === hovered) {
        ctx.strokeStyle = colText; ctx.lineWidth = 2.2; ctx.stroke();
      } else if (role === "in" || role === "out") {
        ctx.strokeStyle = role === "in" ? colIn : colOut;
        ctx.lineWidth = 2.2; ctx.stroke();
      }
      annotated.push({ n: n, role: role, dist: dist });
    });
    ctx.restore();
    ctx.globalAlpha = 1;

    drawLabels(annotated, sets, r, colText);
  }

  // Labels are drawn in *screen* space, after the world transform is restored,
  // so font size and stroke weight stay visually constant at every zoom level
  // instead of scaling with the graph. A greedy pass then suppresses labels that
  // would collide with an already-placed one, highest priority first, which
  // keeps the dense hub readable rather than a pile of overlapping text.
  function drawLabels(annotated, sets, rect, colText) {
    var placed = [];
    var ranked = annotated.slice().sort(function (a, b) {
      return priority(b) - priority(a);
    });

    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (var i = 0; i < ranked.length; i++) {
      var item = ranked[i], n = item.n;
      var forced = item.role === "root" || n === hovered;
      // When nothing is selected, small peripheral nodes stay unlabelled until
      // the user zooms in; that keeps the default view legible.
      if (!forced && view.k < 0.55 && n.r < 9) continue;
      if (!forced && sets && !item.role) continue;

      var sx = rect.width / 2 + view.x + n.x * view.k;
      var sy = rect.height / 2 + view.y + n.y * view.k;
      if (sx < -60 || sy < -20 || sx > rect.width + 60 || sy > rect.height + 20) continue;

      var text = n.mod.file + (item.role && item.dist > 1 ? " (" + item.dist + ")" : "");
      ctx.font = (forced ? "600 " : "") + "11px ui-sans-serif, system-ui, sans-serif";
      var w = ctx.measureText(text).width;
      var top = sy + n.r * view.k + 3;
      var box = { x0: sx - w / 2 - 2, y0: top - 1, x1: sx + w / 2 + 2, y1: top + 13 };

      if (!forced && collides(box, placed)) continue;
      placed.push(box);

      ctx.globalAlpha = sets ? (item.role ? 1 : 0.35) : 0.92;
      // A halo keeps text readable where it crosses edges or nodes.
      ctx.strokeStyle = css("--panel");
      ctx.lineWidth = 3;
      ctx.strokeText(text, sx, top);
      ctx.fillStyle = colText;
      ctx.fillText(text, sx, top);
    }
    ctx.globalAlpha = 1;
  }

  function priority(item) {
    if (item.role === "root") return 1e6;
    if (item.n === hovered) return 9e5;
    if (item.role) return 5e5 - item.dist * 1000 + item.n.r;
    return item.n.r;
  }

  function collides(box, placed) {
    for (var i = 0; i < placed.length; i++) {
      var p = placed[i];
      if (box.x0 < p.x1 && box.x1 > p.x0 && box.y0 < p.y1 && box.y1 > p.y0) return true;
    }
    return false;
  }

  // Frame the whole graph once the simulation has settled, so the initial view
  // never leaves nodes stranded outside the viewport.
  function fitToView(padding) {
    if (!nodes.length) return;
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(function (n) {
      minX = Math.min(minX, n.x - n.r); maxX = Math.max(maxX, n.x + n.r);
      minY = Math.min(minY, n.y - n.r); maxY = Math.max(maxY, n.y + n.r);
    });
    var rect = canvas.getBoundingClientRect();
    var pad = padding == null ? 46 : padding;
    var w = Math.max(1, maxX - minX), h = Math.max(1, maxY - minY);
    view.k = Math.max(0.18, Math.min(2.4,
      Math.min((rect.width - pad * 2) / w, (rect.height - pad * 2) / h)));
    view.x = -((minX + maxX) / 2) * view.k;
    view.y = -((minY + maxY) / 2) * view.k;
  }

  function toWorld(ev) {
    var r = canvas.getBoundingClientRect();
    return {
      x: (ev.clientX - r.left - r.width / 2 - view.x) / view.k,
      y: (ev.clientY - r.top - r.height / 2 - view.y) / view.k,
    };
  }
  function hit(p) {
    for (var i = nodes.length - 1; i >= 0; i--) {
      var n = nodes[i], dx = p.x - n.x, dy = p.y - n.y;
      if (dx * dx + dy * dy <= (n.r + 4) * (n.r + 4)) return n;
    }
    return null;
  }

  // ------------------------------------------------------------ interaction
  var tip = el("tip");
  canvas.addEventListener("mousemove", function (ev) {
    if (dragging) {
      var p = toWorld(ev);
      dragging.x = p.x; dragging.y = p.y; dragging.pinned = true;
      alpha = Math.max(alpha, 0.3); wake(); return;
    }
    if (panning) {
      view.x += ev.clientX - panning.x; view.y += ev.clientY - panning.y;
      panning = { x: ev.clientX, y: ev.clientY }; draw(); return;
    }
    var n = hit(toWorld(ev));
    if (n !== hovered) { hovered = n; draw(); }
    if (n) {
      var kinds = Object.keys(n.mod.kinds).map(function (k) { return n.mod.kinds[k] + " " + k; });
      tip.innerHTML = "<strong>" + esc(n.mod.file) + "</strong><br>" +
        esc(n.mod.language) + " &middot; " + n.mod.symbolCount + " symbols" +
        (kinds.length ? "<br>" + esc(kinds.join(", ")) : "");
      tip.classList.add("show");
      var r = canvas.getBoundingClientRect();
      tip.style.left = Math.min(r.width - 270, ev.clientX - r.left + 12) + "px";
      tip.style.top = (ev.clientY - r.top + 12) + "px";
    } else {
      tip.classList.remove("show");
    }
  });
  canvas.addEventListener("mouseleave", function () {
    tip.classList.remove("show"); hovered = null; draw();
  });
  canvas.addEventListener("mousedown", function (ev) {
    var n = hit(toWorld(ev));
    if (n) { dragging = n; canvas.classList.add("dragging"); }
    else { panning = { x: ev.clientX, y: ev.clientY }; canvas.classList.add("dragging"); }
  });
  window.addEventListener("mouseup", function () {
    dragging = null; panning = null; canvas.classList.remove("dragging");
  });
  canvas.addEventListener("click", function (ev) {
    var n = hit(toWorld(ev));
    select(n ? n.key : null);
  });
  canvas.addEventListener("dblclick", function () {
    nodes.forEach(function (n) { n.pinned = false; });
    alpha = 0.7; fitted = false; wake();
  });
  canvas.addEventListener("wheel", function (ev) {
    ev.preventDefault();
    var f = Math.exp(-ev.deltaY * 0.0016);
    view.k = Math.max(0.18, Math.min(5, view.k * f));
    draw();
  }, { passive: false });

  function wake() { if (!running) { running = true; requestAnimationFrame(tick); } }

  // ================================================================= ESCAPE
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // =================================================================== TREE
  var treeRoot = el("tree");

  function buildTree() {
    var byLang = {};
    M.forEach(function (m) { (byLang[m.language] || (byLang[m.language] = [])).push(m); });
    var html = Object.keys(byLang).sort().map(function (lang) {
      var mods = byLang[lang];
      var total = mods.reduce(function (a, m) { return a + m.symbolCount; }, 0);
      return group("lang::" + lang,
        '<span class="dot lang-' + esc(lang) + '"></span><span class="nm">' + esc(lang) +
        '</span><span class="ct">' + mods.length + " files &middot; " + total + " symbols</span>",
        mods.map(function (m) {
          return group("mod::" + m.key,
            '<span class="nm mono">' + esc(m.file) + '</span><span class="ct">' +
            m.symbolCount + "</span>",
            m.tree.map(function (s) { return symbolNode(s, m); }),
            m.key);
        }).join(""));
    }).join("");
    treeRoot.innerHTML = html;
  }

  function group(key, inner, childrenHtml, selKey) {
    var open = !!state.expanded[key];
    var kids = [].concat(childrenHtml).join("");
    return '<li data-key="' + esc(key) + '">' +
      '<div class="node-row">' +
      '<button class="twisty" aria-expanded="' + open + '" data-toggle="' + esc(key) +
      '" aria-label="Toggle">&#9654;</button>' +
      '<button class="label"' + (selKey ? ' data-select="' + esc(selKey) + '"' : "") + ">" +
      inner + "</button></div>" +
      '<ul class="' + (open ? "" : "hidden") + '">' + kids + "</ul></li>";
  }

  function symbolNode(s, m) {
    var kids = (s.children || []).map(function (c) { return symbolNode(c, m); });
    var inner = '<span class="kind">' + esc(s.kind.slice(0, 4)) + '</span><span class="nm mono">' +
      esc(s.name) + "</span>" +
      (s.line ? '<span class="ct">:' + s.line + "</span>" : "");
    if (kids.length) return group("sym::" + s.id, inner, kids, s.id);
    return '<li data-key="sym::' + esc(s.id) + '">' +
      '<div class="node-row"><button class="twisty leaf" tabindex="-1"></button>' +
      '<button class="label" data-select="' + esc(s.id) + '">' + inner + "</button></div></li>";
  }

  treeRoot.addEventListener("click", function (ev) {
    var t = ev.target.closest("[data-toggle]");
    if (t) {
      var key = t.getAttribute("data-toggle");
      state.expanded[key] = !state.expanded[key];
      t.setAttribute("aria-expanded", String(!!state.expanded[key]));
      var ul = t.closest("li").querySelector(":scope > ul");
      if (ul) ul.classList.toggle("hidden", !state.expanded[key]);
      return;
    }
    var s = ev.target.closest("[data-select]");
    if (s) select(s.getAttribute("data-select"));
  });

  function applyTreeFilter() {
    var q = state.query.trim().toLowerCase();
    var items = treeRoot.querySelectorAll("li");
    // Pass 1: leaf visibility from query + language filter.
    items.forEach(function (li) {
      var key = li.getAttribute("data-key") || "";
      var lang = key.indexOf("lang::") === 0 ? key.slice(6) : null;
      if (lang) { li.classList.toggle("hidden", !state.langs[lang]); return; }
      var label = li.querySelector(":scope > .node-row > .label");
      var text = label ? label.textContent.toLowerCase() : "";
      li.dataset.match = (!q || text.indexOf(q) !== -1) ? "1" : "0";
    });
    // Pass 2: a node stays visible if it or any descendant matches.
    var all = Array.prototype.slice.call(items).reverse();
    all.forEach(function (li) {
      if ((li.getAttribute("data-key") || "").indexOf("lang::") === 0) return;
      var self = li.dataset.match === "1";
      var kid = li.querySelector(":scope > ul > li:not(.hidden)");
      li.classList.toggle("hidden", !(self || kid));
      if (q && kid) {
        var ul = li.querySelector(":scope > ul");
        if (ul) ul.classList.remove("hidden");
        var tw = li.querySelector(":scope > .node-row > .twisty");
        if (tw) tw.setAttribute("aria-expanded", "true");
      }
    });
    el("tree-empty").classList.toggle("hidden",
      !!treeRoot.querySelector(":scope > li:not(.hidden)"));
  }

  function revealAndMark(id) {
    treeRoot.querySelectorAll('.label[aria-current="true"]').forEach(function (b) {
      b.removeAttribute("aria-current");
    });
    if (id == null) return;
    var btn = treeRoot.querySelector('.label[data-select="' + cssEsc(id) + '"]');
    if (!btn) return;
    btn.setAttribute("aria-current", "true");
    var li = btn.closest("li");
    while (li) {
      var ul = li.parentElement;
      if (ul && ul.tagName === "UL") {
        ul.classList.remove("hidden");
        var owner = ul.closest("li");
        var tw = owner && owner.querySelector(":scope > .node-row > .twisty");
        if (tw) { tw.setAttribute("aria-expanded", "true"); state.expanded[owner.getAttribute("data-key")] = true; }
        li = owner;
      } else break;
    }
    btn.scrollIntoView({ block: "nearest" });
  }
  function cssEsc(s) {
    return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\\\]/g, "\\\\$&");
  }

  // ================================================================ DETAILS
  function renderDetails() {
    var box = el("details"), sel = state.selected;
    if (sel == null) {
      box.innerHTML = '<p class="empty">Select a file in the graph or a symbol in the tree to see ' +
        "what calls it and what it calls.<br><br>" +
        "<kbd>scroll</kbd> zoom &middot; <kbd>drag</kbd> pan or move a node &middot; " +
        "<kbd>dbl-click</kbd> reset</p>";
      return;
    }
    var html = "";
    if (isSymbol(sel)) {
      var s = symbolById[sel], m = moduleByKey[s.module];
      html += '<p class="detail-title mono">' + esc(s.name) + "</p>" +
        '<p class="detail-sub">' + esc(s.kind) + " in " + esc(m ? m.file : "?") +
        (s.line ? ":" + s.line : "") + "</p>";
      if (s.tags.length || s.entry) {
        html += '<div class="tags">' + (s.entry ? '<span class="tag">entry point</span>' : "") +
          s.tags.map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("") +
          "</div>";
      }
      html += linkSection("Called by", "in", (inAdj[sel] || []).filter(typeOk).map(function (e) {
        return e.s;
      }));
      html += linkSection("Calls", "out", (outAdj[sel] || []).filter(typeOk).map(function (e) {
        return e.t;
      }));
    } else {
      var mm = moduleByKey[sel];
      if (!mm) { box.innerHTML = '<p class="empty">Unknown selection.</p>'; return; }
      html += '<p class="detail-title mono">' + esc(mm.file) + "</p>" +
        '<p class="detail-sub">' + esc(mm.language) + " &middot; " + mm.symbolCount +
        " symbols &middot; " + Object.keys(mm.kinds).map(function (k) {
          return mm.kinds[k] + " " + k;
        }).join(", ") + "</p>";
      html += modSection("Imported / called by", "in", (modIn[sel] || []).filter(function (e) {
        return state.edgeTypes[e.type];
      }), "source");
      html += modSection("Depends on", "out", (modOut[sel] || []).filter(function (e) {
        return state.edgeTypes[e.type];
      }), "target");
    }
    box.innerHTML = html;
  }
  function typeOk(e) { return state.edgeTypes[e.ty]; }

  function linkSection(title, dir, ids) {
    var uniq = [], seen = {};
    ids.forEach(function (i) { if (!seen[i]) { seen[i] = 1; uniq.push(i); } });
    uniq.sort();
    var items = uniq.map(function (id) {
      var s = symbolById[id];
      var where = s && moduleByKey[s.module] ? moduleByKey[s.module].file : "";
      return '<li><button data-goto="' + esc(id) + '"><span class="mono">' +
        esc(s ? s.name : id) + '</span><span class="where mono">' + esc(where) + "</span></button></li>";
    }).join("");
    return section(title, dir, uniq.length, items);
  }
  function modSection(title, dir, list, field) {
    var items = list.map(function (e) {
      var k = e[field], m = moduleByKey[k];
      return '<li><button data-goto="' + esc(k) + '"><span class="mono">' +
        esc(m ? m.file : k) + '</span><span class="where">' + esc(e.type) + " &times;" +
        e.weight + "</span></button></li>";
    }).join("");
    return section(title, dir, list.length, items);
  }
  function section(title, dir, count, items) {
    return '<div class="sec"><h3><span class="bar ' + dir + '"></span>' + esc(title) +
      " (" + count + ")</h3>" +
      (count ? '<ul class="link-list">' + items + "</ul>" : '<p class="empty">none</p>') + "</div>";
  }

  el("details").addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-goto]");
    if (b) select(b.getAttribute("data-goto"));
  });

  // ============================================================ SELECT / URL
  function select(id) {
    state.selected = id;
    revealAndMark(id);
    renderDetails();
    syncHash();
    // Deliberately does NOT re-heat the simulation: a node must not move just
    // because it was selected, or the reader loses their mental map of the graph.
    draw();
  }

  function syncHash() {
    var p = new URLSearchParams();
    if (state.selected) p.set("sel", state.selected);
    if (state.depth !== 1) p.set("depth", String(state.depth));
    if (state.query) p.set("q", state.query);
    var offLangs = Object.keys(state.langs).filter(function (l) { return !state.langs[l]; });
    if (offLangs.length) p.set("nolang", offLangs.join(","));
    var offTypes = Object.keys(state.edgeTypes).filter(function (t) { return !state.edgeTypes[t]; });
    if (offTypes.length) p.set("noedge", offTypes.join(","));
    var h = p.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname);
  }

  function readHash() {
    var p = new URLSearchParams(location.hash.replace(/^#/, ""));
    (p.get("nolang") || "").split(",").filter(Boolean).forEach(function (l) { state.langs[l] = false; });
    (p.get("noedge") || "").split(",").filter(Boolean).forEach(function (t) { state.edgeTypes[t] = false; });
    state.depth = Math.max(1, Math.min(4, parseInt(p.get("depth") || "1", 10) || 1));
    state.query = p.get("q") || "";
    state.selected = p.get("sel") || null;
  }

  // ============================================================== CONTROLS
  function renderChips() {
    el("lang-chips").innerHTML = Object.keys(state.langs).sort().map(function (l) {
      return '<button class="chip" data-lang="' + esc(l) + '" aria-pressed="' +
        !!state.langs[l] + '"><span class="dot lang-' + esc(l) + '"></span> ' + esc(l) + "</button>";
    }).join("");
    el("edge-chips").innerHTML = Object.keys(state.edgeTypes).sort().map(function (t) {
      return '<button class="chip" data-edge="' + esc(t) + '" aria-pressed="' +
        !!state.edgeTypes[t] + '">' + esc(t) + "</button>";
    }).join("");
  }

  el("lang-chips").addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-lang]"); if (!b) return;
    var l = b.getAttribute("data-lang");
    state.langs[l] = !state.langs[l];
    b.setAttribute("aria-pressed", String(state.langs[l]));
    buildGraph(); applyTreeFilter(); syncHash(); wake();
  });
  el("edge-chips").addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-edge]"); if (!b) return;
    var t = b.getAttribute("data-edge");
    state.edgeTypes[t] = !state.edgeTypes[t];
    b.setAttribute("aria-pressed", String(state.edgeTypes[t]));
    buildGraph(); renderDetails(); syncHash(); wake();
  });
  el("depth").addEventListener("input", function (ev) {
    state.depth = parseInt(ev.target.value, 10);
    el("depth-val").textContent = state.depth;
    syncHash(); draw();
  });
  el("q").addEventListener("input", function (ev) {
    state.query = ev.target.value;
    applyTreeFilter(); syncHash();
  });
  el("expand-all").addEventListener("click", function () {
    treeRoot.querySelectorAll("[data-toggle]").forEach(function (t) {
      state.expanded[t.getAttribute("data-toggle")] = true;
      t.setAttribute("aria-expanded", "true");
      var ul = t.closest("li").querySelector(":scope > ul");
      if (ul) ul.classList.remove("hidden");
    });
  });
  el("collapse-all").addEventListener("click", function () {
    treeRoot.querySelectorAll("[data-toggle]").forEach(function (t) {
      state.expanded[t.getAttribute("data-toggle")] = false;
      t.setAttribute("aria-expanded", "false");
      var ul = t.closest("li").querySelector(":scope > ul");
      if (ul) ul.classList.add("hidden");
    });
  });
  el("theme").addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme");
    var next = cur === "dark" ? "light" : cur === "light" ? "dark"
      : (matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark");
    document.documentElement.setAttribute("data-theme", next);
    draw();
  });
  el("clear").addEventListener("click", function () { select(null); });

  // ================================================================== BOOT
  readHash();
  renderChips();
  buildTree();
  el("depth").value = String(state.depth);
  el("depth-val").textContent = state.depth;
  el("q").value = state.query;
  applyTreeFilter();
  buildGraph();
  revealAndMark(state.selected);
  renderDetails();
  window.addEventListener("resize", resize);
  resize();
  requestAnimationFrame(tick);
})();
"""
