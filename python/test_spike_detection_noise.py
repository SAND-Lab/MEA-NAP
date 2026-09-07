"""The noise statistics detection shares between its methods.

Every method run on one channel needs the same two numbers — the robust sigma
and the median of the filtered trace — and each is a full partition of a
multi-million-sample array. They are now measured once per channel and handed
to each method, which is most of why detection got faster.

That is only sound while the shared numbers are *the same numbers* each method
would have computed for itself. Nothing about the code makes that obvious, and
getting it wrong would not crash: it would shift every threshold slightly and
quietly change which events are spikes. So it is asserted here, on real traces
rather than on constructed ones, because the property is about arithmetic on
noisy data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.pipeline.io import load_raw_recording  # noqa: E402
from meanap.pipeline.spike_detection import (  # noqa: E402
    SpikeDetectionParams, _determine_scales, align_peaks, bandpass_filter,
    detect_spikes_recording, detect_spikes_threshold, peak_noise, trace_noise,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def traces() -> tuple[np.ndarray, np.ndarray, float]:
    """A few real filtered channels, or synthetic ones if the example is absent."""
    example = Path("ExampleData/NGN2_20230208_P1_DIV14_A2.mat")
    if example.exists():
        dat, channels, fs = load_raw_recording(example)
        return dat[:, :3].astype(np.float64), channels[:3], float(fs)
    rng = np.random.default_rng(11)
    fs = 12500.0
    dat = rng.normal(0, 1.0, size=(int(fs * 8), 3))
    spike = -9.0 * np.exp(-((np.arange(-20, 21)) ** 2) / 18.0)
    for ch in range(3):
        for at in rng.integers(100, dat.shape[0] - 100, 400):
            dat[at - 20:at + 21, ch] += spike
    return dat, np.arange(1, 4), fs


dat, channels, fs = traces()
print(f"\n{dat.shape[1]} channels, {dat.shape[0] / fs:.0f} s at {fs:.0f} Hz")


print("\nThe shared numbers are the numbers each method would have computed")

for ch in range(dat.shape[1]):
    filtered = bandpass_filter(dat[:, ch], fs, 600.0, 8000.0)
    sigma, median = trace_noise(filtered)

    # Over the whole recording the peak bound's centre is the window's mean,
    # which is the same mean — so detection reuses one sigma for both. If that
    # ever stops holding, the peak bounds move without anything saying so.
    check(f"ch{ch}: the peak sigma is the trace sigma over a full window",
          peak_noise(filtered) == sigma,
          f"{peak_noise(filtered)!r} vs {sigma!r}")

    # Only the multiplier differs between thresholds, so a precomputed pair
    # must give each of them exactly the threshold it computed for itself.
    for multiplier in (3.0, 4.5, 5.0):
        own_frames, own_thr = detect_spikes_threshold(
            filtered, multiplier, 1.0, fs)
        shared_frames, shared_thr = detect_spikes_threshold(
            filtered, multiplier, 1.0, fs, noise=(sigma, median))
        check(f"ch{ch}: threshold at {multiplier} MAD is unchanged",
              own_thr == shared_thr, f"{own_thr!r} vs {shared_thr!r}")
        check(f"ch{ch}: the same spikes at {multiplier} MAD",
              np.array_equal(own_frames, shared_frames),
              f"{own_frames.size} vs {shared_frames.size}")

    frames, _ = detect_spikes_threshold(filtered, 4.0, 1.0, fs,
                                        noise=(sigma, median))
    own_aligned, own_waves = align_peaks(frames, filtered, remove_artifacts=True)
    shared_aligned, shared_waves = align_peaks(frames, filtered,
                                               remove_artifacts=True,
                                               noise_sigma=sigma)
    check(f"ch{ch}: aligned peaks are unchanged",
          np.array_equal(own_aligned, shared_aligned))
    check(f"ch{ch}: waveforms are unchanged",
          np.array_equal(own_waves, shared_waves))


print("\nPeak alignment at the recording's edges")

# Alignment gathers the spikes whose search window lies wholly inside the
# recording as one block and does the rest singly. The edges are where those
# two paths could disagree, and real recordings rarely put a spike in the first
# ten samples — so they are constructed here.
rng = np.random.default_rng(5)
short = rng.normal(size=400)
edges = np.array([0, 1, 2, 9, 10, 24, 25, 26, 200, 373, 374, 390, 398, 399])
aligned, waves = align_peaks(edges, short)
check("every spike survives with no artifact rejection",
      aligned.size == edges.size, f"{aligned.size} of {edges.size}")
check("waveforms are all the same width whatever the edge did",
      waves.shape == (edges.size, 51), str(waves.shape))
check("an aligned frame is never outside the recording",
      bool(((aligned >= 0) & (aligned < short.size)).all()), str(aligned))
check("each is the lowest sample within the search window",
      all(short[f] == short[max(0, s - 10):min(short.size, s + 11)].min()
          for s, f in zip(edges, aligned)), str(aligned))
check("a spike at sample 0 is padded on its left, not wrapped",
      bool((waves[0, :25 - aligned[0]] == 0).all()), str(waves[0, :6]))
check("no spikes gives an empty result of the right shape",
      align_peaks(np.array([], dtype=int), short)[1].shape == (0, 51))


print("\nThe cached scale table")

first = _determine_scales("bior1.5", (0.4, 0.8), fs, 5)
first[0] = 999
again = _determine_scales("bior1.5", (0.4, 0.8), fs, 5)
check("a caller writing to the scales it got does not poison the next one",
      again[0] != 999, str(again))
check("different widths get a different table",
      not np.array_equal(_determine_scales("bior1.5", (0.2, 0.4), fs, 5), again),
      str(_determine_scales("bior1.5", (0.2, 0.4), fs, 5)))


print("\nA whole channel, both ways")

params = SpikeDetectionParams(fs=fs, thresholds=[3.0, 4.0, 5.0], wname_list=[])
one = detect_spikes_recording(dat[:, :1], channels[:1], fs, params, max_workers=1)
many = detect_spikes_recording(dat[:, :1], channels[:1], fs, params, max_workers=4)
check("threading a channel does not change what it finds",
      all(np.array_equal(one.spike_times[0][m], many.spike_times[0][m])
          for m in one.spike_times[0]),
      str({m: (one.spike_times[0][m].size, many.spike_times[0][m].size)
           for m in one.spike_times[0]}))

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) failed:")
    for failure in FAILURES:
        print(f"  - {failure}")
    sys.exit(1)
print("All checks passed.")
