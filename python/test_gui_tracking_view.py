"""Reviewing tracked cells in the app: missing days and cell-type conflicts.

Run from the repo root::

    uv run pytest python/test_gui_tracking_view.py

A synthetic chain with known drift between days: the expected position of a
cell on a day it was missed must be its position elsewhere moved by that drift,
in the missing day's own pixels. Then the page: filters, the per-day table,
the dashed ring, and a cell-type decision saved and read back.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from meanap.catnap.tracking.review import (  # noqa: E402
    MIN_SHARED, day_shifts, expected_positions, final_call, is_flip, missing_sessions,
    nearest_roi, needs_decision, roi_number,
)

#: How far each day's field sits from day 0's, as (dy, dx).
DRIFT = [(0.0, 0.0), (5.0, -20.0), (-3.0, 10.0)]
DIVS = [14, 21, 28]
N_CELLS = 12


def _b64(values) -> str:
    return base64.b64encode(np.asarray(values, dtype=np.float32).tobytes()).decode()


def _chain(*, missing: dict[int, list[int]] | None = None, wrong_match: bool = False,
           extra_untracked: bool = True) -> dict:
    """Cells on a grid, every day drifted by :data:`DRIFT`.

    *missing* maps a cluster to the days it was not found on. Each day also
    carries one untracked ROI, and its rows map to suite2p indices offset by
    100 so a row number cannot pass for an ROI number.
    """
    missing = missing or {}
    rng = np.random.default_rng(0)
    base = np.column_stack([rng.uniform(100, 900, N_CELLS), rng.uniform(100, 900, N_CELLS)])
    sessions, positions = [], {c: [] for c in range(N_CELLS)}
    for k, (dy, dx) in enumerate(DRIFT):
        ys, xs, clusters = [], [], []
        for c in range(N_CELLS):
            if k in missing.get(c, []):
                continue
            y, x = base[c, 0] + dy, base[c, 1] + dx
            if wrong_match and k == 1 and c == 0:
                y, x = y + 300, x + 300          # one match far off: medians ignore it
            positions[c].append([k, float(y), float(x)])
            ys.append(y)
            xs.append(x)
            clusters.append(c)
        if extra_untracked:
            ys.append(base[0, 0] + dy + 4)       # an unmatched ROI 4 px from cell 0
            xs.append(base[0, 1] + dx)
            clusters.append(-1)
        sessions.append({"div": DIVS[k], "cy": _b64(ys), "cx": _b64(xs),
                         "cluster": clusters, "roi": [100 + i for i in range(len(ys))],
                         "recording": f"rec_DIV{DIVS[k]}"})
    cells = []
    for c in range(N_CELLS):
        days = [p[0] for p in positions[c]]
        # cell 1's Mecp2 flips and ties; cell 2's flips but the vote settles it
        mecp2 = ([1, -1, 1][:len(days)] if c == 2 else
                 [1, -1][:len(days)] + [0] * (len(days) - 2) if c == 1 else [1] * len(days))
        call = "~" if c in (1, 2) else "+"
        rec = ({"call": None, "reason": "tie"} if c == 1 else
               {"call": "+", "reason": "majority"} if c == 2 else
               {"call": "+", "reason": "unanimous"})
        cells.append({"cluster": c, "divs": [DIVS[k] for k in days],
                      "positions": positions[c], "rescuedDivs": [], "mergedDivs": [],
                      "fingerprint": 0.1 * c, "percentile": 50.0, "crops": [],
                      "traces": [], "metrics": [{} for _ in days], "comparisons": [],
                      "types": {"Mecp2": mecp2}, "typeCall": {"Mecp2": call},
                      "typeRec": {"Mecp2": rec}})
    return {"chainKey": "chainA", "subtitle": "", "frame": 1024, "sessions": sessions,
            "cells": cells, "markers": ["Mecp2"], "genotype": "Het", "overrides": {}}


# ── the arithmetic ───────────────────────────────────────────────────────────


def test_day_shifts_recover_the_drift():
    shifts = day_shifts(_chain()["sessions"])
    for a in range(3):
        for b in range(3):
            if a == b:
                continue
            dy, dx, n = shifts[(a, b)]
            assert (dy, dx) == pytest.approx((DRIFT[b][0] - DRIFT[a][0],
                                              DRIFT[b][1] - DRIFT[a][1]), abs=1e-3)
            assert n == N_CELLS


def test_expected_position_is_in_the_missing_days_own_pixels():
    payload = _chain(missing={3: [2]})
    cell = payload["cells"][3]
    assert missing_sessions(cell, 3) == [2]
    e = expected_positions(payload)[3][2]
    y0, x0 = cell["positions"][0][1:]
    # day 0 position moved by day 2's drift — not day 0's own coordinates
    assert (e.y, e.x) == pytest.approx((y0 + DRIFT[2][0], x0 + DRIFT[2][1]), abs=1e-3)
    assert e.n_days == 2 and e.spread_px == pytest.approx(0, abs=1e-3)


def test_one_wrong_match_does_not_move_the_shift():
    shifts = day_shifts(_chain(wrong_match=True)["sessions"])
    assert shifts[(0, 1)][:2] == pytest.approx(DRIFT[1], abs=1e-3)


def test_no_estimate_from_days_sharing_too_few_cells():
    # day 2 keeps only cells 0..MIN_SHARED-2: too few shared with anything
    gone = {c: [2] for c in range(MIN_SHARED - 1, N_CELLS)}
    payload = _chain(missing=gone)
    expected = expected_positions(payload)
    assert all(2 not in expected.get(c, {}) for c in gone)


def test_roi_numbers_are_suite2p_indices_not_rows():
    session = _chain()["sessions"][0]
    assert roi_number(session, 0) == 100
    assert roi_number({"cluster": [0]}, 0) == 0          # older payloads: rows
    row, dist = nearest_roi(session, *_chain()["cells"][0]["positions"][0][1:])
    assert (row, dist) == (0, 0.0)


def test_cell_type_calls_follow_the_web_page():
    payload = _chain()
    tie, settled, plain = payload["cells"][1], payload["cells"][2], payload["cells"][3]
    assert is_flip(tie, "Mecp2") and is_flip(settled, "Mecp2") and not is_flip(plain, "Mecp2")
    assert final_call(tie, "Mecp2", {}) is None
    assert final_call(settled, "Mecp2", {}) == "+"
    assert needs_decision(tie, ["Mecp2"], {}) and not needs_decision(settled, ["Mecp2"], {})
    decided = {"1": {"Mecp2": "-"}}
    assert final_call(tie, "Mecp2", decided) == "-"
    assert not needs_decision(tie, ["Mecp2"], decided)
    assert final_call(tie, "Mecp2", {"1": {"Mecp2": "?"}}) is None


# ── the page ─────────────────────────────────────────────────────────────────


class _Service:
    """What the page asks of a run, with decisions kept in a real overrides file."""

    def __init__(self, payload: dict, overrides: Path):
        self.payload, self.path = payload, overrides

    def tracking(self):
        return {"available": True, "chains": [
            {"chain": "chainA", "divs": DIVS, "genotype": "Het"},
            {"chain": "chainB", "divs": DIVS, "genotype": "WT"}]}

    def tracking_payload(self, chain):
        from meanap.catnap.tracking.celltypes import load_overrides

        return {**self.payload, "chainKey": chain,
                "overrides": load_overrides(self.path).get(chain, {})}

    def set_tracking_override(self, body):
        from meanap.catnap.tracking.celltypes import set_override

        saved = set_override(self.path, body["chain"], body["cluster"], body["marker"],
                             body["value"])
        return {"chain": body["chain"], "overrides": saved, "file": str(self.path)}


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def slot_errors(monkeypatch):
    """Fail on an exception raised inside a Qt slot.

    PyQt hands those to ``sys.excepthook`` and carries on, so a broken slot
    would otherwise pass as a page that merely shows the wrong thing.
    """
    raised = []
    monkeypatch.setattr(sys, "excepthook", lambda *info: raised.append(info))
    yield
    assert not raised, "a slot raised: " + "; ".join(repr(e[1]) for e in raised)


def _view(app, tmp_path, **chain):
    from meanap.gui.tracking_view import TrackingView

    view = TrackingView()
    view.resize(1400, 1000)
    assert view.load(_Service(_chain(**chain), tmp_path / "overrides.json"))
    view.show()
    app.processEvents()
    return view


def test_search_hides_other_chains(app, tmp_path):
    view = _view(app, tmp_path)
    view.search.setText("chainb")
    hidden = [view.chains.item(i).isHidden() for i in range(view.chains.count())]
    assert hidden == [True, False]


def test_missing_filter_and_the_expected_ring(app, tmp_path):
    view = _view(app, tmp_path, missing={3: [2], 4: [1, 2]})
    labels = [view.missing_filter.itemText(i) for i in range(view.missing_filter.count())]
    assert labels[1] == "Missing on any day (2)"
    assert "Missing on DIV 28 (2)" in labels and "Missing on DIV 21 (1)" in labels

    view.missing_filter.setCurrentIndex(view.missing_filter.findData(1))   # DIV 21
    assert view.cells.rowCount() == 1 and view.cell["cluster"] == 4

    view.select_cluster(3)
    rows = view.day_rows(view.cell)
    assert [r["found"] for r in rows] == [True, True, False]
    assert [r["roi"] for r in rows[:2]] == [103, 103]
    y0, x0 = view.cell["positions"][0][1:]
    assert (rows[2]["y"], rows[2]["x"]) == pytest.approx(
        (y0 + DRIFT[2][0], x0 + DRIFT[2][1]), abs=1e-3)
    # the dashed ring sits there on the missing day; the solid ring elsewhere
    ring = view._days[2].expected.getData()
    assert (ring[0][0], ring[1][0]) == pytest.approx((rows[2]["x"], rows[2]["y"]), abs=1e-3)
    assert len(view._days[2].ring.getData()[0]) == 0
    assert len(view._days[0].ring.getData()[0]) == 1
    text = view.cell_text()
    assert text.splitlines()[0].startswith("chain\tcell\tDIV\trecording\tsuite2p ROI\tx\ty")
    assert "rec_DIV28" in text and "not found" in text.splitlines()[3]


def test_conflict_filter_and_a_saved_decision(app, tmp_path):
    view = _view(app, tmp_path)
    items = {view.type_filter.itemData(i): view.type_filter.itemText(i)
             for i in range(view.type_filter.count())}
    assert items["review"] == "Needs a decision (1)"
    assert items["flip:Mecp2"] == "Mecp2 changes across days (2)"

    view.type_filter.setCurrentIndex(view.type_filter.findData("review"))
    assert view.cells.rowCount() == 1 and view.cell["cluster"] == 1
    view.decide("Mecp2", "-")
    # settled: it leaves the review filter, which stays chosen
    assert view.type_filter.currentData() == "review"
    assert view.type_filter.currentText() == "Needs a decision (0)"
    assert view.cells.rowCount() == 0

    # and it was written: a fresh page over the same file reads it back
    again = _view(app, tmp_path)
    assert again.overrides == {"1": {"Mecp2": "-"}}
    again.select_cluster(1)
    combo = again.decisions.findChild(type(again.colour_by), "decision_Mecp2")
    assert combo.currentData() == "-"
    combo.setCurrentIndex(0)                              # back to the recommendation
    assert again.overrides == {}


def test_clicking_a_filtered_out_cell_clears_the_filters(app, tmp_path):
    view = _view(app, tmp_path, missing={3: [2]})
    view.missing_filter.setCurrentIndex(view.missing_filter.findData("any"))
    assert view.cells.rowCount() == 1
    view.select_cluster(7)
    assert view.cell["cluster"] == 7 and view.missing_filter.currentIndex() == 0
