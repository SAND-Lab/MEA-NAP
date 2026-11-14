"""Stimulus detection checks: what MATLAB's ``plotStimDetectionChecks.m`` draws.

``1_SpikeDetection/1C_StimDetectionChecks/<group>/<recording>/``

* ``1_StimsDetected``: every electrode's detected pulses over the recording, one
  row each, by electrode ID (``plotStimTimes.m``);
* ``2_StimsHeatmap``: the array, stimulating electrodes filled and labelled
  with their pattern (``plotStimHeatmap.m``);
* ``3_StimsElectrode_<id>`` for every stimulating electrode and
  ``3_NoStimsElectrode_<id>`` for five others picked at random: the trace over
  the recording above the pulses detected on it (``plotIdvStimDataAndTrace.m``).

A straight port: same figures, names and layout. The traces need the raw
voltage, which a bundle does not carry, so the step keeps what the figures
show in ``ExperimentMatFiles/<recording>_stimChecks.npz`` and draws them from
that: each plotted electrode's trace as its minimum and maximum in
:data:`TRACE_BINS` time bins (every artifact and spike still reaches its full
height), the detected pulses and the layout. The viewer redraws from the same
file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

__all__ = [
    "STIM_CHECKS_SUFFIX", "STIM_CHECKS_DIR", "TRACE_BINS", "StimCheckData",
    "compute_stim_check_data", "save_stim_check_data", "load_stim_check_data",
    "stim_check_names", "draw_stim_check_figures",
]

STIM_CHECKS_SUFFIX = "_stimChecks.npz"
STIM_CHECKS_DIR = "1_SpikeDetection/1C_StimDetectionChecks"
#: Time bins a trace is kept at — finer than any screen or saved figure shows.
TRACE_BINS = 4000
#: Bumped when the file changes shape, so an old one is refused, not misread.
VERSION = 1
#: matplotlib's default colour cycle, which the MATLAB-style rows step through.
_CYCLE = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
          "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf")
_TEXT = dict(title_size=12, label_size=10, tick_size=9)


@dataclass
class StimCheckData:
    recording: str
    duration_s: float
    channel_names: np.ndarray               # (n,) electrode IDs, in channel order
    coords: np.ndarray                      # (n, 2)
    stim_times: list                        # n arrays of pulse onsets (s)
    patterns: list                          # n tuples of pattern IDs (empty: none)
    stim_dur_for_plotting: float            # s; how wide a pulse is drawn
    detection_method: str
    detection_value: float
    #: Channels with a trace, in drawing order: the stimulating ones, then the
    #: randomly picked others (``picked_no_stim``), and their envelopes.
    traced: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    picked_no_stim: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    trace_t: np.ndarray = field(default_factory=lambda: np.zeros(0))
    trace_low: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    trace_high: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))

    def stimulating(self) -> np.ndarray:
        return np.array([i for i, t in enumerate(self.stim_times) if len(t)], int)


def _envelope(trace: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray]:
    """Minimum and maximum of *trace* in *bins* equal runs of samples."""
    edges = np.linspace(0, trace.size, min(bins, max(trace.size, 1)) + 1).astype(np.int64)
    low = np.minimum.reduceat(trace, edges[:-1])
    high = np.maximum.reduceat(trace, edges[:-1])
    return low, high


def compute_stim_check_data(raw: np.ndarray, stim_info: list, params: dict, recording: str,
                            rng: np.random.Generator | None = None, *,
                            num_no_stim: int = 5, bins: int = TRACE_BINS,
                            channels: list[int] | None = None) -> StimCheckData:
    """What the check figures show, from the raw data (samples × channels).

    *channels*, if given, are the ones to keep a trace of instead of every
    stimulating electrode and *num_no_stim* others at random.
    """
    fs = float(params["fs"])
    n_time = raw.shape[0]
    rng = rng if rng is not None else np.random.default_rng()
    stim = [i for i, s in enumerate(stim_info) if s.elec_stim_times.size > 0]
    if channels is not None:
        picks = [int(c) for c in channels if stim_info[c].elec_stim_times.size == 0]
        stim = [int(c) for c in channels if int(c) not in picks]
    else:
        # Channel index 15 (1-based) is MATLAB's reference electrode, never picked.
        others = [i for i, s in enumerate(stim_info)
                  if s.elec_stim_times.size == 0 and i != 14]
        picks = []
        for _ in range(min(num_no_stim, len(others))):
            picks.append(others.pop(int(rng.integers(len(others)))))
    traced = np.array(stim + picks, int)
    lows, highs = [], []
    for ch in traced:
        low, high = _envelope(np.asarray(raw[:, ch], float), bins)
        lows.append(low)
        highs.append(high)
    k = len(lows[0]) if lows else 0
    edges = np.linspace(0, n_time, k + 1) / fs
    return StimCheckData(
        recording=recording, duration_s=n_time / fs,
        channel_names=np.array([int(s.channel_name) for s in stim_info]),
        coords=np.array([np.asarray(s.coords, float).ravel()[:2] for s in stim_info]),
        stim_times=[np.asarray(s.elec_stim_times, float).ravel() for s in stim_info],
        patterns=[tuple(int(p) for p in (s.pattern_ids or ((s.pattern,) if s.pattern else ())))
                  for s in stim_info],
        stim_dur_for_plotting=float(params["stimDurationForPlotting"]),
        detection_method=str(params.get("stimDetectionMethod", "")),
        detection_value=float(params.get("stimDetectionVal") or np.nan),
        traced=traced, picked_no_stim=np.array(picks, int),
        trace_t=(edges[:-1] + edges[1:]) / 2,
        trace_low=np.array(lows).reshape(len(traced), k),
        trace_high=np.array(highs).reshape(len(traced), k))


def save_stim_check_data(path: Path | str, data: StimCheckData) -> Path:
    from meanap.pipeline.atomic import atomic_savez
    from meanap.stim.redraw import _dumps, _ragged

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    times, offsets = _ragged(data.stim_times)
    atomic_savez(
        path, compressed=True, version=np.array(VERSION),
        meta=_dumps({"recording": data.recording, "duration_s": data.duration_s,
                     "patterns": [list(p) for p in data.patterns],
                     "stim_dur_for_plotting": data.stim_dur_for_plotting,
                     "detection_method": data.detection_method,
                     "detection_value": data.detection_value}),
        channel_names=data.channel_names, coords=data.coords,
        stim_times=times, stim_offsets=offsets, traced=data.traced,
        picked_no_stim=data.picked_no_stim, trace_t=data.trace_t,
        trace_low=data.trace_low.astype(np.float32),
        trace_high=data.trace_high.astype(np.float32))
    return path


def load_stim_check_data(path: Path | str) -> StimCheckData:
    from meanap.stim.redraw import _loads, _unragged

    with np.load(path) as d:
        if int(d["version"]) != VERSION:
            raise ValueError(f"stimulus check file version {int(d['version'])}; "
                             f"this MEA-NAP reads version {VERSION}")
        meta = _loads(d["meta"])
        return StimCheckData(
            recording=meta["recording"], duration_s=float(meta["duration_s"]),
            channel_names=d["channel_names"], coords=d["coords"],
            stim_times=_unragged(d["stim_times"], d["stim_offsets"]),
            patterns=[tuple(p) for p in meta["patterns"]],
            stim_dur_for_plotting=float(meta["stim_dur_for_plotting"]),
            detection_method=meta["detection_method"],
            detection_value=float(meta["detection_value"]),
            traced=d["traced"], picked_no_stim=d["picked_no_stim"], trace_t=d["trace_t"],
            trace_low=d["trace_low"].astype(float), trace_high=d["trace_high"].astype(float))


def stim_check_names(data: StimCheckData) -> list[str]:
    """The figure stems :func:`draw_stim_check_figures` writes, in MATLAB's order."""
    picked = set(int(c) for c in data.picked_no_stim)
    names = ["1_StimsDetected", "2_StimsHeatmap"]
    names += [f"3_NoStimsElectrode_{int(data.channel_names[c])}"
              for c in data.traced if int(c) in picked]
    names += [f"3_StimsElectrode_{int(data.channel_names[c])}"
              for c in data.traced if int(c) not in picked]
    return names


# ── drawing ───────────────────────────────────────────────────────────────────

def _pulses(times: np.ndarray, width: float, duration: float) -> tuple[np.ndarray, np.ndarray]:
    """A 0/1 step over [0, *duration*]: up for *width* seconds at each pulse."""
    xs, ys = [0.0], [0.0]
    for t in np.sort(np.asarray(times, float)):
        xs += [t, t, t + width, t + width]
        ys += [0.0, 1.0, 1.0, 0.0]
    xs.append(duration)
    ys.append(0.0)
    return np.array(xs), np.array(ys)


def _stims_detected(data: StimCheckData):
    """``1_StimsDetected`` (``plotStimTimes.m``)."""
    from meanap.native.chart import Chart, Line, Panel, Text, rgba

    names = data.channel_names
    n = len(names)
    marks = []
    for row, elec in enumerate(np.sort(names)):
        ch = int(np.flatnonzero(names == elec)[0])
        vert = (n - row) * 1.2
        xs, ys = _pulses(data.stim_times[ch], data.stim_dur_for_plotting, data.duration_s)
        times = data.stim_times[ch]
        said = (f"electrode {int(elec)} (channel {ch + 1}): {len(times)} pulse(s)"
                + (f", first at {times.min():.2f} s" if len(times) else ""))
        marks.append(Line(xs, ys + vert, colour=rgba(_CYCLE[row % len(_CYCLE)]), width=0.8,
                          hover=[said] * len(xs)))
        marks.append(Text(-1, vert + 0.5, str(int(elec)), size=7, ha="right"))
        marks.append(Text(data.duration_s + 1, vert + 0.5, str(ch + 1), size=7, ha="left"))
    ylim = (0.9, n * 1.2 + 1.3)
    base = Panel(marks=marks, xlabel="Time (s)", ylabel="Electrode ID", yticks=[], grid="",
                 ylim=ylim, **_TEXT)
    right = Panel(twin=True, ylabel="Channel Index", yticks=[], ylim=ylim, **_TEXT)
    return Chart([base, right], size=(6, 15))


def _circle(xc: float, yc: float, r: float = 0.5, n: int = 48):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return xc + r * np.cos(t), yc + r * np.sin(t)


def _stims_heatmap(data: StimCheckData):
    """``2_StimsHeatmap`` (``plotStimHeatmap.m``)."""
    from meanap.native.chart import Chart, Panel, Polygon, Text, rgba

    marks = []
    for ch, (elec, (xc, yc)) in enumerate(zip(data.channel_names, data.coords)):
        if not (np.isfinite(xc) and np.isfinite(yc)):
            continue
        px, py = _circle(float(xc), float(yc))
        times, pats = data.stim_times[ch], data.patterns[ch]
        if len(times) == 0:
            marks.append(Polygon(px, py, fill=rgba("white"), edge=rgba("black"),
                                 edge_width=1.0, hover=f"electrode {int(elec)}: no stimulation"))
            continue
        label = ",".join(str(p) for p in pats)
        marks.append(Polygon(px, py, fill=rgba("black"), edge=rgba("red"), edge_width=1.5,
                             hover=f"electrode {int(elec)}: {len(times)} pulse(s), "
                                   f"pattern {label or '–'}", z=2))
        if label:
            marks.append(Text(float(xc), float(yc), label, colour=rgba("white"),
                              size=12 if len(pats) < 2 else 8))
    placed = data.coords[np.isfinite(data.coords).all(axis=1)]
    lo, hi = (placed.min(axis=0), placed.max(axis=0)) if len(placed) else ((0, 0), (1, 1))
    panel = Panel(marks=marks, bare=True, equal=True, xlim=(lo[0] - 1, hi[0] + 1),
                  ylim=(lo[1] - 1, hi[1] + 1))
    return Chart([panel], size=(6, 6))


def _electrode_trace(data: StimCheckData, ch: int):
    """``3_(No)StimsElectrode_<id>`` (``plotIdvStimDataAndTrace.m``)."""
    from meanap.native.chart import Chart, Line, Panel, Rule, Segments, rgba

    k = int(np.flatnonzero(data.traced == ch)[0])
    t, low, high = data.trace_t, data.trace_low[k], data.trace_high[k]
    blue = rgba(_CYCLE[0])
    # One stroke per time bin, from its lowest to its highest sample: the trace
    # as matplotlib draws it at this width, and far quicker than one polygon.
    marks = [Segments(np.column_stack([t, low, t, high]), colour=blue, width=0.5)]
    hover_line = Line(t, (low + high) / 2, colour=rgba(_CYCLE[0], 0.0), width=0.5,
                      hover=[f"{tt:.2f} s: {lo:.4g} to {hi:.4g}"
                             for tt, lo, hi in zip(t, low, high)])
    marks.append(hover_line)
    if data.detection_method == "absPosThreshold" and np.isfinite(data.detection_value):
        marks.append(Rule(data.detection_value, colour=rgba("black"), dash="--"))
    elec = int(data.channel_names[ch])
    trace = Panel(cell=(0, 0), marks=marks, xlabel="Time", ylabel="Filtered signal",
                  title=f"Electrode {elec} (Channel {ch + 1})", grid="", sharex="time",
                  xlim=(0, data.duration_s), **_TEXT)
    times = data.stim_times[ch]
    xs, ys = _pulses(times, data.stim_dur_for_plotting, data.duration_s)
    pulses = Panel(cell=(1, 0), xlabel="Time (s)", ylabel="Stim Pulses Detected", ylim=(0, 1),
                   grid="", sharex="time", xlim=(0, data.duration_s),
                   marks=[Line(xs, ys, colour=blue, width=0.8,
                               hover=[f"{len(times)} pulse(s) detected on electrode {elec}"]
                               * len(xs))], **_TEXT)
    return Chart([trace, pulses], size=(10, 6), grid=(2, 1))


def draw_stim_check_figures(data: StimCheckData, out_dir: Path | str, *, fmt: str = "png",
                            only: str | None = None) -> list[Path]:
    """Write the check figures into *out_dir*, or just the one named *only*."""
    from meanap.native.chart_paint import save_chart

    out_dir = Path(out_dir)
    by_name = {f"{n}": None for n in stim_check_names(data)}
    written: list[Path] = []
    for name in by_name:
        if only is not None and Path(only).stem != name:
            continue
        if name == "1_StimsDetected":
            chart = _stims_detected(data)
        elif name == "2_StimsHeatmap":
            chart = _stims_heatmap(data)
        else:
            elec = int(name.rsplit("_", 1)[1])
            chart = _electrode_trace(data, int(np.flatnonzero(data.channel_names == elec)[0]))
        written.append(save_chart(chart, out_dir / f"{name}.{fmt}"))
    return written
