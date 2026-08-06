"""Batch (group × age) comparison figures for the CAT-NAP path.

The electrophysiology pipeline ends steps 2 and 4 by pooling every recording
and drawing half-violin comparisons across experimental groups and ages
(``plot_step2_group_comparisons`` / ``plot_step4_group_comparisons``); MATLAB's
suite2p branch does the same through ``PlotEphysStats``/``PlotNetMet``. The
Python CAT-NAP path produced only per-recording figures. This module supplies
the missing batch layer:

* :func:`plot_twop_group_comparisons` — the calcium counterpart of step 2's
  ``2B_GroupComparisons``. The event-rate metrics parallel the ephys
  firing-rate ones; amplitude / duration / area have no ephys counterpart and
  exist only here.
* :func:`plot_subnetwork_group_comparisons` — cell-type subnetworks compared
  across groups and ages, one figure per (metric, cell type) so a cell type's
  panel can be read beside the ``Whole network`` panel of the same metric.

Network metrics themselves need nothing new: CAT-NAP's per-recording results
dict has the same shape as the ephys one, so the runner calls the shared
:func:`~meanap.pipeline.plotting_step4.plot_step4_group_comparisons` directly.

Every figure is drawn by the shared
:func:`~meanap.pipeline.plotting_step4.plot_half_violin_by_x`
(``plotHalfViolinByX.m``), so CAT-NAP and ephys comparison plots look the same
and land in the same folder layout.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

# ── Two-photon activity metrics (step-2 equivalent) ───────────────────────────
# Keys are ``calc_twop_activity_stats`` fields; values are axis labels. Units:
# event heights and areas come off the deconvolved relative-intensity trace, so
# they are arbitrary units; durations and areas are converted from frames to
# seconds by the stats routine.

TWOP_REC_METRICS = {
    "numActiveElec": "Number of Active Cells",
    "FRmean": "Mean Event Rate (Hz)",
    "FRmedian": "Median Event Rate (Hz)",
    "FRiqr": "Event Rate IQR (Hz)",
    "ISImean": "Mean Inter-Event Interval (s)",
    "recHeightMean": "Mean Event Amplitude (a.u.)",
    "recPeakDurMean": "Mean Event Duration (s)",
    "recEventAreaMean": "Mean Event Area (a.u.·s)",
}

TWOP_NODE_METRICS = {
    "FR": "Event Rate per Cell (Hz)",
    "FRactive": "Event Rate per Active Cell (Hz)",
    "ISI": "Mean Inter-Event Interval per Cell (s)",
    "unitHeightMean": "Mean Event Amplitude per Cell (a.u.)",
    "unitPeakDurMean": "Mean Event Duration per Cell (s)",
    "unitEventAreaMean": "Mean Event Area per Cell (a.u.·s)",
    "unitEventAreaSum": "Total Event Area per Cell (a.u.·s)",
}

# ── Cell-type subnetwork metrics (step-4 equivalent) ──────────────────────────
# Also the single source of truth for which metrics the *per-recording*
# subnetwork figures draw — ``catnap/pipeline.py`` takes its ordered lists from
# these dicts.

SUBNET_GRAPH_METRICS = {
    "Dens": "Density",
    "NDmean": "Mean Node Degree",
    "NSmean": "Mean Node Strength",
    "MEW_mean": "Mean Edge Weight",
    "Eglob": "Global Efficiency",
    "ElocMean": "Mean Local Efficiency",
    "CC_rawMean": "Clustering Coefficient",
    "SW": "Small-worldness (SW)",
    "SWw": "Small-worldness (SWw)",
    "Q": "Modularity (Q)",
    "nMod": "Number of Modules",
}

SUBNET_NODE_METRICS = {
    "ND": "Node Degree",
    "NS": "Node Strength",
    "MEW": "Mean Edge Weight",
    "Eloc": "Local Efficiency",
    "BC": "Betweenness Centrality",
    "PC": "Participation Coefficient",
    "Z": "Within-Module Degree Z-Score",
    "NE": "Nodal Efficiency",
    "CC_raw": "Clustering Coefficient",
    "WithinGroupStrengthFrac": "Within-Group Strength Fraction",
}


# ── Two-photon activity ───────────────────────────────────────────────────────

def twop_stats_frames(
    recordings: list,
    all_stats: dict[str, dict],
    channels_by_rec: dict[str, np.ndarray] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pool ``calc_twop_activity_stats`` output into recording- and node-level frames.

    Both frames carry ``FileName``/``Grp``/``DIV`` so they can be fed straight
    to :func:`~meanap.pipeline.plotting_step4.plot_half_violin_by_x`; the
    node-level frame adds ``Channel`` (the suite2p ROI id when
    *channels_by_rec* supplies one, otherwise a 1-based position).

    ``DIV`` is stringified to match the ephys frames — the plotter renders
    whole-number ages as integers either way.
    """
    rec_rows: list[dict] = []
    node_rows: list[dict] = []

    for rec in recordings:
        stats = all_stats.get(rec.filename)
        if not stats:
            continue
        base = {"FileName": rec.filename, "Grp": rec.group, "DIV": str(rec.div)}

        rec_row = dict(base)
        for key in TWOP_REC_METRICS:
            value = stats.get(key)
            if value is None or np.size(value) != 1:
                continue
            rec_row[key] = float(np.ravel(value)[0])
        rec_rows.append(rec_row)

        # Per-unit arrays. They are all length n_units, but a run using an
        # activity type other than 'peaks' leaves the 2P-specific ones as None.
        arrays = {
            key: np.asarray(stats[key], dtype=float).ravel()
            for key in TWOP_NODE_METRICS
            if isinstance(stats.get(key), (list, np.ndarray))
        }
        if not arrays:
            continue
        n_units = max(arr.size for arr in arrays.values())
        channels = channels_by_rec.get(rec.filename) if channels_by_rec else None
        channels = np.asarray(channels).ravel() if channels is not None else None

        for i in range(n_units):
            row = dict(base)
            row["Channel"] = int(channels[i]) if channels is not None and i < channels.size else i + 1
            for key, arr in arrays.items():
                if arr.size == n_units:
                    row[key] = float(arr[i])
            node_rows.append(row)

    return pd.DataFrame(rec_rows), pd.DataFrame(node_rows)


def plot_twop_group_comparisons(
    recordings: list,
    all_stats: dict[str, dict],
    out_dir: Path,
    custom_grp_order: list[str] | None = None,
    channels_by_rec: dict[str, np.ndarray] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Draw the ``2B_GroupComparisons`` figures for two-photon activity.

    *out_dir* is the run's ``2_NeuronalActivity`` folder. Writes the same four
    sub-folders the ephys step-2 comparison uses, so the two pipelines produce
    an identically-shaped output tree. Returns the two pooled frames, which the
    runner also saves as CSVs.
    """
    from meanap.pipeline.plotting_step4 import plot_half_violin_by_x

    df_rec, df_node = twop_stats_frames(recordings, all_stats, channels_by_rec)
    base = Path(out_dir) / "2B_GroupComparisons"

    specs = [
        (df_rec, TWOP_REC_METRICS, "group",
         base / "3_RecordingsByGroup" / "HalfViolinPlots", "{key}_byGroup.png"),
        (df_rec, TWOP_REC_METRICS, "DIV",
         base / "4_RecordingsByAge" / "HalfViolinPlots", "{key}_byDIV.png"),
        (df_node, TWOP_NODE_METRICS, "group",
         base / "1_NodeByGroup", "{key}_byGroup_node.png"),
        (df_node, TWOP_NODE_METRICS, "DIV",
         base / "2_NodeByAge", "{key}_byDIV_node.png"),
    ]
    for df, metrics, x_kind, directory, pattern in specs:
        if df.empty:
            continue
        directory.mkdir(parents=True, exist_ok=True)
        for key, label in metrics.items():
            if key not in df.columns:
                continue
            plot_half_violin_by_x(
                df, key, label, x_kind, directory / pattern.format(key=key),
                group_order=custom_grp_order,
            )

    return df_rec, df_node


# ── Activity split by cell type ───────────────────────────────────────────────

#: Label for cells belonging to none of the user's groups.
UNASSIGNED = "Unassigned"

#: Per-recording composition metrics, computed for every cell-type group.
COMPOSITION_METRICS = {
    "nCells": "Number of Cells",
    "fracOfCells": "Fraction of All Cells",
    "nActiveCells": "Number of Active Cells",
    "fracActive": "Fraction of This Type That Is Active",
}


def _cell_type_lookup(groups, channels) -> dict[int, list[str]]:
    """``channel id → the group names that channel belongs to``.

    A channel can appear under several groups (marker columns overlap freely),
    which is why the value is a list — the frames built from it are long
    format, one row per (cell × group), so every group's distribution is
    complete rather than each cell being forced into one bucket.
    """
    channels = np.asarray(channels).ravel()
    lookup: dict[int, list[str]] = {}
    for pos, channel in enumerate(channels):
        names = [n for i, n in enumerate(groups.names) if groups.masks[pos, i]]
        lookup[int(channel)] = names or [UNASSIGNED]
    return lookup


def add_cell_type_column(
    df_node: pd.DataFrame,
    groups_by_rec: dict,
    channels_by_rec: dict,
    include_unassigned: bool = True,
) -> pd.DataFrame:
    """Long-format copy of a node-level frame with a ``CellType`` column.

    Recordings with no cell-type information are dropped rather than lumped
    into a catch-all, so a partially-labelled batch doesn't silently mix
    "no marker" with "not measured".
    """
    if df_node.empty or not groups_by_rec:
        return pd.DataFrame()

    rows = []
    for filename, groups in groups_by_rec.items():
        channels = channels_by_rec.get(filename)
        if groups is None or channels is None:
            continue
        lookup = _cell_type_lookup(groups, channels)
        sub = df_node[df_node["FileName"] == filename]
        for record in sub.to_dict("records"):
            for name in lookup.get(int(record.get("Channel", -1)), []):
                if name == UNASSIGNED and not include_unassigned:
                    continue
                rows.append(dict(record, CellType=name))
    return pd.DataFrame(rows)


def composition_frame(
    recordings: list,
    groups_by_rec: dict,
    channels_by_rec: dict,
    active_by_rec: dict | None = None,
) -> pd.DataFrame:
    """Per (recording × cell type) counts and fractions.

    Deliberately generic over whatever groups the user defined — nothing here
    assumes an excitatory/inhibitory split, so a per-marker grouping produces
    one row per marker just as readily.

    ``active_by_rec`` maps a recording to the set of channel ids that passed
    the activity threshold; without it the "active" columns are omitted rather
    than guessed. Note that group membership may overlap, so ``nCells`` need
    not sum to the recording's cell count.
    """
    rows = []
    for rec in recordings:
        groups = groups_by_rec.get(rec.filename)
        channels = channels_by_rec.get(rec.filename)
        if groups is None or channels is None:
            continue
        n_total = int(np.size(channels))
        if n_total == 0:
            continue
        active = active_by_rec.get(rec.filename) if active_by_rec else None
        lookup = _cell_type_lookup(groups, channels)

        per_group: dict[str, list[int]] = {}
        for channel, names in lookup.items():
            for name in names:
                per_group.setdefault(name, []).append(channel)

        for name in list(groups.names) + [UNASSIGNED]:
            members = per_group.get(name, [])
            if name == UNASSIGNED and not members:
                continue
            row = {
                "FileName": rec.filename, "Grp": rec.group, "DIV": str(rec.div),
                "CellType": name,
                "nCells": len(members),
                "fracOfCells": len(members) / n_total,
            }
            if active is not None:
                n_active = sum(1 for c in members if c in active)
                row["nActiveCells"] = n_active
                row["fracActive"] = (n_active / len(members)) if members else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def plot_activity_by_cell_type(
    df_node: pd.DataFrame,
    composition: pd.DataFrame,
    out_dir: Path,
    custom_grp_order: list[str] | None = None,
    cell_type_order: list[str] | None = None,
) -> None:
    """Two-photon activity and cell-type composition, split by cell type.

    *out_dir* is the run's ``2_NeuronalActivity`` folder. Cell type becomes a
    third factor *within* each panel — paired half-violins at every age, in
    every experimental group — rather than a separate file per type, so "do
    inhibitory cells fire faster, and does that differ by genotype?" is one
    figure.
    """
    from meanap.pipeline.plotting_step4 import plot_half_violin_by_x

    base = Path(out_dir) / "2B_GroupComparisons"
    order = cell_type_order or (sorted(df_node["CellType"].dropna().unique())
                                if not df_node.empty and "CellType" in df_node else None)

    specs = [
        (df_node, TWOP_NODE_METRICS, "group",
         base / "1_NodeByGroup" / "ByCellType", "{key}_byGroup_node.png"),
        (df_node, TWOP_NODE_METRICS, "DIV",
         base / "2_NodeByAge" / "ByCellType", "{key}_byDIV_node.png"),
        (composition, COMPOSITION_METRICS, "group",
         base / "5_CellTypeComposition", "{key}_byGroup.png"),
        (composition, COMPOSITION_METRICS, "DIV",
         base / "5_CellTypeComposition", "{key}_byDIV.png"),
    ]
    for df, metrics, x_kind, directory, pattern in specs:
        if df is None or df.empty or "CellType" not in df.columns:
            continue
        directory.mkdir(parents=True, exist_ok=True)
        for key, label in metrics.items():
            if key not in df.columns:
                continue
            plot_half_violin_by_x(
                df, key, label, x_kind, directory / pattern.format(key=key),
                group_order=custom_grp_order,
                series_col="CellType", series_order=order,
            )


# ── Cell-type subnetworks ─────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    """Filename-safe version of a cell-type group name (``NeuN+ & ~GAD+`` …)."""
    return re.sub(r"[^\w.+-]+", "_", str(name)).strip("_") or "group"


def _lag_folder(lag) -> str:
    """``'1000mslag'`` → ``'Lag1000ms'`` (the naming the ephys folders use)."""
    text = str(lag).replace("lag", "")
    return f"Lag{text}" if "ms" in text else f"Lag{text}ms"


def plot_subnetwork_group_comparisons(
    summary_rows: list[dict],
    node_rows: list[dict],
    out_dir: Path,
    custom_grp_order: list[str] | None = None,
) -> None:
    """Compare cell-type subnetworks across experimental groups and ages.

    *out_dir* is the run's ``4_NetworkActivity`` folder; figures land under
    ``4B_GroupComparisons/8_CellTypeSubnetworks/Lag<n>ms/``. The inputs are the
    same row lists the runner writes to ``Subnetwork_RecordingLevel.csv`` /
    ``Subnetwork_NodeLevel.csv``.

    One figure per (metric, cell type): each is laid out exactly like the
    whole-network comparison of that metric, so ``Dens_Inhibitory_byGroup.png``
    can be read straight against ``Dens_Whole_network_byGroup.png`` — the
    reference row ``compute_subnetwork_metrics`` already emits under
    :data:`~meanap.catnap.subnetwork.WHOLE_NETWORK`. Splitting by cell type
    into separate files rather than crowding one figure keeps the shared
    half-violin plotter (whose two axes are already spent on group and age)
    usable without a third dimension.
    """
    from meanap.pipeline.plotting_step4 import plot_half_violin_by_x

    base = Path(out_dir) / "4B_GroupComparisons" / "8_CellTypeSubnetworks"

    sources = [
        (summary_rows, SUBNET_GRAPH_METRICS,
         ("RecordingsByGroup", "{key}_{ct}_byGroup.png"),
         ("RecordingsByAge", "{key}_{ct}_byDIV.png")),
        (node_rows, SUBNET_NODE_METRICS,
         ("NodeByGroup", "{key}_{ct}_byGroup_node.png"),
         ("NodeByAge", "{key}_{ct}_byDIV_node.png")),
    ]

    for rows, metrics, by_group, by_age in sources:
        df = pd.DataFrame(rows)
        if df.empty or "Group" not in df.columns:
            continue
        df = df.copy()
        df["DIV"] = df["DIV"].astype(str)
        # Node rows are per (node × group) and carry no FileName-unique key of
        # their own; FileName is what plot_half_violin_by_x counts recordings
        # with, and it is already present on every row from the runner's base.

        for lag, df_lag in df.groupby("Lag", sort=False):
            lag_dir = base / _lag_folder(lag)
            for cell_type, df_ct in df_lag.groupby("Group", sort=False):
                safe = _safe_name(cell_type)
                for x_kind, (sub, pattern) in (("group", by_group), ("DIV", by_age)):
                    directory = lag_dir / sub
                    directory.mkdir(parents=True, exist_ok=True)
                    for key, label in metrics.items():
                        if key not in df_ct.columns or df_ct[key].dropna().empty:
                            continue
                        plot_half_violin_by_x(
                            df_ct, key, f"{label} — {cell_type}", x_kind,
                            directory / pattern.format(key=key, ct=safe),
                            group_order=custom_grp_order,
                        )
