"""Test the spatial/temporal autocorrelation metrics (Shinn et al. 2023).

Run from the repo root::

    uv run python python/test_spatiotemporal.py

Everything here is checked against an answer known by construction rather
than against a stored output:

  A. TA-Δ₁ — equals ``np.corrcoef(x[:-1], x[1:])`` (the paper's definition) on
     arbitrary data, recovers φ from an AR(1) process, and is NaN, not 0, for a
     silent channel;
  B. SA-λ / SA-∞ — recovered exactly from a noiseless exponential-with-floor
     profile, unaffected by the zero diagonal of an adjacency matrix, and
     reported in whatever unit the distances are in;
  C. the spatiotemporal model — its surrogates have the TA-Δ₁ and (on average
     over draws) the SA curve they were asked for, as closely as the reference
     package's own do, and the same seed gives the same surrogates;
  D. density matching — same edge count and the same weights as the data, on
     the model's strongest pairs;
  E. Lin's concordance — 1 for identical values, below 1 for a shift that
     Pearson's r would not notice;
  F. ``graph_summary`` computes each metric exactly as step 4 does for the
     data, so the data and the model are never measured differently;
  G. end to end — a network that *is* spatially autocorrelated has its
     node-degree ranking predicted by the model fitted to it; shuffling node
     positions weakens that, and shuffling TA as well removes it;
  H. a step-4 pipeline run on an MCS60 layout — SA-λ comes back per recording
     in electrode pitches, the CSVs carry the new columns, switching SA/TA or
     the model on moves no other metric, the concordance CSV and figure are
     written, and an adjacency file without raw matrices is skipped cleanly;
  I. a CAT-NAP run — SA/TA on both the correlation and the event path, SA-λ in
     pixels (doubling every position doubles it), no other metric moved, the
     model's concordance written, and the new state fields round-tripping
     through the file a resumed run reads;
  J. the four settings round-trip through the GUI panel, and stay live in
     CAT-NAP mode.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

warnings.simplefilter("ignore")

from meanap.pipeline.spatiotemporal import (  # noqa: E402
    MODEL_NODE_METRICS, MODEL_REC_METRICS, bin_event_times,
    density_matched_network, graph_summary, lins_concordance,
    pairwise_distances, spatial_autocorrelation, spatial_exponential_floor,
    spatiotemporal_metrics, spatiotemporal_model_timeseries,
    temporal_autocorrelation,
)
from meanap.pipeline.step4 import compute_network_metrics  # noqa: E402
from meanap.params import Params  # noqa: E402

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


def _grid(side: int) -> np.ndarray:
    xs, ys = np.meshgrid(np.arange(side), np.arange(side))
    return np.column_stack([xs.ravel(), ys.ravel()]).astype(float)


def _ar1(phi: float, n: int, rng) -> np.ndarray:
    x = np.zeros(n)
    e = rng.standard_normal(n)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return x


def section_a() -> list[Check]:
    rng = np.random.default_rng(0)
    checks: list[Check] = []

    x = rng.standard_normal((5, 200)).cumsum(axis=1)
    ref = np.array([np.corrcoef(r[:-1], r[1:])[0, 1] for r in x])
    got = temporal_autocorrelation(x)
    checks.append(("matches np.corrcoef(x[:-1], x[1:]) row by row",
                   np.allclose(got, ref), f"max diff {np.max(np.abs(got - ref)):.2e}"))

    phis = [0.0, 0.3, 0.6, 0.9]
    est = temporal_autocorrelation(np.vstack([_ar1(p, 20000, rng) for p in phis]))
    checks.append(("recovers φ of AR(1) processes to ±0.03",
                   np.allclose(est, phis, atol=0.03), f"{np.round(est, 3)} vs {phis}"))

    flat = temporal_autocorrelation(np.vstack([np.zeros(100), np.ones(100)]))
    checks.append(("silent / constant channel is NaN", np.all(np.isnan(flat)), str(flat)))

    counts = bin_event_times([np.array([0.05, 0.15, 0.16, 0.95]), np.array([])], 1.0, 0.1)
    checks.append(("event binning counts per bin, drops nothing in range",
                   counts.shape == (2, 10) and counts[0].tolist()
                   == [1, 2, 0, 0, 0, 0, 0, 0, 0, 1] and counts[1].sum() == 0,
                   str(counts[0])))
    counts = bin_event_times([np.array([0.05, 0.99])], 0.95, 0.1)
    checks.append(("trailing partial bin is dropped", counts.shape == (1, 9), str(counts.shape)))
    return checks


def section_b() -> list[Check]:
    checks: list[Check] = []
    coords = _grid(8)
    dist = pairwise_distances(coords)
    for lam, inf in [(1.5, 0.1), (3.0, 0.3), (0.6, -0.05)]:
        corr = spatial_exponential_floor(dist, lam, inf)
        got = spatial_autocorrelation(corr, dist, n_bins=200)
        checks.append((f"recovers λ={lam}, ∞={inf} from a noiseless profile",
                       np.allclose(got, (lam, inf), rtol=2e-2, atol=2e-3),
                       f"got {np.round(got, 4)}"))

    corr = spatial_exponential_floor(dist, 2.0, 0.2)
    with_diag_one = spatial_autocorrelation(corr, dist)
    np.fill_diagonal(corr, 0.0)
    with_diag_zero = spatial_autocorrelation(corr, dist)
    checks.append(("zero diagonal (adjacency convention) changes nothing",
                   np.allclose(with_diag_one, with_diag_zero), f"{with_diag_one} vs {with_diag_zero}"))

    scaled = spatial_autocorrelation(spatial_exponential_floor(dist * 200, 400.0, 0.2),
                                     dist * 200)
    checks.append(("λ comes back in the distances' unit (×200 → λ×200)",
                   np.allclose(scaled, (400.0, 0.2), rtol=2e-2, atol=2e-3),
                   f"got {np.round(scaled, 3)}"))

    corr = spatial_exponential_floor(dist, 2.0, 0.2)
    corr[0, :] = np.nan
    corr[:, 0] = np.nan
    got = spatial_autocorrelation(corr, dist)
    checks.append(("NaN pairs (silent channels) are ignored, not propagated",
                   np.all(np.isfinite(got)), str(got)))

    # The paper's curve is pinned to 1 at distance 0. Coupling that starts lower
    # (STTC between neighbouring electrodes rarely nears 1) is fitted with a
    # shorter λ. A property of the definition, kept on purpose; pinned here so
    # the documentation of it stays true.
    lam_scaled, _ = spatial_autocorrelation(spatial_exponential_floor(dist, 2.0, 0.05) * 0.6, dist)
    checks.append(("documented bias: coupling below 1 at d→0 shortens λ (2.0 → < 1.6)",
                   lam_scaled < 1.6, f"λ={lam_scaled:.3f}"))

    two = spatial_autocorrelation(np.array([[1, .5], [.5, 1]]), np.array([[0, 1], [1, 0]]))
    checks.append(("too few distance bins → NaN, not a fit to one point",
                   np.all(np.isnan(two)), str(two)))
    return checks


def section_c() -> list[Check]:
    checks: list[Check] = []
    coords = _grid(7)
    dist = pairwise_distances(coords)
    n = len(coords)
    rng = np.random.default_rng(1)
    ta_targets = rng.uniform(0.2, 0.9, n)
    tss = spatiotemporal_model_timeseries(dist, 1.5, 0.15, ta_targets, 20000, 0.1,
                                          np.random.default_rng(2))
    ta = temporal_autocorrelation(tss)
    # Not exact per node: the reference package's own surrogates miss by the
    # same margin (r ≈ 0.91, median error ≈ 0.08 on these inputs), because one
    # realisation of brown noise has a TA-Δ₁ of its own that varies.
    r = np.corrcoef(ta, ta_targets)[0, 1]
    err = np.median(np.abs(ta - ta_targets))
    checks.append(("surrogate TA-Δ₁ tracks each node's target (r > 0.85, median |err| < 0.12)",
                   r > 0.85 and err < 0.12, f"r={r:.3f}, median |err|={err:.3f}"))

    # In expectation, not per realisation: sample correlations between brown
    # noise series are very noisy, so a single draw's fitted λ can be off by a
    # factor of two (the reference's is too). Averaged over draws the curve
    # comes back. Near-noiseless nodes, since white noise lowers each pair's
    # correlation by the product of the two nodes' signal fractions.
    seeds = np.random.default_rng(3)
    mean_corr = np.mean([np.corrcoef(spatiotemporal_model_timeseries(
        dist, 1.5, 0.15, np.full(n, 0.999), 4000, 0.1, seeds)) for _ in range(30)], axis=0)
    got = spatial_autocorrelation(mean_corr, dist)
    checks.append(("surrogate correlations follow the SA curve, on average over draws",
                   abs(got[0] - 1.5) < 0.25 and abs(got[1] - 0.15) < 0.08,
                   f"got λ={got[0]:.3f}, ∞={got[1]:.3f}"))

    high = spatiotemporal_model_timeseries(dist, 1.5, 0.15, np.full(n, 0.9999), 2000, 0.1,
                                           np.random.default_rng(3))
    checks.append(("TA target above what the spectrum gives → no noise, not NaN "
                   "(the reference returns NaN here)", np.all(np.isfinite(high)), ""))

    a = spatiotemporal_model_timeseries(dist, 1.5, 0.15, ta_targets, 1000, 0.1,
                                        np.random.default_rng(7))
    b = spatiotemporal_model_timeseries(dist, 1.5, 0.15, ta_targets, 1000, 0.1,
                                        np.random.default_rng(7))
    checks.append(("same seed → identical surrogates", np.array_equal(a, b), ""))
    odd = spatiotemporal_model_timeseries(dist, 1.5, 0.15, ta_targets, 1001, 0.1,
                                          np.random.default_rng(7))
    checks.append(("odd length is rounded down to even", odd.shape == (n, 1000), str(odd.shape)))
    return checks


def section_d() -> list[Check]:
    rng = np.random.default_rng(4)
    n = 20
    data = np.triu(rng.uniform(0.1, 1.0, (n, n)) * (rng.random((n, n)) < 0.25), 1)
    data = data + data.T
    model_corr = rng.standard_normal((n, n))
    model_corr = (model_corr + model_corr.T) / 2
    out = density_matched_network(model_corr, data)
    iu = np.triu_indices(n, 1)
    d_w, m_w = np.sort(data[iu][data[iu] > 0]), np.sort(out[iu][out[iu] > 0])
    k = d_w.size
    top = np.argsort(-model_corr[iu])[:k]
    return [
        ("symmetric, zero diagonal", np.allclose(out, out.T) and not out.diagonal().any(), ""),
        ("same number of edges as the data", m_w.size == k, f"{m_w.size} vs {k}"),
        ("same edge weights as the data", np.allclose(d_w, m_w), ""),
        ("edges sit on the model's strongest pairs",
         set(np.flatnonzero(out[iu] > 0)) == set(top), ""),
        ("strongest pair gets the strongest weight",
         out[iu][top[0]] == d_w.max(), ""),
        ("an empty data network gives an empty model network",
         not density_matched_network(model_corr, np.zeros((n, n))).any(), ""),
    ]


def section_e() -> list[Check]:
    x = np.arange(10.0)
    return [
        ("identical values → 1", np.isclose(lins_concordance(x, x), 1.0), ""),
        ("shifted values → below 1 (Pearson would say 1)",
         lins_concordance(x, x + 5) < 0.5, f"{lins_concordance(x, x + 5):.3f}"),
        ("NaN pairs dropped", np.isclose(lins_concordance(np.r_[x, np.nan], np.r_[x, 1.0]), 1.0), ""),
        ("fewer than three pairs → NaN", np.isnan(lins_concordance([1, 2], [1, 2])), ""),
    ]


def _correlated_network(coords, sa_lambda, seed, density=0.2):
    """A data network with spatial structure, as step 3 + 4 would see it."""
    dist = pairwise_distances(coords)
    n = len(coords)
    rng = np.random.default_rng(seed)
    ta = rng.uniform(0.3, 0.9, n)
    tss = spatiotemporal_model_timeseries(dist, sa_lambda, 0.05, ta, 4000, 0.1, rng)
    raw = np.corrcoef(tss)
    np.fill_diagonal(raw, 0.0)
    iu = np.triu_indices(n, 1)
    cut = np.quantile(raw[iu], 1 - density)
    adj = np.where(raw >= cut, raw, 0.0)
    np.fill_diagonal(adj, 0.0)
    return raw, adj, dist, temporal_autocorrelation(tss)


def section_f() -> list[Check]:
    params = Params()
    _raw, adj, _dist, _ta = _correlated_network(_grid(6), 1.5, 5)
    n = adj.shape[0]
    metrics = compute_network_metrics(adj, np.full(n, 100), 100.0, 0.0, 3,
                                      params=params, rng=np.random.default_rng(0))
    summary = graph_summary(metrics["adjMsub"], np.random.default_rng(0))
    checks: list[Check] = []
    for k in MODEL_REC_METRICS + MODEL_NODE_METRICS:
        a, b = np.asarray(metrics[k], dtype=float), np.asarray(summary[k], dtype=float)
        # Q is stochastic, but the same seed through the same calls in the same
        # order... is not what compute_network_metrics does (it draws SW nulls
        # first), so Q is only required to be close.
        same = np.allclose(a, b, atol=0.05) if k == "Q" else np.allclose(a, b, equal_nan=True)
        checks.append((f"{k} computed as step 4 computes it", same, f"{a} vs {b}"))
    return checks


def section_g() -> list[Check]:
    checks: list[Check] = []
    coords = _grid(8)
    raw, adj, dist, ta = _correlated_network(coords, 2.0, 6)
    n = len(coords)
    params = Params()
    metrics = compute_network_metrics(adj, np.full(n, 100), 100.0, 0.0, 3,
                                      params=params, rng=np.random.default_rng(0))
    out = spatiotemporal_metrics(metrics, raw, dist, ta, n_timepoints=4000,
                                 sample_interval_s=0.1, null_model=True, n_reps=2,
                                 rng=np.random.default_rng(1))
    expected = {"SA_lambda", "SA_inf", "TA_global", "TA_regional"}
    expected |= {f"ST_{k}" for k in MODEL_REC_METRICS}
    expected |= {f"STrho_{k}" for k in MODEL_NODE_METRICS}
    checks.append(("returns every metric", expected <= set(out),
                   str(sorted(expected - set(out)))))
    checks.append(("TA_regional has one value per active node",
                   len(out["TA_regional"]) == len(metrics["activeChannelIndex"]), ""))
    checks.append(("spatially structured network: model predicts node degree (ρ > 0.4)",
                   out["STrho_ND"] > 0.4, f"ρ={out['STrho_ND']:.3f}"))

    # Same correlations, but each node's position shuffled: SA no longer
    # describes the network. TA still does — a low-TA node carries more white
    # noise, so fewer edges, in the data and the model alike — so the ranking
    # weakens but survives. That is the paper's point: both statistics predict
    # topology.
    perm = np.random.default_rng(9).permutation(n)
    shuffled = spatiotemporal_metrics(metrics, raw, dist[np.ix_(perm, perm)], ta,
                                      n_timepoints=4000, sample_interval_s=0.1,
                                      null_model=True, n_reps=2,
                                      rng=np.random.default_rng(1))
    checks.append(("positions shuffled: SA-λ collapses and the ranking weakens",
                   shuffled["SA_lambda"] < out["SA_lambda"] / 2
                   and shuffled["STrho_ND"] < out["STrho_ND"],
                   f"λ {out['SA_lambda']:.2f}→{shuffled['SA_lambda']:.2f}, "
                   f"ρ {out['STrho_ND']:.2f}→{shuffled['STrho_ND']:.2f}"))
    # Shuffle the TA values too, and the model knows nothing true about any node.
    both = spatiotemporal_metrics(metrics, raw, dist[np.ix_(perm, perm)],
                                  ta[np.random.default_rng(10).permutation(n)],
                                  n_timepoints=4000, sample_interval_s=0.1,
                                  null_model=True, n_reps=2,
                                  rng=np.random.default_rng(1))
    checks.append(("positions and TA both shuffled: no ranking left (|ρ| < 0.25)",
                   abs(both["STrho_ND"]) < 0.25, f"ρ={both['STrho_ND']:.2f}"))

    off = spatiotemporal_metrics(metrics, raw, dist, ta, n_timepoints=4000,
                                 sample_interval_s=0.1, null_model=False)
    checks.append(("null model off → only the four statistics",
                   set(off) == {"SA_lambda", "SA_inf", "TA_global", "TA_regional"}, str(set(off))))
    checks.append(("network below the node floor → nothing",
                   spatiotemporal_metrics({"aN": 2, "activeChannelIndex": np.arange(2)},
                                          raw, dist, ta, n_timepoints=10,
                                          sample_interval_s=0.1) == {}, ""))
    return checks


def _seed_pipeline_inputs(root: Path, recs: list[str], lams: list[float]) -> None:
    """Spike trains and adjacency on a real MCS60 layout, as steps 1 and 3 leave them.

    Step 4 reads the adjacency rather than recomputing STTC, so the raw matrix
    is drawn straight from the SA curve (plus noise) with a known λ per
    recording, and the thresholded one keeps its strongest fifth. The spike
    trains differ in burstiness per channel so TA-Δ₁ has spread.
    """
    from meanap.pipeline.atomic import atomic_savez
    from meanap.pipeline.channel_layout import get_coords_from_layout, node_distances_in_pitches
    from meanap.pipeline.io import save_spike_times_npz

    channels, _ = get_coords_from_layout("MCS60")
    dist = node_distances_in_pitches("MCS60", channels)
    n = len(channels)
    for i, (rec, lam) in enumerate(zip(recs, lams)):
        rng = np.random.default_rng(100 + i)
        spikes = {}
        for ch in range(n):
            burst_starts = np.sort(rng.uniform(0, 60, 5 + ch % 20))
            burst = (burst_starts[:, None] + rng.uniform(0, 0.4, (len(burst_starts), 15))).ravel()
            spikes[ch] = {"bior1p5": np.sort(np.r_[burst, rng.uniform(0, 60, 40)])}
        save_spike_times_npz(
            root / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{rec}_spikes.npz",
            spikes, channels, 12500.0, duration_s=60.0)
        raw = spatial_exponential_floor(dist, lam, 0.05)
        raw = raw + rng.normal(0, 0.03, raw.shape)
        raw = (raw + raw.T) / 2
        np.fill_diagonal(raw, 0)
        cut = np.quantile(raw[np.triu_indices(n, 1)], 0.8)
        thr = np.where(raw >= cut, raw, 0.0)
        atomic_savez(root / "ExperimentMatFiles" / f"{rec}_adjM.npz", channels=channels,
                     adjM25mslag=thr, adjM25mslag_raw=raw)


def section_h() -> list[Check]:
    import json
    import tempfile

    import pandas as pd

    from meanap.pipeline.output_folders import create_output_folders
    from meanap.pipeline.plotting_step4 import ST_MODEL_CSV, ST_MODEL_DIR
    from meanap.pipeline.runner import run_pipeline

    recs = ["rec_A", "rec_B", "rec_C", "rec_D"]
    lams = [0.7, 1.2, 2.0, 3.0]
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pd.DataFrame([{"Recording Filename": r, "DIV group": 14, "Genotype": "WT"} for r in recs]).to_csv(tmp / "recs.csv", index=False)

        def run(name: str, seed_raw: bool = True, **kw) -> tuple[dict, Path]:
            root = create_output_folders(tmp, name, ["WT"])
            _seed_pipeline_inputs(root, recs, lams)
            if not seed_raw:
                from meanap.pipeline.atomic import atomic_savez
                for r in recs:
                    f = root / "ExperimentMatFiles" / f"{r}_adjM.npz"
                    with np.load(f) as d:
                        keep = {k: d[k] for k in d.files if not k.endswith("_raw")}
                    atomic_savez(f, **keep)
            p = Params(output_data_folder=str(tmp), output_data_folder_name=name,
                       spreadsheet_file_name=str(tmp / "recs.csv"),
                       spreadsheet_range="2:100", raw_data=str(tmp / "no-raw"),
                       start_analysis_step=4, stop_analysis_step=4,
                       func_con_lag_val=[25], channel_layout="MCS60",
                       random_seed=5, recording_workers=1,
                       compute_nmf=False, compute_eff_rank=False)
            for k, v in kw.items():
                setattr(p, k, v)
            out = run_pipeline(p, log=lambda m: None)
            return json.load(open(out / "4_NetworkActivity" / "netmet_results.json")), out

        on, on_root = run("On")
        off, _ = run("Off", compute_spatiotemporal=False)
        model, model_root = run("Model", spatiotemporal_null_model=True,
                                spatiotemporal_null_reps=2)
        stale, _ = run("Stale", seed_raw=False)

        m = on["rec_A"]["25mslag"]
        checks.append(("SA_lambda / SA_inf / TA_global / TA_regional in the results",
                       {"SA_lambda", "SA_inf", "TA_global", "TA_regional"} <= set(m),
                       str(sorted(k for k in m if k.startswith(("SA", "TA"))))))
        got = [on[r]["25mslag"]["SA_lambda"] for r in recs]
        checks.append(("SA-λ recovered per recording in electrode pitches (±25%)",
                       np.allclose(got, lams, rtol=0.25), f"{np.round(got, 2)} vs {lams}"))
        checks.append(("TA_regional has one value per active node",
                       len(m["TA_regional"]) == len(m["activeChannelIndex"]), ""))

        rec_csv = pd.read_csv(on_root / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv")
        node_csv = pd.read_csv(on_root / "4_NetworkActivity" / "NetworkActivity_NodeLevel.csv")
        checks.append(("recording-level CSV has the SA/TA columns",
                       {"SA_lambda", "SA_inf", "TA_global"} <= set(rec_csv.columns), ""))
        checks.append(("node-level CSV has TA_regional",
                       "TA_regional" in node_csv.columns
                       and node_csv["TA_regional"].notna().all(), ""))

        sa_ta = {"SA_lambda", "SA_inf", "TA_global", "TA_regional"}
        st_keys = {k for k in model["rec_A"]["25mslag"] if k.startswith(("ST_", "STrho_"))}

        def strip(res, drop):
            return {r: {k: v for k, v in res[r]["25mslag"].items() if k not in drop}
                    for r in recs}

        checks.append(("switching SA/TA off removes exactly those fields",
                       set(m) - set(off["rec_A"]["25mslag"]) == sa_ta,
                       str(set(m) ^ set(off["rec_A"]["25mslag"]))))
        checks.append(("...and every other metric is bit-for-bit unchanged",
                       json.dumps(strip(on, sa_ta), sort_keys=True)
                       == json.dumps(strip(off, set()), sort_keys=True), ""))
        checks.append(("the model adds ST_* and STrho_* fields",
                       len(st_keys) == 11, str(sorted(st_keys))))
        checks.append(("...without moving any other metric (own RNG stream)",
                       json.dumps(strip(model, st_keys), sort_keys=True)
                       == json.dumps(strip(on, set()), sort_keys=True), ""))

        conc = model_root / "4_NetworkActivity" / ST_MODEL_DIR / ST_MODEL_CSV
        table = pd.read_csv(conc) if conc.exists() else pd.DataFrame()
        checks.append(("concordance CSV written, one row per scored metric",
                       len(table) == 11, f"{len(table)} rows"))
        checks.append(("concordance figure drawn",
                       (conc.parent / "SpatiotemporalModel_25mslag.png").exists(), ""))
        checks.append(("no model → no concordance folder",
                       not (on_root / "4_NetworkActivity" / ST_MODEL_DIR).exists(), ""))

        checks.append(("adjacency without raw matrices: skipped, run still completes",
                       "SA_lambda" not in stale["rec_A"]["25mslag"]
                       and "Dens" in stale["rec_A"]["25mslag"], ""))
    return checks


def _write_spatial_suite2p(plane0: Path, seed: int, scale: float = 1.0) -> None:
    """A suite2p plane0 folder whose ROIs are correlated by distance.

    Latent event sources sit at random pixel positions; each ROI picks up each
    source with weight ``exp(−d/40 px)``, so correlation falls with distance by
    construction. *scale* multiplies every ROI position and source position —
    with the source reach scaled too, the data are the same up to units, so
    SA-λ (in pixels) must scale with it.
    """
    rng = np.random.default_rng(seed)
    plane0.mkdir(parents=True, exist_ok=True)
    n_rois, n_frames, fs = 30, 3000, 30.0
    pos = rng.uniform(0, 200, (n_rois, 2))
    src_pos = rng.uniform(0, 200, (12, 2))
    latent = np.zeros((12, n_frames))
    for k in range(12):
        for t in rng.choice(n_frames - 60, size=25, replace=False):
            latent[k, t:t + 30] += np.exp(-np.arange(30) / 8.0)
    w = np.exp(-pairwise_distances(np.vstack([pos, src_pos]))[:n_rois, n_rois:] / 40.0)
    F = 300.0 + 80.0 * (w @ latent) + rng.normal(0, 3.0, (n_rois, n_frames))
    np.save(plane0 / "F.npy", F)
    np.save(plane0 / "Fneu.npy", np.full_like(F, 100.0))
    np.save(plane0 / "spks.npy", np.clip(rng.normal(0, 1, F.shape), 0, None))
    np.save(plane0 / "iscell.npy", np.column_stack([np.ones(n_rois), np.full(n_rois, 0.9)]))
    stat = np.array([{"med": [float(y * scale), float(x * scale)],
                      "ypix": np.array([0]), "xpix": np.array([0])} for x, y in pos],
                    dtype=object)
    np.save(plane0 / "stat.npy", stat, allow_pickle=True)
    np.save(plane0 / "ops.npy", np.array({"fs": fs}, dtype=object), allow_pickle=True)


def section_i() -> list[Check]:
    import json
    import tempfile

    import pandas as pd

    from meanap.catnap.pipeline import run_catnap_pipeline
    from meanap.catnap.store import RecordingState, load_recording_state, save_recording_state
    from meanap.pipeline.output_folders import create_output_folders
    from meanap.pipeline.plotting_step4 import ST_MODEL_CSV, ST_MODEL_DIR
    from meanap.pipeline.spreadsheet import RecordingInfo

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        recs = []
        for i in range(4):
            name = f"CULT{i:02d}_DIV14"
            _write_spatial_suite2p(tmp / "raw" / name / "suite2p" / "plane0", 200 + i)
            _write_spatial_suite2p(tmp / "raw2x" / name / "suite2p" / "plane0", 200 + i, 2.0)
            recs.append(RecordingInfo(filename=name, div=14.0, group="WT"))

        def run(name: str, raw: str, activity: str, **kw) -> tuple[dict, Path]:
            out = create_output_folders(tmp, name, ["WT"])
            p = Params(suite2p_mode=True, raw_data=str(tmp / raw),
                       twop_activity=activity, twop_activities=(activity,),
                       func_con_lag_val=[500], prob_thresh_rep_num=8,
                       min_number_of_nodes_to_cal_net_met=4, num_2p_traces=0,
                       twop_network_background=False, random_seed=7,
                       recording_workers=1)
            for k, v in kw.items():
                setattr(p, k, v)
            logs: list[str] = []
            run_catnap_pipeline(p, recs, out, logs.append)
            return json.load(open(out / "4_NetworkActivity" / "netmet_results.json")), out

        f_on, f_root = run("F_on", "raw", "F")
        f_2x, _ = run("F_2x", "raw2x", "F")
        f_off, _ = run("F_off", "raw", "F", compute_spatiotemporal=False)
        pk, _ = run("Peaks", "raw", "peaks")
        model, model_root = run("F_model", "raw", "F", spatiotemporal_null_model=True,
                                spatiotemporal_null_reps=2)

        name = recs[0].filename
        m = f_on[name]["500mslag"]
        checks.append(("correlation path (F): SA/TA metrics present and finite",
                       all(np.isfinite(m.get(k, np.nan)) for k in ("SA_lambda", "SA_inf", "TA_global")),
                       str({k: m.get(k) for k in ("SA_lambda", "SA_inf", "TA_global")})))
        lam = np.array([f_on[r.filename]["500mslag"]["SA_lambda"] for r in recs])
        lam2 = np.array([f_2x[r.filename]["500mslag"]["SA_lambda"] for r in recs])
        checks.append(("SA-λ is in pixels: doubling every position doubles it (±5%)",
                       np.allclose(lam2 / lam, 2.0, rtol=0.05), f"ratios {np.round(lam2 / lam, 3)}"))
        mp = pk[name]["500mslag"]
        checks.append(("event path (peaks): SA/TA metrics present",
                       {"SA_lambda", "TA_global", "TA_regional"} <= set(mp), ""))
        checks.append(("TA_regional: one value per active node",
                       len(m["TA_regional"]) == len(m["activeChannelIndex"]), ""))

        sa_ta = {"SA_lambda", "SA_inf", "TA_global", "TA_regional"}
        strip = lambda res, drop: json.dumps(
            {r: {k: v for k, v in res[r]["500mslag"].items() if k not in drop} for r in res},
            sort_keys=True)
        checks.append(("switching SA/TA on moves no other metric",
                       strip(f_on, sa_ta) == strip(f_off, set()), ""))
        st = {k for k in model[name]["500mslag"] if k.startswith(("ST_", "STrho_"))}
        checks.append(("the model adds 11 ST fields and moves nothing else",
                       len(st) == 11 and strip(model, st) == strip(f_on, set()),
                       str(sorted(st))))
        conc = model_root / "4_NetworkActivity" / ST_MODEL_DIR / ST_MODEL_CSV
        checks.append(("concordance CSV written in the CAT-NAP output",
                       conc.exists() and len(pd.read_csv(conc)) == 11, str(conc)))
        rec_csv = pd.read_csv(f_root / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv")
        checks.append(("recording-level CSV carries SA/TA",
                       {"SA_lambda", "SA_inf", "TA_global"} <= set(rec_csv.columns), ""))

        path = tmp / "state.npz"
        raw = np.random.default_rng(0).random((5, 5))
        state = RecordingState(
            adjMs={"adjM500mslag": raw}, coords=np.zeros((5, 2)), channels=np.arange(5),
            spike_counts=np.ones(5), duration_s=100.0, plane0=tmp,
            adjMs_raw={"adjM500mslag": raw},
            ta_inputs={"adjM500mslag": {"ta": np.linspace(0, 1, 5), "n_timepoints": 200,
                                         "bin_s": 0.5}})
        save_recording_state(path, state, {"FRmean": 0.5})
        back, _ = load_recording_state(path, tmp)
        ta = back.ta_inputs.get("adjM500mslag", {})
        checks.append(("raw matrices + TA inputs survive save/load (resume, bundles)",
                       np.allclose(back.adjMs_raw["adjM500mslag"], raw, atol=1e-3)
                       and np.allclose(ta.get("ta"), np.linspace(0, 1, 5))
                       and ta.get("n_timepoints") == 200 and ta.get("bin_s") == 0.5, ""))
        state.adjMs_raw, state.ta_inputs = {}, {}
        save_recording_state(path, state, {"FRmean": 0.5})
        back, _ = load_recording_state(path, tmp)
        checks.append(("a state without them loads with them empty",
                       back.adjMs_raw == {} and back.ta_inputs == {}, ""))
    return checks


def section_j() -> list[Check]:
    """The settings round-trip through the GUI panel — a ``Params`` field with
    no widget would be reset to its default on every GUI run."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from meanap.gui.panels.connectivity import ConnectivityPanel

    app = QApplication.instance() or QApplication([])  # noqa: F841
    fields = ("compute_spatiotemporal", "ta_bin_ms", "spatiotemporal_null_model",
              "spatiotemporal_null_reps")
    checks: list[Check] = []
    for label, values in [("defaults", Params()),
                          ("non-defaults", Params(compute_spatiotemporal=False, ta_bin_ms=250.0,
                                                  spatiotemporal_null_model=True,
                                                  spatiotemporal_null_reps=7))]:
        panel = ConnectivityPanel()
        panel.load(values)
        out = Params()
        panel.save(out)
        got = tuple(getattr(out, f) for f in fields)
        want = tuple(getattr(values, f) for f in fields)
        checks.append((f"GUI round trip keeps the {label}", got == want, f"{got} vs {want}"))
    panel = ConnectivityPanel()
    panel.set_pipeline("catnap")
    checks.append(("the box stays live in CAT-NAP mode (both pipelines read it)",
                   panel.compute_spatiotemporal.isEnabled(), ""))
    return checks


def main() -> int:
    total_pass = total = 0
    for title, fn in [
        ("A. Temporal autocorrelation (TA-Δ₁)", section_a),
        ("B. Spatial autocorrelation (SA-λ, SA-∞)", section_b),
        ("C. Spatiotemporal model surrogates", section_c),
        ("D. Density-matched model network", section_d),
        ("E. Lin's concordance", section_e),
        ("F. Model metrics computed as the data's", section_f),
        ("G. End to end on synthetic networks", section_g),
        ("H. Step 4 pipeline run (MCS60)", section_h),
        ("I. CAT-NAP pipeline run", section_i),
        ("J. GUI settings", section_j),
    ]:
        p, t = _report(title, fn())
        total_pass += p
        total += t
    print(f"\nTOTAL: {total_pass}/{total} passed")
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
