"""The unit-vs-noise test (meanap.pipeline.unit_noise), on units whose answer is known.

A real unit is big spikes added to noise; a "noise unit" is what a sorter
returns from noise alone: the times the filtered noise dipped past a low
threshold. The test must pass the first and flag the second, which a
comparison with noise at random times would not.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import sosfiltfilt

sys.path.insert(0, str(Path(__file__).parent))

from meanap.pipeline import unit_noise as un  # noqa: E402
from meanap.pipeline import unit_quality as uq  # noqa: E402
from meanap.pipeline.signal_quality import _bandpass_sos, _extrema  # noqa: E402

FS = 20000.0
T = 30.0


def _spike(depth: float, n: int = 40, trough: int = 15) -> np.ndarray:
    t = (np.arange(n) - trough) / FS * 1e3
    return depth * np.exp(-(t / 0.12) ** 2) + 0.3 * -depth * np.exp(-((t - 0.45) / 0.25) ** 2)


def _noise(seed: int = 0, sd: float = 10.0) -> np.ndarray:
    return np.random.default_rng(seed).normal(0, sd, int(T * FS))


def _add_unit(x: np.ndarray, rate: float, depth: float, seed: int) -> np.ndarray:
    """Spikes of *depth* µV at a refractory Poisson rate; returns their times (s)."""
    rng = np.random.default_rng(seed)
    t = np.cumsum(rng.exponential(1 / rate, int(rate * T * 2)) + 0.003)
    t = t[(t > 0.01) & (t < T - 0.01)]
    w = _spike(depth)
    for s in np.round(t * FS).astype(int):
        x[s - 15:s + 25] += w
    return t


def _noise_unit(x: np.ndarray, k: float = 2.7) -> np.ndarray:
    """What a sorter finds on pure noise: the filtered trace's dips past k SDs."""
    f = sosfiltfilt(_bandpass_sos(FS, un.NoiseTestSettings().band), x)
    z = f / (np.median(np.abs(f)) / 0.6745)
    idx = _extrema(-z, k, int(0.002 * FS))
    return idx / FS


def test_a_real_unit_passes_and_a_noise_unit_is_flagged():
    x = _noise()
    real = _add_unit(x, rate=3.0, depth=-120.0, seed=1)    # ~10 noise SDs after filtering
    fake = _noise_unit(_noise(seed=2))
    real_row, fake_row = un.electrode_noise_test(x, FS, [real])[0], \
        un.electrode_noise_test(_noise(seed=2), FS, [fake])[0]
    assert real_row["raw_sign"] == -1
    assert real_row["raw_snr"] > 6
    assert real_row["noise_fraction"] < 0.01
    assert real_row["noise_p"] < 1e-6
    assert fake_row["noise_fraction"] > 1.0          # noise makes more than the "unit" has
    assert fake_row["noise_p"] > 0.5
    assert 2.5 < fake_row["raw_snr"] < 4.0


def test_a_small_real_unit_lands_in_between():
    """Spikes barely above the noise: noise makes a share of events that size."""
    x = _noise()
    t = _add_unit(x, rate=5.0, depth=-35.0, seed=3)
    row = un.electrode_noise_test(x, FS, [t])[0]
    assert 0.0 < row["noise_fraction"] < 5.0
    assert np.isfinite(row["noise_p"])


def test_too_few_spikes_are_not_scored():
    row = un.electrode_noise_test(_noise(), FS, [np.array([1.0, 2.0, 3.0])])[0]
    assert row["raw_n_spikes"] == 3
    assert np.isnan(row["noise_fraction"])


def test_units_are_scored_on_their_own_row_and_unmatched_units_are_nan():
    a, b = _noise(seed=4), _noise(seed=5)
    real = _add_unit(a, rate=3.0, depth=-120.0, seed=6)
    fake = _noise_unit(b)
    traces = np.vstack([a, b])
    df = un.unit_noise_metrics(traces, np.array([0, 1, -1]), [real, fake, real], FS,
                               n_threads=2)
    assert list(df.columns) == list(un.COLUMNS)
    assert df.noise_fraction[0] < 0.01 and df.noise_fraction[1] > 1.0
    assert df.iloc[2].isna().all()


def test_window_start_shifts_spike_times():
    x = _noise()
    t = _add_unit(x, rate=3.0, depth=-120.0, seed=7)
    half = len(x) // 2
    df = un.unit_noise_metrics(x[None, half:], np.array([0]), [t], FS, start_s=half / FS)
    assert df.raw_n_spikes[0] == pytest.approx(np.sum(t >= half / FS), abs=2)
    assert df.noise_fraction[0] < 0.01


def test_noise_like_units_are_labelled_noise_and_unscored_ones_are_untouched():
    df = uq.compute_unit_quality(uq.UnitQualityInputs(
        unit_ids=["a", "b", "c"], duration_s=600.0, fs=FS,
        spike_trains=[np.sort(np.random.default_rng(i).uniform(0, 600, 3000)) for i in range(3)]))
    df["noise_fraction"] = [0.01, 0.8, np.nan]
    label, fails, _ = uq.classify_units(df)
    assert "noise-like" not in fails[0] and "noise-like" in fails[1] and "noise-like" not in fails[2]
    assert label[1] == "noise"


def _maxwell_file(tmp_path: Path):
    import sorted_import_fixture as fx

    n = int(T * fx.FS)
    rng = np.random.default_rng(0)
    counts = (512 + rng.normal(0, 2.0, (len(fx.CHANNELS), n))).round()
    # A real unit on routed row 3: 20-count spikes in 2-count noise.
    times = np.arange(0.5, T - 0.5, 0.25)
    for s in np.round(times * fx.FS).astype(int):
        counts[3, s:s + 3] -= 20
    raw = tmp_path / f"{fx.NAME}.raw.h5"
    fx.write_maxwell_raw(raw, fs=fx.FS, duration_s=T, voltage=counts.astype(np.uint16),
                         ttl=False)
    return raw, times, fx


def test_read_maxwell_rows_keeps_only_the_rows_asked_for(tmp_path):
    from meanap.pipeline.maxwell import load_maxwell_traces, read_maxwell_rows

    raw, _, fx = _maxwell_file(tmp_path)
    full, _ = load_maxwell_traces(raw, compact=False)
    rows, meta = read_maxwell_rows(raw, [3, 0], start_frame=1000, n_frames=5000, block_frames=700)
    assert rows.shape == (2, 5000)
    np.testing.assert_array_equal(rows[0], full[1000:6000, 3])
    np.testing.assert_array_equal(rows[1], full[1000:6000, 0])
    cmr, _ = read_maxwell_rows(raw, [3], n_frames=5000, common_median=True)
    assert abs(np.median(cmr)) < abs(np.median(rows))      # DC and shared signal gone


def test_maxwell_units_are_matched_to_raw_rows_by_electrode(tmp_path):
    from meanap.pipeline.sorted_import import ElectrodeTable, ImportedSorting

    raw, times, fx = _maxwell_file(tmp_path)
    # The sorter's electrode table in a different order from the raw rows,
    # plus an electrode the raw file does not have.
    ids = np.array([fx.ELECTRODES[5], fx.ELECTRODES[3], 99999])
    imp = ImportedSorting(
        sorter="test", sorter_unit_ids=np.array(["u0", "u1", "u2"]),
        spike_trains=[times, times + 0.1, times],
        peak_index=np.array([1, 0, 2]), electrodes=ElectrodeTable(ids=ids, xy_um=np.zeros((3, 2))),
        fs=fx.FS, duration_s=T, labels=np.array(["good"] * 3))
    df = un.maxwell_unit_noise(raw, imp, log=lambda m: None)
    assert df.noise_fraction[0] < 0.01             # on row 3, where the spikes are
    assert df.noise_fraction[1] > 0.5              # row 5 is noise at those times
    assert df.iloc[2].isna().all()                 # electrode not in the raw file


def test_import_finds_raw_beside_the_sort_and_runs_the_noise_test(tmp_path):
    """The raw file one folder down (``Plate/<rec>.raw.h5`` next to its sort),
    with the fixture's units' spikes in its voltage: every unit is found,
    scored, and clears the noise test; the table carries its columns."""
    import pandas as pd

    import sorted_import_fixture as fx
    from meanap.params import Params
    from meanap.pipeline.runner import run_pipeline
    from meanap.pipeline.unit_quality import UNIT_QUALITY_CSV, UNIT_QUALITY_DIR

    f = fx.make_fixture(tmp_path / "data" / "Plate")
    n = int(fx.DURATION_S * fx.FS)
    rng = np.random.default_rng(0)
    counts = 512 + rng.normal(0, 2.0, (len(fx.CHANNELS), n))
    for u, samples in enumerate(f.samples):
        row = fx.UNIT_PEAK_ROW[u]
        for s in samples[(samples > 2) & (samples < n - 3)].astype(int):
            counts[row, s - 1:s + 2] -= 25
    fx.write_maxwell_raw(f.raw, voltage=counts.round().astype(np.uint16), ttl=False)

    sheet = tmp_path / "batch.csv"
    pd.DataFrame([{"Recording filename": fx.NAME, "DIV": 10, "Group": "Synth"}]).to_csv(
        sheet, index=False)
    run_pipeline(Params(raw_data=str(tmp_path / "data"), output_data_folder=str(tmp_path),
                        output_data_folder_name="Run", spreadsheet_file_name=str(sheet),
                        spreadsheet_range="2:100", spike_source="import",
                        channel_layout="FromFile", random_seed=1, stop_analysis_step=1,
                        overwrite_existing_output=True), log=lambda m: None)
    table = pd.read_csv(tmp_path / "Run" / UNIT_QUALITY_DIR / f"{fx.NAME}{UNIT_QUALITY_CSV}")
    assert set(un.COLUMNS) <= set(table.columns)
    assert table["noise_fraction"].notna().all()
    assert (table["noise_fraction"] < 0.05).all()
    assert not table["fails"].fillna("").str.contains("noise-like").any()
    assert (table["electrode"].isin(fx.ELECTRODES)).all()

    # The electrode check ran on the raw file, the map and the examples were
    # drawn, and the viewer offers both.
    from meanap.pipeline.render import (
        SIGNAL_QUALITY_MAP_FIGURE, UNIT_NOISE_FIGURE, RenderContext,
        available_sorting_check_figures, available_spike_check_figures,
        render_sorting_check_figure, render_spike_check_figure,
    )
    from meanap.pipeline.signal_quality import SIGNAL_QUALITY_DIR

    run = tmp_path / "Run"
    assert (run / SIGNAL_QUALITY_DIR / f"{fx.NAME}_signal_quality_map.png").exists()
    assert (run / UNIT_QUALITY_DIR / f"{fx.NAME}_{un.FIGURE_NAME}.png").exists()
    ctx = RenderContext(params=Params(), recordings={}, results={}, batch_bounds={},
                        root=run, mode="ephys")
    assert SIGNAL_QUALITY_MAP_FIGURE in available_spike_check_figures(ctx, fx.NAME)
    assert UNIT_NOISE_FIGURE in available_sorting_check_figures(ctx, fx.NAME)
    assert render_spike_check_figure(ctx, fx.NAME, SIGNAL_QUALITY_MAP_FIGURE.name,
                                     tmp_path / "fig").exists()
    assert render_sorting_check_figure(ctx, fx.NAME, UNIT_NOISE_FIGURE.name,
                                       tmp_path / "fig").exists()


def test_examples_pick_clearest_borderline_and_typical_noise_like():
    import pandas as pd

    df = pd.DataFrame({"noise_fraction": [0.0, 0.45, 3.0, 9.0, 2.0, np.nan],
                       "raw_snr": [12.0, 4.0, 2.8, 2.5, 2.9, np.nan]})
    assert un.choose_examples(df) == [0, 1, 2]   # flagged sorted 2.0, 3.0, 9.0 → median 3.0
    assert un.choose_examples(pd.DataFrame({"noise_fraction": [np.nan],
                                            "raw_snr": [np.nan]})) == []


def test_example_round_trips_and_draws(tmp_path):
    x = _noise()
    t = _add_unit(x, rate=3.0, depth=-120.0, seed=1)
    ex = un.unit_example(x, FS, t)
    assert ex["snippets"].shape[0] == min(un.N_SNIPPETS, ex["n_spikes"])
    assert ex["median_size"] > 6
    # Noise reaches no spike-sized event: its curve is zero at the median size.
    k = np.searchsorted(ex["thresholds"], ex["median_size"])
    assert ex["noise_rate"][k:].max() == 0 and ex["unit_rate"][k - 1] > 0
    ex.update(unit_id="u1", electrode=7, noise_fraction=0.0)
    path = un.save_examples(tmp_path / "e.npz", [ex])
    back = un.load_examples(path)
    assert back[0]["unit_id"] == "u1" and back[0]["electrode"] == 7
    np.testing.assert_allclose(back[0]["unit_rate"], ex["unit_rate"])
    from meanap.native.chart_paint import save_chart

    out = save_chart(un.unit_examples_chart(back, {"u1": "good"}), tmp_path / "f.png")
    assert out.stat().st_size > 10_000


def test_map_draws_activity_noise_and_units(tmp_path):
    import pandas as pd

    from meanap.native.chart_paint import save_chart
    from meanap.pipeline.quality_maps import signal_quality_map_chart
    from meanap.pipeline.signal_quality import assess_signal_quality

    rng = np.random.default_rng(0)
    dat = rng.normal(0, 10.0, (int(10 * FS), 6)).astype(np.float32)
    for s in rng.integers(100, dat.shape[0] - 100, 200):     # spikes on channel 2 only
        dat[s:s + 4, 2] -= 150.0
    res = assess_signal_quality(dat, FS, np.arange(10, 16), max_seconds=None, n_threads=1)
    res.xy = np.array([[x, y] for y in range(2) for x in range(3)], dtype=float)
    assert res.spiking()[2] and res.spiking().sum() == 1
    units = pd.DataFrame({"unit_id": ["a", "b"], "electrode": [12, 15],
                          "label": ["good", "noise"], "noise_fraction": [0.0, 3.0]})
    chart = signal_quality_map_chart(res, units, title="t")
    assert "1 of 6 electrodes" in chart.panels[0].title
    assert {item.label.split(" (")[0] for item in chart.legend.items} == {"good units", "noise units"}
    assert save_chart(chart, tmp_path / "m.png").stat().st_size > 10_000
