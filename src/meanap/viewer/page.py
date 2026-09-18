"""The viewer's single HTML page.

Kept as one self-contained string — no build step, no external assets, no CDN.
A bundle gets shared with people who will run one command and expect a page;
anything that needs npm or a network fetch fails that test.

Three tabs, because a run holds three different kinds of question:

* **Recordings** — one spatial network plot at a time, with the full Network
  Viewer control set live beside it. Every change re-requests the figure from
  Python, so what is on screen is always something the pipeline could have
  drawn.
* **Comparisons** — the 2B/4B half-violin sets. These used to be a gallery of
  every small multiple at once: 274 of them on a three-lag run, in one scroll,
  with the only organisation in the caption text. They are now selected by the
  address each figure actually has — lag, level, split, metric — and drawn one
  at a time. The CAT-NAP cell-type families, which have no such address, stay
  galleries, listed separately so the difference is visible rather than
  surprising.
* **Across lags** — the two sets whose subject is the lag itself: each metric's
  curve against lag, and the cartography roles at each lag. They answer a
  different question from anything sliced at one lag, so they get their own
  tab rather than sitting among figures that are all one lag deep.

The styling controls are *hidden* outside the Recordings tab, not disabled:
they style spatial network plots, and no violin or line plot reads them. A
greyed-out panel would still imply the knobs mean something there.
"""

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MEA-NAP viewer</title>
<style>
  :root {
    /* Plot colours live here rather than in the script so the theme toggle
       moves them too. The dark variants are lightened: the light-theme blues
       and purples sit at roughly 30% luminance and vanish on a dark ground. */
    --plot-wt: #2c7fb8; --plot-het: #7b3294; --plot-ko: #d95f0e;
    --plot-other: #6b7280; --plot-off: #98a0a8; --plot-sel: #d62728;
    --bg: #ffffff; --fg: #16181d; --muted: #6b7280; --line: #e3e6ea;
    --panel: #f7f8fa; --accent: #2563eb; --accent-soft: #eaf0fe;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --plot-wt: #5aa9dd; --plot-het: #b07bd6; --plot-ko: #f2a057;
      --plot-other: #9aa1ac; --plot-off: #6b747d; --plot-sel: #ff6b6b;
      --bg: #14161a; --fg: #e7e9ee; --muted: #9aa1ac; --line: #2a2e35;
      --panel: #1b1e24; --accent: #6ea8fe; --accent-soft: #1e2836;
    }
  }
  /* The toggle has to win in both directions, so dark is also stated
     explicitly rather than only as a media-query default. */
  :root[data-theme="dark"] {
    --plot-wt: #5aa9dd; --plot-het: #b07bd6; --plot-ko: #f2a057;
    --plot-other: #9aa1ac; --plot-off: #6b747d; --plot-sel: #ff6b6b;
    --bg: #14161a; --fg: #e7e9ee; --muted: #9aa1ac; --line: #2a2e35;
    --panel: #1b1e24; --accent: #6ea8fe; --accent-soft: #1e2836;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    display: grid; height: 100vh;
    grid-template-columns: 260px 1fr 280px;
    grid-template-rows: auto 1fr;
    grid-template-areas: "tabs tabs tabs" "left main right";
    transition: grid-template-columns .12s ease; }
  /* The right column is a fixed track, so hiding the panel inside it leaves a
     280px gap. Collapse the track itself when nothing is in it. */
  body.no-right { grid-template-columns: 260px 1fr 0;
  }
  @media (max-width: 900px) {
    body { grid-template-columns: 1fr; grid-template-rows: auto auto auto auto;
           grid-template-areas: "tabs" "left" "main" "right"; height: auto; }
  }

  #tabs { grid-area: tabs; display: flex; gap: 4px; align-items: center;
    border-bottom: 1px solid var(--line); padding: 0 14px; background: var(--panel); }
  #tabs .brand { font-size: 13px; font-weight: 600; margin-right: 14px;
    padding: 10px 0; letter-spacing: -0.01em; }
  #tabs button { width: auto; background: transparent; border: none;
    border-bottom: 2px solid transparent; border-radius: 0; padding: 11px 14px;
    color: var(--muted); font-weight: 500; }
  #tabs button:hover { color: var(--fg); }
  #tabs button[aria-selected="true"] {
    color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
  #tabs .spacer { flex: 1; }
  #params { padding: 4px 2px 24px; overflow-y: auto; }
  #params h3 { margin: 20px 0 6px; font-size: 12px; letter-spacing: .04em;
    text-transform: uppercase; color: var(--muted); font-weight: 600; }
  #params table { border-collapse: collapse; width: 100%; max-width: 860px;
    font-size: 13px; }
  #params td { padding: 5px 10px; border-top: 1px solid var(--line);
    vertical-align: top; }
  #params tr.changed td.k, #params tr.changed td.v { font-weight: 600; }
  #params td.k { width: 38%; font-family: ui-monospace, SFMono-Regular, Menlo,
    monospace; word-break: break-word; }
  #params td.v { width: 37%; word-break: break-word; }
  #params td.d { width: 25%; color: var(--muted); font-size: 12px; }
  #params .redacted { color: var(--muted); font-style: italic; }
  #params .lead { color: var(--muted); font-size: 13px; margin: 4px 0 14px; }
  #tabs .src { color: var(--muted); font-size: 12px; padding-right: 4px;
    overflow-wrap: anywhere; max-width: 40ch; text-align: right; }

  aside { overflow-y: auto; padding: 16px; }
  aside.left { grid-area: left; border-right: 1px solid var(--line); }
  aside.right { grid-area: right; border-left: 1px solid var(--line); }
  main { grid-area: main; overflow-y: auto; padding: 20px 24px; min-width: 0;
         display: flex; flex-direction: column; }

  .sub { color: var(--muted); font-size: 12px; margin-bottom: 14px;
         overflow-wrap: anywhere; }
  h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
       color: var(--muted); margin: 18px 0 8px; font-weight: 600; }
  h2:first-child { margin-top: 0; }

  select, input, button { font: inherit; color: inherit; background: var(--bg);
    border: 1px solid var(--line); border-radius: 6px; padding: 5px 7px; width: 100%; }
  button { cursor: pointer; }
  button:hover { border-color: var(--accent); }
  label { display: block; margin-bottom: 10px; font-size: 12px; color: var(--muted); }
  label span.l { display: block; margin-bottom: 3px; color: var(--fg); }
  label small { display: block; margin-top: 3px; color: var(--muted); font-size: 11px; }
  #rec-fs { margin-top: 4px; font-size: 11.5px; color: var(--muted); line-height: 1.45; }
  #rec-fs.mixed { color: #b45309; }
  #rec-fs b { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 600; }
  /* A control the current mode does not read — see syncNodeSizeMode. */
  label.muted { opacity: .45; }
  label.muted input { cursor: not-allowed; }

  .list { display: flex; flex-direction: column; gap: 2px; }
  .list button { text-align: left; border: 1px solid transparent;
    background: transparent; border-radius: 6px; padding: 6px 8px; }
  .list button:hover { background: var(--panel); }
  .list button[aria-current="true"] {
    background: var(--accent-soft); border-color: var(--accent); font-weight: 600; }

  figure { margin: 0 0 20px; }
  figure img { max-width: 100%; height: auto; display: block;
    border: 1px solid var(--line); border-radius: 8px; background: #fff; }
  figure figcaption { font-size: 12px; color: var(--muted); margin-top: 6px; }
  /* A single figure fits the pane: main is a 1fr row of a 100vh grid, so it
     has a height to give, and the image shrinks to what is left below the
     toolbar. The served PNG is untouched — only on-screen scaling. min-height
     overrides the flex default that refuses to shrink below content; flex-start
     keeps the width derived from the shrunken height, so the border still hugs
     the picture. Galleries and the parameters table keep scrolling.
     The pair's figures share the pane by their own height (basis auto, not
     0): under 900px the grid stacks and main has no height to give, and a
     zero basis with nothing to grow into left the figure zero pixels tall. */
  #single, #pair { flex: 1 1 auto; min-height: 0; display: flex;
    flex-direction: column; }
  #pair figure { flex: 1 1 auto; min-height: 0; display: flex;
    flex-direction: column; }
  #single img, #pair img { flex: 0 1 auto; min-height: 0;
    align-self: flex-start; object-fit: contain; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
         margin-bottom: 14px; }
  .row button { width: auto; }
  .status { color: var(--muted); font-size: 12px; min-height: 18px; }
  .err { color: #b42318; white-space: pre-wrap; font-size: 12px; }

  .gallery { display: grid; gap: 14px;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); }
  .gallery figure { border: 1px solid var(--line); border-radius: 8px;
    padding: 8px; background: var(--panel); margin: 0; }
  .gallery img { border: none; border-radius: 4px; }
  .gallery figcaption { font-size: 11px; color: var(--muted); margin-top: 6px;
    overflow-wrap: anywhere; }
  .group-head { grid-column: 1 / -1; font-size: 11px; text-transform: uppercase;
    letter-spacing: .08em; color: var(--muted); margin-top: 8px; }
  .hidden { display: none !important; }
  .trackgrid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(430px, 1fr));
               padding: 4px 2px 16px; }
  .trackfig { margin: 0; border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
  .trackfig figcaption { font-size: 12.5px; margin-bottom: 6px; }
  .trackplot { width: 100%; height: auto; display: block; }
  .trackgrid .legend { display: flex; gap: 12px; flex-wrap: wrap; font-size: 11px;
                       margin-top: 4px; }
  #tip { position: fixed; z-index: 99; display: none; max-width: 330px;
         background: var(--panel); color: var(--fg); border: 1px solid var(--line);
         border-radius: 7px; padding: 8px 10px; font-size: 12px; line-height: 1.45;
         box-shadow: 0 6px 22px rgba(0,0,0,.28); pointer-events: none; }
  #tip hr { border: 0; border-top: 1px solid var(--line); margin: 5px 0; }
  #tip .dim { color: var(--muted); }
  #tip code { font-size: 11.5px; }
  .warn { color: var(--plot-ko); }
  .hotdot { cursor: help; }
  .hotdot:hover { stroke: var(--fg); stroke-width: 1.4px; }
  .axhelp { cursor: help; text-decoration: underline dotted; }
  .trackgrid .legend .sw { display: inline-block; width: 10px; height: 10px;
                           border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
  .twocol { display: flex; gap: 18px; flex-wrap: wrap; }
  .netrow { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-start; }
  .netfig { flex: 0 0 auto; }
  .netlegend { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
               font-size: 11px; margin-bottom: 8px; }
  .netlegend .ramp { display: inline-block; width: 160px; height: 10px;
                     border-radius: 3px; border: 1px solid var(--line); }
  .netnode { cursor: pointer; }
  .netplot { cursor: grab; touch-action: none; }
  .netplot:active { cursor: grabbing; }
  .netfig figcaption { margin-top: 4px; text-align: center; }
  .tracktab { border-collapse: collapse; font-size: 12px; flex: 1 1 160px; }
  .tracktab th, .tracktab td { text-align: left; padding: 2px 8px 2px 0;
                               border-bottom: 1px solid var(--line); }
  .tracktab .num { text-align: right; font-variant-numeric: tabular-nums; }
  .tracktab .bar { display: inline-block; height: 7px; border-radius: 3px;
                   background: var(--plot-wt); min-width: 1px; }
</style>
</head>
<body>

<nav id="tabs">
  <span class="brand">MEA-NAP viewer</span>
  <button id="tab-recordings" data-tab="recordings" aria-selected="true">Recordings</button>
  <button id="tab-comparisons" data-tab="comparisons" aria-selected="false">Comparisons</button>
  <button id="tab-lags" data-tab="lags" aria-selected="false">Across lags</button>
  <button id="tab-tracking" data-tab="tracking" aria-selected="false"
          class="hidden">Cell tracking</button>
  <button id="theme" class="ghost" title="Light, dark, or follow the system"
          aria-label="Theme">◐ system</button>
  <button id="tab-stats" data-tab="stats" aria-selected="false">Statistics</button>
  <button id="tab-params" data-tab="params" aria-selected="false">Parameters</button>
  <span class="spacer"></span>
  <button id="export" class="hidden" title="Draw every figure out into an ordinary
folder, with a report.html to browse them — for sending results to someone who
does not have MEA-NAP installed.">Export output folder</button>
  <span class="src" id="source">loading…</span>
</nav>

<aside class="left">
  <div id="side-recordings">
    <h2>Recording</h2>
    <select id="recording"></select>
    <div id="rec-fs"></div>
    <h2 id="lag-head">Lag</h2>
    <select id="lag"></select>

    <h2>Network figures</h2>
    <div class="list" id="figures"></div>

    <h2>Activity figures</h2>
    <div class="list" id="activity"></div>

    <h2>Spike detection</h2>
    <div class="list" id="spikechecks"></div>

    <h2>Peak detection traces</h2>
    <div class="list" id="traces"></div>

    <h2>Edge thresholding</h2>
    <div class="list" id="edgechecks"></div>

    <h2>Cell-type subnetworks</h2>
    <div class="list" id="subnetworks"></div>
  </div>

  <div id="side-comparisons" class="hidden">
    <h2>Comparison set</h2>
    <select id="cmp-family"></select>
    <h2>Metric</h2>
    <div class="list" id="cmp-metrics"></div>
    <h2>Galleries</h2>
    <p class="sub">Sets that have no per-figure address — shown all at once.</p>
    <div class="list" id="families"></div>
  </div>

  <div id="side-params" class="hidden">
    <h2>Settings</h2>
    <div class="list" id="param-groups"></div>
  </div>

  <div id="side-tracking" class="hidden">
    <h2>View</h2>
    <select id="track-view">
      <option value="overview">Overview &mdash; all chains</option>
      <option value="cells">Cells &mdash; one chain</option>
      <option value="network">Network &mdash; one chain</option>
    </select>
    <h2>Chain</h2>
    <p class="sub">Ordered by how well matches separate from a co-located
    different cell &mdash; not by match rate. The two disagree.</p>
    <select id="track-chain"></select>
    <div id="track-meta" class="sub"></div>
  </div>
  <div id="side-stats" class="hidden">
    <h2 id="stats-lag-head">Timescale</h2>
    <select id="stats-lag"></select>
    <div class="list" id="stats-figures"></div>
  </div>

  <div id="side-lags" class="hidden">
    <h2>Figure set</h2>
    <div class="list" id="lag-series"></div>
    <h2 id="lag-options-head">Figures</h2>
    <div class="list" id="lag-options"></div>
  </div>
</aside>

<main>
  <div class="row" id="toolbar">
    <span class="status" id="status"></span>
    <span style="flex:1"></span>
    <button id="dl-png">Download PNG</button>
    <button id="dl-svg">Download SVG</button>
    <button id="dl-pdf">Download PDF</button>
  </div>
  <div class="err" id="error"></div>
  <figure id="single"><img id="figure-img" alt="">
    <figcaption id="figure-caption" class="sub hidden"></figcaption>
  </figure>
  <div id="pair" class="hidden"></div>
  <div class="gallery hidden" id="gallery"></div>
  <div id="params" class="hidden"></div>
  <div id="tracking" class="hidden"></div>
</main>

<aside class="right" id="controls-panel">
  <div id="variant-panel">
    <h2>Scaling</h2>
    <div class="list" id="variants"></div>
    <p class="sub" style="margin-bottom:12px">
      Individual uses this recording's own range; batch shares one scale across
      every recording, so panels can be compared directly.
    </p>
  </div>
  <h2>Network styling</h2>
  <div id="controls"></div>
  <button id="reset">Reset to pipeline defaults</button>
  <p class="sub" style="margin-top:12px">
    Defaults reproduce the figure the pipeline drew, pixel for pixel.
  </p>
</aside>

<aside class="right hidden" id="facets-panel">
  <h2 id="facets-head">Facets</h2>
  <label id="cmp-lag-label"><span class="l" id="cmp-lag-head">Lag</span>
    <select id="cmp-lag"></select></label>
  <label id="cmp-level-label"><span class="l">Level</span>
    <select id="cmp-level"></select>
    <small>Each point is one recording, or one node.</small></label>
  <label id="cmp-split-label"><span class="l">Split</span>
    <select id="cmp-split"></select>
    <small>Which factor becomes the panels.</small></label>
  <h2>Colours</h2>
  <div id="cmp-controls"></div>
  <button id="cmp-reset">Reset to pipeline defaults</button>
  <p class="sub" style="margin-top:12px">
    These are the figures the pipeline writes to 4B/2B, drawn one at a time.
    Defaults reproduce them exactly.
  </p>
</aside>

<script>
const $ = (id) => document.getElementById(id);
let MANIFEST = null;

// "Lag" or "Bin": a CAT-NAP correlation run's numbers are bin lengths, not
// coincidence windows. Bundles written before the manifest carried this have
// no field, and every one of those was an STTC run.
function timescaleLabel() {
  return (MANIFEST && MANIFEST.timescale === "bin") ? "Bin" : "Lag";
}
let TAB = "recordings";
// Which scaling of a network plot is showing. Reset to "plain" whenever the
// selected figure changes, since not every figure has the other two.
let VARIANT = "plain";
const VARIANT_LABELS = {plain: "Individual", scaled: "Batch-scaled",
                        combined: "Side by side"};
// One selection per tab, never a shared field: the tabs are filled before any
// of them is shown, so a name that means "network figure" on one tab and
// "metric" on another gets overwritten during startup and the first render
// asks for a figure that doesn't exist.
let VIEW = {
  kind: "figure",
  rec: null, lag: null, name: null,   // Recordings
  family: null, metric: null,         // Comparisons
  series: null, key: null,            // Across lags
  statsLag: null, statsKey: null,     // Statistics
  statsLabel: null, statsCaption: null,
  gallery: null,                      // a family shown as a gallery
};
// "figure"     — a network plot, per recording + lag, restylable
// "activity"   — a step-2 plot, per recording only; the network controls don't
//                apply to a raster or a heatmap, so they are hidden for it
// "spikecheck" — a step-1 detection check, per recording; like "activity" but
//                with no styling at all, since its axes are fixed to the
//                recording's own noise level
// "edgecheck"  — a step-3 thresholding check, per recording + lag; also
//                unstyled, and usually absent (the run has to ask for it)
// "subnetwork" — a CAT-NAP cell-type figure, per recording + lag, unstyled
// "comparison" — one 2B/4B half-violin, addressed by lag/level/split/metric
// "both"       — the same metric drawn by group and by age, stacked
// "lagseries"  — one across-lag figure
// "family"     — a gallery of small multiples, for sets with no address

async function getJSON(url) {
  const r = await fetch(url);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

/* ── Recordings tab ─────────────────────────────────────────────────────── */

function overrideParams() {
  const p = new URLSearchParams();
  for (const c of MANIFEST.controls) {
    const el = $("ctl-" + c.key);
    if (!el) continue;
    if (String(el.value) !== String(c.default)) p.set(c.key, el.value);
  }
  return p;
}

function figureURL(extra = {}) {
  if (VIEW.kind === "activity" || VIEW.kind === "spikecheck") {
    const p = new URLSearchParams({rec: VIEW.rec, name: VIEW.name});
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    const route = VIEW.kind === "activity" ? "/api/activity" : "/api/spikecheck";
    return route + "?" + p.toString();
  }
  if (VIEW.kind === "trace") {
    // Carried in the bundle, not rendered: no fmt, no styling overrides. But
    // `download` is neither of those — it decides whether the browser saves
    // the file or just displays it — so it has to be passed through, or
    // "Download PNG" silently becomes "view PNG".
    const p = new URLSearchParams({rec: VIEW.rec, name: VIEW.name});
    if (extra.download) p.set("download", extra.download);
    return "/api/trace?" + p.toString();
  }
  if (VIEW.kind === "edgecheck") {
    const p = new URLSearchParams({rec: VIEW.rec, lag: VIEW.name});
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return "/api/edgecheck?" + p.toString();
  }
  if (VIEW.kind === "subnetwork") {
    const p = new URLSearchParams({rec: VIEW.rec, lag: $("lag").value,
                                   name: VIEW.name});
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return "/api/subnetwork?" + p.toString();
  }
  if (VIEW.kind === "lagseries") {
    const p = colorParams();
    p.set("series", VIEW.series); p.set("key", VIEW.key);
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return "/api/lagseries?" + p.toString();
  }
  if (VIEW.kind === "stats") {
    // Group and age colours only: these are violins, heatmaps and scatters,
    // and none of them reads a network-plot styling control.
    const p = colorParams();
    p.set("lag", VIEW.statsLag); p.set("key", VIEW.statsKey);
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return "/api/stats?" + p.toString();
  }
  if (VIEW.kind === "comparison" || VIEW.kind === "both") {
    return comparisonURL(extra.split || $("cmp-split").value, extra);
  }
  const p = overrideParams();
  p.set("rec", VIEW.rec); p.set("lag", VIEW.lag); p.set("name", VIEW.name);
  if (VARIANT !== "plain") p.set("variant", VARIANT);
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  return "/api/figure?" + p.toString();
}

function buildControls() {
  const box = $("controls");
  box.innerHTML = "";
  for (const c of MANIFEST.controls) {
    const label = document.createElement("label");
    const name = document.createElement("span");
    name.className = "l"; name.textContent = c.label;
    label.appendChild(name);

    let el;
    if (c.kind === "select") {
      el = document.createElement("select");
      for (const opt of c.options) {
        const o = document.createElement("option");
        o.value = opt; o.textContent = opt; el.appendChild(o);
      }
    } else {
      el = document.createElement("input");
      el.type = "number";
      if (c.min !== null) el.min = c.min;
      if (c.max !== null) el.max = c.max;
      if (c.step !== null) el.step = c.step;
    }
    el.id = "ctl-" + c.key;
    el.value = c.default;
    el.addEventListener("change", () => {
      syncNodeSizeMode();
      if (VIEW.kind === "figure") showFigure();
    });
    label.appendChild(el);
    if (c.help) { const s = document.createElement("small"); s.textContent = c.help;
                  label.appendChild(s); }
    box.appendChild(label);
  }
  syncNodeSizeMode();
}

// "Auto" sizes nodes from their packing, so the scale beside it is not read.
// Greyed rather than hidden: the value is still the one Manual would resume
// from, and a control that vanishes reads as a control that was lost.
function syncNodeSizeMode() {
  const mode = $("ctl-node_size_mode"), scale = $("ctl-node_size_scale");
  if (!mode || !scale) return;
  scale.disabled = mode.value === "Auto";
  scale.parentElement.classList.toggle("muted", scale.disabled);
}

function buildComparisonControls() {
  const box = $("cmp-controls");
  box.innerHTML = "";
  for (const c of (MANIFEST.comparison_controls || [])) {
    const label = document.createElement("label");
    const name = document.createElement("span");
    name.className = "l"; name.textContent = c.label;
    label.appendChild(name);

    let el;
    if (c.kind === "select") {
      el = document.createElement("select");
      for (const opt of c.options) {
        const o = document.createElement("option");
        o.value = opt; o.textContent = opt; el.appendChild(o);
      }
      el.value = c.default;
    } else {
      // A free-text list of colours. Applied on change rather than per
      // keystroke, so a half-typed hex code doesn't render as an error.
      el = document.createElement("input");
      el.type = "text";
      el.placeholder = "#1f77b4, crimson, …";
      el.value = "";
    }
    el.id = "cmp-ctl-" + c.key;
    el.addEventListener("change", showComparisonOrLagSeries);
    label.appendChild(el);
    if (c.help) { const s = document.createElement("small"); s.textContent = c.help;
                  label.appendChild(s); }
    box.appendChild(label);
  }
}

function colorParams() {
  const p = new URLSearchParams();
  for (const c of (MANIFEST.comparison_controls || [])) {
    const el = $("cmp-ctl-" + c.key);
    if (!el) continue;
    const value = String(el.value).trim();
    if (!value || value === String(c.default)) continue;
    p.set(c.key, value);
  }
  return p;
}

function resetComparisonControls() {
  for (const c of (MANIFEST.comparison_controls || [])) {
    const el = $("cmp-ctl-" + c.key);
    if (el) el.value = c.kind === "select" ? c.default : "";
  }
  showComparisonOrLagSeries();
}

// The colours apply to both the faceted comparisons and the across-lag
// figures, and the panel is reachable from either, so one handler re-renders
// whichever is on screen.
function showComparisonOrLagSeries() {
  if (VIEW.kind === "lagseries") showLagSeries();
  else showComparison();
}

// Back to what the run itself used — MANIFEST.controls carries the run's
// styling as each control's default, not this viewer's idea of one.
function resetControls() {
  for (const c of MANIFEST.controls) {
    const el = $("ctl-" + c.key);
    if (el) el.value = c.default;
  }
  syncNodeSizeMode();
  if (VIEW.kind === "figure") showFigure();
}

function currentRecording() {
  return MANIFEST.recordings.find((r) => r.name === $("recording").value);
}

function fillRecordings() {
  const sel = $("recording");
  sel.innerHTML = "";
  for (const r of MANIFEST.recordings) {
    const o = document.createElement("option");
    o.value = r.name;
    o.textContent = r.group ? `${r.name}  (${r.group})` : r.name;
    sel.appendChild(o);
  }
  fillLags();
}

function showSamplingRate() {
  const el = $("rec-fs");
  const rec = currentRecording();
  // Absent for ephys runs (where the rate is a setting, shown with the rest)
  // and for bundles written before the rate was recorded.
  if (!rec || rec.fs == null) { el.textContent = ""; el.className = ""; return; }

  const all = MANIFEST.recordings.map((r) => r.fs).filter((v) => v != null);
  const distinct = [...new Set(all)].sort((a, b) => a - b);
  if (distinct.length > 1) {
    el.className = "mixed";
    el.innerHTML =
      "Acquired at <b>" + rec.fs + " Hz</b>. This run mixes " +
      distinct.length + " rates (" + distinct.join(", ") + " Hz) \u2014 each " +
      "recording was analysed at its own, but rate usually tracks the culture " +
      "prep, so check it is not confounded with the groups compared.";
  } else {
    el.className = "";
    el.innerHTML = "Acquired at <b>" + rec.fs + " Hz</b>.";
  }
}

function fillLags() {
  showSamplingRate();
  fillActivity();
  fillSpikeChecks();
  fillTraces();
  fillEdgeChecks();
  const rec = currentRecording();
  const sel = $("lag");
  sel.innerHTML = "";
  for (const lag of (rec ? rec.lags : [])) {
    const o = document.createElement("option");
    o.value = lag; o.textContent = lag + " ms";
    sel.appendChild(o);
  }
  // After the select is repopulated: both of these read $("lag").value, which
  // until now still held the previous recording's lag.
  fillFigures();
  fillSubnetworks();
}

function fillActivity() {
  const rec = currentRecording();
  const box = $("activity");
  box.innerHTML = "";
  const figs = (rec && rec.activity) || [];
  if (!figs.length) {
    box.innerHTML = '<div class="sub">None in this bundle.</div>';
    return;
  }
  for (const f of figs) {
    const b = document.createElement("button");
    b.textContent = f.label;
    b.dataset.activity = f.name;
    b.addEventListener("click", () => {
      VIEW.kind = "activity"; VIEW.rec = rec.name; VIEW.name = f.name;
      showFigure();
    });
    box.appendChild(b);
  }
}

function fillSpikeChecks() {
  const rec = currentRecording();
  const box = $("spikechecks");
  box.innerHTML = "";
  const figs = (rec && rec.spike_checks) || [];
  if (!figs.length) {
    // Either step 1 did not run, or the run predates the stored payload.
    box.innerHTML = '<div class="sub">None in this bundle.</div>';
    return;
  }
  for (const f of figs) {
    const b = document.createElement("button");
    b.textContent = f.label;
    b.dataset.spikecheck = f.name;
    b.addEventListener("click", () => {
      VIEW.kind = "spikecheck"; VIEW.rec = rec.name; VIEW.name = f.name;
      showFigure();
    });
    box.appendChild(b);
  }
}

function fillTraces() {
  const rec = currentRecording();
  const box = $("traces");
  box.innerHTML = "";
  const figs = (rec && rec.traces) || [];
  if (!figs.length) {
    // Either this is an ephys run, or num_2p_traces was 0 — in which case the
    // figures were never drawn and cannot be recovered from the bundle.
    box.innerHTML = '<div class="sub">None in this bundle.</div>';
    return;
  }
  for (const f of figs) {
    const b = document.createElement("button");
    b.textContent = f.label;
    b.dataset.trace = f.name;
    b.addEventListener("click", () => {
      VIEW.kind = "trace"; VIEW.rec = rec.name; VIEW.name = f.name;
      showFigure();
    });
    box.appendChild(b);
  }
}

function fillEdgeChecks() {
  const rec = currentRecording();
  const box = $("edgechecks");
  box.innerHTML = "";
  const lags = (rec && rec.edge_checks) || [];
  if (!lags.length) {
    box.innerHTML = '<div class="sub">Not produced by this run.</div>';
    return;
  }
  for (const lag of lags) {
    const b = document.createElement("button");
    b.textContent = lag + " ms lag";
    b.dataset.edgecheck = String(lag);
    b.addEventListener("click", () => {
      VIEW.kind = "edgecheck"; VIEW.rec = rec.name; VIEW.name = String(lag);
      showFigure();
    });
    box.appendChild(b);
  }
}

function fillSubnetworks() {
  const rec = currentRecording();
  const lag = $("lag").value;
  const box = $("subnetworks");
  box.innerHTML = "";
  const figs = (rec && rec.subnetworks && rec.subnetworks[lag]) || [];
  if (!figs.length) {
    box.innerHTML = '<div class="sub">Not produced by this run.</div>';
    return;
  }
  for (const f of figs) {
    const b = document.createElement("button");
    b.textContent = f.label;
    b.dataset.subnetwork = f.name;
    b.addEventListener("click", () => {
      VIEW.kind = "subnetwork"; VIEW.rec = rec.name; VIEW.name = f.name;
      showFigure();
    });
    box.appendChild(b);
  }
}

function currentFigureSpec() {
  const rec = currentRecording();
  const figs = (rec && rec.figures[$("lag").value]) || [];
  return figs.find((f) => f.name === VIEW.name) || null;
}

function fillVariants() {
  const box = $("variants");
  const spec = VIEW.kind === "figure" ? currentFigureSpec() : null;
  const variants = (spec && spec.variants) || ["plain"];
  // Hidden when there is nothing to choose: a one-option toggle is furniture
  // that implies the other options exist somewhere.
  $("variant-panel").classList.toggle("hidden", variants.length < 2);
  box.innerHTML = "";
  for (const v of variants) {
    const b = document.createElement("button");
    b.textContent = VARIANT_LABELS[v] || v;
    b.dataset.variant = v;
    b.setAttribute("aria-current", String(v === VARIANT));
    b.addEventListener("click", () => {
      VARIANT = v;
      fillVariants();
      showFigure();
    });
    box.appendChild(b);
  }
}

function fillFigures() {
  const rec = currentRecording();
  const lag = $("lag").value;
  const box = $("figures");
  box.innerHTML = "";
  const figs = (rec && rec.figures[lag]) || [];
  if (!figs.length) {
    box.innerHTML = '<div class="sub">No figures for this lag.</div>';
    return;
  }
  for (const f of figs) {
    const b = document.createElement("button");
    b.textContent = f.label;
    b.dataset.name = f.name;
    b.addEventListener("click", () => {
      VIEW.kind = "figure"; VIEW.rec = rec.name; VIEW.lag = lag; VIEW.name = f.name;
      // A new figure may not have the scaling the last one was showing.
      VARIANT = "plain";
      fillVariants();
      showFigure();
    });
    box.appendChild(b);
  }
  // Open the first figure so the tab is never blank.
  if (!VIEW.name || VIEW.kind !== "figure" ||
      !figs.some((f) => f.name === VIEW.name)) {
    VIEW.kind = "figure"; VIEW.rec = rec.name; VIEW.lag = lag;
    VIEW.name = figs[0].name;
  } else {
    VIEW.rec = rec.name; VIEW.lag = lag;
  }
  // The chosen figure may have changed, or its variants may differ at this lag.
  if (!((currentFigureSpec() || {}).variants || []).includes(VARIANT)) {
    VARIANT = "plain";
  }
  fillVariants();
  if (TAB === "recordings") showFigure();
}

/* ── Comparisons tab ────────────────────────────────────────────────────── */

function currentComparison() {
  return (MANIFEST.comparisons || []).find((c) => c.key === $("cmp-family").value);
}

function currentLevel() {
  const fam = currentComparison();
  if (!fam) return null;
  return fam.levels.find((l) => l.key === $("cmp-level").value) || fam.levels[0];
}

function fillComparisonFamilies() {
  const sel = $("cmp-family");
  sel.innerHTML = "";
  for (const fam of (MANIFEST.comparisons || [])) {
    const o = document.createElement("option");
    o.value = fam.key; o.textContent = fam.label;
    sel.appendChild(o);
  }
  fillComparisonFacets();
}

function fillComparisonFacets() {
  const fam = currentComparison();
  if (!fam) {
    $("cmp-metrics").innerHTML = '<div class="sub">Nothing to compare in this bundle.</div>';
    return;
  }
  // A lagless family (step-2 activity) hides the control rather than showing
  // one with nothing in it.
  const lagSel = $("cmp-lag");
  const keepLag = lagSel.value;
  lagSel.innerHTML = "";
  for (const lag of fam.lags) {
    const o = document.createElement("option");
    o.value = lag; o.textContent = lag + " ms";
    lagSel.appendChild(o);
  }
  if (fam.lags.map(String).includes(keepLag)) lagSel.value = keepLag;
  $("cmp-lag-label").classList.toggle("hidden", !fam.lags.length);

  const levelSel = $("cmp-level");
  const keepLevel = levelSel.value;
  levelSel.innerHTML = "";
  for (const level of fam.levels) {
    const o = document.createElement("option");
    o.value = level.key; o.textContent = level.label;
    levelSel.appendChild(o);
  }
  if (fam.levels.some((l) => l.key === keepLevel)) levelSel.value = keepLevel;

  const splitSel = $("cmp-split");
  const keepSplit = splitSel.value;
  splitSel.innerHTML = "";
  for (const split of fam.splits) {
    const o = document.createElement("option");
    o.value = split.key; o.textContent = split.label;
    splitSel.appendChild(o);
  }
  const both = document.createElement("option");
  both.value = "both"; both.textContent = "Both";
  splitSel.appendChild(both);
  if (keepSplit) splitSel.value = keepSplit;

  fillComparisonMetrics();
}

function fillComparisonMetrics() {
  const level = currentLevel();
  const box = $("cmp-metrics");
  box.innerHTML = "";
  if (!level) return;
  for (const m of level.metrics) {
    const b = document.createElement("button");
    b.textContent = m.label;
    b.title = m.name;
    b.dataset.metric = m.name;
    b.addEventListener("click", () => { VIEW.metric = m.name; showComparison(); });
    box.appendChild(b);
  }
  // Keep the chosen metric across a level change when it exists at both
  // levels; otherwise fall back to the first, so the pane is never blank.
  if (!level.metrics.some((m) => m.name === VIEW.metric)) {
    VIEW.metric = level.metrics.length ? level.metrics[0].name : null;
  }
  if (TAB === "comparisons") showComparison();
}

function comparisonURL(split, extra = {}) {
  const fam = currentComparison();
  const p = colorParams();
  p.set("family", fam.key); p.set("level", $("cmp-level").value);
  p.set("split", split); p.set("metric", VIEW.metric);
  if (fam.lags.length) p.set("lag", $("cmp-lag").value);
  for (const [k, v] of Object.entries(extra)) if (k !== "split") p.set(k, v);
  return "/api/comparison?" + p.toString();
}

function showComparison() {
  const fam = currentComparison();
  if (!fam || !VIEW.metric) return;
  const split = $("cmp-split").value;
  VIEW.kind = split === "both" ? "both" : "comparison";
  VIEW.family = fam.key;
  setMode(VIEW.kind); markCurrent();
  $("error").textContent = "";

  const splits = split === "both" ? fam.splits.map((s) => s.key) : [split];
  const labels = Object.fromEntries(fam.splits.map((s) => [s.key, s.label]));
  const box = $("pair");
  box.innerHTML = "";
  $("status").textContent = "rendering…";
  let pending = splits.length;

  for (const s of splits) {
    const fig = document.createElement("figure");
    const img = document.createElement("img");
    img.alt = `${VIEW.metric} — ${labels[s]}`;
    img.src = comparisonURL(s);
    img.onload = () => {
      if (--pending === 0) {
        $("status").textContent = split === "both"
          ? `${VIEW.metric} — both splits (pick one to download)`
          : `${VIEW.metric} — ${labels[s]}`;
      }
    };
    img.onerror = () => {
      $("status").textContent = "";
      $("error").textContent = "Could not render this comparison.";
    };
    const cap = document.createElement("figcaption");
    cap.textContent = labels[s];
    fig.appendChild(img); fig.appendChild(cap);
    box.appendChild(fig);
  }
}

/* ── Across-lags tab ────────────────────────────────────────────────────── */

function currentSeries() {
  return (MANIFEST.lag_series || []).find((s) => s.key === VIEW.series);
}

function fillLagSeries() {
  const box = $("lag-series");
  box.innerHTML = "";
  const sets = MANIFEST.lag_series || [];
  if (!sets.length) {
    box.innerHTML = '<div class="sub">This run has one lag, so there is ' +
                    'nothing to plot against lag.</div>';
    $("lag-options").innerHTML = "";
    return;
  }
  for (const s of sets) {
    const b = document.createElement("button");
    b.textContent = s.label;
    b.dataset.series = s.key;
    b.addEventListener("click", () => { VIEW.series = s.key; VIEW.key = null;
                                        fillLagOptions(); });
    box.appendChild(b);
  }
  if (!sets.some((s) => s.key === VIEW.series)) VIEW.series = sets[0].key;
  fillLagOptions();
}

function fillLagOptions() {
  const series = currentSeries();
  const box = $("lag-options");
  box.innerHTML = "";
  if (!series) return;
  $("lag-options-head").textContent =
    series.keyed_by === "lag" ? timescaleLabel() : "Metric";
  for (const opt of series.options) {
    const b = document.createElement("button");
    b.textContent = opt.label;
    b.dataset.key = opt.key;
    b.addEventListener("click", () => { VIEW.key = opt.key; showLagSeries(); });
    box.appendChild(b);
  }
  if (!series.options.some((o) => o.key === VIEW.key)) {
    VIEW.key = series.options.length ? series.options[0].key : null;
  }
  if (TAB === "lags") showLagSeries();
}

function showLagSeries() {
  if (!VIEW.series || !VIEW.key) return;
  VIEW.kind = "lagseries";
  setMode("lagseries"); markCurrent();
  $("error").textContent = "";
  $("status").textContent = "rendering…";
  const series = currentSeries();
  const chosen = series.options.find((o) => o.key === VIEW.key);
  const img = $("figure-img");
  img.onload = () => {
    $("status").textContent = `${series.label} — ${chosen ? chosen.label : VIEW.key}`;
  };
  img.onerror = () => {
    $("status").textContent = "";
    $("error").textContent = "Could not render this figure.";
  };
  img.src = figureURL();
  img.alt = VIEW.key;
}

/* ── Statistics tab ─────────────────────────────────────────────────────── */

function currentStatsLag() {
  const sets = MANIFEST.stats || [];
  return sets.find((s) => s.lag === VIEW.statsLag) || sets[0];
}

function fillStatsLags() {
  const sets = MANIFEST.stats || [];
  const sel = $("stats-lag");
  sel.innerHTML = "";
  for (const s of sets) {
    const o = document.createElement("option");
    o.value = s.lag; o.textContent = s.lag;
    sel.appendChild(o);
  }
  // A run analysed at one timescale has nothing to choose between, so the
  // selector goes away rather than sitting there with a single entry.
  const one = sets.length <= 1;
  sel.classList.toggle("hidden", one);
  $("stats-lag-head").classList.toggle("hidden", one);
  if (!sets.some((s) => s.lag === VIEW.statsLag))
    VIEW.statsLag = sets.length ? sets[0].lag : null;
  sel.value = VIEW.statsLag || "";
  fillStatsFigures();
}

function fillStatsFigures() {
  const box = $("stats-figures");
  box.innerHTML = "";
  const set = currentStatsLag();
  if (!set) {
    box.innerHTML = '<div class="sub">This run has not been through the ' +
      'statistics step. Run it from the Stats &amp; ML tab, or with ' +
      '<code>meanap-stats</code>, and the figures appear here.</div>';
    return;
  }
  let first = null;
  for (const group of set.groups) {
    const h = document.createElement("h2");
    h.textContent = group.label;
    box.appendChild(h);
    for (const fig of group.figures) {
      const b = document.createElement("button");
      b.textContent = fig.label;
      b.dataset.stats = fig.key;
      b.title = fig.caption;
      b.addEventListener("click", () => {
        VIEW.statsKey = fig.key; VIEW.statsCaption = fig.caption;
        VIEW.statsLabel = fig.label; showStats();
      });
      box.appendChild(b);
      if (first === null) first = fig;
    }
  }
  const known = set.groups.some((g) => g.figures.some((f) => f.key === VIEW.statsKey));
  if (!known && first) {
    VIEW.statsKey = first.key;
    VIEW.statsCaption = first.caption;
    VIEW.statsLabel = first.label;
  }
}

function showStats() {
  if (!VIEW.statsKey) return;
  VIEW.kind = "stats";
  setMode("stats"); markCurrent();
  $("error").textContent = "";
  $("status").textContent = "rendering…";
  const caption = $("figure-caption");
  const img = $("figure-img");
  img.onload = () => {
    $("status").textContent = VIEW.statsLabel || VIEW.statsKey;
    caption.textContent = VIEW.statsCaption || "";
    caption.classList.toggle("hidden", !VIEW.statsCaption);
  };
  img.onerror = () => {
    $("status").textContent = "";
    caption.classList.add("hidden");
    $("error").textContent = "Could not render this figure.";
  };
  img.src = figureURL();
  img.alt = VIEW.statsLabel || VIEW.statsKey;
}

/* ── Galleries (families with no per-figure address) ────────────────────── */

function fillFamilies() {
  const box = $("families");
  box.innerHTML = "";
  // Anything already selectable in the Comparisons facets is not also offered
  // as a gallery — one route to a figure, not two that disagree.
  const faceted = new Set((MANIFEST.comparisons || []).map((c) => c.key));
  const galleries = (MANIFEST.families || []).filter((f) => !faceted.has(f.key));
  if (!galleries.length) {
    box.innerHTML = '<div class="sub">None in this bundle.</div>';
    return;
  }
  for (const fam of galleries) {
    const b = document.createElement("button");
    b.textContent = fam.label;
    b.dataset.family = fam.key;
    b.addEventListener("click", () => showFamily(fam));
    box.appendChild(b);
  }
}

async function showFamily(fam) {
  VIEW.kind = "family"; VIEW.gallery = fam.key;
  setMode("family"); markCurrent();
  $("error").textContent = "";
  $("status").textContent = "rendering gallery — this can take a few seconds the first time…";
  const box = $("gallery");
  box.innerHTML = "";
  try {
    const data = await getJSON("/api/family?key=" + encodeURIComponent(fam.key));
    $("status").textContent =
      `${fam.label} — ${data.count} figures${data.cached ? " (cached)" : ""}`;
    let lastGroup = null;
    for (const item of data.items) {
      if (item.group !== lastGroup) {
        const h = document.createElement("div");
        h.className = "group-head"; h.textContent = item.group;
        box.appendChild(h); lastGroup = item.group;
      }
      const fig = document.createElement("figure");
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = "/api/asset?path=" + encodeURIComponent(item.asset);
      img.alt = item.name;
      const cap = document.createElement("figcaption");
      cap.textContent = item.name;
      fig.appendChild(img); fig.appendChild(cap);
      box.appendChild(fig);
    }
  } catch (e) {
    $("status").textContent = "";
    $("error").textContent = String(e.message || e);
  }
}

/* ── Shared chrome ──────────────────────────────────────────────────────── */

async function onExport() {
  const btn = $("export");
  const label = btn.textContent;
  // Hundreds of figures at ~0.1 s each, so this is tens of seconds. Disable
  // rather than let a second click start a second export beside the first.
  btn.disabled = true;
  btn.textContent = "Exporting…";
  try {
    const r = await getJSON("/api/export");
    const where = r.dest.split("/").slice(-1)[0];
    btn.textContent = `Exported ${r.figures} figures → ${where}`;
    $("error").textContent = r.skipped.length
      ? `${r.skipped.length} figure(s) could not be drawn; the rest are there.`
      : "";
    // The path in full, where it can be copied out of.
    $("status").textContent = r.dest;
  } catch (e) {
    btn.textContent = label;
    $("error").textContent = "Export failed: " + e.message;
  } finally {
    btn.disabled = false;
  }
}

function markCurrent() {
  for (const b of document.querySelectorAll("#figures button"))
    b.setAttribute("aria-current", String(VIEW.kind === "figure" && b.dataset.name === VIEW.name));
  for (const b of document.querySelectorAll("#activity button"))
    b.setAttribute("aria-current", String(VIEW.kind === "activity" && b.dataset.activity === VIEW.name));
  for (const b of document.querySelectorAll("#spikechecks button"))
    b.setAttribute("aria-current", String(VIEW.kind === "spikecheck" && b.dataset.spikecheck === VIEW.name));
  for (const b of document.querySelectorAll("#traces button"))
    b.setAttribute("aria-current", String(VIEW.kind === "trace" && b.dataset.trace === VIEW.name));
  for (const b of document.querySelectorAll("#edgechecks button"))
    b.setAttribute("aria-current", String(VIEW.kind === "edgecheck" && b.dataset.edgecheck === VIEW.name));
  for (const b of document.querySelectorAll("#subnetworks button"))
    b.setAttribute("aria-current", String(VIEW.kind === "subnetwork" && b.dataset.subnetwork === VIEW.name));
  for (const b of document.querySelectorAll("#families button"))
    b.setAttribute("aria-current", String(VIEW.kind === "family" && b.dataset.family === VIEW.gallery));
  const cmp = VIEW.kind === "comparison" || VIEW.kind === "both";
  for (const b of document.querySelectorAll("#cmp-metrics button"))
    b.setAttribute("aria-current", String(cmp && b.dataset.metric === VIEW.metric));
  for (const b of document.querySelectorAll("#lag-series button"))
    b.setAttribute("aria-current", String(VIEW.kind === "lagseries" && b.dataset.series === VIEW.series));
  for (const b of document.querySelectorAll("#lag-options button"))
    b.setAttribute("aria-current", String(VIEW.kind === "lagseries" && b.dataset.key === VIEW.key));
  for (const b of document.querySelectorAll("#stats-figures button"))
    b.setAttribute("aria-current", String(VIEW.kind === "stats" && b.dataset.stats === VIEW.statsKey));
}

function setMode(kind) {
  // Every kind that shows one image in #single. "trace" belongs here: it is a
  // stored PNG rather than a render, but it still goes in the same <figure>,
  // and leaving it out hid the pane the image had just been loaded into — the
  // button highlighted, the PNG arrived, and the reader saw nothing.
  const one = kind === "figure" || kind === "activity" || kind === "lagseries"
              || kind === "spikecheck" || kind === "edgecheck"
              || kind === "subnetwork" || kind === "trace" || kind === "stats";
  // Hidden, not disabled: the styling controls describe spatial network plots.
  // A raster, a violin and a line plot read none of them, so offering the
  // knobs there would imply they do something.
  $("controls-panel").classList.toggle("hidden", kind !== "figure");
  const faceted = kind === "comparison" || kind === "both";
  // The statistics figures read the group and age colours, so the facets
  // panel — which is where those live — stays available for them too.
  $("facets-panel").classList.toggle(
    "hidden", !(faceted || kind === "lagseries" || kind === "stats"));
  // The across-lag figures read the colours but have no lag/level/split of
  // their own, so those rows go away rather than sitting there inert.
  for (const id of ["facets-head", "cmp-level-label", "cmp-split-label"])
    $(id).classList.toggle("hidden", !faceted);
  // Lag stays hidden for a lagless family even while faceted, so this cannot
  // just follow `faceted` — fillComparisonFacets owns that decision.
  const fam = faceted ? currentComparison() : null;
  $("cmp-lag-label").classList.toggle("hidden", !(fam && fam.lags.length));
  $("single").classList.toggle("hidden", !one);
  $("pair").classList.toggle("hidden", !(kind === "comparison" || kind === "both"));
  $("gallery").classList.toggle("hidden", kind !== "family");
  // Every kind setMode is called for is a figure, so the parameters pane is
  // never the right thing to be showing.
  $("params").classList.add("hidden");
  // "Both" shows two figures; a single download button cannot mean both, so
  // the buttons go away rather than silently picking one.
  const downloadable = one || kind === "comparison";
  for (const id of ["dl-png", "dl-svg", "dl-pdf"])
    $(id).classList.toggle("hidden", !downloadable);
  // Only the statistics figures carry a written caption; anything else would
  // leave the previous figure's sentence under the new one.
  if (kind !== "stats") $("figure-caption").classList.add("hidden");
  // A trace figure is a stored PNG. Offering SVG/PDF would promise a
  // re-render that cannot happen — the fluorescence it needs isn't here.
  if (kind === "trace")
    for (const id of ["dl-svg", "dl-pdf"]) $(id).classList.add("hidden");
}

function showFigure() {
  if (!["activity", "spikecheck", "edgecheck", "subnetwork", "trace"].includes(VIEW.kind))
    VIEW.kind = "figure";
  setMode(VIEW.kind); markCurrent();
  $("error").textContent = "";
  $("status").textContent = "rendering…";
  const img = $("figure-img");
  img.onload = () => { $("status").textContent = VIEW.name; };
  img.onerror = () => {
    $("status").textContent = "";
    $("error").textContent = "Could not render this figure.";
  };
  img.src = figureURL();
  img.alt = VIEW.name;
}

/* ── Parameters ──────────────────────────────────────────────────────────
   The settings the run used. Defaults are folded away by default: the question
   is "what was different about this run", and on a typical run that is a dozen
   fields out of 137. The left column filters to one section. */
let PARAM_SECTION = null;      // null = every section
let PARAM_ALL = false;         // false = only what differs from the default

function fmtParam(v) {
  if (v === null || v === undefined) return "\u2014";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "[]";
  if (typeof v === "boolean") return v ? "on" : "off";
  if (typeof v === "object") return JSON.stringify(v);
  if (v === "") return "\u2014";
  return String(v);
}

function fillParamGroups() {
  const box = $("param-groups");
  box.innerHTML = "";
  const mk = (label, section, count) => {
    const b = document.createElement("button");
    b.textContent = count === null ? label : `${label}  (${count})`;
    b.dataset.section = section === null ? "" : section;
    b.addEventListener("click", () => {
      PARAM_SECTION = section;
      showParams();
    });
    box.appendChild(b);
  };
  mk("All sections", null, null);
  for (const g of MANIFEST.params.groups) {
    // The count follows the filter, so it says how many rows the click gives.
    mk(g.name, g.name, PARAM_ALL ? g.entries.length : g.changed);
  }
}

function showParams() {
  const P = MANIFEST.params;
  for (const el of ["single", "pair", "gallery"])
    $(el).classList.add("hidden");
  $("params").classList.remove("hidden");
  $("controls-panel").classList.add("hidden");
  $("facets-panel").classList.add("hidden");
  for (const id of ["dl-png", "dl-svg", "dl-pdf"])
    $(id).classList.add("hidden");
  $("error").textContent = "";
  $("status").textContent = `${P.changed} of ${P.total} settings changed`;

  for (const b of document.querySelectorAll("#param-groups button"))
    b.setAttribute("aria-current",
      String((b.dataset.section || null) === PARAM_SECTION));

  const box = $("params");
  box.innerHTML = "";

  const lead = document.createElement("p");
  lead.className = "lead";
  lead.textContent = "The values this run actually used — the same numbers as "
    + "params.json, grouped for reading. Bold rows differ from the default.";
  box.appendChild(lead);

  const toggle = document.createElement("button");
  toggle.textContent = PARAM_ALL
    ? "Show only what changed" : `Show all ${P.total} settings`;
  toggle.addEventListener("click", () => {
    PARAM_ALL = !PARAM_ALL;
    fillParamGroups();
    showParams();
  });
  box.appendChild(toggle);

  let shown = 0;
  for (const g of P.groups) {
    if (PARAM_SECTION !== null && g.name !== PARAM_SECTION) continue;
    const rows = PARAM_ALL ? g.entries : g.entries.filter(e => e.changed);
    if (!rows.length) continue;
    shown += rows.length;

    const h = document.createElement("h3");
    h.textContent = g.name;
    box.appendChild(h);

    const table = document.createElement("table");
    for (const e of rows) {
      const tr = document.createElement("tr");
      if (e.changed) tr.className = "changed";
      const k = document.createElement("td");
      k.className = "k"; k.textContent = e.name;
      const v = document.createElement("td");
      v.className = "v" + (e.redacted ? " redacted" : "");
      v.textContent = fmtParam(e.value);
      const d = document.createElement("td");
      d.className = "d";
      d.textContent = e.changed ? "default " + fmtParam(e.default) : "";
      tr.appendChild(k); tr.appendChild(v); tr.appendChild(d);
      table.appendChild(tr);
    }
    box.appendChild(table);
  }

  if (!shown) {
    const p = document.createElement("p");
    p.className = "sub";
    p.textContent = PARAM_ALL
      ? "Nothing in this section."
      : "Every setting here was left at its default.";
    box.appendChild(p);
  }

  if (P.unknown && Object.keys(P.unknown).length) {
    const h = document.createElement("h3");
    h.textContent = "Not recognised by this version";
    box.appendChild(h);
    const p = document.createElement("p");
    p.className = "sub";
    p.textContent = "This bundle records settings this build has no field for, "
      + "so it was probably written by a newer version: "
      + Object.keys(P.unknown).join(", ");
    box.appendChild(p);
  }
}

function selectTab(tab) {
  TAB = tab;
  for (const b of document.querySelectorAll("#tabs button"))
    b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  $("side-recordings").classList.toggle("hidden", tab !== "recordings");
  $("side-comparisons").classList.toggle("hidden", tab !== "comparisons");
  $("side-lags").classList.toggle("hidden", tab !== "lags");
  $("side-stats").classList.toggle("hidden", tab !== "stats");
  $("side-params").classList.toggle("hidden", tab !== "params");
  $("side-tracking").classList.toggle("hidden", tab !== "tracking");
  $("tracking").classList.toggle("hidden", tab !== "tracking");
  // The figure panes are hidden by setMode, which only runs for the figure
  // tabs. Without this the last figure — and its styling controls — stay on
  // screen underneath the tracking content, which reads as the tracking view
  // showing someone else's plot.
  // the right column holds only figure controls
  document.body.classList.toggle("no-right", tab === "tracking");
  if (tab === "tracking") {
    // the whole toolbar, not just the buttons: #status carries the current
    // figure's name, which otherwise sits above the tracking view labelling it
    // as something like "1_adjM1000msConnectivityStats"
    for (const id of ["single", "pair", "gallery", "params", "figure-caption",
                      "controls-panel", "facets-panel", "toolbar", "error",
                      "dl-png", "dl-svg", "dl-pdf", "export"])
      if ($(id)) $(id).classList.add("hidden");
  }
  else {
    // leaving tracking: the figure tabs own these again
    for (const id of ["toolbar", "error"])
      if ($(id)) $(id).classList.remove("hidden");
  }
  if (tab === "recordings") showFigure();
  else if (tab === "comparisons") showComparison();
  else if (tab === "stats") showStats();
  else if (tab === "params") showParams();
  else if (tab === "tracking") showTracking();
  else showLagSeries();
}

const THEMES = ["system", "light", "dark"];
const THEME_LABEL = {system: "◐ system", light: "☀ light", dark: "☾ dark"};

function currentTheme() {
  try { return localStorage.getItem("meanap-theme") || "system"; }
  catch (e) { return "system"; }   // private mode, or storage blocked
}

function applyTheme(name) {
  const root = document.documentElement;
  if (name === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", name);
  try { localStorage.setItem("meanap-theme", name); } catch (e) {}
  const btn = $("theme");
  if (btn) btn.textContent = THEME_LABEL[name];
  // Plot colours were resolved to literal values when the SVG was built, so
  // anything already drawn has to be drawn again to pick the new ones up.
  if (TAB === "tracking") showTracking();
}

function cycleTheme() {
  const next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
  applyTheme(next);
}

/** What the iframe should use: the explicit choice, or whatever the OS says. */
function effectiveTheme() {
  const t = currentTheme();
  if (t !== "system") return t;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark" : "light";
}

let TRACKING = null, TRACK_OVERVIEW = null;

const SVGNS = "http://www.w3.org/2000/svg";

/** One tooltip for the whole page, positioned by the cursor.
 *
 *  SVG's native <title> works but takes a second to appear and cannot be
 *  styled or hold more than a line or two — which is not enough to say what a
 *  point is *and* what its axis means.
 */
function tipHost() {
  let el = document.getElementById("tip");
  if (!el) {
    el = document.createElement("div");
    el.id = "tip";
    el.setAttribute("role", "tooltip");
    document.body.appendChild(el);
  }
  return el;
}

function attachTip(el, html) {
  if (!html) return el;
  const show = ev => {
    const t = tipHost();
    t.innerHTML = html;
    t.style.display = "block";
    const pad = 14, w = t.offsetWidth, h = t.offsetHeight;
    // flip towards the middle near an edge, so the tip never leaves the window
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + w > window.innerWidth - 8) x = ev.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = ev.clientY - h - pad;
    t.style.left = Math.max(4, x) + "px";
    t.style.top = Math.max(4, y) + "px";
  };
  el.addEventListener("mousemove", show);
  el.addEventListener("mouseenter", show);
  el.addEventListener("mouseleave", () => { tipHost().style.display = "none"; });
  return el;
}

/** What each axis actually means — the definitions are not guessable. */
const AXIS_HELP = {
  separability:
    "<b>Separability</b><br>Fingerprint AUC against the <i>spatial null</i>: the "
    + "probability that a matched cell's functional fingerprint agrees across days "
    + "better than a different cell in essentially the same place does.<br><br>"
    + "The null swaps each matched cell for its <b>nearest spatial neighbour</b>, so "
    + "position is held roughly fixed and only identity varies. A random null would "
    + "score far higher and mean less — it destroys position as well as identity.<br><br>"
    + "0.5 = no information. This dataset's median is ~0.66.",
  coverage:
    "<b>Coverage</b><br>Median across this chain's day-pairs of "
    + "<code>shared clusters ÷ cells in the smaller session</code>.<br><br>"
    + "How <i>many</i> cells were matched — which is a different question from "
    + "whether the matches are right, and the two disagree.",
  persistence:
    "<b>Persistence</b><br>Fraction of tracked cells present on <i>every</i> day of "
    + "the chain, rather than just some pair of days.",
  divGap:
    "<b>DIV gap</b><br>Days between the two recordings in a pair.",
  matchRate:
    "<b>Match rate</b><br><code>shared clusters ÷ cells in the smaller session</code> "
    + "for one day-pair. The smaller session is the denominator, so a pair matching a "
    + "large session against a small one is the most easily inflated.",
  offset:
    "<b>Field-of-view offset</b><br>Displacement between two days, estimated by "
    + "cross-correlating <b>ROI footprints</b> — never the mean image, which carries a "
    + "detector-fixed stripe artifact that makes unrelated recordings correlate at "
    + "0.87.<br><br>Chains below the gate are tracked unregistered: correcting an "
    + "offset smaller than the measurement resolution injects more error than it removes.",
};
function svgEl(t, a) { const e = document.createElementNS(SVGNS, t);
  for (const k in a) e.setAttribute(k, a[k]); return e; }

/** One scatter panel with axes. `pts` are {x, y, c, r, title}. */
function scatterPanel(title, sub, pts, opts) {
  const W = 470, H = 250, L = 52, R = 14, T = 12, B = 42;
  const fig = document.createElement("figure");
  fig.className = "trackfig";
  fig.innerHTML = `<figcaption><b>${title}</b><br><span class="sub">${sub}</span></figcaption>`;
  const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, class: "trackplot"});
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  let x0 = opts.x0 !== undefined ? opts.x0 : Math.min(...xs);
  let x1 = opts.x1 !== undefined ? opts.x1 : Math.max(...xs);
  let y0 = opts.y0 !== undefined ? opts.y0 : Math.min(...ys);
  let y1 = opts.y1 !== undefined ? opts.y1 : Math.max(...ys);
  if (x1 <= x0) x1 = x0 + 1;
  if (y1 <= y0) y1 = y0 + 1;
  const lg = opts.logX ? v => Math.log10(Math.max(v, opts.logFloor || 1)) : v => v;
  const lx0 = lg(x0), lx1 = lg(x1);
  const sx = v => L + (lg(v) - lx0) / ((lx1 - lx0) || 1) * (W - L - R);
  const sy = v => H - B - (v - y0) / ((y1 - y0) || 1) * (H - B - T);

  svg.append(svgEl("line", {x1: L, y1: H - B, x2: W - R, y2: H - B,
                            stroke: "var(--line)", "stroke-width": 1}));
  svg.append(svgEl("line", {x1: L, y1: T, x2: L, y2: H - B,
                            stroke: "var(--line)", "stroke-width": 1}));
  const tick = (x, y, t, anchor) => { const e = svgEl("text",
    {x, y, "font-size": 10, fill: "var(--muted)", "text-anchor": anchor || "middle"});
    e.textContent = t; svg.append(e); return e; };
  (opts.xTicks || [x0, x1]).forEach(v => tick(sx(v), H - B + 14, opts.fmtX ? opts.fmtX(v) : v));
  (opts.yTicks || [y0, y1]).forEach(v => tick(L - 7, sy(v) + 3, opts.fmtY ? opts.fmtY(v) : v, "end"));

  const xl = tick((L + W - R) / 2, H - 8, opts.xLabel);
  const yl = svgEl("text", {x: 12, y: (T + H - B) / 2, "font-size": 10,
    fill: "var(--muted)", "text-anchor": "middle",
    transform: `rotate(-90 12 ${(T + H - B) / 2})`});
  yl.textContent = opts.yLabel; svg.append(yl);
  // a dotted underline is the convention for "there is an explanation here"
  for (const [el, help] of [[xl, opts.xHelp], [yl, opts.yHelp]]) {
    if (!help) continue;
    el.setAttribute("class", "axhelp");
    attachTip(el, help);
  }

  (opts.rules || []).forEach(r => {
    const vertical = r.x !== undefined;
    svg.append(svgEl("line", vertical
      ? {x1: sx(r.x), y1: T, x2: sx(r.x), y2: H - B}
      : {x1: L, y1: sy(r.y), x2: W - R, y2: sy(r.y)},
      ));
    const ln = svg.lastChild;
    ln.setAttribute("stroke", "var(--muted)");
    ln.setAttribute("stroke-dasharray", "4 3");
    ln.setAttribute("stroke-width", 1);
    ln.setAttribute("opacity", .7);
    const lab = svgEl("text", {"font-size": 9, fill: "var(--muted)",
      x: vertical ? sx(r.x) + 4 : W - R, y: vertical ? T + 9 : sy(r.y) - 4,
      "text-anchor": vertical ? "start" : "end"});
    lab.textContent = r.label; svg.append(lab);
  });

  for (const p of pts) {
    const c = svgEl("circle", {cx: sx(p.x), cy: sy(p.y), r: p.r || 3.4,
      fill: p.c, "fill-opacity": .75, stroke: p.c, "stroke-opacity": .9,
      "stroke-width": .8});
    if (p.tip) {
      // no native <title> alongside it: the browser's own tooltip appears a
      // second later, in its own box, and lands on top of this one
      c.setAttribute("class", "hotdot");
      attachTip(c, p.tip);
    } else if (p.title) {
      const tt = svgEl("title");
      tt.textContent = p.title;
      c.append(tt);
    }
    svg.append(c);
  }
  fig.append(svg);
  return fig;
}


/** Everything known about a chain, for its hover. */
function chainTip(c, extra) {
  const f = (v, d) => v == null ? "n/a" : Number(v).toFixed(d);
  const lines = [
    `<b>${c.chain}</b>`,
    `${c.genotype || "?"} · prep ${c.prep || "?"}`,
    "<hr>",
    `separability <b>${f(c.separability, 3)}</b>`,
    `coverage <b>${f(c.coverage, 3)}</b>`,
    `persistence <b>${f(c.persistence, 3)}</b>`,
    `cells tracked <b>${c.nCells == null ? "n/a" : c.nCells}</b>` +
      (c.nCells == null ? "" : " <span class='dim'>(circle area)</span>"),
    `fingerprints <b>${c.nFingerprints == null ? "n/a" : c.nFingerprints}</b>`,
    `offset <b>${f(c.shiftPx, 1)} px</b> · ` +
      (c.registered ? "registered" : "<i>passed through the gate</i>"),
  ];
  if (extra) lines.push("<hr>", extra);
  return lines.join("<br>");
}

const GENO_VAR = {WT: "--plot-wt", Het: "--plot-het", KO: "--plot-ko"};
/** Resolve a theme variable to a real colour: SVG attributes need a value, and
 *  an unresolved var() silently falls back to black — which is invisible on a
 *  dark ground and is what made these plots unreadable. */
function themeColour(name) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || "#888";
}
const genoColour = g => themeColour(GENO_VAR[g] || "--plot-other");

function legendRow(items) {
  return '<div class="legend">' + items.map(([c, t]) =>
    `<span><i class="sw" style="background:${c}"></i>${t}</span>`).join("") + "</div>";
}

async function showTrackingOverview() {
  const host = $("tracking");
  host.innerHTML = '<p class="sub">Loading…</p>';
  if (!TRACK_OVERVIEW) {
    try { TRACK_OVERVIEW = await getJSON("/api/trackingoverview"); }
    catch (e) { host.innerHTML = '<p class="err">' + String(e.message || e) + "</p>"; return; }
  }
  const D2 = TRACK_OVERVIEW;
  if (!D2.available) { host.innerHTML = '<p class="sub">No tracking results.</p>'; return; }
  host.innerHTML = "";

  const grid = document.createElement("div");
  grid.className = "trackgrid";
  const genos = [...new Set(D2.chains.map(c => c.genotype).filter(Boolean))].sort();
  const legend = legendRow(genos.map(g => [genoColour(g), g]));

  // 1. does tracking decay with elapsed time?
  const pairs = D2.pairs.filter(p => p.rate != null && p.divGap != null);
  grid.append(scatterPanel(
    "Match rate against elapsed time",
    "one point per day-pair" + legend,
    pairs.map(p => ({x: p.divGap, y: p.rate, c: genoColour(p.genotype), r: 3,
                     title: `${p.chain} · DIV gap ${p.divGap} · ${p.rate.toFixed(3)}`,
                     tip: `<b>${p.chain}</b><br>${p.genotype || "?"}<hr>` +
                          `DIV gap <b>${p.divGap}</b> days<br>` +
                          `match rate <b>${p.rate.toFixed(3)}</b><br>` +
                          (p.registered ? "registered" : "<i>passed through the gate</i>")})),
    {xLabel: "DIV gap (days)", yLabel: "match rate", y0: 0,
     xHelp: AXIS_HELP.divGap, yHelp: AXIS_HELP.matchRate,
     y1: Math.max(0.2, ...pairs.map(p => p.rate)),
     rules: [{y: D2.threshold, label: `tracked ≥ ${D2.threshold}`}],
     fmtX: v => v.toFixed(0), fmtY: v => v.toFixed(2)}));

  // 2. the two quality axes disagree, and that is the point
  const q = D2.chains.filter(c => c.separability != null && c.coverage != null);
  const maxCells = Math.max(1, ...q.map(c => c.nCells || 0));
  grid.append(scatterPanel(
    "Separability against coverage",
    "one point per chain, sized by cells tracked" + legend,
    q.map(c => ({x: c.separability, y: c.coverage, c: genoColour(c.genotype),
                 r: 3 + 6 * Math.sqrt((c.nCells || 0) / maxCells),
                 title: `${c.chain} · sep ${c.separability.toFixed(2)} · `
                        + `cov ${c.coverage.toFixed(2)} · ${c.nCells || 0} cells`,
                 tip: chainTip(c,
                   "High separability with low coverage means few matches, well "
                   + "made. The two axes disagree, and match rate is not a "
                   + "per-match quality score.")})),
    {xLabel: "separability (fingerprint AUC vs the spatial null)",
     yLabel: "coverage (median match rate)", x0: 0.4, x1: 1, y0: 0, y1: 1,
     xHelp: AXIS_HELP.separability, yHelp: AXIS_HELP.coverage,
     rules: [{x: 0.55, label: "0.55 — below this, matches barely separate"}],
     fmtX: v => v.toFixed(2), fmtY: v => v.toFixed(2)}));

  // 3. did the gate decide correctly?
  const shifted = D2.chains.filter(c => c.shiftPx != null && c.medianMatch != null);
  grid.append(scatterPanel(
    "Field-of-view offset against match rate",
    "chains left of the gate were tracked unregistered" + legendRow([
      [themeColour("--plot-wt"), "registered"],
      [themeColour("--plot-off"), "passed through"]]),
    shifted.map(c => ({x: Math.max(c.shiftPx, 1), y: c.medianMatch,
                       c: c.registered ? themeColour("--plot-wt")
                                        : themeColour("--plot-off"), r: 4,
                       title: `${c.chain} · ${c.shiftPx.toFixed(1)} px · `
                              + `median ${c.medianMatch.toFixed(3)}`,
                       tip: chainTip(c,
                         `median match <b>${c.medianMatch.toFixed(3)}</b>`)})),
    {xLabel: "measured offset (px, log)", yLabel: "chain median match rate",
     xHelp: AXIS_HELP.offset, yHelp: AXIS_HELP.matchRate,
     logX: true, logFloor: 1, x0: 1, x1: Math.max(100, ...shifted.map(c => c.shiftPx)),
     y0: 0, y1: Math.max(0.2, ...shifted.map(c => c.medianMatch)),
     rules: [{x: D2.gatePx, label: `${D2.gatePx} px gate`},
             {y: D2.threshold, label: `tracked ≥ ${D2.threshold}`}],
     fmtX: v => v.toFixed(0), fmtY: v => v.toFixed(2)}));

  grid.append(usablePanel(D2));
  host.append(grid);
}

/** Usable chains by genotype and prep — the confound, shown by default. */
function usablePanel(D2) {
  const fig = document.createElement("figure");
  fig.className = "trackfig";
  const thr = D2.threshold;
  const byGeno = {}, byPrep = {};
  for (const c of D2.chains) {
    const usable = c.medianMatch != null && c.medianMatch >= thr;
    for (const [map, key] of [[byGeno, c.genotype || "?"], [byPrep, c.prep || "?"]]) {
      map[key] = map[key] || {n: 0, ok: 0};
      map[key].n++; if (usable) map[key].ok++;
    }
  }
  const rows = (map) => Object.entries(map).sort()
    .map(([k, v]) => `<tr><td>${k}</td><td class="num">${v.ok}/${v.n}</td>`
      + `<td><span class="bar" style="width:${(v.n ? v.ok / v.n : 0) * 100}%"></span></td></tr>`)
    .join("");
  fig.innerHTML =
    `<figcaption><b>Usable chains by genotype and prep</b><br>` +
    `<span class="sub">median match ≥ ${thr}. Recovery covaries with prep and prep ` +
    `covaries with genotype, so a group comparison built on tracked cells inherits ` +
    `that — prefer within-prep comparisons.</span></figcaption>` +
    `<div class="twocol"><table class="tracktab"><thead><tr><th>genotype</th>` +
    `<th class="num">usable</th><th></th></tr></thead><tbody>${rows(byGeno)}</tbody></table>` +
    `<table class="tracktab"><thead><tr><th>prep</th><th class="num">usable</th>` +
    `<th></th></tr></thead><tbody>${rows(byPrep)}</tbody></table></div>`;
  return fig;
}

async function initTracking() {
  try { TRACKING = await getJSON("/api/tracking"); }
  catch (e) { TRACKING = {available: false, chains: []}; }
  if (!TRACKING.available || !TRACKING.chains.length) return;
  $("tab-tracking").classList.remove("hidden");
  fillChainPicker();
  $("track-chain").addEventListener("change", showTracking);
  $("track-view").addEventListener("change", showTracking);
  // A link can land straight on a chain's cells: the GUI's "Open in viewer"
  // button sends ?tab=tracking&chain=…, and the tab only exists once the
  // tracking data has answered, which is now.
  const want = new URLSearchParams(location.search);
  if (want.get("tab") === "tracking") {
    const chain = want.get("chain");
    const sel = $("track-chain");
    if (chain && [...sel.options].some(o => o.value === chain)) {
      sel.value = chain;
      // a chain was asked for, so show its cells, not the dataset overview
      $("track-view").value = want.get("view") || "cells";
    }
    selectTab("tracking");
  }
}

async function showTracking() {
  const view = $("track-view") ? $("track-view").value : "cells";
  // Both the per-cell and the network views are of one chain, so the chain
  // picker belongs to both. Only the overview spans the dataset.
  const perChain = view !== "overview";
  for (const id of ["track-chain", "track-meta", "track-chain-head"])
    if ($(id)) $(id).classList.toggle("hidden", !perChain);
  if (perChain) fillChainPicker();
  if (view === "overview") return showTrackingOverview();
  if (view === "network") return showTrackingNetwork();
  const sel = $("track-chain");
  if (!sel || !sel.value) return;
  const meta = (TRACKING.chains || []).find(c => c.chain === sel.value) || {};
  const fmt = (v, d) => v == null ? "n/a" : v.toFixed(d);
  $("track-meta").innerHTML =
    `<b>${meta.genotype || "?"}</b> · ${meta.prep || "?"} · DIVs ${(meta.divs || []).join(", ")}<br>` +
    `separability ${fmt(meta.separability, 2)} · coverage ${fmt(meta.coverage, 2)} · ` +
    `persistence ${fmt(meta.persistence, 2)}<br>` +
    (meta.registered ? "registered" : "passed through unregistered") +
    ` (${fmt(meta.measuredShiftPx, 1)} px)` +
    networkNote(meta) +
    (meta.warnings || []).map(w => `<br><span class="err">${w}</span>`).join("");

  // The per-cell view is its own self-contained page, rebuilt by Python from
  // the payload the bundle carries — the same "re-request it from the data"
  // rule the figure tabs follow. An iframe keeps its markup, styles and script
  // from colliding with this page's.
  const host = $("tracking");
  host.innerHTML = "";
  const frame = document.createElement("iframe");
  frame.setAttribute("title", "tracked cells for " + sel.value);
  frame.style.cssText = "width:100%;height:calc(100vh - 150px);border:0;border-radius:8px";
  frame.src = "/api/trackingpage?chain=" + encodeURIComponent(sel.value)
            + "&theme=" + effectiveTheme();
  host.appendChild(frame);
}

/** Whether this chain can draw a network, said plainly rather than implied. */
function networkNote(meta) {
  const n = meta.networkCells || 0, all = meta.allDayCells || 0;
  return n >= 8
    ? `<br><b>${n}</b> cells tracked into 2+ days (<b>${all}</b> on every day)`
      + " — network can be drawn"
    : `<br><span class="warn">only ${n} cells tracked into 2+ days — too few `
      + "for a network</span>";
}

/** Group and order the chain list for the view being shown.
 *
 *  The network panels need cells present on *every* day, which is a far
 *  stricter bar than being matched in some pair — many chains cannot draw one
 *  at all. Putting those in their own group says so before a chain is picked,
 *  rather than after it renders empty.
 */
function fillChainPicker() {
  const sel = $("track-chain");
  if (!sel || !TRACKING) return;
  const keep = sel.value;
  const view = $("track-view") ? $("track-view").value : "cells";
  const network = view === "network";

  const drawable = c => (c.networkCells || 0) >= 8;
  const chains = TRACKING.chains.slice();
  chains.sort((a, b) => {
    if (network && drawable(a) !== drawable(b)) return drawable(a) ? -1 : 1;
    if (network) return (b.networkCells || 0) - (a.networkCells || 0);
    return (b.separability == null ? -1 : b.separability)
         - (a.separability == null ? -1 : a.separability);
  });

  sel.innerHTML = "";
  const label = c => {
    const sep = c.separability == null ? "n/a" : c.separability.toFixed(2);
    return network
      ? `${c.chain}  ·  ${c.networkCells || 0} cells (${c.allDayCells || 0} all days)`
      : `${c.chain}  ·  sep ${sep}`;
  };
  const add = (into, c) => {
    const o = document.createElement("option");
    o.value = c.chain; o.textContent = label(c);
    into.appendChild(o);
  };
  if (network) {
    const yes = chains.filter(drawable), no = chains.filter(c => !drawable(c));
    for (const [name, list] of [
        [`Network can be drawn (${yes.length})`, yes],
        [`Too few cells through every day (${no.length})`, no]]) {
      if (!list.length) continue;
      const g = document.createElement("optgroup");
      g.label = name;
      for (const c of list) add(g, c);
      sel.appendChild(g);
    }
  } else {
    for (const c of chains) add(sel, c);
  }
  if (keep && [...sel.querySelectorAll("option")].some(o => o.value === keep))
    sel.value = keep;
}

let NETWORK = null;

/** One zoom shared by every network panel: the days are only comparable at the
 *  same magnification and position, exactly as in the field-of-view strip. */
let NET_VIEW = {k: 1, dx: 0, dy: 0};
/** Cell index to isolate, or null for the whole network. */
let NET_FOCUS = null;
function netZoom() { return NET_VIEW; }

/** Live panels, so pan and zoom can move what is on screen instead of
 *  rebuilding it. Re-rendering mid-gesture destroyed the very element holding
 *  the pointer listener, which is why dragging moved once and then stopped. */
let NET_PANELS = [];

function netTransform(S) {
  const z = NET_VIEW;
  return `translate(${(1 - z.k) * S / 2 + z.dx * S} `
       + `${(1 - z.k) * S / 2 + z.dy * S}) scale(${z.k})`;
}

function applyNetView() {
  for (const panel of NET_PANELS)
    panel.g.setAttribute("transform", netTransform(panel.S));
  const label = document.getElementById("net-zoom");
  if (label) label.textContent = NET_VIEW.k.toFixed(1) + "\u00d7";
}

function resetNetZoom() { NET_VIEW = {k: 1, dx: 0, dy: 0}; drawNetwork(); }

function attachNetZoom(svg, S, g) {
  NET_PANELS.push({svg, g, S});

  svg.addEventListener("wheel", ev => {
    ev.preventDefault();
    const r = svg.getBoundingClientRect();
    const ux = (ev.clientX - r.left) / r.width - 0.5;
    const uy = (ev.clientY - r.top) / r.height - 0.5;
    const before = NET_VIEW.k;
    const k = Math.max(1, Math.min(12, before * Math.exp(-ev.deltaY * 0.0016)));
    NET_VIEW.dx -= ux * (k - before) / k;
    NET_VIEW.dy -= uy * (k - before) / k;
    NET_VIEW.k = k;
    if (k === 1) { NET_VIEW.dx = 0; NET_VIEW.dy = 0; }
    // a zoom changes node radii, which only a redraw can recompute
    drawNetwork();
  }, {passive: false});

  let drag = null;
  svg.addEventListener("pointerdown", ev => {
    // no setPointerCapture: capturing on the svg steals the click from the
    // node underneath, which is how clicking a cell stopped working
    drag = {x: ev.clientX, y: ev.clientY, moved: false};
  });
  svg.addEventListener("pointermove", ev => {
    if (!drag) return;
    if (Math.abs(ev.clientX - drag.x) + Math.abs(ev.clientY - drag.y) > 2)
      drag.moved = true;
    const r = svg.getBoundingClientRect();
    NET_VIEW.dx += (ev.clientX - drag.x) / r.width / NET_VIEW.k;
    NET_VIEW.dy += (ev.clientY - drag.y) / r.height / NET_VIEW.k;
    drag = {x: ev.clientX, y: ev.clientY, moved: drag.moved};
    // panning only translates, so move the live panels rather than redraw
    applyNetView();
  });
  const end = () => {
    if (drag) NET_DRAGGED = drag.moved;   // a drag must not read as a click
    drag = null;
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("dblclick", resetNetZoom);
}

/** True when the last pointer gesture moved, so click handlers can ignore it. */
let NET_DRAGGED = false;

const NODE_METRIC_LABEL = {
  none: "uniform", strength: "strength", clustering: "clustering coefficient",
  betweenness: "betweenness", participation: "participation coefficient",
  module_z: "within-module z-score", role: "cartography role",
};

/** MEA-NAP's six roles. Peripheral first — it is ~90% of these nodes. */
const ROLE_LABEL = {1: "peripheral", 2: "non-hub connector", 3: "non-hub kinless",
                    4: "provincial hub", 5: "connector hub", 6: "kinless hub"};
const ROLE_COLOUR = {1: "#9aa4af", 2: "#2c7fb8", 3: "#7b3294",
                     4: "#f2a057", 5: "#d62728", 6: "#1a7f37"};

/** Blue-to-red ramp for a continuous measure. */
function rampColour(t) {
  t = Math.max(0, Math.min(1, t));
  const a = [44, 127, 184], b = [214, 39, 40];
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;
}

async function showTrackingNetwork() {
  const sel = $("track-chain");
  if (!sel || !sel.value) return;
  const host = $("tracking");
  host.innerHTML = '<p class="sub">Loading…</p>';
  host.dataset.span = "";     // each chain picks its own default span
  NET_VIEW = {k: 1, dx: 0, dy: 0};
  NET_FOCUS = null;
  try { NETWORK = await getJSON("/api/trackingnetwork?chain=" + encodeURIComponent(sel.value)); }
  catch (e) { host.innerHTML = '<p class="err">' + String(e.message || e) + "</p>"; return; }
  drawNetwork();
}

/** How many cells survive each span, so the choice is informed before it is made. */
function spanCounts(net) {
  const out = {};
  for (let n = 2; n <= (net.nSessions || 2); n++)
    out[n] = (net.span || []).filter(v => v >= n).length;
  return out;
}

/** The legend for the current colouring: a ramp for a measure, swatches for roles. */
function colourScale(colourBy, lo, hi) {
  if (colourBy === "none") return "";
  if (colourBy === "role") {
    return '<div class="legend netlegend">'
      + Object.keys(ROLE_LABEL).map(r =>
          `<span><i class="sw" style="background:${ROLE_COLOUR[r]}"></i>`
          + `${ROLE_LABEL[r]}</span>`).join("")
      + "</div>";
  }
  const stops = [0, .25, .5, .75, 1].map(t => rampColour(t)).join(",");
  const fmt = v => Number.isFinite(v) ? v.toFixed(2) : "–";
  return '<div class="netlegend"><span class="sub">'
    + `${NODE_METRIC_LABEL[colourBy]}</span>`
    + `<span class="sub">${fmt(lo)}</span>`
    + `<span class="ramp" style="background:linear-gradient(90deg,${stops})"></span>`
    + `<span class="sub">${fmt(hi)}</span>`
    + '<span class="sub">· scaled within each day</span></div>';
}

function drawNetwork() {
  const host = $("tracking");
  const d = NETWORK || {};
  const net = d.network || {};
  host.innerHTML = "";

  if (!net.days || !net.days.length) {
    host.innerHTML = '<p class="sub">Fewer than eight cells were tracked into '
      + 'even two days of this chain, so there is no network to draw.</p>';
    return;
  }

  const counts = spanCounts(net);
  // default to the most demanding span that still has enough cells: the
  // strictest honest answer, rather than the one with the most dots
  let span = Number(host.dataset.span || 0);
  if (!span) {
    span = 2;
    for (let n = net.nSessions; n >= 2; n--)
      if ((counts[n] || 0) >= 8) { span = n; break; }
    host.dataset.span = span;
  }

  const opts = [];
  for (let n = 2; n <= (net.nSessions || 2); n++)
    opts.push(`<option value="${n}"${n === span ? " selected" : ""}>`
      + `tracked into ≥ ${n} days — ${counts[n]} cells</option>`);
  const haveMetrics = (net.days || []).some(d => d.metrics);
  const colourOpts = ["none", "strength", "clustering", "betweenness",
                      "participation", "module_z", "role"]
    .filter(k => k === "none" || haveMetrics)
    .map(k => `<option value="${k}"${k === (host.dataset.colour || "none")
      ? " selected" : ""}>${NODE_METRIC_LABEL[k]}</option>`).join("");
  host.insertAdjacentHTML("beforeend",
    '<div class="ctl" style="margin-bottom:10px">'
    + '<label>cell set <select id="net-span">' + opts.join("") + "</select></label>"
    + '<label>colour by <select id="net-colour">' + colourOpts + "</select></label>"
    + '<label>size <select id="net-size">'
    + ["small", "medium", "large"].map(k =>
        `<option value="${k}"${k === (host.dataset.size || "medium")
          ? " selected" : ""}>${k}</option>`).join("")
    + "</select></label>"
    + '<span class="sub">scroll to zoom · drag to pan · all days move together</span>'
    + '<span class="sub" id="net-zoom">' + NET_VIEW.k.toFixed(1) + '\u00d7</span>' 
    + '<button id="net-reset" type="button">reset view</button>' 
    + `<span class="sub">of ${net.nCells} cells tracked into two or more days; `
    + `${net.nShared} appear on all ${net.nSessions}</span></div>`);
  $("net-span").addEventListener("change", e => {
    host.dataset.span = e.target.value;
    drawNetwork();
  });
  if ($("net-colour"))
    $("net-colour").addEventListener("change", e => {
      host.dataset.colour = e.target.value;
      drawNetwork();
    });
  if ($("net-size"))
    $("net-size").addEventListener("change", e => {
      host.dataset.size = e.target.value;
      drawNetwork();
    });
  if ($("net-reset")) $("net-reset").addEventListener("click", resetNetZoom);
  const colourBy = host.dataset.colour || "none";

  const keep = new Set();
  (net.span || []).forEach((v, i) => { if (v >= span) keep.add(i); });
  if (keep.size < 2) {
    host.insertAdjacentHTML("beforeend",
      '<p class="sub">Too few cells at this span to draw a network.</p>');
    return;
  }

  const sizes = {small: 230, medium: 330, large: 460};
  const sizeKey = host.dataset.size || "medium";
  const S = sizes[sizeKey] || sizes.medium;

  const xy = net.xy;
  let lo = [Infinity, Infinity], hi = [-Infinity, -Infinity];
  for (const i of keep) for (const k of [0, 1]) {
    lo[k] = Math.min(lo[k], xy[i][k]); hi[k] = Math.max(hi[k], xy[i][k]); }
  const pad = 12, spanPx = Math.max(hi[0] - lo[0], hi[1] - lo[1]) || 1;

  let legendLo = Infinity, legendHi = -Infinity;
  if (colourBy !== "none" && colourBy !== "role") {
    for (const day of net.days) {
      const m = (day.metrics || {})[colourBy];
      if (!m) continue;
      for (const i of keep) {
        const v = m[String(i)];
        if (v == null) continue;
        legendLo = Math.min(legendLo, v); legendHi = Math.max(legendHi, v);
      }
    }
  }
  host.insertAdjacentHTML("beforeend", colourScale(colourBy, legendLo, legendHi));
  if (NET_FOCUS != null)
    host.insertAdjacentHTML("beforeend",
      `<p class="sub">Showing <b>cell ${NET_FOCUS}</b> and what it connects to on `
      + "each day; the rest of the network is faded. Click it again, or the "
      + "background, to show everything.</p>");

  NET_PANELS = [];
  const wrap = document.createElement("div");
  wrap.className = "netrow";
  wrap.insertAdjacentHTML("beforeend",
    `<p class="sub" style="flex:1 1 100%">${keep.size} cells, drawn on the `
    + "coordinates of the first day each appears — so what changes between "
    + "panels is the correlation structure, not the field of view. A cell is "
    + "only drawn on the days it was actually tracked into. Edges are the "
    + "strongest tenth on each day; node size is total correlation.</p>");

  for (const day of net.days) {
    const present = new Set((day.present || []).filter(i => keep.has(i)));
    const fig = document.createElement("figure");
    fig.className = "trackfig netfig";
    fig.style.width = (S + 22) + "px";
    const svg = svgEl("svg", {viewBox: `0 0 ${S} ${S}`, class: "trackplot netplot"});
    const zoom = netZoom();
    const g = svgEl("g", {transform:
      `translate(${(1 - zoom.k) * S / 2 + zoom.dx * S} `
      + `${(1 - zoom.k) * S / 2 + zoom.dy * S}) scale(${zoom.k})`});
    svg.append(g);
    const px = v => pad + (v - lo[1]) / spanPx * (S - 2 * pad);
    const py = v => pad + (v - lo[0]) / spanPx * (S - 2 * pad);

    let edges = (day.edges || []).filter(e => keep.has(e[0]) && keep.has(e[1]));
    // clicking a cell asks "who is this one talking to?", so everything else
    // fades rather than disappearing — the rest of the network is the context
    // that makes the answer meaningful
    let neighbours = null;
    if (NET_FOCUS != null) {
      neighbours = new Set([NET_FOCUS]);
      for (const [i, j] of edges) {
        if (i === NET_FOCUS) neighbours.add(j);
        if (j === NET_FOCUS) neighbours.add(i);
      }
    }
    let wlo = Infinity, whi = -Infinity;
    for (const e of edges) { wlo = Math.min(wlo, e[2]); whi = Math.max(whi, e[2]); }
    for (const [i, j, w] of edges) {
      const t = whi > wlo ? (w - wlo) / (whi - wlo) : 1;
      const onFocus = neighbours == null
        || i === NET_FOCUS || j === NET_FOCUS;
      g.append(svgEl("line", {x1: px(xy[i][1]), y1: py(xy[i][0]),
        x2: px(xy[j][1]), y2: py(xy[j][0]),
        stroke: onFocus ? themeColour("--plot-wt") : themeColour("--plot-off"),
        "stroke-width": ((onFocus ? 0.5 + 2.0 * t : 0.3) / zoom.k).toFixed(2),
        opacity: onFocus ? .55 : .06}));
    }
    // size always follows total correlation; colour follows the chosen measure
    const st = day.strength || {};
    let slo = Infinity, shi = -Infinity;
    for (const i of present) {
      const v = st[String(i)]; if (v == null) continue;
      slo = Math.min(slo, v); shi = Math.max(shi, v); }

    const cm = (day.metrics || {})[colourBy];
    let clo = Infinity, chi = -Infinity;
    if (cm) for (const i of present) {
      const v = cm[String(i)]; if (v == null) continue;
      clo = Math.min(clo, v); chi = Math.max(chi, v); }

    for (const i of present) {
      const v = st[String(i)];
      const t = (v != null && shi > slo) ? (v - slo) / (shi - slo) : 0.5;
      let fill = themeColour("--plot-sel");
      if (colourBy === "role" && day.role) {
        fill = ROLE_COLOUR[day.role[String(i)]] || themeColour("--plot-off");
      } else if (cm) {
        const cv = cm[String(i)];
        fill = cv == null ? themeColour("--plot-off")
          : rampColour(chi > clo ? (cv - clo) / (chi - clo) : 0.5);
      }
      const inFocus = neighbours == null || neighbours.has(i);
      const isFocus = i === NET_FOCUS;
      const dot = svgEl("circle", {cx: px(xy[i][1]), cy: py(xy[i][0]),
        // divided by the zoom so nodes stay the same size on screen as you
        // magnify — the point of zooming here is to separate them, not enlarge
        r: ((isFocus ? 3.4 : 1.6 + 2.6 * t) / zoom.k).toFixed(2), fill,
        "fill-opacity": inFocus ? .9 : .12});
      if (isFocus) {
        dot.setAttribute("stroke", themeColour("--fg"));
        dot.setAttribute("stroke-width", (1.4 / zoom.k).toFixed(2));
      }
      dot.setAttribute("class", "netnode");
      dot.addEventListener("click", ev => {
        ev.stopPropagation();
        if (NET_DRAGGED) { NET_DRAGGED = false; return; }
        NET_FOCUS = (NET_FOCUS === i) ? null : i;   // clicking again releases
        drawNetwork();
      });
      // "uniform" has no metric map; reading one because a role map happens to
      // exist threw and took the whole render with it
      const strengthLine = `strength ${v == null ? "n/a" : v.toFixed(3)}`;
      let shown = null;
      if (colourBy === "role" && day.role) shown = ROLE_LABEL[day.role[String(i)]] || "?";
      else if (cm) shown = cm[String(i)] == null ? "n/a" : cm[String(i)].toFixed(3);
      attachTip(dot, `<b>cell ${i}</b><br>` +
        (shown == null ? "" : `${NODE_METRIC_LABEL[colourBy]}: <b>${shown}</b><br>`) +
        strengthLine);
      g.append(dot);
    }
    svg.addEventListener("click", () => {
      if (NET_DRAGGED) { NET_DRAGGED = false; return; }
      if (NET_FOCUS != null) { NET_FOCUS = null; drawNetwork(); }
    });
    attachNetZoom(svg, S, g);
    fig.append(svg);
    fig.insertAdjacentHTML("beforeend",
      `<figcaption class="sub">DIV${day.div} · ${present.size} cells · `
      + `${edges.length} edges` +
      (day.threshold == null ? "" : ` ≥ ${day.threshold.toFixed(2)}`) +
      (day.nModules == null ? ""
        : `<br>${day.nModules} modules · Q ${day.modularity.toFixed(2)}`) +
      "</figcaption>");
    wrap.append(fig);
  }
  host.append(wrap);

  // node measures and roles across days
  const ms = d.metricStability || [];
  if (ms.length) {
    const metrics = Object.keys(ms[0].metrics || {});
    const head = '<tr><th>day-pair</th><th class="num">gap</th><th class="num">n</th>'
      + metrics.map(m => `<th class="num">${NODE_METRIC_LABEL[m] || m}</th>`).join("")
      + '<th class="num">role κ</th></tr>';
    const body = ms.map(r => {
      const cells = metrics.map(m => {
        const v = r.metrics[m] || {};
        if (v.r == null) return '<td class="num sub">n/a</td>';
        // the shuffled null sits beside each value: a measure can look stable
        // simply because its distribution is skewed
        const strong = v.null == null ? v.r > 0.2 : v.r - v.null > 0.15;
        return `<td class="num"><b${strong ? "" : ' class="sub"'}>${v.r.toFixed(2)}</b>`
             + `<br><span class="sub">null ${v.null == null ? "–" : v.null.toFixed(2)}</span></td>`;
      }).join("");
      const k = r.role || {};
      const kappa = k.kappa == null ? "n/a" : k.kappa.toFixed(2);
      return `<tr><td>${r.pair}</td><td class="num">${r.divGap}</td>`
           + `<td class="num">${r.n}</td>${cells}`
           + `<td class="num"><b>${kappa}</b><br><span class="sub">`
           + `${k.agreement == null ? "" : (k.agreement * 100).toFixed(0) + "% raw"}`
           + `</span></td></tr>`;
    }).join("");
    host.insertAdjacentHTML("beforeend",
      '<figure class="trackfig"><figcaption><b>Do node measures and roles hold '
      + 'across days?</b><br><span class="sub">Each cell shows the correlation '
      + 'between the same cells\' values on the two days, with the value from '
      + 'shuffling which cell is which beneath it. A measure is only stable if it '
      + 'clears its own null.<br><br><b>role κ</b> is Cohen\'s kappa, not raw '
      + 'agreement: these subnetworks are ~90% peripheral, so two unrelated '
      + 'labellings already agree ~85% of the time. 0 is chance, 1 is perfect — '
      + 'the raw percentage is shown beneath only for reference.'
      + '</span></figcaption><table class="tracktab"><thead>' + head
      + "</thead><tbody>" + body + "</tbody></table></figure>");
  }

  const rows = (d.stability || []).map(s =>
    `<tr><td>${s.pair}</td><td class="num">${s.divGap}</td>` +
    `<td class="num">${s.nShared}</td>` +
    `<td class="num"><b>${s.edgeR.toFixed(3)}</b></td>` +
    `<td class="num">${s.nullR == null ? "n/a" : s.nullR.toFixed(3)}</td></tr>`).join("");
  host.insertAdjacentHTML("beforeend",
    '<figure class="trackfig"><figcaption><b>Does the structure survive?</b><br>' +
    '<span class="sub">Correlation between the same cells\' edge weights on the two ' +
    'days, against a null that swaps each cell for its nearest neighbour — position ' +
    'held roughly fixed, identity varied. Measured per day-pair on the cells those ' +
    'two days share, so it does not depend on the span chosen above. Across this ' +
    'dataset the matched median is +0.48 against +0.05, and it decays with elapsed ' +
    'time rather than resetting.</span></figcaption>' +
    '<table class="tracktab"><thead><tr><th>day-pair</th><th class="num">gap</th>' +
    '<th class="num">cells</th><th class="num">edge r</th>' +
    '<th class="num">spatial null</th></tr></thead><tbody>' +
    (rows || '<tr><td colspan="5" class="sub">no day-pair had enough shared cells</td></tr>') +
    "</tbody></table></figure>");
}

function download(fmt) {
  if (VIEW.kind === "family" || VIEW.kind === "both") return;
  window.location = figureURL({ fmt: fmt, download: "1" });
}

(async function init() {
  try {
    MANIFEST = await getJSON("/api/manifest");
  } catch (e) {
    document.body.innerHTML =
      '<p class="err" style="padding:24px">Could not load this bundle: ' +
      String(e.message || e) + "</p>";
    return;
  }
  $("source").textContent = `${MANIFEST.source} · ${MANIFEST.mode}`;
  applyTheme(currentTheme());
  $("theme").addEventListener("click", cycleTheme);
  initTracking();
  for (const id of ["lag-head", "cmp-lag-head"])
    if ($(id)) $(id).textContent = timescaleLabel();
  // A run made before version stamping simply has none; say
  // nothing rather than claiming "unknown".
  const pb = MANIFEST.produced_by;
  if (pb && pb.version)
    $("source").textContent += `  ·  ${pb.pipeline_name} ${pb.version}`;
  // A viewer opened on a folder has nothing to export: it is already one.
  $("export").classList.toggle("hidden", !MANIFEST.can_export);
  buildControls();
  buildComparisonControls();
  fillRecordings();
  fillComparisonFamilies();
  fillFamilies();
  fillLagSeries();
  fillStatsLags();

  // A tab with nothing behind it is removed, not shown empty.
  if (!(MANIFEST.stats || []).length) $("tab-stats").classList.add("hidden");
  if (!(MANIFEST.comparisons || []).length && !(MANIFEST.families || []).length)
    $("tab-comparisons").classList.add("hidden");
  if (!(MANIFEST.lag_series || []).length)
    $("tab-lags").classList.add("hidden");
  // An older bundle may carry no params.json at all.
  if (!MANIFEST.params) $("tab-params").classList.add("hidden");
  else fillParamGroups();

  $("stats-lag").addEventListener("change", () => {
    VIEW.statsLag = $("stats-lag").value;
    fillStatsFigures();
    if (TAB === "stats") showStats();
  });
  $("recording").addEventListener("change", fillLags);
  $("lag").addEventListener("change", () => { fillFigures(); fillSubnetworks(); });
  $("export").addEventListener("click", onExport);
  $("cmp-family").addEventListener("change", fillComparisonFacets);
  $("cmp-level").addEventListener("change", fillComparisonMetrics);
  $("cmp-split").addEventListener("change", showComparison);
  $("cmp-lag").addEventListener("change", showComparison);
  $("reset").addEventListener("click", resetControls);
  $("cmp-reset").addEventListener("click", resetComparisonControls);
  $("dl-png").addEventListener("click", () => download("png"));
  $("dl-svg").addEventListener("click", () => download("svg"));
  $("dl-pdf").addEventListener("click", () => download("pdf"));
  for (const b of document.querySelectorAll("#tabs button"))
    b.addEventListener("click", () => selectTab(b.dataset.tab));

  selectTab("recordings");
})();
</script>
</body>
</html>
"""
