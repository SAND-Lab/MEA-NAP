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

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from meanap.pipeline.palette import DEFAULT_SCHEME, ColorScheme
from meanap.stats.celltypes import CLASS_ORDER, CONTRASTS, VERSIONS, feature_label
from meanap.stats.decoding import FAMILY_LABELS, family_of
from meanap.stats.plots import (
    DIVERGING, INK, MUTED, _bare, _family_colour, _group_colors, _save, _stars,
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
    area = lambda n: np.maximum(max_area * np.asarray(n, float) / vmax, 4.0)  # noqa: E731

    fig, axes = plt.subplots(1, len(markers), figsize=(1.6 + 1.9 * len(markers),
                                                       1.4 + 0.16 * n_rows),
                             sharey=True, squeeze=False)
    sc = None
    for ax, marker in zip(axes[0], markers):
        sub = inv[inv["Marker"] == marker]
        n = (sub["Positive"] + sub["Negative"]).to_numpy(float)
        keep = n > 0
        sub, n = sub[keep], n[keep]
        x = sub["DIV"].map(ages.index).to_numpy()
        y = sub["Culture"].map(index).to_numpy()
        sc = ax.scatter(x, y, s=area(n), c=100 * sub["Positive"].to_numpy() / n,
                        cmap=DIVERGING, vmin=0, vmax=100,
                        edgecolors=INK, linewidths=0.4, zorder=3)
        ax.set_xticks(range(len(ages)), [f"{a:g}" for a in ages])
        ax.set_xlim(-0.6, len(ages) - 0.4)
        ax.set_ylim(n_rows - 0.5, -0.5)
        ax.set_title(marker, fontsize=10)
        ax.set_xlabel("DIV")
        _bare(ax)
    ax0 = axes[0][0]
    ax0.set_yticks(range(n_rows), cultures["Culture"], fontsize=5)
    for tick, grp in zip(ax0.get_yticklabels(), cultures["Group"]):
        tick.set_color(colours.get(grp, INK))

    cbar = fig.colorbar(sc, ax=axes[0].tolist(), fraction=0.025, pad=0.02,
                        shrink=0.45, anchor=(0.0, 1.0))
    cbar.set_label("% of cells positive", fontsize=8)
    cbar.set_ticks([0, 25, 50, 75, 100])
    cbar.ax.tick_params(labelsize=7)
    cbar.outline.set_visible(False)
    # The size key sits under the colour bar, in figure coordinates.
    sizes = _nice_counts(vmax)
    handles = [plt.scatter([], [], s=float(area(v)), facecolor="white",
                           edgecolors=INK, linewidths=0.6) for v in sizes]
    fig.legend(handles, [f"{v:g}" for v in sizes], title="labelled cells",
               loc="upper left", bbox_to_anchor=(cbar.ax.get_position().x0, 0.42),
               frameon=False, fontsize=7, title_fontsize=8, labelspacing=1.0,
               borderpad=0, handletextpad=0.8)
    fig.suptitle("Cell-type labels by culture and age  ·  dot area: labelled cells, "
                 "colour: % positive (blue = all -, red = all +)", fontsize=9)
    return _save(fig, out_path)


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


def _network_glyph(ax, cx: float, cy: float, r: float, colours, emphasis=None) -> None:
    """Draw the cartoon network at (cx, cy), radius *r*, one colour per node.

    *emphasis*, when given, is one bool per node: those nodes are drawn in full
    with a dark ring, the rest faded — the cells a comparison is about.
    """
    xy = _GLYPH_NODES * r + (cx, cy)
    for a, b in _GLYPH_EDGES:
        ax.plot(*xy[[a, b]].T, color="#c8c8c8", lw=0.9, zorder=1)
    for k, (x, y) in enumerate(xy):
        on = emphasis is None or emphasis[k]
        ax.scatter(x, y, s=55, color=colours[k], alpha=1.0 if on else 0.25,
                   edgecolors=INK if on else "none", linewidths=0.9 if on else 0,
                   zorder=2)


def _cell_autonomy_key(ax, res, pos_colour, neg_colour) -> None:
    """The two comparisons behind 5G2's axes, as cartoon networks.

    Horizontal: a culture whose every cell is marker- against one whose every
    cell is marker+ — two different networks. Vertical: the marker- against the
    marker+ cells of one mosaic culture — the same network drawn twice, with the
    cells being compared picked out.
    """
    marker = res.meta("Marker", "marker")
    # Lay the key out in inches, so the cartoons stay round whatever the
    # figure's width: the axes' data units are made to be inches.
    fig = ax.figure
    box = ax.get_position()
    width = box.width * fig.get_figwidth()
    height = box.height * fig.get_figheight()
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis("off")

    r, gap, cy = 0.33, 1.35, height * 0.40
    mosaic = [pos_colour if p else neg_colour for p in _GLYPH_MOSAIC_POS]
    is_pos = list(_GLYPH_MOSAIC_POS)
    panels = (
        (width * 0.27, "Horizontal axis · Genotype",
         "two networks, every cell in one state",
         ((f"{res.label('neg')} culture", [neg_colour] * len(is_pos), None),
          (f"{res.label('pos')} culture", [pos_colour] * len(is_pos), None))),
        (width * 0.63, "Vertical axis · Cell-autonomous",
         "one mosaic network, its two kinds of cell compared",
         ((f"{res.label('mosN')} cells", mosaic, [not p for p in is_pos]),
          (f"{res.label('mosP')} cells", mosaic, is_pos))),
    )
    for cx, title, sub, (left, right) in panels:
        ax.text(cx, height - 0.02, title, ha="center", va="top", fontsize=9.5,
                color=INK)
        ax.text(cx, height - 0.24, sub, ha="center", va="top", fontsize=7.5,
                color=MUTED)
        for dx, (label, colours, emph) in ((-gap / 2, left), (gap / 2, right)):
            _network_glyph(ax, cx + dx, cy, r, colours, emph)
            ax.text(cx + dx, cy - r - 0.12, label, ha="center", va="top",
                    fontsize=7.5, color=INK)
        ax.text(cx, cy, "vs", ha="center", va="center", fontsize=8.5, color=MUTED)
    divider = (panels[0][0] + panels[1][0]) / 2
    ax.plot([divider, divider], [0.1, height - 0.05], color="#e0e0e0", lw=0.8)
    for k, (colour, text) in enumerate(((pos_colour, f"{marker}+ cell"),
                                        (neg_colour, f"{marker}- cell"))):
        y = cy + 0.15 - 0.3 * k
        ax.scatter(width * 0.86, y, s=45, color=colour, edgecolors=INK,
                   linewidths=0.6)
        ax.text(width * 0.86 + 0.15, y, text, va="center", fontsize=7.5, color=INK)


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
    # Fixed margins rather than tight_layout, which cannot place the key's
    # spanning axes; the key reads its own size in inches from them.
    fig = plt.figure(figsize=(5.2 * n + 2.6, 7.0))
    grid = fig.add_gridspec(2, n + 1, height_ratios=(1.45, 5.0),
                            width_ratios=[5.2] * n + [2.6], left=0.07, right=0.99,
                            top=0.94, bottom=0.08, hspace=0.18, wspace=0.22)
    styles = _class_style(res, scheme)
    _cell_autonomy_key(fig.add_subplot(grid[0, :n]), res,
                       styles["pos"]["color"], styles["neg"]["color"])
    axes = [fig.add_subplot(grid[1, k]) for k in range(n)]
    for ax, version in zip(axes, versions):
        part = pooled[pooled["Version"] == version]
        wide = part.pivot_table(index="Feature", columns="Contrast",
                                values=["Estimate", "SE", "PValueFDR"])
        x, y = wide["Estimate"]["genotype"], wide["Estimate"]["cell-autonomous"]
        xe, ye = wide["SE"]["genotype"], wide["SE"]["cell-autonomous"]
        sig = wide["PValueFDR"]["cell-autonomous"] < 0.05
        lim = float(np.nanmax(np.abs(np.r_[x + xe, x - xe, y + ye, y - ye]))) * 1.1 or 1
        ax.plot([-lim, lim], [-lim, lim], color=MUTED, lw=1, ls=":")
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.axvline(0, color=MUTED, lw=0.8)
        ax.errorbar(x, y, xerr=1.96 * xe, yerr=1.96 * ye, fmt="none",
                    ecolor="#d0d0d0", elinewidth=0.8, zorder=1)
        feats = [f for f in numbers if f in x.index and np.isfinite(x[f])
                 and np.isfinite(y[f])]
        colours = [_family_colour(family_of(f)) for f in feats]
        filled = sig.reindex(feats).fillna(False).to_numpy(bool)
        ax.scatter(x[feats], y[feats], s=30, zorder=3, linewidths=1.1,
                   facecolors=[c if f else "white" for c, f in zip(colours, filled)],
                   edgecolors=colours)
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_aspect("equal")
        ax.set_xlabel(f"Genotype: {res.label('neg')} vs {res.label('pos')} (SD)")
        ax.set_ylabel(f"Cell-autonomous: {res.label('mosN')} vs {res.label('mosP')} (SD)")
        ax.set_title(VERSIONS[version], fontsize=10)
        _bare(ax)
        _number_points(ax, x[feats].to_numpy(), y[feats].to_numpy(),
                       [str(numbers[f]) for f in feats], colours)
    _feature_key(fig.add_subplot(grid[1, n]), numbers)
    fig.suptitle("On the diagonal the difference travels with the cell "
                 "(cell-autonomous); on the horizontal axis it belongs to the network",
                 fontsize=9, color=MUTED, y=0.995)
    return _save(fig, out_path)


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


def _feature_key(ax, numbers: dict[str, int]) -> None:
    """The number-to-feature key, grouped under each family's name."""
    ax.axis("off")
    ax.set_xlim(0, 1)
    rows: list[tuple[str, str, object]] = []
    family = None
    for feat, k in numbers.items():
        fam = family_of(feat)
        if fam != family:
            if family is not None:
                rows.append(("", "", None))
            rows.append(("head", FAMILY_LABELS.get(fam, fam), _family_colour(fam)))
            family = fam
        rows.append((str(k), feature_label(feat), _family_colour(fam)))
    ax.set_ylim(len(rows), -1.5)
    ax.text(0, -1.2, "Features", fontsize=9, color=INK, va="center")
    ax.text(0, -0.5, "filled: cell-autonomous FDR < 0.05  ·  open: n.s.",
            fontsize=6.5, color=MUTED, va="center")
    for i, (num, text, colour) in enumerate(rows, start=1):
        if num == "head":
            ax.text(0, i, text, fontsize=7.5, color=colour, va="center",
                    fontweight="bold")
        elif num:
            ax.text(0.07, i, num, fontsize=7, color=colour, va="center", ha="right",
                    fontweight="bold")
            ax.text(0.11, i, text, fontsize=7, color=INK, va="center")


def _number_points(ax, x, y, labels, colours, *, fontsize: float = 6.5) -> None:
    """Number each point, nudging the numbers apart so none sits on another.

    Works in pixels. Each number starts just above its point. Numbers that
    overlap are pushed apart *sideways*, keeping the left-to-right order of
    their points, so a dense cluster becomes a row of numbers whose leaders fan
    out without crossing; a stack would leave it unclear which number is
    whose. Numbers are pushed up off any point they cover, and every number
    that ends up away from its point gets a leader.
    """
    ax.apply_aspect()
    to_px = ax.transData
    anchors = to_px.transform(np.c_[x, y])
    px = ax.figure.dpi / 72
    w = np.array([(0.62 * fontsize * len(t) + 3) * px for t in labels])
    h = np.full(len(labels), (fontsize + 1.5) * px)
    dot = 4.5 * px
    pos = anchors + np.c_[np.zeros(len(labels)), dot + h / 2 + px]
    box = ax.get_window_extent()
    lo = np.c_[box.x0 + w / 2, box.y0 + h / 2]
    hi = np.c_[box.x1 - w / 2, box.y1 - h / 2]
    # Left-to-right rank of the points, to break ties when two coincide.
    rank = np.argsort(np.argsort(anchors[:, 0] + 1e-6 * np.arange(len(labels))))
    for _ in range(400):
        moved = False
        for i in range(len(labels)):
            d = pos[i] - pos
            ox = (w[i] + w) / 2 - np.abs(d[:, 0])
            oy = (h[i] + h) / 2 - np.abs(d[:, 1])
            hit = (ox > 0.5) & (oy > 0.5)
            hit[i] = False
            for j in np.flatnonzero(hit):
                sign = 1.0 if rank[i] > rank[j] else -1.0
                pos[i, 0] += sign * ox[j] / 2
                pos[j, 0] -= sign * ox[j] / 2
                moved = True
            d = pos[i] - anchors
            ox = w[i] / 2 + dot - np.abs(d[:, 0])
            oy = h[i] / 2 + dot - np.abs(d[:, 1])
            # Off a covered point, always on the side of its own point the
            # number already sits — pushing it the other way only bounces it
            # between two points.
            side = 1.0 if pos[i, 1] >= anchors[i, 1] else -1.0
            for k in np.flatnonzero((ox > 0.5) & (oy > 0.5)):
                pos[i, 1] = anchors[k, 1] + side * (h[i] / 2 + dot + 0.5)
                moved = True
        pos = np.clip(pos, lo, hi)
        if not moved:
            break
    back = to_px.inverted()
    for (px0, py0), (lx, ly), text, colour, wi, hi_ in zip(
            anchors, pos, labels, colours, w, h):
        tx, ty = back.transform((lx, ly))
        # Directly above its own point, a number needs no leader.
        beside = abs(lx - px0) < wi / 2 and 0 < ly - py0 < dot + h[0] + 2 * px
        if not beside:
            ex = np.clip(px0, lx - wi / 2, lx + wi / 2)
            ey = ly - hi_ / 2 if ly > py0 else ly + hi_ / 2
            ax.plot(*back.transform([(px0, py0), (ex, ey)]).T, color=colour,
                    alpha=0.6, lw=0.6, zorder=2.5)
        ax.text(tx, ty, text, fontsize=fontsize, color=colour, ha="center",
                va="center", fontweight="bold", zorder=4)


# ── 5G3 contrast heatmap ─────────────────────────────────────────────────────

def plot_mosaic_effects(res, out_path: Path) -> Path | None:
    """Every feature against every contrast, pooled over age."""
    e = res.effects
    if e is None or e.empty:
        return None
    pooled = e[e["Scope"] == "pooled"]
    versions = _versions(pooled)
    contrasts = [c for c in CONTRASTS if c in set(pooled["Contrast"])]
    features = _ranked_features(res, versions[0])
    fig, axes = plt.subplots(1, len(versions),
                             figsize=(1.6 + 1.25 * len(contrasts) * len(versions),
                                      1.6 + 0.26 * len(features)),
                             squeeze=False, sharey=True)
    vmax = float(np.nanpercentile(pooled["Estimate"].abs(), 98)) or 1
    for ax, version in zip(axes[0], versions):
        part = pooled[pooled["Version"] == version]
        est = part.pivot(index="Feature", columns="Contrast", values="Estimate") \
            .reindex(index=features, columns=contrasts)
        q = part.pivot(index="Feature", columns="Contrast", values="PValueFDR") \
            .reindex(index=features, columns=contrasts)
        im = ax.imshow(est.to_numpy(float), cmap=DIVERGING, vmin=-vmax, vmax=vmax,
                       aspect="auto")
        for i in range(len(features)):
            for j in range(len(contrasts)):
                s = _stars(q.iat[i, j]) if np.isfinite(q.iat[i, j]) else ""
                if s:
                    ax.text(j, i, s, ha="center", va="center", fontsize=7,
                            color=_ink_on(est.iat[i, j], vmax))
        ax.set_xticks(range(len(contrasts)),
                      [_contrast_label(res, c) for c in contrasts],
                      fontsize=7, rotation=40, ha="right")
        ax.set_title(VERSIONS[version], fontsize=10)
    axes[0][0].set_yticks(range(len(features)), [feature_label(f) for f in features],
                          fontsize=7)
    cbar = fig.colorbar(im, ax=axes[0].tolist(), fraction=0.04, pad=0.02)
    cbar.set_label("difference (SD; per week for the last column)", fontsize=8)
    fig.suptitle("Mosaic contrasts per feature  ·  stars: FDR-corrected", fontsize=10)
    return _save(fig, out_path)


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
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.0 * n_cols, 2.6 * n_rows),
                             squeeze=False, sharex=True)
    cultures = sorted(paired["Culture"].unique())
    cmap = plt.get_cmap("tab20")
    culture_colour = {c: cmap(i % 20) for i, c in enumerate(cultures)}
    rng = np.random.default_rng(0)
    for ax, feat in zip(axes.flat, features):
        sub = paired[paired["Feature"] == feat]
        jitter = rng.uniform(-0.18, 0.18, len(sub))
        xs = sub["DIV"].map({a: i for i, a in enumerate(ages)}).to_numpy() + jitter
        ax.scatter(xs, sub["Diff"], s=14, c=[culture_colour[c] for c in sub["Culture"]],
                   edgecolors="none", alpha=0.85)
        means = sub.groupby("DIV")["Diff"].agg(["mean", "sem"]).reindex(ages)
        ax.errorbar(range(len(ages)), means["mean"], yerr=1.96 * means["sem"],
                    fmt="o-", color=INK, ms=4, lw=1.4, capsize=0, zorder=3)
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_title(feature_label(feat), fontsize=8)
        ax.set_xticks(range(len(ages)), [f"{a:g}" for a in ages], fontsize=7)
        _bare(ax)
    for ax in axes.flat[len(features):]:
        ax.axis("off")
    for ax in axes[:, 0]:
        ax.set_ylabel(f"{res.label('mosN')} - {res.label('mosP')} (SD)", fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("DIV", fontsize=8)
    fig.suptitle(f"Within-recording differences ({VERSIONS[version].lower()})  ·  "
                 "one dot per recording, coloured by culture; black: mean ± 95% CI",
                 fontsize=9)
    fig.tight_layout()
    return _save(fig, out_path)


# ── 5G5 KO-likeness ──────────────────────────────────────────────────────────

def plot_ko_scores(res, out_path: Path, *, scheme=DEFAULT_SCHEME) -> Path | None:
    """Where the mosaic cells fall on the healthy-to-mutant axis."""
    scores = res.scores
    if scores is None or scores.empty:
        return None
    versions = _versions(scores)
    style = _class_style(res, scheme)
    fig, axes = plt.subplots(len(versions), 2, figsize=(9.5, 3.4 * len(versions)),
                             squeeze=False, gridspec_kw={"width_ratios": [1.5, 1]})
    for row, version in zip(axes, versions):
        sub = scores[scores["Version"] == version]
        ax = row[0]
        codes = [c for c in CLASS_ORDER if c in set(sub["Class"])]
        data = [sub.loc[sub["Class"] == c, "Score"].dropna().to_numpy() for c in codes]
        parts = ax.violinplot(data, showextrema=False, widths=0.8)
        for body, code in zip(parts["bodies"], codes):
            body.set_facecolor(style[code]["color"] if style[code]["fill"] else "white")
            body.set_edgecolor(style[code]["color"])
            body.set_linestyle(style[code]["ls"])
            body.set_alpha(0.75)
        ax.scatter(range(1, len(codes) + 1), [np.median(d) for d in data],
                   color=INK, s=18, zorder=3)
        ax.set_xticks(range(1, len(codes) + 1), [res.label(c) for c in codes], fontsize=8)
        ax.axhline(0, color=MUTED, lw=0.8, ls=":")
        summary = res.score_summary
        auc = np.nan
        if summary is not None and not summary.empty:
            s = summary[(summary["Version"] == version)
                        & (summary["Statistic"] == "ReferenceAUC")]
            auc = float(s["Value"].iloc[0]) if not s.empty else np.nan
        ax.set_ylabel(f"{res.label('neg')}-likeness (log-odds)")
        ax.set_title(f"{VERSIONS[version]}  ·  {res.label('neg')} vs {res.label('pos')} "
                     f"held-out AUC {auc:.2f}", fontsize=9)
        _bare(ax)

        ax = row[1]
        het = sub[sub["Class"].isin(["mosP", "mosN"])]
        paired = het.groupby(["FileName", "DIV", "Class"])["Score"].mean().unstack().dropna()
        for _, r in paired.iterrows():
            colour = INK if r["mosN"] > r["mosP"] else MUTED
            ax.plot([0, 1], [r["mosP"], r["mosN"]], color=colour, lw=0.8, alpha=0.7)
        ax.scatter(np.zeros(len(paired)), paired["mosP"], s=12,
                   color=style["mosP"]["color"], zorder=3)
        ax.scatter(np.ones(len(paired)), paired["mosN"], s=12, facecolors="white",
                   edgecolors=style["mosN"]["color"], zorder=3)
        ax.set_xticks([0, 1], [res.label("mosP"), res.label("mosN")], fontsize=8)
        ax.set_xlim(-0.4, 1.4)
        stat = {}
        if summary is not None and not summary.empty:
            s = summary[summary["Version"] == version]
            stat = dict(zip(s["Statistic"], s["Value"]))
        if "WilcoxonP" in stat:
            ax.set_title(f"per recording: {stat['FractionNegHigher'] * 100:.0f}% higher "
                         f"in {res.label('mosN')}\nmodel gap {stat.get('ModelGap', np.nan):.2f}"
                         f" ± {stat.get('ModelGapSE', np.nan):.2f}, "
                         f"Wilcoxon p={stat['WilcoxonP']:.2g}", fontsize=8)
        ax.set_ylabel("recording mean (log-odds)", fontsize=8)
        _bare(ax)
    fig.tight_layout()
    return _save(fig, out_path)


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
    fig, ax = plt.subplots(figsize=(1.8 + 0.7 * len(ages), 1.4 + 0.26 * len(features)))
    im = ax.imshow(est.to_numpy(float), cmap=DIVERGING, vmin=-vmax, vmax=vmax,
                   aspect="auto")
    for i in range(len(features)):
        for j in range(len(ages)):
            s = _stars(q.iat[i, j]) if np.isfinite(q.iat[i, j]) else ""
            if s:
                ax.text(j, i, s, ha="center", va="center", fontsize=7,
                        color=_ink_on(est.iat[i, j], vmax))
    n = part.groupby("DIV")["NCultures"].max().reindex(ages)
    ax.set_xticks(range(len(ages)), [f"{a:g}\n({int(c)})" if np.isfinite(c) else f"{a:g}"
                                     for a, c in zip(ages, n)], fontsize=7)
    ax.set_xlabel("DIV (mosaic cultures)", fontsize=8)
    ax.set_yticks(range(len(features)), [feature_label(f) for f in features], fontsize=7)
    cbar = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.03)
    cbar.set_label(f"{res.label('mosN')} - {res.label('mosP')} (SD)", fontsize=8)
    ax.set_title(f"Cell-autonomous difference by age ({VERSIONS[version].lower()})",
                 fontsize=10)
    fig.tight_layout()
    return _save(fig, out_path)


# ── 5G7 decoding ─────────────────────────────────────────────────────────────

def plot_mosaic_decoding(res, out_path: Path, *, top: int = 12) -> Path | None:
    """Marker state decoded from a cell's place in its own network, by age."""
    dec = res.decoding
    if dec is None or dec.empty:
        return None
    versions = _versions(dec)
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10, 4.0),
                                  gridspec_kw={"width_ratios": [1.2, 1]})
    shades = {"all": INK, "tracked": "#d0730f"}
    labels = []
    for k, version in enumerate(versions):
        sub = dec[dec["Version"] == version]
        scopes = ["pooled"] + sorted([s for s in sub["Scope"] if s != "pooled"],
                                     key=lambda s: float(s[4:]))
        labels = scopes if len(scopes) > len(labels) else labels
        sub = sub.set_index("Scope").reindex(scopes)
        xs = np.arange(len(scopes)) + (k - (len(versions) - 1) / 2) * 0.18
        ax.scatter(xs, sub["NullP95"], marker="_", s=120, color=shades[version],
                   alpha=0.6, linewidths=1.5)
        err = sub["SD"] / np.sqrt(sub["NFolds"].clip(lower=1))
        ax.errorbar(xs, sub["BalancedAccuracy"], yerr=1.96 * err, fmt="o",
                    color=shades[version], ms=5, capsize=0, label=VERSIONS[version])
        for x, (_, r) in zip(xs, sub.iterrows()):
            if np.isfinite(r["PValue"]) and r["PValue"] < 0.05:
                ax.text(x, r["BalancedAccuracy"] + 1.96 * err[_] + 0.005, "*",
                        ha="center", fontsize=9, color=shades[version])
    ax.axhline(0.5, color=MUTED, ls=":", lw=1)
    ax.set_xticks(range(len(labels)), labels, fontsize=8)
    ax.set_ylabel("Balanced accuracy (held-out cultures)")
    ax.set_title(f"{res.label('mosN')} vs {res.label('mosP')} from within-recording "
                 "features\nticks: 95th percentile of the within-recording "
                 "label-shuffle null", fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    _bare(ax)

    imp = res.importance
    if imp is not None and not imp.empty:
        version = versions[0]
        part = imp[(imp["Version"] == version) & (imp["Scope"] == "pooled")] \
            .sort_values("Importance", ascending=True).tail(top)
        ax2.barh(range(len(part)), part["Importance"], xerr=part["SD"],
                 color=INK, ecolor=MUTED)
        ax2.set_yticks(range(len(part)), [feature_label(f) for f in part["Feature"]],
                       fontsize=7)
        ax2.axvline(0, color=MUTED, lw=0.8)
        ax2.set_xlabel("drop in balanced accuracy when shuffled")
        ax2.set_title(f"Permutation importance, pooled ({VERSIONS[version].lower()})",
                      fontsize=9)
        _bare(ax2)
    else:
        ax2.axis("off")
    fig.tight_layout()
    return _save(fig, out_path)


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
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.0 * n_cols, 2.6 * n_rows),
                             squeeze=False)
    for ax, feat in zip(axes.flat, features):
        sub = traj[traj["Feature"] == feat]
        for code in CLASS_ORDER:
            part = sub[sub["Class"] == code].sort_values("DIV")
            if part.empty:
                continue
            st = style[code]
            ax.errorbar(part["DIV"], part["Mean"], yerr=part["SEM"], color=st["color"],
                        ls=st["ls"], marker="o", ms=4, lw=1.5, capsize=0,
                        mfc=st["color"] if st["fill"] else "white", label=res.label(code))
        ax.set_title(feature_label(feat), fontsize=8)
        _bare(ax)
    for ax in axes.flat[len(features):]:
        ax.axis("off")
    for ax in axes[:, 0]:
        ax.set_ylabel("culture mean (SD)", fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("DIV", fontsize=8)
    axes.flat[0].legend(frameon=False, fontsize=7)
    fig.suptitle(f"Trajectories by cell class ({VERSIONS[version].lower()})  ·  "
                 "mean ± SEM across cultures", fontsize=9)
    fig.tight_layout()
    return _save(fig, out_path)
