"""Trial consistency, split-half networks, and the electrical-stimulation wiring.

Synthetic data with known answers:

* a *stationary* culture: every trial drawn the same way, so no drift test
  may fire more than its nominal rate;
* a *drifting* one: the set of responding nodes moves across the array over
  the trials, and the population response fades;
* a *switching* network: pairs (0, 1) and (2, 3) co-vary beyond the stimulus,
  but (0, 1) only in the first half and (2, 3) only in the second. Odd vs even
  halves then agree; first vs second half do not.

    .venv/bin/python -m pytest python/test_stim_consistency.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.stim.consistency import (  # noqa: E402
    edge_overlap, first_spike_latency, mantel, pattern_similarity,
    similarity_by_lag, split_trials, trial_consistency,
)

EVENTS = np.arange(1.0, 121.0, 2.0)          # 60 stimuli, 2 s apart
WINDOW = (0.005, 0.5)
T = 122.0


def _background(rng, n, rate=2.0):
    return [rng.uniform(0, T, rng.poisson(rate * T)) for _ in range(n)]


def _stationary(seed: int, n: int = 12) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    trains = _background(rng, n)
    for e in EVENTS:
        for j in range(n // 2):               # half the nodes respond, every trial
            trains[j] = np.r_[trains[j], e + rng.uniform(0.02, 0.2, rng.poisson(4))]
    return [np.sort(t) for t in trains]


def _drifting(seed: int = 0, n: int = 12) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    trains = _background(rng, n)
    for k, e in enumerate(EVENTS):
        centre = k / len(EVENTS) * (n - 1)    # responding nodes slide across the array
        gain = 1.0 - 0.7 * k / len(EVENTS)    # and the response fades
        for j in range(n):
            lam = 8 * gain * np.exp(-0.5 * ((j - centre) / 1.5) ** 2)
            trains[j] = np.r_[trains[j], e + rng.uniform(0.02, 0.2, rng.poisson(lam))]
    return [np.sort(t) for t in trains]


def _switching(seed: int = 0, n: int = 8) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    trains = _background(rng, n)
    half = len(EVENTS) // 2
    for k, e in enumerate(EVENTS):
        for j in range(n):                    # everyone answers every stimulus
            trains[j] = np.r_[trains[j], e + rng.uniform(0.02, 0.4, 3)]
        pair = (0, 1) if k < half else (2, 3)
        if rng.random() < 0.5:                # ...and one pair co-varies beyond that
            burst = e + rng.uniform(0.05, 0.4, 6)
            for j in pair:
                trains[j] = np.r_[trains[j], burst + rng.normal(0, 0.002, 6)]
    return [np.sort(t) for t in trains]


# ── Building blocks ───────────────────────────────────────────────────────────

def test_split_trials():
    a, b = split_trials(7, "odd_even")
    np.testing.assert_array_equal(a, [0, 2, 4, 6])
    np.testing.assert_array_equal(b, [1, 3, 5])
    a, b = split_trials(7, "first_second")
    np.testing.assert_array_equal(a, [0, 1, 2])
    np.testing.assert_array_equal(b, [3, 4, 5, 6])
    with pytest.raises(ValueError):
        split_trials(4, "random")


def test_first_spike_latency():
    trains = [np.array([0.9, 1.02, 1.3, 3.4]), np.array([])]
    lat = first_spike_latency(trains, np.array([1.0, 3.0]), (0.01, 0.3))
    np.testing.assert_allclose(lat[:, 0], [0.02, np.nan])   # 3.4 is past the window
    assert np.isnan(lat[:, 1]).all()


def test_similarity_by_lag():
    sim = pattern_similarity(np.array([[1, 0, 0], [1, 0, 0], [0, 0, 1.0]]))
    np.testing.assert_allclose(sim[0, 1], 1.0)
    np.testing.assert_allclose(similarity_by_lag(sim), [(1.0 + sim[1, 2]) / 2, sim[0, 2]])


def test_mantel_and_overlap():
    rng = np.random.default_rng(1)
    a = rng.random((15, 15))
    a = a + a.T
    r, p = mantel(a, a, n_perm=300, rng=rng)
    assert r == pytest.approx(1.0) and p < 0.01
    b = rng.random((15, 15))
    r, p = mantel(a, b + b.T, n_perm=300, rng=rng)
    assert p > 0.01
    x = np.zeros((4, 4)); x[0, 1] = x[1, 0] = 1
    jac, chance = edge_overlap(x, x)
    assert jac == 1.0 and chance == pytest.approx((1 / 6) / (2 - 1 / 6))


# ── Drift ─────────────────────────────────────────────────────────────────────

def test_drift_is_found():
    tc = trial_consistency(_drifting(), EVENTS, WINDOW, n_shuffles=300,
                           rng=np.random.default_rng(0))
    s = tc.summary
    assert s["popResponseRho"] < -0.5 and s["popResponseP"] < 0.001
    assert s["similarityLagSlope"] < 0 and s["similarityLagSlopeP"] < 0.01
    assert s["fracNodesDrifting"] > 0.5
    # the window before each stimulus never saw the drift
    assert s["baselineSimilarityLagSlopeP"] > 0.01


def test_stationary_is_not_drift():
    """Nominal 5 %: over 40 stationary cultures neither test fires much more."""
    pops, pats = [], []
    for seed in range(40):
        s = trial_consistency(_stationary(seed), EVENTS, WINDOW, n_shuffles=200,
                              rng=np.random.default_rng(seed)).summary
        pops.append(s["popResponseP"] < 0.05)
        pats.append(s["similarityLagSlopeP"] < 0.05)
    assert np.mean(pops) <= 0.15 and np.mean(pats) <= 0.15


# ── Split-half networks and the pipeline wiring ───────────────────────────────

def _params(**kw):
    from meanap.params import Params
    p = Params(stim_network_rep_num=60, func_con_lag_val=[10], **kw)
    return p


def _condition(name, onsets, steps=((1,),)):
    from meanap.stim.sequences import StimCondition
    return StimCondition(name=name, steps=steps, delays_s=np.zeros(len(steps)),
                         onsets_s=np.asarray(onsets, float), channel_index=())


def _run_networks(trains, tmp_path, exclude=None, window=WINDOW, sttc="trial_mean"):
    from meanap.pipeline.spreadsheet import RecordingInfo
    from meanap.pipeline.stim_step import _electrical_events, _stim_networks

    events = _electrical_events([_condition("pattern_1", EVENTS)])
    channels = np.arange(11, 11 + len(trains))
    return _stim_networks(
        _params(stim_network_sttc=sttc), RecordingInfo("rec", 20, "WT"), {}, trains, events, channels, None,
        tmp_path / "figs", tmp_path / "mats", lambda *_: None,
        windows={"pattern_1": window}, exclude=exclude)


@pytest.mark.parametrize("sttc, margin", [("pooled", 0.3), ("trial_mean", 0.15)])
def test_split_half_tells_reliable_from_changing(tmp_path, sttc, margin):
    # The co-varying pair fires together on only half its trials, which the
    # trial average dilutes more than pooling does: hence the smaller margin.
    tables = _run_networks(_switching(), tmp_path, sttc=sttc)
    rows = {(r["split"], r["epoch"]): r
            for r in tables["StimNetworkSplitHalf_RecordingLevel.csv"]}
    odd_even = rows[("odd_even", "evoked")]
    first_second = rows[("first_second", "evoked")]
    assert odd_even["r_excess"] > 0.45 and odd_even["mantel_p_excess"] < 0.05
    assert first_second["r_excess"] < odd_even["r_excess"] - margin
    figs = {p.name for p in (tmp_path / "figs").iterdir()}
    assert {"13_StimNetwork_pattern_1_10mslag.png", "14_StimConsistency_pattern_1.png",
            "15_StimNetworkSplitHalf_pattern_1_10mslag.png"} <= figs


def test_stimulating_electrodes_left_out(tmp_path):
    trains = _stationary(0, n=6)
    exclude = np.array([False, False, True, False, False, False])
    tables = _run_networks(trains, tmp_path, exclude=exclude)
    nodes = [r for r in tables["StimNetwork_NodeLevel.csv"]]
    assert [r["stim_electrode"] for r in nodes] == exclude.tolist()
    assert np.isnan(nodes[2]["evoked_degree"]) and not np.isnan(nodes[0]["evoked_degree"])
    with np.load(tmp_path / "mats" / "rec_stimNetwork.npz") as d:
        m = d["pattern_1__evoked__10ms__sttc"]
        assert np.isnan(m[2]).all() and np.isnan(m[:, 2]).all()
        assert np.isfinite(m[0, 1])
        np.testing.assert_array_equal(d["stim_electrode"], exclude)
    cons = tables["StimConsistency_NodeLevel.csv"]
    assert np.isnan(cons[2]["driftRho"])


def test_evoked_window_starts_after_artifact():
    from meanap.pipeline.stim_step import _post_artifact_window

    assert _post_artifact_window([0.0, 0.5], 0.0053, lambda *_: None) == (0.0053, 0.5)
    assert _post_artifact_window([0.01, 0.5], 0.0053, lambda *_: None) == (0.01, 0.5)
    with pytest.raises(ValueError):
        _post_artifact_window([0.0, 0.004], 0.0053, lambda *_: None)


def test_electrical_events_one_condition_per_pattern():
    from meanap.pipeline.stim_step import _electrical_events

    ev = _electrical_events([_condition("12", [1.0, 3.0]), _condition("hub", [2.0])])
    assert ev.condition_names == ["12", "hub"]
    np.testing.assert_array_equal(ev.patterns()[1], [2.0])
