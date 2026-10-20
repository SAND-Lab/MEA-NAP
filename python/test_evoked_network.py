"""Stimulus-triggered networks: shared drive vs genuine co-variation.

Three nodes, 60 flashes. Nodes 0 and 1 both respond to every flash but
independently of each other — *shared stimulus drive*. Nodes 2 and 3 respond
together on a random half of the trials — *co-variation beyond the stimulus*.
Node 4 never responds. A circular-shift null calls both pairs connected; the
trial-shuffle null must keep only 2–3, and so must the noise correlations.

    .venv/bin/python -m pytest python/test_evoked_network.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.stim.evoked_network import (  # noqa: E402
    baseline_window, check_windows_fit, concatenate, epoch_network,
    noise_correlations, separated_events, trial_counts, trial_segments,
)

EVENTS = np.arange(1.0, 121.0, 2.0)          # 60 flashes, 2 s apart
WINDOW = (0.0, 0.5)
LAG_MS = 25


def _trains(seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    T = 122.0
    base = [rng.uniform(0, T, rng.poisson(2.0 * T)) for _ in range(5)]
    together = rng.random(len(EVENTS)) < 0.5       # trials on which 2 and 3 fire
    for e, on in zip(EVENTS, together):
        for node in (0, 1):                        # every trial, independently
            base[node] = np.r_[base[node], e + rng.uniform(0.05, 0.25, 6)]
        if on:
            burst = e + rng.uniform(0.05, 0.25, 6)
            base[2] = np.r_[base[2], burst + rng.normal(0, 0.003, 6)]
            base[3] = np.r_[base[3], burst + rng.normal(0, 0.003, 6)]
    return [np.sort(t) for t in base]


def test_segments_and_concatenation_round_trip():
    train = np.array([0.9, 1.1, 1.4, 2.6, 3.05, 3.2])
    segs = trial_segments(train, np.array([1.0, 3.0]), (0.0, 0.5))
    np.testing.assert_allclose(segs[0], [0.1, 0.4])
    np.testing.assert_allclose(segs[1], [0.05, 0.2])
    np.testing.assert_allclose(concatenate(segs, 0.5), [0.1, 0.4, 0.55, 0.7])
    np.testing.assert_allclose(concatenate(segs, 0.5, np.array([1, 0])), [0.05, 0.2, 0.6, 0.9])
    np.testing.assert_array_equal(trial_counts([train], np.array([1.0, 3.0]), (0.0, 0.5)),
                                  [[2], [2]])


def test_windows_must_not_overlap():
    assert baseline_window((0.0, 0.5)) == (-0.5, 0.0)
    check_windows_fit(EVENTS, (0.0, 0.5))
    try:
        check_windows_fit(EVENTS, (0.0, 1.5))
    except ValueError:
        pass
    else:
        raise AssertionError("overlapping windows should be refused")
    # Only the events too close to a neighbour are dropped: 1.0 and 1.6 clash.
    mask = separated_events(np.array([1.0, 1.6, 3.0, 5.0]), (0.0, 0.5))
    assert mask.tolist() == [False, False, True, True]


def test_trial_shuffle_removes_shared_drive_circular_does_not():
    trains = _trains()
    rng = np.random.default_rng(1)
    circ = epoch_network(trains, EVENTS, WINDOW, LAG_MS, null="circular", rep_num=100, rng=rng)
    shuf = epoch_network(trains, EVENTS, WINDOW, LAG_MS, null="trial_shuffle",
                         rep_num=100, rng=rng)
    assert circ.sttc_thr[0, 1] > 0 and circ.sttc_thr[2, 3] > 0
    assert shuf.sttc_thr[0, 1] == 0, "shared stimulus drive passed the trial shuffle"
    assert shuf.sttc_thr[2, 3] > 0, "trial-by-trial co-variation was lost"
    # The shift predictor explains most of 0–1's STTC and little of 2–3's.
    assert shuf.null_mean[0, 1] > 0.5 * shuf.sttc[0, 1]
    assert shuf.null_mean[2, 3] < 0.5 * shuf.sttc[2, 3]


def test_false_positive_rate_is_nominal():
    """Node 4 never responds: its edges are false positives, which a 5 % test
    should produce about 5 % of the time (measured 5.8 % over 800; here 160)."""
    hits = [epoch_network(_trains(seed), EVENTS, WINDOW, LAG_MS, rep_num=100,
                          rng=np.random.default_rng(seed + 100)).sttc_thr[4, :4] > 0
            for seed in range(40)]
    assert np.mean(hits) <= 0.10, np.mean(hits)


def test_baseline_epoch_has_no_driven_edges():
    shuf = epoch_network(_trains(), EVENTS, baseline_window(WINDOW), LAG_MS,
                         epoch="baseline", rep_num=100, rng=np.random.default_rng(2))
    assert np.count_nonzero(np.triu(shuf.sttc_thr, 1)) <= 1


def test_noise_correlations_find_only_covariation():
    nc = noise_correlations(_trains(), EVENTS, (0.0, 0.3), rep_num=300,
                            rng=np.random.default_rng(3))
    assert nc.r[2, 3] > 0.7 and nc.p[2, 3] < 0.01
    assert abs(nc.r[0, 1]) < 0.35 and nc.p[0, 1] > 0.01
    assert np.isnan(nc.r[0, 0])


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
