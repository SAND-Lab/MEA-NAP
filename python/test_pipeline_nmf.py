"""Structural/sanity tests for NMF dimensionality metrics (``nmf.py``).

Run from the repo root::

    uv run python python/test_pipeline_nmf.py

``cal_nmf`` is not just stochastic but *algorithm*-different from MATLAB's
``calNMF.m`` (sklearn's coordinate-descent NMF solver standing in for
MATLAB's built-in ``nnmf``, which defaults to Alternating Least Squares —
see ``nmf.py``'s docstring), so there is no meaningful MATLAB parity check
to run here. What *is* testable: the mathematical invariants the algorithm
should satisfy regardless of which NNMF solver computed it (spike-count
preservation through the "wrap" randomization and binning helpers,
variance-explained converging toward 1 as rank approaches the active-
electrode count, bounded/sane outputs, no crashes) — same rationale as
``test_pipeline_null_models.py``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline.nmf import _bin_spike_times, cal_nmf, randomise_spike_train


def _make_synthetic_recording(rng, n_channels=24, duration_s=120.0, n_components=3):
    component_rates = rng.uniform(0.3, 1.5, size=n_components)
    loadings = rng.random((n_channels, n_components))
    spike_times_list = []
    for ch in range(n_channels):
        times = []
        for c in range(n_components):
            rate = component_rates[c] * loadings[ch, c]
            n_spikes = rng.poisson(rate * duration_s)
            times.append(rng.uniform(0, duration_s, n_spikes))
        times = np.sort(np.concatenate(times)) if times else np.array([])
        spike_times_list.append(times)
    spike_counts = np.array([len(t) for t in spike_times_list])
    return spike_times_list, spike_counts


def test_randomise_spike_train_preserves_count() -> bool:
    print("\n[1] randomise_spike_train — spike count preserved, times stay in bounds")
    rng = np.random.default_rng(0)
    duration_s = 100.0
    times = np.sort(rng.uniform(0, duration_s, 50))
    randomised = randomise_spike_train(times, duration_s, rng)

    checks = {
        "count preserved": len(randomised) == len(times),
        "all times in [0, duration)": bool(np.all((randomised >= 0) & (randomised < duration_s))),
        "actually changed something": not np.allclose(np.sort(randomised), times),
        "empty input handled": len(randomise_spike_train(np.array([]), duration_s, rng)) == 0,
    }
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    return all(checks.values())


def test_bin_spike_times_preserves_count() -> bool:
    print("\n[2] _bin_spike_times — total spike count preserved through binning")
    rng = np.random.default_rng(1)
    duration_s = 60.0
    spike_times_list = [np.sort(rng.uniform(0, duration_s, rng.integers(10, 100))) for _ in range(5)]
    total_before = sum(len(t) for t in spike_times_list)

    binned = _bin_spike_times(spike_times_list, duration_s, n_bins=600)
    total_after = int(binned.sum())

    checks = {
        "total spike count preserved": total_before == total_after,
        "shape matches (n_bins, n_channels)": binned.shape == (600, 5),
        "non-negative counts": bool(np.all(binned >= 0)),
    }
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    return all(checks.values())


def test_cal_nmf_sanity() -> bool:
    print("\n[3] cal_nmf — sanity checks on a synthetic low-rank recording")
    rng = np.random.default_rng(2)
    n_channels = 24
    duration_s = 120.0
    spike_times_list, spike_counts = _make_synthetic_recording(rng, n_channels, duration_s)

    t0 = time.time()
    result = cal_nmf(spike_times_list, spike_counts, duration_s, downsample_freq=10.0, fs=25000.0, rng=rng)
    elapsed = time.time() - t0
    print(f"    done in {elapsed:.1f}s (n={n_channels} channels, {duration_s:.0f}s recording)")

    var_explained = result["nnmf_var_explained"]
    residuals = result["nnmf_residuals"]
    num_components = result["num_nnmf_components"]

    checks = {
        "num_nnmf_components is a positive int <= n_channels": 0 < num_components <= n_channels,
        "nComponentsRelNS bounded in (0, 1]": 0 < result["nComponentsRelNS"] <= 1.0,
        "var_explained bounded in [0, 1]": bool(np.all((var_explained >= -1e-6) & (var_explained <= 1 + 1e-6))),
        "var_explained approaches ~1 at full rank": var_explained[-1] > 0.9,
        "var_explained roughly increasing (last > first)": var_explained[-1] > var_explained[0],
        "residuals non-negative": bool(np.all(residuals >= 0)),
        "residuals roughly decreasing (last < first)": residuals[-1] < residuals[0],
        "no NaN in var_explained": not np.any(np.isnan(var_explained)),
        "randResidualPerComponent has >= 1 entry": len(result["randResidualPerComponent"]) >= 1,
    }
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    return all(checks.values())


def test_cal_nmf_include_components() -> bool:
    print("\n[4] cal_nmf — include_nmf_components=True returns factor matrices")
    rng = np.random.default_rng(3)
    n_channels = 10
    duration_s = 60.0
    spike_times_list, spike_counts = _make_synthetic_recording(rng, n_channels, duration_s, n_components=2)

    result = cal_nmf(
        spike_times_list, spike_counts, duration_s, downsample_freq=10.0, fs=25000.0,
        include_nmf_components=True, rng=rng,
    )

    checks = {
        "downSampleSpikeMatrix present": "downSampleSpikeMatrix" in result,
        "nmfFactors present": result.get("nmfFactors") is not None,
        "nmfWeights present": result.get("nmfWeights") is not None,
        "nmfFactorsVarThreshold present": result.get("nmfFactorsVarThreshold") is not None,
        "nmfWeightsVarThreshold present": result.get("nmfWeightsVarThreshold") is not None,
        "nmfFactors non-negative": bool(np.all(result["nmfFactors"] >= 0)) if result.get("nmfFactors") is not None else False,
    }
    for name, ok in checks.items():
        print(f"    {'✓' if ok else '✗'} {name}")
    return all(checks.values())


def main() -> None:
    print("=" * 70)
    print("MEA-NAP Python  ▸  NMF Structural/Sanity Tests")
    print("=" * 70)

    ok1 = test_randomise_spike_train_preserves_count()
    ok2 = test_bin_spike_times_preserves_count()
    ok3 = test_cal_nmf_sanity()
    ok4 = test_cal_nmf_include_components()

    print(f"\n{'=' * 70}")
    if ok1 and ok2 and ok3 and ok4:
        print("  → All checks passed")
    else:
        print("  → Some checks FAILED — see above")
        sys.exit(1)
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
