"""One table of every tracked cell's metrics on every day, with its cell type.

This is the foundation for comparing cell types *across development*. The
pipeline's own group comparisons pool cells across recordings at each age, so
they show how the population changes. They cannot show how a cell changes,
because nothing in them knows which cell on DIV22 is which cell on DIV44.
Tracking knows that, and this module joins the two.

``TrackedCellMetrics.csv`` has one row per (tracked cell, day, lag), plus
``ActivityType`` on a multi-measure run. Each row carries:

* ``celltype_<marker>``: the cell's final call (``+``, ``-``, or blank for
  unknown), from ``cell_types_final.csv``. That is the recommendation, or a
  person's override.
* every column of ``TwoPhotonActivity_NodeLevel.csv`` for that cell-day.
* every column of ``NetworkActivity_NodeLevel.csv`` for that cell-day and lag.
  These are NaN when the cell was below the activity threshold that day.
* ``NDnorm``: node degree divided by (active cells − 1) in that recording.
  Raw degree is bounded by the network's size, which changes from day to day.

**The network metrics are the pipeline's whole-network node metrics, on
purpose.** The tracking module computes its own graph measures, but on a
thresholded subgraph of the tracked cells only. Those suit its question
(does structure persist?) but would not be comparable with any other CAT-NAP
figure.

Two joins have to be made, and both can fail silently, so both are checked:

**Recording → pipeline ``FileName``.** A run that tracked from raw folder
names can call the same recording ``20230601_13_OPME230505_…_DIV27`` where
the pipeline says ``OPME230505_13_…_DIV27``: the date is added and the tokens
are reordered. The name is matched exactly first. Failing that, it is matched
on its set of tokens without the date, plus the DIV (:func:`name_key`). A key
that two pipeline recordings share is ambiguous, so it matches neither.

**Tracking position → ``Channel``.** Tracking indexes a day's cells by
position among the iscell ROIs; the pipeline's ``Channel`` is raw ROI index
+ 1. A payload that stores the raw indices (``sessions[k].roi``) gives the
mapping directly. Otherwise the recording's channel list stands in, because
CAT-NAP's channels *are* the iscell ROIs in order. That is only trusted when
the counts agree.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from meanap.catnap.tracking.chains import DATE_RE, DIV_RE

#: Written into the ``CellTracking`` folder.
TRACKED_METRICS_CSV = "TrackedCellMetrics.csv"

#: Pipeline tables, relative to the run folder.
ACTIVITY_CSV = Path("2_NeuronalActivity") / "TwoPhotonActivity_NodeLevel.csv"
NETWORK_CSV = Path("4_NetworkActivity") / "NetworkActivity_NodeLevel.csv"

#: Prefix of the per-marker cell-type columns.
CELLTYPE_PREFIX = "celltype_"

#: Network columns with no meaning across days or recordings. A module id is a
#: label local to one recording's partition; the active index is bookkeeping.
_DROP_NETWORK = ("Ci", "activeChannelIndex")

#: The table's key columns, in order; the ``celltype_*`` columns follow them.
_LEAD = ("chain", "cluster", "nDays", "Grp", "DIV", "DIVrecorded", "dayVia",
         "FileName", "Channel", "ActivityType", "Lag")


def name_key(name: str) -> tuple[frozenset, int | None]:
    """A recording name, reduced to what identifies it irrespective of order.

    The tokens other than the 8-digit date and the ``DIV<n>`` token, as a set,
    plus the DIV. The DIV is ``None`` when the name has none.
    """
    tokens = str(name).split("_")
    div = next((int(m.group(1)) for t in tokens if (m := DIV_RE.match(t))), None)
    kept = frozenset(t for t in tokens if not DATE_RE.match(t) and not DIV_RE.match(t))
    return kept, div


def chain_key(chain: str, div: int) -> tuple[frozenset, int]:
    """The :func:`name_key` a chain's recording on *div* would have."""
    return name_key(f"{chain}_DIV{int(div)}")[0], int(div)


@dataclass
class FileNameIndex:
    """Find the pipeline recording a tracking session refers to."""

    exact: set[str]
    by_key: dict[tuple[frozenset, int | None], str]

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "FileNameIndex":
        names = set(map(str, names))
        by_key: dict = {}
        ambiguous = set()
        for n in names:
            k = name_key(n)
            if k in by_key:
                ambiguous.add(k)
            by_key[k] = n
        for k in ambiguous:
            del by_key[k]
        return cls(names, by_key)

    def find(self, recording: str | None, chain: str, div: int) -> str | None:
        if recording and recording in self.exact:
            return recording
        if recording:
            hit = self.by_key.get(name_key(recording))
            if hit:
                return hit
        return self.by_key.get(chain_key(chain, div))


@dataclass
class BuildReport:
    """What could not be joined, so a thin table is never a mystery."""

    chains: int = 0
    cell_days: int = 0
    rows: int = 0
    #: ``chain DIV<n>`` days whose recording is not in the pipeline tables.
    unmatched_days: list[str] = field(default_factory=list)
    #: Days whose cells could not be mapped to channels, with why.
    unmapped_days: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"Tracked cell metrics: {self.rows} rows from {self.cell_days} "
               f"cell-days in {self.chains} chains."]
        if self.unmatched_days:
            out.append(f"  {len(self.unmatched_days)} tracked days have no recording "
                       f"in the pipeline tables, e.g. {self.unmatched_days[0]}")
        for d in self.unmapped_days:
            out.append(f"  not mapped to channels: {d}")
        return out


def read_final_calls(path: str | Path) -> dict[tuple[str, int], dict[str, str]]:
    """``(chain, cluster) → {marker: "+" | "-" | ""}`` from ``cell_types_final.csv``."""
    path = Path(path)
    out: dict = {}
    if not path.is_file():
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out.setdefault((r["chain"], int(r["cluster"])), {})[r["marker"]] = r.get("final", "")
    return out


def _session_channels(session: dict, channels: np.ndarray | None) -> tuple[np.ndarray | None, str]:
    """The pipeline ``Channel`` of each tracking position on one day, and why not."""
    n = len(session["cluster"])
    if session.get("roi") is not None:
        roi = np.asarray(session["roi"], dtype=int)
        if len(roi) != n:
            return None, f"{len(roi)} stored ROI ids for {n} cells"
        return roi + 1, ""
    if channels is None:
        return None, "recording has no rows in the activity table"
    if len(channels) != n:
        return None, f"{len(channels)} channels in the run but {n} cells tracked"
    return np.asarray(channels, dtype=int), ""


def _day_source(cell: dict | None, div: int) -> str:
    """How tracking reached this cell on this day."""
    if cell is None:
        return "roicat"
    if div in set(cell.get("mergedDivs", [])):
        return "merged"
    if div in set(cell.get("rescuedDivs", [])):
        return "rescued"
    return "roicat"


def tracked_cell_metrics(
    payloads: Iterable[dict],
    activity: pd.DataFrame,
    network: pd.DataFrame | None = None,
    final_calls: dict | None = None,
    *,
    min_days: int = 2,
    report: BuildReport | None = None,
) -> pd.DataFrame:
    """The joined table, from tracking payloads and the pipeline's node tables.

    ``payloads`` are the ``CellTracking/payload/*.json`` dicts. ``activity`` and
    ``network`` are the run's node-level frames (``network`` may be ``None``
    or empty, as on a run with no network step). ``final_calls`` comes from
    :func:`read_final_calls`.

    Every cluster present on at least ``min_days`` days is included, read
    from the sessions' cluster arrays rather than ``payload["cells"]``,
    since the viewer may keep only a sample of the cells.
    """
    report = report if report is not None else BuildReport()
    final_calls = final_calls or {}
    network = network if network is not None else pd.DataFrame()

    index = FileNameIndex.from_names(activity["FileName"].unique() if len(activity) else [])
    channels_of = ({f: sub["Channel"].to_numpy(dtype=int)
                    for f, sub in activity.groupby("FileName", sort=False)}
                   if "ActivityType" not in activity.columns else
                   # every measure lists the same cells; take the first
                   {f: sub.loc[sub["ActivityType"] == sub["ActivityType"].iloc[0],
                               "Channel"].to_numpy(dtype=int)
                    for f, sub in activity.groupby("FileName", sort=False)})

    markers = sorted({m for calls in final_calls.values() for m in calls})
    keys: list[dict] = []
    for payload in payloads:
        chain = payload.get("chainKey") or payload.get("chain")
        sessions = payload["sessions"]
        report.chains += 1
        days_of: dict[int, int] = {}
        for s in sessions:
            for c in {int(c) for c in s["cluster"] if c >= 0}:
                days_of[c] = days_of.get(c, 0) + 1
        cells = {int(c["cluster"]): c for c in payload.get("cells", [])}

        for s in sessions:
            div = int(s["div"])
            filename = index.find(s.get("recording"), chain, div)
            if filename is None:
                report.unmatched_days.append(f"{chain} DIV{div}")
                continue
            chans, why = _session_channels(s, channels_of.get(filename))
            if chans is None:
                report.unmapped_days.append(f"{chain} DIV{div} ({filename}): {why}")
                continue
            for pos, cluster in enumerate(s["cluster"]):
                cluster = int(cluster)
                if cluster < 0 or days_of.get(cluster, 0) < min_days:
                    continue
                row = {"chain": chain, "cluster": cluster,
                       "nDays": days_of[cluster], "DIVrecorded": div,
                       "dayVia": _day_source(cells.get(cluster), div),
                       "FileName": filename, "Channel": int(chans[pos])}
                calls = final_calls.get((chain, cluster), {})
                for m in markers:
                    row[CELLTYPE_PREFIX + m] = calls.get(m, "") or ""
                keys.append(row)
    report.cell_days = len(keys)
    if not keys:
        return pd.DataFrame()

    out = pd.DataFrame(keys).merge(activity, on=["FileName", "Channel"], how="left",
                                   validate="one_to_many")
    if not network.empty:
        net = network.drop(columns=[c for c in _DROP_NETWORK if c in network.columns])
        on = ["FileName", "Channel"] + (["ActivityType"] if "ActivityType" in net.columns
                                        and "ActivityType" in out.columns else [])
        # Grp/DIV are the activity table's; the network repeats them
        net = net.drop(columns=[c for c in ("Grp", "DIV") if c in net.columns])
        lags = net["Lag"].dropna().unique()
        if "ND" in net.columns:
            # The table lists active nodes only, so its row count is the network
            # size. Raw degree falls for every cell when the network shrinks, which
            # a trajectory would otherwise read as each cell losing partners.
            size = net.groupby(on[:1] + on[2:] + ["Lag"])["Channel"].transform("size")
            net.insert(net.columns.get_loc("ND") + 1, "NDnorm",
                       net["ND"] / (size - 1).where(size > 1))
        # every cell-day appears under every lag, inactive or not, so a cell
        # dropping below threshold shows as NaN rather than vanishing
        out = out.merge(pd.DataFrame({"Lag": lags}), how="cross")
        out = out.merge(net, on=on + ["Lag"], how="left", validate="one_to_one")

    lead = [c for c in _LEAD if c in out.columns]
    typed = [c for c in out.columns if c.startswith(CELLTYPE_PREFIX)]
    rest = [c for c in out.columns if c not in lead and c not in typed]
    out = out[lead + typed + rest].sort_values(
        [c for c in ("chain", "cluster", "DIVrecorded", "ActivityType", "Lag")
         if c in out.columns], kind="stable").reset_index(drop=True)
    report.rows = len(out)
    return out


def build_for_run(
    tracking_dir: str | Path,
    run_dir: str | Path | None = None,
    *,
    write: bool = True,
    log: Callable[[str], None] = lambda _msg: None,
) -> pd.DataFrame:
    """Build (and by default write) the table for a ``CellTracking`` folder.

    ``run_dir`` defaults to the folder holding ``CellTracking``. The path is
    not resolved, so a symlinked ``CellTracking`` still finds the run it sits in.
    """
    from meanap.catnap.tracking.celltypes import FINAL_CSV

    root = Path(tracking_dir)
    run = Path(run_dir) if run_dir is not None else root.parent
    if not (run / ACTIVITY_CSV).is_file():
        log(f"Tracked cell metrics: no {ACTIVITY_CSV} in {run}; skipped.")
        return pd.DataFrame()
    activity = pd.read_csv(run / ACTIVITY_CSV)
    network = pd.read_csv(run / NETWORK_CSV) if (run / NETWORK_CSV).is_file() else None
    payloads = (json.loads(p.read_text()) for p in sorted((root / "payload").glob("*.json")))
    report = BuildReport()
    df = tracked_cell_metrics(payloads, activity, network,
                              read_final_calls(root / FINAL_CSV), report=report)
    if write:
        df.to_csv(root / TRACKED_METRICS_CSV, index=False)
    for line in report.lines():
        log(line)
    return df


def refresh_cell_types(tracking_dir: str | Path, final_csv: str | Path | None = None) -> bool:
    """Rewrite only the ``celltype_*`` columns of an existing table.

    This runs after every override the viewer saves. A full rebuild would
    re-read every payload, which is too slow to do per click. The calls are
    the only thing a decision changes. Returns whether a table was updated.
    """
    from meanap.catnap.tracking.celltypes import FINAL_CSV

    root = Path(tracking_dir)
    path = root / TRACKED_METRICS_CSV
    if not path.is_file():
        return False
    df = read_table(path)
    calls = read_final_calls(final_csv if final_csv is not None else root / FINAL_CSV)
    df = apply_final_calls(df, calls)
    tmp = path.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)
    return True


def read_table(path: str | Path) -> pd.DataFrame:
    """Read ``TrackedCellMetrics.csv`` with its text columns kept as text.

    A blank cell-type call has to stay ``""`` (unknown) rather than turn into
    NaN, and a lag like ``1000mslag`` must not be parsed as anything else.
    """
    path = Path(path)
    text = {c: str for c in _celltype_columns(path)}
    text.update({"Lag": str, "ActivityType": str, "chain": str, "FileName": str,
                 "dayVia": str})
    df = pd.read_csv(path, dtype=text, keep_default_na=False, na_values=[""])
    for c in _celltype_columns(path):
        df[c] = df[c].fillna("")
    return df


def apply_final_calls(df: pd.DataFrame, calls: dict) -> pd.DataFrame:
    """Replace the ``celltype_*`` columns with *calls* (:func:`read_final_calls`).

    The viewer uses this to show decisions saved since the table was written,
    which on a bundle is the only way they can appear, since a bundle is never
    rewritten.
    """
    df = df.drop(columns=[c for c in df.columns if c.startswith(CELLTYPE_PREFIX)])
    markers = sorted({m for c in calls.values() for m in c})
    # straight after the key columns, where the build puts them
    pos = max(df.columns.get_loc(c) for c in _LEAD if c in df.columns) + 1
    keys = list(zip(df["chain"], df["cluster"].astype(int)))
    for k, m in enumerate(markers):
        df.insert(pos + k, CELLTYPE_PREFIX + m,
                  [calls.get(key, {}).get(m, "") or "" for key in keys])
    return df


def _celltype_columns(path: Path) -> list[str]:
    with open(path, newline="") as fh:
        header = next(csv.reader(fh), [])
    return [c for c in header if c.startswith(CELLTYPE_PREFIX)]


def main(argv=None) -> int:
    """Build ``TrackedCellMetrics.csv`` for a run that has cell tracking.

        python -m meanap.catnap.tracking.development <run>[/CellTracking]
    """
    import argparse

    ap = argparse.ArgumentParser(prog="meanap.catnap.tracking.development",
                                 description=main.__doc__.split("\n")[0])
    ap.add_argument("path", type=Path, help="a run folder, or its CellTracking folder")
    ap.add_argument("--run", type=Path, default=None,
                    help="the run folder, when CellTracking is not inside it")
    args = ap.parse_args(argv)
    root = args.path
    if not (root / "payload").is_dir() and (root / "CellTracking" / "payload").is_dir():
        root = root / "CellTracking"
    if not (root / "payload").is_dir():
        ap.error(f"{args.path} has no payload/ folder")
    build_for_run(root, args.run, log=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
