"""Spike detection on MaxWell ``.raw.h5`` voltage: loading, units, layout, run.

The synthetic recording reuses ``sorted_import_fixture.py``'s 12 electrodes
(routed order deliberately not ID order, mapping table in a third order) and
adds voltage: uint16 counts round 512 with noise, and spikes on three known
rows. Real files compress the voltage with MaxWell's filter 401, which cannot
be written without MaxWell's plugin, so the synthetic voltage is gzip; the
last test reads a real file when the plugin and the file are both here.

    .venv/bin/python -m pytest python/test_maxwell_voltage.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sorted_import_fixture as fx  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline import maxwell  # noqa: E402
from meanap.pipeline.io import (  # noqa: E402
    count_raw_samples, find_raw_file, load_raw_recording, load_spike_file,
    raw_electrode_table,
)
from meanap.pipeline.sorted_import import layout_coords_from_um  # noqa: E402

NAME = "SynthMxwVolt_DIV10_A"
FS = 20000.0
DURATION_S = 10.0
N_FRAMES = int(FS * DURATION_S)
#: Routed rows that carry spikes, and how many each.
SPIKING_ROWS = (0, 4, 9)
N_SPIKES = 40
NOISE_COUNTS = 2.0            # ≈ 12.6 µV
TROUGH_COUNTS = 30.0          # ≈ 190 µV

#: A real MaxOne legacy-layout .raw.h5 for the one test that needs MaxWell's
#: compression plugin. Not in the repository: point MEANAP_MAXWELL_TEST_FILE
#: at any recording you have (1012-ish routed electrodes, 20 kHz).
REAL_FILE = Path(os.environ.get("MEANAP_MAXWELL_TEST_FILE", "/nonexistent.raw.h5"))


def _voltage(rng: np.random.Generator) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    v = 512.0 + rng.normal(0.0, NOISE_COUNTS, (len(fx.CHANNELS), N_FRAMES))
    t = np.arange(-20, 21) / FS
    shape = -TROUGH_COUNTS * np.exp(-(t / 1.5e-4) ** 2) \
        + 0.3 * TROUGH_COUNTS * np.exp(-((t - 4e-4) / 3e-4) ** 2)
    truth = {}
    for row in SPIKING_ROWS:
        # 40 spikes spread evenly with jitter: always > refractory apart.
        frames = (np.linspace(0.2, DURATION_S - 0.2, N_SPIKES) * FS).astype(int)
        frames += rng.integers(-200, 200, N_SPIKES)
        for fr in frames:
            v[row, fr - 20:fr + 21] += shape
        truth[row] = frames
    return np.round(v).astype(np.uint16), truth


_DATA: tuple[Path, np.ndarray, dict[int, np.ndarray]] | None = None


def data() -> tuple[Path, np.ndarray, dict[int, np.ndarray]]:
    """``(raw_path, counts, spike frames by row)``, built once."""
    global _DATA
    if _DATA is None:
        folder = Path(tempfile.mkdtemp()) / "raw"
        folder.mkdir()
        counts, truth = _voltage(np.random.default_rng(0))
        raw = folder / f"{NAME}.raw.h5"
        fx.write_maxwell_raw(raw, fs=FS, duration_s=DURATION_S, voltage=counts, ttl=False)
        _DATA = (raw, counts, truth)
    return _DATA


# ── Loading ───────────────────────────────────────────────────────────────────

def test_voltage_is_counts_times_lsb_in_routed_order():
    raw, counts, _ = data()
    dat, channels, fs = load_raw_recording(raw)
    assert fs == FS and dat.shape == (N_FRAMES, len(fx.CHANNELS)) and dat.dtype == np.float32
    # Electrode numbers, routed-row order — what an import of the file uses.
    np.testing.assert_array_equal(channels, fx.ELECTRODES)
    expected = counts.T.astype(np.float32) * np.float32(fx.LSB_V * 1e6)
    np.testing.assert_array_equal(dat, expected)
    # No offset: counts near 512 are ~3.2 mV, as neo/SpikeInterface give.
    assert 3000 < float(np.median(dat)) < 3500


def test_compact_holds_counts_and_reads_the_same_microvolts():
    raw, counts, _ = data()
    full, _, _ = load_raw_recording(raw)
    compact, channels, _ = load_raw_recording(raw, compact=True)
    assert isinstance(compact, maxwell.MaxwellTraces)
    assert compact.shape == full.shape and compact.nbytes == full.nbytes // 2
    for key in (np.s_[:, 3], np.s_[:, [0, 4, 9]], np.s_[100:200, 5], np.s_[7, :]):
        np.testing.assert_array_equal(compact[key], full[key])
    np.testing.assert_array_equal(np.asarray(compact), full)


def test_max_frames_reads_only_the_start():
    raw, _, _ = data()
    part, meta = maxwell.load_maxwell_traces(raw, max_frames=1234)
    full, _ = maxwell.load_maxwell_traces(raw)
    assert part.shape == (1234, len(fx.CHANNELS)) and meta.n_frames == N_FRAMES
    np.testing.assert_array_equal(part[:, :], full[:1234, :])


def test_found_by_name_with_or_without_dot_raw():
    raw, _, _ = data()
    assert find_raw_file(raw.parent, NAME).path == raw
    assert find_raw_file(raw.parent, f"{NAME}.raw").path == raw
    assert count_raw_samples(raw, len(fx.CHANNELS)) == N_FRAMES


def test_electrode_table_is_the_one_an_import_writes():
    raw, _, _ = data()
    table = raw_electrode_table(raw)
    np.testing.assert_array_equal(table["ids"], fx.ELECTRODES)
    coords, _ = layout_coords_from_um(fx.electrode_xy_um())
    np.testing.assert_allclose(table["coords"], coords)
    np.testing.assert_allclose(table["coords_um"], fx.electrode_xy_um())


def test_other_formats_have_no_electrode_table():
    import scipy.io as sio

    with tempfile.TemporaryDirectory() as d:
        mat = Path(d) / "x.mat"
        sio.savemat(mat, {"dat": np.zeros((100, 2)), "channels": np.array([12, 13]), "fs": 25000.0})
        assert raw_electrode_table(mat) is None


def test_probe_says_from_file():
    from meanap.pipeline.recording_probe import channel_samples, detect_layout, probe_folder

    raw, _, _ = data()
    probes = probe_folder(raw.parent)
    assert [p.format for p in probes] == ["maxwell"]
    assert probes[0].fs == FS and probes[0].n_channels == len(fx.CHANNELS)
    guess = detect_layout(probes)
    assert guess.layout == "FromFile" and guess.sure
    assert channel_samples(raw) == N_FRAMES * len(fx.CHANNELS)


def test_metadata_only_file_says_it_has_no_voltage():
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d) / "meta_only.raw.h5"
        fx.write_maxwell_raw(raw)
        with pytest.raises(ValueError, match="no voltage"):
            load_raw_recording(raw)


def test_missing_plugin_says_how_to_install_it(monkeypatch, tmp_path):
    import h5py

    raw, _, _ = data()
    monkeypatch.setattr(maxwell, "_uses_filter", lambda dset, fid: True)
    monkeypatch.setattr(h5py.h5z, "filter_avail", lambda fid: False)
    monkeypatch.setattr(maxwell, "DEFAULT_PLUGIN_DIR", tmp_path / "nowhere")
    monkeypatch.setenv("HDF5_PLUGIN_PATH", "")
    with pytest.raises(maxwell.MaxwellPluginMissing) as err:
        load_raw_recording(raw)
    msg = str(err.value)
    assert "401" in msg and "HDF5_PLUGIN_PATH" in msg and "nowhere" in msg


def test_refuses_what_will_not_fit_in_memory(monkeypatch):
    from meanap.pipeline import parallel

    raw, _, _ = data()
    monkeypatch.setattr(parallel, "_HAVE_PSUTIL", True)
    monkeypatch.setattr(parallel, "available_ram_gb", lambda: 0.5)
    with pytest.raises(MemoryError, match="GB is free"):
        load_raw_recording(raw, compact=True)


def test_detection_threads_are_capped_by_free_memory(monkeypatch):
    from meanap.pipeline import parallel, spike_detection

    monkeypatch.setattr(parallel, "_HAVE_PSUTIL", True)
    # 6 GB free, 1 GB kept back: 5 GB over 0.5 GB a thread (5e6 samples).
    monkeypatch.setattr(parallel, "available_ram_gb", lambda: 6.0)
    assert spike_detection._memory_thread_cap(5_000_000, None) == 10
    assert spike_detection._memory_thread_cap(5_000_000, 4) == 4
    monkeypatch.setattr(parallel, "available_ram_gb", lambda: 0.1)
    assert spike_detection._memory_thread_cap(5_000_000, None) == 1


# ── Through the pipeline ──────────────────────────────────────────────────────

def _params(tmp: Path, raw_folder: Path, name: str = NAME, **overrides) -> Params:
    sheet = tmp / "batch.csv"
    pd.DataFrame([{"Recording filename": name, "DIV": 10, "Group": "Synth"}]).to_csv(
        sheet, index=False)
    kw = dict(raw_data=str(raw_folder), output_data_folder=str(tmp),
              output_data_folder_name="Run", spreadsheet_file_name=str(sheet),
              spreadsheet_range="2:100", channel_layout="FromFile", random_seed=1,
              overwrite_existing_output=True, thresholds=[5.0], wname_list=["None"],
              spikes_method="thr5", express_mode=True)
    kw.update(overrides)
    return Params(**kw)


def test_steps_1_to_4_detect_on_maxwell_with_from_file_layout():
    from meanap.pipeline.runner import run_pipeline

    raw, _, truth = data()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        run_pipeline(_params(tmp, raw.parent, stop_analysis_step=4), log=lambda m: None)
        # Express mode: the run is in its bundle.
        from meanap.pipeline.bundle import open_bundle

        out = open_bundle(tmp / "Run.meanap").root
        sf = load_spike_file(out / "1_SpikeDetection" / "1A_SpikeDetectedData"
                             / f"{NAME}_spikes.npz")
        assert not sf.sorted and sf.fs == FS and sf.duration_s == DURATION_S
        np.testing.assert_array_equal(sf.channels, fx.ELECTRODES)
        np.testing.assert_array_equal(sf.electrodes["ids"], fx.ELECTRODES)
        for row in range(len(fx.CHANNELS)):
            times = sf.spike_times[row]["thr5"]
            if row in truth:
                assert len(times) == N_SPIKES
                # Within 0.5 ms of where each was put.
                np.testing.assert_allclose(np.sort(times), np.sort(truth[row]) / FS, atol=5e-4)
            else:
                assert len(times) <= 1
        # Steps 2-4 placed the nodes from the file, not a fixed layout.
        node_csvs = list(out.rglob("*NodeLevel*.csv"))
        assert node_csvs, "step 4 wrote no node-level table"


def test_from_file_refused_up_front_for_a_format_without_positions():
    import scipy.io as sio

    from meanap.pipeline.runner import run_pipeline

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        raw_folder = tmp / "raw"
        raw_folder.mkdir()
        sio.savemat(raw_folder / "Plain_DIV10_A.mat",
                    {"dat": np.zeros((1000, 2)), "channels": np.array([12, 13]), "fs": 25000.0})
        p = _params(tmp, raw_folder, name="Plain_DIV10_A")
        with pytest.raises(ValueError, match="only MaxWell"):
            run_pipeline(p, log=lambda m: None)
        assert not (tmp / "Run").exists()


# ── A real file ───────────────────────────────────────────────────────────────

def _plugin_available() -> bool:
    try:
        maxwell.ensure_maxwell_plugin()
        return True
    except maxwell.MaxwellPluginMissing:
        return False


@pytest.mark.skipif(not REAL_FILE.exists() or not _plugin_available(),
                    reason="needs MaxWell's HDF5 plugin and MEANAP_MAXWELL_TEST_FILE")
def test_real_maxone_file_reads_and_has_microvolt_noise():
    from scipy.signal import butter, sosfiltfilt

    traces, meta = maxwell.load_maxwell_traces(REAL_FILE, max_frames=int(5 * 20000))
    assert traces.shape == (100_000, len(meta.channels)) and meta.fs == 20000.0
    assert meta.lsb_v == pytest.approx(6.2942504e-06)
    seg = np.asarray(traces).T
    sos = butter(3, [300, 6000], btype="band", fs=meta.fs, output="sos")
    filt = sosfiltfilt(sos, seg, axis=1)
    mad = np.median(np.abs(filt - np.median(filt, axis=1, keepdims=True)), axis=1) / 0.6745
    # MaxOne noise after this band is typically 5-7 µV.
    assert 4.0 < float(np.median(mad)) < 8.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
