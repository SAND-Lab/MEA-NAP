"""Tests for CAT-NAP cross-day cell tracking.

Each test here corresponds to something that actually went wrong while the
prototype was built, so they are regression tests rather than coverage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.catnap.tracking.chains import build_chains, parse_recording
from meanap.catnap.tracking.complete import complete_clusters, merge_split_clusters
from meanap.catnap.tracking.controls import roi_shift_control, summarise_floor
from meanap.catnap.tracking.footprint import density_map, displacement
from meanap.catnap.tracking.register import (
    padded_frame,
    shift_stat,
    solve_offsets,
    verify_offsets,
)
from meanap.catnap.tracking.validate import (
    _zscore_rows,
    auc_vs_null,
    correct_neuropil,
    event_metrics,
    reduce_session,
)
from meanap.catnap.tracking.viewer import CellCard, select_cards


def _rois(centres, frame=256, radius=3, rng=None):
    """Minimal stat-like ROIs at the given centres."""
    out = []
    for cy, cx in centres:
        ys, xs = [], []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dy * dy + dx * dx <= radius * radius:
                    ys.append(int(cy) + dy)
                    xs.append(int(cx) + dx)
        ys, xs = np.array(ys), np.array(xs)
        keep = (ys >= 0) & (xs >= 0) & (ys < frame) & (xs < frame)
        out.append({"ypix": ys[keep], "xpix": xs[keep],
                    "lam": np.ones(keep.sum(), dtype=float),
                    "med": [float(cy), float(cx)]})
    return np.array(out, dtype=object)


# ── chain discovery ───────────────────────────────────────────────────────────

def test_chain_key_drops_date_as_well_as_div():
    """The imaging date changes with the DIV, so dropping only the DIV fails."""
    a = parse_recording("OPME240517_17_20240602_P1_pup2D_WT_MOI50000_DIV16")
    b = parse_recording("OPME240517_17_20240610_P1_pup2D_WT_MOI50000_DIV30")
    assert a.chain == b.chain
    assert (a.div, b.div) == (16, 30)


def test_chain_key_handles_the_other_naming_convention():
    rec = parse_recording("20230518_9_OPME230505_P1_pup5B_KO_MOI25000_DIV13")
    assert rec.chain == "9_OPME230505_P1_pup5B_KO_MOI25000"
    assert rec.prep == "OPME230505" and rec.genotype == "KO"


def test_duplicate_div_is_collapsed_and_single_div_chains_dropped():
    chains = build_chains([
        "OPME1_20230101_P1_pup1A_WT_MOI1_DIV10",
        "OPME1_20230108_P1_pup1A_WT_MOI1_DIV17",
        "OPME1_20230108_P1_pup1A_WT_MOI1_DIV17",   # duplicate share
        "OPME2_20230101_P1_pup2A_WT_MOI1_DIV10",   # only one DIV
    ])
    assert len(chains) == 1
    (chain,) = chains.values()
    assert chain.divs == [10, 17]


def test_recording_without_a_div_is_ignored_not_fatal():
    assert build_chains(["IFanalysisScripts", "notes.csv"]) == {}


# ── the displacement estimator ────────────────────────────────────────────────

def test_displacement_recovers_a_known_shift_and_its_sign():
    rng = np.random.default_rng(0)
    centres = rng.integers(20, 236, size=(40, 2))
    a = density_map(_rois(centres), 256)
    shifted = centres + np.array([24, -16])
    b = density_map(_rois(shifted), 256)

    dy, dx, _pz, ncc = displacement(a, b)
    # b is brought into a's frame by ADDING (dy, dx), so the offset b sits at
    # relative to a is -(dy, dx)
    assert (-dy, -dx) == pytest.approx((24, -16), abs=8)
    assert ncc > 0.8


def test_aligned_ncc_separates_same_field_from_unrelated():
    rng = np.random.default_rng(1)
    centres = rng.integers(20, 236, size=(40, 2))
    same = density_map(_rois(centres + np.array([8, 8])), 256)
    other = density_map(_rois(rng.integers(20, 236, size=(40, 2))), 256)
    base = density_map(_rois(centres), 256)

    assert displacement(base, same)[3] > displacement(base, other)[3]


# ── the offset solve ──────────────────────────────────────────────────────────

def test_solve_offsets_puts_sessions_in_one_frame():
    rng = np.random.default_rng(2)
    centres = rng.integers(30, 226, size=(50, 2))
    truth = [np.array([0, 0]), np.array([24, 0]), np.array([0, -24])]
    maps = [density_map(_rois(centres + t), 256) for t in truth]

    offsets = solve_offsets(maps)
    residual = verify_offsets(maps, offsets.offsets)
    assert residual["median_after_px"] < residual["median_before_px"]
    assert residual["median_after_px"] <= 8.0


def test_an_unrelated_session_does_not_drag_the_others():
    """A different field of view must not constrain the solve.

    Plain least squares over all pairs let exactly this move a chain from a
    12 px offset to 89 px.
    """
    rng = np.random.default_rng(3)
    centres = rng.integers(30, 226, size=(50, 2))
    maps = [
        density_map(_rois(centres), 256),
        density_map(_rois(centres + np.array([24, 0])), 256),
        density_map(_rois(rng.integers(30, 226, size=(50, 2))), 256),  # foreign
    ]
    offsets = solve_offsets(maps)
    # the two real sessions still land within a bin of each other
    solved_gap = offsets.offsets[1] - offsets.offsets[0]
    assert abs(abs(solved_gap[0]) - 24) <= 8
    assert abs(solved_gap[1]) <= 8


def test_gate_leaves_an_already_aligned_chain_alone():
    rng = np.random.default_rng(4)
    centres = rng.integers(30, 226, size=(50, 2))
    maps = [density_map(_rois(centres), 256),
            density_map(_rois(centres), 256)]
    assert solve_offsets(maps).should_register() is False


def test_gate_catches_one_drifted_session_among_aligned_ones():
    """One session 24 px off in a four-session chain.

    Three of the six pairs measure the drift and three measure 0, so a median
    over pairs lands between them and passes the chain through -- which is how
    a real DIV21 was left 20 px off and matched nothing. The gate must look at
    the largest reliable pair.
    """
    rng = np.random.default_rng(5)
    centres = rng.integers(30, 226, size=(50, 2))
    maps = [density_map(_rois(centres + t), 256)
            for t in ([0, 0], [0, 0], [0, 0], [24, 0])]
    offsets = solve_offsets(maps)
    assert offsets.median_shift_px < 16.0          # the trap
    assert offsets.max_session_shift_px >= 16.0
    assert offsets.should_register() is True
    # the three aligned sessions stay put; only the drifted one moves
    assert [tuple(o) for o in offsets.offsets[:3]] == [(0, 0)] * 3
    assert abs(offsets.offsets[3][0] - 24) <= 8


def test_a_single_wobbly_pair_does_not_register_an_aligned_chain(monkeypatch):
    """Three sessions; one pair measured two bins off, the other two pairs
    measured 0. That is quantisation noise, not a drift: the solve spreads it
    and no session ends up two bins from the majority. Gating on the largest
    *pair* would register the chain and nudge every session."""
    from meanap.catnap.tracking import register
    from meanap.catnap.tracking.register import PairMeasurement

    wobbly = [PairMeasurement(0, 1, 16.0, 0.0, 20.0, 0.8),
              PairMeasurement(0, 2, 0.0, 0.0, 20.0, 0.8),
              PairMeasurement(1, 2, 0.0, 0.0, 20.0, 0.8)]
    monkeypatch.setattr(register, "measure_pairs", lambda maps, bin_px: wobbly)
    offsets = solve_offsets([np.zeros((4, 4))] * 3)
    assert max(p.shift_px for p in offsets.pairs) >= 16.0
    assert offsets.max_session_shift_px < 16.0
    assert offsets.should_register() is False


def test_sessions_below_the_gate_keep_their_solved_offset(monkeypatch):
    """One session 24 px off, another 8 px off: the chain registers, and the
    8 px session keeps its solved offset. Zeroing sub-gate sessions was tried
    and cost matches on 19 of the 25 chains it touched -- the small solved
    components carry real sub-bin information."""
    from meanap.catnap.tracking import register
    from meanap.catnap.tracking.register import PairMeasurement

    # sessions at 0, 0, 24 and 8 px along y
    truth = [0.0, 0.0, 24.0, 8.0]
    measured = [PairMeasurement(i, j, truth[j] - truth[i], 0.0, 20.0, 0.8)
                for i in range(4) for j in range(i + 1, 4)]
    monkeypatch.setattr(register, "measure_pairs", lambda maps, bin_px: measured)
    offsets = solve_offsets([np.zeros((4, 4))] * 4)
    assert offsets.should_register() is True
    assert offsets.offsets.tolist() == [[0, 0], [0, 0], [-24, 0], [-8, 0]]


def test_gate_ignores_offsets_measured_on_different_fields():
    """Two unrelated fields have no offset to correct, however large the
    correlation peak's position. Registering them would switch ROICaT's own
    alignment off in exchange for all-zero offsets."""
    rng = np.random.default_rng(6)
    maps = [density_map(_rois(rng.integers(30, 226, size=(50, 2))), 256),
            density_map(_rois(rng.integers(30, 226, size=(50, 2))), 256)]
    offsets = solve_offsets(maps)
    assert all(p.aligned_ncc < offsets.reliable_ncc for p in offsets.pairs)
    assert offsets.max_session_shift_px == 0.0
    assert offsets.should_register() is False


# ── staging ───────────────────────────────────────────────────────────────────

def test_padded_canvas_keeps_every_roi():
    offsets = np.array([[0, 0], [24, -16], [-8, 8]])
    height, width, pad_y, pad_x = padded_frame(offsets, 256)
    stat = _rois([(10, 10), (250, 250), (128, 128)], frame=256)
    for off in offsets:
        moved = shift_stat(stat, int(off[0]), int(off[1]), pad_y, pad_x, (height, width))
        assert len(moved) == len(stat), "padding should mean nothing is clipped"


# ── validation ────────────────────────────────────────────────────────────────

def test_a_nan_trace_does_not_poison_the_other_cells():
    """One bad row used to NaN a whole correlation matrix, costing 51.7% of cells."""
    rng = np.random.default_rng(5)
    F = rng.normal(size=(6, 400))
    F[2] = np.nan          # a silent cell, as OASIS used to leave them
    F[3] = 1.0             # flat
    session = reduce_session(F, rng.normal(size=(6, 2)))

    good = [0, 1, 4, 5]
    assert np.isfinite(session.corr[np.ix_(good, good)]).all()
    assert np.isnan(session.corr[2]).all()
    assert np.isfinite(session.pop_coupling[good]).all()


def test_zscore_rows_flags_degenerate_rows():
    F = np.vstack([np.arange(10.0), np.full(10, 3.0), np.full(10, np.nan)])
    _, ok = _zscore_rows(F)
    assert ok.tolist() == [True, False, False]


def test_auc_is_oriented_so_above_half_favours_the_match():
    assert auc_vs_null([0.9, 0.8, 0.7], [0.1, 0.2, 0.3]) == pytest.approx(1.0)
    assert auc_vs_null([0.1, 0.2, 0.3], [0.9, 0.8, 0.7]) == pytest.approx(0.0)
    assert auc_vs_null([], [0.1]) != auc_vs_null([], [0.1])   # nan


def test_neuropil_correction_uses_suite2p_convention():
    F = np.array([[10.0, 20.0]])
    Fneu = np.array([[10.0, 10.0]])
    got = correct_neuropil(F, Fneu, neucoeff=0.7)
    assert got.ravel().tolist() == pytest.approx([3.0, 13.0])


def test_event_metrics_ignore_nan_padding():
    peaks = np.array([[0.0, 30.0, 60.0, np.nan], [np.nan] * 4])
    rate, iei = event_metrics(peaks, n_frames=1800, fs=30.0)
    assert rate[0] == pytest.approx(3.0)      # 3 events in one minute
    assert rate[1] == 0.0
    assert iei[0] == pytest.approx(1.0)       # 30 frames at 30 Hz
    assert np.isnan(iei[1])


# ── controls ──────────────────────────────────────────────────────────────────

def test_roi_shift_control_drops_rois_that_leave_the_frame():
    stat = _rois([(10, 10), (128, 128)], frame=256)
    moved = roi_shift_control(stat, -40, 0, frame_px=256)
    assert len(moved) == 1, "the ROI shifted off the top should be dropped"


def test_floor_summary_warns_when_there_are_too_few_pairs():
    assert "warning" in summarise_floor([0.0, 0.04])
    many = summarise_floor([0.0, 0.02, 0.09] * 5)
    assert "warning" not in many
    assert many["recommended_threshold"] >= many["max"]


# ── viewer ────────────────────────────────────────────────────────────────────

def test_viewer_orders_worst_first_and_unscored_counts_as_worst():
    cards = [CellCard(cluster=i, divs=[1], crops=[], traces=[], metrics=[],
                      fingerprint=v)
             for i, v in enumerate([0.9, 0.2, float("nan"), 0.5])]
    order = [c.fingerprint for c in select_cards(cards, 4)]
    assert np.isnan(order[0])
    assert order[1:] == [0.2, 0.5, 0.9]
    # 0 = no cap: every cell gets a card, still worst first
    assert len(select_cards(cards, 0)) == 4
    assert len(select_cards(cards, 2)) == 2


# ── data source ───────────────────────────────────────────────────────────────

def test_local_source_resolves_plane0_directly(tmp_path):
    from meanap.catnap.tracking.source import LocalSessionSource

    src = LocalSessionSource(raw_data=tmp_path)
    assert src.plane0("rec1") == tmp_path / "rec1" / "suite2p" / "plane0"


def test_source_delegates_to_a_recording_source_when_given_one(tmp_path):
    """A remote dataset reaches tracking through RecordingSource.plane0()."""
    from meanap.catnap.tracking.source import LocalSessionSource

    calls = []

    class FakeRemote:
        def plane0(self, recording):
            calls.append(("plane0", recording))
            return tmp_path / "fetched" / recording
        def unpin(self, recording):
            calls.append(("unpin", recording))
        def release(self, recording):
            calls.append(("release", recording))

    src = LocalSessionSource(raw_data=tmp_path / "unused", source=FakeRemote())
    assert src.plane0("rec1") == tmp_path / "fetched" / "rec1"
    src.release("rec1")
    assert calls == [("plane0", "rec1"), ("unpin", "rec1"), ("release", "rec1")]


def test_release_is_a_no_op_without_a_remote_source(tmp_path):
    from meanap.catnap.tracking.source import LocalSessionSource

    LocalSessionSource(raw_data=tmp_path).release("rec1")   # must not raise


def test_iscell_length_mismatch_is_reported_not_silently_wrong(tmp_path):
    """One folder in the Mecp2 share has iscell longer than stat."""
    from meanap.catnap.tracking.source import LocalSessionSource

    plane = tmp_path / "rec1" / "suite2p" / "plane0"
    plane.mkdir(parents=True)
    np.save(plane / "stat.npy", np.array([{"ypix": np.array([0])}] * 3, dtype=object),
            allow_pickle=True)
    np.save(plane / "iscell.npy", np.ones((5, 2)))

    with pytest.raises(ValueError, match="stat has 3 ROIs, iscell has 5"):
        LocalSessionSource(raw_data=tmp_path).stat("rec1")


def test_missing_fneu_falls_back_and_says_so(tmp_path):
    """A remote run without Fneu must not silently mix corrected traces."""
    from meanap.catnap.tracking.source import LocalSessionSource

    plane = tmp_path / "rec1" / "suite2p" / "plane0"
    plane.mkdir(parents=True)
    np.save(plane / "iscell.npy", np.ones((2, 2)))
    np.save(plane / "ops.npy", {"fs": 30.0, "Ly": 8, "Lx": 8,
                                "meanImg": np.zeros((8, 8))}, allow_pickle=True)
    np.save(plane / "Fdenoised.npy", np.ones((2, 50)))

    src = LocalSessionSource(raw_data=tmp_path)
    traces, fs = src.traces("rec1")
    assert traces.shape == (2, 50) and fs == 30.0
    assert "rec1" in src.uncorrected, "the fallback must be recorded, not silent"


def test_fneu_is_used_when_present(tmp_path):
    from meanap.catnap.tracking.source import LocalSessionSource

    plane = tmp_path / "rec1" / "suite2p" / "plane0"
    plane.mkdir(parents=True)
    np.save(plane / "iscell.npy", np.ones((1, 2)))
    np.save(plane / "ops.npy", {"fs": 30.0, "Ly": 8, "Lx": 8,
                                "meanImg": np.zeros((8, 8))}, allow_pickle=True)
    np.save(plane / "F.npy", np.full((1, 4), 10.0))
    np.save(plane / "Fneu.npy", np.full((1, 4), 10.0))

    src = LocalSessionSource(raw_data=tmp_path)
    traces, _ = src.traces("rec1", neucoeff=0.7)
    assert traces.ravel().tolist() == pytest.approx([3.0] * 4)
    assert not src.uncorrected


# ── quality ───────────────────────────────────────────────────────────────────

def test_percentile_orientation_follows_the_metric():
    from meanap.catnap.tracking.quality import percentile_of

    pool = np.array([1.0, 2.0, 3.0, 4.0])
    # higher is better: a big value beats most of the pool
    assert percentile_of(3.5, pool, higher_is_better=True) == pytest.approx(75.0)
    # lower is better: the same big value is now worse
    assert percentile_of(3.5, pool, higher_is_better=False) == pytest.approx(25.0)


def test_spatial_metrics_are_marked_as_not_independent():
    """Centroid shift separates well and proves nothing — it must be labelled."""
    from meanap.catnap.tracking.quality import METRIC_SPECS

    by_key = {s["key"]: s for s in METRIC_SPECS}
    assert by_key["centroid_shift"]["independent"] is False
    assert by_key["fingerprint"]["independent"] is True


def test_chain_quality_warns_about_unusable_separability():
    from meanap.catnap.tracking.quality import chain_quality

    q = chain_quality("c", fingerprint_auc=0.51, pair_rates=[0.3],
                      cluster_spans=[2, 2, 3], n_sessions=3,
                      residual_shift_px=2.0, n_fingerprints=500)
    assert any("barely separate" in w for w in q.warnings)
    assert q.persistence == pytest.approx(1 / 3)


def test_chain_quality_is_a_vector_not_a_single_number():
    """A composite was measured to add nothing (0.685 vs 0.681)."""
    from meanap.catnap.tracking.quality import ChainQuality

    fields = set(ChainQuality.__dataclass_fields__)
    assert {"separability", "coverage", "persistence", "residual_shift_px"} <= fields
    assert not any(f in fields for f in ("score", "overall", "composite"))


def test_payload_carries_data_not_pictures(tmp_path):
    """The page embeds arrays so plots stay sharp and selection is instant."""
    from meanap.catnap.tracking.viewer import (CellCard, SessionView,
                                               build_payload, mean_image_png)

    rng = np.random.default_rng(0)
    view = SessionView(div=14, mean_png=mean_image_png(rng.random((64, 64))),
                       centroids=rng.random((5, 2)) * 64,
                       cluster_of=np.array([0, 1, -1, -1, 2]))
    card = CellCard(cluster=0, divs=[14], crops=[rng.random((6, 6))],
                    traces=[rng.random(9000)], metrics=[{"rate": 2.0, "pop": 0.3}],
                    fingerprint=0.4, percentile=70.0, positions=[(0, 5.0, 7.0)])
    payload = build_payload("c", "s", [card], 30.0, [view],
                            {"fingerprint": {"null": rng.random(80),
                                             "matched": rng.random(80)}})
    assert payload["sessions"][0]["cluster"] == [0, 1, -1, -1, 2]
    assert payload["cells"][0]["positions"] == [[0, 5.0, 7.0]]
    # a quantile summary on a shared scale, not the raw pool
    pool = payload["pools"]["fingerprint"]
    assert len(pool["q"]["null"]) == 7 and len(pool["q"]["matched"]) == 7
    assert pool["lo"] < pool["hi"]


def test_traces_are_decimated_keeping_peaks():
    from meanap.catnap.tracking.viewer import TRACE_POINTS, _decimate

    trace = np.zeros(20000)
    trace[12345] = 9.0          # a single event must survive the shrink
    out = _decimate(trace)
    assert out.size == TRACE_POINTS
    assert out.max() == pytest.approx(9.0)


def test_distributions_share_a_scale_between_null_and_matched():
    """Separately-scaled summaries cannot be read against each other."""
    from meanap.catnap.tracking.viewer import QUANTILES, _distribution

    rng = np.random.default_rng(0)
    dist = _distribution({"null": rng.normal(0.2, 0.2, 400),
                          "matched": rng.normal(0.6, 0.2, 400)})
    assert len(dist["q"]["null"]) == len(QUANTILES)
    # the matched median sits above the null median, on one shared scale
    assert dist["q"]["matched"][3] > dist["q"]["null"][3]
    assert dist["nullN"] == 400


def test_small_pools_are_dropped_rather_than_summarised():
    from meanap.catnap.tracking.viewer import build_payload

    payload = build_payload("c", "s", [], 30.0, [],
                            {"fingerprint": {"null": np.array([0.1, 0.2])}})
    assert "fingerprint" not in payload["pools"]


def test_exactly_one_registration_happens(tmp_path):
    """Pre-registered chains disable ROICaT; gated-out chains must not.

    Disabling ROICaT on a chain we deliberately left unregistered removes the
    only correction available and cost one chain 0.36 -> 0.06.
    """
    pytest.importorskip("roicat")
    from meanap.catnap.tracking.roicat import build_params

    pre = build_params(tmp_path, tmp_path, "c", pre_registered=True)
    assert pre["alignment"]["fit_geometric"]["method"] == "NullRegistration"
    assert pre["alignment"]["fit_nonrigid"]["method"] == "NullRegistration"

    passed = build_params(tmp_path, tmp_path, "c", pre_registered=False)
    assert passed["alignment"]["fit_nonrigid"]["method"] != "NullRegistration"


# ── completion ────────────────────────────────────────────────────────────────

def _three_days(cluster_at, extra):
    """Two days with a cluster at ``cluster_at``, a third day with ``extra``
    unmatched cells at the given positions. Returns (labels, centroids)."""
    labels = [np.array([0, -1]), np.array([0, -1]), np.full(len(extra), -1)]
    centroids = [np.array([cluster_at, [200.0, 200.0]]),
                 np.array([cluster_at, [200.0, 200.0]]),
                 np.array(extra, dtype=float)]
    return labels, centroids


def test_completion_adds_the_one_unmatched_cell_where_the_cluster_should_be():
    labels, centroids = _three_days([50.0, 50.0], [[54.0, 52.0], [200.0, 200.0]])
    new, rescues = complete_clusters(labels, centroids, radius_px=10.0)
    assert new[2].tolist() == [0, -1]
    assert [(r.cluster, r.session, r.roi) for r in rescues] == [(0, 2, 0)]
    assert rescues[0].dist_px == pytest.approx(np.hypot(4, 2))
    assert labels[2].tolist() == [-1, -1]        # inputs untouched


def test_completion_refuses_when_two_cells_are_both_close():
    """Two unmatched cells within the radius and no way to choose: leave it."""
    labels, centroids = _three_days([50.0, 50.0], [[54.0, 52.0], [47.0, 45.0]])
    new, rescues = complete_clusters(labels, centroids, radius_px=10.0)
    assert new[2].tolist() == [-1, -1]
    assert rescues == []


def test_completion_refuses_a_cell_two_clusters_want():
    labels = [np.array([0, 1]), np.array([0, 1]), np.array([-1])]
    centroids = [np.array([[50.0, 50.0], [56.0, 56.0]]),
                 np.array([[50.0, 50.0], [56.0, 56.0]]),
                 np.array([[53.0, 53.0]])]
    new, rescues = complete_clusters(labels, centroids, radius_px=10.0)
    assert new[2].tolist() == [-1]
    assert rescues == []


def test_completion_never_reassigns_a_matched_cell_or_grows_a_singleton():
    # day 2's cell at the cluster position already belongs to cluster 1
    labels = [np.array([0]), np.array([0]), np.array([1]), np.array([1, -1])]
    centroids = [np.array([[50.0, 50.0]])] * 3 + [np.array([[50.0, 50.0], [300.0, 300.0]])]
    new, rescues = complete_clusters(labels, centroids, radius_px=10.0)
    assert [l.tolist() for l in new] == [[0], [0], [1], [1, -1]]
    assert rescues == []


def test_completion_respects_the_radius():
    labels, centroids = _three_days([50.0, 50.0], [[62.0, 50.0]])
    assert complete_clusters(labels, centroids, radius_px=10.0)[1] == []
    assert len(complete_clusters(labels, centroids, radius_px=14.0)[1]) == 1


def _split(pos_b, other_days=(2, 3)):
    """Cluster 0 on days 0-1 at (50, 50); cluster 1 on ``other_days`` at
    ``pos_b``; a far cell 5 everywhere."""
    labels = [np.array([0, 5]), np.array([0, 5]), np.array([-1, 5]), np.array([-1, 5])]
    for d in other_days:
        labels[d][0] = 1
    centroids = [np.array([[50.0, 50.0], [300.0, 300.0]])] * 2 + \
                [np.array([pos_b, [300.0, 300.0]], dtype=float)] * 2
    return labels, centroids


def test_split_clusters_on_disjoint_days_are_joined():
    labels, centroids = _split([53.0, 54.0])
    new, merges = merge_split_clusters(labels, centroids, radius_px=10.0)
    assert [(m.cluster, m.absorbed) for m in merges] == [(0, 1)]
    assert merges[0].dist_px == pytest.approx(5.0)
    assert [l[0] for l in new] == [0, 0, 0, 0]
    assert labels[2][0] == 1                    # inputs untouched


def test_clusters_sharing_a_day_are_two_cells_not_one():
    labels, centroids = _split([53.0, 54.0], other_days=(1, 2))
    new, merges = merge_split_clusters(labels, centroids, radius_px=10.0)
    assert merges == []
    assert [l.tolist() for l in new] == [l.tolist() for l in labels]


def test_a_cluster_with_two_candidate_partners_is_left_alone():
    # clusters 1 and 2 both on days 2-3, both within radius of cluster 0
    labels = [np.array([0]), np.array([0]), np.array([1, 2]), np.array([1, 2])]
    centroids = [np.array([[50.0, 50.0]])] * 2 + [np.array([[53.0, 50.0], [50.0, 53.0]])] * 2
    new, merges = merge_split_clusters(labels, centroids, radius_px=10.0)
    assert merges == []


def test_merge_respects_the_radius():
    labels, centroids = _split([62.0, 50.0])
    assert merge_split_clusters(labels, centroids, radius_px=10.0)[1] == []
    assert len(merge_split_clusters(labels, centroids, radius_px=14.0)[1]) == 1


def test_reused_clusters_must_come_from_the_same_gate_decision(tmp_path):
    """A passed-through chain's clusters describe unshifted coordinates; a
    registered chain's describe staged ones. Never mix them."""
    from meanap.catnap.tracking.pipeline import _reuse_clusters

    runs = tmp_path / "work" / "runs"          # <run>/work/runs, beside <run>/chains
    (runs / "c").mkdir(parents=True)
    (runs / "c" / "c.tracking.results_clusters.json").write_text(
        json.dumps({"labels_bySession": [[0, -1], [0, 1]]}))
    (runs / "c" / "c.tracking.params_used.json").write_text(
        json.dumps({"aligner": {"fit_geometric": {"method": "NullRegistration"}}}))

    dest = tmp_path / "new" / "c"
    assert _reuse_clusters(runs, dest, "c", pre_registered=False) is None
    got = _reuse_clusters(runs, dest, "c", pre_registered=True)
    assert got == {"labels_bySession": [[0, -1], [0, 1]]}
    assert (dest / "c.tracking.results_clusters.json").exists()
    assert _reuse_clusters(runs, dest, "missing", pre_registered=True) is None

    # with the earlier chain result beside it, the staged geometry must agree
    # up to a common translation, which the matcher cannot see
    (tmp_path / "chains").mkdir()
    (tmp_path / "chains" / "c.json").write_text(json.dumps({"offsets": [[0, 0], [24, 0]]}))
    assert _reuse_clusters(runs, dest, "c", pre_registered=True,
                           offsets=[[-8, 0], [16, 0]]) is not None
    assert _reuse_clusters(runs, dest, "c", pre_registered=True,
                           offsets=[[0, 0], [16, 0]]) is None


def test_viewer_js_render_path_executes(tmp_path):
    """Run the page's JavaScript against a DOM shim.

    The payload can be perfectly well-formed while the rendering code throws —
    it did, on a race where a cached image's onload fired before its canvas was
    registered. Structure tests do not catch that; executing it does.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")

    from meanap.catnap.tracking.viewer import (CellCard, SessionView,
                                               build_payload, mean_image_png)

    rng = np.random.default_rng(0)
    sessions = [SessionView(div=d, mean_png=mean_image_png(rng.random((64, 64))),
                            centroids=rng.random((12, 2)) * 1280,
                            cluster_of=np.array([0, 1, 2] + [-1] * 9))
                for d in (14, 21)]
    cards = [CellCard(cluster=c, divs=[14, 21],
                      crops=[rng.random((7, 7)), rng.random((7, 7))],
                      traces=[rng.random(5000), rng.random(5000)],
                      metrics=[{"rate": 2.0, "pop": 0.3}] * 2,
                      fingerprint=0.1 * c, percentile=10.0 * c,
                      positions=[(0, 5.0, 7.0), (1, 6.0, 8.0)])
             for c in range(3)]
    payload = build_payload("c", "s", cards, 30.0, sessions,
                            {"fingerprint": {"null": rng.random(60),
                                             "matched": rng.random(60)}})
    payload["frame"] = 1280

    js_dir = Path(__file__).resolve().parent / "js"
    from meanap.catnap.tracking import viewer as v
    (tmp_path / "viewer.js").write_text(v._JS)
    (tmp_path / "payload.json").write_text(json.dumps(payload))

    script = f"""
      const {{calls}} = require({str(js_dir / 'viewer_dom_shim.js')!r});
      const fs = require('fs');
      global.window.__TRACK__ = JSON.parse(fs.readFileSync({str(tmp_path / 'payload.json')!r}));
      const src = fs.readFileSync({str(tmp_path / 'viewer.js')!r}, 'utf8');
      const api = new Function(src + '; return {{buildFov, applyFilter, select, order}};')();
      api.buildFov(); api.applyFilter();
      api.select(0); api.select(api.order.length - 1);
      if (calls.putImageData === 0) throw new Error('no footprints drawn');
      if (calls.arcs === 0) throw new Error('no ROIs drawn on the field of view');
      console.log('OK');
    """
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[:600]
    assert "OK" in result.stdout


def test_fov_click_picks_the_nearest_cell_that_has_a_card(tmp_path):
    """Only the cells with cards can be selected. Picking the nearest *tracked*
    cell made most clicks on a big chain do nothing, because the nearest one
    had no card; and a click far from any card must not jump the selection."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")

    from meanap.catnap.tracking.viewer import (CellCard, SessionView,
                                               build_payload, mean_image_png)

    rng = np.random.default_rng(0)
    # clusters 0-2 have cards; cluster 7 is tracked but has none, and sits
    # right next to where the click lands
    centroids = np.array([[100, 100], [1000, 1000], [500, 500], [520, 520],
                          [300, 900]], dtype=float)
    sessions = [SessionView(div=d, mean_png=mean_image_png(rng.random((64, 64))),
                            centroids=centroids,
                            cluster_of=np.array([0, 1, 2, 7, -1]))
                for d in (14, 21)]
    cards = [CellCard(cluster=c, divs=[14, 21],
                      crops=[rng.random((7, 7))] * 2, traces=[rng.random(500)] * 2,
                      metrics=[{"rate": 2.0, "pop": 0.3}] * 2,
                      fingerprint=0.1 * c, percentile=10.0 * c,
                      positions=[(0, 5.0, 7.0), (1, 6.0, 8.0)])
             for c in range(3)]
    payload = build_payload("c", "s", cards, 30.0, sessions, {})
    payload["frame"] = 1280

    js_dir = Path(__file__).resolve().parent / "js"
    from meanap.catnap.tracking import viewer as v
    (tmp_path / "viewer.js").write_text(v._JS)
    (tmp_path / "payload.json").write_text(json.dumps(payload))

    script = f"""
      require({str(js_dir / 'viewer_dom_shim.js')!r});
      const fs = require('fs');
      global.window.__TRACK__ = JSON.parse(fs.readFileSync({str(tmp_path / 'payload.json')!r}));
      const src = fs.readFileSync({str(tmp_path / 'viewer.js')!r}, 'utf8');
      const api = new Function(src + '; return {{buildFov, applyFilter, select, pickFromFov, cells, order, current: () => cells[order[sel]].cluster}};')();
      api.buildFov(); api.applyFilter();
      const size = 300, k = size / 1280;           // canvas px per frame px at 1x
      const ev = (fx, fy) => ({{clientX: fx * k, clientY: fy * k,
                                target: {{getBoundingClientRect: () => ({{left: 0, top: 0}})}}}});
      api.select(0);
      api.pickFromFov(0, ev(522, 522), size);      // nearest tracked is 7 (no card); nearest card is 2
      if (api.current() !== 2) throw new Error('expected cluster 2, got ' + api.current());
      api.pickFromFov(0, ev(1270, 10), size);      // nothing with a card anywhere near
      if (api.current() !== 2) throw new Error('a far click moved the selection to ' + api.current());
      api.pickFromFov(0, ev(1010, 990), size);     // generous: 14 frame px off cluster 1
      if (api.current() !== 1) throw new Error('expected cluster 1, got ' + api.current());
      console.log('OK');
    """
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[:600]
    assert "OK" in result.stdout


# ── bundle + viewer ───────────────────────────────────────────────────────────

def _fake_tracking_output(root: Path) -> None:
    """A CellTracking folder shaped like a real run's."""
    from meanap.catnap.tracking.viewer import (CellCard, SessionView,
                                               build_payload, mean_image_png)

    rng = np.random.default_rng(0)
    ct = root / "CellTracking"
    (ct / "payload").mkdir(parents=True)
    (ct / "chains").mkdir(parents=True)
    (ct / "viewer").mkdir(parents=True)
    (ct / "work" / "staged").mkdir(parents=True)

    sessions = [SessionView(div=d, mean_png=mean_image_png(rng.random((48, 48))),
                            centroids=rng.random((5, 2)) * 1280,
                            cluster_of=np.array([0, 1, -1, -1, 2])) for d in (14, 21)]
    cards = [CellCard(cluster=0, divs=[14, 21],
                      crops=[rng.random((5, 5))] * 2, traces=[rng.random(2000)] * 2,
                      metrics=[{"rate": 1.0, "pop": 0.2}] * 2,
                      fingerprint=0.4, percentile=70.0,
                      positions=[(0, 5.0, 7.0), (1, 6.0, 8.0)])]
    payload = build_payload("chainA", "sub", cards, 30.0, sessions,
                            {"fingerprint": {"null": rng.random(40),
                                             "matched": rng.random(40)}})
    payload["frame"] = 1280
    (ct / "payload" / "chainA.json").write_text(json.dumps(payload))
    (ct / "chains" / "chainA.json").write_text(json.dumps({
        "chain": "chainA", "divs": [14, 21], "genotype": "WT", "prep": "OPME1",
        "registered": True, "measured_shift_px": 24.0,
        "quality": {"separability": 0.7, "coverage": 0.3, "persistence": 0.5,
                    "warnings": ["only 32 fingerprints — separability is noisy here"]},
    }))
    (ct / "summary.json").write_text(json.dumps({"chains": 1, "usable_chains": 1}))
    (ct / "viewer" / "chainA.html").write_text("<html>rendered</html>")
    (ct / "work" / "staged" / "big.npy").write_bytes(b"0" * 5000)


def test_bundle_carries_tracking_data_but_not_pages_or_workdir(tmp_path):
    from meanap.pipeline.bundle import _is_reconstructable_member as skipped

    _fake_tracking_output(tmp_path)
    assert skipped(Path("CellTracking/work/staged/big.npy"))
    assert skipped(Path("CellTracking/viewer/chainA.html"))
    assert not skipped(Path("CellTracking/payload/chainA.json"))
    assert not skipped(Path("CellTracking/chains/chainA.json"))
    assert not skipped(Path("CellTracking/summary.json"))


def test_viewer_lists_chains_by_separability_not_match_rate(tmp_path):
    from meanap.viewer.server import ViewerService

    _fake_tracking_output(tmp_path)
    svc = ViewerService.__new__(ViewerService)
    svc._bundle = None
    svc.source = tmp_path
    listing = svc.tracking()
    assert listing["available"] is True
    (chain,) = listing["chains"]
    assert chain["chain"] == "chainA"
    assert chain["separability"] == 0.7
    assert chain["registered"] is True
    assert chain["warnings"]


def test_viewer_rebuilds_the_page_from_the_stored_payload(tmp_path):
    from meanap.viewer.server import ViewerService

    _fake_tracking_output(tmp_path)
    svc = ViewerService.__new__(ViewerService)
    svc._bundle = None
    svc.source = tmp_path
    html_out = svc.tracking_page("chainA")
    assert "__TRACK__" in html_out          # the data went in
    assert "field of view" in html_out      # and the page around it


def test_tracking_payload_rejects_a_path_outside_the_folder(tmp_path):
    from meanap.viewer.server import ViewerService

    _fake_tracking_output(tmp_path)
    svc = ViewerService.__new__(ViewerService)
    svc._bundle = None
    svc.source = tmp_path
    with pytest.raises(FileNotFoundError):
        svc.tracking_payload("../../etc/passwd")


def test_viewer_says_nothing_available_without_tracking(tmp_path):
    from meanap.viewer.server import ViewerService

    svc = ViewerService.__new__(ViewerService)
    svc._bundle = None
    svc.source = tmp_path
    assert svc.tracking() == {"available": False, "chains": []}


def test_tracking_overview_aggregates_chains_and_pairs(tmp_path):
    from meanap.viewer.server import ViewerService

    _fake_tracking_output(tmp_path)
    # give the fake chain some day-pairs to aggregate
    meta_path = tmp_path / "CellTracking" / "chains" / "chainA.json"
    meta = json.loads(meta_path.read_text())
    meta["pairwise"] = {"DIV14-DIV21": {"frac_of_smaller": 0.3, "div_gap": 7,
                                        "shared": 4}}
    meta_path.write_text(json.dumps(meta))

    svc = ViewerService.__new__(ViewerService)
    svc._bundle = None
    svc.source = tmp_path
    o = svc.tracking_overview()
    assert o["available"] is True
    (chain,) = o["chains"]
    assert chain["separability"] == 0.7 and chain["medianMatch"] == 0.3
    (pair,) = o["pairs"]
    assert pair["divGap"] == 7 and pair["rate"] == 0.3


def test_overview_plots_render(tmp_path):
    """Run the viewer page's overview renderer against a DOM shim.

    Four panels, each with data points — a structure test would pass on a
    renderer that silently drew nothing.
    """
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")

    from meanap.viewer.page import PAGE_HTML
    from meanap.viewer.server import ViewerService

    _fake_tracking_output(tmp_path)
    meta_path = tmp_path / "CellTracking" / "chains" / "chainA.json"
    meta = json.loads(meta_path.read_text())
    meta["pairwise"] = {f"DIV14-DIV{d}": {"frac_of_smaller": 0.1 * i, "div_gap": d,
                                          "shared": 3}
                        for i, d in enumerate((21, 28, 35), start=1)}
    meta_path.write_text(json.dumps(meta))

    svc = ViewerService.__new__(ViewerService)
    svc._bundle = None
    svc.source = tmp_path
    (tmp_path / "overview.json").write_text(json.dumps(svc.tracking_overview()))

    m = re.search(r"(let TRACKING = null, TRACK_OVERVIEW = null;.*?)\nfunction download\(",
                  PAGE_HTML, re.S)
    assert m, "overview renderer not found in the page"
    (tmp_path / "overview.js").write_text(m.group(1))

    shim = Path(__file__).resolve().parent / "js" / "overview_dom_shim.js"
    script = f"""
      const {{calls, reg}} = require({str(shim)!r});
      const fs = require('fs');
      global.getJSON = async () => JSON.parse(
        fs.readFileSync({str(tmp_path / 'overview.json')!r}, 'utf8'));
      const src = fs.readFileSync({str(tmp_path / 'overview.js')!r}, 'utf8');
      new Function('return (async()=>{{' + src + '; await showTrackingOverview();}})()')()
        .then(() => {{
          const grid = reg['tracking'].children[0];
          if (!grid || grid.children.length !== 4) throw new Error('expected 4 panels');
          if (calls.circles === 0) throw new Error('no data points drawn');
          console.log('OK');
        }})
        .catch(e => {{ console.error(e.message); process.exit(1); }});
    """
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[:600]
    assert "OK" in result.stdout


def test_tracking_survives_a_bundle_round_trip(tmp_path):
    """Pack a run with tracking, reopen it as a bundle, rebuild the page.

    The earlier service tests bypass ``ViewerService.__init__``; this one goes
    through it, so it covers loading a real manifest and reading the payload
    back out of the zip rather than off disk.
    """
    import json as _json

    from meanap.pipeline.bundle import write_bundle
    from meanap.viewer.server import ViewerService

    # a minimal but real output folder: the viewer refuses one without step-4
    # results, so the fixture has to carry them
    (tmp_path / "ExperimentMatFiles").mkdir()
    (tmp_path / "4_NetworkActivity").mkdir()
    (tmp_path / "4_NetworkActivity" / "netmet_results.json").write_text(
        _json.dumps({"rec1": {"25mslag": {}}}))
    (tmp_path / "params.json").write_text("{}")
    manifest = {"format": 1, "mode": "catnap", "express": True, "lags": [25],
                "recordings": [{"filename": "rec1", "group": "WT", "div": 21}],
                "reconstructable": [], "not_reconstructable": [],
                "embedded_figures": []}
    (tmp_path / "manifest.json").write_text(_json.dumps(manifest))
    _fake_tracking_output(tmp_path)

    dest = write_bundle(tmp_path, manifest, tmp_path.parent / "packed.meanap")
    import zipfile
    names = zipfile.ZipFile(dest).namelist()
    assert any(n.startswith("CellTracking/payload/") for n in names)
    assert not any("/work/" in n for n in names), "ROICaT intermediates must not travel"
    assert not any("CellTracking/viewer/" in n for n in names), "pages are rebuilt, not carried"

    svc = ViewerService(dest)
    try:
        listing = svc.tracking()
        assert listing["available"] is True
        assert listing["chains"][0]["chain"] == "chainA"
        page = svc.tracking_page("chainA")
        assert "__TRACK__" in page and "field of view" in page
    finally:
        svc.close()


# ── theming ───────────────────────────────────────────────────────────────────

def test_viewer_defines_every_plot_colour_it_uses():
    """An unresolved var() falls back to black, which is invisible on dark.

    This is the bug that made the tracking plots unreadable: the page defines
    ``--muted`` and the plots asked for ``--mut``.
    """
    import re

    from meanap.viewer.page import PAGE_HTML

    used = set(re.findall(r"var\((--[a-z-]+)\)", PAGE_HTML))
    used |= set(re.findall(r'themeColour\("(--[a-z-]+)"\)', PAGE_HTML))
    used |= set(re.findall(r'"(--plot-[a-z]+)"', PAGE_HTML))
    declared = set(re.findall(r"(--[a-z-]+)\s*:", PAGE_HTML))
    assert not (used - declared), f"undeclared CSS variables: {sorted(used - declared)}"


def test_dark_theme_is_declared_for_both_media_query_and_toggle():
    from meanap.viewer.page import PAGE_HTML

    # the media query default, and the explicit choice that must beat it
    assert 'prefers-color-scheme: dark' in PAGE_HTML
    assert ':root[data-theme="dark"]' in PAGE_HTML
    assert ':root:not([data-theme="light"])' in PAGE_HTML


def test_plot_colours_differ_between_light_and_dark():
    """The dark variants must actually be lighter, not the same values."""
    import re

    from meanap.viewer.page import PAGE_HTML

    def block(pattern):
        m = re.search(pattern + r"\s*\{([^}]*)\}", PAGE_HTML, re.S)
        return dict(re.findall(r"(--plot-[a-z]+)\s*:\s*(#[0-9a-fA-F]{6})", m.group(1)))

    light = block(r":root\s")
    dark = block(r':root\[data-theme="dark"\]')
    assert light and dark
    for key in ("--plot-wt", "--plot-het", "--plot-ko"):
        assert light[key] != dark[key], f"{key} is the same in both themes"
        lum = lambda h: sum(int(h[i:i + 2], 16) for i in (1, 3, 5))
        assert lum(dark[key]) > lum(light[key]), f"{key} is not lighter in dark"


def test_per_cell_page_honours_a_theme_parameter():
    from meanap.catnap.tracking.viewer import _CSS, _THEME_JS

    assert "theme" in _THEME_JS and "data-theme" in _THEME_JS
    # and the page's own stylesheet responds to it in both directions
    assert ':root[data-theme=dark]' in _CSS
    assert ':root:not([data-theme=light])' in _CSS


def test_parallel_workers_can_import_meanap(tmp_path):
    """A subprocess does not inherit the parent's sys.path.

    A source checkout is on sys.path but not on PYTHONPATH, so without this
    every worker dies with ModuleNotFoundError and the whole run reports
    failures that have nothing to do with the data.
    """
    import os
    import subprocess
    import sys

    import meanap

    pkg_parent = str(Path(meanap.__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_parent + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c",
         "import meanap.catnap.tracking.__main__ as m; print(bool(m.main))"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr[:400]
    assert "True" in result.stdout


# ── network stability ─────────────────────────────────────────────────────────

def _sym(rng, n, scale=1.0):
    m = rng.normal(scale=scale, size=(n, n))
    m = (m + m.T) / 2
    np.fill_diagonal(m, 1.0)
    return m


def test_stability_separates_a_preserved_network_from_a_shuffled_one():
    from meanap.catnap.tracking.network import stability

    rng = np.random.default_rng(0)
    n = 24
    base = _sym(rng, n)
    kept = base + _sym(rng, n, 0.25)          # same structure, noisier
    labels = np.arange(n)
    centroids = rng.random((n, 2)) * 500

    s = stability(base, kept, labels, labels, centroids, div_gap=7)
    assert s.usable and s.edge_r > 0.7
    # the spatial null swaps identities, so it must not track the structure
    assert s.null_r < 0.3
    assert s.div_gap == 7


def test_stability_needs_enough_shared_cells():
    from meanap.catnap.tracking.network import MIN_SHARED_CELLS, stability

    rng = np.random.default_rng(1)
    n = MIN_SHARED_CELLS - 1
    m = _sym(rng, n)
    labels = np.arange(n)
    s = stability(m, m, labels, labels, rng.random((n, 2)))
    assert not s.usable, "too few cells must not produce a correlation"


def test_edges_above_uses_a_quantile_not_a_fixed_weight():
    """Correlation scale shifts between recordings; a fixed cut would draw a
    dense graph on one day and an empty one on the next from that alone."""
    from meanap.catnap.tracking.network import edges_above

    rng = np.random.default_rng(2)
    weak = _sym(rng, 20, 0.1)
    strong = _sym(rng, 20, 2.0)
    e_weak, t_weak = edges_above(weak, 0.9)
    e_strong, t_strong = edges_above(strong, 0.9)
    assert len(e_weak) == len(e_strong), "a quantile keeps the same edge count"
    assert t_strong > t_weak, "but at a different weight"


def test_network_payload_is_small_enough_to_bundle():
    from meanap.catnap.tracking.pipeline import MAX_STORED_EDGES
    assert MAX_STORED_EDGES <= 1000


def test_network_view_renders(tmp_path):
    """Run the viewer's network renderer against a DOM shim, at two spans."""
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")

    from meanap.viewer.page import PAGE_HTML

    rng = np.random.default_rng(3)
    n = 12
    # half the cells appear on both days, half on only the first
    span = [2] * 6 + [1] * 6
    data = {
        "chain": "c", "divs": [14, 21],
        "network": {
            "nShared": 6, "nCells": n, "nSessions": 2,
            "span": span,
            "xy": [[float(y), float(x)] for y, x in rng.random((n, 2)) * 500],
            "days": [
                {"div": 14, "threshold": 0.4,
                 "edges": [[i, j, 0.5] for i in range(n) for j in range(i + 1, n)][:20],
                 "strength": {str(i): float(v) for i, v in enumerate(rng.random(n))},
                 "present": list(range(n))},
                {"div": 21, "threshold": 0.4,
                 "edges": [[i, j, 0.5] for i in range(6) for j in range(i + 1, 6)],
                 "strength": {str(i): float(v) for i, v in enumerate(rng.random(6))},
                 "present": list(range(6))},
            ],
        },
        "stability": [{"pair": "DIV14-DIV21", "divGap": 7, "nShared": 6,
                       "nEdges": 20, "edgeR": 0.62, "nullR": 0.03}],
    }
    (tmp_path / "net.json").write_text(json.dumps(data))

    m = re.search(r"(let TRACKING = null, TRACK_OVERVIEW = null;.*?)\nfunction download\(",
                  PAGE_HTML, re.S)
    (tmp_path / "net.js").write_text(m.group(1))
    shim = Path(__file__).resolve().parent / "js" / "overview_dom_shim.js"
    script = f"""
      const {{calls, reg}} = require({str(shim)!r});
      const fs = require('fs');
      reg['track-view'].value = 'network';
      reg['track-chain'].value = 'c';
      global.getJSON = async () => JSON.parse(
        fs.readFileSync({str(tmp_path / 'net.json')!r}, 'utf8'));
      const src = fs.readFileSync({str(tmp_path / 'net.js')!r}, 'utf8');
      new Function('return (async()=>{{' + src + '; await showTrackingNetwork();'
        + ' const wide = calls.circles;'
        + ' reg["tracking"].dataset.span = "2"; drawNetwork();'
        + ' if (calls.circles === wide) throw new Error("span made no difference");'
        + '}})()')()
        .then(() => {{
          if (calls.lines === 0) throw new Error('no edges drawn');
          if (calls.circles === 0) throw new Error('no cells drawn');
          console.log('OK');
        }})
        .catch(e => {{ console.error(e.message); process.exit(1); }});
    """
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[:600]
    assert "OK" in result.stdout


def test_overview_points_and_axes_carry_hover_help(tmp_path):
    """Every scatter point and both axis labels must explain themselves.

    A bare number on a plot is not self-describing: "separability 0.73" means
    nothing without knowing the null it is measured against.
    """
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")

    from meanap.viewer.page import PAGE_HTML
    from meanap.viewer.server import ViewerService

    _fake_tracking_output(tmp_path)
    meta_path = tmp_path / "CellTracking" / "chains" / "chainA.json"
    meta = json.loads(meta_path.read_text())
    meta["pairwise"] = {"DIV14-DIV21": {"frac_of_smaller": 0.3, "div_gap": 7,
                                        "shared": 4}}
    meta_path.write_text(json.dumps(meta))

    svc = ViewerService.__new__(ViewerService)
    svc._bundle = None
    svc.source = tmp_path
    (tmp_path / "overview.json").write_text(json.dumps(svc.tracking_overview()))

    m = re.search(r"(let TRACKING = null, TRACK_OVERVIEW = null;.*?)\nfunction download\(",
                  PAGE_HTML, re.S)
    (tmp_path / "overview.js").write_text(m.group(1))
    shim = Path(__file__).resolve().parent / "js" / "overview_dom_shim.js"
    script = f"""
      const {{calls, reg, listeners}} = require({str(shim)!r});
      const fs = require('fs');
      global.getJSON = async () => JSON.parse(
        fs.readFileSync({str(tmp_path / 'overview.json')!r}, 'utf8'));
      const src = fs.readFileSync({str(tmp_path / 'overview.js')!r}, 'utf8');
      new Function('return (async()=>{{' + src + '; await showTrackingOverview();}})()')()
        .then(() => {{
          // three handlers per hoverable element (enter, move, leave)
          if (listeners.count < 9) throw new Error('too few hover handlers: ' + listeners.count);
          console.log('OK ' + listeners.count);
        }})
        .catch(e => {{ console.error(e.message); process.exit(1); }});
    """
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[:600]
    assert "OK" in result.stdout


def test_axis_help_explains_the_spatial_null():
    """The null is the part nobody can guess, so it has to be stated."""
    from meanap.viewer.page import PAGE_HTML

    assert "nearest spatial neighbour" in PAGE_HTML
    assert "0.5 = no information" in PAGE_HTML
    # and the circle-size question the plot itself cannot answer
    assert "circle area" in PAGE_HTML


def test_a_point_never_has_both_tooltips():
    """The browser's native <title> pops up a second later, in its own box, on
    top of the styled one. A point gets one or the other, never both."""
    from meanap.viewer.page import PAGE_HTML

    # the else-if is what enforces it
    assert 'if (p.tip) {' in PAGE_HTML
    assert '} else if (p.title) {' in PAGE_HTML


def test_page_lands_on_a_chain_when_the_url_asks_for_it():
    """The GUI's "Open in viewer" sends ?tab=tracking&chain=…; the page must
    select that chain and tab once the tracking data has answered -- the tab
    does not exist before then, so this cannot happen in init()."""
    import re

    from meanap.viewer.page import PAGE_HTML

    m = re.search(r"async function initTracking\(\) \{(.*?)\n\}", PAGE_HTML, re.S)
    body = m.group(1)
    assert 'want.get("tab") === "tracking"' in body
    assert 'want.get("chain")' in body
    assert 'selectTab("tracking")' in body
    # the chain is set, and the view switched off the overview, before the tab
    # is shown -- otherwise showTracking draws the overview
    assert body.index("sel.value = chain") < body.index('selectTab("tracking")')
    assert '$("track-view").value' in body


def test_gui_button_opens_the_served_viewer_on_the_chain(tmp_path, monkeypatch):
    """The panel asks; the main window serves the run folder and opens the
    browser on the tracking tab at that chain. Not a static file: the page
    written at run time carries that day's JavaScript and none of the other
    tracking views."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from meanap.gui.panels.catnap import CatNapPanel

    root = tmp_path / "OutputData"
    _fake_tracking_output(root)
    panel = CatNapPanel()
    panel.set_output_root(root)
    assert panel._track_viewer_btn.isEnabled()
    asked = []
    panel.open_tracking_viewer_requested.connect(asked.append)
    panel._track_viewer_btn.click()
    assert asked == ["chainA"]

    # the window side, without a window: the same method the signal reaches
    from meanap.gui import main_window as mw
    opened = []
    monkeypatch.setattr(mw.webbrowser, "open", opened.append)

    class FakeViewers:
        def url_for(self, source):
            return None
        def open(self, source):
            assert Path(source) == root.resolve()
            return "http://127.0.0.1:1/"

    class Stub:
        _last_output_root = root
        _viewers = FakeViewers()
        _run_panel = type("P", (), {"append_log": staticmethod(lambda *_: None)})()
        _open_in_viewer = mw.MainWindow._open_in_viewer
    mw.MainWindow._on_open_tracking_viewer(Stub(), "chainA")
    assert opened == ["http://127.0.0.1:1/?tab=tracking&chain=chainA"]


def test_tracking_tab_hides_the_figure_panes():
    """setMode hides those panes and only runs for figure tabs, so the tracking
    tab has to hide them itself — otherwise the last figure stays on screen and
    looks like part of the tracking view."""
    import re

    from meanap.viewer.page import PAGE_HTML

    m = re.search(r"function selectTab\(tab\) \{(.*?)\n\}", PAGE_HTML, re.S)
    body = m.group(1)
    assert 'if (tab === "tracking") {' in body
    for pane in ("single", "pair", "gallery", "params", "controls-panel",
                 "toolbar"):
        assert f'"{pane}"' in body, f"{pane} is not hidden on the tracking tab"
    # #status lives in the toolbar and names the current figure, so the toolbar
    # has to come back when a figure tab is selected again
    assert 'remove("hidden")' in body


def test_chain_picker_is_available_to_every_per_chain_view():
    """Cells and Network are both one-chain views; only the overview is not."""
    import re

    from meanap.viewer.page import PAGE_HTML

    m = re.search(r"async function showTracking\(\) \{(.*?)\n\}", PAGE_HTML, re.S)
    body = m.group(1)
    assert 'view !== "overview"' in body, "the picker must follow 'not overview'"
    assert 'view !== "cells"' not in body, "hiding it for anything but cells hides it for Network"
    # and the heading is toggled by id rather than by matching its text
    assert 'track-chain-head' in PAGE_HTML


def test_folder_mode_comes_from_the_manifest_not_params_defaults(tmp_path):
    """A run without params.json is not therefore an ephys run.

    The manifest records what the run was; deriving the mode from
    ``params.suite2p_mode`` alone mislabels a CAT-NAP run as ephys whenever
    params.json is missing, because the default is False.
    """
    import json as _json

    from meanap.pipeline.render import load_context

    (tmp_path / "4_NetworkActivity").mkdir()
    (tmp_path / "4_NetworkActivity" / "netmet_results.json").write_text(
        _json.dumps({"rec1": {"25mslag": {}}}))
    (tmp_path / "manifest.json").write_text(_json.dumps(
        {"format": 1, "mode": "catnap", "recordings": [], "lags": [25]}))
    # deliberately no params.json
    ctx = load_context(tmp_path)
    assert ctx.mode == "catnap"


def test_mode_falls_back_to_params_without_a_manifest(tmp_path):
    import json as _json

    from meanap.pipeline.render import load_context

    (tmp_path / "4_NetworkActivity").mkdir()
    (tmp_path / "4_NetworkActivity" / "netmet_results.json").write_text(
        _json.dumps({"rec1": {"25mslag": {}}}))
    ctx = load_context(tmp_path)
    assert ctx.mode == "ephys"


def test_right_column_collapses_when_it_holds_nothing():
    """Hiding the panel inside a fixed grid track leaves the track's width."""
    from meanap.viewer.page import PAGE_HTML

    assert "body.no-right" in PAGE_HTML
    assert 'classList.toggle("no-right"' in PAGE_HTML


# ── field-of-view backgrounds ─────────────────────────────────────────────────

def test_mask_layers_are_separate_so_the_untracked_toggle_applies():
    """One combined image would bake the untracked cells in, and the
    'show untracked' control would silently do nothing on that background."""
    from meanap.catnap.tracking.viewer import masks_image_png

    stat = np.array([
        {"ypix": np.array([10, 11]), "xpix": np.array([10, 11]),
         "lam": np.array([1.0, 1.0]), "med": [10, 10]},
        {"ypix": np.array([40, 41]), "xpix": np.array([40, 41]),
         "lam": np.array([1.0, 1.0]), "med": [40, 40]},
    ], dtype=object)
    cluster_of = np.array([0, -1])     # first tracked, second not

    tracked = masks_image_png(stat, 64, cluster_of, tracked=True, size=64)
    other = masks_image_png(stat, 64, cluster_of, tracked=False, size=64)
    assert tracked and other and tracked != other

    import base64
    import io

    from PIL import Image

    def pixels(png):
        im = Image.open(io.BytesIO(base64.b64decode(png))).convert("RGBA")
        return np.asarray(im)[..., 3]        # the alpha channel

    a, b = pixels(tracked), pixels(other)
    # each layer holds its own ROI and not the other's
    assert a[10, 10] > 0 and a[40, 40] == 0
    assert b[40, 40] > 0 and b[10, 10] == 0


def test_background_selector_offers_mean_masks_and_none():
    from meanap.catnap.tracking.viewer import _JS, build_page

    page = build_page("t", "s", [], 30.0, sessions=[], frame_px=1280)
    for value in ('value="mean"', 'value="masks"', 'value="none"'):
        assert value in page
    # and the script acts on each
    assert 'background === "mean"' in _JS
    assert 'background === "masks"' in _JS


def test_masks_background_suppresses_the_dot_cloud():
    """The footprints already show every ROI; drawing every centroid on top
    would just cover them."""
    from meanap.catnap.tracking.viewer import _JS

    assert 'background !== "masks" && i < s._cy.length' in _JS


def test_tracked_cells_keep_their_colour_across_days():
    """Colour comes from the cluster id, not from position or draw order, so
    the same cell is the same colour in every panel."""
    from meanap.catnap.tracking.viewer import cluster_colour

    assert cluster_colour(7) == cluster_colour(7)
    assert cluster_colour(7) != cluster_colour(8)
    # consecutive ids must not come out as near-identical hues
    a, b = cluster_colour(3), cluster_colour(4)
    assert sum(abs(x - y) for x, y in zip(a, b)) > 60


def test_masks_render_larger_than_the_mean_image():
    """A suite2p ROI is ~4 px in a 1280 px frame; at the mean image's preview
    size each cell collapses to one pixel."""
    from meanap.catnap.tracking.viewer import FOV_PREVIEW_PX, MASK_PREVIEW_PX

    assert MASK_PREVIEW_PX > FOV_PREVIEW_PX


def test_each_background_scales_by_its_own_resolution():
    """Masks and the mean image are different sizes; one shared scale factor
    would put the mask layer in the wrong place."""
    from meanap.catnap.tracking.viewer import _JS

    assert "maskPreviewPx" in _JS
    assert "paint(s._img, D.fovPreviewPx)" in _JS


def test_canvas_ground_follows_the_background_choice():
    """The mean projection is light-on-dark and wants black; coloured masks on
    transparent read better on the page's own ground — white in light mode."""
    from meanap.catnap.tracking.viewer import _CSS, _JS

    assert 'background === "mean" ? "#000" : css("--bg")' in _JS
    # the FOV canvas takes its ground from the theme...
    fov_rule = _CSS[_CSS.index(".fov canvas"):_CSS.index(".fov figcaption")]
    assert "background:var(--bg)" in fov_rule
    assert "#000" not in fov_rule
    # ...while the per-day crop canvases stay black, which suits a magma map
    assert "background:#000" in _CSS[_CSS.index(".day canvas"):]


# ── per-cell page help ────────────────────────────────────────────────────────

def test_per_cell_page_declares_every_css_variable_it_uses():
    """An unresolved var() falls back silently — a transparent tooltip, or
    black text on a dark ground. This is the check that caught --mut."""
    import re

    from meanap.catnap.tracking.viewer import _CSS

    used = set(re.findall(r"var\((--[a-z-]+)\)", _CSS))
    declared = set(re.findall(r"(--[a-z-]+)\s*:", _CSS))
    assert not (used - declared), f"undeclared: {sorted(used - declared)}"


def test_every_measure_on_the_page_has_an_explanation():
    """A number with no definition is not self-describing: "fingerprint r" and
    "pop +0.40" mean nothing without saying what they measure."""
    from meanap.catnap.tracking.viewer import _JS

    for key in ("fingerprint", "d_event_rate", "d_iei", "d_pop_coupling",
                "centroid_shift", "rate", "pop", "listR", "fov", "masks"):
        assert f"{key}:" in _JS, f"no help text for {key}"


def test_fingerprint_help_states_it_is_independent_of_the_match():
    """The whole point of the measure, and the part nobody can infer."""
    from meanap.catnap.tracking.viewer import _JS

    assert "never looked at activity" in _JS
    assert "spatial null" in _JS
    # and that the spatial metric is not evidence
    assert "Description, not evidence" in _JS


def test_help_targets_are_actually_attached():
    from meanap.catnap.tracking.viewer import _JS, build_page

    page = build_page("t", "s", [], 30.0, sessions=[], frame_px=1280)
    for anchor in ("h-fov", "h-listr", "h-strips"):
        assert anchor in page, f"{anchor} missing from the markup"
        assert f'$("#{anchor}")' in _JS, f"{anchor} never gets a tooltip"


def test_footprint_overlap_is_iou_and_respects_registration():
    from meanap.catnap.tracking.quality import footprint_overlap

    a = {"ypix": np.array([0, 0, 1, 1]), "xpix": np.array([0, 1, 0, 1]),
         "lam": np.ones(4)}
    b = {"ypix": np.array([0, 0, 1, 1]), "xpix": np.array([1, 2, 1, 2]),
         "lam": np.ones(4)}
    assert footprint_overlap(a, a) == 1.0
    assert footprint_overlap(a, b) == pytest.approx(1 / 3)
    # undoing b's one-pixel offset makes them identical again
    assert footprint_overlap(a, b, (0, 0), (0, 1)) == 1.0


def test_footprint_metrics_are_marked_as_not_evidence():
    """They separate at AUC ~0.997 because the matcher used them. Presenting
    that as evidence would be circular."""
    from meanap.catnap.tracking.quality import METRIC_SPECS

    by_key = {m["key"]: m for m in METRIC_SPECS}
    assert by_key["footprint_iou"]["independent"] is False
    assert by_key["centroid_shift"]["independent"] is False
    assert by_key["fingerprint"]["independent"] is True


def test_spatial_metrics_use_registered_coordinates():
    """The source returns raw coordinates, so a chain shifted by 40 px would
    otherwise report every matched pair as 40 px apart."""
    import re

    src = Path("src/meanap/catnap/tracking/pipeline.py").read_text()
    assert "aligned[a][i] - aligned[b][jj]" in src
    assert "result.registered and result.offsets" in src


def test_iou_hover_expands_the_acronym_with_a_worked_example():
    """"IoU" is only obvious if you have come from computer vision."""
    from meanap.catnap.tracking.viewer import _JS

    assert "intersection over" in _JS
    assert "0.43" in _JS, "the worked example is what makes it concrete"
    assert "re-segments each day independently" in _JS, "why 1.0 is not expected"


def test_network_payload_keeps_cells_tracked_into_two_or_more_days():
    """Requiring presence on every day excluded 79 of 92 chains. A network held
    over three of five days is still a network; the viewer picks the span."""
    src = Path("src/meanap/catnap/tracking/pipeline.py").read_text()
    assert "len(days) >= 2" in src
    assert '"span": [len(spans[c]) for c in cells]' in src
    # and the all-days count survives as its own field rather than the gate
    assert '"nShared": sum(1 for c in cells if len(spans[c]) == len(sessions))' in src


def test_network_view_defaults_to_the_strictest_usable_span():
    """Not the span with the most dots — the most demanding one that still has
    enough cells to mean something."""
    from meanap.viewer.page import PAGE_HTML

    assert "for (let n = net.nSessions; n >= 2; n--)" in PAGE_HTML
    assert "net-span" in PAGE_HTML


def test_a_cell_is_only_drawn_on_days_it_was_tracked_into():
    from meanap.viewer.page import PAGE_HTML

    assert "day.present" in PAGE_HTML


# ── node metrics and roles ────────────────────────────────────────────────────

def test_node_metrics_do_not_silently_fall_back_to_one_module():
    """A bare except around Louvain made participation identically zero and
    every node peripheral, which then read as 99% role stability while
    measuring nothing at all."""
    src = Path("src/meanap/catnap/tracking/network.py").read_text()
    body = src[src.index("def node_metrics("):src.index("def _roles(")]
    assert "except Exception" not in body
    assert "rng=np.random.default_rng(seed)" in body


def test_node_metrics_returns_every_measure_and_a_role():
    from meanap.catnap.tracking.network import NODE_METRICS, node_metrics

    rng = np.random.default_rng(0)
    n = 30
    w = rng.random((n, n))
    w = (w + w.T) / 2
    np.fill_diagonal(w, 1.0)
    out = node_metrics(w)
    for name in NODE_METRICS:
        assert name in out and len(out[name]) == n
    assert len(out["role"]) == n
    assert out["n_modules"] >= 1


def test_role_stability_reports_kappa_not_just_agreement():
    """~90% of these nodes are peripheral, so raw agreement has an ~85% floor."""
    from meanap.catnap.tracking.network import role_stability

    # two unrelated labellings that agree often purely because one role dominates
    a = [1] * 90 + [2] * 10
    b = [1] * 85 + [2] * 5 + [1] * 10
    out = role_stability(a, b)
    assert out["agreement"] > 0.8, "raw agreement is high"
    assert abs(out["kappa"]) < 0.3, "kappa should not be"
    assert out["expected"] > 0.7


def test_perfect_role_agreement_gives_kappa_one():
    from meanap.catnap.tracking.network import role_stability

    roles = [1, 2, 3, 4, 1, 2, 5, 1]
    assert role_stability(roles, roles)["kappa"] == pytest.approx(1.0)


def test_metric_stability_null_destroys_the_pairing():
    from meanap.catnap.tracking.network import (metric_stability,
                                                metric_stability_null)

    rng = np.random.default_rng(1)
    a = list(rng.normal(size=40))
    b = [v + rng.normal(scale=0.2) for v in a]
    assert metric_stability(a, b) > 0.8
    assert abs(metric_stability_null(a, b)) < 0.3


def test_node_metrics_keeps_its_shape_for_a_tiny_network():
    """The early return has to carry every key the caller reads, or a two-cell
    day raises KeyError halfway through a batch."""
    from meanap.catnap.tracking.network import NODE_METRICS, node_metrics

    out = node_metrics(np.eye(2))
    for key in (*NODE_METRICS, "role", "n_modules", "modularity"):
        assert key in out, f"missing {key}"
    assert len(out["role"]) == 2


def test_uniform_colouring_does_not_read_a_missing_metric_map():
    """"uniform" has no metric map. Reading one because a role map happens to
    exist threw a TypeError and took the whole network render with it."""
    from meanap.viewer.page import PAGE_HTML

    assert 'else if (cm) shown = cm[String(i)]' in PAGE_HTML
    assert "if (cm || day.role) {" not in PAGE_HTML


def test_network_panels_are_sizeable_and_share_one_zoom():
    from meanap.viewer.page import PAGE_HTML

    assert "net-size" in PAGE_HTML and "small" in PAGE_HTML and "large" in PAGE_HTML
    assert "NET_VIEW" in PAGE_HTML and "attachNetZoom" in PAGE_HTML
    # node radius divided by the zoom, so magnifying separates rather than enlarges
    assert "/ zoom.k).toFixed(2)" in PAGE_HTML


def test_colour_scale_covers_both_continuous_and_categorical():
    from meanap.viewer.page import PAGE_HTML

    assert "function colourScale(" in PAGE_HTML
    assert "linear-gradient" in PAGE_HTML          # a measure
    assert "ROLE_LABEL[r]" in PAGE_HTML            # roles


def test_clicking_a_node_isolates_its_connections():
    from meanap.viewer.page import PAGE_HTML

    assert "NET_FOCUS" in PAGE_HTML
    # a second click releases, and the background clears it too
    assert "(NET_FOCUS === i) ? null : i" in PAGE_HTML
    # the rest fades rather than vanishing, so the context is kept
    assert "opacity: onFocus ? .55 : .06" in PAGE_HTML


def _run_network_js(tmp_path, data, steps):
    """Run the network renderer plus some driving steps under the DOM shim."""
    import re
    import shutil
    import subprocess

    from meanap.viewer.page import PAGE_HTML

    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")

    (tmp_path / "net.json").write_text(json.dumps(data))
    m = re.search(r"(let TRACKING = null, TRACK_OVERVIEW = null;.*?)\nfunction download\(",
                  PAGE_HTML, re.S)
    (tmp_path / "net.js").write_text(m.group(1))
    shim = Path(__file__).resolve().parent / "js" / "overview_dom_shim.js"
    script = f"""
      const {{calls, reg}} = require({str(shim)!r});
      const fs = require('fs');
      reg['track-view'].value = 'network';
      reg['track-chain'].value = 'c';
      global.getJSON = async () => JSON.parse(
        fs.readFileSync({str(tmp_path / 'net.json')!r}, 'utf8'));
      const src = fs.readFileSync({str(tmp_path / 'net.js')!r}, 'utf8');
      new Function('calls', 'reg', 'return (async()=>{{' + src + {steps!r} + '}})()')(calls, reg)
        .then(() => console.log('OK'))
        .catch(e => {{ console.error(e.message); process.exit(1); }});
    """
    return subprocess.run([node, "-e", script], capture_output=True, text=True)


def _network_fixture(n=12):
    rng = np.random.default_rng(3)
    return {
        "chain": "c", "divs": [14, 21],
        "network": {
            "nShared": 6, "nCells": n, "nSessions": 2, "span": [2] * n,
            "xy": [[float(y), float(x)] for y, x in rng.random((n, 2)) * 500],
            "days": [{"div": d, "threshold": 0.4,
                      "edges": [[i, j, 0.5] for i in range(n)
                                for j in range(i + 1, n)][:20],
                      "strength": {str(i): float(v) for i, v in enumerate(rng.random(n))},
                      "present": list(range(n))} for d in (14, 21)],
        },
        "stability": [], "metricStability": [],
    }


def test_dragging_pans_every_move_of_the_gesture(tmp_path):
    """Re-rendering mid-gesture destroyed the element holding the listener, so
    a drag moved once and then died."""
    steps = """
      await showTrackingNetwork();
      const p = NET_PANELS[0];
      if (!p) throw new Error('no live panel');
      const before = NET_VIEW.dx;
      p.svg.fire('pointerdown', {clientX: 100, clientY: 100});
      p.svg.fire('pointermove', {clientX: 130, clientY: 100});
      p.svg.fire('pointermove', {clientX: 160, clientY: 100});
      p.svg.fire('pointerup', {clientX: 160, clientY: 100});
      if (NET_VIEW.dx === before) throw new Error('drag did not pan');
      if (!p.g.attrs.transform) throw new Error('live panel was not transformed');
    """
    result = _run_network_js(tmp_path, _network_fixture(), steps)
    assert result.returncode == 0, result.stderr[:500]


def test_clicking_a_node_focuses_and_a_second_click_releases(tmp_path):
    """setPointerCapture on the svg stole the click from the node beneath it."""
    steps = """
      await showTrackingNetwork();
      let node = null;
      const walk = el => {
        if (!el || !el.children) return;
        if (el.attrs && el.attrs.class === 'netnode' && !node) node = el;
        for (const c of el.children) walk(c);
      };
      walk(reg['tracking']);
      if (!node) throw new Error('no clickable node');
      node.fire('click', {stopPropagation(){}});
      if (NET_FOCUS === null) throw new Error('click did not focus');
      let again = null;
      const walk2 = el => {
        if (!el || !el.children) return;
        if (el.attrs && el.attrs.class === 'netnode' && !again) again = el;
        for (const c of el.children) walk2(c);
      };
      walk2(reg['tracking']);
      again.fire('click', {stopPropagation(){}});
      if (NET_FOCUS !== null) throw new Error('second click did not release');
    """
    result = _run_network_js(tmp_path, _network_fixture(), steps)
    assert result.returncode == 0, result.stderr[:500]


def test_a_drag_is_not_treated_as_a_click(tmp_path):
    steps = """
      await showTrackingNetwork();
      const p = NET_PANELS[0];
      p.svg.fire('pointerdown', {clientX: 100, clientY: 100});
      p.svg.fire('pointermove', {clientX: 160, clientY: 100});
      p.svg.fire('pointerup', {clientX: 160, clientY: 100});
      const before = NET_FOCUS;
      p.svg.fire('click', {});
      if (NET_FOCUS !== before) throw new Error('a drag cleared the focus');
    """
    result = _run_network_js(tmp_path, _network_fixture(), steps)
    assert result.returncode == 0, result.stderr[:500]
