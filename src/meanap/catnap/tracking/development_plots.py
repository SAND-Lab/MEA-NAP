"""Tracked cells across development, compared between cell types.

Everything here reads ``TrackedCellMetrics.csv`` (see
:mod:`meanap.catnap.tracking.development`) and writes to
``CellTracking/DevelopmentByCellType/``:

* ``1_Trajectories``: a metric against age. There is one thin line per tracked
  cell, and the mean ± 95% CI per cell type on top, in one panel per
  experimental group.
* ``2_ChangePerCell``: each cell's rate of change (a least-squares slope over
  its own days, per week), by cell type and group. This is the paired view:
  each cell is compared with itself.
* ``3_RoleTransitions``: how cells move between cartography roles from one
  tracked day to the next, by cell type. "inactive" counts as a role, since
  dropping out of the network is itself a transition.
* ``Stats_MixedModel.csv`` and ``Stats_WithinChain.csv``: see
  :func:`mixed_model_rows` and :func:`within_chain_rows`.

**Cell types** come from the per-marker final calls. They are defined either
as one marker's ``+`` against ``-`` (the default, one definition per marker)
or by the run's group expressions (``twop_subnetwork_groups``), evaluated on
those calls. A call is three-valued, so expressions are evaluated in Kleene
logic: ``PV+ | GAD+`` holds for a PV+ cell whose GAD was never stained, but
``NeuN+ & ~GAD+`` does not, because it might be GAD+. Unknown is never
silently counted as negative.

**Every mean is a mean of chain means.** Cells in one field of view are
neither independent of each other nor of their culture. Treating 300 cells
as 300 samples would make any difference look significant.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from meanap.catnap.tracking.development import (
    ACTIVITY_CSV, CELLTYPE_PREFIX, TRACKED_METRICS_CSV, read_table,
)

OUT_DIR = "DevelopmentByCellType"

#: Okabe–Ito hues, in a fixed order: a type keeps its colour whatever else is
#: shown. Slots 4–6 are darker steps than the standard set, so the palette also
#: passes the lightness band on the viewer's dark background (#14161a). The
#: order keeps pink away from green, a pair deuteranopes confuse. Checked with
#: the dataviz palette validator in both themes.
TYPE_COLOURS = ("#0072B2", "#D55E00", "#009E73", "#BF8500", "#4892C8", "#B5649A")

#: A type needs this many tracked cells in the whole run to be compared at all.
MIN_TYPE_CELLS = 5
#: Within-chain tests need this many chains holding both types.
MIN_CHAINS = 5

ROLE_COLUMN = "NdCartDiv"
ROLE_NAMES = {1: "Peripheral", 2: "Non-hub connector", 3: "Non-hub kinless",
              4: "Provincial hub", 5: "Connector hub", 6: "Kinless hub"}
INACTIVE = "inactive"

#: Columns that identify a row rather than measure the cell.
_KEYS = {"chain", "cluster", "nDays", "Grp", "DIV", "DIVrecorded", "dayVia",
         "FileName", "Channel", "ActivityType", "Lag"}


# ── cell-type definitions ────────────────────────────────────────────────────

@dataclass
class TypeDefinition:
    """One way of splitting cells into types: ``{type name: expression}``."""

    name: str
    types: dict[str, str]


def markers_in(df: pd.DataFrame) -> list[str]:
    return [c[len(CELLTYPE_PREFIX):] for c in df.columns if c.startswith(CELLTYPE_PREFIX)]


def type_definitions(markers: list[str], group_spec=None) -> list[TypeDefinition]:
    """One ``M+`` / ``M-`` definition per marker, plus the run's groups if any.

    ``group_spec`` is what ``Params.twop_subnetwork_groups`` holds: a dict of
    ``{name: expression}``, the preset ``"E/I"``, or ``None``.
    """
    from meanap.catnap.subnetwork import default_ei_groups

    defs = [TypeDefinition(m, {f"{m}+": f"{m}+", f"{m}-": f"{m}-"}) for m in markers]
    if isinstance(group_spec, str) and group_spec.strip().upper() in ("E/I", "EI", "E_I"):
        group_spec = default_ei_groups([f"{m}+" for m in markers])
        if group_spec:
            defs.append(TypeDefinition("ExcitatoryInhibitory", dict(group_spec)))
    elif isinstance(group_spec, dict) and group_spec:
        defs.append(TypeDefinition("CellTypeGroups", dict(group_spec)))
    return defs


def _atoms(markers: list[str]) -> dict[str, tuple[str, str]]:
    """Every spelling an expression may use for a marker's sign → (marker, sign).

    ``NeuN+``, as the tracking labels are named, and ``NeuN_Positive`` /
    ``NeuN Positive``, as the spreadsheet columns that the pipeline's group
    expressions are written against are named.
    """
    out = {}
    for m in markers:
        for sign, words in (("+", ("Positive", "Pos")), ("-", ("Negative", "Neg"))):
            out[f"{m}{sign}"] = (m, sign)
            for w in words:
                out[f"{m}_{w}"] = (m, sign)
                out[f"{m} {w}"] = (m, sign)
    return out


def evaluate(expr: str, calls: pd.DataFrame, markers: list[str]) -> np.ndarray:
    """Kleene evaluation of a marker expression: 1 true, 0 false, 0.5 unknown.

    ``calls`` holds the ``celltype_<marker>`` columns (``+``, ``-`` or blank).
    """
    from meanap.catnap.subnetwork import GroupExpressionError, _tokenize

    atoms = _atoms(markers)
    tokens = _tokenize(expr, list(atoms))
    pos = 0

    def value(name: str) -> np.ndarray:
        m, sign = atoms[name]
        col = calls[CELLTYPE_PREFIX + m].fillna("").astype(str).to_numpy()
        other = "-" if sign == "+" else "+"
        return np.where(col == sign, 1.0, np.where(col == other, 0.0, 0.5))

    def parse_or():
        nonlocal pos
        v = parse_and()
        while pos < len(tokens) and tokens[pos] == "|":
            pos += 1
            v = np.maximum(v, parse_and())
        return v

    def parse_and():
        nonlocal pos
        v = parse_not()
        while pos < len(tokens) and tokens[pos] == "&":
            pos += 1
            v = np.minimum(v, parse_not())
        return v

    def parse_not():
        nonlocal pos
        if pos < len(tokens) and tokens[pos] == "~":
            pos += 1
            return 1.0 - parse_not()
        return parse_atom()

    def parse_atom():
        nonlocal pos
        if pos >= len(tokens):
            raise GroupExpressionError(f"unexpected end of expression: {expr!r}")
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            v = parse_or()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise GroupExpressionError(f"unbalanced parentheses in {expr!r}")
            pos += 1
            return v
        if tok in (")", "&", "|"):
            raise GroupExpressionError(f"unexpected {tok!r} in {expr!r}")
        return value(tok)

    out = parse_or()
    if pos != len(tokens):
        raise GroupExpressionError(f"trailing tokens in {expr!r}")
    return out


def typed(df: pd.DataFrame, definition: TypeDefinition) -> pd.DataFrame:
    """Rows of *df* with a ``CellType`` column; a row per type the cell is in.

    Types with fewer than :data:`MIN_TYPE_CELLS` cells are dropped. Fewer than
    two types left means there is nothing to compare, and the frame is empty.
    """
    parts = [df[member].assign(CellType=name)
             for name, member in memberships(df, definition).items()]
    if len(parts) < 2:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def memberships(df: pd.DataFrame, definition: TypeDefinition) -> dict[str, np.ndarray]:
    """``{type: row mask}`` for the types with :data:`MIN_TYPE_CELLS` cells or more.

    Shared by the figures and the viewer, so the two cannot disagree on who is
    which type or on which types are large enough to show.
    """
    markers = markers_in(df)
    out = {}
    for name, expr in definition.types.items():
        member = evaluate(expr, df, markers) == 1.0
        if df.loc[member, ["chain", "cluster"]].drop_duplicates().shape[0] >= MIN_TYPE_CELLS:
            out[name] = member
    return out


# ── summaries ─────────────────────────────────────────────────────────────────

def chain_means(df: pd.DataFrame, metric: str, age: str = "DIV") -> pd.DataFrame:
    """Mean of chain means per (group, type, age), with a 95% t interval over chains."""
    from scipy import stats

    per_chain = (df.dropna(subset=[metric])
                 .groupby(["Grp", "CellType", age, "chain"], sort=False)[metric].mean()
                 .reset_index())
    rows = []
    for (grp, ct, a), sub in per_chain.groupby(["Grp", "CellType", age], sort=False):
        v = sub[metric].to_numpy(dtype=float)
        n = len(v)
        half = (stats.t.ppf(0.975, n - 1) * v.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
        rows.append({"Grp": grp, "CellType": ct, age: a, "mean": v.mean(),
                     "ci": half, "nChains": n})
    return pd.DataFrame(rows)


def cell_slopes(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Each cell's least-squares slope of *metric* on its recorded age, per week."""
    rows = []
    for (chain, cluster, ct), sub in df.groupby(["chain", "cluster", "CellType"], sort=False):
        sub = sub.dropna(subset=[metric])
        days = sub["DIVrecorded"].to_numpy(dtype=float)
        if np.unique(days).size < 2:
            continue
        slope = np.polyfit(days, sub[metric].to_numpy(dtype=float), 1)[0] * 7.0
        rows.append({"chain": chain, "cluster": cluster, "Grp": sub["Grp"].iloc[0],
                     "CellType": ct, "metric": metric, "slopePerWeek": slope,
                     "nDays": int(np.unique(days).size)})
    return pd.DataFrame(rows)


def role_transitions(df: pd.DataFrame) -> pd.DataFrame:
    """Counts of role on one tracked day → role on the cell's next tracked day."""
    states = [*ROLE_NAMES.values(), INACTIVE]
    rows = []
    for (_c, _k, grp, ct), sub in df.sort_values("DIVrecorded").groupby(
            ["chain", "cluster", "Grp", "CellType"], sort=False):
        roles = [ROLE_NAMES.get(int(r), INACTIVE) if np.isfinite(r) else INACTIVE
                 for r in sub[ROLE_COLUMN].to_numpy(dtype=float)]
        for a, b in zip(roles, roles[1:]):
            rows.append((grp, ct, a, b))
    if not rows:
        return pd.DataFrame()
    t = pd.DataFrame(rows, columns=["Grp", "CellType", "from", "to"])
    counts = t.groupby(["Grp", "CellType", "from", "to"]).size().rename("n").reset_index()
    counts["from"] = pd.Categorical(counts["from"], states)
    counts["to"] = pd.Categorical(counts["to"], states)
    return counts


# ── statistics ────────────────────────────────────────────────────────────────

def _comparable_groups(df: pd.DataFrame, types: list[str]) -> tuple[list, list[str]]:
    """Groups holding every type, and a note for each that does not.

    A group with only one type cannot separate type from group: in a WT/Het/KO
    run defined by Mecp2, every WT cell is Mecp2+ and every KO cell Mecp2−.
    """
    keep, notes = [], []
    for grp, sub in df.groupby("Grp", sort=False):
        have = set(sub["CellType"])
        missing = [t for t in types if t not in have]
        if missing:
            notes.append(f"{grp} has no {', '.join(missing)} cells")
        else:
            keep.append(grp)
    return keep, notes


def mixed_model_rows(df: pd.DataFrame, metric: str, types: list[str],
                     group_order: list | None = None) -> list[dict]:
    """``metric ~ age × type × group``; chains get their own intercept and
    slope, and cells their own intercept within a chain.

    **The per-chain slope is not optional.** Fields of view develop at
    different rates, for reasons that have nothing to do with cell type (one
    network shrinks, another grows). With intercepts only, a chain with more
    cells of one type passes its slope to that type's age effect. On the Yin
    data that made node degree's age × Mecp2 term look like p = 8e-7. It was
    p = 0.59 once chains had their own slopes, matching the within-chain test.

    Age is the recorded DIV in weeks, centred. The reference type is the
    first of the definition; the reference group is the first in the run's
    order. Only groups holding every type are fitted (see
    :func:`_comparable_groups`). A cell in two overlapping types is dropped,
    because the model gives each observation one type.
    """
    import statsmodels.formula.api as smf

    base = {"metric": metric}
    d = df.dropna(subset=[metric]).copy()
    multi = d.groupby(["chain", "cluster"])["CellType"].transform("nunique") > 1
    d = d[~multi]
    groups, notes = _comparable_groups(d, types)
    d = d[d["Grp"].isin(groups)]
    present = [t for t in types if t in set(d["CellType"])]
    note = "; ".join(notes)
    if len(present) < 2 or d["chain"].nunique() < 2:
        return [dict(base, term="", note=(note or "fewer than two types to compare"))]

    order = [g for g in (group_order or []) if g in groups] + \
            [g for g in groups if g not in (group_order or [])]
    d["age"] = (d["DIVrecorded"] - d["DIVrecorded"].mean()) / 7.0
    d["cell"] = d["chain"].astype(str) + ":" + d["cluster"].astype(str)
    d["type"] = pd.Categorical(d["CellType"], present)
    d["grp"] = pd.Categorical(d["Grp"], order)
    formula = f"Q('{metric}') ~ age * C(type)" + (" * C(grp)" if len(order) > 1 else "")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = smf.mixedlm(formula, d, groups="chain", re_formula="1 + age",
                              vc_formula={"cell": "0 + C(cell)"}).fit(
                                  # tried in turn until one converges
                                  method=["lbfgs", "bfgs", "powell"])
    except Exception as e:
        return [dict(base, term="", note=f"model failed: {type(e).__name__}: {e}")]

    extra = {"nCells": d["cell"].nunique(), "nChains": d["chain"].nunique(),
             "groupsFitted": ", ".join(order), "referenceType": present[0],
             "converged": bool(fit.converged), "note": note}
    ci = fit.conf_int()
    rows = []
    for term in fit.fe_params.index:
        rows.append(dict(base, term=_readable_term(term), estimate=fit.fe_params[term],
                         se=fit.bse[term], ciLow=ci.loc[term, 0], ciHigh=ci.loc[term, 1],
                         p=fit.pvalues[term], **extra))
    return rows


def _fit_task(task: tuple) -> list[dict]:
    """One mixed model, as a pool task: ``(tag, frame, metric, types, order)``.

    BLAS is held to one thread. These are many small fits, and on the serial
    path BLAS would otherwise spread each one over every core. That cost 95
    CPU-minutes for 4 wall-minutes on the Yin run.
    """
    from threadpoolctl import threadpool_limits

    tag, frame, metric, types, order = task
    with threadpool_limits(1):
        return [dict(tag, **r) for r in mixed_model_rows(frame, metric, types, order)]


def _readable_term(term: str) -> str:
    """``C(type)[T.Mecp2-]:age`` → ``type=Mecp2-:age``."""
    return re.sub(r"C\((type|grp)\)\[T\.([^\]]*)\]", r"\1=\2", term)


def within_chain_rows(df: pd.DataFrame, metric: str, types: list[str],
                      slopes: pd.DataFrame) -> list[dict]:
    """Type differences measured *inside* each field of view, tested over chains.

    Each pair of types gets two tests, per group and pooled:

    * *level*: the mean of A minus the mean of B, on each day both are present
      and then averaged over days;
    * *slope*: the mean slope of A minus that of B.

    Each chain contributes one difference. The Wilcoxon signed-rank test is
    then taken across chains. Prep and culture are held fixed by
    construction, which a between-chain comparison cannot claim.
    """
    from itertools import combinations

    from scipy.stats import wilcoxon

    d = df.dropna(subset=[metric])
    day = d.groupby(["Grp", "chain", "DIVrecorded", "CellType"])[metric].mean().unstack()
    slope = (slopes.groupby(["Grp", "chain", "CellType"])["slopePerWeek"].mean().unstack()
             if not slopes.empty else pd.DataFrame())
    rows = []
    for a, b in combinations(types, 2):
        for kind, table in (("level", day), ("slope", slope)):
            if table.empty or a not in table or b not in table:
                continue
            diff = (table[a] - table[b]).dropna()
            if kind == "level":
                diff = diff.groupby(level=["Grp", "chain"]).mean()
            for grp in [None, *diff.index.get_level_values("Grp").unique()]:
                v = diff if grp is None else diff.xs(grp, level="Grp")
                v = v.to_numpy(dtype=float)
                p = (wilcoxon(v).pvalue if len(v) >= MIN_CHAINS and np.any(v != 0)
                     else np.nan)
                rows.append({"metric": metric, "comparison": f"{a} - {b}", "measure": kind,
                             "Grp": "all" if grp is None else grp, "nChains": len(v),
                             "medianDiff": float(np.median(v)) if len(v) else np.nan,
                             "meanDiff": float(np.mean(v)) if len(v) else np.nan,
                             "p": p})
    return rows


#: What makes one family of tests besides the question-specific columns: one
#: cell-type split, one block (activity, or network at one lag), one measure.
_FAMILY = ("definition", "block", "ActivityType", "Lag")


def add_fdr(table: pd.DataFrame, question: list[str]) -> pd.DataFrame:
    """Add ``q``, the Benjamini–Hochberg adjusted p, within each family.

    A family is one question asked of every metric, for example "does
    Mecp2- develop differently from Mecp2+ (``age:type=Mecp2-``), among the
    network metrics at 1000 ms?". That is how the figures are read, a metric
    at a time looking for the ones that differ. So the correction runs across
    metrics, and never mixes terms or blocks that answer different questions.
    Rows without a p (notes, failed fits) get no q.
    """
    from statsmodels.stats.multitest import multipletests

    if table.empty or "p" not in table.columns:
        return table
    table = table.copy()
    table["q"] = np.nan
    keys = [c for c in (*_FAMILY, *question) if c in table.columns]
    # groupby drops NaN keys by default, and Lag is NaN for the activity block
    for _, idx in table.groupby(keys, dropna=False, sort=False).groups.items():
        p = table.loc[idx, "p"]
        ok = p.notna()
        if ok.any():
            table.loc[p[ok].index, "q"] = multipletests(p[ok], method="fdr_bh")[1]
    return table


# ── figures ───────────────────────────────────────────────────────────────────

def _colours(types: list[str]) -> dict[str, str]:
    return {t: TYPE_COLOURS[i % len(TYPE_COLOURS)] for i, t in enumerate(types)}


def _group_order(df: pd.DataFrame, order: list | None) -> list:
    present = list(dict.fromkeys(df["Grp"]))
    return [g for g in (order or []) if g in present] + \
        [g for g in present if g not in (order or [])]


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color="#e4e4e4", linewidth=0.6)
    ax.set_axisbelow(True)


def plot_trajectories(df: pd.DataFrame, metric: str, label: str, types: list[str],
                      out: Path, group_order=None, title: str = "") -> None:
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    groups = _group_order(df, group_order)
    colours = _colours(types)
    means = chain_means(df, metric)
    fig, axes = plt.subplots(1, len(groups), figsize=(3.6 * len(groups) + 1.2, 4.2),
                             sharey=True, squeeze=False)
    lo_all, hi_all = np.inf, -np.inf
    for ax, grp in zip(axes[0], groups):
        sub = df[df["Grp"] == grp].dropna(subset=[metric])
        ends = []
        for ct in types:
            cells = sub[sub["CellType"] == ct].sort_values("DIV")
            segs = [g[["DIV", metric]].to_numpy(dtype=float)
                    for _, g in cells.groupby(["chain", "cluster"], sort=False) if len(g) > 1]
            if segs:
                ax.add_collection(LineCollection(segs, colors=colours[ct], linewidths=0.6,
                                                 alpha=0.12, zorder=1))
            m = means[(means["Grp"] == grp) & (means["CellType"] == ct)].sort_values("DIV")
            if m.empty:
                continue
            n_cells = cells[["chain", "cluster"]].drop_duplicates().shape[0]
            n_chains = cells["chain"].nunique()
            # types side by side at each age rather than on top of each other
            dodge = (types.index(ct) - (len(types) - 1) / 2) * 0.6
            ax.errorbar(m["DIV"] + dodge, m["mean"], yerr=m["ci"], color=colours[ct], lw=2,
                        marker="o", ms=6, capsize=3, zorder=3,
                        mec="white", mew=1, label=f"{ct} ({n_cells} cells, {n_chains} chains)")
            ends.append((m.iloc[-1]["mean"], ct, m.iloc[-1]["DIV"] + dodge))
        # direct labels at the line ends, spread apart in the order they end in
        # so close lines do not print on top of each other
        for rank, (y, ct, x) in enumerate(sorted(ends)):
            ax.annotate(ct, (x, y), xytext=(6, (rank - (len(ends) - 1) / 2) * 10),
                        textcoords="offset points", va="center", fontsize=8,
                        color="#333333")
        # Scale to the cells and the means, not the intervals. An interval over
        # two or three chains can be many times the data's range, and letting
        # it set the axis flattens everything else.
        shown = np.concatenate([sub[metric].to_numpy(dtype=float),
                                means.loc[means["Grp"] == grp, "mean"].to_numpy(dtype=float)])
        shown = shown[np.isfinite(shown)]
        if shown.size:
            ylo = min(lo_all, float(np.percentile(shown, 1)))
            yhi = max(hi_all, float(np.percentile(shown, 99)))
            lo_all, hi_all = ylo, yhi
        ax.autoscale_view(scaley=False)
        ax.set_title(str(grp), fontsize=10)
        ax.set_xlabel("Age (DIV)")
        _style(ax)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=7, frameon=False, loc="best")
    if np.isfinite(lo_all) and hi_all > lo_all:
        pad = 0.06 * (hi_all - lo_all)
        axes[0][0].set_ylim(lo_all - pad, hi_all + pad)    # shared across panels
    axes[0][0].set_ylabel(label)
    fig.suptitle(title or label, fontsize=11)
    fig.text(0.01, 0.01, "Thin lines: individual tracked cells.  Points: mean of chain "
             "means ± 95% CI over chains (axis scaled to the cells' 1st–99th "
             "percentile; a wide interval may run off it).", fontsize=7, color="#666666")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_change(slopes: pd.DataFrame, label: str, types: list[str], out: Path,
                group_order=None, title: str = "") -> None:
    import matplotlib.pyplot as plt

    groups = _group_order(slopes, group_order)
    colours = _colours(types)
    rng = np.random.default_rng(0)
    width = 0.8 / len(types)
    fig, ax = plt.subplots(figsize=(1.6 * len(groups) * len(types) + 2.2, 4.2))
    ax.axhline(0, color="#999999", lw=0.8, ls="--", zorder=0)
    for gi, grp in enumerate(groups):
        for ti, ct in enumerate(types):
            x0 = gi + (ti - (len(types) - 1) / 2) * width
            sub = slopes[(slopes["Grp"] == grp) & (slopes["CellType"] == ct)]
            if sub.empty:
                continue
            ax.scatter(x0 + rng.uniform(-width * 0.3, width * 0.3, len(sub)),
                       sub["slopePerWeek"], s=6, color=colours[ct], alpha=0.25,
                       linewidths=0, zorder=1)
            per_chain = sub.groupby("chain")["slopePerWeek"].mean()
            ax.scatter(np.full(len(per_chain), x0), per_chain, s=36, facecolor="white",
                       edgecolor=colours[ct], linewidths=1.5, zorder=3)
            ax.hlines(per_chain.median(), x0 - width * 0.35, x0 + width * 0.35,
                      color=colours[ct], lw=2.5, zorder=4)
    ax.set_xticks(range(len(groups)), [str(g) for g in groups])
    ax.set_ylabel(f"Change in {label}\nper week")
    handles = [plt.Line2D([], [], color=colours[t], marker="o", ls="", label=t) for t in types]
    handles += [plt.Line2D([], [], color="#555555", marker="o", mfc="white", ls="",
                           label="chain mean"),
                plt.Line2D([], [], color="#555555", lw=2.5, label="median of chains")]
    ax.legend(handles=handles, fontsize=7, frameon=False, loc="upper left",
              bbox_to_anchor=(1.0, 1.0))
    # cells far out of range would flatten the chain means into a line
    lo, hi = np.nanpercentile(slopes["slopePerWeek"], [1, 99]) if len(slopes) else (0, 1)
    if hi > lo:
        pad = 0.08 * (hi - lo)
        ax.set_ylim(lo - pad, hi + pad)
    _style(ax)
    ax.set_title(title or label, fontsize=11)
    fig.text(0.01, 0.01, "Dots: one tracked cell's slope over its days (1st–99th "
             "percentile shown).  Rings: chain means.", fontsize=7, color="#666666")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_role_transitions(counts: pd.DataFrame, types: list[str], out: Path,
                          group_order=None, title: str = "") -> None:
    import matplotlib.pyplot as plt

    groups = _group_order(counts, group_order)
    states = list(counts["from"].cat.categories)
    fig, axes = plt.subplots(len(types), len(groups),
                             figsize=(3.4 * len(groups) + 1, 3.2 * len(types) + 0.6),
                             squeeze=False)
    for r, ct in enumerate(types):
        for c, grp in enumerate(groups):
            ax = axes[r][c]
            sub = counts[(counts["Grp"] == grp) & (counts["CellType"] == ct)]
            if sub.empty:
                ax.axis("off")
                ax.text(0.5, 0.5, f"no {ct} cells in {grp}", ha="center", va="center",
                        fontsize=8, color="#666666", transform=ax.transAxes)
                continue
            m = (sub.pivot_table(index="from", columns="to", values="n", aggfunc="sum",
                                 observed=False)
                 .reindex(index=states, columns=states).fillna(0).to_numpy(dtype=float))
            rows = m.sum(axis=1, keepdims=True)
            frac = np.divide(m, rows, out=np.zeros_like(m), where=rows > 0)
            ax.imshow(frac, cmap="Blues", vmin=0, vmax=1)
            for i in range(len(states)):
                for j in range(len(states)):
                    if m[i, j]:
                        ax.text(j, i, int(m[i, j]), ha="center", va="center", fontsize=6,
                                color="white" if frac[i, j] > 0.6 else "#333333")
            ax.set_xticks(range(len(states)), states, rotation=60, ha="right", fontsize=6)
            ax.set_yticks(range(len(states)), states if c == 0 else [], fontsize=6)
            ax.set_title(f"{ct} · {grp}  ({int(m.sum())} transitions)", fontsize=8)
            if r == len(types) - 1:
                ax.set_xlabel("role on the next tracked day", fontsize=7)
            if c == 0:
                ax.set_ylabel("role on one day", fontsize=7)
    fig.suptitle(title or "Cartography role transitions", fontsize=11)
    fig.text(0.01, 0.005, "Shade: share of that row's cells; numbers: counts.",
             fontsize=7, color="#666666")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


# ── orchestration ─────────────────────────────────────────────────────────────

def metric_columns(df: pd.DataFrame, activity_metrics: list[str]) -> tuple[list, list]:
    """(activity metrics, network metrics) present in the table, as numbers."""
    numeric = [c for c in df.columns
               if c not in _KEYS and not c.startswith(CELLTYPE_PREFIX)
               and c != ROLE_COLUMN and pd.api.types.is_numeric_dtype(df[c])
               and df[c].notna().any()]
    if not activity_metrics:
        # no activity table to read the split from (a trimmed bundle): fall back
        # to the names CAT-NAP's activity step writes
        from meanap.catnap.group_plots import TWOP_NODE_METRICS
        activity_metrics = list(TWOP_NODE_METRICS)
    activity = [c for c in numeric if c in set(activity_metrics)]
    network = [c for c in numeric if c not in set(activity_metrics)]
    return activity, network


def _labels(activity_type: str | None) -> dict[str, str]:
    from meanap.catnap.group_plots import twop_metric_labels
    from meanap.pipeline.plotting_step4 import NETMET_NODE_METRICS

    _, node = twop_metric_labels(activity_type or "peaks")
    return {**NETMET_NODE_METRICS, "CC_raw": "Clustering Coefficient",
            "NDnorm": "Node Degree / (Active Cells − 1)",
            "NE": "Nodal Efficiency", **node}


def _safe(name: str) -> str:
    return re.sub(r"[^\w.+-]+", "_", str(name)).strip("_") or "x"


def plot_development(
    df: pd.DataFrame,
    out_dir: str | Path,
    activity_metrics: list[str],
    *,
    group_spec=None,
    group_order: list | None = None,
    timescale: str = "lag",
    figures: bool = True,
    stats: bool = True,
    max_workers: int | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> dict[str, pd.DataFrame]:
    """Every figure and table for one run's tracked-cell table.

    Returns the three tables (``slopes``, ``mixed``, ``within``) as well as
    writing them, so a caller can inspect them without re-reading the CSVs.
    """
    from meanap.pipeline.plotting_step4 import _timescale_group_folder

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    activity_cols, network_cols = metric_columns(df, activity_metrics)
    definitions = type_definitions(markers_in(df), group_spec)
    measures = (list(dict.fromkeys(df["ActivityType"]))
                if "ActivityType" in df.columns else [None])
    lags = list(dict.fromkeys(df["Lag"].dropna())) if "Lag" in df.columns else [None]
    tables: dict[str, list] = {"slopes": [], "mixed": [], "within": []}
    fits: list[tuple] = []

    for measure in measures:
        dm = df if measure is None else df[df["ActivityType"] == measure]
        labels = _labels(measure)
        mroot = out_dir if len(measures) == 1 else out_dir / _safe(measure)
        for definition in definitions:
            dt = typed(dm, definition)
            if dt.empty:
                log(f"  {definition.name}: fewer than two types with "
                    f"{MIN_TYPE_CELLS}+ tracked cells; skipped.")
                continue
            types = [t for t in definition.types if t in set(dt["CellType"])]
            droot = mroot / _safe(definition.name)
            # activity does not depend on lag: one lag's rows are the cell-days
            first = dt if lags == [None] else dt[dt["Lag"] == lags[0]]
            blocks = [("Activity", None, first, activity_cols)]
            blocks += [("Network", lag, dt if lag is None else dt[dt["Lag"] == lag],
                        network_cols) for lag in lags]
            for kind, lag, d, cols in blocks:
                where = droot / kind
                if lag is not None and kind == "Network":
                    where = where / _timescale_group_folder(lag, timescale)
                tag = {"definition": definition.name, "block": kind,
                       **({"ActivityType": measure} if measure else {}),
                       **({"Lag": lag} if kind == "Network" and lag else {})}
                for metric in cols:
                    label = labels.get(metric, metric)
                    slopes = cell_slopes(d, metric)
                    tables["slopes"] += [dict(tag, **r) for r in slopes.to_dict("records")]
                    if stats:
                        cols_needed = ["chain", "cluster", "Grp", "DIVrecorded",
                                       "CellType", metric]
                        fits.append((dict(tag), d[cols_needed].copy(), metric, types,
                                     group_order))
                        tables["within"] += [dict(tag, **r) for r in
                                             within_chain_rows(d, metric, types, slopes)]
                    if not figures:
                        continue
                    title = f"{label} — tracked cells by {definition.name}"
                    try:
                        plot_trajectories(d, metric, label, types,
                                          where / "1_Trajectories" / f"{_safe(metric)}.png",
                                          group_order, title)
                        if not slopes.empty:
                            plot_change(slopes, label, types,
                                        where / "2_ChangePerCell" / f"{_safe(metric)}.png",
                                        group_order, title)
                    except Exception as e:
                        log(f"  figure for {metric} ({definition.name}) failed: {e}")
                if figures and kind == "Network" and ROLE_COLUMN in d.columns:
                    counts = role_transitions(d)
                    try:
                        if not counts.empty:
                            plot_role_transitions(
                                counts, types, where / "3_RoleTransitions.png", group_order,
                                f"Cartography role transitions — by {definition.name}")
                    except Exception as e:
                        log(f"  role transitions ({definition.name}) failed: {e}")
            log(f"  {definition.name}: {', '.join(types)}")

    if fits:
        from meanap.pipeline.parallel import map_recordings

        log(f"  fitting {len(fits)} mixed models…")
        for rows in map_recordings(_fit_task, fits, mem_per_task_gb=0.3,
                                   max_workers=max_workers, blas_threads="1"):
            tables["mixed"] += rows

    out = {k: pd.DataFrame(v) for k, v in tables.items()}
    out["mixed"] = add_fdr(out["mixed"], ["term"])
    out["within"] = add_fdr(out["within"], ["comparison", "measure", "Grp"])
    for key, name in (("slopes", "CellSlopes.csv"), ("mixed", "Stats_MixedModel.csv"),
                      ("within", "Stats_WithinChain.csv")):
        if not out[key].empty:
            out[key].to_csv(out_dir / name, index=False)
    return out


def plot_for_run(
    tracking_dir: str | Path,
    run_dir: str | Path | None = None,
    *,
    group_spec=None,
    group_order: list | None = None,
    timescale: str = "lag",
    figures: bool = True,
    stats: bool = True,
    max_workers: int | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> dict[str, pd.DataFrame]:
    """:func:`plot_development` on a run's ``TrackedCellMetrics.csv``."""
    root = Path(tracking_dir)
    run = Path(run_dir) if run_dir is not None else root.parent
    path = root / TRACKED_METRICS_CSV
    if not path.is_file():
        log(f"Development by cell type: no {TRACKED_METRICS_CSV}; skipped.")
        return {}
    df = read_table(path)
    activity_metrics = (list(pd.read_csv(run / ACTIVITY_CSV, nrows=0).columns)
                        if (run / ACTIVITY_CSV).is_file() else [])
    log("Development by cell type:")
    return plot_development(df, root / OUT_DIR, activity_metrics, group_spec=group_spec,
                            group_order=group_order, timescale=timescale,
                            figures=figures, stats=stats, max_workers=max_workers,
                            log=log)


def main(argv=None) -> int:
    """Development-by-cell-type figures and statistics for a tracked run.

        python -m meanap.catnap.tracking.development_plots <run>[/CellTracking]

    Builds ``TrackedCellMetrics.csv`` first when it is missing. ``--groups``
    takes the same thing as ``twop_subnetwork_groups``: ``E/I``, or a JSON
    object of ``{name: expression}``.
    """
    import argparse
    import json

    from meanap.catnap.tracking.development import build_for_run

    ap = argparse.ArgumentParser(prog="meanap.catnap.tracking.development_plots",
                                 description=main.__doc__.split("\n")[0])
    ap.add_argument("path", type=Path, help="a run folder, or its CellTracking folder")
    ap.add_argument("--run", type=Path, default=None,
                    help="the run folder, when CellTracking is not inside it")
    ap.add_argument("--groups", default=None, help="'E/I' or a JSON {name: expression}")
    ap.add_argument("--group-order", nargs="+", default=None)
    ap.add_argument("--timescale", default="lag", choices=("lag", "bin"))
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--no-stats", action="store_true")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args(argv)

    root = args.path
    if not (root / "payload").is_dir() and (root / "CellTracking" / "payload").is_dir():
        root = root / "CellTracking"
    if not (root / "payload").is_dir():
        ap.error(f"{args.path} has no payload/ folder")
    groups = args.groups
    if groups and groups.strip().startswith("{"):
        groups = json.loads(groups)
    if not (root / TRACKED_METRICS_CSV).is_file():
        build_for_run(root, args.run, log=print)
    plot_for_run(root, args.run, group_spec=groups, group_order=args.group_order,
                 timescale=args.timescale, figures=not args.no_figures,
                 stats=not args.no_stats, max_workers=args.workers, log=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
