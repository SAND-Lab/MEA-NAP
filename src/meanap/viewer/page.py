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
  at a time. The CAT-NAP families that have no such address stay galleries,
  listed separately so the difference is visible rather than surprising.
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
    --bg: #ffffff; --fg: #16181d; --muted: #6b7280; --line: #e3e6ea;
    --panel: #f7f8fa; --accent: #2563eb; --accent-soft: #eaf0fe;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14161a; --fg: #e7e9ee; --muted: #9aa1ac; --line: #2a2e35;
      --panel: #1b1e24; --accent: #6ea8fe; --accent-soft: #1e2836;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    display: grid; height: 100vh;
    grid-template-columns: 260px 1fr 280px;
    grid-template-rows: auto 1fr;
    grid-template-areas: "tabs tabs tabs" "left main right";
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
  #tabs .src { color: var(--muted); font-size: 12px; padding-right: 4px;
    overflow-wrap: anywhere; max-width: 40ch; text-align: right; }

  aside { overflow-y: auto; padding: 16px; }
  aside.left { grid-area: left; border-right: 1px solid var(--line); }
  aside.right { grid-area: right; border-left: 1px solid var(--line); }
  main { grid-area: main; overflow-y: auto; padding: 20px 24px; min-width: 0; }

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
</style>
</head>
<body>

<nav id="tabs">
  <span class="brand">MEA-NAP viewer</span>
  <button id="tab-recordings" data-tab="recordings" aria-selected="true">Recordings</button>
  <button id="tab-comparisons" data-tab="comparisons" aria-selected="false">Comparisons</button>
  <button id="tab-lags" data-tab="lags" aria-selected="false">Across lags</button>
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
    <h2>Lag</h2>
    <select id="lag"></select>

    <h2>Network figures</h2>
    <div class="list" id="figures"></div>

    <h2>Activity figures</h2>
    <div class="list" id="activity"></div>

    <h2>Spike detection</h2>
    <div class="list" id="spikechecks"></div>

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
  <figure id="single"><img id="figure-img" alt=""></figure>
  <div id="pair" class="hidden"></div>
  <div class="gallery hidden" id="gallery"></div>
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
  <label id="cmp-lag-label"><span class="l">Lag</span>
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
    el.addEventListener("change", () => { if (VIEW.kind === "figure") showFigure(); });
    label.appendChild(el);
    if (c.help) { const s = document.createElement("small"); s.textContent = c.help;
                  label.appendChild(s); }
    box.appendChild(label);
  }
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

function resetControls() {
  for (const c of MANIFEST.controls) {
    const el = $("ctl-" + c.key);
    if (el) el.value = c.default;
  }
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

function fillLags() {
  fillActivity();
  fillSpikeChecks();
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
  $("lag-options-head").textContent = series.keyed_by === "lag" ? "Lag" : "Metric";
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
}

function setMode(kind) {
  const one = kind === "figure" || kind === "activity" || kind === "lagseries"
              || kind === "spikecheck" || kind === "edgecheck"
              || kind === "subnetwork";
  // Hidden, not disabled: the styling controls describe spatial network plots.
  // A raster, a violin and a line plot read none of them, so offering the
  // knobs there would imply they do something.
  $("controls-panel").classList.toggle("hidden", kind !== "figure");
  const faceted = kind === "comparison" || kind === "both";
  $("facets-panel").classList.toggle("hidden", !(faceted || kind === "lagseries"));
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
  // "Both" shows two figures; a single download button cannot mean both, so
  // the buttons go away rather than silently picking one.
  const downloadable = one || kind === "comparison";
  for (const id of ["dl-png", "dl-svg", "dl-pdf"])
    $(id).classList.toggle("hidden", !downloadable);
}

function showFigure() {
  if (!["activity", "spikecheck", "edgecheck", "subnetwork"].includes(VIEW.kind))
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

function selectTab(tab) {
  TAB = tab;
  for (const b of document.querySelectorAll("#tabs button"))
    b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  $("side-recordings").classList.toggle("hidden", tab !== "recordings");
  $("side-comparisons").classList.toggle("hidden", tab !== "comparisons");
  $("side-lags").classList.toggle("hidden", tab !== "lags");
  if (tab === "recordings") showFigure();
  else if (tab === "comparisons") showComparison();
  else showLagSeries();
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
  // A viewer opened on a folder has nothing to export: it is already one.
  $("export").classList.toggle("hidden", !MANIFEST.can_export);
  buildControls();
  buildComparisonControls();
  fillRecordings();
  fillComparisonFamilies();
  fillFamilies();
  fillLagSeries();

  // A tab with nothing behind it is removed, not shown empty.
  if (!(MANIFEST.comparisons || []).length && !(MANIFEST.families || []).length)
    $("tab-comparisons").classList.add("hidden");
  if (!(MANIFEST.lag_series || []).length)
    $("tab-lags").classList.add("hidden");

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
