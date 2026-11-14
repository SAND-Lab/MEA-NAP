"""The interval-jitter null for edge thresholding (``Params.prob_thresh_null``).

Run: ``uv run python test_jitter_null.py`` (from ``python/``; ~20 s).

What it has to show:
- the jitter keeps every train's count in every window, and moves nothing
  out of its window or out of the recording;
- the circular null is untouched (same seed, same edges as before);
- on planted data, channels that share only slow bursts are connected under
  the circular null and not under the jitter null, while channels with real
  fine-timescale synchrony are connected under both. Bursts whose onsets are
  shared to the sample *are* fine timing, and the jitter null says so;
- a run's settings carry the choice, and the Connectivity tab writes it.
"""

from __future__ import annotations

import os
import sys

import numpy as np

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def jitter_checks() -> None:
    from meanap.pipeline.probabilistic_threshold import interval_jitter_spikes

    print("The jitter")
    rng = np.random.default_rng(0)
    duration, window = 60.0, 0.05
    trains = {0: np.sort(rng.random(3000) * duration),
              1: np.sort(rng.random(40) * duration),
              2: np.array([])}
    moved = interval_jitter_spikes(trains, 3, window, duration, np.random.default_rng(1))
    edges = np.arange(0, duration + window, window)
    check("every train keeps its count in every window",
          all(np.array_equal(np.histogram(trains[c], edges)[0], np.histogram(moved[c], edges)[0])
              for c in range(3)))
    check("no spike leaves its own window",
          np.array_equal(np.floor(np.sort(trains[0]) / window),
                         np.floor(moved[0] / window)))
    check("and none leaves the recording, the last part-window included",
          moved[0].min() >= 0 and moved[0].max() < duration
          and interval_jitter_spikes({0: np.array([59.99])}, 1, 0.05, 59.995,
                                     np.random.default_rng(2))[0][0] < 59.995)
    check("spikes do move, and come back sorted",
          not np.allclose(moved[0], trains[0]) and np.all(np.diff(moved[0]) >= 0))
    again = interval_jitter_spikes(trains, 3, window, duration, np.random.default_rng(1))
    check("the same seed gives the same surrogate",
          all(np.array_equal(again[c], moved[c]) for c in range(3)))
    try:
        interval_jitter_spikes(trains, 3, 0.0, duration, rng)
        check("a zero window is refused", False)
    except ValueError:
        check("a zero window is refused", True)


def planted(seed: int = 0, duration: float = 300.0, *, sharp: bool = False):
    """Channels 0-9 share only slow bursts; 10-15 are three pairs firing 2 ms
    apart; 16-25 are independent.

    The bursts are smooth (spike times spread with an SD of 300 ms round
    each burst centre) unless *sharp*, when each burst is a 300 ms block
    with a hard start and end that every channel shares to the sample.
    """
    rng = np.random.default_rng(seed)
    centres = np.sort(rng.random(int(duration / 4)) * duration)   # one per ~4 s

    def bursty():
        background = rng.random(int(0.5 * duration)) * duration
        counts = rng.poisson(6, len(centres))
        if sharp:
            within = np.concatenate([c + rng.random(k) * 0.3 for c, k in zip(centres, counts)])
        else:
            within = np.concatenate([c + rng.normal(0, 0.3, k) for c, k in zip(centres, counts)])
        within = within[(within > 0) & (within < duration)]
        return np.sort(np.concatenate([background, within]))

    trains = {ch: bursty() for ch in range(10)}
    for ch in (10, 12, 14):
        driver = np.sort(rng.random(int(2 * duration)) * duration)
        follower = driver + 0.002 + rng.normal(0, 0.0005, len(driver))
        trains[ch] = driver
        trains[ch + 1] = np.sort(follower[(follower > 0) & (follower < duration)])
    for ch in range(16, 26):
        trains[ch] = np.sort(rng.random(int(2 * duration)) * duration)
    return trains, duration


def _pass_rate(adj, channels):
    sub = adj[np.ix_(channels, channels)]
    iu = np.triu_indices(len(channels), 1)
    return float((sub[iu] > 0).mean())


def null_checks() -> None:
    from meanap.pipeline.probabilistic_threshold import adjm_thr

    print("What each null calls an edge")
    trains, duration = planted()
    n, fs, reps = 26, 10_000.0, 100
    bursty, independent = list(range(10)), list(range(16, 26))
    _, before = adjm_thr(trains, n, 10, 0.05, fs, duration, reps,
                         rng=np.random.default_rng(7))
    _, circular = adjm_thr(trains, n, 10, 0.05, fs, duration, reps,
                           rng=np.random.default_rng(7), null="circular")
    check("the circular null is unchanged by the option (same seed, same edges)",
          np.array_equal(before, circular))
    _, jitter = adjm_thr(trains, n, 10, 0.05, fs, duration, reps,
                         rng=np.random.default_rng(7), null="jitter", jitter_ms=50)
    shared_c, shared_j = _pass_rate(circular, bursty), _pass_rate(jitter, bursty)
    check("shared slow bursts alone: nearly every pair an edge under the circular null",
          shared_c >= 0.8, f"{shared_c:.2f}")
    check("but about the tail's worth under the jitter null",
          shared_j <= 0.15, f"{shared_j:.2f}")
    check("fine-timescale synchrony: an edge under both",
          all(circular[c, c + 1] > 0 and jitter[c, c + 1] > 0 for c in (10, 12, 14)))
    free_c, free_j = _pass_rate(circular, independent), _pass_rate(jitter, independent)
    check("independent channels: about the tail's worth under either",
          free_c <= 0.15 and free_j <= 0.15, f"{free_c:.2f} {free_j:.2f}")

    sharp, _ = planted(sharp=True)
    _, sharp_j = adjm_thr(sharp, n, 10, 0.05, fs, duration, reps,
                          rng=np.random.default_rng(7), null="jitter", jitter_ms=50)
    # A hard burst edge shared to the sample is timing finer than the window,
    # so some of it leaks through: well above the tail, though not every pair.
    check("bursts whose onsets are shared to the sample partly pass as fine timing",
          _pass_rate(sharp_j, bursty) >= 0.2, f"{_pass_rate(sharp_j, bursty):.2f}")
    try:
        adjm_thr(trains, n, 10, 0.05, fs, duration, 5, null="shuffle")
        check("an unknown null is refused by name", False)
    except ValueError as err:
        check("an unknown null is refused by name", "shuffle" in str(err))


def settings_checks() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from meanap.gui.panels.connectivity import ConnectivityPanel
    from meanap.params import Params

    print("Settings")
    defaults = Params()
    check("circular stays the default, with a 5 x lag window ready",
          defaults.prob_thresh_null == "circular" and defaults.prob_thresh_jitter_lags == 5.0)
    app = QApplication.instance() or QApplication([])
    panel = ConnectivityPanel()
    check("the window is greyed out until jitter is chosen",
          not panel.prob_thresh_jitter_lags.isEnabled())
    params = Params(prob_thresh_null="jitter", prob_thresh_jitter_lags=10.0)
    panel.load(params)
    check("a jitter run's settings load, and wake the window",
          panel.prob_thresh_null.currentData() == "jitter"
          and panel.prob_thresh_jitter_lags.value() == 10.0
          and panel.prob_thresh_jitter_lags.isEnabled())
    out = Params()
    panel.save(out)
    check("and are written back", out.prob_thresh_null == "jitter"
          and out.prob_thresh_jitter_lags == 10.0)
    panel.set_timescale("bin")
    check("correlation measures (always circular) grey the choice out",
          not panel.prob_thresh_null.isEnabled()
          and not panel.prob_thresh_jitter_lags.isEnabled())
    del app


def main() -> int:
    jitter_checks()
    null_checks()
    settings_checks()
    print(f"\nFAILURES: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
