#!/usr/bin/env python3
"""Generate a side-by-side MATLAB-vs-Python plot parity report for MEA-NAP.

Walks a MATLAB output tree and a Python output tree, pairs the plots each
pipeline produced (handling the two pipelines' different file/folder naming
conventions), and emits a single self-contained HTML report that shows every
plot from both pipelines side by side. Missing cells make parity gaps obvious.

Usage:
    python python/plot_parity_report.py \
        --matlab OutputData24Dec2025 \
        --python OutputData_Python \
        --out plot_parity_report.html

Re-run after each plotting fix to track progress. Image tags reference the
output files by path *relative to the report's location*, so keep the report at
the repo root (default) or pass --out somewhere the relative paths still resolve.
"""
from __future__ import annotations

import argparse
import html
import os
import re
from collections import defaultdict
from pathlib import Path

# --- MATLAB readable label -> Python metric code -----------------------------
# MATLAB names group-comparison plots "<N>_<readable label>_by<Grouping>.png";
# Python names them "<code>_by<Grouping>[_node].png". This maps the readable
# label to the code so the two can be paired. Derived from PlotNetMet.m /
# PlotEphysStats.m ordering and src/meanap/pipeline/plotting_step{2,4}.py.
LABEL2CODE = {
    # step 2 - recording level (ephys)
    "number of active electrodes": "numActiveElec",
    "mean firing rate (Hz)": "FRmean",
    "median firing rate (Hz)": "FRmedian",
    "network burst rate (per minute)": "NBurstRate",
    "mean number of channels involved in network bursts": "meanNumChansInvolvedInNbursts",
    "mean network burst length (s)": "meanNBstLengthS",
    "mean ISI within network burst (ms)": "meanISIWithinNbursts_ms",
    "mean ISI outside network bursts (ms)": "meanISIoutsideNbursts_ms",
    "coefficient of variation of inter network burst intervals": "CVofINBI",
    "fraction of bursts in network bursts": "fracInNburst",
    "Single-electrode burst rate (per minute)": "channelAveBurstRate",
    "Single-electrode average burst duration (ms)": "channelAveBurstDur",
    "Single-electrode average ISI within burst (ms)": "channelAveISIwithinBurst",
    "Single-electrode average ISI outside burst (ms)": "channelAveISIoutsideBurst",
    "Mean fraction of spikes in bursts per electrode": "channelAveFracSpikesInBursts",
    # step 2 - node level (ephys)
    "mean_firing_rate_node": "FR",
    "mean_firing_rate_active_node": "FRactive",
    "Unit burst rate (per minute)": "channelBurstRate",
    "Unit within-burst firing rate (Hz)": "channelWithinBurstFr",
    "Unit burst duration (ms)": "channelBurstDur",
    "Unit ISI within burst (ms)": "channelISIwithinBurst",
    "Unit ISI outside burst (ms)": "channeISIoutsideBurst",
    "Unit fraction of spikes in bursts": "channelFracSpikesInBursts",
    # step 4 - recording level (network)
    "network size": "aN",
    "density": "Dens",
    "Node degree mean": "NDmean",
    "Top 25% node degree": "NDtop25",
    "Significant edge weight mean": "sigEdgesMean",
    "Top 10% edge weight mean": "sigEdgesTop10",
    "Node strength mean": "NSmean",
    "Local efficiency mean": "ElocMean",
    "clustering coefficient": "CC",
    "number of modules": "nMod",
    "modularity score": "Q",
    "Percentage within-module z-score greater than 0": "percentZscoreGreaterThanZero",
    "Percentage within-module z-score less than 0": "percentZscoreLessThanZero",
    "mean path length": "PL",
    "Participant coefficient (PC) mean": "PCmean",
    "Bottom 10% PC": "PCmeanBottom10",
    "Top 10% PC": "PCmeanTop10",
    "global efficiency": "Eglob",
    "NC1PeripheralNodes": "NCpn1",
    "NC2NonhubConnectors": "NCpn2",
    "NC3NonhubKinless": "NCpn3",
    "NC4ProvincialHubs": "NCpn4",
    "NC5ConnectorHubs": "NCpn5",
    "NC6KinlessHubs": "NCpn6",
    "small worldness sigma": "SW",
    "small worldness omega": "SWw",
    "Mean average controllability": "aveControlMean",
    "Mean modal controllability": "modalControlMean",
    "Num NMF components": "num_nnmf_components",
    "nNMF div network size": "nComponentsRelNS",
    "Effective rank": "effRank",
    # step 4 - node level (network)
    "node degree": "ND",
    "edge weight": "MEW",
    "node strength": "NS",
    "local efficiency": "Eloc",
    "within-module degree z-score": "Z",
    "betweenness centrality": "BC",
    "participation coefficient": "PC",
    "Average Controllability": "aveControl",
    "Modal Controllability": "modalControl",
}

BY_SUFFIX = re.compile(r"_by(Group|Age|DIV)(_node)?$")
NUM_PREFIX = re.compile(r"^\d+_")
LAG_PY = re.compile(r"Lag(\d+)ms")


def canon_path(rel: str) -> str:
    """Normalise a relative path so MATLAB and Python trees line up.

    Python uses 'Lag10ms' folder tokens where MATLAB uses '10mslag'.
    """
    return LAG_PY.sub(lambda m: f"{m.group(1)}mslag", rel)


def metric_key(stem: str, is_matlab: bool, is_group: bool) -> str:
    """Reduce a filename stem to a pipeline-agnostic key for pairing.

    Only group-comparison plots (those under a 2B/4B *_GroupComparisons folder)
    get the numeric-prefix strip + MATLAB-label->code translation, because only
    there do the two pipelines diverge: MATLAB writes "<N>_<readable>_by<Grp>",
    Python writes "<code>_by<Grp>[_node]". MATLAB is also inconsistent — the
    ByAge folders drop the "_by<Grp>" suffix — so we key on the folder, not the
    suffix. Individual / spike / edge-threshold plots share identical filenames
    across pipelines, so their stems are left untouched and pair verbatim.
    """
    if not is_group:
        return stem
    stem = BY_SUFFIX.sub("", stem)
    if is_matlab:
        readable = NUM_PREFIX.sub("", stem)
        return LABEL2CODE.get(readable, readable)
    return stem


def pair_key(rel: str, is_matlab: bool) -> str:
    """Full pairing key: canonical directory + metric key."""
    rel = canon_path(rel)
    d, name = os.path.split(rel)
    stem = name[:-4] if name.lower().endswith(".png") else name
    is_group = "GroupComparisons" in d
    return f"{d}/{metric_key(stem, is_matlab, is_group)}"


def section_of(key: str) -> str:
    """Human-readable section for grouping/navigation."""
    if key.startswith("./1_SpikeDetection") or key.startswith("1_SpikeDetection"):
        return "1 · Spike Detection"
    if "2A_IndividualNeuronalAnalysis" in key:
        return "2A · Neuronal Activity — Individual"
    if "2B_GroupComparisons" in key:
        return "2B · Neuronal Activity — Group"
    if "3_EdgeThresholdingCheck" in key:
        return "3 · Edge Thresholding Check"
    if "4A_IndividualNetworkAnalysis" in key:
        return "4A · Network Activity — Individual"
    if "4B_GroupComparisons" in key:
        return "4B · Network Activity — Group"
    return "Other"


SECTION_ORDER = [
    "1 · Spike Detection",
    "2A · Neuronal Activity — Individual",
    "2B · Neuronal Activity — Group",
    "3 · Edge Thresholding Check",
    "4A · Network Activity — Individual",
    "4B · Network Activity — Group",
    "Other",
]


def collect(root: Path, is_matlab: bool) -> dict[str, str]:
    """Map pairing key -> path relative to `root` for every PNG under root."""
    out: dict[str, str] = {}
    for p in root.rglob("*.png"):
        rel = os.path.relpath(p, root)
        out[pair_key("./" + rel, is_matlab)] = rel
    return out


def rel_from_report(report_dir: Path, root: Path, rel: str) -> str:
    return os.path.relpath(root / rel, report_dir).replace(os.sep, "/")


def build_report(matlab_root: Path, python_root: Path, out_path: Path) -> dict:
    mat = collect(matlab_root, is_matlab=True)
    py = collect(python_root, is_matlab=False)
    report_dir = out_path.parent.resolve()

    all_keys = sorted(set(mat) | set(py))
    sections: dict[str, list] = defaultdict(list)
    for k in all_keys:
        sections[section_of(k)].append(k)

    # per-section stats
    stats = {}
    for sec, keys in sections.items():
        both = sum(1 for k in keys if k in mat and k in py)
        mat_only = sum(1 for k in keys if k in mat and k not in py)
        py_only = sum(1 for k in keys if k in py and k not in mat)
        stats[sec] = (both, mat_only, py_only, len(keys))

    tot_both = sum(s[0] for s in stats.values())
    tot_mat_only = sum(s[1] for s in stats.values())
    tot_py_only = sum(s[2] for s in stats.values())

    def img_cell(root, rel, side):
        if rel is None:
            return f'<div class="cell missing"><span>— no {side} plot —</span></div>'
        src = html.escape(rel_from_report(report_dir, root, rel))
        title = html.escape(rel)
        return (
            f'<div class="cell"><a href="{src}" target="_blank">'
            f'<img loading="lazy" src="{src}" title="{title}"></a>'
            f'<div class="fname">{title}</div></div>'
        )

    parts = []
    parts.append(HEADER)
    parts.append(f"""
    <header>
      <h1>MEA-NAP plot parity — MATLAB vs Python</h1>
      <p class="paths"><b>MATLAB:</b> {html.escape(str(matlab_root))} &nbsp;|&nbsp;
         <b>Python:</b> {html.escape(str(python_root))}</p>
      <div class="totals">
        <span class="badge both">{tot_both} paired</span>
        <span class="badge matonly">{tot_mat_only} MATLAB-only (missing in Python)</span>
        <span class="badge pyonly">{tot_py_only} Python-only (extra)</span>
      </div>
      <label class="filter"><input type="checkbox" id="onlyGaps"> Show only parity gaps (missing on one side)</label>
    </header>
    <nav>
    """)
    for sec in SECTION_ORDER:
        if sec not in stats:
            continue
        b, mo, po, _ = stats[sec]
        parts.append(
            f'<a href="#{slug(sec)}">{html.escape(sec)} '
            f'<small>({b}✓ {mo}▲ {po}▼)</small></a>'
        )
    parts.append("</nav>")

    for sec in SECTION_ORDER:
        if sec not in sections:
            continue
        keys = sections[sec]
        b, mo, po, tot = stats[sec]
        parts.append(f'<section id="{slug(sec)}">')
        parts.append(
            f'<h2>{html.escape(sec)} '
            f'<span class="secstats">{b} paired · {mo} MATLAB-only · {po} Python-only</span></h2>'
        )
        parts.append(
            '<div class="colbar"><div></div>'
            '<div class="cols"><span class="mlab">MATLAB</span>'
            '<span class="pyth">Python</span></div></div>'
        )
        for k in keys:
            m_rel = mat.get(k)
            p_rel = py.get(k)
            gap = (m_rel is None) or (p_rel is None)
            row_cls = "row gap" if gap else "row"
            label = html.escape(k.split("/")[-1])
            sub = html.escape("/".join(k.split("/")[:-1]))
            parts.append(f'<div class="{row_cls}" data-gap="{int(gap)}">')
            parts.append(f'<div class="rowhead"><b>{label}</b><br><small>{sub}</small></div>')
            parts.append('<div class="pair">')
            parts.append(img_cell(matlab_root, m_rel, "MATLAB"))
            parts.append(img_cell(python_root, p_rel, "Python"))
            parts.append("</div></div>")
        parts.append("</section>")

    parts.append(FOOTER)
    out_path.write_text("\n".join(parts), encoding="utf-8")
    return {
        "paired": tot_both,
        "matlab_only": tot_mat_only,
        "python_only": tot_py_only,
        "sections": stats,
        "out": str(out_path),
    }


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


HEADER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MEA-NAP plot parity</title>
<style>
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif;
       background: #0f1115; color: #e6e8eb; }
header { padding: 20px 24px; border-bottom: 1px solid #2a2e37; position: sticky; top: 0;
         background: #0f1115ee; backdrop-filter: blur(6px); z-index: 10; }
h1 { margin: 0 0 6px; font-size: 20px; }
.paths { margin: 0 0 10px; color: #9aa0aa; font-size: 12px; }
.totals { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.badge { padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.badge.both { background: #16351f; color: #7ee2a0; }
.badge.matonly { background: #3a2a12; color: #f0b866; }
.badge.pyonly { background: #122a3a; color: #6cc2f0; }
.filter { font-size: 13px; color: #c3c8d0; cursor: pointer; user-select: none; }
nav { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 24px; border-bottom: 1px solid #2a2e37; }
nav a { color: #c3c8d0; text-decoration: none; font-size: 12px; padding: 4px 10px;
        background: #1a1d24; border-radius: 6px; }
nav a small { color: #8b919b; }
nav a:hover { background: #262a33; }
section { padding: 8px 24px 32px; }
h2 { font-size: 16px; border-bottom: 1px solid #2a2e37; padding-bottom: 6px; }
h2 .secstats { font-size: 12px; font-weight: 400; color: #8b919b; margin-left: 8px; }
.row { display: grid; grid-template-columns: 190px 1fr; gap: 14px; padding: 12px 0;
       border-bottom: 1px solid #1c2027; align-items: start; }
.row.gap { background: #1a140c22; }
.rowhead { font-size: 13px; word-break: break-word; }
.rowhead small { color: #8b919b; font-size: 11px; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.colbar { display: grid; grid-template-columns: 190px 1fr; gap: 14px; position: sticky;
          top: 118px; z-index: 5; background: #0f1115; padding: 6px 0; }
.colbar .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.colbar .cols span { font-weight: 700; color: #9aa0aa; font-size: 12px;
                     text-transform: uppercase; letter-spacing: .05em; }
.colbar .cols .mlab { color: #f0b866; }
.colbar .cols .pyth { color: #6cc2f0; }
.cell { background: #1a1d24; border: 1px solid #2a2e37; border-radius: 8px; padding: 8px;
        display: flex; flex-direction: column; align-items: center; }
.cell img { max-width: 100%; height: auto; border-radius: 4px; background: #fff; }
.cell.missing { justify-content: center; min-height: 120px; color: #8b6a3a;
                border-style: dashed; font-style: italic; }
.fname { font-size: 10px; color: #7c828c; margin-top: 6px; word-break: break-all; text-align: center; }
.colhdr { display: grid; grid-template-columns: 190px 1fr; gap: 14px; padding: 6px 24px 0; }
.colhdr .labels { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; font-weight: 700; color: #9aa0aa; }
</style></head><body>
"""

FOOTER = """
<script>
document.getElementById('onlyGaps').addEventListener('change', function(e){
  const on = e.target.checked;
  document.querySelectorAll('.row').forEach(r => {
    r.style.display = (on && r.dataset.gap === '0') ? 'none' : '';
  });
});
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matlab", default="OutputData24Dec2025")
    ap.add_argument("--python", default="OutputData_Python")
    ap.add_argument("--out", default="plot_parity_report.html")
    args = ap.parse_args()

    res = build_report(Path(args.matlab), Path(args.python), Path(args.out))
    print(f"Wrote {res['out']}")
    print(f"  paired:      {res['paired']}")
    print(f"  MATLAB-only: {res['matlab_only']}")
    print(f"  Python-only: {res['python_only']}")
    print("  by section:")
    for sec, (b, mo, po, tot) in res["sections"].items():
        print(f"    {sec:45s} {b:4d} paired  {mo:4d} MATLAB-only  {po:4d} Python-only")


if __name__ == "__main__":
    main()
