"""Test the density sweep — topology measured at matched connection density.

Run from the repo root::

    uv run python python/test_density_sweep.py

The sweep exists to remove a confound, so the checks are mostly about whether
it actually removes it. Section A works on graphs whose topology is known by
construction (ring lattices, random graphs, disconnected graphs), where the
right answer can be stated rather than eyeballed:

  - proportional thresholding realises the density it was asked for, and says
    so honestly when it cannot;
  - a lattice is separated from a random graph *at the same density*, which is
    the whole premise — if the sweep could not do that it would be measuring
    nothing;
  - two graphs that differ only in edge *strength* give identical sweeps, which
    is the confound the binarisation is there to remove;
  - cost integration reduces to the mean over the range on curves whose
    integral is known;
  - ``lccFraction`` reports fragmentation correctly, since path length is only
    trustworthy where it is high.

Section B runs the whole sweep over a small synthetic output folder, and
Section C over the real Yin run when the gitignored ``local/`` folder is there.
"""

from __future__ import annotations

import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

warnings.simplefilter("ignore")

from meanap.stats.density_sweep import (  # noqa: E402
    CONTROL_LEVELS, DEFAULT_DENSITIES, RAW_COUNTERPART, SWEEP_METRICS,
    _largest_component_fraction, attach_labels, binarise_at_density,
    control_effects, control_values, cost_integrate, decompose_targets,
    group_gaps, lag_key_to_label, retention, run_density_sweep,
    selection_sensitivity, subsample_nodes, sweep_one_matrix,
)

Check = tuple[str, bool, str]

BUNDLE = REPO_ROOT / "local" / "YinThesisRun.meanap"


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


def _density(binary: np.ndarray) -> float:
    n = binary.shape[0]
    return float(binary[np.triu_indices(n, 1)].mean())


def _ring_lattice(n: int, k: int, rng) -> np.ndarray:
    """Each node joined to its ``k`` nearest neighbours around a ring.

    High clustering, long paths — the topology the sweep must tell apart from a
    random graph of the same density. Weights are random so that binarising is
    doing real work rather than reading an already-binary matrix.
    """
    w = np.zeros((n, n))
    for i in range(n):
        for offset in range(1, k // 2 + 1):
            j = (i + offset) % n
            weight = rng.uniform(0.5, 1.0)
            w[i, j] = w[j, i] = weight
    return w


def _random_graph(n: int, k: int, rng) -> np.ndarray:
    w = np.zeros((n, n))
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    chosen = rng.choice(len(pairs), size=n * k // 2, replace=False)
    for index in chosen:
        i, j = pairs[index]
        w[i, j] = w[j, i] = rng.uniform(0.5, 1.0)
    return w


# ── Section A ────────────────────────────────────────────────────────────────

def _threshold_checks() -> list[Check]:
    rng = np.random.default_rng(4)
    checks: list[Check] = []

    w = rng.uniform(0, 1, (60, 60))
    w = (w + w.T) / 2
    np.fill_diagonal(w, 0)

    realised = {}
    for target in (0.02, 0.1, 0.25, 0.4):
        binary = binarise_at_density(w, target)
        realised[target] = _density(binary)
    checks.append((
        "the realised density matches the target",
        all(abs(realised[t] - t) < 0.005 for t in realised),
        str({k: round(v, 4) for k, v in realised.items()})))

    binary = binarise_at_density(w, 0.1)
    checks.append((
        "the result is binary, symmetric and self-loop free",
        set(np.unique(binary)) <= {0.0, 1.0} and np.allclose(binary, binary.T)
        and np.allclose(np.diag(binary), 0), ""))

    sparse = np.zeros((30, 30))
    sparse[0, 1] = sparse[1, 0] = 1.0
    checks.append((
        "a density the matrix cannot reach returns None, not a wrong answer",
        binarise_at_density(sparse, 0.5) is None, ""))
    checks.append((
        "a matrix too small to be a graph returns None",
        binarise_at_density(np.zeros((2, 2)), 0.5) is None, ""))

    # Strength is discarded, so scaling every weight must change nothing.
    scaled = binarise_at_density(w * 7.3, 0.1)
    checks.append((
        "rescaling every edge weight leaves the thresholded graph identical",
        np.array_equal(binary, scaled), ""))
    return checks


def _topology_checks() -> list[Check]:
    """The premise: at equal density, does the sweep separate known topologies?"""
    rng = np.random.default_rng(11)
    checks: list[Check] = []
    # k = 16 on 80 nodes is n*k/2 = 640 of 3160 possible edges, so the graphs
    # carry ~20% density and every target below that is reachable. With a
    # sparser fixture the top of the sweep is simply absent from the matrix and
    # the sweep correctly returns NaN — which is right, but tests nothing.
    n, k = 80, 16
    lattice = _ring_lattice(n, k, rng)
    random_graph = _random_graph(n, k, rng)

    densities = (0.05, 0.1, 0.15)
    lat = sweep_one_matrix(lattice, densities, modularity_reps=5, seed=1)
    ran = sweep_one_matrix(random_graph, densities, modularity_reps=5, seed=1)

    checks.append((
        "a lattice is more clustered than a random graph at every density",
        bool(np.all(lat["CC"] > ran["CC"])),
        f"lattice {np.round(lat['CC'], 3)} vs random {np.round(ran['CC'], 3)}"))
    checks.append((
        "and less globally efficient at every density",
        bool(np.all(lat["Eglob"] < ran["Eglob"])),
        f"lattice {np.round(lat['Eglob'], 3)} vs random {np.round(ran['Eglob'], 3)}"))
    checks.append((
        "efficiency rises with density, as adding edges must",
        bool(np.all(np.diff(ran["Eglob"]) > 0)), str(np.round(ran["Eglob"], 3))))

    # The confound the binarisation removes: two graphs identical in topology
    # but different in strength must sweep identically.
    weaker = lattice * 0.11
    weak = sweep_one_matrix(weaker, densities, modularity_reps=5, seed=1)
    same = all(np.allclose(lat[m], weak[m], equal_nan=True)
               for m in ("CC", "Eglob", "ElocMean", "PL"))
    checks.append((
        "halving every edge weight changes no swept metric",
        same, "strength leaked into the sweep"))

    checks.append((
        "every requested metric is returned, one value per density",
        all(m in lat and len(lat[m]) == len(densities) for m in SWEEP_METRICS),
        str(sorted(set(SWEEP_METRICS) - set(lat)))))
    return checks


def _component_checks() -> list[Check]:
    checks: list[Check] = []
    connected = np.zeros((10, 10))
    for i in range(9):
        connected[i, i + 1] = connected[i + 1, i] = 1.0
    checks.append((
        "a connected graph reports a largest component of 1",
        _largest_component_fraction(connected) == 1.0, ""))

    split = np.zeros((10, 10))
    for i in (0, 1, 2):
        split[i, i + 1] = split[i + 1, i] = 1.0
    for i in (6, 7):
        split[i, i + 1] = split[i + 1, i] = 1.0
    checks.append((
        "a split graph reports the larger part",
        _largest_component_fraction(split) == 0.4,
        f"{_largest_component_fraction(split)}"))
    checks.append((
        "an edgeless graph is all singletons",
        _largest_component_fraction(np.zeros((10, 10))) == 0.1, ""))

    # A sparse threshold fragments a network; the sweep has to say so, because
    # path length is only averaged over pairs that remain connected.
    rng = np.random.default_rng(5)
    w = _ring_lattice(60, 10, rng)
    swept = sweep_one_matrix(w, (0.01, 0.15), metrics=("lccFraction",),
                             modularity_reps=5)
    checks.append((
        "fragmentation at sparse densities is reported, not hidden",
        swept["lccFraction"][0] < swept["lccFraction"][1],
        str(np.round(swept["lccFraction"], 3))))
    return checks


def _integration_checks() -> list[Check]:
    checks: list[Check] = []
    densities = np.linspace(0.02, 0.4, 20)

    flat = pd.DataFrame({"FileName": "r1", "Lag": "adjM25mslag",
                         "Density": densities, "CC": 0.42, "Eglob": np.nan})
    out = cost_integrate(flat, metrics=("CC", "Eglob"))
    checks.append((
        "integrating a constant curve returns the constant",
        abs(float(out["CC_costInt"].iloc[0]) - 0.42) < 1e-9,
        str(out["CC_costInt"].tolist())))
    checks.append((
        "an all-missing metric integrates to NaN rather than zero",
        bool(np.isnan(out["Eglob_costInt"].iloc[0])), ""))

    # A straight line integrates to its midpoint value.
    linear = pd.DataFrame({"FileName": "r1", "Lag": "adjM25mslag",
                           "Density": densities, "CC": 3.0 * densities})
    mid = 3.0 * (densities[0] + densities[-1]) / 2
    got = float(cost_integrate(linear, metrics=("CC",))["CC_costInt"].iloc[0])
    checks.append((
        "integrating a straight line returns its midpoint value",
        abs(got - mid) < 1e-9, f"{got:.6f} vs {mid:.6f}"))

    two = pd.concat([flat, flat.assign(FileName="r2", CC=0.10)])
    out2 = cost_integrate(two, metrics=("CC",))
    checks.append((
        "one row per recording, and they keep their own values",
        len(out2) == 2 and set(np.round(out2["CC_costInt"], 3)) == {0.42, 0.1},
        str(out2.to_dict("records"))))
    checks.append((
        "the number of usable densities is recorded",
        int(out2["NDensities"].iloc[0]) == len(densities), ""))
    return checks


def _label_checks() -> list[Check]:
    from meanap.stats.dataset import StatsDataset, metric_labels

    checks: list[Check] = []
    checks.append(("the lag key is translated to the step-5 label",
                   lag_key_to_label("adjM1000mslag") == "1000mslag", ""))
    checks.append(("a label already in step-5 form is left alone",
                   lag_key_to_label("1000mslag") == "1000mslag", ""))

    table = pd.DataFrame({
        "FileName": ["a_DIV14", "b_DIV14"], "Culture": ["a", "b"],
        "Grp": ["WT", "KO"], "DIV": [14.0, 14.0], "Lag": ["25mslag"] * 2,
        "Dens": [0.1, 0.2]})
    ds = StatsDataset(table=table, metrics=["Dens"], labels=metric_labels())
    curves = pd.DataFrame({
        "FileName": ["a_DIV14", "b_DIV14", "ghost"],
        "Lag": ["adjM25mslag"] * 3, "Density": [0.1, 0.1, 0.1], "CC": [1.0, 2.0, 3.0]})
    joined = attach_labels(curves, ds)
    checks.append((
        "group and age are joined on by recording name",
        set(joined["Grp"]) == {"WT", "KO"} and len(joined) == 2, str(len(joined))))
    checks.append((
        "a swept recording the statistics step never saw is dropped",
        "ghost" not in set(joined["FileName"]), ""))
    return checks


def _subsample_checks() -> list[Check]:
    """Controlling network size — the other half of van Wijk's problem."""
    rng = np.random.default_rng(13)
    checks: list[Check] = []

    w = _ring_lattice(80, 16, rng)
    sub = subsample_nodes(w, 30, rng)
    checks.append((
        "a subsample is a square symmetric induced subgraph of the right size",
        sub.shape == (30, 30) and np.allclose(sub, sub.T)
        and np.allclose(np.diag(sub), 0), str(sub.shape)))
    checks.append((
        "every edge in the subgraph existed in the original",
        bool(np.isin(np.unique(sub[sub > 0]), np.unique(w[w > 0])).all()), ""))
    checks.append((
        "a network smaller than the target cannot be subsampled",
        subsample_nodes(w, 200, rng) is None, ""))
    checks.append((
        "asking for the network's own size returns it unchanged",
        subsample_nodes(w, 80, rng) is w, ""))

    # Two networks of very different size but the same topology must agree once
    # both are cut to a common size. This is the property subsampling exists
    # for, and it fails without it.
    small = _ring_lattice(60, 12, rng)
    large = _ring_lattice(240, 48, rng)
    densities = (0.05, 0.1)
    plain_s = sweep_one_matrix(small, densities, modularity_reps=5, seed=2)
    plain_l = sweep_one_matrix(large, densities, modularity_reps=5, seed=2)
    sized_s = sweep_one_matrix(small, densities, n_nodes=50, n_subsamples=8,
                               modularity_reps=5, seed=2)
    sized_l = sweep_one_matrix(large, densities, n_nodes=50, n_subsamples=8,
                               modularity_reps=5, seed=2)
    plain_gap = float(np.nanmax(np.abs(plain_s["BCmean"] - plain_l["BCmean"])))
    sized_gap = float(np.nanmax(np.abs(sized_s["BCmean"] - sized_l["BCmean"])))
    checks.append((
        "size-matching shrinks the gap between a small and a large network",
        sized_gap < plain_gap,
        f"betweenness gap {plain_gap:.4f} unmatched vs {sized_gap:.4f} matched"))

    # Averaging over draws must actually average: one draw is noisier than many.
    spreads = []
    for n_draws in (1, 12):
        values = [sweep_one_matrix(large, (0.1,), n_nodes=40, n_subsamples=n_draws,
                                   modularity_reps=5, seed=100 + s)["CC"][0]
                  for s in range(6)]
        spreads.append(float(np.std(values)))
    checks.append((
        "averaging more draws gives a more stable answer",
        spreads[1] < spreads[0],
        f"sd over seeds: {spreads[0]:.4f} with 1 draw, {spreads[1]:.4f} with 12"))
    checks.append((
        "the same seed reproduces the same subsampled sweep",
        np.allclose(
            sweep_one_matrix(large, densities, n_nodes=50, n_subsamples=4,
                             modularity_reps=5, seed=9)["CC"],
            sweep_one_matrix(large, densities, n_nodes=50, n_subsamples=4,
                             modularity_reps=5, seed=9)["CC"], equal_nan=True), ""))
    return checks


def _retention_checks() -> list[Check]:
    """Retention is the number that says whether subsampling traded one confound
    for another, so it has to be right."""
    checks: list[Check] = []
    observed = pd.DataFrame({
        "FileName": [f"r{i}" for i in range(10)],
        "Grp": ["WT"] * 5 + ["KO"] * 5,
        "NNodes": [10, 20, 90, 95, 99] + [90, 91, 92, 93, 94],
        "Retained": [False, False, True, True, True] + [True] * 5,
    })
    out = retention(observed).set_index("Group")
    checks.append((
        "retention is reported per group",
        set(out.index) == {"WT", "KO"}, str(out.index.tolist())))
    checks.append((
        "and counts what was actually kept",
        out.loc["WT", "NKept"] == 3 and out.loc["KO", "NKept"] == 5
        and abs(out.loc["WT", "Fraction"] - 0.6) < 1e-9, out.to_dict()))
    checks.append((
        "differential loss between groups is visible in the output",
        out.loc["KO", "Fraction"] > out.loc["WT", "Fraction"], ""))
    checks.append((
        "an unlabelled table still reports an overall figure",
        retention(observed.drop(columns=["Grp"])).iloc[0]["NKept"] == 8, ""))
    checks.append((
        "an empty table gives an empty result rather than an error",
        retention(pd.DataFrame()).empty, ""))
    return checks


def _frame(values_by_group: dict, metric: str = "CC") -> pd.DataFrame:
    """A cost-integrated table: ``{group: [values]}`` laid out one row each."""
    rows = []
    for group, values in values_by_group.items():
        for value in values:
            rows.append({"FileName": f"r{len(rows)}", "Grp": group,
                         f"{metric}_costInt": float(value)})
    return pd.DataFrame(rows)


def _gap_checks() -> list[Check]:
    """Pairwise group gaps - the quantity both new analyses are differences of."""
    checks: list[Check] = []

    frame = _frame({"A": [1.0] * 4, "B": [0.0] * 4})
    table = group_gaps(frame)
    spread = float(np.std([1, 1, 1, 1, 0, 0, 0, 0], ddof=1))
    row = table[table.Metric == "CC"].iloc[0]
    checks.append((
        "a gap is the difference in means over the pooled SD",
        abs(row.Gap - 1.0 / spread) < 1e-12, f"{row.Gap:.6f} vs {1/spread:.6f}"))
    checks.append((
        "and the pair is ordered by the group labels, so signs are stable",
        row.GroupA == "A" and row.GroupB == "B", f"{row.GroupA}/{row.GroupB}"))
    checks.append((
        "group sizes are carried alongside",
        row.NA == 4 and row.NB == 4, f"{row.NA}/{row.NB}"))

    three = group_gaps(_frame({"A": [1.0] * 3, "B": [0.0] * 3, "C": [2.0] * 3}))
    checks.append((
        "three groups give all three pairs",
        len(three) == 3, str(len(three))))

    # lccFraction is a fragmentation diagnostic; comparing it between groups is
    # a statement about connectedness, not topology, so it is not a gap metric.
    with_lcc = _frame({"A": [1.0] * 4, "B": [0.0] * 4})
    with_lcc["lccFraction_costInt"] = 1.0
    checks.append((
        "lccFraction is excluded from gap tables",
        "lccFraction" not in set(group_gaps(with_lcc).Metric), ""))

    checks.append((
        "a group too small to compare is skipped rather than guessed at",
        group_gaps(_frame({"A": [1.0] * 2, "B": [0.0] * 4})).empty, ""))
    checks.append((
        "a metric with no spread is skipped rather than dividing by zero",
        group_gaps(_frame({"A": [1.0] * 4, "B": [1.0] * 4})).empty, ""))
    checks.append((
        "an empty table gives an empty result",
        group_gaps(pd.DataFrame()).empty, ""))
    return checks


def _selection_checks() -> list[Check]:
    """The free half of A/B/C: re-reading one sweep over the larger networks."""
    checks: list[Check] = []

    # Built so the answer is known: over everything the two groups are
    # identical, and over the large networks alone they are as far apart as the
    # data allows. Any honest check must call that out.
    integrated = pd.DataFrame({
        "FileName": [f"r{i}" for i in range(40)],
        "Grp": (["WT"] * 10 + ["KO"] * 10) * 2,
        "CC_costInt": ([1.0] * 10 + [0.0] * 10) + ([0.0] * 10 + [1.0] * 10),
    })
    observed = pd.DataFrame({
        "FileName": [f"r{i}" for i in range(40)],
        "NNodes": [100] * 20 + [30] * 20,
    })

    check = selection_sensitivity(integrated, observed, threshold=100)
    checks.append((
        "the check runs and reports the cohort it restricted to",
        check.ran and check.threshold == 100 and check.n_all == 40
        and check.n_restricted == 20,
        f"{check.n_restricted}/{check.n_all} at {check.threshold}"))
    row = check.table[check.table.Metric == "CC"].iloc[0]
    checks.append((
        "a gap that is zero overall but real in the large networks is caught",
        abs(row.GapAll) < 1e-12 and abs(row.GapRestricted) > 0.5,
        f"{row.GapAll:.3f} -> {row.GapRestricted:.3f}"))
    checks.append((
        "Delta is exactly the movement between the two cohorts",
        abs(row.Delta - (row.GapRestricted - row.GapAll)) < 1e-12, ""))
    checks.append((
        "and it is flagged, since that is selection rather than topology",
        bool(row.Flagged) and ("CC", "KO", "WT") in check.flagged,
        str(check.flagged)))

    # The opposite case: restricting changes nothing, so nothing is flagged.
    steady = pd.DataFrame({
        "FileName": [f"r{i}" for i in range(40)],
        "Grp": (["WT"] * 10 + ["KO"] * 10) * 2,
        "CC_costInt": ([1.0] * 10 + [0.0] * 10) * 2,
    })
    quiet = selection_sensitivity(steady, observed, threshold=100)
    checks.append((
        "a gap with the same group means in both cohorts is not flagged",
        quiet.ran and not quiet.flagged
        # Not exactly zero: each gap is standardised within its own cohort, so
        # the pooled SD moves with the sample even when the means do not.
        and abs(quiet.table.iloc[0].Delta) < 0.05,
        f"delta {quiet.table.iloc[0].Delta:.4f}, flagged {quiet.flagged}"))

    thin = selection_sensitivity(integrated, observed, threshold=1000)
    checks.append((
        "a threshold nothing clears is refused, with a reason",
        not thin.ran and "clear" in thin.note, thin.note))

    same = selection_sensitivity(integrated, observed, threshold=1)
    checks.append((
        "a threshold that drops almost nothing is refused too",
        not same.ran and "drops only" in same.note, same.note))

    checks.append((
        "a sweep with no node counts is refused rather than guessed at",
        not selection_sensitivity(
            integrated, observed.drop(columns=["NNodes"])).ran, ""))
    checks.append((
        "an unlabelled table is refused rather than compared with no groups",
        not selection_sensitivity(
            integrated.drop(columns=["Grp"]), observed).ran, ""))
    return checks


def _decomposition_checks() -> list[Check]:
    """The full A/B/C design: selection and resolution split apart."""
    checks: list[Check] = []
    rng = np.random.default_rng(5)

    names = [f"r{i}" for i in range(40)]
    groups = ["WT"] * 20 + ["KO"] * 20
    low = pd.DataFrame({
        "FileName": names, "Grp": groups,
        "CC_costInt": np.concatenate([rng.normal(0.3, 0.3, 20),
                                      rng.normal(0.0, 0.3, 20)]),
    })
    # B keeps only the first half of each group, and resolves them far better -
    # the separation has to grow against the within-group spread, since a
    # standardised gap carries the separation in its denominator too.
    keep = names[:10] + names[20:30]
    high = pd.DataFrame({
        "FileName": keep, "Grp": ["WT"] * 10 + ["KO"] * 10,
        "CC_costInt": np.concatenate([rng.normal(1.5, 0.3, 10),
                                      rng.normal(0.0, 0.3, 10)]),
    })

    table = decompose_targets(low, high)
    row = table[table.Metric == "CC"].iloc[0]
    checks.append((
        "the decomposition reports all three conditions",
        {"GapA", "GapC", "GapB"} <= set(table.columns), str(table.columns.tolist())))
    checks.append((
        "selection and resolution sum to the whole difference between targets",
        abs((row.Selection + row.Resolution) - row.Total) < 1e-12,
        f"{row.Selection:.4f}+{row.Resolution:.4f} vs {row.Total:.4f}"))
    checks.append((
        "C is A read over B's recordings, not a separate measurement",
        abs(row.GapC - group_gaps(low[low.FileName.isin(keep)]).iloc[0].Gap) < 1e-12,
        ""))
    checks.append((
        "the cohort sizes are those of the three conditions",
        row.NA == 40 and row.NC == 20 and row.NB == 20,
        f"{row.NA}/{row.NC}/{row.NB}"))
    checks.append((
        "the dominant term is named, and here it is resolution",
        row.Dominant == "resolution"
        and abs(row.Resolution) > abs(row.Selection),
        f"{row.Dominant}: sel {row.Selection:.3f} res {row.Resolution:.3f}"))

    # A high target whose cohort is a *biased* subset moves the gap without any
    # change of target - that is the selection term, and it must show up as one.
    biased_keep = names[:4] + names[20:]
    biased = decompose_targets(
        low, low[low.FileName.isin(biased_keep)].copy())
    checks.append((
        "with B measured identically to A, the whole difference is selection",
        abs(biased.iloc[0].Resolution) < 1e-12
        and biased.iloc[0].Dominant == "selection",
        f"res {biased.iloc[0].Resolution:.4f}"))

    checks.append((
        "no shared recordings gives an empty result rather than an error",
        decompose_targets(
            low, high.assign(FileName=lambda d: d.FileName + "_x")).empty, ""))
    checks.append((
        "an empty target table gives an empty result",
        decompose_targets(low, pd.DataFrame()).empty, ""))
    return checks


def _control_dataset():
    """A small run: two genotypes, three ages, six cultures each."""
    from meanap.stats.dataset import StatsDataset, metric_labels

    rng = np.random.default_rng(3)
    rows = []
    for group, shift in (("WT", 0.0), ("KO", 1.0)):
        for culture in range(6):
            for age in (14.0, 21.0, 28.0):
                name = f"{group}{culture}_DIV{int(age)}"
                rows.append({
                    "FileName": name, "Culture": f"{group}{culture}",
                    "Grp": group, "DIV": age, "Lag": "25mslag",
                    # Raw metrics carry a strong age effect on top of genotype.
                    "CC_rawMean": 0.3 * shift + 0.05 * age + rng.normal(0, 0.1),
                    "Eglob": 0.2 * shift + 0.04 * age + rng.normal(0, 0.1),
                    "Q": 0.4 * shift + rng.normal(0, 0.1),
                    # The null-model-normalised CC, which must NOT be used.
                    "CC": 99.0 + rng.normal(0, 0.1),
                })
    table = pd.DataFrame(rows)
    ds = StatsDataset(table=table, metrics=["CC_rawMean", "Eglob", "Q", "CC"],
                      labels=metric_labels())
    # Controlled features: genotype kept, the age effect removed.
    integrated = pd.DataFrame({
        "FileName": table["FileName"], "Lag": "adjM25mslag",
        "CC_costInt": [0.3 * (g == "KO") + rng.normal(0, 0.1)
                       for g in table["Grp"]],
        "Eglob_costInt": [0.2 * (g == "KO") + rng.normal(0, 0.1)
                          for g in table["Grp"]],
        "Q_costInt": [0.4 * (g == "KO") + rng.normal(0, 0.1)
                      for g in table["Grp"]],
    })
    return ds, integrated


def _control_effect_checks() -> list[Check]:
    """Effects recomputed under each level of control."""
    checks: list[Check] = []
    ds, integrated = _control_dataset()

    checks.append((
        "the raw counterpart of CC is the unnormalised one, not NetMet.CC",
        RAW_COUNTERPART["CC"] == "CC_rawMean" and RAW_COUNTERPART["PL"] == "PL_raw",
        str(RAW_COUNTERPART)))
    checks.append((
        "betweenness has no step-4 counterpart and is not invented one",
        "BCmean" not in RAW_COUNTERPART, ""))

    two = control_effects(ds, density_and_size=integrated)
    checks.append((
        "a single sweep gives the uncontrolled and the controlled condition",
        set(two["Control"]) == {"none", "density+size"},
        str(sorted(set(two["Control"])))))
    checks.append((
        "columns are named by the swept metric, not by the source column",
        set(two["Metric"]) <= {"CC", "Eglob", "Q"}, str(sorted(set(two["Metric"])))))
    checks.append((
        "both an age term and a genotype contrast are reported",
        "age" in set(two["Term"])
        and any(" vs " in str(t) for t in two["Term"]), str(sorted(set(two["Term"])))))

    # The fixture removes the age effect under control and keeps genotype, so
    # the table must show exactly that - this is the figure's whole reading.
    age = two[two["Term"] == "age"].set_index(["Metric", "Control"])["EffectSize"]
    shrank = all(abs(age[(m, "density+size")]) < abs(age[(m, "none")])
                 for m in ("CC", "Eglob") if (m, "none") in age.index)
    checks.append((
        "an age effect the control removes shows as a smaller effect size",
        shrank, age.round(2).to_dict()))

    three = control_effects(ds, density_only=integrated,
                            density_and_size=integrated)
    checks.append((
        "with both sweeps present all three levels of control appear",
        set(three["Control"]) == set(CONTROL_LEVELS),
        str(sorted(set(three["Control"])))))

    # NetMet.CC is a different quantity from what the sweep measures, so a run
    # carrying only it must not silently pair the two.
    without_raw = ds.table.drop(columns=["CC_rawMean"])
    bare = control_effects(ds._with_table(without_raw),
                           density_and_size=integrated)
    uncontrolled = bare[bare["Control"] == "none"]
    checks.append((
        "with no raw counterpart, the normalised metric is not substituted",
        "CC" not in set(uncontrolled["Metric"]),
        str(sorted(set(uncontrolled["Metric"])))))

    checks.append((
        "no sweep at all gives only the uncontrolled condition",
        set(control_effects(ds)["Control"]) == {"none"}, ""))
    checks.append((
        "a table that joins onto nothing gives an empty result",
        control_effects(
            ds._with_table(ds.table.drop(columns=["CC_rawMean", "Eglob", "Q"])),
            density_and_size=integrated.assign(
                FileName=lambda d: d.FileName + "_x")).empty, ""))
    return checks


def _per_age_checks() -> list[Check]:
    """Genotype contrasts measured at each age, and the metrics themselves."""
    checks: list[Check] = []
    ds, integrated = _control_dataset()
    effects = control_effects(ds, density_and_size=integrated)

    per_age = effects[effects["Scope"] == "per-age"]
    checks.append((
        "the table separates pooled models from per-age contrasts",
        set(effects["Scope"]) == {"pooled", "per-age"},
        str(sorted(set(effects["Scope"])))))
    checks.append((
        "every age in the run gets its own contrast",
        set(per_age["Age"].dropna()) == {14.0, 21.0, 28.0},
        str(sorted(set(per_age["Age"].dropna())))))
    checks.append((
        "the age is stripped off the term, so a pair can be followed across ages",
        all(" at DIV " not in str(c) for c in per_age["Contrast"]),
        str(sorted(set(per_age["Contrast"])))))
    checks.append((
        "per-age contrasts are Hedges' g, never the model's beta",
        set(per_age["EffectSizeName"]) == {"Hedges g"},
        str(set(per_age["EffectSizeName"]))))
    checks.append((
        "and they are reported under each level of control",
        set(per_age["Control"]) == {"none", "density+size"},
        str(sorted(set(per_age["Control"])))))

    values = control_values(ds, density_and_size=integrated)
    checks.append((
        "the value table carries a row per control, metric, group and age",
        len(values) == len(set(map(tuple, values[
            ["Control", "Metric", "Group", "Age"]].to_numpy()))),
        f"{len(values)} rows"))
    checks.append((
        "with the summary statistics an effect size cannot give",
        {"Mean", "SD", "SEM", "N", "Median"} <= set(values.columns),
        str(values.columns.tolist())))

    # The means must be the data's own, not something rescaled on the way.
    raw = values[(values.Control == "none") & (values.Metric == "CC")
                 & (values.Group == "WT") & (values.Age == 14.0)]
    expected = ds.table[(ds.table.Grp == "WT") & (ds.table.DIV == 14.0)][
        "CC_rawMean"].mean()
    checks.append((
        "a mean is the mean of the metric it names",
        abs(float(raw["Mean"].iloc[0]) - float(expected)) < 1e-12,
        f"{float(raw['Mean'].iloc[0]):.4f} vs {float(expected):.4f}"))
    checks.append((
        "the standard error is the SD over root n",
        abs(float(raw["SEM"].iloc[0])
            - float(raw["SD"].iloc[0]) / np.sqrt(float(raw["N"].iloc[0]))) < 1e-12,
        ""))
    checks.append((
        "the uncontrolled column reads the raw metric, never the normalised one",
        abs(float(raw["Mean"].iloc[0]) - 99.0) > 1.0,
        f"{float(raw['Mean'].iloc[0]):.3f} (NetMet.CC was set to 99)"))
    checks.append((
        "no sweep gives values for the uncontrolled condition only",
        set(control_values(ds)["Control"]) == {"none"}, ""))
    checks.append((
        "an empty dataset gives an empty table rather than an error",
        control_values(ds._with_table(ds.table.iloc[0:0])).empty, ""))
    return checks


# ── Section B ────────────────────────────────────────────────────────────────

def _folder_checks() -> list[Check]:
    """The whole sweep over a small synthetic output folder."""
    checks: list[Check] = []
    rng = np.random.default_rng(7)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mats = root / "ExperimentMatFiles"
        mats.mkdir(parents=True)
        for i in range(4):
            w = _ring_lattice(40, 8, rng) if i % 2 else _random_graph(40, 8, rng)
            # An isolated node, to check it is dropped rather than deflating
            # every path-based metric.
            w[0, :] = w[:, 0] = 0.0
            np.savez(mats / f"rec{i}_catnap.npz", adj__adjM25mslag=w)

        res = run_density_sweep(root, densities=(0.05, 0.1, 0.2),
                                modularity_reps=5, n_jobs=1)
        checks.append((
            "every recording and density appears once",
            len(res.curves) == 4 * 3
            and res.curves["FileName"].nunique() == 4, f"{len(res.curves)} rows"))
        checks.append((
            "the disconnected node is dropped from the swept network",
            bool((res.observed["NNodes"] == 39).all()),
            str(res.observed["NNodes"].tolist())))
        checks.append((
            "the observed density is recorded per recording",
            res.observed["ObservedDensity"].between(0, 1).all(), ""))
        checks.append((
            "cost-integrated features come out, one row per recording",
            len(res.integrated) == 4
            and "CC_costInt" in res.integrated.columns, str(res.integrated.columns.tolist())))
        checks.append(("nothing was skipped", not res.skipped, str(res.skipped)))

        try:
            run_density_sweep(root / "nope", n_jobs=1)
            ok, detail = False, "no error raised"
        except ValueError as exc:
            ok, detail = "adjacency" in str(exc).lower(), str(exc)
        checks.append(("a folder with no matrices says so actionably", ok, detail))

    # The cost-integrated names must be classified as topology, or the family
    # decomposition would drop them into "other".
    from meanap.stats.decoding import family_of

    unclassified = [f"{m}_costInt" for m in ("CC", "PL", "Eglob", "Q")
                    if family_of(f"{m}_costInt") != "topology"]
    checks.append((
        "cost-integrated metrics are classified as topology",
        not unclassified, str(unclassified)))
    checks.append((
        "the fragmentation diagnostic is deliberately not a topology feature",
        family_of("lccFraction_costInt") == "other", ""))
    return checks


# ── Section C ────────────────────────────────────────────────────────────────

def _real_checks(root: Path) -> list[Check]:
    from meanap.stats.dataset import load_dataset

    checks: list[Check] = []
    ds = load_dataset(root)
    names = [p.name.replace("_catnap.npz", "")
             for p in sorted((root / "ExperimentMatFiles").glob("*_catnap.npz"))][:6]
    res = run_density_sweep(root, recordings=names, densities=DEFAULT_DENSITIES,
                            modularity_reps=5)

    checks.append((
        "the default grid is Schroeter et al.'s 2-40% in 2% steps",
        len(DEFAULT_DENSITIES) == 20 and abs(DEFAULT_DENSITIES[0] - 0.02) < 1e-9
        and abs(DEFAULT_DENSITIES[-1] - 0.40) < 1e-9, str(DEFAULT_DENSITIES[:3])))
    checks.append((
        "every requested recording produced a full curve",
        res.curves["FileName"].nunique() == len(names)
        and (res.curves.groupby("FileName").size() == 20).all(), ""))

    means = res.curves.groupby("Density")[["Eglob", "lccFraction"]].mean()
    checks.append((
        "efficiency rises monotonically with imposed density on real data",
        bool(np.all(np.diff(means["Eglob"]) > 0)), ""))
    checks.append((
        "these networks fragment at the sparsest densities",
        means["lccFraction"].iloc[0] < 0.8 < means["lccFraction"].iloc[-1],
        f"{means['lccFraction'].iloc[0]:.2f} at 2% to "
        f"{means['lccFraction'].iloc[-1]:.2f} at 40%"))
    checks.append((
        "observed densities are far above the swept range",
        res.observed["ObservedDensity"].median() > max(DEFAULT_DENSITIES),
        f"median observed {res.observed['ObservedDensity'].median():.2f}"))

    labelled = attach_labels(res.curves, ds)
    checks.append((
        "labels join onto the real run",
        not labelled.empty and labelled[ds.group_col].notna().all(), ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("Density sweep — topology at matched connection density")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [
        ("Section A1 — proportional thresholding:", _threshold_checks),
        ("Section A2 — known topologies at equal density:", _topology_checks),
        ("Section A3 — fragmentation:", _component_checks),
        ("Section A4 — cost integration:", _integration_checks),
        ("Section A5 — joining labels:", _label_checks),
        ("Section A6 — node subsampling:", _subsample_checks),
        ("Section A7 — retention:", _retention_checks),
        ("Section A8 — group gaps:", _gap_checks),
        ("Section A9 — selection sensitivity:", _selection_checks),
        ("Section A10 — selection vs resolution:", _decomposition_checks),
        ("Section A11 — effects under control:", _control_effect_checks),
        ("Section A12 — per-age contrasts and metric values:", _per_age_checks),
        ("Section B — a whole output folder:", _folder_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if root is not None and (root / "ExperimentMatFiles").is_dir():
        p, n = _report("Section C — the real run:", _real_checks(root))
        total_pass += p
        total += n
    else:
        print("\nSection C — SKIPPED (pass an extracted run folder as argv[1])")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
