"""Binned correlation on the ``F`` / ``spks`` / ``denoised F`` paths.

These paths never involved a lag: they correlate whole traces at zero lag, and
the number in the output folder was only ever the frame period, filed under a
name (``30mslag``) that read like a 30 ms STTC window. So the number is now a
real, user-chosen *bin* — the traces are averaged into bins that long before
correlating — and the folder says ``msbin``.

What is checked here is that the binning is the binning anyone would expect
(the arithmetic, the dropped tail, the scale-invariance that lets one code path
serve both "mean the fluorescence" and "sum the spikes"), and that the old
behaviour is still reachable rather than merely gone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from meanap.catnap.adjacency import (  # noqa: E402
    _bin_columns, _corr_columns, frames_per_bin, suite2p_to_adjm,
)
from meanap.catnap.loader import Suite2pData  # noqa: E402
from meanap.timescale import (  # noqa: E402
    is_correlation_run, timescale_folder, timescale_kind,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


FS = 33.3
N_FRAMES, N_ROIS = 2000, 6


def make_data() -> Suite2pData:
    """A small suite2p recording with real correlation structure to find."""
    rng = np.random.default_rng(7)
    t = np.arange(N_FRAMES) / FS
    # Two cells share a slow drive, two share a fast one, two are noise. The
    # slow pair should only become visibly correlated once bins are long.
    slow = np.sin(2 * np.pi * 0.05 * t)
    fast = np.sin(2 * np.pi * 5.0 * t)
    F = np.vstack([
        slow + rng.normal(0, 3, N_FRAMES),
        slow + rng.normal(0, 3, N_FRAMES),
        fast + rng.normal(0, 0.5, N_FRAMES),
        fast + rng.normal(0, 0.5, N_FRAMES),
        rng.normal(0, 1, N_FRAMES),
        rng.normal(0, 1, N_FRAMES),
    ])
    return Suite2pData(
        F=F, spks=np.abs(F), iscell=np.ones((N_ROIS, 2)),
        xy_loc=rng.uniform(0, 500, (2, N_ROIS)), fs=FS,
        n_frames=N_FRAMES, duration_s=N_FRAMES / FS,
    )


# ── The arithmetic ────────────────────────────────────────────────────────────

print("\nBinning arithmetic")

check("a bin is rounded to whole frames",
      frames_per_bin(1000, FS) == 33, str(frames_per_bin(1000, FS)))
check("a bin shorter than a frame collapses to one, not zero",
      frames_per_bin(1, FS) == 1 and frames_per_bin(0, FS) == 1, "")

x = np.arange(20.0).reshape(10, 2)
binned = _bin_columns(x, 3)
check("bins are the mean over their frames",
      np.allclose(binned[0], x[0:3].mean(axis=0)), str(binned[0]))
check("the trailing partial bin is dropped",
      binned.shape == (3, 2), str(binned.shape))
check("a one-frame bin is the identity — the old un-binned behaviour",
      _bin_columns(x, 1) is x, "")
# _bin_columns is pure arithmetic: too-few-frames is caught by the caller,
# which clamps the bin so at least two survive (checked below).
check("more frames per bin than rows leaves nothing to correlate",
      _bin_columns(x, 99).shape == (0, 2), str(_bin_columns(x, 99).shape))

# Pearson is scale-invariant and every kept bin holds the same frame count, so
# "mean the fluorescence" and "sum the spikes" cannot disagree. This is what
# lets one code path serve both readings.
summed = x[:9].reshape(3, 3, 2).sum(axis=1)
check("summing instead of averaging gives the same correlations",
      np.allclose(_corr_columns(binned), _corr_columns(summed)), "")


# ── What binning does to the adjacency ────────────────────────────────────────

print("\nBinning changes the adjacency, and in the right direction")

data = make_data()
res = suite2p_to_adjm(data, "F", [30, 1000, 5000])

check("one adjacency per requested bin, mirroring one per lag",
      sorted(res.adjMs) == ["adjM1000mslag", "adjM30mslag", "adjM5000mslag"],
      str(sorted(res.adjMs)))
check("the realised frame counts are reported back",
      res.bin_frames == {30: 1, 1000: 33, 5000: 167}, str(res.bin_frames))
check("the requested bins are what the run says it used",
      res.func_con_lag_val == [30, 1000, 5000], str(res.func_con_lag_val))

fine = res.adjMs["adjM30mslag"]
coarse = res.adjMs["adjM1000mslag"]
check("a one-frame bin reproduces the un-binned correlation exactly",
      np.allclose(fine, _corr_columns(data.F.T)), "")
check("a longer bin gives a genuinely different matrix",
      not np.allclose(fine, coarse), "")
# Cells 0,1 share a 0.05 Hz drive buried under noise: averaging over ~1 s of
# frames is exactly what should pull it out.
check("slow shared structure is recovered by long bins, not short ones",
      coarse[0, 1] > fine[0, 1] + 0.2, f"{fine[0, 1]:.3f} -> {coarse[0, 1]:.3f}")
# Cells 2,3 share a 5 Hz drive, which a 1 s bin averages away.
check("fast shared structure is averaged away by long bins",
      coarse[2, 3] < fine[2, 3], f"{fine[2, 3]:.3f} -> {coarse[2, 3]:.3f}")



# ── A bin too long for the recording ──────────────────────────────────────────

print("\nA bin longer than the recording")

# 2000 frames at 33.3 Hz is a 60 s recording. Correlating needs two bins to
# correlate across; one bin spanning everything has no variance at all, and an
# all-NaN adjacency would carry the whole downstream run into nothing.
long_bin = suite2p_to_adjm(data, "F", [600_000])
check("an over-long bin is shortened rather than left unusable",
      long_bin.bin_frames[600_000] == N_FRAMES // 2,
      str(long_bin.bin_frames))
adj = long_bin.adjMs["adjM600000mslag"]
check("…so the adjacency it produces is a real matrix, not NaN",
      not np.isnan(adj).any(), "")
check("…and it is still filed under the bin that was asked for",
      list(long_bin.adjMs) == ["adjM600000mslag"], str(list(long_bin.adjMs)))


# ── Continuity with what ran before ───────────────────────────────────────────

print("\nOld runs still reproduce")

# Before bins were settable this path produced exactly one matrix, at the frame
# period. An empty lag list is what a params file predating the field looks
# like, and it has to keep meaning that.
legacy = suite2p_to_adjm(data, "F", [])
check("no timescales at all falls back to the single frame-period matrix",
      list(legacy.adjMs) == [f"adjM{round(1000 / FS)}mslag"], str(list(legacy.adjMs)))
check("…and that matrix is the un-binned correlation",
      np.allclose(legacy.adjMs[f"adjM{round(1000 / FS)}mslag"],
                  _corr_columns(data.F.T)), "")

# An old CAT-NAP params file carrying ephys-scale lags rounds every one of them
# to a single frame, so it still reproduces its old numbers.
old_params = suite2p_to_adjm(data, "F", [10, 15, 25])
check("ephys-scale lags in an old file still give the old result",
      all(np.allclose(m, _corr_columns(data.F.T))
          for m in old_params.adjMs.values()), "")


# ── The peaks path is untouched ───────────────────────────────────────────────

print("\nThe STTC path is unaffected")

peaks_data = make_data()
# Minimal denoising outputs so the peaks branch can run: two peaks per cell.
peaks_data.F_denoised = peaks_data.F.copy()
starts = np.tile(np.array([100.0, 900.0]), (N_ROIS, 1))
peaks_data.peak_start_frames = starts
peaks_data.peak_end_frames = starts + 20
peaks_data.peak_heights = np.ones((N_ROIS, 2))
peaks_data.event_areas = np.ones((N_ROIS, 2))

peaks_res = suite2p_to_adjm(peaks_data, "peaks", [1000, 2500],
                            prob_thresh_rep_num=10,
                            rng=np.random.default_rng(0))
check("every correlation path bins the same way",
      all(np.allclose(
          suite2p_to_adjm(peaks_data, a, [1000]).adjMs["adjM1000mslag"],
          _corr_columns(_bin_columns(
              {"F": peaks_data.F, "spks": peaks_data.spks,
               "denoised F": peaks_data.F_denoised}[a].T, 33)))
          for a in ("F", "spks", "denoised F")), "")

check("a peaks run reports no bins — it never binned anything",
      peaks_res.bin_frames == {}, str(peaks_res.bin_frames))
check("…and still builds one adjacency per STTC lag",
      sorted(peaks_res.adjMs) == ["adjM1000mslag", "adjM2500mslag"],
      str(sorted(peaks_res.adjMs)))


# ── What the outputs are called ───────────────────────────────────────────────

print("\nNaming")


class _P:
    def __init__(self, suite2p_mode, twop_activity):
        self.suite2p_mode, self.twop_activity = suite2p_mode, twop_activity


ephys = _P(False, "peaks")
cat_peaks = _P(True, "peaks")
cat_corr = _P(True, "F")

check("only a CAT-NAP correlation run is a bin run",
      (is_correlation_run(cat_corr)
       and not is_correlation_run(cat_peaks)
       and not is_correlation_run(ephys)), "")
check("folders say what the number is",
      (timescale_folder(1000, cat_corr) == "1000msbin"
       and timescale_folder(1000, cat_peaks) == "1000mslag"
       and timescale_folder(1000, ephys) == "1000mslag"),
      timescale_folder(1000, cat_corr))
check("prose follows the same rule",
      timescale_kind(cat_corr) == "bin" and timescale_kind(ephys) == "lag", "")

# The adjMs keys deliberately do NOT change: they are shared with the ephys
# pipeline, are what MATLAB writes, and are recorded in every existing bundle.
check("the structural key keeps its historical spelling",
      all(k.endswith("mslag") for k in res.adjMs), str(list(res.adjMs)))


# ── Self-correlations must not become edges ───────────────────────────────
# MATLAB's suite2pToAdjm.m stores corr(...) verbatim, leaving a diagonal of 1
# — the largest weight in the matrix — which inflates Dens (past 1.0), NS and
# both sigEdges* metrics. The ETTC path has always returned a zero diagonal,
# so without this the two measures were not comparable graphs.
for activity in ("F", "spks", "denoised F"):
    r = suite2p_to_adjm(peaks_data, activity, [1000])
    a = r.adjMs["adjM1000mslag"]
    check(f"{activity}: correlation adjacency has a zero diagonal",
          a.shape[0] > 1 and np.allclose(np.diag(a), 0.0), str(np.diag(a)[:4]))

corr_adj = suite2p_to_adjm(peaks_data, "spks", [1000]).adjMs["adjM1000mslag"]
ettc_adj = peaks_res.adjMs["adjM1000mslag"]
check("both measures agree about self-edges",
      np.allclose(np.diag(corr_adj), np.diag(ettc_adj)),
      f"corr={np.diag(corr_adj)[:3]} ettc={np.diag(ettc_adj)[:3]}")

import meanap.pipeline.network_metrics as _nm  # noqa: E402
n = corr_adj.shape[0]
check("density stays a proportion",
      0.0 <= _nm.density_und(corr_adj) <= 1.0,
      f"{_nm.density_und(corr_adj):.4f}")
with_loops = corr_adj.copy()
np.fill_diagonal(with_loops, 1.0)
check("...which it would not with self-loops present",
      _nm.density_und(with_loops) > _nm.density_und(corr_adj),
      f"{_nm.density_und(with_loops):.4f} vs {_nm.density_und(corr_adj):.4f}")
check("off-diagonal correlations are untouched by the fix",
      np.allclose(corr_adj[~np.eye(n, dtype=bool)],
                  with_loops[~np.eye(n, dtype=bool)]), "")

# ── Probabilistic thresholding of correlations ────────────────────────────────

print("\nCircular-shift thresholding on the correlation paths")

from meanap.catnap.adjacency import threshold_correlation  # noqa: E402
from meanap.params import Params  # noqa: E402

check("on by default for a run", Params().twop_corr_prob_thresh is True, "")

binned = _bin_columns(data.F.T, 33)
raw = _corr_columns(binned)
thr = threshold_correlation(binned, 0.05, 200, np.random.default_rng(1))

check("thresholding only ever removes edges",
      np.all((thr == 0) | np.isclose(thr, raw)), "")
check("the matrix stays symmetric with a zero diagonal",
      np.allclose(thr, thr.T) and np.allclose(np.diag(thr), 0), "")
# The caveat of any circular-shift null: a shifted periodic signal is still the
# same periodic signal, so a pure sine shared by two cells (here 3 cycles of
# 0.05 Hz) correlates about as well after shifting and is *not* significant.
check("a shared purely periodic drive is not significant under shifting",
      thr[0, 1] == 0, f"{raw[0, 1]:.3f} -> {thr[0, 1]:.3f}")

# A shared *aperiodic* drive — sparse calcium-like events — is what the test
# is for, and it has to survive.
ev_rng = np.random.default_rng(11)
events = np.convolve((ev_rng.random(N_FRAMES) < 0.01).astype(float),
                     np.exp(-np.arange(60) / 20.0))[:N_FRAMES]
ev = np.column_stack([events + ev_rng.normal(0, 0.3, N_FRAMES),
                      events + ev_rng.normal(0, 0.3, N_FRAMES),
                      ev_rng.normal(0, 0.3, N_FRAMES)])
ev_thr = threshold_correlation(_bin_columns(ev, 5), 0.05, 200,
                               np.random.default_rng(2))
check("a shared aperiodic drive survives thresholding",
      ev_thr[0, 1] > 0.3, f"{ev_thr[0, 1]:.3f}")

# Calibration: among independent cells the test should pass about ``tail`` of
# the edges — no more (it would be too lenient), no fewer (the null would be
# wrong). A single pair is a coin flip at 5%, so count over many.
noise = np.random.default_rng(13).normal(size=(600, 40))
kept = threshold_correlation(noise, 0.05, 200, np.random.default_rng(14))
iu = np.triu_indices(40, 1)
rate = float(np.mean(kept[iu] > 0))
check("independent cells keep about `tail` of their edges",
      0.02 <= rate <= 0.08, f"{rate:.3f} of {len(iu[0])} pairs")
check("every negative correlation is removed (one-sided test)",
      not (thr < 0).any() and (raw < 0).any(), "")

# The counting shortcut must agree with the sort-and-pick cutoff adjm_thr uses.
rng_a, rng_b = np.random.default_rng(5), np.random.default_rng(5)
R, tail = 40, 0.1
fast_thr = threshold_correlation(binned, tail, R, rng_a)
n_bins, n_units = binned.shape
z = (binned - binned.mean(0)) / binned.std(0)
surr = np.empty((n_units, n_units, R))
for r in range(R):
    k = rng_b.integers(1, n_bins, size=n_units)
    shifted = np.column_stack([np.roll(z[:, u], k[u]) for u in range(n_units)])
    surr[:, :, r] = np.corrcoef(shifted, rowvar=False)
import math  # noqa: E402
cut = np.sort(surr, axis=2)[:, :, math.ceil((1 - tail) * R) - 1]
slow_thr = raw.copy()
slow_thr[cut > raw] = 0
np.fill_diagonal(slow_thr, 0)
check("the count-based cutoff equals sorting the surrogates",
      np.allclose(fast_thr, slow_thr), "")

res_thr = suite2p_to_adjm(peaks_data, "spks", [1000], corr_prob_threshold=True,
                          prob_thresh_rep_num=50, rng=np.random.default_rng(3))
res_raw = suite2p_to_adjm(peaks_data, "spks", [1000])
check("suite2p_to_adjm thresholds when asked, and not otherwise",
      np.allclose(res_raw.adjMs["adjM1000mslag"],
                  _corr_columns(_bin_columns(peaks_data.spks.T, 33)))
      and (res_thr.adjMs["adjM1000mslag"] == 0).sum()
      > (res_raw.adjMs["adjM1000mslag"] == 0).sum(), "")
same_seed = suite2p_to_adjm(peaks_data, "spks", [1000], corr_prob_threshold=True,
                            prob_thresh_rep_num=50, rng=np.random.default_rng(3))
check("a seeded run reproduces",
      np.array_equal(res_thr.adjMs["adjM1000mslag"],
                     same_seed.adjMs["adjM1000mslag"]), "")

# Near-identical cells put real and surrogate correlations within rounding of
# each other, where comparing the two halves separately used to split an edge
# — an asymmetric matrix that crashed null_model_und_sign in step 4.
tie_rng = np.random.default_rng(21)
base = tie_rng.normal(size=(300, 1))
ties = np.hstack([base + tie_rng.normal(0, 1e-3, (300, 1)) for _ in range(8)]
                 + [tie_rng.normal(size=(300, 6))])
check("near-tied edges are kept or dropped on both sides together",
      all(np.array_equal(t, t.T) for t in (
          (threshold_correlation(ties, 0.05, 30, np.random.default_rng(s)) != 0)
          for s in range(20))), "")

const = binned.copy()
const[:, 5] = 2.0
with np.errstate(invalid="ignore", divide="ignore"):
    c_thr = threshold_correlation(const, 0.05, 20, np.random.default_rng(0))
    c_raw = _corr_columns(const)
check("a constant cell's NaN edges stay NaN rather than turning into 0",
      np.isnan(c_thr[5, :4]).all() and np.array_equal(np.isnan(c_thr), np.isnan(c_raw)),
      str(c_thr[5]))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All correlation-bin checks passed.")
