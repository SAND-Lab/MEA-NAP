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
    "2A_IndividualNeuronalAnalysis": "Per-recording firing rate and burst-detection plots. For a CAT-NAP (calcium imaging) run, the per-cell raw/denoised fluorescence trace figures.",
    "2B_GroupComparisons": "Activity metrics pooled across the whole batch and compared between experimental groups and ages. For a CAT-NAP run these are calcium event rate, amplitude, duration and area instead of spike firing rate and bursts.",
    "3_EdgeThresholdingCheck": "Step 3 — functional connectivity. Diagnostic plots for the STTC computation and significance thresholding (not yet populated by the Python port's step 3).",
    "4_NetworkActivity": "Step 4 — network activity. Graph-theoretic metrics (node degree, clustering, efficiency, centrality, ...) computed from step 3's thresholded adjacency matrices.",
    "4A_IndividualNetworkAnalysis": "Per-recording, per-lag network plots and connectivity statistics.",
    "4B_GroupComparisons": "Network metrics pooled across the whole batch and compared between experimental groups and ages, one sub-folder per STTC lag.",
    "ExperimentMatFiles": "Per-recording adjacency matrices (STTC, raw + significance-thresholded) saved as .npz, one file per recording.",
    # Comparison sub-folders (shared by the ephys and CAT-NAP paths).
    "1_NodeByGroup": "Node-level metrics compared between experimental groups — one subplot per group, x-axis = age. Every node of every recording contributes a point.",
    "2_NodeByAge": "The same node-level metrics, transposed: one subplot per age, x-axis = experimental group.",
    "3_RecordingsByGroup": "Recording-level (whole-network / whole-culture) metrics compared between experimental groups — one subplot per group, x-axis = age.",
    "4_RecordingsByAge": "The same recording-level metrics, transposed: one subplot per age, x-axis = experimental group.",
    "5_GraphMetricsByLag": "How each network metric varies with the STTC lag used to build the adjacency matrix — a sanity check that conclusions aren't an artefact of one lag choice.",
    "6_NodeCartographyByLag": "Proportion of nodes in each cartography role, plotted against age, one figure per lag.",
    "7_DensityLandscape": "The pooled participation-coefficient / within-module-z-score landscape used to place the node-cartography role boundaries for this batch.",
    "8_CellTypeSubnetworks": "CAT-NAP only. Cell-type subnetwork metrics compared across experimental groups and ages, one file per (metric, cell type). 'Whole network' appears as one of the cell types, as the reference to read the others against.",
    "cellTypeSubnetworks": "CAT-NAP only. This recording's network split by putative cell type (from its immunohistochemistry spreadsheet): induced subgraphs per cell type, whole-network node metrics split by type, and within- vs between-type edge mixing. Each cell type also gets its own sub-folder holding the complete step-4A figure set for its induced subgraph.",
    "5_CellTypeComposition": "CAT-NAP only. How many cells of each type each recording contained, and how many of them were active — a result in its own right, and a check on whether downstream differences between groups are compositional rather than functional.",
    "ByCellType": "The same per-cell activity metrics as the parent folder, split by cell type: paired half-violins at each age, within each experimental group.",
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
        "The boundary lines are placed from the batch's own pooled PC/Z "
        "landscape when auto-set cartography boundaries is on (the default), "
        "and are the fixed Params thresholds otherwise. Module assignment "
        "and the participation-coefficient normalization are both "
        "stochastic — expect run-to-run variation. (MEA-NAP docs, Step 4A "
        "Figure 9)",
    ),
    # ── CAT-NAP (calcium imaging) ──────────────────────────────────────────
    (
        re.compile(r"^unit_(?P<roi>\d+)_2ptraces\.png$"),
        "Calcium Traces — ROI {roi}",
        "Three panels for one suite2p cell: raw fluorescence, the raw trace "
        "min-max scaled over the denoised trace (to check the denoising "
        "tracked the real signal), and the denoised trace with detected "
        "event onsets marked. The first check to make before trusting any "
        "downstream CAT-NAP result — if the event markers don't sit on real "
        "transients, retune the denoising threshold.",
    ),
    (
        re.compile(r"^1_CellTypeNetwork\.png$"),
        "Network by Cell Type",
        "The whole functional network with nodes drawn at their suite2p cell "
        "centroids and coloured by putative cell type. Within-type edges are "
        "drawn over pale between-type ones, so type-specific wiring is "
        "visible by eye.",
    ),
    (
        re.compile(r"^2_SubnetworkGraphs\.png$"),
        "Induced Subgraph per Cell Type",
        "One panel per cell type showing only that type's nodes and the "
        "edges among them, on shared axes. These are the subgraphs whose "
        "metrics the subnetwork CSVs report.",
    ),
    (
        re.compile(r"^3_NodeMetricsByCellType\.png$"),
        "Whole-Network Node Metrics by Cell Type",
        "The graph is left intact and every node is simply labelled by its "
        "cell type, then the node-level metric distributions are compared. "
        "Answers whether one cell type is more hub-like within the whole "
        "network — a different question from the induced-subgraph metrics, "
        "and usually the more interesting one.",
    ),
    (
        re.compile(r"^4_SubnetworkMetrics\.png$"),
        "Metrics of Each Cell-Type Subnetwork",
        "Graph-level metrics of each induced subgraph, against the whole "
        "network. Read these alongside each group's node count, annotated on "
        "the figure: density and small-worldness are size-dependent, so two "
        "cell types with very different cell counts are not directly "
        "comparable.",
    ),
    (
        re.compile(r"^5_EdgeMixing\.png$"),
        "Connectivity Within and Between Cell Types",
        "Cell type x cell type heatmaps of edge density and mean edge "
        "weight. The diagonal is within-type connectivity, the off-diagonal "
        "between-type — showing whether cell types wire preferentially to "
        "their own kind.",
    ),
    (
        re.compile(r"^ZandPC_scatter_with_kmeans_boundaries_\.png$"),
        "Pooled Cartography Landscape",
        "Participation coefficient vs. within-module degree z-score pooled "
        "over every recording in the batch, with the six node-cartography "
        "role boundaries placed where this dataset's nodes actually cluster "
        "rather than at fixed defaults. These boundaries are what the "
        "per-recording cartography plots and the NCpn columns in the CSVs "
        "use.",
    ),
    # ── Batch comparison half-violins (both pipelines) ─────────────────────
    # Generic: the metric name is whatever precedes the suffix. For the
    # cell-type subnetwork figures that token is "<metric>_<cell type>".
    (
        re.compile(r"^(?P<metric>.+)_byGroup_node\.png$"),
        "{metric} — by group (nodes)",
        "Half-violin distribution of this node-level metric, one subplot per "
        "experimental group with age along the x-axis. Every node of every "
        "recording contributes a point; the black dot and bar are the mean "
        "and its standard error.",
    ),
    (
        re.compile(r"^(?P<metric>.+)_byDIV_node\.png$"),
        "{metric} — by age (nodes)",
        "The same node-level distribution transposed: one subplot per age, "
        "experimental groups along the x-axis. Use this layout to read "
        "group differences at a fixed age.",
    ),
    (
        re.compile(r"^(?P<metric>.+)_byGroup\.png$"),
        "{metric} — by group",
        "Half-violin distribution of this recording-level metric, one "
        "subplot per experimental group with age along the x-axis. One point "
        "per recording; the black dot and bar are the mean and its standard "
        "error.",
    ),
    (
        re.compile(r"^(?P<metric>.+)_byDIV\.png$"),
        "{metric} — by age",
        "The same recording-level distribution transposed: one subplot per "
        "age, experimental groups along the x-axis.",
    ),
    (
        re.compile(r"^12_MeanImageAndNetwork\.png$"),
        "Field of View and Network",
        "CAT-NAP. Left: the imaged field (suite2p's mean projection). Right: "
        "the network derived from it, on identical axes — a position on one "
        "panel is the same position on the other. Use it to check that nodes "
        "sit on real somata before trusting anything downstream. Shown side by "
        "side rather than overlaid because a few hundred nodes and a dense "
        "edge set cover the image completely.",
    ),
    # ── Remaining shared step-4A figures ───────────────────────────────────
    (
        re.compile(r"^10_.*Averagecontrollability\.png$"),
        "Spatial Network Plot — Average Controllability",
        "Node color encodes average controllability: how easily that node "
        "could steer the network into many nearby states if driven. High "
        "values mark nodes well placed to push the network around locally.",
    ),
    (
        re.compile(r"^11_.*Modalcontrollability\.png$"),
        "Spatial Network Plot — Modal Controllability",
        "Node color encodes modal controllability: how well that node can "
        "drive the network into distant, hard-to-reach states. Tends to be "
        "high where average controllability is low.",
    ),
    (
        re.compile(r"^6_circular_NetworkPlotNodedegreeModule\.png$"),
        "Circular Network Plot — Modules",
        "The network drawn on a circle with nodes grouped by the module "
        "consensus clustering assigned them to, sized by node degree. Makes "
        "the modular structure legible where the spatial layout is too dense "
        "to read. Module assignment is stochastic — expect run-to-run "
        "variation.",
    ),
    (
        re.compile(r"^9_circular_NetworkPlotNodeCartography\.png$"),
        "Circular Network Plot — Cartography Roles",
        "The same circular layout with nodes coloured by their cartography "
        "role, so hub nodes and the edges between them can be picked out "
        "directly.",
    ),
    (
        re.compile(r"^7_adjM(?P<lag>\d+)msGraphMetricsByNode\.png$"),
        "Graph Metrics by Node ({lag} ms lag)",
        "Every per-node metric — degree, mean edge weight, strength, "
        "within-module z-score, local efficiency, participation coefficient, "
        "betweenness — plotted per node in one panel set, for spotting "
        "outlier nodes and how the metrics relate to each other.",
    ),
    (
        re.compile(r"^(?P<n>\d+)_scaled_(?P<rest>.+)\.png$"),
        "Spatial Network Plot {n} — scaled to the whole batch",
        "The same network as the matching un-scaled figure, but node size, "
        "node colour and edge width are scaled to the pooled range of every "
        "recording in the batch rather than this recording's own range. This "
        "is the version to compare across recordings; the un-scaled one shows "
        "this recording's internal structure best.",
    ),
    (
        re.compile(r"^(?P<n>\d+)_combined_MEA_NetworkPlot(?P<rest>.*)\.png$"),
        "Spatial Network Plot {n} — recording vs batch scaling",
        "The recording-scaled and batch-scaled versions of the same network "
        "side by side, so the effect of the scaling choice is visible at a "
        "glance.",
    ),
]

# Patterns that only make sense inside a particular folder — bare metric names
# like "Dens.png" would be far too greedy as a global pattern. Keyed by the
# containing folder's name; checked before the global patterns above.
_FOLDER_PLOT_PATTERNS: dict[str, list[tuple[re.Pattern, str, str]]] = {
    "5_GraphMetricsByLag": [(
        re.compile(r"^(?P<metric>.+)\.png$"),
        "{metric} vs. STTC lag",
        "This network metric plotted against the STTC lag used to build the "
        "adjacency matrix, one line per experimental group. A conclusion that "
        "holds at every lag is robust; one that appears at a single lag is "
        "probably an artefact of that choice.",
    )],
    "5_CellTypeComposition": [(
        re.compile(r"^(?P<metric>.+)_by(?P<axis>Group|DIV)\.png$"),
        "{metric} — by {axis}",
        "Cell-type composition per recording, with one violin per cell type at "
        "each position. Read alongside the metric comparisons: a group that "
        "simply contains more inhibitory cells will differ downstream for "
        "compositional reasons.",
    )],
    "6_NodeCartographyByLag": [(
        re.compile(r"^NodeCartography(?P<lag>\d+)mslag\.png$"),
        "Cartography Role Proportions ({lag} ms lag)",
        "The proportion of nodes in each of the six cartography roles, "
        "plotted against age, one line per role. Shows how network "
        "organisation — peripheral nodes giving way to hubs, say — shifts as "
        "the culture matures.",
    )],
}

_DATA_FILE_DESCRIPTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r".*_spikes\.npz$"), "Detected spike times (per electrode, per detection method) and metadata, in NumPy .npz format."),
    (re.compile(r".*_adjM\.npz$"), "STTC adjacency matrices for this recording — one raw + one significance-thresholded array per lag value."),
    (re.compile(r"^ephys_results\.json$"), "All step 2 (firing rate + burst) metrics for every recording, in one JSON file."),
    (re.compile(r"^netmet_results\.json$"), "All step 4 (network) metrics for every recording and lag, in one JSON file."),
    (re.compile(r"^NetworkActivity_RecordingLevel\.csv$"), "One row per recording per lag: every whole-network metric (density, efficiency, small-worldness, modularity, cartography role proportions, ...). The main table for statistics across groups."),
    (re.compile(r"^NetworkActivity_NodeLevel\.csv$"), "One row per active node per recording per lag: node degree, strength, participation coefficient, betweenness, local efficiency and the rest. ``Channel`` is the real electrode ID (or suite2p ROI id for CAT-NAP)."),
    (re.compile(r"^TwoPhotonActivity_RecordingLevel\.csv$"), "CAT-NAP. One row per recording: calcium event-rate summaries, active-cell count, and mean event amplitude / duration / area."),
    (re.compile(r"^TwoPhotonActivity_NodeLevel\.csv$"), "CAT-NAP. One row per cell per recording: event rate, mean inter-event interval, and mean event amplitude, duration, area and total area. ``Channel`` is the suite2p ROI id."),
    (re.compile(r"^Subnetwork_RecordingLevel\.csv$"), "CAT-NAP. One row per recording x lag x cell type: graph metrics of that cell type's induced subgraph, plus ``aN`` (its node count — needed to interpret the size-dependent metrics)."),
    (re.compile(r"^Subnetwork_NodeLevel\.csv$"), "CAT-NAP. One row per recording x lag x node x cell type: whole-network node metrics labelled by type, plus each node's within-group strength fraction. Long format — a cell positive for two markers appears once per group."),
    (re.compile(r"^Subnetwork_EdgeMix\.csv$"), "CAT-NAP. One row per recording x lag x cell-type pair: edge density and mean weight within and between types."),
    (re.compile(r"^step_durations\.json$"), "Wall-clock seconds spent in each pipeline step, for performance comparison."),
]


def describe_plot(filename: str, folder: str | None = None) -> tuple[str, str] | None:
    """Returns (title, caption) for a known plot filename, else None.

    ``folder`` is the name of the directory holding the file. Some figures are
    named only for their metric (``Dens.png``) and are identifiable solely by
    where they sit, so those patterns are folder-scoped and take precedence.
    """
    patterns = _FOLDER_PLOT_PATTERNS.get(folder or "", []) + _PLOT_PATTERNS
    for pattern, title_tmpl, caption_tmpl in patterns:
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


# ── CSV previews ────────────────────────────────────────────────────────────
# The report has to work when opened straight off disk, and a page on a
# ``file://`` origin cannot fetch neighbouring files (browsers treat each one as
# an opaque origin). So a preview cannot be loaded on demand in the viewer — the
# first rows are read here and embedded in the page. Hence the caps: enough to
# see a table's shape and sanity-check its values, not enough to bloat the HTML.

#: Data rows embedded per CSV.
CSV_PREVIEW_ROWS = 20
#: Columns embedded; wide tables are cut with a note rather than dropped.
CSV_PREVIEW_MAX_COLS = 40
#: Longest cell text kept, so one runaway field can't dominate the payload.
CSV_PREVIEW_CELL_CHARS = 40
#: Stop counting rows past this, to bound the cost on a pathological file.
_CSV_COUNT_LIMIT = 500_000


def csv_preview(path: Path | str) -> dict | None:
    """First rows of a CSV, as embeddable JSON. ``None`` if it can't be read.

    Values are kept as the literal text in the file — no parsing or
    reformatting — so what the preview shows is what a downstream tool will
    read.
    """
    import csv

    path = Path(path)
    try:
        size = path.stat().st_size
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                return {"columns": [], "rows": [], "totalRows": 0, "totalCols": 0,
                        "truncatedCols": False, "sizeBytes": size}

            rows: list[list[str]] = []
            total = 0
            for row in reader:
                total += 1
                if len(rows) < CSV_PREVIEW_ROWS:
                    rows.append(row)
                elif total >= _CSV_COUNT_LIMIT:
                    break
    except Exception:
        return None

    def _clip(cells: list[str]) -> list[str]:
        out = []
        for cell in cells[:CSV_PREVIEW_MAX_COLS]:
            text = str(cell)
            out.append(text if len(text) <= CSV_PREVIEW_CELL_CHARS
                       else text[: CSV_PREVIEW_CELL_CHARS - 1] + "…")
        return out

    return {
        "columns": _clip(header),
        "rows": [_clip(r) for r in rows],
        "totalRows": total,
        "totalCols": len(header),
        "truncatedCols": len(header) > CSV_PREVIEW_MAX_COLS,
        "countCapped": total >= _CSV_COUNT_LIMIT,
        "sizeBytes": size,
    }


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
            described = describe_plot(entry.name, dir_path.name)
            title, caption = described if described else (entry.stem, "")
            children.append({
                "type": "image",
                "name": entry.name,
                "path": str(entry.relative_to(root)).replace("\\", "/"),
                "title": title,
                "caption": caption,
            })
        elif entry.suffix.lower() in (".npz", ".json", ".csv", ".mat"):
            node = {
                "type": "file",
                "name": entry.name,
                "path": str(entry.relative_to(root)).replace("\\", "/"),
                "caption": describe_data_file(entry.name) or "",
            }
            if entry.suffix.lower() == ".csv":
                preview = csv_preview(entry)
                if preview is not None:
                    node["preview"] = preview
            children.append(node)

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

    # Escape "<" so no value in the tree — a CSV cell, a filename — can close
    # the <script> block it is embedded in. \u003c is still "<" to JSON.parse.
    tree_json = json.dumps(tree).replace("<", "\\u003c")
    html = _HTML_TEMPLATE.replace("__TREE_JSON__", tree_json)
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
  .csv-toggle { margin-top: 6px; font-size: 11.5px; padding: 3px 9px; cursor: pointer;
                border: 1px solid var(--border); border-radius: 999px; background: #fff;
                color: var(--accent); font-family: inherit; }
  .csv-toggle:hover { background: #f2f5fb; }
  .csv-panel { display: none; margin-top: 8px; }
  .csv-panel.open { display: block; }
  .csv-scroll { overflow: auto; max-height: 340px; border: 1px solid var(--border); border-radius: 8px; }
  table.csv { border-collapse: collapse; font-family: ui-monospace, monospace; font-size: 11.5px;
              white-space: nowrap; }
  table.csv th, table.csv td { padding: 4px 10px; border-bottom: 1px solid var(--border); text-align: left; }
  table.csv th { position: sticky; top: 0; background: var(--sidebar-bg); font-weight: 600;
                 border-bottom: 1px solid var(--border); z-index: 1; }
  table.csv tbody tr:nth-child(even) { background: #fafbfc; }
  table.csv td.num { text-align: right; }
  .csv-meta { color: var(--muted); font-size: 11.5px; margin-top: 6px; }
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
      if (f.preview) li.appendChild(buildCsvPreview(f));
      ul.appendChild(li);
    }
    content.appendChild(ul);
  }
}

// ── CSV preview ───────────────────────────────────────────────────────────
// The rows are embedded in this page rather than fetched: a report opened from
// disk is on a file:// origin, and browsers block those from reading sibling
// files. So this renders what generate_report() already captured.
function humanSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

function buildCsvPreview(f) {
  const p = f.preview;
  const wrap = document.createElement("div");

  const btn = document.createElement("button");
  btn.className = "csv-toggle";
  const panel = document.createElement("div");
  panel.className = "csv-panel";

  const label = (open) =>
    (open ? "▾ Hide preview" : "▸ Preview") +
    (p.totalRows ? "  (" + p.totalRows.toLocaleString() + " rows)" : "  (empty)");
  btn.textContent = label(false);
  btn.addEventListener("click", () => {
    const open = panel.classList.toggle("open");
    btn.textContent = label(open);
    if (open && !panel.dataset.built) { renderCsvTable(panel, p); panel.dataset.built = "1"; }
  });

  wrap.appendChild(btn);
  wrap.appendChild(panel);
  return wrap;
}

function renderCsvTable(panel, p) {
  if (!p.columns.length) {
    const empty = document.createElement("div");
    empty.className = "csv-meta";
    empty.textContent = "This file has no columns.";
    panel.appendChild(empty);
    return;
  }
  const scroll = document.createElement("div");
  scroll.className = "csv-scroll";
  const table = document.createElement("table");
  table.className = "csv";

  const thead = document.createElement("thead");
  const hrow = document.createElement("tr");
  for (const col of p.columns) {
    const th = document.createElement("th");
    th.textContent = col;
    hrow.appendChild(th);
  }
  thead.appendChild(hrow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of p.rows) {
    const tr = document.createElement("tr");
    for (let i = 0; i < p.columns.length; i++) {
      const td = document.createElement("td");
      const val = row[i] === undefined ? "" : row[i];
      td.textContent = val;
      // Right-align anything that reads as a number, so columns line up.
      if (val !== "" && !isNaN(val)) td.className = "num";
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  scroll.appendChild(table);
  panel.appendChild(scroll);

  const bits = [];
  if (p.rows.length < p.totalRows)
    bits.push("first " + p.rows.length + " of " +
              p.totalRows.toLocaleString() + (p.countCapped ? "+" : "") + " rows");
  else
    bits.push(p.totalRows.toLocaleString() + " rows");
  bits.push(p.totalCols + " columns" + (p.truncatedCols ? " (first " + p.columns.length + " shown)" : ""));
  bits.push(humanSize(p.sizeBytes));
  const meta = document.createElement("div");
  meta.className = "csv-meta";
  meta.textContent = "Showing " + bits.join("  ·  ") + ". Open the file for the full table.";
  panel.appendChild(meta);
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
