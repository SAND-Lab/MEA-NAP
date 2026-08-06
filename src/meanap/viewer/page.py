"""The viewer's single HTML page.

Kept as one self-contained string — no build step, no external assets, no CDN.
A bundle gets shared with people who will run one command and expect a page;
anything that needs npm or a network fetch fails that test.

Two views, and the difference between them is the point:

* **A recording's figure** — one spatial network plot at a time, with the full
  Network Viewer control set live beside it. Every change re-requests the
  figure from Python, so what is on screen is always something the pipeline
  could have drawn.
* **A comparison family** — a gallery of small multiples. The controls are
  *hidden* here, not disabled: they style spatial network plots, and none of
  the violin plots in these families read them. A greyed-out panel would still
  imply the knobs mean something for this view.
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
    display: grid; grid-template-columns: 260px 1fr 280px; height: 100vh;
  }
  @media (max-width: 900px) { body { grid-template-columns: 1fr; height: auto; } }

  aside { border-right: 1px solid var(--line); overflow-y: auto; padding: 16px; }
  aside.right { border-right: none; border-left: 1px solid var(--line); }
  main { overflow-y: auto; padding: 20px 24px; min-width: 0; }

  h1 { font-size: 15px; margin: 0 0 2px; letter-spacing: -0.01em; }
  .sub { color: var(--muted); font-size: 12px; margin-bottom: 18px;
         overflow-wrap: anywhere; }
  h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
       color: var(--muted); margin: 18px 0 8px; font-weight: 600; }

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

  figure { margin: 0; }
  figure img { max-width: 100%; height: auto; display: block;
    border: 1px solid var(--line); border-radius: 8px; background: #fff; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
         margin-bottom: 14px; }
  .row button { width: auto; }
  .status { color: var(--muted); font-size: 12px; min-height: 18px; }
  .err { color: #b42318; white-space: pre-wrap; font-size: 12px; }

  .gallery { display: grid; gap: 14px;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); }
  .gallery figure { border: 1px solid var(--line); border-radius: 8px;
    padding: 8px; background: var(--panel); }
  .gallery img { border: none; border-radius: 4px; }
  .gallery figcaption { font-size: 11px; color: var(--muted); margin-top: 6px;
    overflow-wrap: anywhere; }
  .group-head { grid-column: 1 / -1; font-size: 11px; text-transform: uppercase;
    letter-spacing: .08em; color: var(--muted); margin-top: 8px; }
  .hidden { display: none !important; }
</style>
</head>
<body>

<aside>
  <h1>MEA-NAP viewer</h1>
  <div class="sub" id="source">loading…</div>

  <h2>Recording</h2>
  <select id="recording"></select>
  <h2>Lag</h2>
  <select id="lag"></select>

  <h2>Network figures</h2>
  <div class="list" id="figures"></div>

  <h2>Activity figures</h2>
  <div class="list" id="activity"></div>

  <h2>Comparisons</h2>
  <div class="list" id="families"></div>
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
  <div class="gallery hidden" id="gallery"></div>
</main>

<aside class="right" id="controls-panel">
  <h2>Network styling</h2>
  <div id="controls"></div>
  <button id="reset">Reset to pipeline defaults</button>
  <p class="sub" style="margin-top:12px">
    Defaults reproduce the figure the pipeline drew, pixel for pixel.
  </p>
</aside>

<script>
const $ = (id) => document.getElementById(id);
let MANIFEST = null;
let VIEW = { kind: "figure", rec: null, lag: null, name: null, family: null };
// "figure"   — a network plot, per recording + lag, restylable
// "activity" — a step-2 plot, per recording only; the network controls don't
//              apply to a raster or a heatmap, so they are hidden for it
// "family"   — a gallery of small multiples

async function getJSON(url) {
  const r = await fetch(url);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

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
  if (VIEW.kind === "activity") {
    const p = new URLSearchParams({rec: VIEW.rec, name: VIEW.name});
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return "/api/activity?" + p.toString();
  }
  const p = overrideParams();
  p.set("rec", VIEW.rec); p.set("lag", VIEW.lag); p.set("name", VIEW.name);
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
  const rec = currentRecording();
  const sel = $("lag");
  sel.innerHTML = "";
  for (const lag of (rec ? rec.lags : [])) {
    const o = document.createElement("option");
    o.value = lag; o.textContent = lag + " ms";
    sel.appendChild(o);
  }
  fillFigures();
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
      VIEW = { kind: "activity", rec: rec.name, lag: null, name: f.name, family: null };
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
      VIEW = { kind: "figure", rec: rec.name, lag: lag, name: f.name, family: null };
      showFigure();
    });
    box.appendChild(b);
  }
  // Open the first figure so the page is never blank.
  if (!VIEW.name || VIEW.kind !== "figure" ||
      !figs.some((f) => f.name === VIEW.name)) {
    VIEW = { kind: "figure", rec: rec.name, lag: lag, name: figs[0].name, family: null };
  } else {
    VIEW.rec = rec.name; VIEW.lag = lag;
  }
  showFigure();
}

function fillFamilies() {
  const box = $("families");
  box.innerHTML = "";
  if (!MANIFEST.families.length) {
    box.innerHTML = '<div class="sub">None in this bundle.</div>';
    return;
  }
  for (const fam of MANIFEST.families) {
    const b = document.createElement("button");
    b.textContent = fam.label;
    b.dataset.family = fam.key;
    b.addEventListener("click", () => showFamily(fam));
    box.appendChild(b);
  }
}

function markCurrent() {
  for (const b of document.querySelectorAll("#figures button"))
    b.setAttribute("aria-current", String(VIEW.kind === "figure" && b.dataset.name === VIEW.name));
  for (const b of document.querySelectorAll("#activity button"))
    b.setAttribute("aria-current", String(VIEW.kind === "activity" && b.dataset.activity === VIEW.name));
  for (const b of document.querySelectorAll("#families button"))
    b.setAttribute("aria-current", String(VIEW.kind === "family" && b.dataset.family === VIEW.family));
}

function setMode(kind) {
  const single = kind === "figure" || kind === "activity";
  // Hidden, not disabled: the controls style spatial network plots. A raster,
  // a heatmap and a violin gallery read none of them, so offering the knobs
  // there would imply they do something.
  $("controls-panel").classList.toggle("hidden", kind !== "figure");
  $("single").classList.toggle("hidden", !single);
  $("gallery").classList.toggle("hidden", single);
  for (const id of ["dl-png", "dl-svg", "dl-pdf"])
    $(id).classList.toggle("hidden", !single);
}

function showFigure() {
  if (VIEW.kind !== "activity") VIEW.kind = "figure";
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

async function showFamily(fam) {
  VIEW = { kind: "family", rec: null, lag: null, name: null, family: fam.key };
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

function download(fmt) {
  if (VIEW.kind === "family") return;
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
  buildControls();
  fillRecordings();
  fillFamilies();
  $("recording").addEventListener("change", fillLags);
  $("lag").addEventListener("change", fillFigures);
  $("reset").addEventListener("click", resetControls);
  $("dl-png").addEventListener("click", () => download("png"));
  $("dl-svg").addEventListener("click", () => download("svg"));
  $("dl-pdf").addEventListener("click", () => download("pdf"));
})();
</script>
</body>
</html>
"""
