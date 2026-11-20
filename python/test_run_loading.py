"""Opening a large run quickly, and without a frozen window.

Listing a bundle's figures used to parse step 2's ``ephys_results.json`` a few
times per recording (minutes on a 200-recording batch); it is now read once
per version of the file. And the GUI reads the run on a worker thread
(:func:`meanap.gui.run_loading.read_run`).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from meanap.pipeline import render  # noqa: E402


def _ctx(root: Path):
    # Only .root is read by the functions under test; a plain object takes
    # the cache attributes the way the frozen dataclass does.
    return SimpleNamespace(root=root)


def _write(root: Path, stats: dict) -> Path:
    path = root / "2_NeuronalActivity" / "ephys_results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats))
    return path


def test_ephys_stats_parsed_once_and_again_when_the_file_changes(tmp_path, monkeypatch):
    path = _write(tmp_path, {"a": {"FR": [1.0, 2.0]}, "b": {"FR": [5.0]}})
    loads = []
    real = json.load
    monkeypatch.setattr(render.json, "load", lambda fh: loads.append(1) or real(fh))
    ctx = _ctx(tmp_path)
    first = render._ephys_stats(ctx)
    assert render._ephys_stats(ctx) is first and len(loads) == 1
    assert np.array_equal(first["a"]["FR"], [1.0, 2.0])

    time.sleep(0.01)
    _write(tmp_path, {"a": {"FR": [9.0]}})
    os.utime(path, ns=(time.time_ns(), time.time_ns() + 10**9))
    assert np.array_equal(render._ephys_stats(ctx)["a"]["FR"], [9.0]) and len(loads) == 2


def test_batch_maxima_computed_once_per_stats(tmp_path, monkeypatch):
    metric = next(iter(render._ACTIVITY_BATCH_METRICS))
    _write(tmp_path, {"a": {metric: [1.0, 3.0]}, "b": {metric: [7.0, np.nan]}})
    ctx = _ctx(tmp_path)
    got = render._activity_batch_max(ctx)
    assert got[metric] == 7.0
    got[metric] = -1                                # a caller's copy, not the cache
    calls = []
    real = np.nanmax
    monkeypatch.setattr(render.np, "nanmax", lambda *a, **k: calls.append(1) or real(*a, **k))
    assert render._activity_batch_max(ctx)[metric] == 7.0 and not calls


_APP = []


def _app():
    from PyQt6.QtWidgets import QApplication

    if not _APP:
        _APP.append(QApplication.instance() or QApplication([]))
    return _APP[0]


def test_read_run_returns_the_run_and_raises_what_reading_raised(tmp_path, monkeypatch):
    _app()
    from meanap.gui import run_loading
    import meanap.viewer.server as server

    class Slow:
        def __init__(self, source):
            time.sleep(run_loading.QUIET_S * 2)     # long enough for the dialog
            self.source = source

        def manifest(self):
            return {"recordings": []}

    monkeypatch.setattr(server, "ViewerService", Slow)
    service, manifest = run_loading.read_run(tmp_path)
    assert service.source == tmp_path and manifest == {"recordings": []}

    class Broken:
        def __init__(self, source):
            raise ValueError("not a MEA-NAP bundle")

    monkeypatch.setattr(server, "ViewerService", Broken)
    with pytest.raises(ValueError, match="not a MEA-NAP bundle"):
        run_loading.read_run(tmp_path)
