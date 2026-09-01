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
    "binarise_at_density",
    "cost_integrate",
    "run_density_sweep",
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
