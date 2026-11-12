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
import pytest

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


# ── STTC within each trial, averaged (stim/trial_sttc.py) ─────────────────────

def _slow_state_trains(seed, n=16, timed=False, locked=False):
    """Every node's rate swings 4-40 Hz together on a 75 s cycle: shared slow
    state with no timing between nodes. *timed*: nodes 0-3 also share spikes
    to within 2 ms. *locked*: every node answers each event at ~5 ms on its own."""
    r = np.random.default_rng(seed)
    T, ev = 302.0, np.arange(1.0, 301.0, 5.0)
    trains = []
    for _ in range(n):
        c = r.uniform(0, T, r.poisson(45 * T))
        keep = r.uniform(0, 45, c.size) < 22 + 18 * np.sin(2 * np.pi * c / 75.0)
        trains.append(list(c[keep]))
    for e in ev:
        if timed:
            for t0 in e + r.uniform(0.002, 0.05, r.poisson(2)):
                for i in range(4):
                    trains[i].append(t0 + r.normal(0, 0.002))
        if locked:
            for i in range(n):
                if r.random() < 0.8:
                    trains[i] += list(e + 0.005 + r.normal(0, 0.0015, r.integers(1, 4)))
    return [np.sort(np.array(t)) for t in trains], ev


def test_trial_mean_matches_sttc_pair_per_trial():
    from meanap.pipeline.sttc import sttc_pair
    from meanap.stim.evoked_network import trial_segments
    from meanap.stim.trial_sttc import trial_mean_sttc

    trains, ev = _slow_state_trains(0, n=3)
    w = (0.002, 0.05)
    segs = [trial_segments(t, ev, w) for t in trains]
    obs, _, _, _ = trial_mean_sttc(segs, w[1] - w[0], 10, 5, np.random.default_rng(0),
                                   min_valid=1)
    ref = np.nanmean([sttc_pair(segs[0][k], segs[1][k], 0.01, 0, w[1] - w[0])
                      for k in range(len(ev))])
    assert obs[0, 1] == pytest.approx(ref) and obs[1, 0] == pytest.approx(ref)


def test_trial_mean_ignores_slow_state_and_finds_timing():
    """Joined windows count shared slow state as edges; trial means do not,
    and still find precisely timed pairs."""
    from meanap.stim.evoked_network import epoch_network

    iu = np.triu_indices(16, 1)
    core = np.zeros((16, 16), bool)
    core[:4, :4] = True
    trains, ev = _slow_state_trains(2, timed=True)
    pooled = epoch_network(trains, ev, (0.002, 0.05), 10, rep_num=200,
                           rng=np.random.default_rng(3))
    trial = epoch_network(trains, ev, (0.002, 0.05), 10, rep_num=200,
                          rng=np.random.default_rng(3), sttc_mode="trial_mean")
    others = ~core[iu]
    assert (pooled.sttc_thr[iu][others] > 0).mean() > 0.2      # the problem
    assert (trial.sttc_thr[iu][others] > 0).mean() < 0.1       # gone
    assert (trial.sttc_thr[np.triu(core, 1)] > 0).all()        # timing kept
    assert trial.n_valid_trials is not None


def test_trial_mean_locked_responses_are_not_edges():
    """Each node answering every event on its own is not an edge."""
    from meanap.stim.evoked_network import epoch_network

    iu = np.triu_indices(16, 1)
    trains, ev = _slow_state_trains(4, locked=True)
    net = epoch_network(trains, ev, (0.002, 0.05), 10, rep_num=200,
                        rng=np.random.default_rng(4), sttc_mode="trial_mean")
    assert (net.sttc_thr[iu] > 0).mean() < 0.15
    with pytest.raises(ValueError):
        epoch_network(trains, ev, (0.002, 0.05), 10, null="circular", sttc_mode="trial_mean")
