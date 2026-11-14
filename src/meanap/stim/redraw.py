"""Stimulation figures drawn from what the run saved, by the run and the viewer alike.

Every per-recording stim figure is drawn here from a stored payload, never
from objects that exist only while the step runs. The step saves the payload,
then calls the same functions the viewer calls on a bundle, so the two cannot
draw different pictures.

Two payloads per recording, both in ``ExperimentMatFiles/``:

``<rec>_stimFigures.npz``
    What :func:`~meanap.stim.pipeline.write_stim_figures` reads: the
    stimulation detected on each electrode, the patterns, the spike times
    after the artifact was cleaned out, and the stim parameters. Figures 9,
    10, the pattern heatmaps, the per-electrode PSTHs and the shuffle tests.
    The spike times are stored cleaned, so redrawing needs neither the raw
    recording nor the blanking it was cleaned with.

``<rec>_stimNetwork.npz``
    The stimulus-network matrices, plus a ``figure_meta`` JSON entry and the
    arrays figures 13–15 need beyond them (latencies, trial-similarity
    matrices, the halves' null means and spike counts). A network file
    without ``figure_meta`` predates this and has nothing to redraw from.

Matrices are stored at full size, NaN for the stimulating electrodes left out
of the analysis (``stim_electrode``); figures 14 and 15 were drawn on the
subset, so loading takes it back out.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

import numpy as np

FIGURES_SUFFIX = "_stimFigures.npz"
NETWORK_SUFFIX = "_stimNetwork.npz"
#: Bumped when the payload changes shape, so an old one is refused, not misread.
PAYLOAD_VERSION = 1


# ── Serialising ───────────────────────────────────────────────────────────────

def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"cannot store {type(o).__name__} in a stim figure payload")


def _dumps(obj) -> np.ndarray:
    return np.array(json.dumps(obj, default=_json_default))


def _loads(arr) -> object:
    return json.loads(str(np.asarray(arr)[()]))


def _ragged(seqs) -> tuple[np.ndarray, np.ndarray]:
    """Values and offsets: ``seqs[i] == values[offsets[i]:offsets[i + 1]]``."""
    seqs = [np.asarray(s, float).ravel() for s in seqs]
    offsets = np.r_[0, np.cumsum([s.size for s in seqs])].astype(np.int64)
    values = np.concatenate(seqs) if seqs else np.array([], float)
    return values, offsets


def _unragged(values: np.ndarray, offsets: np.ndarray) -> list[np.ndarray]:
    return [values[offsets[i]:offsets[i + 1]].copy() for i in range(len(offsets) - 1)]


# ── Figures 9, 10, heatmaps, PSTHs, shuffle tests ─────────────────────────────

def save_figure_payload(path: Path, *, stim_info: list, patterns: list,
                        spike_times: dict, method: str, params: dict,
                        artifact_s: float, info: dict, seed: int,
                        recording: str) -> Path:
    """Store everything :func:`draw_activity_figures` needs for one recording."""
    from meanap.pipeline.atomic import atomic_savez

    n = len(stim_info)
    trains = [spike_times.get(c, {}).get(method, []) for c in range(n)]
    tv, to = _ragged(trains)
    sv, so = _ragged([s.elec_stim_times for s in stim_info])
    dv, do = _ragged([s.elec_stim_dur for s in stim_info])
    pv, po = _ragged([s.pattern_ids for s in stim_info])
    patv, pato = _ragged(patterns)
    coords = np.array([np.asarray(s.coords, float).ravel()[:2] for s in stim_info]
                      ).reshape(n, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_savez(
        path, compressed=True,
        version=np.array(PAYLOAD_VERSION),
        channel_name=np.array([int(s.channel_name) for s in stim_info]),
        coords=coords,
        pattern=np.array([int(s.pattern or 0) for s in stim_info]),
        stim_times=sv, stim_times_offsets=so,
        stim_dur=dv, stim_dur_offsets=do,
        pattern_ids=pv, pattern_ids_offsets=po,
        patterns=patv, patterns_offsets=pato,
        spikes=tv, spikes_offsets=to,
        meta=_dumps({"method": method, "params": params, "artifact_s": float(artifact_s),
                     "info": info, "seed": int(seed), "recording": recording}))


def load_figure_payload(path: Path) -> dict:
    """The inverse of :func:`save_figure_payload`, as the arguments it was given."""
    from meanap.stim.detection import StimChannelInfo

    with np.load(path) as d:
        if int(d["version"]) != PAYLOAD_VERSION:
            raise ValueError(f"{Path(path).name} is a version {int(d['version'])} stim "
                             f"payload; this MEA-NAP reads version {PAYLOAD_VERSION}")
        meta = _loads(d["meta"])
        stim = _unragged(d["stim_times"], d["stim_times_offsets"])
        dur = _unragged(d["stim_dur"], d["stim_dur_offsets"])
        pids = _unragged(d["pattern_ids"], d["pattern_ids_offsets"])
        trains = _unragged(d["spikes"], d["spikes_offsets"])
        stim_info = [StimChannelInfo(elec_stim_times=stim[i], elec_stim_dur=dur[i],
                                     channel_name=int(d["channel_name"][i]),
                                     coords=d["coords"][i].copy(),
                                     pattern=int(d["pattern"][i]),
                                     pattern_ids=tuple(int(p) for p in pids[i]))
                     for i in range(len(d["channel_name"]))]
        patterns = _unragged(d["patterns"], d["patterns_offsets"])
    method = meta["method"]
    return {"stim_info": stim_info, "patterns": patterns,
            "spike_times": {c: {method: t} for c, t in enumerate(trains)},
            "params": meta["params"], "artifact_s": meta["artifact_s"],
            "info": meta["info"], "seed": meta["seed"], "recording": meta["recording"]}


def draw_activity_figures(payload: dict, dest: Path, only: str | None = None,
                          shuffles: dict | None = None) -> list[Path]:
    """Figures 9, 10, the heatmaps, PSTHs and shuffle tests, from a loaded payload
    — or just the one named *only* (its path under *dest*, no suffix). *shuffles*
    keeps the shuffle tests between calls (see ``write_stim_figures``)."""
    from meanap.pipeline.rng import make_rng
    from meanap.stim.pipeline import write_stim_figures

    return write_stim_figures(
        dest, payload["stim_info"], payload["patterns"], payload["spike_times"],
        payload["params"], None, payload["artifact_s"], payload["info"],
        rng=make_rng(payload["seed"], "stim-figures", payload["recording"]), only=only,
        shuffles=shuffles)


def record_figure_names(path: Path, written: list[Path], dest: Path) -> None:
    """Add the names of the figures drawn from the payload at *path* to it, so
    a viewer can list them without drawing (the per-electrode PSTHs are named
    after whichever electrodes responded most)."""
    from meanap.pipeline.atomic import atomic_savez

    names = [Path(w).relative_to(dest).with_suffix("").as_posix() for w in written]
    with np.load(path) as d:
        arrays = {k: d[k] for k in d.files}
    arrays["figure_names"] = np.array(names, dtype=str)
    atomic_savez(path, compressed=True, **arrays)


# ── Figures 13–15: stimulus networks ──────────────────────────────────────────

def _graph_lags(meta: dict) -> list:
    """Lags with a three-epoch network for at least one condition, when the run
    saved electrode positions to draw them at."""
    if not meta.get("has_coords"):
        return []
    lags = [lg["lag"] for c in meta["conditions"] for lg in c["lags"]
            if "post" in lg["epochs"]]
    return list(dict.fromkeys(lags))


def network_figure_names(meta: dict) -> list[str]:
    """The stems :func:`draw_network_figures` writes, in drawing order."""
    out = []
    for c in meta["conditions"]:
        if c.get("consistency") is not None:
            out.append(f"14_StimConsistency_{c['name']}")
        for lg in c["lags"]:
            out.append(f"13_StimNetwork_{c['name']}_{lg['lag']}mslag")
            if lg.get("split_rows"):
                out.append(f"15_StimNetworkSplitHalf_{c['name']}_{lg['lag']}mslag")
    out += [f"16_StimNetworkGraph_{lag}mslag" for lag in _graph_lags(meta)]
    return out


def has_network_figures(arrays: Mapping) -> bool:
    return "figure_meta" in arrays


def draw_network_figures(arrays: Mapping, fig_dir: Path, only: str | None = None) -> list[Path]:
    """Figures 13–16 for every condition and lag in a ``_stimNetwork.npz`` — or
    just the one whose name (no suffix) is *only*."""
    from meanap.stim.consistency import PatternDrift, TrialConsistency
    from meanap.stim.consistency_plots import plot_split_half, plot_trial_consistency
    from meanap.stim.evoked_network import EpochNetwork, NoiseCorrelation
    from meanap.pipeline.stim_step import _plot_stim_network

    meta = _loads(arrays["figure_meta"])
    if meta.get("version") != PAYLOAD_VERSION:
        raise ValueError(f"stim network figure payload version {meta.get('version')}; "
                         f"this MEA-NAP reads version {PAYLOAD_VERSION}")
    fig_dir = Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    keep = ~np.asarray(arrays["stim_electrode"], bool)
    channels = np.asarray(arrays["channels"])
    sub2 = np.ix_(keep, keep)
    title = meta["title"]
    written: list[Path] = []

    def want(stem: str) -> bool:
        return only is None or only == stem

    def net(cond, epoch, lag, info, prefix, *, subset=False, n_trials=None):
        def get(k, nd=2):
            key = f"{prefix}__{k}"
            if key not in arrays:
                return np.full((keep.size,) * nd, np.nan)
            a = np.asarray(arrays[key], float)
            return (a[sub2] if a.ndim == 2 else a[keep]) if subset else a
        nan = np.full((keep.size,) * 2, np.nan)
        return EpochNetwork(
            condition=cond, epoch=epoch, window_s=tuple(info["window_s"]), lag_ms=lag,
            null=meta["null"], n_trials=int(n_trials if n_trials is not None
                                            else info["n_trials"]),
            duration_s=float(info.get("duration_s", np.nan)),
            sttc=get("sttc"), sttc_thr=get("sttc_thr"), null_mean=get("null_mean"),
            p=nan[sub2] if subset else nan, spike_counts=get("spike_counts", 1),
            sttc_mode=meta.get("sttc_mode", "pooled"))

    for c in meta["conditions"]:
        cond = c["name"]
        if c.get("consistency") is not None and want(f"14_StimConsistency_{cond}"):
            cs = c["consistency"]

            def drift(kind):
                k = f"{cond}__{kind}_drift"
                return PatternDrift(
                    similarity=np.asarray(arrays[f"{k}__similarity"]),
                    lag_similarity=np.asarray(arrays[f"{k}__lag_similarity"]),
                    lag_null=np.asarray(arrays[f"{k}__lag_null"]),
                    slope=cs[f"{kind}_slope"], slope_p=cs[f"{kind}_slope_p"])

            tc = TrialConsistency(
                condition=cond, window_s=tuple(c["window_s"]),
                evoked=np.asarray(arrays[f"{cond}__trial_evoked"])[:, keep],
                baseline=np.asarray(arrays[f"{cond}__trial_baseline"])[:, keep],
                latency_s=np.asarray(arrays[f"{cond}__trial_latency"])[:, keep],
                node_rho=np.asarray(arrays[f"{cond}__node_rho"])[keep],
                node_p=np.asarray(arrays[f"{cond}__node_p"])[keep],
                evoked_drift=drift("evoked"), baseline_drift=drift("baseline"),
                summary=cs["summary"])
            path = fig_dir / f"14_StimConsistency_{cond}.png"
            plot_trial_consistency(tc, channels[keep], path, f"{title} — {cond}")
            written.append(path)

        nc = NoiseCorrelation(condition=cond, window_s=tuple(c["window_s"]),
                              n_trials=int(c["noise_n_trials"]),
                              r=np.asarray(arrays[f"{cond}__noise_r"]),
                              p=np.asarray(arrays[f"{cond}__noise_p"]),
                              counts=np.empty((0, keep.size)))
        for lg in c["lags"]:
            lag = lg["lag"]
            if want(f"13_StimNetwork_{cond}_{lag}mslag"):
                nets = {ep: net(cond, ep, lag, lg["epochs"][ep], f"{cond}__{ep}__{lag}ms")
                        for ep in ("baseline", "evoked")}
                path = fig_dir / f"13_StimNetwork_{cond}_{lag}mslag.png"
                _plot_stim_network(nets, nc, path, f"{title} — {cond}, lag {lag} ms",
                                   names=channels)
                written.append(path)
            if lg.get("split_rows") and want(f"15_StimNetworkSplitHalf_{cond}_{lag}mslag"):
                halves = {}
                for r in lg["split_rows"]:
                    if r["epoch"] not in ("baseline", "evoked"):
                        continue
                    for half in ("A", "B"):
                        halves[(r["split"], r["epoch"], half)] = net(
                            cond, r["epoch"], lag, lg["epochs"][r["epoch"]],
                            f"{cond}__{r['epoch']}__{lag}ms__{r['split']}_{half}",
                            subset=True, n_trials=r[f"n_trials_{half}"])
                path = fig_dir / f"15_StimNetworkSplitHalf_{cond}_{lag}mslag.png"
                plot_split_half(halves, lg["split_rows"], path,
                                f"{title} — {cond}, lag {lag} ms", names=channels[keep])
                written.append(path)
    for lag in _graph_lags(meta):
        if not want(f"16_StimNetworkGraph_{lag}mslag"):
            continue
        path = fig_dir / f"16_StimNetworkGraph_{lag}mslag.png"
        plot_epoch_graphs(arrays, meta, lag, path)
        written.append(path)
    return written


#: The three epochs of figure 16, in column order.
GRAPH_EPOCHS = (("baseline", "Pre-stimulus"), ("evoked", "During stimulation"),
                ("post", "Post-stimulus"))
#: The stimulating electrodes of a row's pattern (Okabe-Ito vermillion).
STIM_MARK = "#D55E00"


def plot_epoch_graphs(arrays: Mapping, meta: dict, lag, path: Path) -> None:
    """Figure 16: each pattern's network before, during and after stimulation,
    drawn on the array. One row per pattern, one column per epoch.

    Edges are the significant STTC edges (the run's null). Node size is degree
    and edge width STTC, on scales shared by every panel, so a node or edge
    can be compared across epochs and patterns. Stimulating electrodes are
    left out of the networks; the row's own are starred, any others crossed.
    """
    from meanap.native import output
    from meanap.native.network_paint import NetworkGridPainter, NetworkGridScene
    from meanap.native.scene import network_scene

    keep = ~np.asarray(arrays["stim_electrode"], bool)
    channels = np.asarray(arrays["channels"]).astype(int)
    coords = np.asarray(arrays["coords"], float)
    placed = np.isfinite(coords).all(axis=1)
    shown = keep & placed                            # e.g. a grounded corner has none
    idx = np.flatnonzero(shown)

    rows = []
    for c in meta["conditions"]:
        lg = next((x for x in c["lags"] if x["lag"] == lag and "post" in x["epochs"]), None)
        if lg is None:
            continue
        mats = []
        for epoch, _label in GRAPH_EPOCHS:
            m = np.nan_to_num(np.asarray(arrays[f"{c['name']}__{epoch}__{lag}ms__sttc_thr"],
                                         float)[np.ix_(idx, idx)])
            m[m < 0] = 0.0
            np.fill_diagonal(m, 0.0)
            mats.append((m, lg["epochs"][epoch]))
        rows.append((c, mats))

    weights = np.concatenate([m[np.triu_indices(len(idx), 1)] for _c, ms in rows
                              for m, _e in ms] or [np.zeros(0)])
    weights = weights[weights > 0]
    edge_bounds = ((float(weights.min()), float(weights.max())) if weights.size
                   else (0.0, 1.0))
    max_degree = max([float((m > 0).sum(axis=1).max()) for _c, ms in rows for m, _e in ms
                      if m.size] + [1.0])
    every = coords[placed]
    extent = ((float(every[:, 0].min()), float(every[:, 0].max()),
               float(every[:, 1].min()), float(every[:, 1].max())) if len(every)
              else (0.0, 1.0, 0.0, 1.0))

    grid = []
    for c, mats in rows:
        own = set(c.get("electrodes") or [])
        markers = []
        for i in np.flatnonzero(~keep & placed):
            mine = int(channels[i]) in own
            markers.append({"xy": tuple(coords[i]), "shape": "star" if mine else "cross",
                            "colour": STIM_MARK if mine else "#8a8f98",
                            "size": 16 if mine else 7,
                            "text": f"electrode {int(channels[i])}: stimulating"
                                    + (" in this pattern" if mine else " in another pattern")})
        panels = []
        for (m, ep), (_epoch, label) in zip(mats, GRAPH_EPOCHS):
            n_edges = int(np.count_nonzero(np.triu(m, 1)))
            w0, w1 = ep["window_s"]
            of = (f" of {ep['n_defined_pairs']} defined pairs"
                  if ep.get("n_defined_pairs") is not None
                  and ep["n_defined_pairs"] < ep.get("n_pairs", 0) else "")
            net = network_scene(
                m, coords[idx], 0.0, (m > 0).sum(axis=1).astype(float),
                title=f"{label}  {w0 * 1000:g} to {w1 * 1000:g} ms\n"
                      f"{n_edges} significant edges{of}, {ep['n_trials']} trials",
                names=channels[idx], noun="electrode",
                z_scale_override=max_degree, edge_bounds_override=edge_bounds)
            net.extent, net.markers = extent, markers
            panels.append(net)
        grid.append(panels)
    how = (", STTC within each trial and averaged" if meta.get("sttc_mode") == "trial_mean"
           else "")
    scene = NetworkGridScene(
        title=f"{meta['title']}: networks before, during and after stimulation, lag {lag} ms\n"
              f"Significant STTC edges ({meta['null'].replace('_', ' ')} null{how}). "
              f"Node size: degree; edge width: STTC; shared across panels. "
              f"\u2605 the row's stimulating electrodes (left out of the networks).",
        panels=grid, row_names=[c["name"] for c, _m in rows])
    painter = NetworkGridPainter(scene)
    output.save(painter, path, capture=output.NativeFigure("network_grid", scene, painter))


# ── What a recording has, by name ─────────────────────────────────────────────

#: Every per-recording stim figure the step writes, by stem (or sub-folder).
STIM_FIGURE_PATTERN = re.compile(
    r"^(9_FR_before_after_stimulation|10_stimulation_raster_and_psth|"
    r"stimPattern_\d+_heatmap|spikeLatency_pattern_\d+_heatmap|12_shuffle_test_|"
    r"13_StimNetwork_|14_StimConsistency_|15_StimNetworkSplitHalf_|16_StimNetworkGraph_|"
    r"Individual_PSTH_and_Raster_Pattern_\d+/)")


def is_stim_figure(relative: str) -> bool:
    """Whether a path relative to a recording's 2A folder is a stim figure."""
    return bool(STIM_FIGURE_PATTERN.match(relative))


_LABELS = (
    (r"^9_FR_before_after_stimulation$", "Firing rate before vs after, all stimuli"),
    (r"^9_FR_before_after_stimulation_pattern_(\d+)$",
     "Firing rate before vs after, pattern {0}"),
    (r"^10_stimulation_raster_and_psth$", "Raster and PSTH, all stimuli"),
    (r"^10_stimulation_raster_and_psth_pattern_(\d+)$", "Raster and PSTH, pattern {0}"),
    (r"^stimPattern_(\d+)_heatmap$", "Response heatmap, pattern {0}"),
    (r"^spikeLatency_pattern_(\d+)_heatmap$", "Spike latency heatmap, pattern {0}"),
    (r"^12_shuffle_test_null_dist_pattern_(\d+)$", "Shuffle test null, pattern {0}"),
    (r"^12_shuffle_test_sig_heatmap_pattern_(\d+)$", "Shuffle test significance, pattern {0}"),
    (r"^Individual_PSTH_and_Raster_Pattern_(\d+)/Individual_PSTH_and_Raster_electrode_(\d+)$",
     "PSTH and raster, pattern {0}, electrode {1}"),
    (r"^13_StimNetwork_(.+)_(\d+)mslag$", "Baseline vs evoked network, {0}, {1} ms lag"),
    (r"^14_StimConsistency_(.+)$", "Trial-by-trial consistency, {0}"),
    (r"^15_StimNetworkSplitHalf_(.+)_(\d+)mslag$", "Split-half networks, {0}, {1} ms lag"),
    (r"^16_StimNetworkGraph_(\d+)mslag$", "Networks before, during, after: {0} ms lag"),
)


def stim_figure_label(name: str) -> str:
    for pattern, label in _LABELS:
        m = re.match(pattern, name)
        if m:
            return label.format(*m.groups())
    return name.replace("_", " ")


def _order(name: str) -> tuple:
    """Pipeline numbering first (9 before 10 before 13), then by name."""
    lead = name.split("/")[0]
    digits = re.match(r"^(\d+)_", lead)
    rank = {"stimPattern": 10.5, "spikeLatency": 10.6, "Individual": 11}
    num = (float(digits.group(1)) if digits
           else next((v for k, v in rank.items() if lead.startswith(k)), 99))
    return (num, name)


def sort_stim_names(names) -> list[str]:
    return sorted(set(names), key=_order)
