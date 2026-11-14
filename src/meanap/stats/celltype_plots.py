"""Figures for the cell-level mosaic analysis (:mod:`meanap.stats.celltypes`).

Kept apart from :mod:`meanap.stats.plots` only because that module is already
long; the drawing rules are its own (diverging maps centred on zero for signed
values, group colours from the run's scheme, MATLAB's bare axes), and the
helpers are borrowed from it rather than redefined.

Every function takes the :class:`~meanap.stats.celltypes.MosaicResults` tables,
never the analyses, so each figure redraws from the CSVs alone.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from meanap.native.chart import (Bars, Cells, Chart, ColourBar, ErrorBars, Labels, Legend,
                                 LegendItem, Line, Panel, Points, Polygon, Rule, Segments, Text,
                                 rgba)
from meanap.native.chart_paint import save_chart
from meanap.pipeline.palette import DEFAULT_SCHEME, ColorScheme
from meanap.stats.celltypes import CLASS_ORDER, CONTRASTS, VERSIONS, feature_label
from meanap.stats.decoding import FAMILY_LABELS, family_of
from meanap.stats.plots import (
    DIVERGING, INK, INK_RGBA, MUTED, MUTED_RGBA, _family_colour, _group_colors, _stars,
)

__all__ = [
    "plot_cell_autonomy",
    "plot_celltype_inventory",
    "plot_ko_scores",
    "plot_mosaic_by_age",
    "plot_mosaic_decoding",
    "plot_mosaic_effects",
    "plot_mosaic_trajectories",
    "plot_paired_differences",
]

_CONTRAST_LABELS = {
    "cell-autonomous": "Cell-autonomous\n{neg_mos} vs {pos_mos}",
    "environment-pos": "Environment, {marker}+ cells\n{pos_mos} vs {pos}",
    "environment-neg": "Environment, {marker}- cells\n{neg} vs {neg_mos}",
    "genotype": "Genotype\n{neg} vs {pos}",
    "cell-autonomous-per-week": "Cell-autonomous gap\nchange per week",
}


def _contrast_label(res, key: str) -> str:
    return _CONTRAST_LABELS[key].format(
        marker=res.meta("Marker", "marker"), pos=res.label("pos"),
        neg=res.label("neg"), pos_mos=res.label("mosP"), neg_mos=res.label("mosN"))


def _class_style(res, scheme: ColorScheme) -> dict:
    """Colour and line style per class.

    The three genotypes keep the colours they wear on every other figure in the
    folder; the mosaic group's two classes share its colour, told apart by a
    filled versus an open marker and a solid versus a dashed line.
    """
    order = res.group_order() or [g for g in (res.meta("PositiveGroup"),
                                              res.meta("MosaicGroup"),
                                              res.meta("NegativeGroup")) if g]
    colours = _group_colors(order, scheme)
    get = lambda g: colours.get(g, MUTED)  # noqa: E731
    return {
        "pos": dict(color=get(res.meta("PositiveGroup")), ls="-", fill=True),
        "mosP": dict(color=get(res.meta("MosaicGroup")), ls="-", fill=True),
        "mosN": dict(color=get(res.meta("MosaicGroup")), ls="--", fill=False),
        "neg": dict(color=get(res.meta("NegativeGroup")), ls="-", fill=True),
    }


def _ink_on(value: float, vmax: float) -> str:
    """Star colour that stays legible on the diverging map's saturated ends."""
    return "white" if np.isfinite(value) and abs(value) > 0.6 * vmax else INK


def _versions(frame: pd.DataFrame) -> list[str]:
    present = set(frame["Version"]) if "Version" in frame.columns else set()
    return [v for v in VERSIONS if v in present]


def _ranked_features(res, version: str | None = None, top: int | None = None) -> list[str]:
    """Features by the size of their pooled cell-autonomous effect."""
    e = res.effects
    sel = (e["Scope"] == "pooled") & (e["Contrast"] == "cell-autonomous")
    if version is not None:
        sel &= e["Version"] == version
    ranked = (e[sel].assign(z=lambda d: (d["Estimate"] / d["SE"]).abs())
              .groupby("Feature")["z"].max().sort_values(ascending=False))
    out = ranked.index.tolist()
    return out[:top] if top else out


def _cmap_colours(values, cmap: str, low: float, high: float) -> list:
    table = matplotlib.colormaps[cmap]
    span = (high - low) or 1.0
    return [tuple(float(c) for c in table(min(max((v - low) / span, 0.0), 1.0)))
            for v in np.asarray(values, float)]


# ── 5G1 inventory ────────────────────────────────────────────────────────────

def _nice_counts(vmax: float) -> list[int]:
    """Three round cell counts to key the dot sizes: the largest at most *vmax*."""
    steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
    k = max([i for i, v in enumerate(steps) if v <= vmax] or [0])
    return sorted({steps[max(k - 3, 0)], steps[max(k - 2, 0)], steps[k]})


def plot_celltype_inventory(res, out_path: Path, *, scheme=DEFAULT_SCHEME) -> Path | None:
    """Labelled cells per culture and age, one panel per marker.

    One dot per culture and age. Its area is the number of cells with a call
    for that marker, and its colour the share of them called positive, so a
    mosaic culture is a row of pale dots between the two ends.
    """
    inv = res.inventory
    if inv is None or inv.empty:
        return None
    markers = list(pd.unique(inv["Marker"]))
    order = res.group_order() or list(pd.unique(inv["Group"]))
    ages = sorted(inv["DIV"].unique())
    cultures = (inv[["Group", "Culture"]].drop_duplicates()
                .assign(g=lambda d: d["Group"].map({g: i for i, g in enumerate(order)}))
                .sort_values(["g", "Culture"]))
    colours = _group_colors(order, scheme)
    index = {c: i for i, c in enumerate(cultures["Culture"])}
    n_rows = len(cultures)
    counts = inv["Positive"] + inv["Negative"]
    vmax = float(max(counts.max(), 1))
    max_area = 110.0

    # Area, not radius, in proportion to the count; with a floor, so a handful
    # of cells is still a visible dot.
    def diameter(n):
        return np.sqrt(np.maximum(max_area * np.asarray(n, float) / vmax, 4.0))

    panels = []
    for k, marker in enumerate(markers):
        sub = inv[inv["Marker"] == marker]
        n = (sub["Positive"] + sub["Negative"]).to_numpy(float)
        keep = n > 0
        sub, n = sub[keep], n[keep]
        share = 100 * sub["Positive"].to_numpy(float) / n
        panels.append(Panel(
            cell=(0, k),
            marks=[Points(sub["DIV"].map(ages.index).to_numpy(float),
                          sub["Culture"].map(index).to_numpy(float),
                          fill=_cmap_colours(share, DIVERGING, 0, 100), edge=INK_RGBA,
                          edge_width=0.4, size=list(diameter(n)),
                          key=[str(c) for c in sub["Culture"]],
                          hover=[f"{c} ({g}), DIV {a:g}, {marker}: {int(p)} of {int(t)} "
                                 f"cells positive ({s:.0f}%)"
                                 for c, g, a, p, t, s in zip(sub["Culture"], sub["Group"],
                                                             sub["DIV"], sub["Positive"], n,
                                                             share)])],
            xticks=[(i, f"{a:g}") for i, a in enumerate(ages)], xlim=(-0.6, len(ages) - 0.4),
            ylim=(-0.5, n_rows - 0.5), y_down=True, title=str(marker), title_size=10,
            xlabel="DIV", ylabels=k == 0, sharey="culture", zoom=(False, True),
            yticks=[(i, str(c), rgba(colours.get(g, INK)))
                    for i, (c, g) in enumerate(zip(cultures["Culture"], cultures["Group"]))],
            tick_size=5))
    sizes = _nice_counts(vmax)
    legend = Legend([LegendItem(f"{v:g}", rgba("white"), kind="point", edge=INK_RGBA,
                                size=float(diameter(v))) for v in sizes],
                    title="labelled cells", loc="right", size=7)
    chart = Chart(panels, size=(1.6 + 1.9 * len(markers), 1.4 + 0.16 * n_rows),
                  grid=(1, len(markers)), title_size=9, legend=legend,
                  colour_bar=ColourBar(DIVERGING, 0, 100, "% of cells positive",
                                       ticks=[(v, f"{v}") for v in (0, 25, 50, 75, 100)],
                                       shrink=0.45, top=True, fraction=0.025),
                  title="Cell-type labels by culture and age  ·  dot area: labelled cells, "
                        "colour: % positive (blue = all -, red = all +)")
    return save_chart(chart, out_path)


# ── 5G2 cell-autonomy scatter ────────────────────────────────────────────────

#: A small network drawn as a cartoon: node positions on a unit disc, and edges.
#: Fixed rather than random, so the key looks the same on every run.
_GLYPH_NODES = np.array([
    (0.00, 0.80), (0.70, 0.45), (0.75, -0.40), (0.10, -0.80), (-0.65, -0.55),
    (-0.80, 0.25), (-0.15, 0.15), (0.35, -0.05),
])
_GLYPH_EDGES = ((0, 1), (0, 5), (0, 6), (1, 2), (1, 7), (2, 3), (2, 7), (3, 4),
                (3, 7), (4, 5), (4, 6), (5, 6), (6, 7))
#: Which nodes of the mosaic cartoon are marker+ — roughly half, interleaved.
_GLYPH_MOSAIC_POS = (True, False, True, False, True, False, False, True)


def _network_glyph(cx: float, cy: float, r: float, colours, emphasis=None) -> list:
    """The cartoon network at (cx, cy), radius *r*, one colour per node.

    *emphasis*, when given, is one bool per node: those nodes are drawn in full
    with a dark ring, the rest faded — the cells a comparison is about.
    """
    xy = _GLYPH_NODES * r + (cx, cy)
    lines = [(*xy[a], *xy[b]) for a, b in _GLYPH_EDGES]
    on = [emphasis is None or emphasis[k] for k in range(len(xy))]
    return [Segments(lines, colour=rgba("#c8c8c8"), width=0.9, z=1),
            Points(xy[:, 0], xy[:, 1], fill=[rgba(c, 1.0 if o else 0.25)
                                             for c, o in zip(colours, on)],
                   edge=[INK_RGBA if o else rgba("none") for o in on], edge_width=0.9,
                   size=float(np.sqrt(55)), z=2)]


def _cell_autonomy_key(res, pos_colour, neg_colour, width: float, height: float) -> list:
    """The two comparisons behind 5G2's axes, as cartoon networks, in inches.

    Horizontal: a culture whose every cell is marker- against one whose every
    cell is marker+ — two different networks. Vertical: the marker- against the
    marker+ cells of one mosaic culture — the same network drawn twice, with the
    cells being compared picked out.
    """
    marker = res.meta("Marker", "marker")
    r, gap, cy = 0.33, 1.35, height * 0.40
    mosaic = [pos_colour if p else neg_colour for p in _GLYPH_MOSAIC_POS]
    is_pos = list(_GLYPH_MOSAIC_POS)
    groups = (
        (width * 0.27, "Horizontal axis · Genotype",
         "two networks, every cell in one state",
         ((f"{res.label('neg')} culture", [neg_colour] * len(is_pos), None),
          (f"{res.label('pos')} culture", [pos_colour] * len(is_pos), None))),
        (width * 0.63, "Vertical axis · Cell-autonomous",
         "one mosaic network, its two kinds of cell compared",
         ((f"{res.label('mosN')} cells", mosaic, [not p for p in is_pos]),
          (f"{res.label('mosP')} cells", mosaic, is_pos))),
    )
    marks = []
    for cx, title, sub, (left, right) in groups:
        marks += [Text(cx, height - 0.02, title, INK_RGBA, size=9.5, va="top"),
                  Text(cx, height - 0.24, sub, MUTED_RGBA, size=7.5, va="top")]
        for dx, (label, colours, emph) in ((-gap / 2, left), (gap / 2, right)):
            marks += _network_glyph(cx + dx, cy, r, colours, emph)
            marks.append(Text(cx + dx, cy - r - 0.12, label, INK_RGBA, size=7.5, va="top"))
        marks.append(Text(cx, cy, "vs", MUTED_RGBA, size=8.5))
    divider = (groups[0][0] + groups[1][0]) / 2
    marks.append(Segments([[divider, 0.1, divider, height - 0.05]], colour=rgba("#e0e0e0"),
                          width=0.8))
    for k, (colour, text) in enumerate(((pos_colour, f"{marker}+ cell"),
                                        (neg_colour, f"{marker}- cell"))):
        y = cy + 0.15 - 0.3 * k
        marks += [Points([width * 0.86], [y], fill=rgba(colour), edge=INK_RGBA, edge_width=0.6,
                         size=float(np.sqrt(45))),
                  Text(width * 0.86 + 0.15, y, text, INK_RGBA, size=7.5, ha="left")]
    return marks


def plot_cell_autonomy(res, out_path: Path, *, scheme=DEFAULT_SCHEME) -> Path | None:
    """Cell-autonomous effect against the total genotype effect, per feature.

    On the diagonal, the mutant cell differs from its healthy neighbour as much
    as a mutant culture differs from a healthy one: the difference is the
    cell's own. On the horizontal axis, mosaic neighbours are alike and the
    genotype difference is the network's. A key above the panels draws the two
    comparisons as cartoon networks, nodes coloured by marker state in the
    colours of the two reference genotypes.
    """
    e = res.effects
    if e is None or e.empty:
        return None
    pooled = e[e["Scope"] == "pooled"]
    versions = [v for v in _versions(pooled)
                if {"cell-autonomous", "genotype"} <= set(
                    pooled.loc[pooled["Version"] == v, "Contrast"])]
    if not versions:
        return None
    n = len(versions)
    numbers = _feature_numbers(pooled, versions)
    styles = _class_style(res, scheme)
    # The key is laid out in inches, so its cartoons stay round: the width and
    # height of the band it gets.
    key_w = (5.2 * n + 2.6) * 0.92 * (5.2 * n) / (5.2 * n + 2.6)
    key_h = 7.0 * 0.86 * 1.45 / 6.45
    panels = [Panel(cell=(0, 0), span=(1, n), bare=True, equal=True, xlim=(0, key_w),
                    ylim=(0, key_h), zoom=(False, False),
                    marks=_cell_autonomy_key(res, styles["pos"]["color"],
                                             styles["neg"]["color"], key_w, key_h))]
    for k, version in enumerate(versions):
        part = pooled[pooled["Version"] == version]
        wide = part.pivot_table(index="Feature", columns="Contrast",
                                values=["Estimate", "SE", "PValueFDR"])
        x, y = wide["Estimate"]["genotype"], wide["Estimate"]["cell-autonomous"]
        xe, ye = wide["SE"]["genotype"], wide["SE"]["cell-autonomous"]
        sig = wide["PValueFDR"]["cell-autonomous"] < 0.05
        lim = float(np.nanmax(np.abs(np.r_[x + xe, x - xe, y + ye, y - ye]))) * 1.1 or 1
        feats = [f for f in numbers if f in x.index and np.isfinite(x[f])
                 and np.isfinite(y[f])]
        colours = [rgba(_family_colour(family_of(f))) for f in feats]
        filled = sig.reindex(feats).fillna(False).to_numpy(bool)
        fx, fy = x[feats].to_numpy(float), y[feats].to_numpy(float)
        families = [str(FAMILY_LABELS.get(family_of(f), family_of(f))) for f in feats]
        hover = [f"{numbers[f]}. {feature_label(f)}\ngenotype {a:+.2f}, "
                 f"cell-autonomous {b:+.2f} (SD)" for f, a, b in zip(feats, fx, fy)]
        panels.append(Panel(
            cell=(1, k), equal=True, xlim=(-lim, lim), ylim=(-lim, lim), title_size=10,
            title=VERSIONS[version],
            xlabel=f"Genotype: {res.label('neg')} vs {res.label('pos')} (SD)",
            ylabel=f"Cell-autonomous: {res.label('mosN')} vs {res.label('mosP')} (SD)",
            marks=[Line([-lim, lim], [-lim, lim], MUTED_RGBA, width=1, dash=":", z=0),
                   Rule(0, colour=MUTED_RGBA, width=0.8, z=0),
                   Rule(0, axis="x", colour=MUTED_RGBA, width=0.8, z=0),
                   ErrorBars(x[feats].to_numpy(float), y[feats].to_numpy(float),
                             xerr=1.96 * xe[feats].to_numpy(float),
                             yerr=1.96 * ye[feats].to_numpy(float), colour=rgba("#d0d0d0"),
                             width=0.8, z=1),
                   Points(fx, fy, fill=[c if f else rgba("white")
                                        for c, f in zip(colours, filled)],
                          edge=colours, edge_width=1.1, size=float(np.sqrt(30)), key=families,
                          hover=hover),
                   Labels(fx, fy, [str(numbers[f]) for f in feats], colours, keys=families)]))
    panels.append(_feature_key(numbers, cell=(1, n)))
    chart = Chart(panels, size=(5.2 * n + 2.6, 7.0), grid=(2, n + 1),
                  heights=[1.45, 5.0], widths=[5.2] * n + [2.6], title_size=9,
                  title_colour=MUTED_RGBA,
                  title="On the diagonal the difference travels with the cell "
                        "(cell-autonomous); on the horizontal axis it belongs to the network")
    return save_chart(chart, out_path)


def _feature_numbers(pooled: pd.DataFrame, versions: list[str]) -> dict[str, int]:
    """A number per feature, shared by every panel: by family, then by size.

    Within a family, features run from the largest genotype effect down, in the
    first version that has them, so the key reads in the order the eye finds
    the points — the far ones first.
    """
    gen = pooled[(pooled["Contrast"] == "genotype") & (pooled["Version"] == versions[0])]
    size = gen.set_index("Feature")["Estimate"].abs()
    feats = list(pd.unique(pooled.loc[pooled["Contrast"] == "genotype", "Feature"]))
    families = list(FAMILY_LABELS)
    feats.sort(key=lambda f: (families.index(family_of(f)) if family_of(f) in families
                              else len(families), -size.get(f, 0.0)))
    return {f: k + 1 for k, f in enumerate(feats)}


def _feature_key(numbers: dict[str, int], cell) -> Panel:
    """The number-to-feature key, grouped under each family's name."""
    rows: list[tuple[str, str, object, str]] = []
    family = None
    for feat, k in numbers.items():
        fam = family_of(feat)
        name = str(FAMILY_LABELS.get(fam, fam))
        if fam != family:
            if family is not None:
                rows.append(("", "", None, ""))
            rows.append(("head", name, _family_colour(fam), name))
            family = fam
        rows.append((str(k), feature_label(feat), _family_colour(fam), name))
    marks = [Text(0, -1.2, "Features", INK_RGBA, size=9, ha="left"),
             Text(0, -0.5, "filled: cell-autonomous FDR < 0.05  ·  open: n.s.", MUTED_RGBA,
                  size=6.5, ha="left")]
    for i, (num, text, colour, _) in enumerate(rows, start=1):
        if num == "head":
            marks.append(Text(0, i, text, rgba(colour), size=7.5, ha="left", bold=True))
        elif num:
            marks += [Text(0.07, i, num, rgba(colour), size=7, ha="right", bold=True),
                      Text(0.11, i, text, INK_RGBA, size=7, ha="left")]
    return Panel(cell=cell, bare=True, marks=marks, xlim=(0, 1), ylim=(-1.5, len(rows)),
                 y_down=True, zoom=(False, False))


# ── 5G3 contrast heatmap ─────────────────────────────────────────────────────

def _effect_cells(est: pd.DataFrame, q: pd.DataFrame, vmax: float, row_names, col_names,
                  ) -> Cells:
    values = est.to_numpy(float)
    qs = q.to_numpy(float)
    rows, cols = values.shape
    text = [[_stars(qs[i, j]) if np.isfinite(qs[i, j]) else "" for j in range(cols)]
            for i in range(rows)]
    inks = [[rgba(_ink_on(values[i, j], vmax)) for j in range(cols)] for i in range(rows)]
    hover = [[f"{row_names[i]} · {col_names[j]}\n{values[i, j]:+.2f} SD"
              + (f", FDR q = {qs[i, j]:.3g}" if np.isfinite(qs[i, j]) else "")
              if np.isfinite(values[i, j]) else "" for j in range(cols)] for i in range(rows)]
    return Cells(values, DIVERGING, -vmax, vmax, text=text, text_colour=inks, text_size=7,
                 hover=hover)


def plot_mosaic_effects(res, out_path: Path) -> Path | None:
    """Every feature against every contrast, pooled over age."""
    e = res.effects
    if e is None or e.empty:
        return None
    pooled = e[e["Scope"] == "pooled"]
    versions = _versions(pooled)
    contrasts = [c for c in CONTRASTS if c in set(pooled["Contrast"])]
    features = _ranked_features(res, versions[0])
    vmax = float(np.nanpercentile(pooled["Estimate"].abs(), 98)) or 1
    names = [feature_label(f) for f in features]
    heads = [_contrast_label(res, c) for c in contrasts]
    panels = []
    for k, version in enumerate(versions):
        part = pooled[pooled["Version"] == version]
        est = part.pivot(index="Feature", columns="Contrast", values="Estimate") \
            .reindex(index=features, columns=contrasts)
        q = part.pivot(index="Feature", columns="Contrast", values="PValueFDR") \
            .reindex(index=features, columns=contrasts)
        panels.append(Panel(
            cell=(0, k), marks=[_effect_cells(est, q, vmax, names,
                                              [h.replace("\n", ", ") for h in heads])],
            xticks=[(j, h) for j, h in enumerate(heads)], xtick_rotation=40,
            yticks=[(i, n) for i, n in enumerate(names)], ylabels=k == 0, tick_size=7,
            grid="", y_down=True, title=VERSIONS[version], title_size=10, sharey="feature"))
    chart = Chart(panels, size=(1.6 + 1.25 * len(contrasts) * len(versions),
                                1.6 + 0.26 * len(features)),
                  grid=(1, len(versions)), title_size=10,
                  title="Mosaic contrasts per feature  ·  stars: FDR-corrected",
                  colour_bar=ColourBar(DIVERGING, -vmax, vmax,
                                       "difference (SD; per week for the last column)",
                                       fraction=0.04))
    return save_chart(chart, out_path)


# ── 5G4 paired per recording ─────────────────────────────────────────────────

def plot_paired_differences(res, out_path: Path, *, top: int = 8,
                            version: str = "all") -> Path | None:
    """Marker- minus marker+ in each mosaic recording, for the strongest features."""
    paired = res.paired
    if paired is None or paired.empty:
        return None
    if version not in set(paired["Version"]):
        version = _versions(paired)[0]
    paired = paired[paired["Version"] == version]
    features = [f for f in _ranked_features(res, version) if f in set(paired["Feature"])][:top]
    if not features:
        return None
    ages = sorted(paired["DIV"].unique())
    n_cols = min(4, len(features))
    n_rows = int(np.ceil(len(features) / n_cols))
    cultures = sorted(paired["Culture"].unique())
    table = matplotlib.colormaps["tab20"]
    culture_colour = {c: rgba(table(i % 20), 0.85) for i, c in enumerate(cultures)}
    rng = np.random.default_rng(0)
    ylabel = f"{res.label('mosN')} - {res.label('mosP')} (SD)"
    panels = []
    for k, feat in enumerate(features):
        sub = paired[paired["Feature"] == feat]
        jitter = rng.uniform(-0.18, 0.18, len(sub))
        xs = sub["DIV"].map({a: i for i, a in enumerate(ages)}).to_numpy(float) + jitter
        diffs = sub["Diff"].to_numpy(float)
        means = sub.groupby("DIV")["Diff"].agg(["mean", "sem"]).reindex(ages)
        name_col = "FileName" if "FileName" in sub.columns else "Culture"
        r, c = divmod(k, n_cols)
        mean, ci = means["mean"].to_numpy(float), 1.96 * means["sem"].to_numpy(float)
        panels.append(Panel(
            cell=(r, c), title=feature_label(feat), title_size=8, sharex="age",
            xticks=[(i, f"{a:g}") for i, a in enumerate(ages)],
            xlabel="DIV" if r == n_rows - 1 else "", ylabel=ylabel if c == 0 else "",
            label_size=8,
            marks=[Points(xs, diffs, fill=[culture_colour[c] for c in sub["Culture"]],
                          size=float(np.sqrt(14)), key=[str(c) for c in sub["Culture"]],
                          hover=[f"{nm}, DIV {a:g}: {d:+.2f} SD"
                                 for nm, a, d in zip(sub[name_col], sub["DIV"], diffs)]),
                   ErrorBars(np.arange(len(ages), dtype=float), mean, yerr=ci,
                             colour=INK_RGBA, width=1.4, z=3),
                   Line(np.arange(len(ages), dtype=float), mean, INK_RGBA, width=1.4,
                        marker="o", marker_size=4, z=3,
                        hover=[f"DIV {a:g}: mean {m:+.2f} ± {e:.2f} (95% CI)"
                               for a, m, e in zip(ages, mean, ci)]),
                   Rule(0, colour=MUTED_RGBA, width=0.8)]))
    chart = Chart(panels, size=(3.0 * n_cols, 2.6 * n_rows), grid=(n_rows, n_cols),
                  title_size=9,
                  title=f"Within-recording differences ({VERSIONS[version].lower()})  ·  "
                        "one dot per recording, coloured by culture; black: mean ± 95% CI")
    return save_chart(chart, out_path)


# ── 5G5 KO-likeness ──────────────────────────────────────────────────────────

def _violin_body(values: np.ndarray, pos: float, width: float = 0.8):
    """A violin's outline as matplotlib's ``violinplot`` draws it: a Gaussian
    KDE (Scott's rule) over the data's range, at most *width* wide."""
    from scipy.stats import gaussian_kde

    values = values[np.isfinite(values)]
    if len(values) < 2 or np.ptp(values) == 0:
        return None
    grid = np.linspace(values.min(), values.max(), 100)
    density = gaussian_kde(values)(grid)
    half = density / density.max() * width / 2
    return np.r_[pos - half, (pos + half)[::-1]], np.r_[grid, grid[::-1]]


def plot_ko_scores(res, out_path: Path, *, scheme=DEFAULT_SCHEME) -> Path | None:
    """Where the mosaic cells fall on the healthy-to-mutant axis."""
    scores = res.scores
    if scores is None or scores.empty:
        return None
    versions = _versions(scores)
    style = _class_style(res, scheme)
    summary = res.score_summary
    panels = []
    for r, version in enumerate(versions):
        sub = scores[scores["Version"] == version]
        codes = [c for c in CLASS_ORDER if c in set(sub["Class"])]
        data = [sub.loc[sub["Class"] == c, "Score"].dropna().to_numpy(float) for c in codes]
        marks = []
        for k, (code, values) in enumerate(zip(codes, data)):
            body = _violin_body(values, k + 1.0)
            st = style[code]
            if body is not None:
                marks.append(Polygon(
                    body[0], body[1], fill=rgba(st["color"] if st["fill"] else "white", 0.75),
                    edge=rgba(st["color"], 0.75), edge_width=1.0,
                    dash="--" if st["ls"] == "--" else "-", key=res.label(code),
                    hover=f"{res.label(code)}: {len(values)} cells, median "
                          f"{np.median(values):.2f}"))
        medians = [float(np.median(d)) if len(d) else np.nan for d in data]
        marks += [Points(np.arange(1, len(codes) + 1, dtype=float), medians, fill=INK_RGBA,
                         size=float(np.sqrt(18)),
                         hover=[f"{res.label(c)}: median {m:.2f}"
                                for c, m in zip(codes, medians)]),
                  Rule(0, colour=MUTED_RGBA, width=0.8, dash=":")]
        auc = np.nan
        if summary is not None and not summary.empty:
            s = summary[(summary["Version"] == version)
                        & (summary["Statistic"] == "ReferenceAUC")]
            auc = float(s["Value"].iloc[0]) if not s.empty else np.nan
        panels.append(Panel(
            cell=(r, 0), marks=marks, tick_size=7,
            xticks=[(k + 1, res.label(c)) for k, c in enumerate(codes)],
            ylabel=f"{res.label('neg')}-likeness (log-odds)", zoom=(False, True),
            title=f"{VERSIONS[version]}  ·  {res.label('neg')} vs {res.label('pos')} "
                  f"held-out AUC {auc:.2f}"))

        het = sub[sub["Class"].isin(["mosP", "mosN"])]
        paired = het.groupby(["FileName", "DIV", "Class"])["Score"].mean().unstack().dropna()
        lines = np.column_stack([np.zeros(len(paired)), paired["mosP"],
                                 np.ones(len(paired)), paired["mosN"]]) \
            if len(paired) else np.zeros((0, 4))
        line_colours = [INK_RGBA if row["mosN"] > row["mosP"] else MUTED_RGBA
                        for _, row in paired.iterrows()]
        names = [f"{f}, DIV {d:g}" for f, d in paired.index]
        right = Panel(
            cell=(r, 1), xlim=(-0.4, 1.4), zoom=(False, True), tick_size=8,
            xticks=[(0, res.label("mosP")), (1, res.label("mosN"))],
            ylabel="recording mean (log-odds)", label_size=8,
            marks=[Segments(lines, colour=[rgba(c, 0.7) for c in line_colours], width=0.8),
                   Points(np.zeros(len(paired)), paired.get("mosP", []),
                          fill=rgba(style["mosP"]["color"]), size=float(np.sqrt(12)), z=3,
                          hover=[f"{n}: {res.label('mosP')} {v:.2f}"
                                 for n, v in zip(names, paired.get("mosP", []))]),
                   Points(np.ones(len(paired)), paired.get("mosN", []), fill=rgba("white"),
                          edge=rgba(style["mosN"]["color"]), edge_width=1.0,
                          size=float(np.sqrt(12)), z=3,
                          hover=[f"{n}: {res.label('mosN')} {v:.2f}"
                                 for n, v in zip(names, paired.get("mosN", []))])])
        stat = {}
        if summary is not None and not summary.empty:
            s = summary[summary["Version"] == version]
            stat = dict(zip(s["Statistic"], s["Value"]))
        if "WilcoxonP" in stat:
            right.title = (f"per recording: {stat['FractionNegHigher'] * 100:.0f}% higher "
                           f"in {res.label('mosN')}\nmodel gap "
                           f"{stat.get('ModelGap', np.nan):.2f}"
                           f" ± {stat.get('ModelGapSE', np.nan):.2f}, "
                           f"Wilcoxon p={stat['WilcoxonP']:.2g}")
            right.title_size = 8
        panels.append(right)
    chart = Chart(panels, size=(9.5, 3.4 * len(versions)), grid=(len(versions), 2),
                  widths=[1.5, 1])
    return save_chart(chart, out_path)


# ── 5G6 cell-autonomous effect by age ────────────────────────────────────────

def plot_mosaic_by_age(res, out_path: Path, *, version: str = "all") -> Path | None:
    """The cell-autonomous contrast at each age, per feature."""
    e = res.effects
    if e is None or e.empty:
        return None
    sel = (e["Contrast"] == "cell-autonomous") & e["Scope"].str.startswith("DIV")
    if version not in set(e.loc[sel, "Version"]):
        if not sel.any():
            return None
        version = _versions(e[sel])[0]
    part = e[sel & (e["Version"] == version)].copy()
    part["DIV"] = part["Scope"].str[4:].astype(float)
    features = _ranked_features(res, version)
    ages = sorted(part["DIV"].unique())
    est = part.pivot(index="Feature", columns="DIV", values="Estimate").reindex(
        index=features, columns=ages)
    q = part.pivot(index="Feature", columns="DIV", values="PValueFDR").reindex(
        index=features, columns=ages)
    vmax = float(np.nanpercentile(np.abs(est.to_numpy(float)), 98)) or 1
    n = part.groupby("DIV")["NCultures"].max().reindex(ages)
    names = [feature_label(f) for f in features]
    panel = Panel(
        marks=[_effect_cells(est, q, vmax, names, [f"DIV {a:g}" for a in ages])],
        xticks=[(j, f"{a:g}\n({int(c)})" if np.isfinite(c) else f"{a:g}")
                for j, (a, c) in enumerate(zip(ages, n))],
        xlabel="DIV (mosaic cultures)", yticks=[(i, t) for i, t in enumerate(names)],
        tick_size=7, grid="", y_down=True, title_size=10,
        title=f"Cell-autonomous difference by age ({VERSIONS[version].lower()})")
    chart = Chart([panel], size=(1.8 + 0.7 * len(ages), 1.4 + 0.26 * len(features)),
                  colour_bar=ColourBar(DIVERGING, -vmax, vmax,
                                       f"{res.label('mosN')} - {res.label('mosP')} (SD)",
                                       fraction=0.05))
    return save_chart(chart, out_path)


# ── 5G7 decoding ─────────────────────────────────────────────────────────────

def plot_mosaic_decoding(res, out_path: Path, *, top: int = 12) -> Path | None:
    """Marker state decoded from a cell's place in its own network, by age."""
    dec = res.decoding
    if dec is None or dec.empty:
        return None
    versions = _versions(dec)
    shades = {"all": INK, "tracked": "#d0730f"}
    labels: list[str] = []
    marks, items = [], []
    for k, version in enumerate(versions):
        sub = dec[dec["Version"] == version]
        scopes = ["pooled"] + sorted([s for s in sub["Scope"] if s != "pooled"],
                                     key=lambda s: float(s[4:]))
        labels = scopes if len(scopes) > len(labels) else labels
        sub = sub.set_index("Scope").reindex(scopes)
        xs = np.arange(len(scopes)) + (k - (len(versions) - 1) / 2) * 0.18
        colour = rgba(shades[version])
        name = VERSIONS[version]
        err = (sub["SD"] / np.sqrt(sub["NFolds"].clip(lower=1))).to_numpy(float)
        acc = sub["BalancedAccuracy"].to_numpy(float)
        marks += [Points(xs, sub["NullP95"], fill=rgba(shades[version], 0.6), marker="_",
                         size=float(np.sqrt(120)), edge_width=1.5, key=name,
                         hover=[f"{name}, {s}: null 95th percentile {v:.3f}"
                                for s, v in zip(scopes, sub["NullP95"])]),
                  ErrorBars(xs, acc, yerr=1.96 * err, colour=colour, width=1.25, key=name),
                  Points(xs, acc, fill=colour, size=5, key=name,
                         hover=[f"{name}, {s}: {v:.3f} ± {1.96 * e:.3f} (95% CI)"
                                + (f", p = {p:.3g}" if np.isfinite(p) else "")
                                for s, v, e, p in zip(scopes, acc, err, sub["PValue"])])]
        for x, a, e, p in zip(xs, acc, err, sub["PValue"].to_numpy(float)):
            if np.isfinite(p) and p < 0.05:
                marks.append(Text(x, a + 1.96 * e + 0.005, "*", colour, size=9, va="bottom"))
        items.append(LegendItem(name, colour, kind="point", key=name))
    marks.append(Rule(0.5, colour=MUTED_RGBA, width=1, dash=":"))
    left = Panel(cell=(0, 0), marks=marks, xticks=[(i, s) for i, s in enumerate(labels)],
                 tick_size=8, ylabel="Balanced accuracy (held-out cultures)",
                 zoom=(False, True), legend=Legend(items, loc="best", size=8),
                 title=f"{res.label('mosN')} vs {res.label('mosP')} from within-recording "
                       "features\nticks: 95th percentile of the within-recording "
                       "label-shuffle null")
    right = Panel(cell=(0, 1), bare=True)
    imp = res.importance
    if imp is not None and not imp.empty:
        version = versions[0]
        part = imp[(imp["Version"] == version) & (imp["Scope"] == "pooled")] \
            .sort_values("Importance", ascending=True).tail(top)
        y = np.arange(len(part), dtype=float)
        names = [feature_label(f) for f in part["Feature"]]
        values, sd = part["Importance"].to_numpy(float), part["SD"].to_numpy(float)
        right = Panel(
            cell=(0, 1), zoom=(True, False), tick_size=7,
            marks=[Bars(y, values, width=0.8, colour=INK_RGBA, horizontal=True,
                        hover=[f"{n}: {v:.3f} ± {s:.3f}" for n, v, s in zip(names, values, sd)]),
                   ErrorBars(values, y, xerr=sd, colour=MUTED_RGBA, width=1.25),
                   Rule(0, axis="x", colour=MUTED_RGBA, width=0.8)],
            yticks=[(v, n) for v, n in zip(y, names)],
            xlabel="drop in balanced accuracy when shuffled",
            title=f"Permutation importance, pooled ({VERSIONS[version].lower()})")
    chart = Chart([left, right], size=(10, 4.0), grid=(1, 2), widths=[1.2, 1])
    return save_chart(chart, out_path)


# ── 5G8 trajectories ─────────────────────────────────────────────────────────

def plot_mosaic_trajectories(res, out_path: Path, *, top: int = 8,
                             scheme=DEFAULT_SCHEME) -> Path | None:
    """The four classes across age, for the features with the strongest effects.

    Drawn from the tracked version when there is one — the same cells, followed
    — and from every labelled cell otherwise.
    """
    traj = res.trajectories
    if traj is None or traj.empty:
        return None
    versions = _versions(traj)
    version = "tracked" if "tracked" in versions else versions[0]
    traj = traj[traj["Version"] == version]
    # Ranked on every labelled cell, which has the power the tracked subset
    # lacks; the trajectories themselves are the tracked cells'.
    rank_on = "all" if "all" in set(res.effects["Version"]) else version
    features = [f for f in _ranked_features(res, rank_on) if f in set(traj["Feature"])][:top]
    if not features:
        return None
    style = _class_style(res, scheme)
    n_cols = min(4, len(features))
    n_rows = int(np.ceil(len(features) / n_cols))
    panels, items = [], {}
    for k, feat in enumerate(features):
        sub = traj[traj["Feature"] == feat]
        marks = []
        for code in CLASS_ORDER:
            part = sub[sub["Class"] == code].sort_values("DIV")
            if part.empty:
                continue
            st = style[code]
            colour, name = rgba(st["color"]), res.label(code)
            ages = part["DIV"].to_numpy(float)
            mean, sem = part["Mean"].to_numpy(float), part["SEM"].to_numpy(float)
            marks += [ErrorBars(ages, mean, yerr=sem, colour=colour, width=1.5, key=name),
                      Line(ages, mean, colour, width=1.5, dash="--" if st["ls"] == "--" else "-",
                           marker="o", marker_size=4,
                           marker_fill=colour if st["fill"] else rgba("white"),
                           marker_edge=colour, marker_edge_width=1.0, key=name,
                           hover=[f"{name}, DIV {a:g}: {m:+.2f} ± {s:.2f} (SEM)"
                                  for a, m, s in zip(ages, mean, sem)])]
            if k == 0:
                items[name] = LegendItem(name, colour, dash="--" if st["ls"] == "--" else "-",
                                         marker=True, key=name)
        r, c = divmod(k, n_cols)
        panels.append(Panel(cell=(r, c), marks=marks, title=feature_label(feat), title_size=8,
                            xlabel="DIV" if r == n_rows - 1 else "", label_size=8,
                            ylabel="culture mean (SD)" if c == 0 else "",
                            legend=(Legend(list(items.values()), loc="best", size=7)
                                    if k == 0 else None)))
    chart = Chart(panels, size=(3.0 * n_cols, 2.6 * n_rows), grid=(n_rows, n_cols),
                  title_size=9,
                  title=f"Trajectories by cell class ({VERSIONS[version].lower()})  ·  "
                        "mean ± SEM across cultures")
    return save_chart(chart, out_path)
