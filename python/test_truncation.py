"""Recording truncation: keep the first or the last ``trunc_length`` seconds.

Run from the repo root::

    uv run python python/test_truncation.py

``Params.trunc_rec`` / ``trunc_length`` were carried over from MATLAB and shown
on the Data tab, but no Python step ever read them — every run analysed the
whole recording whatever the checkbox said. This checks that they now apply,
on both paths:

- MEA: ``truncate_spike_times`` cuts one recording's spike times, and returns
  the duration they now span (every firing rate is spikes / that duration).
- CAT-NAP: ``truncate_suite2p`` cuts the suite2p traces and the peak arrays
  denoising produced.

and that ``trunc_keep = "last"`` keeps the end of the recording, re-timed to
start at 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap.loader import Suite2pData, truncate_suite2p  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline.io import truncate_spike_times  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


# ── MEA spike times ───────────────────────────────────────────────────────────

print("MEA spike times")

spikes = {0: np.array([1.0, 50.0, 119.0, 150.0, 290.0]), 1: np.array([])}
duration = 300.0

out, dur = truncate_spike_times(spikes, duration, Params(trunc_rec=False))
check("off leaves the recording whole",
      out is spikes and dur == duration)

out, dur = truncate_spike_times(
    spikes, duration, Params(trunc_rec=True, trunc_length=120.0))
check("first keeps [0, 120]",
      np.array_equal(out[0], [1.0, 50.0, 119.0]) and dur == 120.0,
      f"{out[0]} {dur}")
check("first is the default", Params().trunc_keep == "first")

out, dur = truncate_spike_times(
    spikes, duration,
    Params(trunc_rec=True, trunc_length=120.0, trunc_keep="last"))
check("last keeps [180, 300], re-timed to [0, 120]",
      np.array_equal(out[0], [290.0 - 180.0]), f"{out[0]}")
check("last spans trunc_length", dur == 120.0, f"{dur}")
check("empty channels stay empty", out[1].size == 0)

out, dur = truncate_spike_times(
    spikes, duration,
    Params(trunc_rec=True, trunc_length=400.0, trunc_keep="last"))
check("a recording shorter than the window is kept whole",
      out is spikes and dur == duration)


# ── CAT-NAP suite2p traces ────────────────────────────────────────────────────

print("\nCAT-NAP suite2p traces")

fs, n_frames, n_rois = 10.0, 1000, 3                 # 100 s recording
F = np.tile(np.arange(n_frames, dtype=float), (n_rois, 1))
nan = np.nan
starts = np.array([[5, 250, 900], [950, nan, nan], [nan, nan, nan]])
data = Suite2pData(
    F=F, spks=F * 2, iscell=np.ones((n_rois, 2)), xy_loc=np.zeros((2, n_rois)),
    fs=fs, n_frames=n_frames, duration_s=n_frames / fs,
    F_denoised=F * 3,
    peak_start_frames=starts, peak_end_frames=starts + 4,
    peak_heights=starts / 100, event_areas=starts / 10,
    time_points=np.arange(n_frames) / fs,
)

first = truncate_suite2p(data, Params(trunc_rec=True, trunc_length=30.0))
check("first keeps 300 frames", first.F.shape == (3, 300) and first.n_frames == 300)
check("first keeps the start of every trace",
      first.F[0, 0] == 0 and first.spks[0, -1] == 2 * 299
      and first.F_denoised[0, -1] == 3 * 299)
check("first duration is 30 s", first.duration_s == 30.0)
check("first keeps the peaks that start inside it",
      np.array_equal(first.peak_start_frames[0, :2], [5, 250])
      and np.isnan(first.peak_start_frames[1:]).all(),
      f"{first.peak_start_frames}")
check("the original data is left alone", data.F.shape == (3, 1000))

last = truncate_suite2p(
    data, Params(trunc_rec=True, trunc_length=30.0, trunc_keep="last"))
check("last keeps the final 300 frames",
      last.F.shape == (3, 300) and last.F[0, 0] == 700 and last.F[0, -1] == 999)
check("last re-indexes peaks from the window start",
      last.peak_start_frames[0, 0] == 200 and last.peak_start_frames[1, 0] == 250
      and last.peak_end_frames[0, 0] == 204,
      f"{last.peak_start_frames}")
check("peak sizes travel with their peaks",
      last.peak_heights[0, 0] == 9.0 and last.event_areas[1, 0] == 95.0)
check("peak arrays are packed to the most kept per ROI",
      last.peak_start_frames.shape == (3, 1))
check("time points restart at 0",
      last.time_points[0] == 0 and np.isclose(last.time_points[-1], 29.9))

whole = truncate_suite2p(data, Params(trunc_rec=True, trunc_length=500.0))
check("a recording shorter than the window is kept whole", whole is data)


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All truncation checks passed.")
