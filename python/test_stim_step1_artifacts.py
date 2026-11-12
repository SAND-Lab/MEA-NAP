"""Step 1 drops detections in a stimulation blank (runner._drop_stim_artifacts).

The amplifier coming out of its blank looks like a spike to every detector,
once per stimulus on every electrode. These check the windows on synthetic
stimulation info, and that the detections, not the neighbouring spikes, go.

    .venv/bin/python -m pytest python/test_stim_step1_artifacts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

STIM = np.array([1.0, 6.0, 11.0])


def _stim_info(n=4, stim_ch=1):
    from meanap.stim.events import stim_info_without_stim_nodes

    info = stim_info_without_stim_nodes(np.arange(11, 11 + n), np.zeros((n, 2)))
    for c, s in enumerate(info):
        s.non_stim_blank_starts = STIM.copy()
        s.non_stim_blank_ends = STIM + 0.0015          # 1.5 ms blank elsewhere
    info[stim_ch].elec_stim_times = STIM.copy()
    info[stim_ch].blank_starts = STIM.copy()
    info[stim_ch].blank_ends = STIM + 0.0048           # 4.8 ms on the stim electrode
    return info


def test_windows():
    from meanap.stim.cleaning import artifact_windows

    starts, ends, own = artifact_windows(_stim_info(), {"postStimWindowDur": 0.5})
    np.testing.assert_allclose(starts, STIM)
    np.testing.assert_allclose(ends, STIM + 0.0015 + 0.0005)
    assert set(own) == {1}
    np.testing.assert_allclose(own[1][1], STIM + 0.0048 + 0.0005)


def test_in_windows_overlapping():
    from meanap.stim.cleaning import in_windows

    s, e = np.array([0.0, 0.1, 5.0]), np.array([1.0, 0.2, 6.0])
    got = in_windows(np.array([-1, 0.0, 0.5, 0.15, 1.0, 1.5, 5.5, 6.0, 7.0]), s, e)
    assert got.tolist() == [False, True, True, True, True, False, True, True, False]
    assert in_windows(np.array([]), s, e).size == 0


def test_step1_drops_only_the_blank(monkeypatch):
    from meanap.params import Params
    from meanap.pipeline import runner
    from meanap.pipeline.spike_detection import SpikeDetectionResult
    from meanap.pipeline.spreadsheet import RecordingInfo
    import meanap.stim.detection as det

    monkeypatch.setattr(det, "detect_stim_times", lambda *a, **k: _stim_info())
    artifact = STIM + 0.0012                         # in every channel's blank
    late = STIM + 0.003                              # past it, except on the stim electrode
    real = np.array([0.5, 3.0, 8.0])
    times = {c: {"thr4": np.sort(np.r_[artifact, late, real])} for c in range(4)}
    waves = {c: {"thr4": np.arange(9.0)[:, None] * np.ones((1, 3))} for c in range(4)}
    res = SpikeDetectionResult(times, waves, {}, np.arange(11, 15), 25000.0)
    p = Params(stimulation_mode=True)
    out = runner._drop_stim_artifacts(p, RecordingInfo("r", 1, "WT"), np.zeros((10, 4)),
                                      res.channels, res.fs, res, lambda *_: None)
    np.testing.assert_allclose(out.spike_times[0]["thr4"], np.sort(np.r_[late, real]))
    np.testing.assert_allclose(out.spike_times[1]["thr4"], real)   # its own 4.8 ms blank
    assert len(out.spike_waveforms[0]["thr4"]) == 6

    p = Params(stimulation_mode=True, stim_detection_method="eventsCSV")
    same = runner._drop_stim_artifacts(p, RecordingInfo("r", 1, "WT"), np.zeros((10, 4)),
                                       res.channels, res.fs, res, lambda *_: None)
    assert same is res
