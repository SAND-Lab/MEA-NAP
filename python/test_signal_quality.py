"""Signal-quality check: noise of any colour is called noise; injected spikes are found."""
import numpy as np
import pytest

from meanap.pipeline.signal_quality import (
    assess_signal_quality, load_signal_quality, phase_randomise, save_signal_quality,
)

FS = 20000.0


def coloured_noise(n_s, n_ch, rng, alpha=1.0):
    """Gaussian noise with a 1/f^alpha spectrum plus a line-noise peak: not white."""
    n = int(n_s * FS)
    f = np.fft.rfftfreq(n, 1 / FS)
    amp = 1 / np.maximum(f, 50) ** (alpha / 2)
    amp[np.argmin(np.abs(f - 50))] *= 30
    spec = amp[:, None] * (rng.standard_normal((len(f), n_ch)) + 1j * rng.standard_normal((len(f), n_ch)))
    x = np.fft.irfft(spec, n=n, axis=0)
    return (x / x.std(axis=0)).astype(np.float32)


def add_spikes(x, ch, rate_hz, amp, rng):
    t = np.arange(-20, 40)
    wave = -np.exp(-(t / 4.0) ** 2) + 0.35 * np.exp(-((t - 14) / 8.0) ** 2)
    n = x.shape[0]
    times = np.sort(rng.choice(np.arange(100, n - 100), int(rate_hz * n / FS), replace=False))
    for s in times:
        x[s - 20:s + 40, ch] += amp * wave
    return x


def test_coloured_noise_is_noise():
    rng = np.random.default_rng(1)
    x = coloured_noise(30, 16, rng)
    res = assess_signal_quality(x, FS, max_seconds=None, band=(300, 6000))
    assert res.spiking().sum() == 0
    assert "noise" in res.summary()["verdict"]


def test_injected_spikes_found_only_where_injected():
    rng = np.random.default_rng(2)
    x = coloured_noise(30, 16, rng)
    sd = np.median(np.abs(x), axis=0) / 0.6745
    for ch in (3, 7):
        x = add_spikes(x, ch, 3.0, 12 * sd[ch], rng)
    res = assess_signal_quality(x, FS, max_seconds=None, band=(300, 6000))
    assert set(np.flatnonzero(res.spiking())) == {3, 7}
    assert res.example_channel in (3, 7)
    assert res.excess_hz()[[3, 7]].min() > 1.0


def test_flat_channel_does_not_crash():
    rng = np.random.default_rng(3)
    x = coloured_noise(5, 4, rng)
    x[:, 2] = 0
    res = assess_signal_quality(x, FS, max_seconds=None)
    assert not res.spiking()[2]


def test_phase_randomise_keeps_spectrum():
    rng = np.random.default_rng(4)
    x = rng.standard_normal((4000, 3)).cumsum(0)
    y = phase_randomise(x, rng)
    np.testing.assert_allclose(np.abs(np.fft.rfft(x, axis=0)), np.abs(np.fft.rfft(y, axis=0)), rtol=1e-6, atol=1e-6)


def test_window_and_roundtrip(tmp_path):
    rng = np.random.default_rng(5)
    x = coloured_noise(10, 3, rng)
    res = assess_signal_quality(x, FS, max_seconds=4, start_s=2, units="uV")
    assert res.duration_s == pytest.approx(4)
    back = load_signal_quality(save_signal_quality(tmp_path / "r_signal_quality.npz", res))
    np.testing.assert_array_equal(back.obs_neg, res.obs_neg)
    assert back.summary() == res.summary()


def test_step1_writes_check_and_warns_on_noise(tmp_path):
    """Through run_pipeline: one noise recording, one with spikes."""
    import scipy.io as sio
    import pandas as pd
    from meanap.params import Params
    from meanap.pipeline.runner import run_pipeline

    fs = 12500.0
    rng = np.random.default_rng(6)
    raw = tmp_path / "raw"; raw.mkdir()
    for name, spiky in (("rec_noise", False), ("rec_spiky", True)):
        n = int(12 * fs)
        x = rng.standard_normal((n, 8)).astype(np.float32) * 5.0
        if spiky:
            t = np.arange(-10, 20); w = -np.exp(-(t / 2.0) ** 2) * 80
            for s in rng.choice(np.arange(100, n - 100), 100, replace=False):
                x[s - 10:s + 20, 2] += w
        sio.savemat(raw / f"{name}.mat", {"dat": x, "channels": np.arange(1, 9), "fs": fs})
    sheet = tmp_path / "recs.csv"
    sheet.write_text("Recording Filename,DIV group,Genotype\nrec_noise,14,WT\nrec_spiky,14,WT\n")
    p = Params(output_data_folder=str(tmp_path), output_data_folder_name="Run",
               spreadsheet_file_name=str(sheet), raw_data=str(raw),
               thresholds=[5.0], wname_list=[], spikes_method="thr5",
               start_analysis_step=1, stop_analysis_step=1, prior_analysis=False,
               express_mode=True, signal_quality_seconds=10)
    logs: list[str] = []
    out = run_pipeline(p, log=logs.append)
    # express mode: everything has to travel inside the .meanap bundle
    import io, zipfile
    assert out.suffix == ".meanap"
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        d = next(n for n in names if n.endswith("1C_SignalQuality/signal_quality_summary.csv"))
        root = d[: -len("signal_quality_summary.csv")]
        table = pd.read_csv(io.BytesIO(z.read(d))).set_index("recording")
    assert table.loc["rec_noise", "n_spiking"] == 0
    assert table.loc["rec_spiky", "n_spiking"] == 1
    for name in ("rec_noise", "rec_spiky"):
        for ext in (".png", ".csv", ".npz"):
            assert f"{root}{name}_signal_quality{ext}" in names
    text = "\n".join(logs)
    assert "! [rec_noise] signal quality: no electrode" in text
    assert "[rec_spiky] signal quality: 1 of 8" in text
    # and detection still ran
    assert any(n.endswith("1A_SpikeDetectedData/rec_spiky_spikes.npz") for n in names)


def test_thread_count_does_not_change_results():
    rng = np.random.default_rng(7)
    x = coloured_noise(8, 40, rng)
    one = assess_signal_quality(x, FS, max_seconds=None, n_threads=1, channel_block=8)
    many = assess_signal_quality(x, FS, max_seconds=None, n_threads=4, channel_block=8)
    for f in ("obs_neg", "surr_neg", "surr_pos", "kurtosis", "hist_surr", "example_surr"):
        np.testing.assert_array_equal(getattr(one, f), getattr(many, f))


def test_positive_only_artifacts_are_not_spikes():
    rng = np.random.default_rng(8)
    x = coloured_noise(30, 8, rng)
    sd = np.median(np.abs(x), axis=0) / 0.6745
    n = x.shape[0]
    for s in rng.choice(np.arange(100, n - 100), 90, replace=False):   # 3 Hz positive pops
        x[s - 2:s + 3, 5] += 12 * sd[5] * np.array([0.3, 0.8, 1.0, 0.8, 0.3])
    res = assess_signal_quality(x, FS, max_seconds=None, band=(300, 6000))
    assert res.spiking().sum() == 0
    assert list(np.flatnonzero(res.positive_only())) == [5]
    assert "artifact" in res.summary()["verdict"]


def test_long_recording_stays_fast():
    """The example-window search once used an O(n*w) convolution: minutes per minute of data."""
    import time
    rng = np.random.default_rng(9)
    x = coloured_noise(60, 4, rng)
    t = time.perf_counter()
    res = assess_signal_quality(x, FS, max_seconds=None, n_threads=1)
    assert time.perf_counter() - t < 30
    assert len(res.example_obs) == int(2.0 * FS)
