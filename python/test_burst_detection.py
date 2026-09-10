"""Network burst detection on a densely firing array.

Run from the repo root::

    uv run python python/test_burst_detection.py

Both things checked here were found on ``HCNT26_DIV58_E2``, a 16-channel
recording firing at ~460 Hz array-wide, on which burst detection reported *no
bursts at all* even though its raster has obvious network events.

1. ``get_isin_threshold`` picks the burst threshold as the valley between the
   burst mode and the background mode of the ISI\\ :sub:`N` distribution. It
   used to bin ISI\\ :sub:`N` in *milliseconds* against Bakkum's log-spaced
   edges ``10 ** (-5:0.05:1.5)``, which are in *seconds* (``getISInTh.m``
   documents ``'Steps' [sec]`` and plots ``Steps * 1000`` under an "ms" axis
   label). That capped the histogram at 31.6 ms. Any array whose baseline
   ISI\\ :sub:`N` is above that — which is what a high firing rate means — had
   its background mode fall off the top, leaving one peak, so the "<= 1 peak"
   fallback decided the threshold instead of the valley. On a dense recording
   that fallback returns **0.0**, and a threshold of zero finds no bursts.

   The synthetic recordings below are built to sit in exactly that regime:
   dense Poisson background plus planted events, with enough of the
   ISI\\ :sub:`N` distribution above 31.6 ms that the background mode is lost.
   The pre-fix function is kept in this file and run on the same input, so the
   test shows the old code returning 0.0 rather than asserting a proxy for it.

2. ``merge_close_bursts`` rejoins the fragments ISI\\ :sub:`N` detection splits
   one event into. On a dense array the background firing keeps
   ISI\\ :sub:`N` hovering around the threshold, so it crosses back and forth
   several times inside a single event: a 400 ms event on HCNT26 came out as
   21 bursts a few milliseconds apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scipy.signal import find_peaks, savgol_filter  # noqa: E402

from meanap.pipeline.burst_detection import (  # noqa: E402
    burst_detect_network, get_isin_threshold, merge_close_bursts,
)


def get_isin_threshold_before_fix(spike_times: np.ndarray, n: int = 10) -> float:
    """``get_isin_threshold`` as it was, so the regression stays pinned.

    Identical to the current function except that it bins ISI_N in
    milliseconds against the second-valued edges — the bug. Kept here rather
    than described in a comment so the test can show the old code failing on
    the same input the new code handles, instead of asserting a proxy for it.
    """
    if len(spike_times) <= n:
        return 0.1
    isin = spike_times[n - 1:] - spike_times[:-(n - 1)]
    if len(isin) == 0:
        return 0.1
    steps = 10 ** np.arange(-5, 1.55, 0.05)
    counts, _ = np.histogram(isin * 1000.0, bins=steps)   # <- ms against s
    if counts.sum() == 0:
        return 0.1
    curve = counts / counts.sum()
    window = 9 if len(curve) >= 9 else (len(curve) | 1)
    if window > 3:
        curve = savgol_filter(curve, window, 1)
    peaks, _ = find_peaks(curve, distance=2)
    if len(peaks) <= 1:
        return 0.0 if np.max(np.diff(spike_times)) < 0.1 else 0.1
    valley = peaks[0] + np.argmin(curve[peaks[0]:peaks[1] + 1])
    return min(steps[valley] / 1000.0, 0.1)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def dense_array_with_events(
    n_channels: int = 16,
    duration_s: float = 120.0,
    background_hz: float = 25.0,
    n_events: int = 60,
    event_span_s: float = 0.004,
    event_spikes: int = 60,
    seed: int = 0,
) -> tuple[dict[int, np.ndarray], np.ndarray]:
    """A recording in the regime that broke: dense background, tight events.

    ``background_hz`` per channel over ``n_channels`` gives a ~400 Hz array, so
    the pooled background ISI\\ :sub:`10` sits around 20 ms with a long tail
    past the old 31.6 ms cap — the background mode's upper half falls off the
    histogram, which is exactly what happens on HCNT26_DIV58_E2. Each planted
    event puts ``event_spikes`` spikes into ``event_span_s``, an
    ISI\\ :sub:`10` of well under a millisecond, so the burst mode is
    unambiguous.

    Returns the per-channel spike times and the planted event start times.
    """
    rng = np.random.default_rng(seed)

    spikes: dict[int, list[np.ndarray]] = {ch: [] for ch in range(n_channels)}
    for ch in range(n_channels):
        n = rng.poisson(background_hz * duration_s)
        spikes[ch].append(np.sort(rng.uniform(0, duration_s, n)))

    # Kept clear of the ends and of each other so no two events can merge.
    event_starts = np.linspace(2.0, duration_s - 2.0, n_events)
    for t0 in event_starts:
        for _ in range(event_spikes):
            ch = int(rng.integers(n_channels))
            spikes[ch].append(np.array([t0 + rng.uniform(0, event_span_s)]))

    times = {ch: np.sort(np.concatenate(parts)) for ch, parts in spikes.items()}
    return times, event_starts


def dense_array_with_decaying_events(
    n_channels: int = 16,
    duration_s: float = 120.0,
    background_hz: float = 25.0,
    n_events: int = 20,
    event_span_s: float = 0.400,
    peak_hz: float = 20000.0,
    tau_s: float = 0.100,
    seed: int = 1,
) -> tuple[dict[int, np.ndarray], np.ndarray]:
    """The same array, but with events that decay the way real ones do.

    A flat, very dense event never fragments — ISI_N stays far below threshold
    from start to finish. Fragmentation happens where the *within-event* rate
    passes through the threshold, which on a real burst is its decaying tail:
    ISI_N crosses back and forth on Poisson fluctuation alone, and the detector
    ends the burst and starts another each time. So the events here are
    inhomogeneous Poisson with an exponentially decaying rate, which is what
    HCNT26_DIV58_E2's events look like — 8700 Hz at onset falling to ~1600 Hz
    over ~400 ms.
    """
    rng = np.random.default_rng(seed)

    spikes: dict[int, list[np.ndarray]] = {ch: [] for ch in range(n_channels)}
    for ch in range(n_channels):
        n = rng.poisson(background_hz * duration_s)
        spikes[ch].append(np.sort(rng.uniform(0, duration_s, n)))

    event_starts = np.linspace(2.0, duration_s - 2.0, n_events)
    for t0 in event_starts:
        # Thinning: draw from the peak rate, keep each with probability
        # rate(t) / peak_hz.
        n_candidates = rng.poisson(peak_hz * event_span_s)
        offsets = rng.uniform(0, event_span_s, n_candidates)
        keep = rng.random(n_candidates) < np.exp(-offsets / tau_s)
        offsets = offsets[keep]
        chans = rng.integers(n_channels, size=len(offsets))
        for ch in range(n_channels):
            mine = offsets[chans == ch]
            if len(mine):
                spikes[ch].append(t0 + mine)

    times = {ch: np.sort(np.concatenate(parts)) for ch, parts in spikes.items()}
    return times, event_starts


print("[1] the ISIn threshold on a densely firing array")

times, event_starts = dense_array_with_events()
pooled = np.sort(np.concatenate(list(times.values())))
duration_s = 120.0
fs = 12500.0

isin = pooled[9:] - pooled[:-9]
array_hz = len(pooled) / duration_s
print(f"  ({len(pooled)} spikes, {array_hz:.0f} Hz array-wide, "
      f"background ISI_10 median {np.median(isin) * 1000:.1f} ms)")

# The regime has to be the one that broke, or the test proves nothing. Two
# things put a recording there: enough of the ISI_10 distribution above the old
# 31.6 ms cap that the background mode is lost, and an array that never falls
# silent for 100 ms — which is what sent the old fallback to 0 rather than 0.1.
check("enough of the ISI_10 distribution sits above the old 31.6 ms cap",
      float(np.mean(isin > 0.0316)) > 0.1,
      f"only {100 * np.mean(isin > 0.0316):.1f}% above 31.6 ms")
check("and the array never goes quiet for 100 ms, as on a real dense recording",
      float(np.max(np.diff(pooled))) < 0.1,
      f"max ITI = {np.max(np.diff(pooled)) * 1000:.1f} ms")

# The bug itself: on this input the old code returns a threshold of zero, and
# a threshold of zero means no bursts however obvious the events are.
check("the pre-fix code returns the 0.0 'no bursts' threshold here",
      get_isin_threshold_before_fix(pooled, n=10) == 0.0,
      f"got {get_isin_threshold_before_fix(pooled, n=10)}")

threshold = get_isin_threshold(pooled, n=10)
check("a threshold is found rather than the 0.0 'no bursts' fallback",
      threshold > 0.0, f"threshold = {threshold}")
check("and it separates the events from the background",
      0.0 < threshold < float(np.median(isin)),
      f"threshold {threshold * 1000:.2f} ms vs background "
      f"{np.median(isin) * 1000:.1f} ms")

# The planted events are the only real bursts, so detection should find about
# as many as were planted and put them where they were planted.
_, burst_times, _, info = burst_detect_network(
    times, fs, min_spikes=10, min_channels=3, isin_th_param="automatic")
starts = burst_times[:, 0] / fs
ends = burst_times[:, 1] / fs
print(f"  ({len(starts)} bursts at ISIn = {info['isin_th'] * 1000:.2f} ms, "
      f"{len(event_starts)} events planted)")

check("bursts are detected at all", len(starts) > 0, f"{len(starts)} bursts")

# Every planted event should be covered by some detected burst.
covered = sum(
    bool(np.any((starts <= t0 + 0.01) & (ends >= t0)))
    for t0 in event_starts
)
check("every planted event is covered by a detected burst",
      covered == len(event_starts), f"{covered}/{len(event_starts)}")

# And no more bursts than events: the Poisson background must not produce any.
check("the Poisson background produces no spurious bursts",
      len(starts) <= len(event_starts),
      f"{len(starts)} bursts vs {len(event_starts)} events")


print("\n[2] merge_close_bursts")

# Ordinary case: a run of fragments a few ms apart becomes one burst.
frag_start = np.array([1.000, 1.006, 1.013, 1.021, 5.000, 5.004])
frag_end = np.array([1.004, 1.011, 1.019, 1.030, 5.002, 5.009])
got_s, got_e = merge_close_bursts(frag_start, frag_end, 0.020)
check("fragments within the gap become one burst",
      len(got_s) == 2, f"{len(got_s)} bursts")
check("the merged burst spans the whole run",
      np.allclose(got_s, [1.000, 5.000]) and np.allclose(got_e, [1.030, 5.009]),
      f"{got_s} -> {got_e}")

# gap = 0 must be exactly the old behaviour, so an existing run is unchanged.
got_s, got_e = merge_close_bursts(frag_start, frag_end, 0.0)
check("a gap of 0 leaves the bursts untouched",
      np.array_equal(got_s, frag_start) and np.array_equal(got_e, frag_end),
      f"{got_s} -> {got_e}")

# A short burst wholly inside a longer one must not truncate it.
got_s, got_e = merge_close_bursts(
    np.array([1.0, 1.1]), np.array([2.0, 1.2]), 0.020)
check("a burst nested inside another does not shorten it",
      len(got_s) == 1 and np.isclose(got_e[0], 2.0), f"{got_s} -> {got_e}")

# Unsorted input must still merge correctly.
got_s, got_e = merge_close_bursts(
    np.array([5.000, 1.000, 1.006]), np.array([5.002, 1.004, 1.011]), 0.020)
check("unsorted input merges on time order, not array order",
      len(got_s) == 2 and np.allclose(got_s, [1.000, 5.000]),
      f"{got_s} -> {got_e}")

# Degenerate inputs.
empty = np.array([])
got_s, got_e = merge_close_bursts(empty, empty, 0.020)
check("no bursts merges to no bursts", len(got_s) == 0)
got_s, got_e = merge_close_bursts(np.array([1.0]), np.array([2.0]), 0.020)
check("one burst stays one burst", len(got_s) == 1 and got_e[0] == 2.0)


print("\n[3] merging an event the detector fragments")

# Section 1's events are 4 ms flashes, which come out whole. The case merging
# exists for is a *sustained* event — HCNT26's are ~400 ms — where the array's
# background firing keeps ISI_N crossing the threshold repeatedly inside one
# event, so the detector reports a run of fragments.
sustained, sustained_starts = dense_array_with_decaying_events()

_, bt_raw, _, _ = burst_detect_network(
    sustained, fs, min_spikes=10, min_channels=3,
    isin_th_param="automatic", merge_gap_ms=0.0)
_, bt_merged, _, _ = burst_detect_network(
    sustained, fs, min_spikes=10, min_channels=3,
    isin_th_param="automatic", merge_gap_ms=20.0)
print(f"  {len(bt_raw)} fragments -> {len(bt_merged)} bursts, "
      f"{len(sustained_starts)} events planted")

check("the detector does fragment a sustained event",
      len(bt_raw) > 2 * len(sustained_starts),
      f"{len(bt_raw)} fragments for {len(sustained_starts)} events")
check("merging recovers roughly one burst per event",
      len(sustained_starts) <= len(bt_merged) <= 2 * len(sustained_starts),
      f"{len(bt_merged)} bursts for {len(sustained_starts)} events")

# A merged burst should span most of the event it came from, which is the
# thing burst *duration* was getting wrong.
merged_durs = (bt_merged[:, 1] - bt_merged[:, 0]) / fs
raw_durs = (bt_raw[:, 1] - bt_raw[:, 0]) / fs
print(f"  median duration {np.median(raw_durs) * 1000:.0f} ms -> "
      f"{np.median(merged_durs) * 1000:.0f} ms (events are 400 ms)")
check("merged bursts have event-scale durations, not fragment-scale",
      np.median(merged_durs) > 5 * np.median(raw_durs),
      f"{np.median(merged_durs) * 1000:.1f} ms vs "
      f"{np.median(raw_durs) * 1000:.1f} ms")


print("\n[4] merging only re-segments — it adds no time and no spikes")

# The property that makes merging safe to leave on: it joins bursts already
# found, so the time and the spikes it calls bursting can only grow by the
# gaps it bridged, never by pulling in stretches the detector called quiet.
pooled_all = np.sort(np.concatenate(list(sustained.values())))
for gap_ms in (0.0, 20.0, 100.0):
    _, bt, _, _ = burst_detect_network(
        sustained, fs, min_spikes=10, min_channels=3,
        isin_th_param="automatic", merge_gap_ms=gap_ms)
    s, e = bt[:, 0] / fs, bt[:, 1] / fs
    in_burst = sum(int(np.sum((pooled_all >= a) & (pooled_all <= b)))
                   for a, b in zip(s, e))
    print(f"  gap {gap_ms:5.0f} ms -> {len(s):3d} bursts, "
          f"{(e - s).sum():.3f} s in burst, {in_burst} spikes in burst")
    if gap_ms == 0.0:
        base_time, base_spikes, base_n = (e - s).sum(), in_burst, len(s)
    else:
        check(f"gap {gap_ms:.0f} ms: never more bursts than unmerged",
              len(s) <= base_n, f"{len(s)} > {base_n}")
        check(f"gap {gap_ms:.0f} ms: time in burst grows by at most the gaps",
              base_time <= (e - s).sum() <= base_time + gap_ms / 1000 * base_n,
              f"{(e - s).sum():.4f} vs base {base_time:.4f}")
        check(f"gap {gap_ms:.0f} ms: spikes in burst do not shrink",
              in_burst >= base_spikes, f"{in_burst} < {base_spikes}")


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All burst detection checks passed.")
