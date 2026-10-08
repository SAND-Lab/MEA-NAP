"""Cell types compared across groups and ages, one cell type per series.

This is the cross-sectional counterpart of
:mod:`meanap.catnap.tracking.development_plots`. Every cell on every day
counts here, tracked or not. The tracked analysis follows cells; this one
shows the population at each age. The two must not disagree about which cell
is which type, so this module uses the same three-valued calls, the same
split definitions and the same membership function.

**Calls.** For each recording, the cell-type file is found where the pipeline
looks for it (an explicit folder, then ``twop_cell_type_file``, then
``rawData/<recording>/``). It is matched by name, or by name tokens when the
file carries the raw recording name, which has a date the pipeline's name
lacks. It is then read as positive / negative / unknown. A tracked cell takes
its *final* call instead (the recommendation across its days, or a person's
decision), so a cell judged mislabelled on one day is not counted under that
day's label.

**Figures**, per split definition (one per marker, plus the run's groups):

* activity and network node metrics with cell type as the series in each
  panel. Network metrics are per lag.
* the same metrics as recording means per cell type. That is n = recordings,
  the right unit for comparing groups: cells from one culture are not
  independent samples.

They are written beside the pipeline's own comparisons, under
``2B_GroupComparisons/6_CellTypeComparisons/`` and
``4B_GroupComparisons/9_CellTypeComparisons/<Lag>/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from meanap.catnap.tracking.development import (
    ACTIVITY_CSV, CELLTYPE_PREFIX, NETWORK_CSV, TRACKED_METRICS_CSV, FileNameIndex,
    read_final_calls,
)

CALLS_CSV = "CellTypeCalls.csv"
ACTIVITY_DIR = Path("2_NeuronalActivity") / "2B_GroupComparisons" / "6_CellTypeComparisons"
NETWORK_DIR = Path("4_NetworkActivity") / "4B_GroupComparisons" / "9_CellTypeComparisons"
#: What one cell is here: a cell on one day.
UNIT = ("FileName", "Channel")

_SIGN = {1: "+", -1: "-", 0: ""}


def _label_files(folders: list[Path]) -> FileNameIndex:
    """Every flat label file in *folders*, findable by token-matched name."""
    names = []
    for folder in folders:
        if folder.is_dir():
            names += [p.stem for p in folder.iterdir()
                      if p.is_file() and p.suffix.lower() in (".csv", ".xlsx", ".xls")]
    return FileNameIndex.from_names(names)


def cell_calls(
    channels: dict[str, np.ndarray],
    label_folders: Iterable,
    *,
    tracking_dir: str | Path | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> pd.DataFrame:
    """``FileName, Channel, celltype_<marker>…, callSource``, one row per cell-day.

    *channels* maps each recording to its ``Channel`` ids (raw suite2p index + 1,
    the pipeline's convention).
    """
    from meanap.catnap.tracking.celltypes import (
        find_label_file, place_labels, read_marker_labels,
    )

    folders = [Path(f) for f in label_folders if f]
    index = _label_files(folders)
    parts = []
    for rec, chans in channels.items():
        chans = np.asarray(chans, dtype=int)
        path = find_label_file(rec, folders)
        if path is None:
            hit = index.find(rec, "", -1)
            path = find_label_file(hit, folders) if hit else None
        if path is None:
            continue
        try:
            placed = place_labels(read_marker_labels(path), chans - 1,
                                  recording=rec, source=path.name)
        except Exception as e:      # one bad file must not cost the rest
            log(f"  cell types: {path.name} not used for {rec}: {e}")
            continue
        part = pd.DataFrame({"FileName": rec, "Channel": chans})
        for m, st in placed.states.items():
            part[CELLTYPE_PREFIX + m] = [_SIGN[int(v)] for v in st]
        part["callSource"] = "label file"
        parts.append(part)
    if not parts:
        return pd.DataFrame()
    calls = pd.concat(parts, ignore_index=True)
    calls = calls.fillna({c: "" for c in calls.columns if c.startswith(CELLTYPE_PREFIX)})
    if tracking_dir is not None:
        calls = _apply_tracked_calls(calls, Path(tracking_dir), log)
    return calls


def read_calls(path: str | Path) -> pd.DataFrame:
    """Read ``CellTypeCalls.csv``, keeping blank calls as ``""`` (unknown)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["Channel"] = df["Channel"].astype(int)
    return df


def _apply_tracked_calls(calls: pd.DataFrame, root: Path,
                         log: Callable[[str], None]) -> pd.DataFrame:
    """Give tracked cells their final call, on every day they were tracked.

    The cell-day → tracked cell link comes from ``TrackedCellMetrics.csv``,
    which already solved the naming and ID-space joins. A blank final call (a
    tie nobody has decided) makes that marker unknown on those days. The day's
    own label is exactly what is in dispute.
    """
    from meanap.catnap.tracking.celltypes import FINAL_CSV

    table, final = root / TRACKED_METRICS_CSV, root / FINAL_CSV
    if not table.is_file() or not final.is_file():
        return calls
    link = (pd.read_csv(table, usecols=["chain", "cluster", "FileName", "Channel"],
                        dtype={"chain": str, "FileName": str})
            .drop_duplicates(["FileName", "Channel"]))
    finals = read_final_calls(final)
    markers = sorted({m for c in finals.values() for m in c})
    calls = calls.copy()
    for m in markers:
        if CELLTYPE_PREFIX + m not in calls:
            calls[CELLTYPE_PREFIX + m] = ""
    merged = calls[["FileName", "Channel"]].reset_index().merge(link, on=["FileName", "Channel"])
    for row in merged.itertuples(index=False):
        fc = finals.get((row.chain, int(row.cluster)))
        if fc is None:
            continue
        for m in markers:
            if m in fc:
                calls.at[row.index, CELLTYPE_PREFIX + m] = fc[m] or ""
        calls.at[row.index, "callSource"] = "tracked cell, final call"
    log(f"  cell types: {len(merged)} cell-days take their tracked cell's final call")
    return calls


def _typed(df: pd.DataFrame, definition) -> tuple[pd.DataFrame, list[str]]:
    from meanap.catnap.tracking import development_plots as dp

    members = dp.memberships(df, definition, unit=UNIT)
    if len(members) < 2:
        return pd.DataFrame(), []
    parts = [df[mask].assign(CellType=name) for name, mask in members.items()]
    return pd.concat(parts, ignore_index=True), list(members)


def recording_means(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Mean of each metric per (recording, cell type): n becomes recordings."""
    keys = [c for c in ("FileName", "Grp", "DIV", "CellType") if c in df.columns]
    out = df.groupby(keys, sort=False)[metrics].mean().reset_index()
    out["nCells"] = df.groupby(keys, sort=False).size().to_numpy()
    return out


def _plot_block(df: pd.DataFrame, metrics: dict[str, str], types: list[str],
                where: Path, order, fmt: str, log) -> int:
    """Node-level and recording-level figures for one block; returns how many."""
    from meanap.catnap.tracking.development_plots import TYPE_COLOURS
    from meanap.pipeline.plotting_step4 import plot_half_violin_by_x

    colours = [TYPE_COLOURS[i % len(TYPE_COLOURS)] for i in range(len(types))]
    rec = recording_means(df, list(metrics))
    n = 0
    for level, data, suffix in (("Node", df, "_node"), ("Recordings", rec, "")):
        for x_kind, split, stem in (("group", "ByGroup", "byGroup"), ("DIV", "ByAge", "byDIV")):
            folder = where / f"{level}{split}"
            folder.mkdir(parents=True, exist_ok=True)
            for key, label in metrics.items():
                if data[key].dropna().empty:
                    continue
                try:
                    plot_half_violin_by_x(
                        data, key, label + (" (recording mean)" if level == "Recordings" else ""),
                        x_kind, folder / f"{key}_{stem}{suffix}.{fmt}",
                        group_order=order, series_col="CellType", series_order=types,
                        series_colors=colours)
                    n += 1
                except Exception as e:
                    log(f"  {folder.name}/{key}: {e}")
    return n


def plot_cell_type_comparisons(
    run_dir: str | Path,
    *,
    out_dir: str | Path | None = None,
    label_folders: Iterable = (),
    group_spec=None,
    group_order: list | None = None,
    timescale: str = "lag",
    activity: str = "peaks",
    fmt: str = "png",
    log: Callable[[str], None] = lambda _m: None,
) -> pd.DataFrame:
    """Write every cross-sectional cell-type figure for a finished run.

    Reads only the run's node tables, its label files and (if present) its
    cell tracking, so it can be re-run at any time, for instance after
    cell-type decisions. When label files are found, the calls are written to
    ``2_NeuronalActivity/CellTypeCalls.csv``. When none are (a bundle carries
    no raw data), that saved file is used instead, with the tracked cells'
    current final calls applied on top. *out_dir* (default: the run itself)
    is where figures go, so a read-only bundle can be rendered elsewhere.
    """
    from threadpoolctl import threadpool_limits

    # Hundreds of small KDE figures: left alone, BLAS spreads each one over
    # every core and spends far more on coordination than on the work (on the
    # Yin run, 43 CPU-minutes for 3 wall-minutes).
    with threadpool_limits(1):
        return _plot_cell_type_comparisons(
            Path(run_dir), Path(out_dir) if out_dir is not None else Path(run_dir),
            label_folders=label_folders, group_spec=group_spec,
            group_order=group_order, timescale=timescale, activity=activity,
            fmt=fmt, log=log)


def _plot_cell_type_comparisons(run: Path, out: Path, *, label_folders, group_spec, group_order,
                                timescale, activity, fmt, log) -> pd.DataFrame:
    from meanap.catnap.tracking import development_plots as dp
    from meanap.pipeline.plotting_step4 import _timescale_group_folder

    if not (run / ACTIVITY_CSV).is_file():
        log(f"Cell-type comparisons: no {ACTIVITY_CSV}; skipped.")
        return pd.DataFrame()
    act = pd.read_csv(run / ACTIVITY_CSV, dtype={"FileName": str, "ActivityType": str})
    net = (pd.read_csv(run / NETWORK_CSV, dtype={"FileName": str, "Lag": str,
                                                 "ActivityType": str})
           if (run / NETWORK_CSV).is_file() else pd.DataFrame())
    # every measure lists the same cells, so the first is enough to label them
    first = act if "ActivityType" not in act else act[act["ActivityType"] == act["ActivityType"].iloc[0]]
    channels = {f: g["Channel"].to_numpy() for f, g in first.groupby("FileName", sort=False)}
    tracking = run / "CellTracking"
    tracking = tracking if (tracking / "payload").is_dir() else None
    calls = cell_calls(channels, label_folders, tracking_dir=tracking, log=log)
    saved = run / "2_NeuronalActivity" / CALLS_CSV
    if not calls.empty:
        if out == run:
            calls.to_csv(saved, index=False)
    elif saved.is_file():
        calls = read_calls(saved)
        if tracking is not None:
            calls = _apply_tracked_calls(calls, tracking, log)
    if calls.empty:
        log("Cell-type comparisons: no recording has a cell-type file; skipped.")
        return calls
    log(f"Cell-type comparisons: {calls['FileName'].nunique()} recordings labelled.")

    labels = dp._labels(activity)
    measures = (list(dict.fromkeys(act["ActivityType"].dropna()))
                if "ActivityType" in act else [None])
    total = 0
    for definition in dp.type_definitions(dp.markers_in(calls), group_spec):
        for measure in measures:
            a = act if measure is None else act[act["ActivityType"] == measure]
            df = a.merge(calls, on=["FileName", "Channel"], how="inner")
            typed, types = _typed(df, definition)
            if not types:
                log(f"  {definition.name}: fewer than two types with "
                    f"{dp.MIN_TYPE_CELLS}+ cells; skipped.")
                break
            sub = "" if measure is None or len(measures) == 1 else measure
            metrics = {k: labels.get(k, k) for k in a.columns
                       if k not in ("FileName", "Grp", "DIV", "Channel", "ActivityType")
                       and pd.api.types.is_numeric_dtype(a[k])}
            total += _plot_block(typed, metrics, types,
                                 out / ACTIVITY_DIR / sub / dp._safe(definition.name),
                                 group_order, fmt, log)
            if net.empty:
                continue
            n = net if measure is None or "ActivityType" not in net else \
                net[net["ActivityType"] == measure]
            n = n.drop(columns=[c for c in ("Ci", "activeChannelIndex") if c in n.columns])
            if "ND" in n.columns:
                # as in the tracked table: raw degree is bounded by how many cells
                # were active, which differs between recordings far more than
                # between the cell types being compared
                size = n.groupby(["FileName", "Lag"])["Channel"].transform("size")
                n = n.assign(NDnorm=n["ND"] / (size - 1).where(size > 1))
            for lag, nl in n.groupby("Lag", sort=False):
                dfn = nl.merge(calls, on=["FileName", "Channel"], how="inner")
                typed_n, types_n = _typed(dfn, definition)
                if not types_n:
                    continue
                nmetrics = {k: labels.get(k, k) for k in nl.columns
                            if k not in ("FileName", "Grp", "DIV", "Channel", "Lag",
                                         "ActivityType", "NdCartDiv")
                            and pd.api.types.is_numeric_dtype(nl[k])}
                total += _plot_block(typed_n, nmetrics, types_n,
                                     out / NETWORK_DIR / sub / _timescale_group_folder(lag, timescale)
                                     / dp._safe(definition.name), group_order, fmt, log)
        log(f"  {definition.name} done")
    log(f"Cell-type comparisons: {total} figures.")
    return calls


def main(argv=None) -> int:
    """Cross-sectional cell-type figures for a finished CAT-NAP run.

        python -m meanap.catnap.celltype_comparisons <run> --labels <folder>
    """
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="meanap.catnap.celltype_comparisons",
                                 description=main.__doc__.split("\n")[0])
    ap.add_argument("run", type=Path)
    ap.add_argument("--labels", type=Path, action="append", default=[],
                    help="folder of <recording>.csv cell-type files (repeatable)")
    ap.add_argument("--groups", default=None, help="'E/I' or a JSON {name: expression}")
    ap.add_argument("--group-order", nargs="+", default=None)
    ap.add_argument("--timescale", default="lag", choices=("lag", "bin"))
    args = ap.parse_args(argv)
    groups = args.groups
    if groups and groups.strip().startswith("{"):
        groups = json.loads(groups)
    plot_cell_type_comparisons(args.run, label_folders=args.labels, group_spec=groups,
                               group_order=args.group_order, timescale=args.timescale,
                               log=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
