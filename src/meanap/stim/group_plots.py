"""Group-level half-violins of the stimulus networks, by stimulation condition.

The same figures as step 4B (one panel per group with DIV on the x-axis, and
one per DIV with group on it, one folder per lag), with stimulation added as
side-by-side violins in each cell, drawn by
:func:`~meanap.pipeline.plotting_step4.plot_half_violin_by_x`. Every point is
one recording (one recording × condition, when it has several).

``StimNetwork_GroupComparisons/``

* ``1_ChangeByGroup``, ``2_ChangeByAge``: each network metric's evoked −
  baseline difference, violins split by **condition**. The difference is taken
  within each recording, so the baseline-evoked pairing is kept; side-by-side
  violins would hide it.
* ``3_EpochsByGroup``, ``4_EpochsByAge``: the raw metric, **baseline,
  evoked and post-stimulus** violins, one sub-folder per condition. Shows whether a change comes
  from the evoked network or from a baseline that differs between groups.
* ``5_ResponseByGroup``, ``6_ResponseByAge``: per-condition summaries with no
  epoch — split-half agreement (per lag), noise correlations, and the
  trial-consistency measures.

Conditions are matched across recordings by name: their electrodes
(``12+13``, ``12>13>14``) or their ``StimConditions`` label
(:mod:`meanap.stim.sequences`).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

#: Categorical colours for conditions, in this fixed order (Okabe–Ito, reordered
#: so neighbours stay apart under colour-vision deficiency).
CONDITION_COLORS = ("#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9")
#: Baseline, evoked, post — baseline grey as the neutral reference (as in
#: figures 13–15), post an orange that stays apart from the blue under CVD.
EPOCH_COLORS = ("#8a8f98", "#2a62c9", "#c0610f")
EPOCHS = ("baseline", "evoked", "post")

#: Network summaries beyond step 4's metrics, from ``network_summary``.
EXTRA_NETWORK_METRICS = {"meanSTTC": "mean STTC",
                         "meanSTTCminusNull": "mean STTC above null",
                         "nSigEdges": "number of significant edges"}

#: Split-half agreement, per lag: column → label.
SPLIT_METRICS = {"r_excess_odd_even": "split-half r odd vs even (above null)",
                 "r_excess_first_second": "split-half r first vs second half (above null)",
                 "r_sttc_odd_even": "split-half r odd vs even (raw STTC)",
                 "r_sttc_first_second": "split-half r first vs second half (raw STTC)"}

#: Per-condition response summaries with no lag.
RESPONSE_METRICS = {"meanNoiseCorr": "mean noise correlation",
                    "fracSigNoiseCorr": "fraction of significant noise correlations",
                    "meanPopResponse": "population response (evoked - baseline spikes)",
                    "popResponseRho": "population response trend over trials (rho)",
                    "fracNodesDrifting": "fraction of nodes drifting",
                    "similarityLagSlope": "pattern similarity slope over trial separation",
                    "medianLatency_ms": "median first-spike latency (ms)"}

#: Bounded metrics' y-limits; the rest scale to the data.
_LIMITS = {"r_excess_odd_even": (-1, 1), "r_excess_first_second": (-1, 1),
           "r_sttc_odd_even": (-1, 1), "r_sttc_first_second": (-1, 1),
           "fracSigNoiseCorr": (0, 1), "fracNodesDrifting": (0, 1),
           "popResponseRho": (-1, 1), "meanNoiseCorr": (-1, 1)}


def _plain_keys(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Grp as text and DIV as ``"14"``, whatever the table they came from used."""
    if df is None or df.empty:
        return df
    df = df.copy()
    df["Grp"] = df["Grp"].astype(str)
    df["DIV"] = df["DIV"].map(lambda d: f"{float(d):g}")
    return df


def _all_network_metrics() -> dict[str, str]:
    from meanap.pipeline.plotting_step4 import NETMET_REC_METRICS

    return {**NETMET_REC_METRICS, **EXTRA_NETWORK_METRICS}


def _network_metrics(df: pd.DataFrame) -> dict[str, str]:
    metrics = _all_network_metrics()
    return {k: v for k, v in metrics.items()
            if k in df.columns and pd.to_numeric(df[k], errors="coerce").notna().any()}


def _ordered(df: pd.DataFrame, group_order: list[str] | None) -> pd.DataFrame:
    df = df.copy()
    df["DIV"] = df["DIV"].map(lambda d: f"{float(d):g}")
    if group_order:
        df["Grp"] = pd.Categorical(df["Grp"], categories=group_order, ordered=True)
    return df


def change_frame(net: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Evoked − baseline per recording × condition × lag, for each of *metrics*."""
    keys = ["FileName", "Grp", "DIV", "condition", "lag_ms"]
    ep = net[net["epoch"].isin(["baseline", "evoked"])]
    cols = [m for m in metrics if m in ep.columns]
    ev = ep[ep["epoch"] == "evoked"].set_index(keys)[cols].apply(pd.to_numeric, errors="coerce")
    bl = ep[ep["epoch"] == "baseline"].set_index(keys)[cols].apply(pd.to_numeric, errors="coerce")
    return (ev - bl).reset_index()


def split_frame(split: pd.DataFrame) -> pd.DataFrame:
    """One row per recording × condition × lag, with each split's evoked agreement."""
    ev = split[split["epoch"] == "evoked"]
    keys = ["FileName", "Grp", "DIV", "condition", "lag_ms"]
    out = None
    for sp in ("odd_even", "first_second"):
        part = ev[ev["split"] == sp].set_index(keys)[["r_excess", "r_sttc"]]
        part = part.rename(columns={"r_excess": f"r_excess_{sp}", "r_sttc": f"r_sttc_{sp}"})
        out = part if out is None else out.join(part, how="outer")
    return out.reset_index() if out is not None else pd.DataFrame(columns=keys)


def response_frame(net: pd.DataFrame, cons: pd.DataFrame | None) -> pd.DataFrame:
    """Noise-correlation and trial-consistency summaries per recording × condition."""
    keys = ["FileName", "Grp", "DIV", "condition"]
    net, cons = _plain_keys(net), _plain_keys(cons)   # join on equal-typed keys
    nc = net[net["epoch"] == "noise_corr"]
    cols = [c for c in ("meanNoiseCorr", "fracSigNoiseCorr") if c in nc.columns]
    out = nc[keys + cols].drop_duplicates(keys).set_index(keys)
    if cons is not None and not cons.empty:
        ccols = [c for c in RESPONSE_METRICS if c in cons.columns]
        out = out.join(cons.drop_duplicates(keys).set_index(keys)[ccols], how="outer")
    return out.reset_index()


def _violins(df, metrics: dict[str, str], out_dir: Path, *, series_col: str,
             series_order: list, series_colors, group_order, colors, fmt: str,
             limits: dict | None = None, label_suffix: str = "",
             metric_kde_limits: bool = True, n_electrodes: int | None = None,
             numbering: dict | None = None) -> int:
    """One figure per metric and layout. *numbering* is the full metric list
    whose positions number the files, so a metric absent from this batch does
    not renumber the rest (step 4B numbers by ``NETMET_REC_METRICS`` too)."""
    from meanap.pipeline.plotting_step4 import comparison_figure_stem, plot_half_violin_by_x

    n_written = 0
    for kind, suffix, by_age in (("group", "byGroup", False), ("DIV", "byAge", True)):
        dest = out_dir[kind]
        dest.mkdir(parents=True, exist_ok=True)
        order = list(numbering or metrics)
        for key, label in metrics.items():
            n = order.index(key) + 1
            plot_half_violin_by_x(
                df, key, label + label_suffix, kind,
                dest / f"{comparison_figure_stem(n, label, suffix, by_age)}.{fmt}",
                group_order=group_order, series_col=series_col, series_order=series_order,
                series_colors=list(series_colors), colors=colors,
                ylim=(limits or {}).get(key),
                kde_limits="auto" if metric_kde_limits else None, max_nodes=n_electrodes)
            n_written += 1
    return n_written


def plot_stim_group_comparisons(tables: dict[str, list[dict]], out_dir: Path, *,
                                group_order: list[str] | None = None, colors=None,
                                fmt: str = "png", n_electrodes: int | None = None,
                                log=print) -> int:
    """Draw every ``StimNetwork_GroupComparisons`` figure; returns how many."""
    from meanap.pipeline.plotting_step4 import comparison_timescale_folder

    net_rows = tables.get("StimNetwork_RecordingLevel.csv")
    if not net_rows:
        return 0
    net = _ordered(pd.DataFrame(net_rows), group_order)
    conditions = list(dict.fromkeys(net["condition"]))
    cond_colors = [CONDITION_COLORS[i % len(CONDITION_COLORS)] for i in range(len(conditions))]
    if len(conditions) > len(CONDITION_COLORS):
        log(f"  ! {len(conditions)} stimulation conditions but {len(CONDITION_COLORS)} "
            f"distinct colours; colours repeat — read the legend")
    root = Path(out_dir) / "StimNetwork_GroupComparisons"
    metrics = _network_metrics(net)
    common = dict(group_order=group_order, colors=colors, fmt=fmt, n_electrodes=n_electrodes)
    written = 0

    change = change_frame(net, list(metrics))
    for lag in sorted(net["lag_ms"].dropna().unique()):
        folder = comparison_timescale_folder(lag)
        written += _violins(
            change[change["lag_ms"] == lag], metrics,
            {"group": root / "1_ChangeByGroup" / folder, "DIV": root / "2_ChangeByAge" / folder},
            series_col="condition", series_order=conditions, series_colors=cond_colors,
            label_suffix=" (evoked - baseline)", metric_kde_limits=False,
            numbering=_all_network_metrics(), **common)
        epochs = net[(net["lag_ms"] == lag) & net["epoch"].isin(EPOCHS)]
        present = [e for e in EPOCHS if e in set(epochs["epoch"])]
        for cond in conditions:
            sub = epochs[epochs["condition"] == cond]
            if sub.empty:
                continue
            cdir = _safe(cond)
            written += _violins(
                sub, metrics,
                {"group": root / "3_EpochsByGroup" / cdir / folder,
                 "DIV": root / "4_EpochsByAge" / cdir / folder},
                series_col="epoch", series_order=present,
                series_colors=[EPOCH_COLORS[EPOCHS.index(e)] for e in present],
                numbering=_all_network_metrics(), **common)

    split_rows = tables.get("StimNetworkSplitHalf_RecordingLevel.csv")
    if split_rows:
        split = _ordered(split_frame(pd.DataFrame(split_rows)), group_order)
        for lag in sorted(split["lag_ms"].dropna().unique()):
            folder = comparison_timescale_folder(lag)
            sub = split[split["lag_ms"] == lag]
            written += _violins(
                sub, {k: v for k, v in SPLIT_METRICS.items() if k in sub.columns},
                {"group": root / "5_ResponseByGroup" / folder,
                 "DIV": root / "6_ResponseByAge" / folder},
                series_col="condition", series_order=conditions, series_colors=cond_colors,
                limits=_LIMITS, numbering=SPLIT_METRICS, **common)

    cons_rows = tables.get("StimConsistency_RecordingLevel.csv")
    resp = _ordered(response_frame(pd.DataFrame(net_rows),
                                   pd.DataFrame(cons_rows) if cons_rows else None),
                    group_order)
    written += _violins(
        resp, {k: v for k, v in RESPONSE_METRICS.items() if k in resp.columns},
        {"group": root / "5_ResponseByGroup", "DIV": root / "6_ResponseByAge"},
        series_col="condition", series_order=conditions, series_colors=cond_colors,
        limits=_LIMITS, numbering=RESPONSE_METRICS, **common)
    log(f"  Wrote {written} stimulation group-comparison figures to {root.name}/")
    return written


def _safe(name: str) -> str:
    """A condition name as a folder name: ``12>13`` → ``12 to 13``."""
    return (name.replace(">", " to ").replace("/", "-").replace("\\", "-")
            .replace(":", "-").strip() or "condition")
