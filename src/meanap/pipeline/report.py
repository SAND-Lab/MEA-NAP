"""Self-contained HTML output viewer for a MEA-NAP pipeline run.

Walks an output folder (the same tree ``output_folders.py`` creates) and
writes a single ``report.html`` that lets you browse it — a folder tree on
the left, an image gallery on the right, with a caption under each plot
explaining what it shows. No server or external JS/CSS needed; opening the
file directly in a browser works, including over ``file://``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}

# ── Folder descriptions ────────────────────────────────────────────────────
# Keyed by folder name (not full path) — matches MEA-NAP's fixed top-level
# and second-level folder names from output_folders.py / CreateOutputFolders.m.
FOLDER_DESCRIPTIONS: dict[str, str] = {
    "1_SpikeDetection": "Step 1 — spike detection. Raw voltage traces are filtered and thresholded/wavelet-detected to find individual spike times per electrode.",
    "1A_SpikeDetectedData": "Detected spike times per recording, saved as .npz (one array per electrode per detection method).",
    "1B_SpikeDetectionChecks": "Diagnostic plots for step 1, one subfolder per recording — use these to sanity-check that spike detection worked before trusting anything downstream.",
    "2_NeuronalActivity": "Step 2 — neuronal activity. Firing rates and burst structure (single-electrode and network-wide) computed from step 1's spike times.",
    "2A_IndividualNeuronalAnalysis": "Per-recording firing rate and burst-detection plots.",
    "2B_GroupComparisons": "Firing rate / burst metrics compared across recording groups (not yet populated by the Python port — group-level aggregation isn't implemented).",
    "3_EdgeThresholdingCheck": "Step 3 — functional connectivity. Diagnostic plots for the STTC computation and significance thresholding (not yet populated by the Python port's step 3).",
    "4_NetworkActivity": "Step 4 — network activity. Graph-theoretic metrics (node degree, clustering, efficiency, centrality, ...) computed from step 3's thresholded adjacency matrices.",
    "4A_IndividualNetworkAnalysis": "Per-recording, per-lag network plots and connectivity statistics.",
    "4B_GroupComparisons": "Network metrics compared across recording groups (not yet populated by the Python port — group-level aggregation isn't implemented).",
    "ExperimentMatFiles": "Per-recording adjacency matrices (STTC, raw + significance-thresholded) saved as .npz, one file per recording.",
}

# ── Plot captions ──────────────────────────────────────────────────────────
# (regex matched against the filename only, title template, caption template)
# Named groups in the regex are available for .format() substitution.
#
# Captions are adapted from the official MEA-NAP figure-legend reference
# (docs/meanap-outputs.rst) wherever a description exists there, reworded to
# describe what this Python port's (simpler, single-panel) plot actually
# shows — MATLAB's originals often also render "scaled to whole dataset" and
# "combined" side-by-side variants that this port doesn't produce yet. Where
# no MATLAB documentation exists at all (six step-2 burst heatmaps —
# confirmed via repo search: MEApipeline.m only lists filenames, no prose),
# the caption is original, written to match the sibling group-comparison
# figures' documented semantics for the same metric.
_PLOT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"^1_ExampleTraces\.png$"),
        "Example Traces",
        "Sample ~60 ms filtered voltage traces from a few electrodes, each "
        "centered on a detected spike. Colored markers indicate which "
        "detection method caught that spike (e.g. ‘thr4’/‘thr5’ "
        "= median-absolute-deviation threshold methods; ‘bior1.5’ = "
        "wavelet method). Lets you compare detection methods at the "
        "individual-electrode level. (MEA-NAP docs, Step 1B Figure 1)",
    ),
    (
        re.compile(r"^2_SpikeFrequencies\.png$"),
        "Spike Frequencies",
        "Running spike frequency (1-second bins) over the length of the "
        "recording, one line per spike-detection method — compares how "
        "sensitive each method/parameter combination is over time. "
        "(MEA-NAP docs, Step 1B Figure 2)",
    ),
    (
        re.compile(r"^3_Waveforms\.png$"),
        "Detected Waveforms",
        "Overlaid individual spike waveforms (gray) and the mean waveform "
        "(black) detected by each method, from one representative "
        "electrode. A tight overlay indicates consistent, clean "
        "detections; a messy spread suggests noise is being picked up. "
        "(MEA-NAP docs, Step 1B Figure 3)",
    ),
    (
        re.compile(r"^1_FiringRateByElectrode\.png$"),
        "Firing Rate by Electrode",
        "Mean firing rate (spikes/second) of every electrode as a scatter "
        "+ violin plot, showing the distribution of activity levels "
        "across the whole array. (MEA-NAP docs, Step 2A Figure 1)",
    ),
    (
        re.compile(r"^2_Heatmap\.png$"),
        "Firing Rate Heatmap",
        "Mean firing rate (Hz) of each electrode, arranged spatially to "
        "match the physical MEA layout — bright spots mark the most "
        "active regions of the culture. (MEA-NAP docs, Step 2A Figure 2 — "
        "MATLAB additionally scales a second panel to the whole dataset; "
        "this port renders the single recording-scaled heatmap.)",
    ),
    (
        re.compile(r"^3_Raster\.png$"),
        "Raster Plot",
        "Spike raster (each row an electrode, each point a spike) across "
        "the whole recording, with a firing-rate histogram alongside — "
        "the main plot for spotting synchronous or bursting activity by "
        "eye. (MEA-NAP docs, Step 2A Figure 3 — MATLAB additionally shows "
        "a second raster scaled to the whole dataset; this port renders "
        "the single recording-scaled raster.)",
    ),
    (
        re.compile(r"^3_BurstRate_heatmap\.png$"),
        "Burst Rate Heatmap",
        "Spatial heatmap of single-electrode burst rate (bursts per "
        "minute), using the same MEA-layout convention as the firing-rate "
        "heatmap.",
    ),
    (
        re.compile(r"^4_BurstDur_heatmap\.png$"),
        "Burst Duration Heatmap",
        "Spatial heatmap of mean single-electrode burst duration (ms).",
    ),
    (
        re.compile(r"^5_FractSpikesInBursts_heatmap\.png$"),
        "Fraction of Spikes in Bursts",
        "Spatial heatmap of what fraction of each electrode's spikes "
        "occur inside a detected burst, versus isolated/tonic firing.",
    ),
    (
        re.compile(r"^6_ISIwithinBurst_heatmap\.png$"),
        "ISI Within Burst",
        "Spatial heatmap of the mean inter-spike interval (ms) between "
        "spikes within the same burst — smaller values mean tighter, "
        "more intense bursts.",
    ),
    (
        re.compile(r"^7_ISIoutsideBurst_heatmap\.png$"),
        "ISI Outside Burst",
        "Spatial heatmap of the mean inter-spike interval (ms) between "
        "spikes outside of bursts (baseline/tonic firing).",
    ),
    (
        re.compile(r"^8_BurstDetectionInfo\.png$"),
        "Burst Detection Overview",
        "Full raster vs. a raster restricted to spikes inside detected "
        "network bursts, plus an inter-spike-interval distribution — the "
        "main check that network burst detection is picking out genuine "
        "synchronous events rather than false positives.",
    ),
    (
        re.compile(r"^1_adjM(?P<lag>\d+)msConnectivityStats\.png$"),
        "Connectivity Stats ({lag} ms lag)",
        "Adjacency matrix heatmap of pairwise STTC values, plus bar "
        "charts of the max/mean correlation and histograms of node "
        "degree, node strength, and significant edge weight — at a "
        "{lag} ms STTC lag. The main check that functional connectivity "
        "was computed sensibly before deriving network metrics from it. "
        "(MEA-NAP docs, Step 4A Figure 1)",
    ),
    (
        re.compile(r"^2_MEA_NetworkPlot\.png$"),
        "Spatial Network Plot",
        "Functional connectivity network drawn at the electrodes' real "
        "spatial layout. Node size = node degree (number of significant "
        "connections); edges = significant functional connections; edge "
        "thickness = connection strength (STTC weight). (MEA-NAP docs, "
        "Step 4A Figure 2 — MATLAB additionally produces ‘scaled’ "
        "and ‘combined’ variants normalized across the whole "
        "dataset; this port renders the single per-recording version.)",
    ),
    (
        re.compile(r"^3_MEA_NetworkPlotNodedegreeBetweennesscentrality\.png$"),
        "Spatial Network Plot — Betweenness Centrality",
        "Same spatial network layout as the base network plot, but node "
        "color now encodes betweenness centrality — the proportion of "
        "shortest paths between any two other nodes that pass through "
        "this node. Highlights which electrodes act as the network's "
        "relay hubs. (MEA-NAP docs, Step 4A Figure 3)",
    ),
    (
        re.compile(r"^4_MEA_NetworkPlotNodedegreeParticipationcoefficient\.png$"),
        "Spatial Network Plot — Participation Coefficient",
        "Same spatial network layout as the base network plot, but node "
        "color now encodes participation coefficient (normalized) — how "
        "spread a node's connections are across different network modules. "
        "Values near 0 mean the node's edges stay within its own module; "
        "values near 1 mean they're evenly spread across modules. Module "
        "assignment is stochastic (consensus clustering) — expect "
        "run-to-run variation. (MEA-NAP docs, Step 4A Figure 4)",
    ),
    (
        re.compile(r"^5_MEA_NetworkPlotNodestrengthLocalefficiency\.png$"),
        "Spatial Network Plot — Local Efficiency",
        "Same spatial network layout, but node size now encodes node "
        "strength (sum of edge weights) instead of node degree — the one "
        "plot in this set that sizes by strength rather than degree, "
        "matching MATLAB exactly. Node color encodes local efficiency: how "
        "efficiently a node's immediate neighbors could still exchange "
        "information if that node were removed — a measure of local "
        "network resilience/redundancy around each electrode. (MEA-NAP "
        "docs, Step 4A Figure 5)",
    ),
    (
        re.compile(r"^9_adjM(?P<lag>\d+)msNodeCartography\.png$"),
        "Node Cartography ({lag} ms lag)",
        "Each node plotted by normalized participation coefficient (x — how "
        "spread its connections are across modules) vs. within-module "
        "degree z-score (y — how connected it is within its own module), "
        "colored by role: peripheral node, non-hub connector, non-hub "
        "kinless node, provincial hub, connector hub, or kinless hub. "
        "Boundary lines are fixed thresholds from Params. Module assignment "
        "and the participation-coefficient normalization are both "
        "stochastic — expect run-to-run variation. (MEA-NAP docs, Step 4A "
        "Figure 9)",
    ),
]

_DATA_FILE_DESCRIPTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r".*_spikes\.npz$"), "Detected spike times (per electrode, per detection method) and metadata, in NumPy .npz format."),
    (re.compile(r".*_adjM\.npz$"), "STTC adjacency matrices for this recording — one raw + one significance-thresholded array per lag value."),
    (re.compile(r"^ephys_results\.json$"), "All step 2 (firing rate + burst) metrics for every recording, in one JSON file."),
    (re.compile(r"^netmet_results\.json$"), "All step 4 (network) metrics for every recording and lag, in one JSON file."),
]


def describe_plot(filename: str) -> tuple[str, str] | None:
    """Returns (title, caption) for a known plot filename, else None."""
    for pattern, title_tmpl, caption_tmpl in _PLOT_PATTERNS:
        m = pattern.match(filename)
        if m:
            groups = m.groupdict()
            return title_tmpl.format(**groups), caption_tmpl.format(**groups)
    return None


def describe_data_file(filename: str) -> str | None:
    for pattern, desc in _DATA_FILE_DESCRIPTIONS:
        if pattern.match(filename):
            return desc
    return None


def describe_folder(name: str) -> str | None:
    return FOLDER_DESCRIPTIONS.get(name)


# ── Tree building ───────────────────────────────────────────────────────────

def _build_tree(dir_path: Path, root: Path) -> dict:
    children = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        entries = []

    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            child = _build_tree(entry, root)
            if child["children"] or FOLDER_DESCRIPTIONS.get(entry.name):
                children.append(child)
        elif entry.suffix.lower() in IMAGE_EXTENSIONS:
            described = describe_plot(entry.name)
            title, caption = described if described else (entry.stem, "")
            children.append({
                "type": "image",
                "name": entry.name,
                "path": str(entry.relative_to(root)).replace("\\", "/"),
                "title": title,
                "caption": caption,
            })
        elif entry.suffix.lower() in (".npz", ".json", ".csv", ".mat"):
            children.append({
                "type": "file",
                "name": entry.name,
                "path": str(entry.relative_to(root)).replace("\\", "/"),
                "caption": describe_data_file(entry.name) or "",
            })

    return {
        "type": "folder",
        "name": dir_path.name,
        "path": str(dir_path.relative_to(root)).replace("\\", "/") if dir_path != root else "",
        "description": describe_folder(dir_path.name) or "",
        "children": children,
    }


def generate_report(output_root: Path | str, out_path: Path | str | None = None) -> Path:
    """Build ``report.html`` for a MEA-NAP output folder. Returns its path."""
    output_root = Path(output_root)
    out_path = Path(out_path) if out_path else output_root / "report.html"

    tree = _build_tree(output_root, output_root)
    tree["name"] = output_root.name

    html = _HTML_TEMPLATE.replace("__TREE_JSON__", json.dumps(tree))
    html = html.replace("__TITLE__", f"MEA-NAP Output Report — {output_root.name}")
    out_path.write_text(html)
    return out_path


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #ffffff; --sidebar-bg: #f6f7f9; --border: #e2e4e8;
    --text: #1f2328; --muted: #6b7280; --accent: #2563eb; --card-bg: #ffffff;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
         color: var(--text); background: var(--bg); }
  #layout { display: flex; height: 100vh; }
  #sidebar { width: 320px; flex-shrink: 0; background: var(--sidebar-bg); border-right: 1px solid var(--border);
             overflow-y: auto; padding: 12px 8px; }
  #sidebar h1 { font-size: 14px; padding: 4px 8px 12px; margin: 0; color: var(--text); word-break: break-word; }
  #main { flex: 1; overflow-y: auto; padding: 24px 32px; }
  ul.tree { list-style: none; margin: 0; padding-left: 14px; }
  ul.tree.root { padding-left: 0; }
  .tree li { margin: 1px 0; }
  .node-label { display: flex; align-items: center; gap: 5px; padding: 4px 6px; border-radius: 6px;
                cursor: pointer; font-size: 13px; user-select: none; white-space: nowrap; }
  .node-label:hover { background: #eceef2; }
  .node-label.selected { background: var(--accent); color: white; }
  .node-label .caret { width: 12px; display: inline-block; color: var(--muted); font-size: 10px; }
  .node-label.selected .caret { color: white; }
  .node-label .icon { width: 16px; text-align: center; }
  .count { color: var(--muted); font-size: 11px; margin-left: auto; padding-left: 8px; }
  .node-label.selected .count { color: #dbeafe; }
  #breadcrumb { font-size: 13px; color: var(--muted); margin-bottom: 6px; }
  #folder-desc { font-size: 14px; color: var(--muted); margin: 0 0 20px; padding: 12px 16px;
                 background: #f6f7f9; border-radius: 8px; border-left: 3px solid var(--accent); max-width: 900px; }
  h2#main-title { margin: 0 0 4px; font-size: 20px; }
  .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
  .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
          display: flex; flex-direction: column; }
  .card img { width: 100%; display: block; cursor: zoom-in; background: #fafafa; border-bottom: 1px solid var(--border); }
  .card .card-body { padding: 10px 14px 14px; }
  .card .card-title { font-weight: 600; font-size: 13.5px; margin: 0 0 4px; }
  .card .card-caption { font-size: 12.5px; color: var(--muted); line-height: 1.45; margin: 0; }
  .filelist { font-size: 13px; }
  .filelist li { padding: 6px 0; border-bottom: 1px solid var(--border); }
  .filelist a { color: var(--accent); text-decoration: none; font-family: ui-monospace, monospace; font-size: 12.5px; }
  .filelist .file-caption { color: var(--muted); font-size: 12px; margin-top: 2px; }
  #lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.85); display: none;
              align-items: center; justify-content: center; z-index: 100; cursor: zoom-out; flex-direction: column; }
  #lightbox.open { display: flex; }
  #lightbox img { max-width: 92vw; max-height: 82vh; box-shadow: 0 10px 40px rgba(0,0,0,0.5); }
  #lightbox .lb-caption { color: #eee; max-width: 700px; text-align: center; margin-top: 16px; font-size: 14px; }
  .empty { color: var(--muted); font-size: 14px; }
</style>
</head>
<body>
<div id="layout">
  <div id="sidebar">
    <h1>__TITLE__</h1>
    <ul class="tree root" id="tree-root"></ul>
  </div>
  <div id="main">
    <div id="breadcrumb"></div>
    <h2 id="main-title">Select a folder</h2>
    <p id="folder-desc" style="display:none;"></p>
    <div id="content"></div>
  </div>
</div>
<div id="lightbox">
  <img id="lightbox-img" src="">
  <div class="lb-caption" id="lightbox-caption"></div>
</div>
<script>
const TREE = __TREE_JSON__;

function countImages(node) {
  if (node.type !== "folder") return node.type === "image" ? 1 : 0;
  return node.children.reduce((sum, c) => sum + countImages(c), 0);
}

function iconFor(node) {
  if (node.type === "folder") return "\u{1F4C1}";
  if (node.type === "image") return "\u{1F5BC}";
  return "\u{1F4C4}";
}

const treeRoot = document.getElementById("tree-root");
const mainTitle = document.getElementById("main-title");
const folderDesc = document.getElementById("folder-desc");
const breadcrumb = document.getElementById("breadcrumb");
const content = document.getElementById("content");
const NODE_REGISTRY = {}; // node.path -> {node, label, childUl}

function buildTreeDOM(node, container, path) {
  const li = document.createElement("li");
  const label = document.createElement("div");
  label.className = "node-label";

  const caret = document.createElement("span");
  caret.className = "caret";
  const hasChildren = node.type === "folder" && node.children.some(c => c.type === "folder");
  caret.textContent = hasChildren ? "▶" : "";
  label.appendChild(caret);

  const icon = document.createElement("span");
  icon.className = "icon";
  icon.textContent = iconFor(node);
  label.appendChild(icon);

  const text = document.createElement("span");
  text.textContent = node.name;
  label.appendChild(text);

  if (node.type === "folder") {
    const n = countImages(node);
    if (n > 0) {
      const count = document.createElement("span");
      count.className = "count";
      count.textContent = n;
      label.appendChild(count);
    }
  }

  li.appendChild(label);
  container.appendChild(li);

  let childUl = null;
  if (node.type === "folder") {
    childUl = document.createElement("ul");
    childUl.className = "tree";
    childUl.style.display = "none";
    for (const child of node.children) {
      if (child.type === "folder") buildTreeDOM(child, childUl, path.concat(node.name));
    }
    li.appendChild(childUl);
  }

  function setOpen(open) {
    if (!childUl || !hasChildren) return;
    childUl.style.display = open ? "block" : "none";
    caret.textContent = open ? "▼" : "▶";
  }

  label.addEventListener("click", (e) => {
    e.stopPropagation();
    if (node.type === "folder") {
      setOpen(childUl.style.display === "none");
      selectFolder(node, path.concat(node.name), label);
      history.replaceState(null, "", "#" + encodeURIComponent(node.path));
    }
  });

  if (node.type === "folder") {
    NODE_REGISTRY[node.path] = { node, label, path: path.concat(node.name), setOpen };
  }

  return li;
}

let selectedLabel = null;
function selectFolder(node, path, labelEl) {
  if (selectedLabel) selectedLabel.classList.remove("selected");
  labelEl.classList.add("selected");
  selectedLabel = labelEl;

  breadcrumb.textContent = path.join(" / ");
  mainTitle.textContent = node.name;

  if (node.description) {
    folderDesc.textContent = node.description;
    folderDesc.style.display = "block";
  } else {
    folderDesc.style.display = "none";
  }

  content.innerHTML = "";
  const images = node.children.filter(c => c.type === "image");
  const files = node.children.filter(c => c.type === "file");
  const subfolders = node.children.filter(c => c.type === "folder");

  if (images.length === 0 && files.length === 0 && subfolders.length > 0) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "No plots directly in this folder — expand it in the sidebar to browse subfolders.";
    content.appendChild(p);
  }

  if (images.length > 0) {
    const gallery = document.createElement("div");
    gallery.className = "gallery";
    for (const img of images) {
      const card = document.createElement("div");
      card.className = "card";
      const imEl = document.createElement("img");
      imEl.src = img.path;
      imEl.loading = "lazy";
      imEl.addEventListener("click", () => openLightbox(img));
      card.appendChild(imEl);
      const body = document.createElement("div");
      body.className = "card-body";
      const title = document.createElement("p");
      title.className = "card-title";
      title.textContent = img.title;
      body.appendChild(title);
      if (img.caption) {
        const cap = document.createElement("p");
        cap.className = "card-caption";
        cap.textContent = img.caption;
        body.appendChild(cap);
      }
      card.appendChild(body);
      gallery.appendChild(card);
    }
    content.appendChild(gallery);
  }

  if (files.length > 0) {
    const h3 = document.createElement("h3");
    h3.textContent = "Data files";
    h3.style.fontSize = "14px";
    h3.style.marginTop = images.length ? "28px" : "0";
    content.appendChild(h3);
    const ul = document.createElement("ul");
    ul.className = "filelist";
    for (const f of files) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = f.path;
      a.textContent = f.name;
      li.appendChild(a);
      if (f.caption) {
        const cap = document.createElement("div");
        cap.className = "file-caption";
        cap.textContent = f.caption;
        li.appendChild(cap);
      }
      ul.appendChild(li);
    }
    content.appendChild(ul);
  }
}

const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const lightboxCaption = document.getElementById("lightbox-caption");
function openLightbox(img) {
  lightboxImg.src = img.path;
  lightboxCaption.textContent = img.title + (img.caption ? "  —  " + img.caption : "");
  lightbox.classList.add("open");
}
lightbox.addEventListener("click", () => lightbox.classList.remove("open"));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") lightbox.classList.remove("open"); });

buildTreeDOM(TREE, treeRoot, []);

function openHashPath() {
  const target = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (target && NODE_REGISTRY[target]) {
    // Expand every ancestor folder (including the root), then select the target.
    if (NODE_REGISTRY[""]) NODE_REGISTRY[""].setOpen(true);
    const parts = target.split("/");
    for (let i = 1; i <= parts.length; i++) {
      const ancestorPath = parts.slice(0, i).join("/");
      const entry = NODE_REGISTRY[ancestorPath];
      if (entry) entry.setOpen(true);
    }
    const entry = NODE_REGISTRY[target];
    entry.label.scrollIntoView({ block: "center" });
    selectFolder(entry.node, entry.path, entry.label);
    return true;
  }
  return false;
}

// Deep-link support: opening report.html#Some/Sub/Folder auto-navigates
// there (path segments match each folder's location relative to the report
// root, joined by "/" — matches the "path" field embedded in TREE).
if (!openHashPath() && treeRoot.firstChild) {
  treeRoot.firstChild.querySelector(".node-label").click();
}
window.addEventListener("hashchange", openHashPath);
</script>
</body>
</html>
"""
