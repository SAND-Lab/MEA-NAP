"""Node metrics of the baseline, evoked and post-stimulus networks
(``meanap.stim.node_metrics``, ``Params.stim_node_metrics``).

Run: ``uv run pytest test_stim_node_metrics.py`` (from ``python/``; ~1 min).

What it has to show:
- every node gets every metric for every epoch and weighting, stimulating
  electrodes are left out, and the rate matches the existing node table;
- turning node metrics on changes none of the stim step's other numbers;
- the weightings mean what they say: electrodes that only share a response
  to the stimulus (no connections) gain co-activation strength during
  stimulation but not strength beyond the response; and a real connection
  that stimulation leaves alone keeps about the same strength beyond the
  response before and during it, despite the very different spike counts;
- figure 17 is drawn, and redrawn from the saved arrays; figure 18 too, on
  the electrode layout;
- recordings are summarised by their median node, and the paired test across
  recordings finds a consistent change (and declines with too few);
- the group figures get one folder per weighting;
- step 4 skips small-worldness when asked, and only that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

EVENTS = np.arange(2.0, 300.0, 1.0)
WINDOW = (0.0, 0.1)


def _culture(seed=0, n=10, responders=5, coupled=False):
    """Poisson background; the first *responders* electrodes each fire ~3
    spikes 5–40 ms after every stimulus, independently — common input only.
    With *coupled*, electrode 9 also follows half of electrode 8's spikes by
    2 ms, at all times: a connection stimulation does not touch."""
    rng = np.random.default_rng(seed)
    T = 302.0
    out = []
    for i in range(n):
        rate = 6.0 if coupled and i == 8 else 2.0
        t = rng.uniform(0, T, rng.poisson(rate * T))
        if i < responders:
            k = rng.poisson(3.0, EVENTS.size)
            t = np.concatenate([t, np.repeat(EVENTS, k) + rng.uniform(0.005, 0.04, k.sum())])
        out.append(np.sort(t))
    if coupled:
        src = out[8]
        out[9] = np.sort(np.concatenate([out[9], src[rng.random(src.size) < 0.5] + 0.002]))
    return out


def _run(trains, tmp_path, *, node_metrics=True, exclude=None, sub="run"):
    from meanap.params import Params
    from meanap.pipeline.spreadsheet import RecordingInfo
    from meanap.pipeline.stim_step import _electrical_events, _stim_networks
    from meanap.stim.sequences import StimCondition

    cond = StimCondition(name="pattern_1", steps=((1,),), delays_s=np.zeros(1),
                         onsets_s=EVENTS, channel_index=())
    params = Params(stim_network_rep_num=40, func_con_lag_val=[10], stim_split_half=False,
                    stim_trial_consistency=False, stim_node_metrics=node_metrics)
    root = tmp_path / sub
    return _stim_networks(params, RecordingInfo("rec", 20, "WT"), {}, trains,
                          _electrical_events([cond]), np.arange(11, 11 + len(trains)), None,
                          root / "figs", root / "mats", lambda *_: None,
                          windows={"pattern_1": WINDOW}, exclude=exclude)


def test_every_node_epoch_weighting(tmp_path):
    from meanap.stim.node_metrics import NODE_METRICS, WEIGHTINGS

    exclude = np.zeros(10, bool)
    exclude[7] = True
    tables = _run(_culture(), tmp_path, exclude=exclude)
    nm = pd.DataFrame(tables["StimNetwork_NodeMetrics.csv"])
    assert len(nm) == 10 * 3 * len(WEIGHTINGS)
    assert set(nm["epoch"]) == {"baseline", "evoked", "post"}
    assert set(nm["weighting"]) == set(WEIGHTINGS)
    assert set(NODE_METRICS) <= set(nm.columns)
    stim = nm[nm["stim_electrode"]]
    assert set(stim["channel_id"]) == {18} and stim[list(NODE_METRICS)].isna().all().all()
    # The rate is the one the existing node table reports.
    nl = pd.DataFrame(tables["StimNetwork_NodeLevel.csv"]).set_index("channel_id")
    ev = nm[(nm["epoch"] == "evoked") & (nm["weighting"] == "coactivation")].set_index(
        "channel_id")
    ok = ~ev["stim_electrode"]
    np.testing.assert_allclose(ev.loc[ok, "rate_hz"], nl.loc[ev.index[ok], "evoked_rate_hz"])


def test_other_numbers_unchanged(tmp_path):
    on = _run(_culture(), tmp_path, node_metrics=True, sub="on")
    off = _run(_culture(), tmp_path, node_metrics=False, sub="off")
    assert "StimNetwork_NodeMetrics.csv" not in off
    a = pd.DataFrame(on["StimNetwork_RecordingLevel.csv"])
    b = pd.DataFrame(off["StimNetwork_RecordingLevel.csv"])
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(pd.DataFrame(on["StimNetwork_NodeLevel.csv"]),
                                  pd.DataFrame(off["StimNetwork_NodeLevel.csv"]))


def test_weightings_tell_common_input_from_coupling(tmp_path):
    tables = _run(_culture(seed=1), tmp_path)
    nm = pd.DataFrame(tables["StimNetwork_NodeMetrics.csv"])
    resp = nm["channel_id"] < 16            # the five responding electrodes

    def strength(epoch, w):
        d = nm[(nm["epoch"] == epoch) & (nm["weighting"] == w) & resp]
        return float(np.nanmean(d["NS"]))
    co_change = strength("evoked", "coactivation") - strength("baseline", "coactivation")
    beyond_change = strength("evoked", "beyond") - strength("baseline", "beyond")
    assert co_change > 0.5, co_change
    assert abs(beyond_change) < 0.25 * co_change, (beyond_change, co_change)


def test_unchanged_connection_stays_unchanged(tmp_path):
    tables = _run(_culture(seed=2, coupled=True), tmp_path)
    nm = pd.DataFrame(tables["StimNetwork_NodeMetrics.csv"])
    pair = nm[nm["channel_id"].isin([19, 20]) & (nm["weighting"] == "beyond")]
    s = pair.groupby("epoch")["NS"].mean()
    assert s["baseline"] > 0.1 and s["evoked"] > 0.1, s
    assert abs(s["evoked"] - s["baseline"]) < 0.35 * s["baseline"], s


def test_figure_17_drawn_and_redrawn(tmp_path):
    from meanap.stim.redraw import draw_network_figures, network_figure_names, _loads

    _run(_culture(), tmp_path)
    name = "17_StimNodeMetrics_pattern_1_10mslag"
    assert (tmp_path / "run" / "figs" / f"{name}.png").exists()
    with np.load(tmp_path / "run" / "mats" / "rec_stimNetwork.npz") as d:
        arrays = {k: d[k] for k in d.files}
    assert name in network_figure_names(_loads(arrays["figure_meta"]))
    out = draw_network_figures(arrays, tmp_path / "redrawn", only=name)
    assert [p.name for p in out] == [f"{name}.png"]


def test_recording_summary_and_paired_tests():
    from meanap.stim.node_metrics import paired_tests, summarise_recordings

    rows = []
    rng = np.random.default_rng(0)
    for r in range(8):                          # 8 recordings, 6 nodes each, NS up by ~1
        for node in range(1, 7):
            base = rng.normal(5, 1)
            for ep, v in (("baseline", base), ("evoked", base + 1 + 0.1 * rng.normal()),
                          ("post", base)):
                rows.append({"FileName": f"r{r}", "Grp": "WT", "DIV": 21, "condition": "c",
                             "lag_ms": 10, "weighting": "beyond", "node": node,
                             "stim_electrode": node == 6, "epoch": ep, "NS": v,
                             "rate_hz": 2.0})
    summary = summarise_recordings(rows)
    assert len(summary) == 8 and all(s["n_nodes"] == 5 for s in summary)
    assert all(0.7 < s["NS_change"] < 1.3 and s["NS_fracUp"] == 1.0 for s in summary)
    tests = {t["metric"]: t for t in paired_tests(summary)}
    assert tests["NS"]["n_recordings"] == 8 and tests["NS"]["n_up"] == 8
    assert tests["NS"]["wilcoxon_p"] < 0.01
    assert np.isnan(paired_tests(summary[:5])[0]["wilcoxon_p"])   # too few to test


def test_figure_18_on_the_array(tmp_path):
    from meanap.params import Params
    from meanap.pipeline.spreadsheet import RecordingInfo
    from meanap.pipeline.stim_step import _electrical_events, _stim_networks
    from meanap.stim.redraw import _loads, draw_network_figures, network_figure_names
    from meanap.stim.sequences import StimCondition

    trains = _culture()
    cond = StimCondition(name="pattern_1", steps=((1,),), delays_s=np.zeros(1),
                         onsets_s=EVENTS, channel_index=())
    params = Params(stim_network_rep_num=30, func_con_lag_val=[10], stim_split_half=False,
                    stim_trial_consistency=False)
    coords = np.column_stack([np.arange(10) % 5, np.arange(10) // 5]).astype(float)
    exclude = np.zeros(10, bool)
    exclude[3] = True
    _stim_networks(params, RecordingInfo("rec", 20, "WT"), {}, trains,
                   _electrical_events([cond]), np.arange(11, 21), None, tmp_path / "figs",
                   tmp_path / "mats", lambda *_: None, windows={"pattern_1": WINDOW},
                   exclude=exclude, coords=coords, condition_electrodes={"pattern_1": [14]})
    name = "18_StimNodeChangeMap_pattern_1_10mslag"
    assert (tmp_path / "figs" / f"{name}.png").exists()
    with np.load(tmp_path / "mats" / "rec_stimNetwork.npz") as d:
        arrays = {k: d[k] for k in d.files}
    assert name in network_figure_names(_loads(arrays["figure_meta"]))
    assert [p.name for p in draw_network_figures(arrays, tmp_path / "re", only=name)] == \
        [f"{name}.png"]


def test_group_figures_for_node_changes(tmp_path):
    from meanap.stim.group_plots import plot_stim_group_comparisons
    from meanap.stim.node_metrics import paired_tests, summarise_recordings

    tables = {"StimNetwork_RecordingLevel.csv": [], "StimNetwork_NodeMetrics.csv": []}
    for i, (grp, seed) in enumerate((("WT", 1), ("WT", 2), ("KO", 3), ("KO", 4))):
        t = _run(_culture(seed=seed), tmp_path, sub=f"g{i}")
        for name in tables:
            for r in t[name]:
                tables[name].append({**r, "FileName": f"rec{i}", "Grp": grp})
    tables["StimNodeMetrics_RecordingSummary.csv"] = summarise_recordings(
        tables["StimNetwork_NodeMetrics.csv"])
    assert paired_tests(tables["StimNodeMetrics_RecordingSummary.csv"])
    plot_stim_group_comparisons(tables, tmp_path / "out", log=lambda *_: None)
    root = tmp_path / "out" / "StimNetwork_GroupComparisons"
    for w in ("significant", "coactivation", "beyond"):
        figs = list((root / "7_NodeChangeByGroup" / w).rglob("*.png"))
        assert len(figs) == 6, (w, figs)


def test_step4_small_world_option():
    from meanap.params import Params
    from meanap.pipeline.step4 import compute_network_metrics

    rng = np.random.default_rng(0)
    a = rng.random((12, 12))
    a = (a + a.T) / 2
    np.fill_diagonal(a, 0)
    counts = np.full(12, 100.0)
    full = compute_network_metrics(a, counts, 60.0, 0.0, 3, params=Params(),
                                   rng=np.random.default_rng(1))
    lean = compute_network_metrics(a, counts, 60.0, 0.0, 3, params=Params(),
                                   rng=np.random.default_rng(1), small_world=False)
    assert "SW" in full and "SW" not in lean
    for k in ("NS", "ND", "aveControl", "BC"):
        np.testing.assert_allclose(full[k], lean[k])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
