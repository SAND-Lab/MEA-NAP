"""Network topology measured at matched connection density.

Every graph metric MEA-NAP computes depends on how many edges the network has,
and on the Yin timecourse density rises from ~0.35 to ~0.98 across development.
A difference in clustering or efficiency between two groups at their own
densities therefore cannot be read as a difference in *organisation*: it is
confounded with the difference in how much correlation there was to begin with.
This is the problem van Wijk, Stam & Daffertshofer (2010, PLoS ONE) set out,
and it is not solved by the null-model normalisation MEA-NAP applies — a
degree-preserving null preserves density exactly, so the ratio is
density-*conditioned*, not density-independent, and it saturates as the graph
approaches complete.

The standard remedy is to stop comparing at the observed densities and compare
at a common one instead: threshold every recording to the same proportion of
edges, and repeat across a range. What survives the whole range is topology;
what appears at one density is not worth reporting. Ginestet, Nichols, Bullmore
& Simmons (2011, PLoS ONE) call integrating over that range *cost integration*,
and show it controls for any monotonic transformation of the weights.
Schroeter, Charlesworth, Kitzbichler, Paulsen & Bullmore (2015, J Neurosci) did
exactly this on the closest design to MEA-NAP's — dissociated hippocampal
cultures on MEAs, density climbing over four weeks in vitro — sweeping 2-40% in
2% steps, which is the default grid here.

**Binary, not weighted.** At a fixed density the surviving edges still carry
their weights, and those weights still differ between groups, so a weighted
sweep removes only half the confound. Discarding them is what the cost/density
literature means by proportional thresholding, and it is the only version that
isolates topology. It also means the strength metrics (``NS``, ``MEW``,
``Dens``, ``ND``) are constant by construction and are simply not swept.

**No null models.** ``CC``/``PL``/``SW`` are normalised against degree-preserving
nulls precisely to control for density; once density is fixed by construction
that control is redundant, and the raw quantities are what the sweep reports.

**Matching density is only half of it.** van Wijk et al.'s title is "networks
of different size *and* connectivity density", and thresholding to a common
density does nothing about the first. It matters: on the Yin timecourse node
counts differ 2.4x between genotypes (median 143 KO, 93 Het, 59 WT), and at 20%
imposed density only ``Eglob`` (r = -0.01) and ``Q`` (r = -0.04) are
uncorrelated with node count — ``CC``, ``PL``, ``ElocMean``, ``nMod`` and
``BCmean`` all still carry it. Passing *n_nodes* closes that half: every
network is reduced to a random induced subgraph of the same size before it is
thresholded, and the whole sweep is repeated over *n_subsamples* draws and
averaged, since which nodes are drawn matters.

The cost of doing so is a **selection bias that has to be watched**. A
recording with fewer than *n_nodes* nodes cannot be subsampled and is dropped,
and on real data smallness is not randomly distributed: at 80 nodes the Yin run
keeps 76% of KO recordings but only 34% of wildtype ones, which would compare
the largest wildtype networks against typical KO ones — a confound traded, not
removed. :func:`run_density_sweep` reports retention per group for exactly this
reason, and the default target is a low percentile of the observed counts
rather than anything ambitious.

**Two caveats to read the output with.** A sparse graph is usually
disconnected, and ``charpath`` — like BCT's — averages over connected pairs
only, so a more fragmented network can show a *shorter* apparent path length.
``lccFraction`` is swept alongside for that reason: where it falls well below 1,
prefer ``Eglob``, which counts a disconnected pair as zero efficiency rather
than discarding it. And the sweep imposes densities the recordings do not have
(2-40% against an observed 35-98%), which is the point but does mean the
networks being compared are not the ones step 4 measured.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "DEFAULT_DENSITIES",
    "SWEEP_METRICS",
    "COST_INT_SUFFIX",
    "DensitySweep",
    "CONTROL_LEVELS",
    "RAW_COUNTERPART",
    "SelectionCheck",
    "binarise_at_density",
    "control_effects",
    "control_values",
    "cost_integrate",
    "decompose_targets",
    "group_gaps",
    "run_density_sweep",
    "selection_sensitivity",
    "subsample_nodes",
    "sweep_one_matrix",
]

#: Schroeter et al. (2015)'s grid: 2% to 40% of possible edges, in 2% steps.
DEFAULT_DENSITIES: tuple[float, ...] = tuple(
    round(x, 3) for x in np.arange(0.02, 0.401, 0.02))

#: What is measured at each density. Topology only — the strength and density
#: metrics are fixed by construction here and would be flat lines.
SWEEP_METRICS: tuple[str, ...] = (
    "CC", "PL", "Eglob", "ElocMean", "BCmean", "Q", "nMod", "lccFraction",
)

#: Suffix marking a metric integrated over the density range. Chosen to avoid
#: colliding with ``Ci`` (the community index) under case-insensitive matching.
COST_INT_SUFFIX = "_costInt"


@dataclass
class DensitySweep:
    """Topology as a function of imposed density, and its integral."""

    #: One row per (recording, lag, density): a column per swept metric.
    curves: pd.DataFrame
    #: One row per (recording, lag): each metric integrated over the density
    #: range, named ``<metric>_costInt``. These are the density-controlled
    #: features — one number per recording, usable anywhere the ordinary
    #: metrics are.
    integrated: pd.DataFrame = field(default_factory=pd.DataFrame)
    densities: tuple[float, ...] = DEFAULT_DENSITIES
    metrics: tuple[str, ...] = SWEEP_METRICS
    #: One row per (recording, lag): the density step 4 actually measured at,
    #: for reading the sweep against.
    observed: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: ``curves`` with ``Grp``/``DIV``/``Culture`` joined on, as the figures
    #: need them. Filled by :func:`attach_labels`; empty until then.
    labelled: pd.DataFrame = field(default_factory=pd.DataFrame)
    group_col: str = "Grp"
    age_col: str = "DIV"
    #: Common node count every network was reduced to, or ``None`` when size
    #: was not controlled.
    n_nodes: int | None = None
    #: Random draws averaged over, when subsampling.
    n_subsamples: int = 0
    #: Recordings that could not be swept, and why.
    skipped: list = field(default_factory=list)


# ── thresholding ─────────────────────────────────────────────────────────────

def binarise_at_density(w: np.ndarray, target: float) -> np.ndarray | None:
    """Keep the strongest *target* fraction of possible edges, as a binary graph.

    Ties at the cutoff are all kept, so the realised density can exceed the
    target slightly — the alternative is breaking ties arbitrarily, which makes
    the result depend on node ordering. Returns ``None`` when the matrix has too
    few non-zero edges to reach the target, which is the honest answer: that
    density does not exist for this recording.
    """
    w = np.asarray(w, dtype=float)
    n = w.shape[0]
    if n < 3:
        return None
    upper = np.triu_indices(n, 1)
    weights = w[upper]
    n_possible = weights.size
    n_keep = int(round(target * n_possible))
    if n_keep < 1:
        return None
    # Only positive weights are edges; a target needing more than exist cannot
    # be met without inventing connections out of zeros.
    positive = weights[weights > 0]
    if positive.size < n_keep:
        return None

    cutoff = np.sort(positive)[::-1][n_keep - 1]
    binary = np.zeros_like(w)
    binary[w >= cutoff] = 1.0
    binary[w <= 0] = 0.0
    np.fill_diagonal(binary, 0.0)
    return binary


def subsample_nodes(w: np.ndarray, n_nodes: int, rng) -> np.ndarray | None:
    """A random induced subgraph on *n_nodes* nodes, or ``None`` if too small.

    Uniformly at random, without replacement. Picking the *strongest* nodes
    instead would be cheaper to interpret and quite wrong: it would select on
    exactly the connectivity the sweep is trying to control for, so the
    subgraph of a weakly-coupled network would be its most-coupled corner.
    """
    n = w.shape[0]
    if n < n_nodes:
        return None
    if n == n_nodes:
        return w
    idx = np.sort(rng.choice(n, size=n_nodes, replace=False))
    return w[np.ix_(idx, idx)]


def _largest_component_fraction(binary: np.ndarray) -> float:
    """Fraction of nodes in the largest connected component.

    Reported because ``PL`` is averaged over connected pairs only: where this
    drops, path length is being measured on a shrinking subset of the network
    and stops being comparable across recordings.
    """
    n = binary.shape[0]
    if n == 0:
        return float("nan")
    seen = np.zeros(n, dtype=bool)
    best = 0
    for start in range(n):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        size = 0
        while stack:
            node = stack.pop()
            size += 1
            for neighbour in np.nonzero(binary[node])[0]:
                if not seen[neighbour]:
                    seen[neighbour] = True
                    stack.append(int(neighbour))
        best = max(best, size)
    return best / n


# ── one matrix ───────────────────────────────────────────────────────────────

def sweep_one_matrix(
    w: np.ndarray,
    densities=DEFAULT_DENSITIES,
    *,
    metrics=SWEEP_METRICS,
    modularity_reps: int = 20,
    n_nodes: int | None = None,
    n_subsamples: int = 20,
    seed: int = 0,
) -> dict[str, np.ndarray]:
    """Measure *metrics* on one network at each density in *densities*.

    Returns a dict of metric name → array over densities, NaN where that
    density could not be realised. ``modularity_reps`` is the consensus-Louvain
    repeat count; step 4 uses 50, and this defaults lower because the sweep
    pays it once per density and the curve smooths across them anyway.

    With *n_nodes* set, the network is first reduced to a random induced
    subgraph of that size and the whole sweep repeated over *n_subsamples*
    draws, then averaged — so the result is comparable across recordings in
    size as well as density. Returns ``None`` for a network with fewer than
    *n_nodes* nodes: it cannot be brought to the common size, and padding it
    would invent structure.

    Subsampling happens **before** thresholding, so the target density is a
    proportion of the *subgraph's* possible edges. The other order would
    threshold the whole network and then take a subgraph of whatever survived,
    which lands at an uncontrolled density.
    """
    if n_nodes is not None:
        if w.shape[0] < n_nodes:
            return None
        rng = np.random.default_rng(seed)
        draws = []
        for draw in range(max(1, n_subsamples)):
            sub = subsample_nodes(w, n_nodes, rng)
            draws.append(_sweep_fixed_network(
                sub, densities, metrics=metrics,
                modularity_reps=modularity_reps, seed=seed + 1000 * draw))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # all-NaN densities are expected
            return {m: np.nanmean([d[m] for d in draws], axis=0) for m in metrics}
    return _sweep_fixed_network(w, densities, metrics=metrics,
                                modularity_reps=modularity_reps, seed=seed)


def _sweep_fixed_network(
    w: np.ndarray, densities, *, metrics, modularity_reps: int, seed: int,
) -> dict[str, np.ndarray]:
    """One network, one pass over the densities — the body of the sweep."""
    from meanap.pipeline import network_metrics as nm
    from meanap.pipeline.modularity import mod_consensus_cluster_iterate

    wanted = list(metrics)
    out = {m: np.full(len(densities), np.nan) for m in wanted}
    need_q = "Q" in out or "nMod" in out

    for i, target in enumerate(densities):
        binary = binarise_at_density(w, float(target))
        if binary is None:
            continue

        if "CC" in out:
            out["CC"][i] = float(np.mean(nm.clustering_coef_wu(binary)))
        if "PL" in out or "Eglob" in out:
            lengths = nm.weight_conversion_lengths(binary)
            distances = nm.distance_wei(lengths)
            path_length, _ = nm.charpath(distances)
            if "PL" in out:
                out["PL"][i] = path_length
        if "Eglob" in out:
            out["Eglob"][i] = nm.efficiency_wei_global(binary)
        if "ElocMean" in out:
            out["ElocMean"][i] = float(np.mean(nm.efficiency_wei_local(binary)))
        if "BCmean" in out:
            # Normalised by ((n-1)(n-2)) exactly as step 4 and MATLAB's
            # ExtractNetMet do. Raw Brandes betweenness counts shortest paths,
            # so it scales with the square of the node count — on this dataset
            # the unnormalised mean correlates with node count at r = 0.89,
            # which makes it a size measure rather than a topology one. That
            # matters more here than in step 4: the whole point of the sweep is
            # comparing across recordings.
            nodes = binary.shape[0]
            if nodes > 2:
                bc = nm.betweenness_wei(binary) / ((nodes - 1) * (nodes - 2))
                out["BCmean"][i] = float(np.mean(bc))
        if "lccFraction" in out:
            out["lccFraction"][i] = _largest_component_fraction(binary)
        if need_q:
            # Seeded per density so a rerun reproduces, and so two densities
            # do not share a partition by accident.
            rng = np.random.default_rng(seed + i)
            ci, q, _ = mod_consensus_cluster_iterate(
                binary, threshold=0.4, rep_num=modularity_reps, rng=rng)
            if "Q" in out:
                out["Q"][i] = float(q)
            if "nMod" in out:
                out["nMod"][i] = float(np.max(ci)) if np.size(ci) else np.nan
    return out


# ── cost integration ─────────────────────────────────────────────────────────

def cost_integrate(
    curves: pd.DataFrame, *, metrics=SWEEP_METRICS, id_cols=("FileName", "Lag"),
) -> pd.DataFrame:
    """Integrate each metric over the density range — Ginestet's cost integration.

    The trapezoidal integral divided by the range covered, so the result is on
    the metric's own scale (a mean over density, not an area) and is comparable
    to the unswept metric. NaN densities are dropped per metric before
    integrating, so a recording that cannot reach the sparsest densities is
    integrated over the part of the range it does have — with ``NDensities``
    recording how much of it that was.
    """
    if curves.empty:
        return pd.DataFrame()

    rows = []
    for keys, block in curves.groupby(list(id_cols), dropna=False):
        row = dict(zip(id_cols, keys if isinstance(keys, tuple) else (keys,)))
        block = block.sort_values("Density")
        for metric in metrics:
            if metric not in block.columns:
                continue
            valid = block[["Density", metric]].dropna()
            if len(valid) < 2:
                row[f"{metric}{COST_INT_SUFFIX}"] = np.nan
                continue
            x = valid["Density"].to_numpy(dtype=float)
            y = valid[metric].to_numpy(dtype=float)
            row[f"{metric}{COST_INT_SUFFIX}"] = float(
                np.trapezoid(y, x) / (x[-1] - x[0])) if x[-1] > x[0] else float(y[0])
        row["NDensities"] = int(block[list(metrics)[0]].notna().sum())
        rows.append(row)
    return pd.DataFrame(rows)


# ── running it over a whole run ──────────────────────────────────────────────

def _adjacency_files(root: Path):
    """``(recording name, path)`` for every stored adjacency in a run."""
    from meanap.pipeline.resume import ADJM_SUFFIX, CATNAP_SUFFIX

    folder = Path(root) / "ExperimentMatFiles"
    if not folder.is_dir():
        return []
    found = []
    for suffix in (CATNAP_SUFFIX, ADJM_SUFFIX):
        for path in sorted(folder.glob(f"*{suffix}")):
            found.append((path.name[: -len(suffix)], path))
    return found


def _matrices(path: Path) -> dict[str, np.ndarray]:
    """``lag key -> weighted adjacency``, preferring the pre-thresholding copy.

    Step 3 stores both ``adjM{lag}mslag`` (significance-thresholded, what step 4
    measured) and ``adjM{lag}mslag_raw``. The sweep wants the raw one: imposing
    a 2% density on a matrix that significance has already reduced would be
    thresholding twice, and the sparsest targets would be unreachable for
    exactly the recordings whose connectivity is weakest — the bias van den
    Heuvel et al. (2017) warn about. CAT-NAP stores one matrix, prefixed
    ``adj__``, which is the correlation matrix before thresholding.
    """
    out: dict[str, np.ndarray] = {}
    with np.load(path, allow_pickle=True) as data:
        keys = list(data.files)
        prefixed = {k[len("adj__"):]: k for k in keys if k.startswith("adj__")}
        if prefixed:
            for lag_key, stored in prefixed.items():
                out[lag_key] = np.asarray(data[stored], dtype=float)
            return out
        bare = [k for k in keys if k.startswith("adjM") and k.endswith("mslag")]
        for lag_key in bare:
            raw_key = f"{lag_key}_raw"
            source = raw_key if raw_key in keys else lag_key
            out[lag_key] = np.asarray(data[source], dtype=float)
    return out


def _clean(w: np.ndarray) -> np.ndarray:
    """Negatives to zero, NaNs to zero, no self-loops — as step 4 does."""
    w = np.asarray(w, dtype=float).copy()
    w[w < 0] = 0.0
    w = np.nan_to_num(w, nan=0.0)
    np.fill_diagonal(w, 0.0)
    return w


def _active_subgraph(w: np.ndarray) -> np.ndarray:
    """Drop nodes with no connections at all.

    Step 4 restricts to ``activeChannelIndex``; here the equivalent is dropping
    nodes that are never coupled, which after cleaning is the same set for the
    matrices this reads. Keeping them would add isolated nodes that no
    proportional threshold can connect, deflating every path-based metric.
    """
    keep = np.nonzero(w.sum(axis=1) > 0)[0]
    return w[np.ix_(keep, keep)]


def _sweep_recording(name, path, densities, metrics, modularity_reps, seed,
                     n_nodes=None, n_subsamples=20):
    """One recording, every lag it has. Returns ``(rows, observed, skipped)``."""
    rows, observed, skipped = [], [], []
    try:
        matrices = _matrices(Path(path))
    except Exception as exc:  # a corrupt file costs its own recording, not the run
        return [], [], [(name, f"{type(exc).__name__}: {exc}")]

    for lag_key, raw in matrices.items():
        w = _active_subgraph(_clean(raw))
        if w.shape[0] < 5:
            skipped.append((f"{name} {lag_key}", f"only {w.shape[0]} connected nodes"))
            continue
        upper = np.triu_indices(w.shape[0], 1)
        observed.append({
            "FileName": name, "Lag": lag_key,
            "ObservedDensity": float(np.mean(w[upper] > 0)),
            "NNodes": int(w.shape[0]),
            "NNodesUsed": int(n_nodes) if n_nodes is not None else int(w.shape[0]),
            "Retained": bool(n_nodes is None or w.shape[0] >= n_nodes),
        })
        swept = sweep_one_matrix(
            w, densities, metrics=metrics, modularity_reps=modularity_reps,
            n_nodes=n_nodes, n_subsamples=n_subsamples, seed=seed)
        if swept is None:
            skipped.append((f"{name} {lag_key}",
                            f"{w.shape[0]} nodes, fewer than the {n_nodes} "
                            "the sweep subsamples to"))
            continue
        for i, density in enumerate(densities):
            row = {"FileName": name, "Lag": lag_key, "Density": float(density)}
            row.update({m: float(swept[m][i]) for m in metrics})
            rows.append(row)
    return rows, observed, skipped


def run_density_sweep(
    source: Path | str,
    *,
    densities=DEFAULT_DENSITIES,
    metrics=SWEEP_METRICS,
    modularity_reps: int = 20,
    n_nodes: int | None = None,
    n_subsamples: int = 20,
    seed: int = 0,
    n_jobs: int = -1,
    recordings: list[str] | None = None,
    log=None,
    progress=None,
) -> DensitySweep:
    """Sweep every recording in a finished run, in parallel over recordings.

    *source* is an output folder — a bundle should be opened first, since this
    reads the per-recording adjacency files. Recordings are independent, which
    is what makes this embarrassingly parallel and worth the joblib dependency
    already in use elsewhere.

    *n_nodes* additionally reduces every network to that many randomly drawn
    nodes before thresholding, controlling size as well as density. Recordings
    with fewer nodes are dropped and listed in ``skipped`` — check
    :attr:`DensitySweep.retention` afterwards, because on real data the dropped
    ones are not a random sample.
    """
    from joblib import Parallel, delayed

    root = Path(source)
    files = _adjacency_files(root)
    if recordings is not None:
        wanted = set(recordings)
        files = [(name, path) for name, path in files if name in wanted]
    if not files:
        raise ValueError(
            f"No adjacency files under {root / 'ExperimentMatFiles'} — the "
            "density sweep needs the per-recording matrices step 3 wrote.")

    if log is not None:
        size = (f", subsampled to {n_nodes} nodes x{n_subsamples}"
                if n_nodes is not None else "")
        log(f"    sweeping {len(files)} recordings over {len(densities)} densities "
            f"({densities[0]:.0%}-{densities[-1]:.0%}){size}")

    results = Parallel(n_jobs=n_jobs, prefer="processes")(
        delayed(_sweep_recording)(
            name, path, tuple(densities), tuple(metrics), modularity_reps, seed,
            n_nodes, n_subsamples)
        for name, path in files)

    rows, observed, skipped = [], [], []
    for r, o, s in results:
        rows.extend(r)
        observed.extend(o)
        skipped.extend(s)
    if progress is not None:
        progress(len(files), len(files))

    curves = pd.DataFrame(rows)
    return DensitySweep(
        curves=curves,
        integrated=cost_integrate(curves, metrics=tuple(metrics)),
        densities=tuple(densities), metrics=tuple(metrics),
        observed=pd.DataFrame(observed), skipped=skipped,
        n_nodes=n_nodes, n_subsamples=n_subsamples if n_nodes is not None else 0,
    )


def retention(observed: pd.DataFrame, group_col: str = "Grp") -> pd.DataFrame:
    """How many recordings survived the node-count cut, per group.

    The number to look at before believing anything a subsampled sweep says.
    Recordings too small to reach the common size are dropped, and if that loss
    falls unevenly across groups the comparison has swapped a size confound for
    a selection one — on the Yin run a target of 80 nodes keeps 76% of KO
    recordings against 34% of wildtype.
    """
    if observed.empty or "Retained" not in observed.columns:
        return pd.DataFrame()
    if group_col not in observed.columns:
        kept = observed["Retained"]
        return pd.DataFrame([{ "Group": "all", "NKept": int(kept.sum()),
                               "NTotal": int(len(kept)),
                               "Fraction": float(kept.mean())}])
    out = (observed.groupby(group_col)["Retained"]
           .agg(NKept="sum", NTotal="size").reset_index())
    out["Fraction"] = out["NKept"] / out["NTotal"]
    return out.rename(columns={group_col: "Group"})


def lag_key_to_label(lag_key: str) -> str:
    """``'adjM1000mslag'`` → ``'1000mslag'``.

    The adjacency files key their matrices by the step-3 name; every table in
    step 5 uses the bare lag label. Joining the two needs one of them
    translated, and translating here keeps the sweep's own output in the
    convention the rest of the step reads.
    """
    return lag_key[len("adjM"):] if lag_key.startswith("adjM") else lag_key


def attach_labels(frame: pd.DataFrame, ds) -> pd.DataFrame:
    """Add ``Grp``/``DIV``/``Culture`` to a sweep table, by recording name.

    An inner join: a swept recording with no row in the metric table is one the
    statistics step never saw, and carrying it into a group comparison with no
    group would be worse than dropping it.
    """
    if frame.empty:
        return frame
    out = frame.copy()
    if "Lag" in out.columns:
        out["Lag"] = out["Lag"].map(lag_key_to_label)
    keys = [c for c in (ds.name_col, ds.group_col, ds.age_col, ds.culture_col)
            if c in ds.table.columns]
    labels = ds.table[keys].drop_duplicates(subset=[ds.name_col])
    return out.merge(labels, on=ds.name_col, how="inner")


# -- separating selection from resolution ------------------------------------
#
# Raising the subsample target does two things at once. Topology is measured on
# bigger subgraphs, so real differences between recordings are less attenuated
# (*resolution*); and a smaller, non-random set of recordings clears the cut, so
# the comparison is over a different cohort (*selection*). Comparing one target
# against another moves both, which is why a target cannot be chosen by trying
# two and keeping whichever showed the larger effect.
#
# The three-condition design that separates them:
#
#     A   target N, every recording reaching N
#     B   target M > N, every recording reaching M
#     C   target N, but only B's recordings
#
# A vs C is then selection alone and C vs B resolution alone. The useful
# asymmetry is that **C is free**: a recording's swept result depends only on
# its matrix, the target and the seed, never on which cohort it sits in, so C is
# a row subset of A rather than a second sweep. ``selection_sensitivity``
# exploits that to report the selection term from the sweep already run;
# ``decompose_targets`` completes the design once a second sweep supplies B.
#
# Every gap here is standardised by the spread of that metric *within its own
# condition*, which is what an analysis restricted to that cohort would report.
# So a delta between two conditions mixes a change in group means with a change
# in spread - deliberately, because both are things the restriction really did
# to the number you would quote.

#: Dropped from gap tables: a fragmentation diagnostic for reading ``PL``
#: against, not a topology measure anyone compares between groups.
_NOT_A_GAP_METRIC = ("lccFraction",)


def _gap_columns(frame: pd.DataFrame, metrics) -> list[str]:
    """The ``<metric>_costInt`` columns present in *frame*, diagnostics excluded."""
    return [f"{m}{COST_INT_SUFFIX}" for m in metrics
            if m not in _NOT_A_GAP_METRIC
            and f"{m}{COST_INT_SUFFIX}" in frame.columns]


def _keyed(frame: pd.DataFrame) -> pd.Series:
    """A per-recording key, including the lag when the table carries one."""
    if "Lag" in frame.columns:
        return frame["FileName"].astype(str) + " " + frame["Lag"].astype(str)
    return frame["FileName"].astype(str)


def group_gaps(
    integrated: pd.DataFrame,
    *,
    group_col: str = "Grp",
    metrics=SWEEP_METRICS,
    min_per_group: int = 3,
) -> pd.DataFrame:
    """Standardised difference between every pair of groups, per metric.

    One row per (metric, group pair): the difference in means divided by the
    metric's SD across every recording in *integrated*. Pairs are ordered by
    the group labels' sort order, so ``Gap`` keeps a stable sign between calls
    and two conditions can be subtracted row for row.
    """
    from itertools import combinations

    if integrated is None or integrated.empty or group_col not in integrated.columns:
        return pd.DataFrame()

    groups = sorted(g for g in integrated[group_col].dropna().unique())
    rows = []
    for col in _gap_columns(integrated, metrics):
        spread = integrated[col].std()
        if not np.isfinite(spread) or spread == 0:
            continue
        for a, b in combinations(groups, 2):
            xa = integrated.loc[integrated[group_col] == a, col].dropna()
            xb = integrated.loc[integrated[group_col] == b, col].dropna()
            if len(xa) < min_per_group or len(xb) < min_per_group:
                continue
            rows.append({
                "Metric": col[: -len(COST_INT_SUFFIX)],
                "GroupA": a, "GroupB": b,
                "NA": int(len(xa)), "NB": int(len(xb)),
                "Gap": float((xa.mean() - xb.mean()) / spread),
            })
    return pd.DataFrame(rows)


@dataclass
class SelectionCheck:
    """How much the group differences move when the cohort is restricted.

    The free half of the three-condition design: no second sweep, just the
    sweep already run read over a smaller cohort. A large ``Delta`` means the
    reported effect is partly a statement about *which recordings were big
    enough to keep*, not about topology.
    """

    #: One row per (metric, group pair): ``GapAll``, ``GapRestricted``,
    #: ``Delta``, and whether the sign changed. Empty when the check could not
    #: be run, with :attr:`note` saying why.
    table: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: Node count the restricted cohort required, or ``None`` if not run.
    threshold: int | None = None
    n_all: int = 0
    n_restricted: int = 0
    #: ``(metric, group A, group B)`` for every gap that moved enough to be
    #: worth reading as selection rather than topology.
    flagged: list = field(default_factory=list)
    note: str = ""

    @property
    def ran(self) -> bool:
        return not self.table.empty


def selection_sensitivity(
    integrated: pd.DataFrame,
    observed: pd.DataFrame,
    *,
    group_col: str = "Grp",
    metrics=SWEEP_METRICS,
    threshold: int | None = None,
    percentile: float = 40.0,
    min_restricted: int = 20,
    min_dropped: float = 0.1,
    min_delta: float = 0.1,
    delta_ratio: float = 0.5,
) -> SelectionCheck:
    """Re-read one sweep over a higher-node-count cohort - the A vs C contrast.

    *integrated* is a labelled cost-integrated table and *observed* supplies
    ``NNodes``; both come from a finished :class:`DensitySweep`. Recordings
    below *threshold* nodes are dropped and the group gaps recomputed. Nothing
    is swept again - the same per-recording numbers are simply aggregated over
    fewer recordings, which is exactly what raising the target would have done
    to the cohort while leaving resolution alone.

    *threshold* defaults to the *percentile* of the node counts actually swept.
    A gap is flagged when it moves by at least *min_delta* **and** either
    changes sign or moves by *delta_ratio* of its own size - the combination
    matters, since a large relative move on a gap of 0.02 is noise and a small
    relative move on a gap of 1.0 is not worth a warning.
    """
    if integrated is None or integrated.empty or observed is None or observed.empty:
        return SelectionCheck(note="nothing to check")
    if "NNodes" not in observed.columns:
        return SelectionCheck(note="the sweep recorded no node counts")
    if group_col not in integrated.columns:
        return SelectionCheck(note=f"no {group_col} column to compare groups by")

    join = ["FileName", "Lag"] if ("Lag" in integrated.columns
                                   and "Lag" in observed.columns) else ["FileName"]
    sizes = observed[join + ["NNodes"]].drop_duplicates(subset=join)
    merged = integrated.merge(sizes, on=join, how="inner")
    if merged.empty:
        return SelectionCheck(note="node counts did not join onto the swept table")

    counts = merged["NNodes"].to_numpy(dtype=float)
    if threshold is None:
        threshold = int(np.percentile(counts, percentile))
    threshold = int(threshold)

    restricted = merged[merged["NNodes"] >= threshold]
    dropped = 1.0 - len(restricted) / len(merged)
    if len(restricted) < min_restricted:
        return SelectionCheck(
            threshold=threshold, n_all=len(merged), n_restricted=len(restricted),
            note=f"only {len(restricted)} recordings clear {threshold} nodes")
    if dropped < min_dropped:
        return SelectionCheck(
            threshold=threshold, n_all=len(merged), n_restricted=len(restricted),
            note=(f"{threshold} nodes drops only {dropped:.0%} of the swept "
                  "recordings - too few to say anything about selection"))

    all_gaps = group_gaps(merged, group_col=group_col, metrics=metrics)
    restricted_gaps = group_gaps(restricted, group_col=group_col, metrics=metrics)
    if all_gaps.empty or restricted_gaps.empty:
        return SelectionCheck(
            threshold=threshold, n_all=len(merged), n_restricted=len(restricted),
            note="not enough recordings per group to form gaps")

    keys = ["Metric", "GroupA", "GroupB"]
    table = all_gaps.merge(restricted_gaps, on=keys, how="inner",
                           suffixes=("All", "Restricted"))
    if table.empty:
        return SelectionCheck(
            threshold=threshold, n_all=len(merged), n_restricted=len(restricted),
            note="no metric could be compared across both cohorts")

    table["Delta"] = table["GapRestricted"] - table["GapAll"]
    table["SignFlip"] = np.sign(table["GapRestricted"]) != np.sign(table["GapAll"])
    table["Flagged"] = (table["Delta"].abs() >= min_delta) & (
        table["SignFlip"] | (table["Delta"].abs()
                             >= delta_ratio * table["GapAll"].abs()))
    table["NodeThreshold"] = threshold
    table = table.sort_values("Delta", key=lambda s: s.abs(), ascending=False)

    flagged = [(r.Metric, r.GroupA, r.GroupB)
               for r in table.itertuples() if r.Flagged]
    return SelectionCheck(
        table=table.reset_index(drop=True), threshold=threshold,
        n_all=len(merged), n_restricted=len(restricted), flagged=flagged)


def decompose_targets(
    low: pd.DataFrame,
    high: pd.DataFrame,
    *,
    group_col: str = "Grp",
    metrics=SWEEP_METRICS,
    min_per_group: int = 3,
) -> pd.DataFrame:
    """The full A/B/C decomposition, given cost-integrated tables at two targets.

    *low* is the sweep at the smaller target and *high* the sweep at the larger
    one; both must already carry group labels. Condition C - the low target
    over the high target's recordings - is derived from *low* by subsetting, so
    the only cost beyond the ordinary sweep is having run *high* at all.

    Returns one row per (metric, group pair) with ``GapA``/``GapC``/``GapB``
    and the two terms they decompose into: ``Selection`` (C - A, the cohort
    changing) and ``Resolution`` (B - C, the target changing). ``Total`` is
    their sum, and is what comparing the two targets naively would have shown.
    """
    if low is None or low.empty or high is None or high.empty:
        return pd.DataFrame()

    cohort = set(_keyed(high))
    middle = low[_keyed(low).isin(cohort)]
    if middle.empty:
        return pd.DataFrame()

    keys = ["Metric", "GroupA", "GroupB"]
    a = group_gaps(low, group_col=group_col, metrics=metrics,
                   min_per_group=min_per_group)
    c = group_gaps(middle, group_col=group_col, metrics=metrics,
                   min_per_group=min_per_group)
    b = group_gaps(high, group_col=group_col, metrics=metrics,
                   min_per_group=min_per_group)
    if a.empty or c.empty or b.empty:
        return pd.DataFrame()

    out = (a[keys + ["Gap"]].rename(columns={"Gap": "GapA"})
           .merge(c[keys + ["Gap"]].rename(columns={"Gap": "GapC"}), on=keys)
           .merge(b[keys + ["Gap"]].rename(columns={"Gap": "GapB"}), on=keys))
    if out.empty:
        return out

    out["Selection"] = out["GapC"] - out["GapA"]
    out["Resolution"] = out["GapB"] - out["GapC"]
    out["Total"] = out["GapB"] - out["GapA"]
    # Which term dominates is the reading: "selection" means the apparent
    # effect of raising the target was mostly the cohort changing under it.
    out["Dominant"] = np.where(out["Selection"].abs() >= out["Resolution"].abs(),
                               "selection", "resolution")
    out["NA"] = len(low)
    out["NC"] = len(middle)
    out["NB"] = len(high)
    return out.sort_values("Total", key=lambda s: s.abs(), ascending=False
                           ).reset_index(drop=True)


# -- effects under each level of control --------------------------------------
#
# "Does this genotype difference survive the control?" is a different question
# from "do the curves separate", and it is the one a reader of the 5A heatmaps
# will ask. The answer is the same effect statistic the heatmaps use, recomputed
# on the controlled features: standardised betas from the mixed model for
# genotype, and its "SD change across age range" for age, both FDR-corrected.
#
# Three levels of control, because the sweep moves two things at once:
#
#     none          step 4's own metrics, at each network's own density and size
#     density       cost-integrated over the density grid, size left alone
#     density+size  the same, on networks first cut to a common node count
#
# The step from "density" to "density+size" is the subsampling effect on its
# own. It needs the sweep run twice, which is why the middle condition is
# optional; with only one sweep the table simply carries the two conditions it
# has, and the figure draws whatever is there.

#: Levels of control, weakest first. Also the plotting order.
CONTROL_LEVELS: tuple[str, ...] = ("none", "density", "density+size")

#: The step-4 column each swept metric is compared against. The sweep measures
#: the *raw* quantities on binary graphs, so ``CC`` and ``PL`` pair with
#: ``CC_rawMean`` and ``PL_raw`` — **not** with the null-model-normalised
#: ``CC``/``PL`` the pipeline saves under those same short names, which are a
#: different quantity and would make the comparison meaningless. ``BCmean`` has
#: no recording-level counterpart in step 4 at all, so it appears only in the
#: controlled conditions.
RAW_COUNTERPART: dict[str, str] = {
    "CC": "CC_rawMean",
    "PL": "PL_raw",
    "Eglob": "Eglob",
    "ElocMean": "ElocMean",
    "Q": "Q",
    "nMod": "nMod",
}

#: Effect sizes the pooled comparison keeps: the two the mixed model reports,
#: over the whole timecourse at once.
_POOLED_EFFECTS = ("standardised beta", "SD change across age range")

#: The per-age genotype contrasts are Hedges' g from a Welch t-test at each age.
#: A different statistic on a different subset from the pooled ones, which is
#: why the table carries a ``Scope`` column rather than stacking them on one
#: axis: the two are not comparable and must not share a panel.
_PER_AGE_EFFECT = "Hedges g"


def _swept_name(column: str, metrics) -> str:
    """The swept metric a raw or cost-integrated column belongs to."""
    if column.endswith(COST_INT_SUFFIX):
        return column[: -len(COST_INT_SUFFIX)]
    for swept in metrics:
        if RAW_COUNTERPART.get(swept) == column:
            return swept
    return column


def _model_rows(table: pd.DataFrame, control: str, metrics) -> pd.DataFrame:
    """The comparison rows worth carrying, tagged with *control*.

    Two scopes, kept apart by a ``Scope`` column: ``"pooled"`` is the mixed
    model over the whole timecourse, ``"per-age"`` is the genotype contrast
    measured separately at each age. ``Contrast`` strips the age off the term,
    so the same genotype pair can be followed across ages and across controls.
    """
    if table is None or table.empty:
        return pd.DataFrame()
    keep = table[table["EffectSize"].notna()].copy()
    if keep.empty:
        return pd.DataFrame()
    at_age = keep["Term"].astype(str).str.contains(" at DIV ")

    pooled = keep[keep["EffectSizeName"].isin(_POOLED_EFFECTS) & ~at_age].copy()
    pooled["Scope"] = "pooled"
    pooled["Age"] = np.nan
    pooled["Contrast"] = pooled["Term"].astype(str)

    per_age = keep[(keep["EffectSizeName"] == _PER_AGE_EFFECT) & at_age].copy()
    per_age["Scope"] = "per-age"
    per_age["Age"] = (per_age["Term"].astype(str)
                      .str.extract(r" at DIV ([-\d.]+)$")[0].astype(float))
    per_age["Contrast"] = (per_age["Term"].astype(str)
                           .str.replace(r" at DIV [-\d.]+$", "", regex=True))

    out = pd.concat([pooled, per_age], ignore_index=True)
    if out.empty:
        return pd.DataFrame()
    out["Control"] = control
    out["Metric"] = [_swept_name(m, metrics) for m in out["Metric"]]
    columns = [c for c in ("Lag", "Control", "Scope", "Metric", "Term",
                           "Contrast", "Age", "EffectSize", "EffectSizeName",
                           "PValue", "PValueFDR", "N")
               if c in out.columns]
    return out[columns]


def _dataset_with_integrated(ds, integrated: pd.DataFrame, metrics):
    """*ds* with the cost-integrated features joined on, as its only metrics."""
    cols = _gap_columns(integrated, metrics)
    if not cols:
        return None
    table = integrated.copy()
    if "Lag" in table.columns:
        table["Lag"] = table["Lag"].map(lag_key_to_label)
    join = ["FileName", "Lag"] if ("Lag" in ds.table.columns
                                   and "Lag" in table.columns) else ["FileName"]
    # Only the join keys and the features: an integrated table that has already
    # had labels attached would otherwise duplicate ``Grp``/``DIV`` on merge.
    slim = table[join + cols].drop_duplicates(subset=join)
    merged = ds.table.merge(slim, on=join, how="inner")
    if merged.empty:
        return None
    return ds._with_table(merged).with_metrics(cols)


def _common_cohort(ds, tables, *, match: bool):
    """Restrict *ds* and *tables* to the recordings every condition has.

    Without this the comparison is not like-for-like. A sweep with subsampling
    on drops every recording too small to reach the target, while the
    uncontrolled metrics and an unsubsampled sweep keep all of them — so the
    step between two conditions would mix the control being applied with the
    cohort changing underneath it, which is precisely the confound the
    selection check exists to expose. Matching costs recordings and makes the
    uncontrolled column differ from the 5A tables, which is the honest trade:
    those tables answer "what does this run show", this one answers "what did
    the control do".
    """
    live = [t for t in tables if t is not None and not t.empty]
    if not match or not live:
        return ds, tables

    # Key on (name, lag) as a tuple rather than a joined string: recording
    # names come from filenames and may contain anything, spaces included.
    use_lag = ("Lag" in ds.table.columns
               and all("Lag" in t.columns for t in live))

    def keys(frame):
        names = frame["FileName"].astype(str)
        if not use_lag:
            return list(zip(names, [""] * len(frame)))
        return list(zip(names, frame["Lag"].map(lag_key_to_label).astype(str)))

    shared = None
    for table in live:
        found = set(keys(table))
        shared = found if shared is None else (shared & found)
    if not shared:
        return ds, tables

    trimmed = [None if (t is None or t.empty)
               else t[[k in shared for k in keys(t)]] for t in tables]
    kept = ds.table[[k in shared for k in keys(ds.table)]]
    return (ds._with_table(kept) if not kept.empty else ds), trimmed


def control_effects(
    ds,
    *,
    density_only: pd.DataFrame | None = None,
    density_and_size: pd.DataFrame | None = None,
    metrics=SWEEP_METRICS,
    match_cohort: bool = True,
) -> pd.DataFrame:
    """Age and genotype effects for each metric, under each level of control.

    *ds* is the run's own metric table; *density_only* and *density_and_size*
    are cost-integrated tables from a sweep run without and with node
    subsampling. Either may be ``None``, and the result then simply carries the
    conditions that exist.

    Returns one row per (lag, control, metric, term): the same effect size and
    FDR-corrected p-value the 5A comparisons report, so a metric's genotype
    effect before and after the control are directly comparable. The step from
    ``"density"`` to ``"density+size"`` is the subsampling effect isolated;
    ``"none"`` to ``"density"`` is the density control on its own.

    With *match_cohort* every condition is restricted to the recordings all of
    them have, so a step between two conditions is the control changing and not
    the cohort. Leave it on unless you want each condition on all the data it
    could use, in which case the steps stop being attributable.
    """
    from meanap.stats.comparisons import compare_metrics

    ds, (density_only, density_and_size) = _common_cohort(
        ds, [density_only, density_and_size], match=match_cohort)

    frames = []

    raw_cols = [RAW_COUNTERPART[m] for m in metrics
                if m in RAW_COUNTERPART and RAW_COUNTERPART[m] in ds.table.columns]
    if raw_cols:
        frames.append(_model_rows(
            compare_metrics(ds.with_metrics(raw_cols)).table, "none", metrics))

    for label, integrated in (("density", density_only),
                              ("density+size", density_and_size)):
        if integrated is None or integrated.empty:
            continue
        subset = _dataset_with_integrated(ds, integrated, metrics)
        if subset is None:
            continue
        frames.append(_model_rows(
            compare_metrics(subset).table, label, metrics))

    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    order = {level: i for i, level in enumerate(CONTROL_LEVELS)}
    out["_order"] = out["Control"].map(order).fillna(len(order))
    return (out.sort_values(["Scope", "Contrast", "Metric", "Age", "_order"])
            .drop(columns="_order").reset_index(drop=True))


def _values_for(table: pd.DataFrame, columns: dict, ds, control: str) -> pd.DataFrame:
    """Group-by-age summaries of *columns* (``swept name -> column``)."""
    rows = []
    for swept, column in columns.items():
        if column not in table.columns:
            continue
        sub = table[[ds.group_col, ds.age_col, column]].dropna()
        if sub.empty:
            continue
        stat = (sub.groupby([ds.group_col, ds.age_col])[column]
                .agg(Mean="mean", SD="std", N="count", Median="median")
                .reset_index())
        stat["SEM"] = stat["SD"] / np.sqrt(stat["N"].clip(lower=1))
        stat["Control"] = control
        stat["Metric"] = swept
        stat = stat.rename(columns={ds.group_col: "Group", ds.age_col: "Age"})
        rows.append(stat)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def control_values(
    ds,
    *,
    density_only: pd.DataFrame | None = None,
    density_and_size: pd.DataFrame | None = None,
    metrics=SWEEP_METRICS,
    match_cohort: bool = True,
) -> pd.DataFrame:
    """The metrics themselves, per group and age, under each level of control.

    The companion to :func:`control_effects`: an effect size says how far apart
    two groups are in units of their own spread, and says nothing about what
    either group actually measured. This returns one row per (control, metric,
    group, age) with ``Mean``, ``SD``, ``SEM``, ``N`` and ``Median``, so a
    difference can be read in the metric's own units and a control that moves
    every group together can be told from one that moves them apart.

    Note the conditions are not the same measurement: ``"none"`` is step 4 on
    each network at its own density and size, the others are cost-integrated
    over the density grid. Both are on the metric's natural scale, but a shift
    between conditions is a change of definition as well as of control.

    *match_cohort* restricts every condition to the recordings all of them
    have, for the same reason :func:`control_effects` does.
    """
    ds, (density_only, density_and_size) = _common_cohort(
        ds, [density_only, density_and_size], match=match_cohort)

    frames = []

    raw = {m: RAW_COUNTERPART[m] for m in metrics
           if m in RAW_COUNTERPART and RAW_COUNTERPART[m] in ds.table.columns}
    if raw:
        frames.append(_values_for(ds.table, raw, ds, "none"))

    for label, integrated in (("density", density_only),
                              ("density+size", density_and_size)):
        if integrated is None or integrated.empty:
            continue
        subset = _dataset_with_integrated(ds, integrated, metrics)
        if subset is None:
            continue
        columns = {c[: -len(COST_INT_SUFFIX)]: c
                   for c in _gap_columns(subset.table, metrics)}
        frames.append(_values_for(subset.table, columns, ds, label))

    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    order = {level: i for i, level in enumerate(CONTROL_LEVELS)}
    out["_order"] = out["Control"].map(order).fillna(len(order))
    columns = ["Control", "Metric", "Group", "Age", "Mean", "SD", "SEM", "N",
               "Median"]
    return (out.sort_values(["_order", "Metric", "Group", "Age"])
            .drop(columns="_order")[columns].reset_index(drop=True))
