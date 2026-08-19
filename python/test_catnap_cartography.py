"""Test CAT-NAP's node-cartography barrier and its use of the shared 4A figures.

Run from the repo root::

    uv run python python/test_catnap_cartography.py

Two things are checked here.

**The barrier.** Node-cartography roles depend on five boundaries in the
participation-coefficient / within-module-z-score plane. MATLAB
(``autoSetCartographyBoundaries``) places them from the *pooled* PC/Z of the
whole batch, not from the fixed ``Params`` defaults — otherwise nearly every
node is classified as a peripheral node. The ephys path does this in its
step-4 reduce phase; CAT-NAP did not, so its ``NCpn*`` columns were wrong. That
means CAT-NAP has to compute every recording *before* it plots any, and these
checks pin that ordering down: by the time a recording is plotted, the pooled
boundaries must already be on its metrics.

**The figures.** CAT-NAP now draws the same 4A figure set as the ephys path
through the shared ``_plot_recording_lag``, fed suite2p cell centroids via
``coords_all`` instead of an MEA electrode layout. These checks confirm the
whole set renders from a coordinate array with no channel layout involved.

All synthetic — no dataset needed, so this always runs.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap import pipeline as cp  # noqa: E402
from meanap.catnap.adjacency import Suite2pAdjmResult  # noqa: E402
from meanap.catnap.loader import Suite2pData  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402
from meanap.pipeline.step4 import (  # noqa: E402
    _apply_cartography_boundaries, compute_network_metrics,
)

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


N_NODES = 60


def _modular_adj(seed: int, n: int = N_NODES, n_mod: int = 3) -> np.ndarray:
    """A weighted, modular graph — dense within modules, sparse between.

    Node cartography only separates roles when the graph actually has modules;
    a uniformly random graph puts every node in the same corner of the PC/Z
    plane and the check would pass vacuously.
    """
    rng = np.random.default_rng(seed)
    module = np.arange(n) % n_mod
    same = module[:, None] == module[None, :]
    weights = rng.uniform(0.05, 0.4, (n, n))
    weights[same] = rng.uniform(0.4, 1.0, (n, n))[same]
    keep = rng.random((n, n)) < np.where(same, 0.8, 0.15)
    adj = np.where(keep, weights, 0.0)
    adj = np.triu(adj, 1)
    adj = adj + adj.T
    return adj


def _metrics_for(seed: int, params: Params) -> dict:
    adj = _modular_adj(seed)
    spike_counts = np.full(N_NODES, 100.0)
    return compute_network_metrics(
        adj, spike_counts, 600.0, params.min_activity_level, 25,
        exclude_edges_below_threshold=params.exclude_edges_below_threshold,
        params=params, rng=np.random.default_rng(seed),
    )


# ── Section A — the barrier itself ────────────────────────────────────────────

def _boundary_checks() -> list[Check]:
    checks: list[Check] = []
    params = Params()
    all_results = {f"rec{i}": {"1000mslag": _metrics_for(i, params)} for i in range(3)}

    before = {name: dict(res["1000mslag"]) for name, res in all_results.items()}
    checks.append((
        "fixed-boundary roles exist before the barrier",
        all("NdCartDiv" in m and "cartographyBoundaries" not in m
            for m in before.values()), "",
    ))

    logs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        _apply_cartography_boundaries(params, all_results, logs.append, out_dir=Path(tmp))
        landscape = (Path(tmp) / "4B_GroupComparisons" / "7_DensityLandscape"
                     / "ZandPC_scatter_with_kmeans_boundaries_.png")
        checks.append(("pooled PC/Z landscape figure is written",
                       landscape.exists() and landscape.stat().st_size > 0, ""))

    after = {name: res["1000mslag"] for name, res in all_results.items()}
    checks.append((
        "boundaries are recorded on every recording",
        all("cartographyBoundaries" in m for m in after.values()), "",
    ))
    checks.append((
        "all recordings share one boundary set (derived from the pooled batch)",
        len({tuple(m["cartographyBoundaries"]) for m in after.values()}) == 1, "",
    ))
    checks.append((
        "derived boundaries differ from the fixed Params defaults",
        tuple(next(iter(after.values()))["cartographyBoundaries"])
        != (params.hub_boundary_wm_d_deg, params.peri_part_coef,
            params.non_hub_connector_part_coef, params.pro_hub_part_coef,
            params.connector_hub_part_coef), "",
    ))

    reclassified = any(
        not np.array_equal(before[name]["NdCartDiv"], after[name]["NdCartDiv"])
        for name in all_results
    )
    checks.append(("nodes are actually re-classified", reclassified, ""))

    # The headline symptom of the bug: with fixed boundaries nearly everything
    # lands in role 1, and the six proportions must still sum to 1 afterwards.
    frac_sums = [sum(m[f"NCpn{i + 1}"] for i in range(6)) for m in after.values()]
    checks.append(("role proportions still sum to 1",
                   all(abs(s - 1.0) < 1e-9 for s in frac_sums), f"{frac_sums}"))
    counts_match = all(
        sum(m[f"NCpn{i + 1}count"] for i in range(6)) == int(m["aN"])
        for m in after.values()
    )
    checks.append(("role counts still sum to the active-node count", counts_match, ""))
    checks.append(("the barrier logged which boundaries it derived",
                   any("Cartography boundaries" in line for line in logs),
                   "; ".join(logs)))
    return checks


# ── Section B — phase ordering inside run_catnap_pipeline ─────────────────────

def _ordering_checks() -> list[Check]:
    """Drive ``run_catnap_pipeline`` with stubbed I/O and record the call order.

    The point is the *barrier*: no recording may be plotted until every
    recording has been computed and the pooled boundaries applied. Stubbing
    suite2p loading and adjacency keeps this to a second or two.
    """
    checks: list[Check] = []
    params = Params(
        func_con_lag_val=[1000], min_activity_level=0.0,
        min_number_of_nodes_to_cal_net_met=25, random_seed=1,
    )
    recordings = [RecordingInfo(filename=f"rec{i}", div=14.0 + 7 * i, group="WT")
                  for i in range(3)]

    events: list[tuple[str, str]] = []
    plotted_state: dict[str, bool] = {}

    # Build the stubs from the *real* dataclasses rather than hand-rolled
    # look-alikes: a field added to Suite2pData or Suite2pAdjmResult then arrives
    # here with its default instead of raising AttributeError halfway through a
    # run, which is exactly how this test broke three times while the pipeline
    # grew.
    def _fake_res(seed: int) -> Suite2pAdjmResult:
        return Suite2pAdjmResult(
            adjMs={"adjM1000mslag": _modular_adj(seed)},
            coords=np.random.default_rng(seed).uniform(0, 8, (N_NODES, 2)),
            channels=np.arange(N_NODES) + 1,
            F=np.zeros((600, N_NODES)),
            denoised_F=None,
            spks=np.zeros((600, N_NODES)),
            spike_times=[np.array([1.0, 2.0])] * N_NODES,
            fs=1.0,
            activity_properties={},
            func_con_lag_val=[1000],
        )

    originals = {
        "load_suite2p": cp.load_suite2p,
        "suite2p_to_adjm": cp.suite2p_to_adjm,
        "_activity_stats_for": cp._activity_stats_for,
        "_plot_recording": cp._plot_recording,
    }
    seeds = {rec.filename: i for i, rec in enumerate(recordings)}

    def fake_load(plane0, derived_root=None, recording=None):
        return Suite2pData(F=np.zeros((N_NODES, 600)),
                           F_denoised=np.zeros((N_NODES, 600)))

    def fake_adjm(data, *a, **kw):
        name = fake_adjm.current
        events.append(("compute", name))
        return _fake_res(seeds[name])

    def fake_stats(res, params_, duration_s):
        return {"FR": np.full(N_NODES, 0.5), "numActiveElec": N_NODES}

    def fake_plot(params_, rec, state, rec_results, batch_bounds, output_root, log,
                  *args, **kwargs):
        events.append(("plot", rec.filename))
        plotted_state[rec.filename] = all(
            "cartographyBoundaries" in m for m in rec_results.values()
        )

    try:
        cp.load_suite2p = fake_load
        cp.suite2p_to_adjm = fake_adjm
        cp._activity_stats_for = fake_stats
        cp._plot_recording = fake_plot

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            params.raw_data = str(root / "raw")
            for rec in recordings:
                plane0 = cp.suite2p_plane0_dir(params.raw_data, rec.filename)
                plane0.mkdir(parents=True, exist_ok=True)
                (plane0 / "stat.npy").write_bytes(b"")

            # suite2p_to_adjm is called once per recording, in order; track which.
            order = iter([rec.filename for rec in recordings])
            real_adjm = fake_adjm

            def stepping_adjm(data, *a, **kw):
                real_adjm.current = next(order)
                return real_adjm(data, *a, **kw)

            cp.suite2p_to_adjm = stepping_adjm
            cp.run_catnap_pipeline(params, recordings, root / "out",
                                   log=lambda m: None)
    finally:
        for name, fn in originals.items():
            setattr(cp, name, fn)

    computes = [name for kind, name in events if kind == "compute"]
    plots = [name for kind, name in events if kind == "plot"]
    kinds = [kind for kind, _ in events]

    checks.append(("every recording was computed", len(computes) == 3, f"{computes}"))
    checks.append(("every recording was plotted", len(plots) == 3, f"{plots}"))
    checks.append((
        "no recording is plotted before all are computed",
        "compute" not in kinds[kinds.index("plot"):] if "plot" in kinds else False,
        f"{kinds}",
    ))
    checks.append((
        "each recording's metrics carry the pooled boundaries when plotted",
        bool(plotted_state) and all(plotted_state.values()), f"{plotted_state}",
    ))
    return checks


# ── Section C — the shared 4A figure set on suite2p coordinates ───────────────

def _figure_checks() -> list[Check]:
    from meanap.pipeline.step4 import _plot_recording_lag

    checks: list[Check] = []
    params = Params()
    metrics = _metrics_for(0, params)
    all_results = {"rec0": {"1000mslag": metrics}}
    _apply_cartography_boundaries(params, all_results, lambda m: None)

    rec = RecordingInfo(filename="rec0", div=21.0, group="HET")
    channels = np.arange(N_NODES) + 1
    coords = np.random.default_rng(0).uniform(0, 8, (N_NODES, 2))

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _plot_recording_lag(
            rec, 1000, metrics, channels, params, out, lambda m: None,
            {"ND": (0.0, 40.0), "NS": (0.0, 20.0), "BC": None, "PC": None, "Eloc": None},
            coords_all=coords,
        )
        lag_dir = out / "4A_IndividualNetworkAnalysis" / "HET" / "rec0" / "1000mslag"
        made = {p.name for p in lag_dir.glob("*.png")} if lag_dir.exists() else set()

        for name in ("1_adjM1000msConnectivityStats.png",
                     "2_MEA_NetworkPlot.png",
                     "4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png",
                     "5_MEA_NetworkPlotNodestrengthLocalefficiency.png",
                     "6_circular_NetworkPlotNodedegreeModule.png",
                     "7_adjM1000msGraphMetricsByNode.png",
                     "9_adjM1000msNodeCartography.png",
                     "9_circular_NetworkPlotNodeCartography.png"):
            checks.append((f"4A figure on suite2p coords: {name}", name in made,
                           f"{sorted(made)}"))

        checks.append(("batch-scaled variants are produced too",
                       any("_scaled_" in n for n in made) and any("combined" in n for n in made),
                       f"{sorted(made)}"))
        checks.append(("every figure is a non-empty PNG",
                       all((lag_dir / n).stat().st_size > 0 for n in made), ""))

        # The cartography figure must use the derived boundaries, not the
        # Params defaults — that is the whole point of running it after the
        # barrier.
        checks.append(("cartography metrics carry derived boundaries",
                       "cartographyBoundaries" in metrics, ""))

    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP node cartography")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [
        ("Section A — pooled cartography boundaries:", _boundary_checks),
        ("Section B — compute/plot phase ordering:", _ordering_checks),
        ("Section C — shared 4A figures on suite2p coordinates:", _figure_checks),
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
