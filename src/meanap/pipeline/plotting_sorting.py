"""Step-1 check figures for a spike-*sorted* recording.

The detection checks (:mod:`meanap.pipeline.plotting`) answer "did the
detector find spikes?" by showing traces with spikes marked. Sorting raises a
different question — "is each unit a neuron, and how many did each electrode
give?" — so it gets its own three figures:

1. ``1_UnitsPerElectrode`` — the MEA grid coloured by how many units each
   electrode became, with the count on it. The picture that says what sorting
   changed about the network's node set.
2. ``2_UnitTemplates`` — one panel per electrode in the grid, the templates
   of its units overlaid. This is the one to look at when deciding whether
   two units on an electrode are really two neurons.
3. ``3_UnitQuality`` — SNR against refractory-violation fraction for every
   unit the sorter returned, with the curation floors drawn, so the labels can
   be read off the plot; plus firing rate by label.

Like the detection checks, the numbers behind them are saved as a small
``.npz`` payload so a bundle viewer can redraw them, and a ``units.csv`` lists
every unit with its metrics and label.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from meanap.pipeline.atomic import atomic_savez
from meanap.pipeline.probes import layout_coords_for_channels, layout_grid_step

SORTING_CHECKS_SUFFIX = "_sortingchecks.npz"

#: Columns of ``units.csv``, in order. Everything :class:`SortingCheckData`
#: keeps per returned unit.
UNIT_TABLE_COLUMNS = (
    "unit_id", "channel_id", "label", "kept", "n_spikes", "firing_rate", "snr",
    "rp_violation_frac", "presence_ratio", "amplitude_uv", "sorter_unit_id",
)

_LABEL_COLORS = {"good": "#2a9d8f", "mua": "#e9a23b", "noise": "#9a9a9a"}


@dataclass
class SortingCheckData:
    rec_name: str
    channel_layout: str
    sorter_name: str
    sorter_version: str
    #: Every electrode of the recording, and its layout coordinates (NaN when
    #: the layout does not place it).
    electrode_ids: np.ndarray
    electrode_coords: np.ndarray
    #: Per *returned* unit, curated or not — the CSV's rows.
    unit_table: list[dict[str, Any]] = field(default_factory=list)
    #: Per *kept* unit: ID, electrode, label, template on its electrode.
    kept_ids: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=str))
    kept_channel_ids: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))
    kept_labels: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=str))
    templates: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    template_times_ms: np.ndarray = field(default_factory=lambda: np.zeros(0))
    #: Curation floors, drawn on the quality figure.
    min_snr: float = 4.0
    max_rp_violation_frac: float = 0.05
    min_firing_rate: float = 0.05

    def write_unit_table(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=UNIT_TABLE_COLUMNS)
            writer.writeheader()
            for row in self.unit_table:
                writer.writerow({k: row.get(k, "") for k in UNIT_TABLE_COLUMNS})
        return path


def sorting_check_data(result, channels: np.ndarray, channel_layout: str,
                       rec_name: str, params=None) -> SortingCheckData:
    """Reduce a :class:`~meanap.pipeline.spike_sorting.SpikeSortingResult` to
    what the check figures and the unit table show."""
    coords, _ = layout_coords_for_channels(channel_layout, channels)
    kept_ids = list(result.units.get("id", []))
    kept_sorter_ids = {str(s) for s in result.units.get("sorter_unit_id", [])}
    id_by_sorter = {str(s): u for s, u in
                    zip(result.units.get("sorter_unit_id", []), kept_ids)}

    table = []
    for row in result.all_units:
        sid = str(row["sorter_unit_id"])
        table.append({
            "unit_id": id_by_sorter.get(sid, ""),
            "channel_id": row["channel_id"],
            "label": row["label"],
            "kept": int(sid in kept_sorter_ids),
            "n_spikes": row["n_spikes"],
            "firing_rate": round(float(row["firing_rate"]), 4),
            "snr": round(float(row["snr"]), 3),
            "rp_violation_frac": round(float(row["rp_violation_frac"]), 4),
            "presence_ratio": round(float(row["presence_ratio"]), 3),
            "amplitude_uv": round(float(row["amplitude_uv"]), 2),
            "sorter_unit_id": sid,
        })

    data = SortingCheckData(
        rec_name=rec_name, channel_layout=channel_layout,
        sorter_name=result.sorter_name, sorter_version=result.sorter_version,
        electrode_ids=np.asarray(channels).ravel().astype(int),
        electrode_coords=coords, unit_table=table,
        kept_ids=np.array(kept_ids, dtype=str),
        kept_channel_ids=np.asarray(result.channels, dtype=int),
        kept_labels=np.array(list(result.units.get("label", [])), dtype=str),
        templates=np.asarray(result.templates, dtype=np.float32),
        template_times_ms=np.asarray(result.template_times_ms, dtype=float),
    )
    if params is not None:
        data.min_snr = params.curation_min_snr
        data.max_rp_violation_frac = params.curation_max_rp_violation_frac
        data.min_firing_rate = params.curation_min_firing_rate
    return data


# ── Payload ───────────────────────────────────────────────────────────────────

_TABLE_NUMERIC = ("channel_id", "kept", "n_spikes", "firing_rate", "snr",
                  "rp_violation_frac", "presence_ratio", "amplitude_uv")


def save_sorting_check_data(path: Path | str, data: SortingCheckData) -> Path:
    path = Path(path)
    arrays: dict[str, Any] = {
        "rec_name": np.array([data.rec_name]),
        "channel_layout": np.array([data.channel_layout]),
        "sorter": np.array([data.sorter_name, data.sorter_version]),
        "electrode_ids": data.electrode_ids,
        "electrode_coords": data.electrode_coords,
        "kept_ids": data.kept_ids,
        "kept_channel_ids": data.kept_channel_ids,
        "kept_labels": data.kept_labels,
        "templates": data.templates,
        "template_times_ms": data.template_times_ms,
        "floors": np.array([data.min_snr, data.max_rp_violation_frac, data.min_firing_rate]),
        "table_unit_id": np.array([r["unit_id"] for r in data.unit_table], dtype=str),
        "table_label": np.array([r["label"] for r in data.unit_table], dtype=str),
        "table_sorter_unit_id": np.array([r["sorter_unit_id"] for r in data.unit_table], dtype=str),
    }
    for col in _TABLE_NUMERIC:
        arrays[f"table_{col}"] = np.array([r[col] for r in data.unit_table], dtype=float)
    atomic_savez(path, compressed=True, **arrays)
    return path


def load_sorting_check_data(path: Path | str) -> SortingCheckData:
    with np.load(path) as d:
        n = len(d["table_unit_id"])
        table = []
        for i in range(n):
            row = {"unit_id": str(d["table_unit_id"][i]),
                   "label": str(d["table_label"][i]),
                   "sorter_unit_id": str(d["table_sorter_unit_id"][i])}
            for col in _TABLE_NUMERIC:
                v = float(d[f"table_{col}"][i])
                row[col] = int(v) if col in ("channel_id", "kept", "n_spikes") else v
            table.append(row)
        floors = d["floors"]
        return SortingCheckData(
            rec_name=str(d["rec_name"][0]), channel_layout=str(d["channel_layout"][0]),
            sorter_name=str(d["sorter"][0]), sorter_version=str(d["sorter"][1]),
            electrode_ids=d["electrode_ids"], electrode_coords=d["electrode_coords"],
            unit_table=table, kept_ids=d["kept_ids"].astype(str),
            kept_channel_ids=d["kept_channel_ids"], kept_labels=d["kept_labels"].astype(str),
            templates=d["templates"], template_times_ms=d["template_times_ms"],
            min_snr=float(floors[0]), max_rp_violation_frac=float(floors[1]),
            min_firing_rate=float(floors[2]),
        )


# ── Figures ───────────────────────────────────────────────────────────────────

def draw_sorting_check_figures(
    data: SortingCheckData,
    out_dir: Path | str,
    *,
    fmt: str = "png",
    only: str | None = None,
) -> list[Path]:
    """Draw the three sorting check figures, returning the paths written.
    ``fmt`` / ``only`` are the bundle viewer's hooks, as for the detection
    checks."""
    out_dir = Path(out_dir)
    written: list[Path] = []

    def want(name: str) -> Path | None:
        if only is not None and Path(only).stem != name:
            return None
        return out_dir / f"{name}.{fmt}"

    if (path := want("1_UnitsPerElectrode")) is not None:
        _draw_units_per_electrode(data, path)
        written.append(path)
    if (path := want("2_UnitTemplates")) is not None and len(data.kept_ids):
        _draw_templates(data, path)
        written.append(path)
    if (path := want("3_UnitQuality")) is not None and data.unit_table:
        _draw_quality(data, path)
        written.append(path)
    return written


def _grid_axes(data: SortingCheckData):
    """(xs, ys, step) of the placed electrodes, y flipped so row 1 is on top
    — the MEA heatmap convention."""
    ok = np.isfinite(data.electrode_coords[:, 0])
    xy = data.electrode_coords[ok]
    step = layout_grid_step(data.channel_layout)
    return xy[:, 0], xy[:, 1], step, ok


def _draw_units_per_electrode(data: SortingCheckData, path: Path) -> None:
    from matplotlib import colormaps

    from meanap.native.chart import Chart, ColourBar, Panel, Polygon, Text, rgba
    from meanap.native.chart_paint import save_chart

    xs, ys, step, ok = _grid_axes(data)
    ids = data.electrode_ids[ok]
    counts = np.array([(data.kept_channel_ids == e).sum() for e in ids])
    vmax = max(1, int(counts.max()) if len(counts) else 1)
    blues = colormaps["Blues"]
    half = 0.27 * step
    marks = []
    for x, y, e, c in zip(xs, ys, ids, counts):
        units = [str(u) for u, ch in zip(data.kept_ids, data.kept_channel_ids) if ch == e]
        marks.append(Polygon([x - half, x + half, x + half, x - half],
                             [y - half, y - half, y + half, y + half],
                             fill=rgba(blues(c / vmax)), edge=rgba("0.6"), edge_width=0.6,
                             hover=f"electrode {int(e)}: {int(c)} unit(s) kept"
                                   + (f"\n{', '.join(units)}" if units else "")))
        marks.append(Text(x, y + 0.02 * step, str(int(c)), size=9, bold=True,
                          colour=rgba("white" if c > vmax / 2 else "0.2")))
        marks.append(Text(x, y - 0.32 * step, str(int(e)), size=5.5, va="top",
                          colour=rgba("0.45")))
    n_units = len(data.kept_ids)
    n_e = len(np.unique(data.kept_channel_ids)) if n_units else 0
    panel = Panel(
        marks=marks, bare=True, equal=True,
        xlim=(xs.min() - 0.6 * step, xs.max() + 0.6 * step),
        ylim=(ys.min() - 0.6 * step, ys.max() + 0.6 * step),
        title=f"{data.rec_name}\n{n_units} unit(s) on {n_e} of {len(ids)} electrodes "
              f"({data.sorter_name} {data.sorter_version})", title_size=10,
        colour_bar=ColourBar("Blues", 0, vmax, label="units kept on electrode",
                             ticks=[(v, str(v)) for v in range(vmax + 1)]
                             if vmax <= 10 else None,
                             fraction=0.046, tick_size=8))
    save_chart(Chart([panel], size=(6.2, 5.6)), path)


def _draw_templates(data: SortingCheckData, path: Path) -> None:
    from matplotlib import colormaps

    from meanap.native.chart import Chart, Line, Panel, Rule, Text, rgba
    from meanap.native.chart_paint import save_chart

    xs, ys, step, ok = _grid_axes(data)
    ids = data.electrode_ids[ok]
    cols = np.round((xs - xs.min()) / step).astype(int)
    rows = np.round((ys.max() - ys) / step).astype(int)
    n_cols, n_rows = cols.max() + 1, rows.max() + 1

    amp = np.nanmax(np.abs(data.templates)) if data.templates.size else 1.0
    t = data.template_times_ms
    palette = colormaps["tab10"].colors
    panels = []
    for r, c, e in zip(rows, cols, ids):
        here = np.flatnonzero(data.kept_channel_ids == e)
        marks = [Rule(0, colour=rgba("0.9"), width=0.5)]
        for k, i in enumerate(here):
            good = data.kept_labels[i] == "good"
            unit = str(data.kept_ids[i])
            marks.append(Line(t, data.templates[i], colour=rgba(palette[k % 10]), width=1.0,
                              dash="-" if good else "--", key=unit,
                              hover=[f"{unit} ({data.kept_labels[i]}), electrode {int(e)}\n"
                                     f"{v:+.1f} µV at {tt:.2f} ms"
                                     for tt, v in zip(t, data.templates[i])]))
        marks.append(Text(0.03, 0.95, f"{int(e)}" + (f"  ×{len(here)}" if len(here) > 1 else ""),
                          size=6.5, ha="left", va="top", coords="axes", colour=rgba("0.35")))
        panels.append(Panel(cell=(int(r), int(c)), marks=marks, xticks=[], yticks=[],
                            grid="", frame=rgba("0.8"),
                            xlim=(t[0], t[-1]), ylim=(-amp * 1.05, amp * 0.6),
                            sharex="time", sharey="voltage"))
    chart = Chart(panels, size=(1.55 * n_cols, 1.25 * n_rows), grid=(int(n_rows), int(n_cols)),
                  title=f"{data.rec_name} — unit templates on each electrode "
                        f"(solid: good, dashed: multi-unit; ±{amp:.0f} µV)", title_size=10,
                  gap=(4, 4))
    save_chart(chart, path)


def _draw_quality(data: SortingCheckData, path: Path) -> None:
    from meanap.native.chart import (Chart, Legend, LegendItem, Panel, Points, Rule, rgba)
    from meanap.native.chart_paint import save_chart

    tbl = data.unit_table
    snr = np.array([r["snr"] for r in tbl], dtype=float)
    rp = np.array([r["rp_violation_frac"] for r in tbl], dtype=float)
    fr = np.array([r["firing_rate"] for r in tbl], dtype=float)
    labels = np.array([r["label"] for r in tbl])
    names = [f"{r.get('unit_id') or 'sorter unit ' + str(r['sorter_unit_id'])} "
             f"({r['label']}{'' if int(r.get('kept', 0)) else ', dropped'}), "
             f"electrode {r['channel_id']}" for r in tbl]
    grey = rgba("0.5")

    left, right, items = [], [], []
    for x_pos, (lab, colour) in enumerate(_LABEL_COLORS.items()):
        m = labels == lab
        if not m.any():
            continue
        fill = rgba(colour, 0.85)
        who = [names[i] for i in np.flatnonzero(m)]
        stats = [f"{n}\nSNR {a:.2f}, {100 * b:.2f}% short ISIs, {c:.3g} Hz"
                 for n, a, b, c in zip(who, snr[m], rp[m], fr[m])]
        left.append(Points(rp[m] * 100, snr[m], fill=fill, edge=rgba("white"),
                           edge_width=0.4, size=float(np.sqrt(28)), key=lab, hover=stats))
        right.append(Points(np.full(m.sum(), x_pos)
                            + np.random.default_rng(0).uniform(-0.18, 0.18, m.sum()),
                            fr[m], fill=fill, edge=rgba("white"), edge_width=0.4,
                            size=float(np.sqrt(24)), key=lab, hover=stats))
        items.append(LegendItem(f"{lab} ({m.sum()})", rgba(colour), kind="point", key=lab))
    left += [Rule(data.min_snr, colour=grey, width=0.8, dash=":"),
             Rule(data.max_rp_violation_frac * 100, axis="x", colour=grey, width=0.8, dash=":")]
    right.append(Rule(data.min_firing_rate, colour=grey, width=0.8, dash=":"))
    text = dict(title_size=10, label_size=10, tick_size=9, grid="")
    panels = [
        Panel(cell=(0, 0), marks=left, xlabel="ISIs shorter than the refractory period (%)",
              ylabel="SNR", title="Where each unit fell against the curation floors",
              legend=Legend(items, loc="best", size=8), **text),
        Panel(cell=(0, 1), marks=right, ylog=True, ylabel="firing rate (Hz)",
              title="Firing rate by label", xlim=(-0.5, len(_LABEL_COLORS) - 0.5),
              xticks=[(k, lab) for k, lab in enumerate(_LABEL_COLORS)], zoom=(False, True),
              **text),
    ]
    chart = Chart(panels, size=(11, 4.6), grid=(1, 2), title_size=10,
                  title=f"{data.rec_name} — {len(tbl)} unit(s) from {data.sorter_name}")
    save_chart(chart, path)
