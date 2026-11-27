"""The stim step saves its shuffle-test results (not only the 12_ figures).

On a small synthetic event-driven run (two conditions, so the RNG stream runs
across patterns), checks that:

* ``StimActivity_NodeLevel.csv`` has ``trial_prop_obs`` and ``is_sig_hi``,
  right after MATLAB's columns, and responders come out significant;
* MATLAB's ``shuffleResults_pattern_{k}.mat`` is written with MATLAB's names;
* the saved results are the ones the saved figure payload reproduces — what
  the viewer's ``12_shuffle_test_*`` figures show;
* they are saved when plotting fails;
* ``python/rebuild_stim_shuffle.py`` rebuilds the same outputs for a run made
  before they were saved.

    uv run pytest python/test_stim_shuffle_results.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import scipy.io as sio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "python"))

REC = "recA"
T = 70.0
CHANNELS = np.array([12, 13, 14, 15, 16, 17, 21, 22])
RESPONDERS = (0, 1, 3, 4)          # electrode positions that respond to "light"
EVENTS = {"light": np.arange(1.0, 61.0, 2.0), "sound": np.arange(2.0, 62.0, 2.0)}


def _write_inputs(tmp: Path) -> tuple[Path, Path]:
    from meanap.pipeline.io import save_spike_times_npz
    from meanap.pipeline.resume import SPIKE_SUBDIR

    rng = np.random.default_rng(0)
    trains = [rng.uniform(0, T, rng.poisson(3 * T)) for _ in CHANNELS]
    for e in EVENTS["light"]:
        for j in RESPONDERS:
            trains[j] = np.r_[trains[j], e + rng.uniform(0.005, 0.05, rng.poisson(3))]
    spikes = {c: {"thr4p5": np.sort(t)} for c, t in enumerate(trains)}
    out = tmp / "Output"
    save_spike_times_npz(out / SPIKE_SUBDIR / f"{REC}_spikes.npz", spikes, CHANNELS,
                         25000.0, duration_s=T)
    events = tmp / "events"
    events.mkdir()
    rows = sorted((t, c) for c, ts in EVENTS.items() for t in ts)
    (events / f"{REC}_events.csv").write_text(
        "time_s,condition\n" + "".join(f"{t},{c}\n" for t, c in rows))
    return out, events


def _params(events: Path):
    from meanap.params import Params

    return Params(stim_detection_method="eventsCSV", stim_events_folder=str(events),
                  spikes_method="thr4p5", stim_network=False, stim_n_shuffles=60,
                  random_seed=7)


def _run(tmp: Path, log=None) -> Path:
    from meanap.pipeline.spreadsheet import RecordingInfo
    from meanap.pipeline.stim_step import run_stim_analysis

    out, events = _write_inputs(tmp)
    run_stim_analysis(_params(events), [RecordingInfo(REC, 14, "WT")], out,
                      log=log or (lambda *_: None))
    return out


def _dest(out: Path) -> Path:
    return out / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis" / "WT" / REC


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("shuffle"))


def test_csv_has_shuffle_columns(run):
    from meanap.stim.activity import CSV_COLUMNS

    df = pd.read_csv(run / "StimActivity_NodeLevel.csv")
    cols = list(df.columns)
    assert cols[:len(CSV_COLUMNS)] == CSV_COLUMNS
    assert cols[len(CSV_COLUMNS):len(CSV_COLUMNS) + 2] == ["trial_prop_obs", "is_sig_hi"]
    assert df["is_sig_hi"].dtype == bool and df["trial_prop_obs"].between(0, 1).all()
    light = df[df["condition"] == "light"].set_index("file_index")
    for j in RESPONDERS:
        assert light.loc[j + 1, "is_sig_hi"], f"responder at position {j + 1}"
    assert not light.drop(index=[j + 1 for j in RESPONDERS])["is_sig_hi"].any()


def test_matlab_files(run):
    df = pd.read_csv(run / "StimActivity_NodeLevel.csv")
    for k in (1, 2):
        m = sio.loadmat(_dest(run) / f"shuffleResults_pattern_{k}.mat",
                        squeeze_me=True, struct_as_record=False)["patternShuffleResults"]
        # Written as MATLAB logicals; scipy reads logicals back as uint8 0/1.
        assert m.isSigHi.dtype == np.uint8 and m.isSigHi.shape == (len(CHANNELS),)
        assert set(np.unique(m.isSigHi)) <= {0, 1}
        assert m.trialProp_null.shape == (len(CHANNELS), 60) and m.Nshuffles == 60
        np.testing.assert_array_equal(m.isSignificant, m.isSigHi)
        np.testing.assert_array_equal(m.isSigHi.astype(bool), m.trialProp_obs > m.pctile_hi)
        rows = df[df["pattern_id"] == k]
        np.testing.assert_array_equal(rows["is_sig_hi"],
                                      m.isSigHi[rows["file_index"] - 1].astype(bool))
        np.testing.assert_allclose(rows["trial_prop_obs"],
                                   m.trialProp_obs[rows["file_index"] - 1])


def test_saved_results_are_the_payloads(run):
    """The figures (and the viewer) draw the null from the saved payload: the
    step's results must be the same numbers."""
    from meanap.stim.redraw import load_figure_payload, shuffle_tests_from_payload

    redone = shuffle_tests_from_payload(
        load_figure_payload(run / "ExperimentMatFiles" / f"{REC}_stimFigures.npz"))
    for k, sr in redone.items():
        m = sio.loadmat(_dest(run) / f"shuffleResults_pattern_{k}.mat",
                        squeeze_me=True, struct_as_record=False)["patternShuffleResults"]
        np.testing.assert_array_equal(m.trialProp_null, sr.trial_prop_null)
        np.testing.assert_array_equal(m.isSigHi, sr.is_sig_hi)


def test_saved_when_plotting_fails(tmp_path, monkeypatch):
    import meanap.stim.redraw as redraw

    def broken(*a, **k):
        raise RuntimeError("no figures today")

    monkeypatch.setattr(redraw, "draw_activity_figures", broken)
    lines = []
    out = _run(tmp_path, log=lines.append)
    assert any("stim plotting failed" in s for s in lines)
    df = pd.read_csv(out / "StimActivity_NodeLevel.csv")
    assert df["is_sig_hi"].notna().all() and df["is_sig_hi"].any()
    assert (_dest(out) / "shuffleResults_pattern_1.mat").is_file()
    assert not list(_dest(out).glob("12_shuffle_test_*"))


def test_rebuild_for_an_old_run(run, tmp_path):
    from rebuild_stim_shuffle import rebuild_run

    old = tmp_path / "Old"
    shutil.copytree(run, old)
    csv = old / "StimActivity_NodeLevel.csv"
    now = pd.read_csv(csv)
    now.drop(columns=["trial_prop_obs", "is_sig_hi"]).to_csv(csv, index=False)
    for p in _dest(old).glob("shuffleResults_pattern_*.mat"):
        p.unlink()

    assert rebuild_run(old, log=lambda *_: None)
    pd.testing.assert_frame_equal(pd.read_csv(csv), now)
    assert "is_sig_hi" not in pd.read_csv(csv.with_name(csv.name + ".bak")).columns
    for k in (1, 2):
        a = sio.loadmat(_dest(run) / f"shuffleResults_pattern_{k}.mat")["patternShuffleResults"]
        b = sio.loadmat(_dest(old) / f"shuffleResults_pattern_{k}.mat")["patternShuffleResults"]
        for f in a.dtype.names:
            np.testing.assert_array_equal(a[f][0, 0], b[f][0, 0], err_msg=f)

    # A second rebuild changes nothing and keeps the first backup.
    assert rebuild_run(old, log=lambda *_: None)
    pd.testing.assert_frame_equal(pd.read_csv(csv), now)
