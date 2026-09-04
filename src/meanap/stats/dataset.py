"""Assembling the one table every statistical analysis in step 5 is run on.

MATLAB's ``doStats``/``doClassification``/``doLDA`` each take a
``recordingLevelData`` table that ``MEApipeline.m`` builds inline, and each
re-derives the things they need from it — which columns are metrics, which
recordings belong to the same culture, which rows are usable. That derivation
is the part most worth getting right and least worth writing three times, so it
lives here once and the analyses take a :class:`StatsDataset`.

Two things this adds over the MATLAB version:

**Culture identity.** A recording is not an independent sample. The same
culture is imaged at several DIVs, so its rows are repeated measures, and both
the mixed models (:mod:`meanap.stats.comparisons`) and the cross-validation
splits (:mod:`meanap.stats.decoding`) need to know which rows share a culture —
the models to put a random intercept on it, the splits to keep a culture out of
train and test at once. MATLAB's ``doStats`` derives something similar for its
RM-ANOVA (first *n* underscore-separated tokens of the name); ``doClassification``
derives nothing and cross-validates as if all rows were independent, which
leaks. See :func:`derive_culture_ids`.

**One table, both pipelines.** Network metrics and activity metrics are written
to separate CSVs by separate steps, and the two-photon (CAT-NAP) pipeline names
its activity file differently from the ephys one. A question like "which
features separate the genotypes" is not a question about one of those files, so
they are merged on ``FileName`` into a single feature table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "META_COLUMNS",
    "StatsDataset",
    "derive_culture_ids",
    "load_dataset",
    "metric_labels",
]

#: Columns that identify a row rather than measure it. Never treated as
#: features, never tested. ``cartographyBoundaries`` and ``activeChannelIndex``
#: are stringified tuples/arrays rather than scalars, so they are excluded here
#: as well as by the numeric-dtype check — being explicit documents *why*.
META_COLUMNS = frozenset({
    "FileName", "Grp", "DIV", "Lag", "Channel", "Culture", "ActivityType",
    "eGrp", "AgeDiv", "recordingName",
    "cartographyBoundaries", "activeChannelIndex",
})

#: A DIV token in a recording name (``..._DIV21``). Dropped when deriving a
#: culture ID: it is the thing that varies *within* a culture.
_DIV_TOKEN = re.compile(r"^DIV[_-]?\d+\.?\d*$", re.IGNORECASE)

#: A recording-date token (``20240719``, or ``240719`` when the century is left
#: off). Also varies within a culture — the same culture imaged a week later
#: carries a different date but is the same culture.
_DATE_TOKEN = re.compile(r"^(20\d{6}|\d{6})$")

#: Where the recording-level tables live in an output folder or opened bundle.
#: The activity file has two names because the ephys and two-photon pipelines
#: each write their own; a run has one or the other, never both.
_NETWORK_REC = "4_NetworkActivity/NetworkActivity_RecordingLevel.csv"
_NETWORK_NODE = "4_NetworkActivity/NetworkActivity_NodeLevel.csv"
_ACTIVITY_REC = (
    "2_NeuronalActivity/TwoPhotonActivity_RecordingLevel.csv",
    "2_NeuronalActivity/NeuronalActivity_RecordingLevel.csv",
)
_ACTIVITY_NODE = (
    "2_NeuronalActivity/TwoPhotonActivity_NodeLevel.csv",
    "2_NeuronalActivity/NeuronalActivity_NodeLevel.csv",
)


def derive_culture_ids(names: "pd.Series", *, strip_date: bool = True) -> "pd.Series":
    """Map recording names to the culture each was recorded from.

    Recording names are built from underscore-separated tokens, and the tokens
    that vary across a culture's timepoints are its age and its recording date:
    ``OPME240607_6_20240719_P1_pup1B_WT_MOI50000_DIV42`` and
    ``OPME240607_6_20240711_P1_pup1B_WT_MOI50000_DIV34`` are two views of one
    culture. Dropping both token kinds leaves an identifier stable across the
    timecourse. For MEA names (``MPT200114_2A_DIV21``) there is no date token
    and dropping the DIV alone is enough, which is why *strip_date* only
    removes tokens that unambiguously look like dates.

    Returns the names unchanged where this collapses nothing — a naming scheme
    this heuristic does not understand should leave every recording its own
    culture (the analysis is then merely conservative) rather than silently
    merge unrelated recordings into one.
    """
    def collapse(name: str) -> str:
        tokens = str(name).split("_")
        kept = [
            tok for tok in tokens
            if not _DIV_TOKEN.match(tok)
            and not (strip_date and _DATE_TOKEN.match(tok))
        ]
        return "_".join(kept) if kept else str(name)

    derived = names.map(collapse)
    # A heuristic that separates nothing is worse than no heuristic: if every
    # name still maps to itself we have learned nothing, but we have also not
    # wrongly merged anything, so hand back the original names.
    return derived if derived.nunique() < names.nunique() else names.astype(str)


def metric_labels() -> dict[str, str]:
    """Display names for every metric either pipeline can produce.

    Merged from the dicts the plotting modules already use, so a metric is
    named the same on a stats figure as on the group-comparison figure it sits
    beside. Metrics with no entry fall back to their column name.
    """
    from meanap.catnap.group_plots import TWOP_NODE_METRICS, TWOP_REC_METRICS
    from meanap.pipeline.plotting_step4 import NETMET_NODE_METRICS, NETMET_REC_METRICS

    labels: dict[str, str] = {}
    for src in (NETMET_REC_METRICS, NETMET_NODE_METRICS,
                TWOP_REC_METRICS, TWOP_NODE_METRICS):
        labels.update(src)
    labels.setdefault("CC_rawMean", "Clustering Coefficient (raw)")
    labels.setdefault("PL_raw", "Path Length (raw)")
    labels.setdefault("NCpn1count", "Node Cartography R1 (count)")
    labels.setdefault("Hub3", "Hub Nodes (3 criteria)")
    labels.setdefault("Hub4", "Hub Nodes (4 criteria)")
    labels.setdefault("aveControlTop25", "Top 25% Average Controllability")
    labels.setdefault("modalControlPrctLessThanThreshold",
                      "Modal Controllability Below Threshold (%)")
    labels.setdefault("FRstd", "Event Rate SD (Hz)")
    labels.setdefault("FRsem", "Event Rate SEM (Hz)")
    return labels


@dataclass
class StatsDataset:
    """A feature table plus the column roles the analyses need to read it.

    ``table`` is one row per recording (per lag, when a run has several) with
    ``FileName``/``Grp``/``DIV``/``Lag``/``Culture`` and one column per metric.
    ``metrics`` is the ordered subset of columns that are actually features:
    numeric, not metadata, and not constant.
    """

    table: pd.DataFrame
    metrics: list[str]
    labels: dict[str, str] = field(default_factory=dict)
    group_col: str = "Grp"
    age_col: str = "DIV"
    culture_col: str = "Culture"
    name_col: str = "FileName"
    #: Which measure of activity a row was computed from — CAT-NAP only, and
    #: only when a run analysed more than one (see
    #: :mod:`meanap.catnap.activities`). Absent from the table for every ephys
    #: run and every single-measure calcium run, which is why nothing here may
    #: assume the column exists.
    activity_col: str = "ActivityType"
    level: str = "recording"
    source: Path | None = None

    # ── description ──────────────────────────────────────────────────────────

    @property
    def groups(self) -> list[str]:
        """Group levels in the order later analyses should present them."""
        return list(pd.unique(self.table[self.group_col].dropna()))

    @property
    def ages(self) -> list[float]:
        return sorted(pd.unique(self.table[self.age_col].dropna()))

    @property
    def lags(self) -> list:
        if "Lag" not in self.table.columns:
            return []
        return list(pd.unique(self.table["Lag"].dropna()))

    @property
    def activities(self) -> list:
        """Measures of activity present, or ``[]`` when the run used only one.

        Empty rather than one-element for a single-measure run: the caller's
        question is "is there a measure axis to analyse along", and a run with
        one measure has nothing to compare, exactly as a run with no ``Lag``
        column has no lag axis.
        """
        if self.activity_col not in self.table.columns:
            return []
        found = list(pd.unique(self.table[self.activity_col].dropna()))
        return found if len(found) > 1 else []

    @property
    def activity(self):
        """The single measure of activity these rows were computed from.

        ``None`` when the table has no measure column (every ephys run) or
        carries more than one — the two cases where "this dataset's measure" is
        not a question with an answer. Distinct from :attr:`activities`, which
        reports the axis rather than a position on it.
        """
        if self.activity_col not in self.table.columns:
            return None
        found = list(pd.unique(self.table[self.activity_col].dropna()))
        return found[0] if len(found) == 1 else None

    def label(self, metric: str) -> str:
        return self.labels.get(metric, metric)

    def describe(self) -> dict:
        """A summary of the design, for the report header and the GUI."""
        t = self.table
        per_culture = t.groupby(self.culture_col).size() if self.culture_col in t else pd.Series(dtype=int)
        return {
            "n_rows": int(len(t)),
            "n_recordings": int(t[self.name_col].nunique()),
            "n_cultures": int(t[self.culture_col].nunique()) if self.culture_col in t else 0,
            "recordings_per_culture_median": float(per_culture.median()) if len(per_culture) else 0.0,
            "recordings_per_culture_max": int(per_culture.max()) if len(per_culture) else 0,
            "groups": [str(g) for g in self.groups],
            "ages": [float(a) for a in self.ages],
            "lags": [str(x) for x in self.lags],
            "activities": [str(x) for x in self.activities],
            "n_metrics": len(self.metrics),
            "level": self.level,
        }

    # ── subsetting ───────────────────────────────────────────────────────────

    def for_lag(self, lag) -> "StatsDataset":
        """The rows for one lag, as a dataset in its own right.

        Every metric a run computes is computed per lag, so a comparison or a
        decoder mixing lags would be mixing several measurements of the same
        recording. Analyses loop over lags and work on these.
        """
        if "Lag" not in self.table.columns:
            return self
        sub = self.table[self.table["Lag"] == lag].reset_index(drop=True)
        return self._with_table(sub)

    def for_activity(self, activity) -> "StatsDataset":
        """The rows measured one way, as a dataset in its own right.

        The measure axis is handled exactly like the lag axis and for the same
        reason: two measures of one recording are two different measurements,
        and a comparison or a decoder that pooled them would be treating one
        culture as two independent samples. Everything that compares *across*
        measures goes through :mod:`meanap.stats.measures` instead.
        """
        if self.activity_col not in self.table.columns:
            return self
        sub = self.table[self.table[self.activity_col] == activity]
        return self._with_table(sub.reset_index(drop=True))

    def with_metrics(self, metrics: list[str]) -> "StatsDataset":
        keep = [m for m in metrics if m in self.table.columns]
        cols = [c for c in self.table.columns if c in META_COLUMNS] + keep
        return StatsDataset(
            table=self.table[cols].copy(), metrics=keep, labels=self.labels,
            group_col=self.group_col, age_col=self.age_col,
            culture_col=self.culture_col, name_col=self.name_col,
            activity_col=self.activity_col, level=self.level, source=self.source,
        )

    def _with_table(self, table: pd.DataFrame) -> "StatsDataset":
        return StatsDataset(
            table=table, metrics=usable_metrics(table, self.metrics),
            labels=self.labels, group_col=self.group_col, age_col=self.age_col,
            culture_col=self.culture_col, name_col=self.name_col,
            activity_col=self.activity_col, level=self.level, source=self.source,
        )

    # ── the feature matrix ───────────────────────────────────────────────────

    def feature_matrix(
        self, *, metrics: list[str] | None = None, dropna: str = "rows",
    ) -> tuple[np.ndarray, list[str], pd.DataFrame]:
        """``(X, feature_names, meta)`` — the matrix the ML analyses take.

        *dropna* ``"rows"`` drops any recording with a non-finite value in any
        feature (what MATLAB's ``doClassification`` does). ``"columns"`` instead
        drops features that are ever missing, which keeps every recording; it is
        the better choice when one rarely-computed metric would otherwise cost
        most of the dataset. *meta* is the identifying columns for the surviving
        rows, aligned with *X*, so the caller keeps its labels and culture IDs.
        """
        names = list(metrics or self.metrics)
        frame = self.table[names].apply(pd.to_numeric, errors="coerce")
        frame = frame.replace([np.inf, -np.inf], np.nan)

        if dropna == "columns":
            names = [c for c in names if frame[c].notna().all()]
            frame = frame[names]
        keep = frame.notna().all(axis=1)

        meta_cols = [c for c in self.table.columns if c in META_COLUMNS]
        meta = self.table.loc[keep, meta_cols].reset_index(drop=True)
        X = frame.loc[keep].to_numpy(dtype=float)

        # Zero-variance features carry no information and break z-scoring; drop
        # them after row selection, since a feature can become constant once the
        # incomplete rows are gone. (MATLAB lists this as a preprocessing step,
        # `removeZeroVariance`, but only ever applies it in `doLDA`.)
        if X.size:
            varying = X.std(axis=0) > 0
            X = X[:, varying]
            names = [n for n, keep_it in zip(names, varying) if keep_it]
        return X, names, meta


def usable_metrics(table: pd.DataFrame, candidates: list[str] | None = None) -> list[str]:
    """Metric columns of *table* that can actually be analysed.

    Numeric, not metadata, and not entirely missing. Constant columns are kept
    here — a metric that is constant at one DIV but not another is still a
    metric — and dropped per-analysis by :meth:`StatsDataset.feature_matrix`.
    """
    cols = candidates if candidates is not None else list(table.columns)
    out = []
    for col in cols:
        if col in META_COLUMNS or col not in table.columns:
            continue
        series = pd.to_numeric(table[col], errors="coerce")
        if series.notna().any():
            out.append(col)
    return out


# ── loading ──────────────────────────────────────────────────────────────────

def _read_first(root: Path, candidates) -> pd.DataFrame | None:
    for rel in candidates if isinstance(candidates, tuple) else (candidates,):
        path = root / rel
        if path.exists():
            return pd.read_csv(path)
    return None


def _resolve_root(source: Path | str):
    """An output folder for *source*, plus the bundle keeping it alive.

    A ``.meanap`` bundle unpacks to a temporary directory that is cleaned up
    when the :class:`RunBundle` is closed, so the caller has to hold it for as
    long as it reads from the returned root.
    """
    from meanap.pipeline.bundle import is_bundle, open_bundle

    path = Path(source)
    if path.is_file() and is_bundle(path):
        bundle = open_bundle(path)
        return Path(bundle.root), bundle
    if not path.is_dir():
        raise ValueError(
            f"{path} is neither a MEA-NAP output folder nor a .meanap bundle.")
    return path, None


def load_dataset(
    source: Path | str,
    *,
    level: str = "recording",
    include_activity: bool = True,
    strip_date_from_culture: bool = True,
) -> StatsDataset:
    """Read a run's metric tables into one :class:`StatsDataset`.

    *source* is a run's output folder or a ``.meanap`` bundle. At the recording
    level the network and activity tables are merged on ``FileName`` so a single
    feature vector describes a recording; at the node level they are merged on
    ``FileName`` *and* ``Channel``.

    Raises :class:`ValueError` when the run has no network metrics, since every
    analysis here is about network features and a run without them has nothing
    to compare.
    """
    root, bundle = _resolve_root(source)
    try:
        if level == "recording":
            net = _read_first(root, _NETWORK_REC)
            act = _read_first(root, _ACTIVITY_REC) if include_activity else None
            join_on = ["FileName"]
        elif level == "node":
            net = _read_first(root, _NETWORK_NODE)
            act = _read_first(root, _ACTIVITY_NODE) if include_activity else None
            join_on = ["FileName", "Channel"]
        else:
            raise ValueError(f"level must be 'recording' or 'node', not {level!r}")

        if net is None or net.empty:
            raise ValueError(
                f"No {level}-level network metrics in {Path(source).name} — "
                "the statistics step needs a run that reached step 4.")

        table = net
        if act is not None and not act.empty:
            # Grp/DIV are carried by both tables and are identical; keeping one
            # copy avoids the _x/_y suffixes a plain merge would introduce.
            drop = [c for c in ("Grp", "DIV", "Lag") if c in act.columns]
            # A multi-measure CAT-NAP run has one activity row per recording
            # *per measure*, so the measure is part of the key. Joining on the
            # name alone would give a recording the wrong measure's event rates
            # — or, at the recording level, fail the m:1 check outright.
            keys = list(join_on)
            if "ActivityType" in act.columns and "ActivityType" in net.columns:
                keys.append("ActivityType")
            table = net.merge(
                act.drop(columns=drop), on=keys, how="left", validate="m:1"
                if level == "recording" else "m:m")

        table["Culture"] = derive_culture_ids(
            table["FileName"], strip_date=strip_date_from_culture)

        # Group order: honour the run's custom_grp_order when the params travel
        # with the run, so figures here order the genotypes like every other
        # figure in the output folder.
        table = _apply_group_order(table, root)

        metrics = usable_metrics(table)
        return StatsDataset(
            table=table.reset_index(drop=True), metrics=metrics,
            labels=metric_labels(), level=level, source=Path(source),
        )
    finally:
        if bundle is not None:
            # The tables are now in memory, so the temporary extraction can go.
            bundle.close()


def _apply_group_order(table: pd.DataFrame, root: Path) -> pd.DataFrame:
    import json

    params_path = root / "params.json"
    order: list[str] = []
    if params_path.exists():
        try:
            with open(params_path) as fh:
                order = list(json.load(fh).get("custom_grp_order") or [])
        except (OSError, ValueError):
            order = []
    if not order:
        return table
    present = [g for g in order if g in set(table["Grp"].dropna())]
    if not present:
        return table
    rest = [g for g in pd.unique(table["Grp"].dropna()) if g not in present]
    table = table.copy()
    table["Grp"] = pd.Categorical(table["Grp"], categories=present + rest, ordered=True)
    return table.sort_values(["Grp", "DIV"], kind="stable")
