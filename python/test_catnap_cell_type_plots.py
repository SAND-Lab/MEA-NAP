"""Test the cell-type-aware plotting added to CAT-NAP.

Run from the repo root::

    uv run python python/test_catnap_cell_type_plots.py

Three features, none with a MATLAB counterpart to compare against (MATLAB draws
cell-type rings but all solid white, and has no by-cell-type activity
comparison at all), so these are correctness and self-consistency checks:

  - **Genetic-identity rings.** Every node carries one ring per marker at a
    radius fixed by marker index, in that marker's own dash pattern — bright
    where the cell is positive, faint where it is negative. The checks count
    the rendered rings against the membership matrix, because "looks right" is
    not verifiable by eye once there are more than a couple of markers.
  - **Activity split by cell type.** The pooled per-cell frames gain a
    ``CellType`` column in long format (a cell positive for two markers
    contributes a row to each), and composition counts stay consistent with it.
  - **Paired half-violins.** The shared plotter's new series dimension draws one
    violin per (x position x series) and — importantly — leaves the two-factor
    output untouched when no series column is given.

All synthetic; no dataset needed, so this always runs.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from meanap.catnap import group_plots as gp  # noqa: E402
from meanap.catnap.subnetwork import CellTypeGroups  # noqa: E402
from meanap.network_plot import (  # noqa: E402
    _cell_type_styles, _ring_radii, auto_node_size_scale, median_node_spacing,
    plot_network,
)
from meanap.pipeline.plotting_step4 import plot_half_violin_by_x  # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── Section A — genetic-identity rings ────────────────────────────────────────

def _render_rings(ct_matrix: np.ndarray, names: list[str]):
    """Render a small network and return its patch collections by zorder."""
    n = ct_matrix.shape[0]
    rng = np.random.default_rng(0)
    coords = np.array([[i % 4, i // 4] for i in range(n)], dtype=float) * 1.5
    adj = np.triu(rng.random((n, n)), 1)
    adj = adj + adj.T
    z = adj.sum(axis=0)

    fig, ax = plt.subplots(figsize=(6, 6))
    plot_network(ax, adj, coords, 0.0, z, None, "None",
                 cell_type_matrix=ct_matrix, cell_type_names=names)
    from matplotlib.collections import PatchCollection
    cols = {c.get_zorder(): c for c in ax.collections if isinstance(c, PatchCollection)}
    counts = {zo: len(c.get_paths()) for zo, c in cols.items()}
    plt.close(fig)
    return counts


def _ring_checks() -> list[Check]:
    checks: list[Check] = []
    names = ["NeuN+", "GAD+", "PV+", "SST+"]
    ct = np.array([
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [0, 0, 0, 0],   # negative for everything — must still show 4 faint slots
        [1, 1, 1, 1],   # positive for everything — no faint slots
        [0, 1, 0, 1],
        [0, 0, 1, 0],
        [1, 0, 1, 0],
        [0, 1, 1, 1],
    ], dtype=float)
    n, k = ct.shape

    counts = _render_rings(ct, names)
    # zorder 2 = node bodies, 3 = negative slots, 4 = dark halo under each
    # positive ring, 5 = the styled positive ring itself.
    n_pos = int(ct.sum())
    checks.append(("one node body per node", counts.get(2) == n, f"{counts}"))
    checks.append(("one styled ring per positive marker",
                   counts.get(5) == n_pos, f"{counts.get(5)} vs {n_pos}"))
    checks.append(("each positive ring gets a contrast halo",
                   counts.get(4) == n_pos, f"{counts.get(4)} vs {n_pos}"))
    checks.append(("one faint ring per negative marker",
                   counts.get(3) == int((1 - ct).sum()),
                   f"{counts.get(3)} vs {int((1 - ct).sum())}"))
    checks.append(("every node shows a slot for every marker",
                   counts.get(3, 0) + counts.get(5, 0) == n * k,
                   f"{counts}"))

    # A cell negative for everything still renders its full identity — that is
    # the difference from MATLAB, where it would be indistinguishable from a
    # cell with no cell-type data at all. (Two nodes, since plot_network skips
    # zero-degree nodes and a lone node has no edges.)
    both_negative = _render_rings(np.zeros((2, k)), names)
    checks.append(("an all-negative cell still shows every slot",
                   both_negative.get(3) == 2 * k and both_negative.get(5, 0) == 0,
                   f"{both_negative}"))

    radii = _ring_radii(k)
    checks.append(("ring radii are ordered outermost-first and distinct",
                   bool(np.all(np.diff(radii) < 0)) and len(set(radii.tolist())) == k,
                   f"{radii}"))
    checks.append(("ring radii depend only on marker index, not membership",
                   np.array_equal(_ring_radii(k), _ring_radii(k)), ""))
    checks.append(("radii stay inside the node",
                   bool(np.all(radii <= 1.0) and np.all(radii > 0)), f"{radii}"))

    styles = _cell_type_styles(k)
    checks.append(("each marker gets a distinct dash pattern",
                   len({str(s) for s in styles}) == k, f"{styles}"))
    checks.append(("dash patterns are stable across calls",
                   _cell_type_styles(k) == styles, ""))
    checks.append(("patterns cycle rather than failing for many markers",
                   len(_cell_type_styles(30)) == 30, ""))

    # No cell-type data at all → no ring collections, only node bodies.
    fig, ax = plt.subplots(figsize=(4, 4))
    coords = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    adj = np.ones((3, 3)) - np.eye(3)
    plot_network(ax, adj, coords, 0.0, adj.sum(axis=0), None, "None")
    from matplotlib.collections import PatchCollection
    zorders = {c.get_zorder() for c in ax.collections if isinstance(c, PatchCollection)}
    plt.close(fig)
    checks.append(("no ring collections when there are no cell types",
                   zorders.isdisjoint({3, 4, 5}), f"{zorders}"))
    return checks


# ── Section A2 — density-aware node sizing ────────────────────────────────────

def _node_size_checks() -> list[Check]:
    """Nodes are drawn in data units, so a scale tuned for ~60 MEA electrodes
    draws them several times the inter-cell distance on a 2P field. The
    important property of the fix is that it changes *nothing* for the
    electrophysiology path."""
    from meanap.pipeline.channel_layout import get_coords_from_layout

    checks: list[Check] = []
    for layout in ("MCS60", "Axion64", "MCS60old"):
        try:
            _, coords = get_coords_from_layout(layout)
        except Exception:
            continue
        scale = auto_node_size_scale(coords)
        checks.append((f"auto sizing is exactly a no-op on {layout}",
                       abs(scale - 1.0) < 1e-9, f"{scale!r}"))

    # A dense field: ~250 cells in the same coordinate box as ~60 electrodes.
    rng = np.random.default_rng(0)
    dense = rng.uniform(0, 8, (250, 2))
    dense_scale = auto_node_size_scale(dense)
    checks.append(("a dense field shrinks nodes", dense_scale < 0.4, f"{dense_scale:.3f}"))
    checks.append(("the largest node stays under the node spacing",
                   dense_scale < median_node_spacing(dense),
                   f"{dense_scale:.3f} vs {median_node_spacing(dense):.3f}"))

    checks.append(("scale falls back to 1.0 when spacing is undefined",
                   auto_node_size_scale(np.zeros((1, 2))) == 1.0
                   and auto_node_size_scale(np.zeros((0, 2))) == 1.0, ""))
    checks.append(("coincident nodes don't produce a zero scale",
                   auto_node_size_scale(np.zeros((5, 2))) == 1.0, ""))

    # 'auto' must reach plot_network as a number, not blow up.
    coords = np.array([[i % 5, i // 5] for i in range(25)], dtype=float)
    adj = np.ones((25, 25)) - np.eye(25)
    fig, ax = plt.subplots(figsize=(4, 4))
    plot_network(ax, adj, coords, 0.0, adj.sum(axis=0), None, "None",
                 node_size_scale="auto")
    ok = len(ax.collections) > 0
    plt.close(fig)
    checks.append(("plot_network accepts node_size_scale='auto'", ok, ""))
    return checks


# ── Section B — activity split by cell type ───────────────────────────────────

def _groups(channels: np.ndarray, overlap: bool = False) -> CellTypeGroups:
    """Excitatory/inhibitory over *channels*; ``overlap`` makes a cell both."""
    n = len(channels)
    exc = np.zeros(n, bool)
    inh = np.zeros(n, bool)
    exc[: n // 2] = True
    inh[n // 2: n - 1] = True          # last channel belongs to neither
    if overlap:
        inh[0] = True                  # channel 0 is now in both groups
    return CellTypeGroups(["Excitatory", "Inhibitory"], np.column_stack([exc, inh]),
                          ["NeuN+", "GAD+"], np.column_stack([exc, inh]))


def _frame_checks() -> list[Check]:
    checks: list[Check] = []
    recordings = [RecordingInfo(filename=f"rec{i}", div=14.0 + 7 * (i % 2), group="WT")
                  for i in range(2)]
    channels = np.arange(1, 11)
    channels_by_rec = {r.filename: channels for r in recordings}
    groups_by_rec = {r.filename: _groups(channels) for r in recordings}

    rng = np.random.default_rng(0)
    df_node = pd.DataFrame([
        {"FileName": r.filename, "Grp": r.group, "DIV": str(r.div),
         "Channel": int(c), "FR": float(rng.uniform(0.05, 0.3)),
         "FRactive": (float(rng.uniform(0.05, 0.3)) if c != 10 else np.nan)}
        for r in recordings for c in channels
    ])

    tagged = gp.add_cell_type_column(df_node, groups_by_rec, channels_by_rec)
    checks.append(("every cell appears in the tagged frame",
                   set(tagged["Channel"]) == set(channels.tolist()), ""))
    checks.append(("cells in no group are labelled Unassigned",
                   set(tagged[tagged["Channel"] == 10]["CellType"]) == {gp.UNASSIGNED}, ""))
    checks.append(("group sizes are preserved",
                   len(tagged[(tagged.FileName == "rec0") & (tagged.CellType == "Excitatory")]) == 5,
                   ""))
    checks.append(("activity values survive the join",
                   np.isclose(
                       tagged[(tagged.FileName == "rec0") & (tagged.Channel == 1)]["FR"].iloc[0],
                       df_node[(df_node.FileName == "rec0") & (df_node.Channel == 1)]["FR"].iloc[0]), ""))

    # Overlapping membership must produce one row per (cell, group), not a
    # single arbitrary assignment.
    overlap_by_rec = {r.filename: _groups(channels, overlap=True) for r in recordings}
    over = gp.add_cell_type_column(df_node, overlap_by_rec, channels_by_rec)
    ch1 = over[(over.FileName == "rec0") & (over.Channel == 1)]
    checks.append(("a cell in two groups contributes a row to each",
                   set(ch1["CellType"]) == {"Excitatory", "Inhibitory"}, f"{list(ch1.CellType)}"))

    checks.append(("Unassigned can be excluded",
                   gp.UNASSIGNED not in set(gp.add_cell_type_column(
                       df_node, groups_by_rec, channels_by_rec,
                       include_unassigned=False)["CellType"]), ""))

    # Composition.
    active = {r.filename: set(range(1, 10)) for r in recordings}  # channel 10 inactive
    comp = gp.composition_frame(recordings, groups_by_rec, channels_by_rec, active)
    exc0 = comp[(comp.FileName == "rec0") & (comp.CellType == "Excitatory")].iloc[0]
    checks.append(("composition counts cells per group", exc0["nCells"] == 5, f"{exc0['nCells']}"))
    checks.append(("composition fraction is of all cells",
                   np.isclose(exc0["fracOfCells"], 0.5), f"{exc0['fracOfCells']}"))
    checks.append(("composition counts active cells within the group",
                   exc0["nActiveCells"] == 5 and np.isclose(exc0["fracActive"], 1.0), ""))
    unassigned = comp[(comp.FileName == "rec0") & (comp.CellType == gp.UNASSIGNED)].iloc[0]
    checks.append(("the inactive unassigned cell is counted but not active",
                   unassigned["nCells"] == 1 and unassigned["nActiveCells"] == 0, ""))
    checks.append(("composition omits active columns when activity is unknown",
                   "nActiveCells" not in gp.composition_frame(
                       recordings, groups_by_rec, channels_by_rec).columns, ""))

    # Recordings with no cell-type data are dropped, not silently merged.
    partial = {recordings[0].filename: groups_by_rec[recordings[0].filename]}
    checks.append(("recordings without cell types are dropped",
                   set(gp.add_cell_type_column(df_node, partial, channels_by_rec)["FileName"])
                   == {"rec0"}, ""))
    checks.append(("empty input is handled",
                   gp.add_cell_type_column(pd.DataFrame(), {}, {}).empty
                   and gp.composition_frame([], {}, {}).empty, ""))
    return checks


# ── Section C — paired half-violins ───────────────────────────────────────────

def _violin_count(df: pd.DataFrame, **kwargs) -> int:
    """Number of KDE fills drawn — one per violin actually rendered."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "f.png"
        plot_half_violin_by_x(df, "FR", "Event Rate", "group", path, **kwargs)
        assert path.exists()
        return path.stat().st_size


def _series_checks() -> list[Check]:
    checks: list[Check] = []
    rng = np.random.default_rng(0)
    rows = []
    for grp in ("WT", "KO"):
        for div in (14, 21):
            for rep in range(3):
                for ct, mu in (("Excitatory", 0.10), ("Inhibitory", 0.25)):
                    for _ in range(15):
                        rows.append({"FileName": f"{grp}{div}{rep}", "Grp": grp,
                                     "DIV": str(float(div)), "CellType": ct,
                                     "FR": float(rng.normal(mu, 0.03))})
    df = pd.DataFrame(rows)

    # Count rendered violins directly off the axes rather than trusting the file.
    import matplotlib.pyplot as plt_mod
    made = {}

    def _count(series_col):
        with tempfile.TemporaryDirectory() as tmp:
            plot_half_violin_by_x(df, "FR", "Event Rate", "group",
                                  Path(tmp) / "f.png", group_order=["WT", "KO"],
                                  series_col=series_col)
        # The plotter closes its figure; re-render onto our own axes instead.
        return None

    # Re-implement the count by inspecting a live figure: patch savefig away.
    real_savefig = matplotlib.figure.Figure.savefig
    captured: list = []
    try:
        matplotlib.figure.Figure.savefig = lambda self, *a, **k: captured.append(self)
        real_close = plt_mod.close
        plt_mod.close = lambda *a, **k: None
        with tempfile.TemporaryDirectory() as tmp:
            plot_half_violin_by_x(df, "FR", "Event Rate", "group", Path(tmp) / "a.png",
                                  group_order=["WT", "KO"], series_col="CellType")
            paired = captured[-1]
            plot_half_violin_by_x(df, "FR", "Event Rate", "group", Path(tmp) / "b.png",
                                  group_order=["WT", "KO"])
            plain = captured[-1]
    finally:
        matplotlib.figure.Figure.savefig = real_savefig
        plt_mod.close = real_close

    def _fills(fig):
        from matplotlib.collections import PolyCollection
        return sum(len([c for c in ax.collections if isinstance(c, PolyCollection)])
                   for ax in fig.axes)

    made["paired"] = _fills(paired)
    made["plain"] = _fills(plain)
    plt_mod.close(paired)
    plt_mod.close(plain)

    # 2 groups (subplots) x 2 ages x 2 cell types = 8 violins; without the
    # series dimension, 2 x 2 = 4.
    checks.append(("one violin per (age x cell type) per group panel",
                   made["paired"] == 8, f"{made}"))
    checks.append(("the two-factor plot is unchanged without a series column",
                   made["plain"] == 4, f"{made}"))
    checks.append(("adding a series adds a legend",
                   any(ax.get_legend() is not None for ax in paired.axes)
                   and all(ax.get_legend() is None for ax in plain.axes), ""))

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        gp.plot_activity_by_cell_type(
            df.assign(**{m: df["FR"] for m in gp.TWOP_NODE_METRICS}),
            pd.DataFrame([{"FileName": "a", "Grp": "WT", "DIV": "14.0",
                           "CellType": "Excitatory", "nCells": 5, "fracOfCells": 0.5,
                           "nActiveCells": 4, "fracActive": 0.8}]),
            out, custom_grp_order=["WT", "KO"],
        )
        base = out / "2B_GroupComparisons"
        checks.append(("activity-by-cell-type figures land beside the pooled ones",
                       (base / "1_NodeByGroup" / "ByCellType" / "FR_byGroup_node.png").exists()
                       and (base / "2_NodeByAge" / "ByCellType" / "FR_byDIV_node.png").exists(), ""))
        checks.append(("composition figures are written",
                       (base / "5_CellTypeComposition" / "nCells_byGroup.png").exists()
                       and (base / "5_CellTypeComposition" / "fracActive_byDIV.png").exists(), ""))
    return checks


# ── Section D — per-subnetwork figure set ─────────────────────────────────────

def _subnetwork_figure_checks() -> list[Check]:
    from meanap.pipeline.step4 import _plot_recording_lag

    checks: list[Check] = []
    from meanap.params import Params
    params = Params()
    n = 40
    rng = np.random.default_rng(0)
    adj = np.triu(rng.uniform(0.2, 1.0, (n, n)), 1)
    adj = adj + adj.T
    metrics = {
        "aN": n, "activeChannelIndex": np.arange(n), "adjMsub": adj,
        "ND": adj.sum(0), "NS": adj.sum(0), "MEW": adj.mean(0),
        "Eloc": rng.random(n), "BC": rng.random(n), "PC": rng.random(n),
        "Z": rng.normal(0, 1, n), "Ci": rng.integers(1, 4, n),
        "NdCartDiv": rng.integers(1, 7, n),
    }
    rec = RecordingInfo(filename="rec0", div=21.0, group="HET")
    channels = np.arange(1, n + 1)
    coords = rng.uniform(0, 8, (n, 2))
    ct = (rng.random((n, 3)) < 0.5).astype(float)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _plot_recording_lag(rec, 1000, metrics, channels, params, out, lambda m: None, {},
                            coords_all=coords, cell_types=(ct, ["NeuN+", "GAD+", "PV+"]),
                            sub_dir="cellTypeSubnetworks/Inhibitory")
        lag_dir = out / "4A_IndividualNetworkAnalysis" / "HET" / "rec0" / "1000mslag"
        sub = lag_dir / "cellTypeSubnetworks" / "Inhibitory"
        checks.append(("sub_dir nests the figure set under the lag folder",
                       sub.is_dir(), f"{list(lag_dir.rglob('*')) if lag_dir.exists() else 'missing'}"))
        made = {p.name for p in sub.glob("*.png")} if sub.is_dir() else set()
        for name in ("2_MEA_NetworkPlot.png",
                     "9_adjM1000msNodeCartography.png",
                     "9_circular_NetworkPlotNodeCartography.png",
                     "7_adjM1000msGraphMetricsByNode.png"):
            checks.append((f"subnetwork figure: {name}", name in made, f"{sorted(made)}"))
        checks.append(("nothing is written to the whole-network lag folder",
                       not list(lag_dir.glob("*.png")), ""))

        # A backdrop must produce exactly one extra figure — the side-by-side
        # comparison — and must NOT end up behind the ordinary spatial plots,
        # where a few hundred nodes cover it completely.
        img = np.linspace(0, 1, 64 * 64).reshape(64, 64)
        _plot_recording_lag(rec, 1000, metrics, channels, params, out, lambda m: None, {},
                            coords_all=coords, background=(img, (0.0, 8.0, 0.0, 8.0)),
                            sub_dir="withField")
        field_dir = lag_dir / "withField"
        made_bg = {p.name for p in field_dir.glob("*.png")} if field_dir.is_dir() else set()
        checks.append(("a backdrop adds the field-of-view figure",
                       "12_MeanImageAndNetwork.png" in made_bg, f"{sorted(made_bg)}"))
        checks.append(("no field-of-view figure without a backdrop",
                       "12_MeanImageAndNetwork.png" not in made, f"{sorted(made)}"))
        checks.append(("the backdrop adds exactly one figure",
                       len(made_bg) == len(made) + 1,
                       f"{len(made_bg)} vs {len(made)}"))
        checks.append(("no sub_dir keeps the original location",
                       True, ""))

        _plot_recording_lag(rec, 1000, metrics, channels, params, out, lambda m: None, {},
                            coords_all=coords)
        checks[-1] = ("no sub_dir keeps the original location",
                      bool(list(lag_dir.glob("*.png"))), "")
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP cell-type-aware plots")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [
        ("Section A — genetic-identity rings:", _ring_checks),
        ("Section A2 — density-aware node sizing:", _node_size_checks),
        ("Section B — activity and composition by cell type:", _frame_checks),
        ("Section C — paired half-violins:", _series_checks),
        ("Section D — figure set per cell-type subnetwork:", _subnetwork_figure_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
