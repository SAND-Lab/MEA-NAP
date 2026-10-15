"""Cell-level analysis of an X-linked mosaic: is a deficit the cell's own?

Every other analysis in step 5 treats a *recording* as the observation. This
one goes down to the cell, for the case CAT-NAP can answer and an electrode
array cannot: a heterozygous female culture of an X-linked gene (Mecp2 is the
motivating one) is a mosaic, and staining says which cells express the gene.
Mutant and healthy cells then share one dish, one network and one recording,
so comparing them separates two things a WT-vs-KO comparison cannot:

* a **cell-autonomous** effect — the mutant cell differs from its healthy
  neighbour in the same network, and
* an **environment** (non-cell-autonomous) effect — a healthy cell in a
  mutant network differs from a healthy cell in a healthy one.

Four classes of cell make that a 2x2 with one corner shared::

                       marker+ cell        marker- cell
    healthy culture    WT                  —
    mosaic culture     Het marker+         Het marker-
    mutant culture     —                   KO

and the contrasts reported are Het- vs Het+ (cell-autonomous), Het+ vs WT
(environment acting on a healthy cell), KO vs Het- (environment acting on a
mutant cell) and KO vs WT (the total, which is what a recording-level
comparison sees). If the WT-vs-KO difference is cell-autonomous, the first
contrast reproduces it; if it is the network's, the first is ~0 and the
environment contrasts carry it.

The groups are identified from the calls, not their names: the mosaic group is
the one whose labelled cells are a real mix of + and -, and the references are
groups whose labelled cells are (almost) all + or all -. In those reference
groups the marker state follows from the genotype, so *every* cell in them is
used, not only the labelled ones — on the Yin run that is the difference
between 3 WT cultures and 37.

**Cells are not independent.** Every model carries a culture random intercept
with recordings nested inside it, and the tracked version adds the cell itself,
since a tracked cell contributes a row per day. Cross-validation holds out
whole cultures.

Two versions of everything are run, as the user asked for both:

* ``all`` — every labelled cell-day, tracked or not, and
* ``tracked`` — only cells followed across days, with the cell as a random
  effect and the longitudinal views that only tracking allows.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from meanap.stats.comparisons import fdr_correct
from meanap.stats.dataset import (
    _ACTIVITY_NODE, _NETWORK_NODE, _read_first, _resolve_root, derive_culture_ids,
    metric_labels,
)

__all__ = [
    "CONTRASTS",
    "CellTable",
    "MosaicResults",
    "VERSIONS",
    "load_cell_table",
    "run_mosaic",
]

_CALLS = "2_NeuronalActivity/CellTypeCalls.csv"
_TRACKED = "CellTracking/TrackedCellMetrics.csv"

#: Node-level columns that are identifiers or categories, not features: the
#: module a node was put in is a label whose number means nothing, and the
#: cartography role is a category derived from PC and Z, which are kept.
_NOT_FEATURES = frozenset({
    "FileName", "Grp", "DIV", "Lag", "Channel", "activeChannelIndex", "Ci",
    "NdCartDiv", "Culture", "ActivityType",
})

#: Labels for node-level metrics :func:`metric_labels` has no entry for.
_EXTRA_LABELS = {
    "NDnorm": "Normalised Node Degree",
    "CC_raw": "Clustering Coefficient",
    "NE": "Nodal Efficiency",
    "PC_raw": "Participation Coefficient (raw)",
    "PC_residual": "Participation Coefficient (residual)",
}

#: ``key -> label`` for the two versions, in presentation order.
VERSIONS: dict[str, str] = {
    "all": "All labelled cells",
    "tracked": "Tracked cells",
}

#: Internal class codes. Patsy-safe, since they go into model formulae; the
#: readable names (which carry the run's own group and marker names) are made
#: by :meth:`CellTable.class_label`.
_POS, _MOS_POS, _MOS_NEG, _NEG = "pos", "mosP", "mosN", "neg"
CLASS_ORDER = (_POS, _MOS_POS, _MOS_NEG, _NEG)

#: ``key -> (minuend, subtrahend, description)``. The per-week contrast is not a
#: difference of classes and is fitted separately (:func:`_fit_slope`).
CONTRASTS: dict[str, tuple] = {
    "cell-autonomous": (_MOS_NEG, _MOS_POS,
                        "marker- vs marker+ cells within the mosaic cultures"),
    "environment-pos": (_MOS_POS, _POS,
                        "marker+ cells, mosaic vs healthy culture"),
    "environment-neg": (_NEG, _MOS_NEG,
                        "marker- cells, mutant vs mosaic culture"),
    "genotype": (_NEG, _POS, "mutant vs healthy culture"),
    "cell-autonomous-per-week": (None, None,
                                 "change in the cell-autonomous gap per week"),
}


@dataclass
class CellTable:
    """Every cell-day of a run with its features, marker state and identity."""

    table: pd.DataFrame
    features: list[str]
    marker: str
    #: Group names, as the run spells them.
    mosaic_group: str | None = None
    pos_group: str | None = None
    neg_group: str | None = None
    #: The run's group order, for colours that match the rest of the folder.
    group_order: list[str] = field(default_factory=list)
    #: Every marker's calls, per culture and age, for the inventory figure.
    inventory: pd.DataFrame = field(default_factory=pd.DataFrame)
    has_tracking: bool = False
    #: Why the mosaic analysis cannot run, when it cannot.
    reason: str = ""

    def class_label(self, code: str) -> str:
        return class_label(code, self.marker, self.mosaic_group, self.pos_group,
                           self.neg_group)


def class_label(code, marker, mosaic, pos, neg) -> str:
    return {
        _POS: str(pos), _NEG: str(neg),
        _MOS_POS: f"{mosaic} {marker}+", _MOS_NEG: f"{mosaic} {marker}-",
    }.get(code, str(code))


def feature_label(feature: str, labels: dict | None = None) -> str:
    labels = labels if labels is not None else metric_labels()
    return labels.get(feature) or _EXTRA_LABELS.get(feature) or feature


# ── loading ──────────────────────────────────────────────────────────────────

def load_cell_table(source, *, marker: str = "Mecp2") -> CellTable | None:
    """Read a run's node-level tables, its cell-type calls and its tracking.

    ``None`` when the run has no cell-type calls at all — an ephys run, or a
    CAT-NAP run without staining — which is the ordinary case and not an
    error. A run *with* calls but no usable mosaic returns a table whose
    :attr:`CellTable.reason` says why, so the inventory can still be drawn.
    """
    root, bundle = _resolve_root(source)
    try:
        calls = _read_first(root, _CALLS)
        if calls is None or calls.empty:
            return None
        act = _read_first(root, _ACTIVITY_NODE)
        net = _read_first(root, _NETWORK_NODE)
        tracked = _read_first(root, _TRACKED)
    finally:
        if bundle is not None:
            bundle.close()
    if act is None or act.empty:
        return None

    keys = ["FileName", "Channel"]
    calls = calls.drop_duplicates(keys)
    marker_cols = [c for c in calls.columns if c.startswith("celltype_")]
    table = act.merge(calls[keys + marker_cols], on=keys, how="left")
    if net is not None and not net.empty:
        drop = [c for c in ("Grp", "DIV") if c in net.columns]
        on = keys + (["ActivityType"] if "ActivityType" in net.columns
                     and "ActivityType" in table.columns else [])
        table = table.merge(net.drop(columns=drop), on=on, how="left")
    table["Culture"] = derive_culture_ids(table["FileName"])

    has_tracking = tracked is not None and not tracked.empty \
        and {"chain", "cluster"} <= set(tracked.columns)
    if has_tracking:
        ids = tracked[keys + ["chain", "cluster"]].drop_duplicates(keys + ["chain", "cluster"])
        ids["CellID"] = ids["chain"].astype(str) + "#" + ids["cluster"].astype(str)
        # A ROI matched into two tracked cells is ambiguous about which one it
        # is; it stays in the "all" version and out of the tracked one.
        ambiguous = ids.duplicated(keys, keep=False)
        table = table.merge(ids.loc[~ambiguous, keys + ["CellID"]], on=keys, how="left")
    else:
        table["CellID"] = np.nan

    features = [c for c in table.columns
                if c not in _NOT_FEATURES and not c.startswith("celltype_")
                and c != "CellID" and pd.api.types.is_numeric_dtype(table[c])
                and table[c].notna().any()]
    order = list(pd.unique(table["Grp"].dropna()))
    out = CellTable(table=table, features=features, marker=marker,
                    group_order=order, has_tracking=bool(has_tracking),
                    inventory=_inventory(table, marker_cols))
    _identify_groups(out)
    return out


def _inventory(table: pd.DataFrame, marker_cols: list[str]) -> pd.DataFrame:
    """Labelled cells per culture, age and marker — what each question can use."""
    rows = []
    base = table.drop_duplicates(["FileName", "Channel"])
    for col in marker_cols:
        sub = base[base[col].isin(["+", "-"])]
        if sub.empty:
            continue
        grouped = sub.groupby(["Culture", "Grp", "DIV"], observed=True)
        for (culture, grp, div), part in grouped:
            rows.append({
                "Marker": col[len("celltype_"):], "Culture": culture, "Group": grp,
                "DIV": div, "Positive": int((part[col] == "+").sum()),
                "Negative": int((part[col] == "-").sum()),
                "Tracked": int(part["CellID"].notna().sum())
                if "CellID" in part.columns else 0,
            })
    return pd.DataFrame(rows)


def _identify_groups(cells: CellTable) -> None:
    """Find the mosaic group and the two references from the calls themselves."""
    col = f"celltype_{cells.marker}"
    table = cells.table
    if col not in table.columns:
        cells.reason = f"no {cells.marker} calls in this run"
        return
    labelled = table[table[col].isin(["+", "-"])]
    stats = labelled.groupby("Grp", observed=True)[col].agg(
        n="size", share=lambda s: float((s == "+").mean()))
    stats = stats[stats["n"] >= 20]
    mosaic = stats[(stats["share"] > 0.1) & (stats["share"] < 0.9)]
    pos = stats[stats["share"] >= 0.95]
    neg = stats[stats["share"] <= 0.05]
    if mosaic.empty:
        cells.reason = (f"no group has a mix of {cells.marker}+ and "
                        f"{cells.marker}- cells, so there is no mosaic to compare")
        return
    pick = lambda frame: str(frame["n"].idxmax()) if not frame.empty else None  # noqa: E731
    cells.mosaic_group, cells.pos_group, cells.neg_group = pick(mosaic), pick(pos), pick(neg)


def _classes(cells: CellTable) -> pd.Series:
    """Each cell-day's class code, or NaN for a cell outside the design."""
    t = cells.table
    col = f"celltype_{cells.marker}"
    grp = t["Grp"].astype(str)
    state = t[col] if col in t.columns else pd.Series(np.nan, index=t.index)
    out = pd.Series(np.nan, index=t.index, dtype=object)
    in_mosaic = grp == str(cells.mosaic_group)
    out[in_mosaic & (state == "+")] = _MOS_POS
    out[in_mosaic & (state == "-")] = _MOS_NEG
    # References: every cell, labelled or not, except one whose call
    # contradicts the genotype — eight such cells in the Yin WT cultures.
    if cells.pos_group is not None:
        out[(grp == cells.pos_group) & (state != "-")] = _POS
    if cells.neg_group is not None:
        out[(grp == cells.neg_group) & (state != "+")] = _NEG
    # A cell stained as not a neuron is out of every class.
    if "celltype_NeuN" in t.columns:
        out[t["celltype_NeuN"] == "-"] = np.nan
    return out


# ── preparing one version ────────────────────────────────────────────────────

def _transform(values: pd.Series) -> tuple[pd.Series, str]:
    """Log-scale a skewed non-negative metric; leave the rest alone.

    Event rates, areas and centralities span orders of magnitude, and a model
    of the raw values is a model of their few largest cells. The offset is half
    the smallest positive value, so a zero stays finite and stays lowest.
    """
    v = pd.to_numeric(values, errors="coerce")
    finite = v.dropna()
    if finite.empty or (finite < 0).any() or finite.skew() <= 1:
        return v, "none"
    positive = finite[finite > 0]
    offset = positive.min() / 2 if not positive.empty else 1.0
    return np.log10(v + offset), "log10"


@dataclass
class _Prepared:
    """One version's cells: class, identifiers, and standardised features."""

    frame: pd.DataFrame
    features: list[str]
    transforms: dict[str, str]
    version: str


def _prepare(cells: CellTable, version: str, *, lag=None, activity=None) -> _Prepared | None:
    t = cells.table.copy()
    if lag is not None and "Lag" in t.columns:
        # Inactive cells have no network row, so no Lag; they belong to every
        # lag's analysis of activity.
        t = t[(t["Lag"] == lag) | t["Lag"].isna()]
    if activity is not None and "ActivityType" in t.columns:
        t = t[t["ActivityType"] == activity]
    t["Class"] = _classes(cells).reindex(t.index)
    t = t[t["Class"].notna()]
    if version == "tracked":
        t = t[t["CellID"].notna()]
    if t.empty or not (t["Class"] == _MOS_NEG).any() or not (t["Class"] == _MOS_POS).any():
        return None
    transforms: dict[str, str] = {}
    keep: list[str] = []
    for f in cells.features:
        v, how = _transform(t[f])
        sd = v.std()
        if not np.isfinite(sd) or sd == 0 or v.notna().mean() < 0.5:
            continue
        t[f] = (v - v.mean()) / sd
        transforms[f] = how
        keep.append(f)
    return _Prepared(frame=t.reset_index(drop=True), features=keep,
                     transforms=transforms, version=version)


# ── mixed models ─────────────────────────────────────────────────────────────

def _fit(data: pd.DataFrame, formula: str, *, cell_effect: bool):
    """Mixed model with recordings (and cells) nested in cultures.

    Falls back to OLS with culture-clustered errors when the mixed model will
    not fit, which keeps the inference at the culture level either way.
    """
    import statsmodels.formula.api as smf

    vc = {"recording": "0 + C(FileName)"}
    if cell_effect:
        vc["cell"] = "0 + C(CellID)"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res = smf.mixedlm(formula, data, groups=data["Culture"],
                              vc_formula=vc).fit(reml=True)
            if res.converged and np.all(np.isfinite(res.bse_fe)):
                return res.fe_params, res.cov_params().loc[
                    res.fe_params.index, res.fe_params.index], "mixedlm"
        except (ValueError, np.linalg.LinAlgError):
            pass
        codes = pd.factorize(data["Culture"])[0]
        res = smf.ols(formula, data).fit(cov_type="cluster",
                                         cov_kwds={"groups": codes})
        return res.params, res.cov_params(), "ols-cluster"


def _contrast(params, cov, weights: dict) -> tuple[float, float]:
    from scipy import stats

    L = pd.Series(0.0, index=params.index)
    for name, w in weights.items():
        if name not in L.index:
            return np.nan, np.nan
        L[name] = w
    est = float(L @ params)
    se = float(np.sqrt(L @ cov @ L))
    return est, se if np.isfinite(se) else np.nan


def _class_term(code: str) -> str:
    return f"C(Class, Treatment('{_MOS_POS}'))[T.{code}]"


def _class_weights(minuend: str, subtrahend: str) -> dict:
    """Weights on the treatment-coded terms for ``minuend - subtrahend``."""
    weights: dict = {}
    for code, sign in ((minuend, 1.0), (subtrahend, -1.0)):
        if code != _MOS_POS:
            weights[_class_term(code)] = weights.get(_class_term(code), 0.0) + sign
    return weights


def _model_rows(prep: _Prepared, feature: str, scope: str, data: pd.DataFrame,
                *, pooled: bool) -> list[dict]:
    from scipy import stats

    sub = data[["Class", "DIV", "Culture", "FileName", "CellID", feature]].dropna(
        subset=[feature]).rename(columns={feature: "y"})
    present = set(sub["Class"])
    if not {_MOS_POS, _MOS_NEG} <= present:
        return []
    terms = "C(Class, Treatment('mosP'))"
    if pooled and sub["DIV"].nunique() > 1:
        terms += " + C(DIV)"
    cell_effect = prep.version == "tracked" and pooled
    params, cov, how = _fit(sub, f"y ~ {terms}", cell_effect=cell_effect)
    rows = []
    for key, (a, b, _desc) in CONTRASTS.items():
        if a is None or a not in present or b not in present:
            continue
        est, se = _contrast(params, cov, _class_weights(a, b))
        rows.append(_row(prep, feature, scope, key, est, se, how, sub, (a, b)))
    if pooled and sub["DIV"].nunique() > 1:
        rows.extend(_fit_slope(prep, feature, scope, sub, cell_effect))
    return rows


def _fit_slope(prep, feature, scope, sub, cell_effect) -> list[dict]:
    """How the cell-autonomous gap moves with age, within the mosaic cultures."""
    het = sub[sub["Class"].isin([_MOS_POS, _MOS_NEG])].copy()
    if het["DIV"].nunique() < 2:
        return []
    het["mutant"] = (het["Class"] == _MOS_NEG).astype(float)
    het["weeks"] = (het["DIV"] - het["DIV"].mean()) / 7.0
    params, cov, how = _fit(het, "y ~ mutant * weeks", cell_effect=cell_effect)
    est, se = _contrast(params, cov, {"mutant:weeks": 1.0})
    return [_row(prep, feature, scope, "cell-autonomous-per-week", est, se, how,
                 het, (_MOS_POS, _MOS_NEG))]


def _row(prep, feature, scope, key, est, se, how, sub, classes) -> dict:
    from scipy import stats

    z = est / se if se and np.isfinite(se) and se > 0 else np.nan
    p = float(2 * stats.norm.sf(abs(z))) if np.isfinite(z) else np.nan
    used = sub[sub["Class"].isin(classes)]
    return {
        "Version": prep.version, "Scope": scope, "Feature": feature,
        "Contrast": key, "Estimate": est, "SE": se,
        "CILow": est - 1.96 * se if np.isfinite(se) else np.nan,
        "CIHigh": est + 1.96 * se if np.isfinite(se) else np.nan,
        "PValue": p, "NObs": int(len(used)),
        "NCells": int(used["CellID"].nunique()) if prep.version == "tracked"
        else int(len(used)),
        "NRecordings": int(used["FileName"].nunique()),
        "NCultures": int(used["Culture"].nunique()),
        "Transform": prep.transforms.get(feature, "none"), "Fit": how,
    }


def mosaic_effects(prep: _Prepared, *, log=None) -> pd.DataFrame:
    """Every contrast for every feature, pooled over age and at each age."""
    rows: list[dict] = []
    frame = prep.frame
    ages = sorted(frame["DIV"].dropna().unique())
    for feature in prep.features:
        rows += _model_rows(prep, feature, "pooled", frame, pooled=True)
        for age in ages:
            rows += _model_rows(prep, feature, f"DIV {age:g}",
                                frame[frame["DIV"] == age], pooled=False)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # One family per version, scope and contrast: the question "which features
    # differ cell-autonomously at DIV 21" is corrected across features only.
    out["PValueFDR"] = np.nan
    for _, idx in out.groupby(["Version", "Scope", "Contrast"]).groups.items():
        out.loc[idx, "PValueFDR"] = fdr_correct(out.loc[idx, "PValue"].to_numpy())
    return out


# ── within-recording pairs ───────────────────────────────────────────────────

def paired_differences(prep: _Prepared, *, min_cells: int = 5) -> pd.DataFrame:
    """Mean marker- minus marker+ per mosaic recording, per feature.

    The model-free view of the cell-autonomous contrast: every point is one
    recording, so the reader sees how consistent the sign is across dishes
    rather than taking a pooled estimate on trust.
    """
    het = prep.frame[prep.frame["Class"].isin([_MOS_POS, _MOS_NEG])]
    rows = []
    for (name, culture, div), rec in het.groupby(["FileName", "Culture", "DIV"]):
        pos = rec[rec["Class"] == _MOS_POS]
        neg = rec[rec["Class"] == _MOS_NEG]
        for f in prep.features:
            a, b = pos[f].dropna(), neg[f].dropna()
            if len(a) < min_cells or len(b) < min_cells:
                continue
            rows.append({"Version": prep.version, "FileName": name,
                         "Culture": culture, "DIV": div, "Feature": f,
                         "MeanPos": a.mean(), "MeanNeg": b.mean(),
                         "NPos": len(a), "NNeg": len(b),
                         "Diff": b.mean() - a.mean()})
    return pd.DataFrame(rows)


# ── KO-likeness ──────────────────────────────────────────────────────────────

def _feature_matrix(frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    X = frame[features].to_numpy(dtype=float)
    # Standardised already, so the pooled median is ~0; a missing network
    # metric (an inactive cell) is placed at the centre rather than dropped.
    return np.where(np.isfinite(X), X, 0.0)


def _group_folds(y, groups, n_splits: int, seed: int):
    from sklearn.model_selection import StratifiedGroupKFold

    per_class = pd.Series(groups).groupby(pd.Series(y)).nunique()
    k = int(min(n_splits, per_class.min()))
    if k < 2:
        return []
    return list(StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed)
                .split(np.zeros(len(y)), y, groups))


def ko_scores(prep: _Prepared, *, n_splits: int = 5, seed: int = 0):
    """Score every cell on a healthy-vs-mutant axis learned from the references.

    A logistic model is trained to tell cells of the mutant culture from cells
    of the healthy one, then asked where each mosaic cell falls. If the
    references' difference is cell-autonomous, mosaic marker- cells score more
    mutant-like than their marker+ neighbours; if it is the network's, both
    shift together and the within-recording gap is ~0.

    Returns ``(scores, summary)``: per-cell log-odds (out-of-fold for the
    references, so their own separation is honest) and the headline numbers.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    frame = prep.frame
    ref = frame[frame["Class"].isin([_POS, _NEG])]
    het = frame[frame["Class"].isin([_MOS_POS, _MOS_NEG])]
    if ref["Class"].nunique() < 2 or het.empty:
        return pd.DataFrame(), pd.DataFrame()
    X = _feature_matrix(ref, prep.features)
    y = (ref["Class"] == _NEG).to_numpy().astype(int)
    model = lambda: LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000)  # noqa: E731

    oof = np.full(len(ref), np.nan)
    for train, test in _group_folds(y, ref["Culture"].to_numpy(), n_splits, seed):
        oof[test] = model().fit(X[train], y[train]).decision_function(X[test])
    fitted = model().fit(X, y)
    het_scores = fitted.decision_function(_feature_matrix(het, prep.features))

    cols = ["FileName", "Culture", "DIV", "Class"]
    scores = pd.concat([
        ref[cols].assign(Score=oof, OutOfFold=True),
        het[cols].assign(Score=het_scores, OutOfFold=False),
    ], ignore_index=True)
    scores.insert(0, "Version", prep.version)

    summary = [("ReferenceAUC", roc_auc_score(y, oof) if np.isfinite(oof).all()
                else np.nan)]
    paired = (scores[scores["Class"].isin([_MOS_POS, _MOS_NEG])]
              .groupby(["FileName", "Class"])["Score"].mean().unstack())
    paired = paired.dropna()
    if len(paired) >= 3:
        from scipy import stats

        diff = paired[_MOS_NEG] - paired[_MOS_POS]
        summary += [("PairedRecordings", len(diff)),
                    ("MeanPairedDiff", float(diff.mean())),
                    ("FractionNegHigher", float((diff > 0).mean())),
                    ("WilcoxonP", float(stats.wilcoxon(diff).pvalue))]
    for code in CLASS_ORDER:
        part = scores.loc[scores["Class"] == code, "Score"]
        if not part.empty:
            summary.append((f"Median_{code}", float(part.median())))
    # The same gap from a mixed model, so it is tested at the culture level
    # like every other number here.
    het_rows = scores[scores["Class"].isin([_MOS_POS, _MOS_NEG])].copy()
    het_rows["CellID"] = np.nan
    het_rows = het_rows.rename(columns={"Score": "y"})
    params, cov, how = _fit(het_rows, "y ~ C(Class, Treatment('mosP'))",
                            cell_effect=False)
    est, se = _contrast(params, cov, {_class_term(_MOS_NEG): 1.0})
    summary += [("ModelGap", est), ("ModelGapSE", se)]
    out = pd.DataFrame(summary, columns=["Statistic", "Value"])
    out.insert(0, "Version", prep.version)
    return scores, out


# ── decoding marker state within the mosaic ──────────────────────────────────

def _within_recording(frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Features z-scored within each recording.

    The question is whether a cell's *position in its own network* gives its
    marker state away; anything shared by the whole recording is removed, so a
    decoder cannot win by recognising which dish a cell came from.
    """
    z = frame.groupby("FileName")[features].transform(
        lambda s: (s - s.mean()) / s.std() if s.std() > 0 else s * 0)
    return np.where(np.isfinite(z.to_numpy(dtype=float)), z.to_numpy(dtype=float), 0.0)


def _cv_score(X, y, folds, model) -> list[float]:
    from sklearn.metrics import balanced_accuracy_score

    out = []
    for train, test in folds:
        fitted = model().fit(X[train], y[train])
        out.append(balanced_accuracy_score(y[test], fitted.predict(X[test])))
    return out


def decode_marker(prep: _Prepared, *, n_splits: int = 5, n_repeats: int = 5,
                  n_permutations: int = 100, seed: int = 0, n_jobs: int = -1):
    """Held-out accuracy of telling marker- from marker+ mosaic cells.

    Pooled over age and at each age, with whole cultures held out. The null
    shuffles labels *within* each recording, which keeps every recording's
    mix of + and - and so asks only whether the labels line up with the cells.
    """
    from joblib import Parallel, delayed
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import LogisticRegression

    model = lambda: LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000)  # noqa: E731
    het_all = prep.frame[prep.frame["Class"].isin([_MOS_POS, _MOS_NEG])]
    scopes = [("pooled", het_all)] + [
        (f"DIV {age:g}", het_all[het_all["DIV"] == age])
        for age in sorted(het_all["DIV"].unique())]
    rows, importance = [], []
    rng = np.random.default_rng(seed)
    for scope, het in scopes:
        het = het.reset_index(drop=True)
        X = _within_recording(het, prep.features)
        y = (het["Class"] == _MOS_NEG).to_numpy().astype(int)
        groups = het["Culture"].to_numpy()
        folds = _group_folds(y, groups, n_splits, seed)
        if not folds:
            continue
        scores = []
        for r in range(n_repeats):
            scores += _cv_score(X, y, _group_folds(y, groups, n_splits, seed + r), model)

        recs = het["FileName"].to_numpy()
        def shuffled(s):
            from threadpoolctl import threadpool_limits

            g = np.random.default_rng(s)
            yp = y.copy()
            for rec in np.unique(recs):
                idx = np.flatnonzero(recs == rec)
                yp[idx] = g.permutation(yp[idx])
            # One BLAS thread per worker: with OpenBLAS each of the n_jobs
            # workers otherwise starts a thread per core, and the null took
            # many minutes instead of seconds on a 16-core machine.
            with threadpool_limits(1):
                return float(np.mean(_cv_score(X, yp, folds, model)))
        null = np.array(Parallel(n_jobs=n_jobs)(
            delayed(shuffled)(int(s)) for s in rng.integers(0, 2**31, n_permutations))) \
            if n_permutations > 0 else np.array([])
        observed = float(np.mean(_cv_score(X, y, folds, model)))
        rows.append({
            "Version": prep.version, "Scope": scope,
            "BalancedAccuracy": float(np.mean(scores)), "SD": float(np.std(scores)),
            "NFolds": len(scores), "Chance": 0.5,
            "NullMean": float(null.mean()) if null.size else np.nan,
            "NullP95": float(np.percentile(null, 95)) if null.size else np.nan,
            "PValue": float((1 + (null >= observed).sum()) / (1 + null.size))
            if null.size else np.nan,
            "NCells": int(len(het)), "NRecordings": int(het["FileName"].nunique()),
            "NCultures": int(het["Culture"].nunique()),
        })
        drops = np.zeros((len(folds), len(prep.features)))
        for i, (train, test) in enumerate(folds):
            fitted = model().fit(X[train], y[train])
            pi = permutation_importance(fitted, X[test], y[test], n_repeats=5,
                                        scoring="balanced_accuracy",
                                        random_state=seed)
            drops[i] = pi.importances_mean
        for j, f in enumerate(prep.features):
            importance.append({"Version": prep.version, "Scope": scope,
                               "Feature": f, "Importance": float(drops[:, j].mean()),
                               "SD": float(drops[:, j].std())})
    return pd.DataFrame(rows), pd.DataFrame(importance)


# ── trajectories ─────────────────────────────────────────────────────────────

def class_trajectories(prep: _Prepared) -> pd.DataFrame:
    """Per class and age: the mean of culture means, and its SEM across cultures.

    Culture means first, so a dish with 600 cells weighs what a dish with 60
    does — the culture is the replicate.
    """
    rows = []
    frame = prep.frame
    for f in prep.features:
        per_culture = (frame.dropna(subset=[f])
                       .groupby(["Class", "DIV", "Culture"])[f].mean().reset_index())
        for (code, div), part in per_culture.groupby(["Class", "DIV"]):
            vals = part[f]
            rows.append({"Version": prep.version, "Feature": f, "Class": code,
                         "DIV": div, "Mean": vals.mean(),
                         "SEM": vals.std(ddof=1) / np.sqrt(len(vals))
                         if len(vals) > 1 else np.nan,
                         "NCultures": len(vals)})
    return pd.DataFrame(rows)


# ── the whole analysis ───────────────────────────────────────────────────────

@dataclass
class MosaicResults:
    """Every table the mosaic analysis writes, and the design that produced them."""

    design: pd.DataFrame = field(default_factory=pd.DataFrame)
    inventory: pd.DataFrame = field(default_factory=pd.DataFrame)
    effects: pd.DataFrame = field(default_factory=pd.DataFrame)
    paired: pd.DataFrame = field(default_factory=pd.DataFrame)
    scores: pd.DataFrame = field(default_factory=pd.DataFrame)
    score_summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    decoding: pd.DataFrame = field(default_factory=pd.DataFrame)
    importance: pd.DataFrame = field(default_factory=pd.DataFrame)
    trajectories: pd.DataFrame = field(default_factory=pd.DataFrame)

    #: ``attribute -> CSV name``, the one place the on-disk names live.
    FILES = {
        "design": "mosaic_design.csv",
        "inventory": "celltype_inventory.csv",
        "effects": "mosaic_effects.csv",
        "paired": "mosaic_paired_differences.csv",
        "scores": "mosaic_ko_scores.csv",
        "score_summary": "mosaic_ko_score_summary.csv",
        "decoding": "mosaic_decoding.csv",
        "importance": "mosaic_decoding_importance.csv",
        "trajectories": "mosaic_trajectories.csv",
    }

    @property
    def ran(self) -> bool:
        return not self.effects.empty

    def meta(self, key: str, default=None):
        if self.design.empty or key not in self.design.columns:
            return default
        value = self.design[key].iloc[0]
        return default if pd.isna(value) else value

    def label(self, code: str) -> str:
        return class_label(code, self.meta("Marker", "marker"),
                           self.meta("MosaicGroup"), self.meta("PositiveGroup"),
                           self.meta("NegativeGroup"))

    def group_order(self) -> list[str]:
        text = self.meta("GroupOrder", "")
        return [g for g in str(text).split("|") if g]


def run_mosaic(cells: CellTable, *, lag=None, activity=None, n_splits: int = 5,
               n_repeats: int = 5, n_permutations: int = 100, seed: int = 0,
               log=print) -> MosaicResults:
    """Both versions of every mosaic analysis, for one lag.

    BLAS is held to one thread throughout. The mixed models are hundreds of
    small fits, and with OpenBLAS spreading each across every core the tracked
    version ran ~7x slower than single-threaded (20 s against 3 s per feature
    on 16 cores) — the whole step went from minutes to most of an hour.
    """
    from threadpoolctl import threadpool_limits

    with threadpool_limits(1):
        return _run_mosaic(cells, lag=lag, activity=activity, n_splits=n_splits,
                           n_repeats=n_repeats, n_permutations=n_permutations,
                           seed=seed, log=log)


def _run_mosaic(cells, *, lag, activity, n_splits, n_repeats, n_permutations,
                seed, log) -> MosaicResults:
    out = MosaicResults(inventory=cells.inventory)
    out.design = pd.DataFrame([{
        "Marker": cells.marker, "MosaicGroup": cells.mosaic_group,
        "PositiveGroup": cells.pos_group, "NegativeGroup": cells.neg_group,
        "GroupOrder": "|".join(map(str, cells.group_order)),
        "Reason": cells.reason,
    }])
    if cells.mosaic_group is None:
        log(f"  mosaic: skipped — {cells.reason}")
        return out
    collected: dict[str, list] = {k: [] for k in MosaicResults.FILES
                                  if k not in ("design", "inventory")}
    for version in VERSIONS:
        if version == "tracked" and not cells.has_tracking:
            continue
        prep = _prepare(cells, version, lag=lag, activity=activity)
        if prep is None:
            log(f"  mosaic/{version}: no {cells.marker}+ and {cells.marker}- "
                "cells to compare")
            continue
        counts = prep.frame["Class"].value_counts()
        log(f"  mosaic/{version}: " + ", ".join(
            f"{cells.class_label(c)} {counts.get(c, 0)}" for c in CLASS_ORDER)
            + f" cell-days, {len(prep.features)} features")
        collected["effects"].append(mosaic_effects(prep))
        collected["paired"].append(paired_differences(prep))
        scores, summary = ko_scores(prep, n_splits=n_splits, seed=seed)
        collected["scores"].append(scores)
        collected["score_summary"].append(summary)
        dec, imp = decode_marker(prep, n_splits=n_splits, n_repeats=n_repeats,
                                 n_permutations=n_permutations, seed=seed)
        collected["decoding"].append(dec)
        collected["importance"].append(imp)
        collected["trajectories"].append(class_trajectories(prep))
    for key, frames in collected.items():
        frames = [f for f in frames if f is not None and not f.empty]
        if frames:
            setattr(out, key, pd.concat(frames, ignore_index=True))
    return out


def summary_lines(res: MosaicResults) -> list[str]:
    """A few log lines with the headline of each version."""
    lines = []
    if not res.ran:
        return lines
    pooled = res.effects[res.effects["Scope"] == "pooled"]
    for version in pd.unique(pooled["Version"]):
        part = pooled[pooled["Version"] == version]
        auto = part[part["Contrast"] == "cell-autonomous"]
        geno = part[part["Contrast"] == "genotype"]
        n_auto = int((auto["PValueFDR"] < 0.05).sum())
        n_geno = int((geno["PValueFDR"] < 0.05).sum())
        line = (f"  mosaic/{version}: {n_auto}/{len(auto)} features differ "
                f"cell-autonomously (FDR<0.05)")
        if len(geno):
            line += f"; {n_geno}/{len(geno)} differ between the reference genotypes"
        lines.append(line)
        dec = res.decoding[(res.decoding["Version"] == version)
                           & (res.decoding["Scope"] == "pooled")]
        if not dec.empty:
            d = dec.iloc[0]
            lines.append(f"  mosaic/{version}: marker state decoded at "
                         f"{d['BalancedAccuracy']:.2f} balanced accuracy "
                         f"(within-recording null {d['NullMean']:.2f}, p={d['PValue']:.3g})")
    return lines
