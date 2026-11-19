"""Unit quality metrics (meanap.pipeline.unit_quality), on units whose answer is known.

Each metric is checked on synthetic spike trains, amplitudes or waveforms
built to pass or fail it, and the two threshold presets are checked to differ
only where they say they do.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent))

from meanap.pipeline import unit_quality as uq  # noqa: E402

FS = 20000.0


def _refractory_train(rate, duration, dead=0.003, seed=0):
    """A Poisson train with no two spikes closer than *dead*: a clean neuron."""
    rng = np.random.default_rng(seed)
    isi = rng.exponential(1.0 / rate, int(rate * duration * 1.5)) + dead
    t = np.cumsum(isi)
    return t[t < duration]


def _poisson_train(rate, duration, seed=1):
    rng = np.random.default_rng(seed)
    return np.sort(rng.uniform(0, duration, rng.poisson(rate * duration)))


def _spike(n=60, trough=20, depth=-80.0, peak=25.0, fs=FS):
    """A clean extracellular spike: a trough, then a slower positive peak."""
    t = (np.arange(n) - trough) / fs * 1e3
    return depth * np.exp(-(t / 0.12) ** 2) + peak * np.exp(-((t - 0.45) / 0.25) ** 2)


# ── single metrics ────────────────────────────────────────────────────────────


def test_hill_contamination_is_zero_for_a_clean_unit_and_high_for_poisson():
    clean = _refractory_train(20, 600)
    assert uq.hill_contamination(clean, 600) == 0.0
    assert uq.hill_contamination(_poisson_train(20, 600), 600) > 0.3


def test_sliding_test_clears_clean_convicts_noise_and_doubts_sparse_units():
    clean = _refractory_train(15, 600)
    assert uq.sliding_rp_status(clean, 600) == 1
    assert uq.sliding_rp_contamination(clean, 600) <= 0.1
    assert uq.sliding_rp_status(_poisson_train(30, 600), 600) == -1
    # 75 spikes, no violations: nothing can be said either way.
    sparse = _refractory_train(0.25, 300)
    assert uq.sliding_rp_status(sparse, 300) == 0
    assert np.isinf(uq.sliding_rp_contamination(sparse, 300))


def test_presence_ratio_counts_the_minutes_a_unit_fires_in():
    train = _refractory_train(5, 300)
    assert uq.presence_ratio(train, 600) == pytest.approx(0.5)
    assert uq.presence_ratio(_refractory_train(5, 600), 600) == 1.0


def test_spikes_missing_sees_a_cut_off_amplitude_distribution():
    rng = np.random.default_rng(2)
    full = rng.normal(100, 15, 4000)
    assert uq.percent_spikes_missing(full) < 5
    cut = full[full > 100]
    assert 30 < uq.percent_spikes_missing(cut) < 70
    assert np.isnan(uq.percent_spikes_missing(full[:10]))


def test_waveform_metrics_of_a_clean_spike_and_of_noise():
    t = uq.QualityThresholds()
    clean = uq.waveform_metrics(_spike(), FS, t)
    assert clean["n_troughs"] == 1 and clean["n_peaks"] <= 2
    assert 100 < clean["duration_us"] < 1150
    assert clean["baseline_fraction"] < 0.1
    rng = np.random.default_rng(3)
    jagged = uq.waveform_metrics(rng.normal(0, 1, 60), FS, t)
    assert jagged["n_peaks"] > t.max_n_peaks or jagged["n_troughs"] > t.max_n_troughs


def test_spatial_decay_only_on_dense_probes():
    n_ch = 9
    wave = _spike()
    for pitch, scored in ((20.0, True), (87.5, False)):
        xy = np.array([(i % 3, i // 3) for i in range(n_ch)], float) * pitch
        d = np.hypot(*(xy - xy[4]).T)
        tmpl = wave[:, None] * np.exp(-d / 30.0)[None, :]
        inputs = uq.UnitQualityInputs(["u"], [_refractory_train(10, 600)], 600, FS,
                                      templates=tmpl[None], channel_xy_um=xy)
        df = uq.compute_unit_quality(inputs, "bombcell")
        assert np.isfinite(df.spatial_decay[0]) == scored


# ── labels ────────────────────────────────────────────────────────────────────


def _inputs(trains, waves, noise=5.0):
    n_ch = 1
    tmpl = np.stack([w[:, None] for w in waves])
    rng = np.random.default_rng(4)
    amps = [np.abs(rng.normal(w.min(), 0.1 * abs(w.min()), len(tr)))
            for w, tr in zip(waves, trains)]
    return uq.UnitQualityInputs([f"u{i}" for i in range(len(trains))], trains, 600, FS,
                                amplitudes=amps, templates=tmpl, in_uv=True,
                                noise_levels=np.full(n_ch, noise))


def test_a_clean_unit_is_good_noise_is_noise_and_poisson_is_mua():
    rng = np.random.default_rng(5)
    inputs = _inputs([_refractory_train(10, 600), _refractory_train(10, 600, seed=6),
                      _poisson_train(30, 600)],
                     [_spike(), rng.normal(0, 30, 60), _spike()])
    for preset in ("bombcell", "mea"):
        df = uq.compute_unit_quality(inputs, preset)
        assert list(df.label) == ["good", "noise", "mua"], (preset, list(df.fails))
        assert df.fails[0] == "" and "refractory" in df.fails[2]


def test_mea_preset_keeps_short_recordings_and_mea_shaped_spikes():
    # A slow unit on a short recording, on an MEA-like broad positive pre-phase.
    wave = _spike()
    wave[:15] += 30.0 * np.exp(-((np.arange(15) - 14) / 6.0) ** 2)
    sparse = _refractory_train(0.3, 280)
    inputs = uq.UnitQualityInputs(["u"], [sparse], 280, FS, templates=wave[None, :, None],
                                  in_uv=True, noise_levels=np.array([5.0]))
    bomb = uq.compute_unit_quality(inputs, "bombcell")
    mea = uq.compute_unit_quality(inputs, "mea")
    assert bomb.label[0] != "good"
    assert {"few spikes", "refractory unconfirmed"} <= set(bomb.fails[0].split("; "))
    assert mea.label[0] == "good", mea.fails[0]


def test_presets_and_unknown_names():
    assert uq.DEFAULT_PRESET == "mea"
    assert uq.thresholds_for(None) is uq.PRESETS["mea"]
    with pytest.raises(ValueError):
        uq.thresholds_for("kilosort")


def test_figure_is_drawn(tmp_path):
    from meanap.native import output

    output.ensure_app()
    rng = np.random.default_rng(7)
    inputs = _inputs([_refractory_train(10, 600, seed=k) for k in range(5)],
                     [_spike(depth=-40 - 20 * k) for k in range(4)] + [rng.normal(0, 30, 60)])
    df = uq.compute_unit_quality(inputs)
    path = uq.plot_unit_quality(df, tmp_path / "q.png", title="synthetic", amplitude_in_uv=True)
    assert path.exists() and path.stat().st_size > 10_000


def test_reads_a_spikeinterface_analyzer(tmp_path):
    si = pytest.importorskip("spikeinterface.core")
    rec, sorting = si.generate_ground_truth_recording(durations=[60.0], num_units=5,
                                                      num_channels=8, seed=0)
    analyzer = si.create_sorting_analyzer(sorting, rec, format="binary_folder",
                                          folder=tmp_path / "an", sparse=False)
    analyzer.compute(["random_spikes", "templates", "noise_levels", "spike_amplitudes"])
    inputs = uq.inputs_from_analyzer(tmp_path / "an")
    assert len(inputs.unit_ids) == 5 and inputs.templates.shape[0] == 5
    assert len(inputs.amplitudes) == 5
    assert [len(a) for a in inputs.amplitudes] == [len(t) for t in inputs.spike_trains]
    df = uq.compute_unit_quality(inputs)
    assert set(df.label) <= set(uq.LABELS) and np.isfinite(df.snr).all()
