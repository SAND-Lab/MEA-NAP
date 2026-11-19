"""Where on the array are the spikes? The signal-quality map.

Two maps of the same electrodes, drawn where they sit on the array:

* **Spike activity**: how many more negative-going deflections beyond 5 noise
  SDs an electrode has than its own noise makes
  (:meth:`~meanap.pipeline.signal_quality.SignalQuality.excess_hz`). This is
  sorter-free. Electrodes the check does not call spiking are drawn small and
  grey.
* **Noise level**: each electrode's noise SD. It picks out dead, noisy or
  badly routed electrodes, and shows whether a quiet region is quiet or just
  noisier.

When the spikes came from a sorter, every unit is drawn on its peak electrode
over the activity map, ringed in its unit-quality label's colour. Real units
sit where the activity is. Units scattered evenly over electrodes with no
excess activity are what a sorter makes of noise.

Drawn from the saved signal-quality payload (which carries the electrode
positions) and, if there is one, the unit-quality table, so a bundle can
redraw it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

#: The unit-quality labels' colours, as the unit-quality figure draws them.
LABEL_COLOURS = {"good": "#2a9d8f", "mua": "#e9a23b", "noise": "#6e6e6e"}
#: Best first: an electrode with several units is ringed in its best one's colour.
LABEL_ORDER = ("good", "mua", "noise")
MAP_SUFFIX = "_signal_quality_map"
#: The activity colour scale's floor: the check's own minimum excess rate.
ACTIVITY_FLOOR_HZ = 0.1


def _marker_size(n: int) -> float:
    """Dots that neither vanish on a 1012-electrode routing nor swamp a 60-electrode MEA."""
    return float(np.clip(260.0 / np.sqrt(max(n, 1)), 4.0, 16.0))


def _colours(values: np.ndarray, cmap: str, low: float, high: float) -> list:
    import matplotlib

    span = high - low if high > low else 1.0
    table = matplotlib.colormaps[cmap]
    return [tuple(c) for c in table(np.clip((values - low) / span, 0, 1))]


def _log_bar_ticks(low: float, high: float) -> list[tuple[float, str]]:
    from meanap.pipeline.unit_quality import _log_ticks

    return _log_ticks(low, high)


def signal_quality_map_chart(res, units=None, title: str = ""):
    """The map as a :class:`~meanap.native.chart.Chart`.

    *res* is a :class:`~meanap.pipeline.signal_quality.SignalQuality` with
    positions (``res.xy``). *units* is an optional table with ``electrode``
    and ``label`` columns (``unit_id``, ``noise_fraction`` for the hover).
    """
    from meanap.native.chart import (
        Chart, ColourBar, Legend, LegendItem, Panel, Points, rgba,
    )
    from meanap.pipeline.signal_quality import VERDICT_K

    xy = np.asarray(res.xy, dtype=float).reshape(-1, 2)
    if len(xy) != len(res.channels):
        raise ValueError("this signal-quality check has no electrode positions")
    placed = np.all(np.isfinite(xy), axis=1)
    ids = np.asarray(res.channels)
    n = int(placed.sum())
    size = _marker_size(n)
    excess = res.excess_hz(VERDICT_K, "neg")
    spiking = res.spiking(VERDICT_K)
    sigma = np.asarray(res.sigma, dtype=float)
    unit_label = res.units or ""

    # Spike activity, log scale from the check's own floor.
    act = spiking & placed
    hi_act = float(np.log10(max(excess[act].max(), ACTIVITY_FLOOR_HZ * 10))) if act.any() \
        else np.log10(ACTIVITY_FLOOR_HZ * 10)
    lo_act = np.log10(ACTIVITY_FLOOR_HZ)
    quiet = placed & ~spiking
    marks = [Points(xy[quiet, 0], xy[quiet, 1], fill=rgba("#c8c8c8"), size=size * 0.55,
                    key="no excess",
                    hover=[f"electrode {ids[i]}: no more large deflections than its noise"
                           for i in np.flatnonzero(quiet)])]
    if act.any():
        ia = np.flatnonzero(act)
        ia = ia[np.argsort(excess[ia])]           # the most active drawn on top
        marks.append(Points(
            xy[ia, 0], xy[ia, 1],
            fill=_colours(np.log10(np.maximum(excess[ia], ACTIVITY_FLOOR_HZ)),
                          "viridis", lo_act, hi_act),
            size=size, key="spiking",
            hover=[f"electrode {ids[i]}: {excess[i]:.2f} Hz excess beyond "
                   f"−{VERDICT_K:g} SD" for i in ia]))

    legend = None
    n_units = 0
    if units is not None and len(units) and "electrode" in units:
        pos = {int(e): i for i, e in enumerate(ids)}
        by_elec: dict[int, list] = {}
        for _, u in units.iterrows():
            e = int(u["electrode"]) if np.isfinite(u["electrode"]) else -1
            if e in pos and placed[pos[e]]:
                by_elec.setdefault(e, []).append(u)
        for lab in reversed(LABEL_ORDER):          # good drawn last, on top
            es = [e for e, us in by_elec.items()
                  if min(LABEL_ORDER.index(str(x["label"])) for x in us) == LABEL_ORDER.index(lab)]
            if not es:
                continue
            hover = []
            for e in es:
                parts = []
                for x in by_elec[e]:
                    nf = x.get("noise_fraction", np.nan)
                    parts.append(f"unit {x.get('unit_id', '?')} {x['label']}"
                                 + (f", noise {float(nf):.2g}×" if np.isfinite(nf) else ""))
                hover.append(f"electrode {e}: " + "; ".join(parts))
            # Rings just round the dot, so a dense sort does not bury the
            # activity under it; noise units the quietest of the three.
            marks.append(Points([xy[pos[e], 0] for e in es], [xy[pos[e], 1] for e in es],
                                fill=rgba("#ffffff", 0.0),
                                edge=rgba(LABEL_COLOURS[lab], 0.6 if lab == "noise" else 1.0),
                                edge_width=0.8 if lab == "noise" else 1.3,
                                size=size * 1.45, key=lab, hover=hover, z=4))
            n_units += sum(len(by_elec[e]) for e in es)
        counts = {lab: sum(1 for us in by_elec.values() for x in us if x["label"] == lab)
                  for lab in LABEL_ORDER}
        legend = Legend([LegendItem(f"{lab} units ({counts[lab]})", rgba(LABEL_COLOURS[lab]),
                                    kind="box", key=lab) for lab in LABEL_ORDER if counts[lab]],
                        loc="bottom", columns=3, size=8)

    common = dict(equal=True, grid="", xticks=[], yticks=[], title_size=9, label_size=8)
    n_sp = int(act.sum())
    left = Panel(cell=(0, 0), marks=marks,
                 title=f"Spike activity: {n_sp} of {n} electrodes have more large "
                       f"negative deflections than their noise makes",
                 xlabel="ringed: sorted units on their peak electrode" if n_units else "",
                 colour_bar=ColourBar("viridis", lo_act, hi_act,
                                      label=f"excess beyond −{VERDICT_K:g} SD (Hz)",
                                      ticks=_log_bar_ticks(lo_act, hi_act)),
                 **common)

    good = placed & (sigma > 0)
    lo_s, hi_s = (np.percentile(sigma[good], [2, 98]) if good.any() else (0.0, 1.0))
    ig = np.flatnonzero(good)
    noise_marks = [Points(xy[ig, 0], xy[ig, 1], fill=_colours(sigma[ig], "cividis", lo_s, hi_s),
                          size=size, key="noise",
                          hover=[f"electrode {ids[i]}: noise SD {sigma[i]:.3g} {unit_label}"
                                 for i in ig])]
    flat = placed & ~(sigma > 0)
    if flat.any():
        noise_marks.append(Points(xy[flat, 0], xy[flat, 1], fill=rgba("#d62728"), size=size,
                                  key="flat", hover=[f"electrode {ids[i]}: flat (no signal)"
                                                     for i in np.flatnonzero(flat)]))
    right = Panel(cell=(0, 1), marks=noise_marks,
                  title="Noise level" + (f" — {int(flat.sum())} flat electrode(s) in red"
                                         if flat.any() else ""),
                  colour_bar=ColourBar("cividis", float(lo_s), float(hi_s),
                                       label=f"noise SD ({unit_label})" if unit_label
                                       else "noise SD"),
                  **common)
    head = (title + "\n" if title else "") + (
        f"{res.duration_s:.0f} s checked, {res.band_hz[0]:g}–{res.band_hz[1]:g} Hz")
    # As tall as the array is, so a wide MaxWell chip leaves no band of white.
    span = np.ptp(xy[placed], axis=0) if n > 1 else np.array([1.0, 1.0])
    aspect = float(span[1] / span[0]) if span[0] > 0 else 1.0
    # Each map is about 4 in wide once its colour bar and margins are placed.
    height = 4.0 * float(np.clip(aspect, 0.25, 1.2)) + 1.3 + (0.35 if legend else 0.0)
    chart = Chart([left, right], size=(13, height), grid=(1, 2), title=head, title_size=10)
    chart.legend = legend
    return chart


def draw_saved_signal_quality_map(root: str | Path, rec_name: str, out_path: str | Path):
    """Draw *rec_name*'s map from its saved check (and unit table), or ``None``.

    ``None`` when the check did not run or kept no electrode positions.
    """
    import pandas as pd

    from meanap.native.chart_paint import save_chart
    from meanap.pipeline.signal_quality import (
        SIGNAL_QUALITY_DIR, SIGNAL_QUALITY_SUFFIX, load_signal_quality,
    )
    from meanap.pipeline.unit_quality import UNIT_QUALITY_CSV, UNIT_QUALITY_DIR

    root = Path(root)
    sq = root / SIGNAL_QUALITY_DIR / f"{rec_name}{SIGNAL_QUALITY_SUFFIX}"
    if not sq.exists():
        return None
    res = load_signal_quality(sq)
    if len(res.xy) != len(res.channels):
        return None
    table = root / UNIT_QUALITY_DIR / f"{rec_name}{UNIT_QUALITY_CSV}"
    units = pd.read_csv(table) if table.exists() else None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_chart(signal_quality_map_chart(res, units, title=rec_name), out_path)
    return out_path


def has_map(root: str | Path, rec_name: str) -> bool:
    """Whether *rec_name*'s saved check can be drawn as a map."""
    from meanap.pipeline.signal_quality import SIGNAL_QUALITY_DIR, SIGNAL_QUALITY_SUFFIX

    sq = Path(root) / SIGNAL_QUALITY_DIR / f"{rec_name}{SIGNAL_QUALITY_SUFFIX}"
    if not sq.exists():
        return False
    with np.load(sq, allow_pickle=False) as z:
        return "xy" in z.files and len(z["xy"]) == len(z["channels"]) and len(z["xy"]) > 0
