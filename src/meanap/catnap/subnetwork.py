"""Cell-type subnetwork analysis for CAT-NAP.

A CAT-NAP recording comes with a *putative cell type* spreadsheet listing, for
each immunohistochemistry marker (``NeuN+``, ``GAD+``, ``PV+``, …), the suite2p
ROI ids that stained positive. MATLAB only uses that table cosmetically — as
concentric rings drawn around nodes in the network plot
(``StandardisedNetworkPlot.m``). This module turns it into an analysis:

**Induced subgraphs.** For each named group of cells (a marker column, or a
boolean combination of them such as ``Inhibitory = GAD+ | PV+ | SST+``), take
the nodes belonging to that group and the edges *among* them, and re-run the
shared step-4 metric suite on that subgraph. Answers "is the inhibitory network
denser / more efficient / more small-world than the excitatory one?".

**Split full-network metrics.** Tag every node of the *whole* network with its
group(s) and compare the node-level distributions (node degree, node strength,
participation coefficient, betweenness, local efficiency, …). Answers "are
inhibitory cells more hub-like within the whole network?".

**Edge mixing.** How connectivity distributes within versus between groups
(a group × group density / mean-weight matrix, plus a per-node
within-group-strength fraction).

Group membership is deliberately allowed to overlap — a cell can be both
``NeuN+`` and ``Mecp2+`` — so the node-level output is *long* format (one row
per node × group), never a single hard assignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from meanap.catnap.stats import get_cell_type_matrix

# Markers conventionally taken to indicate a GABAergic (inhibitory) cell. Used
# by :func:`default_ei_groups` to build an excitatory/inhibitory split from
# whatever subset of them a given spreadsheet happens to contain.
INHIBITORY_MARKERS = ("GAD+", "PV+", "SST+", "VIP+", "GABA+")

# Marker taken to mean "is a neuron at all" — excitatory cells are defined as
# neurons that are not positive for any inhibitory marker.
NEURON_MARKER = "NeuN+"

# Ready-made preset for the marker set shipped with the example dataset
# (``local/example2pdataWCellTypes``). Assign to
# ``Params.twop_subnetwork_groups`` to compare excitatory against inhibitory
# cells; :func:`default_ei_groups` derives the same thing from whichever
# markers are actually present.
EXCITATORY_INHIBITORY_PRESET: dict[str, str] = {
    "Excitatory": "NeuN+ & ~GAD+ & ~PV+ & ~SST+",
    "Inhibitory": "GAD+ | PV+ | SST+",
}


# ── Locating and loading the cell-type spreadsheet ────────────────────────────

def find_cell_type_file(raw_data: str | Path, filename: str) -> Path | None:
    """Locate a recording's cell-type spreadsheet.

    Mirrors ``MEApipeline.m``, which globs ``rawData/<FN>/*.csv`` and reads it
    when exactly one match exists; extended here to accept ``.xlsx``/``.xls``
    too, and to disambiguate several matches by preferring names starting with
    ``PutativeCellType``. Returns ``None`` when nothing plausible is found.
    """
    folder = Path(raw_data) / filename
    if not folder.is_dir():
        return None

    candidates = sorted(
        p for ext in ("*.csv", "*.xlsx", "*.xls") for p in folder.glob(ext)
    )
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    preferred = [p for p in candidates if p.name.lower().startswith("putativecelltype")]
    return (preferred or candidates)[0]


def load_cell_type_table(path: str | Path) -> pd.DataFrame:
    """Read a cell-type spreadsheet (CSV or Excel) of ROI ids per marker.

    One column per marker; each column lists the **0-indexed** suite2p ROI ids
    positive for that marker, NaN-padded to the longest column (the format the
    ``PutativeCellType_*`` files use).

    Columns that hold no usable ids are dropped. This matters for the
    ``…_PositiveOnly.xlsx`` variant, whose ``NeuN-``-style columns contain a
    single sentence of prose ("Should be all those that are not in List NeuN+")
    rather than ids — MATLAB reads the ``.csv`` sibling, which omits them
    entirely.
    """
    path = Path(path)
    df = pd.read_excel(path) if path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(path)

    keep: dict[str, pd.Series] = {}
    for col in df.columns:
        ids = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(ids):
            keep[str(col).strip()] = ids.reset_index(drop=True)
    return pd.DataFrame(keep)


def build_marker_matrix(
    cell_type_df: pd.DataFrame, channels: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    """``(n_channels, n_markers)`` binary membership matrix for *channels*.

    Thin wrapper over :func:`meanap.catnap.stats.get_cell_type_matrix` (the
    ``getCellTypeMatrix.m`` port), which handles the 0-indexed-ROI → 1-indexed
    ``channels`` conversion.
    """
    ids = {col: cell_type_df[col].to_numpy(dtype=float) for col in cell_type_df.columns}
    matrix, names = get_cell_type_matrix(ids, channels)
    return matrix.astype(bool), names


# ── Group expressions ─────────────────────────────────────────────────────────

class GroupExpressionError(ValueError):
    """Raised when a subnetwork group expression cannot be parsed."""


def _tokenize(expr: str, marker_names: list[str]) -> list[str]:
    """Split *expr* into marker names and the operators ``& | ~ ( )``.

    Marker names are matched greedily longest-first because they contain
    characters (``+``, ``-``) that would otherwise be mistaken for operators or
    split apart — ``NeuN+`` has to win over a hypothetical ``NeuN``.
    """
    by_length = sorted(marker_names, key=len, reverse=True)
    lowered = {n.lower(): n for n in marker_names}
    tokens: list[str] = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "&|~()":
            tokens.append(ch)
            i += 1
            continue
        if ch == "!":  # accept ! as an alias for ~
            tokens.append("~")
            i += 1
            continue
        for name in by_length:
            if expr.startswith(name, i):
                tokens.append(name)
                i += len(name)
                break
        else:
            # Case-insensitive fallback, so "gad+" still resolves.
            match = next(
                (lowered[n.lower()] for n in by_length
                 if expr[i:i + len(n)].lower() == n.lower()), None,
            )
            if match is None:
                raise GroupExpressionError(
                    f"unrecognised token at position {i} in {expr!r}; "
                    f"known markers: {', '.join(marker_names)}"
                )
            tokens.append(match)
            i += len(match)
    return tokens


def eval_group_expression(
    expr: str, marker_matrix: np.ndarray, marker_names: list[str],
) -> np.ndarray:
    """Evaluate a boolean marker expression into an ``(n_channels,)`` mask.

    Supported syntax: marker names, ``&`` (and), ``|`` (or), ``~`` / ``!``
    (not), and parentheses. ``&`` binds tighter than ``|``, as in Python.

        >>> eval_group_expression("GAD+ | PV+ | SST+", m, names)   # inhibitory
        >>> eval_group_expression("NeuN+ & ~GAD+", m, names)       # excitatory
    """
    tokens = _tokenize(expr, marker_names)
    if not tokens:
        raise GroupExpressionError(f"empty group expression: {expr!r}")
    col_of = {name: i for i, name in enumerate(marker_names)}
    pos = 0

    def parse_or() -> np.ndarray:
        nonlocal pos
        value = parse_and()
        while pos < len(tokens) and tokens[pos] == "|":
            pos += 1
            value = value | parse_and()
        return value

    def parse_and() -> np.ndarray:
        nonlocal pos
        value = parse_not()
        while pos < len(tokens) and tokens[pos] == "&":
            pos += 1
            value = value & parse_not()
        return value

    def parse_not() -> np.ndarray:
        nonlocal pos
        if pos < len(tokens) and tokens[pos] == "~":
            pos += 1
            return ~parse_not()
        return parse_atom()

    def parse_atom() -> np.ndarray:
        nonlocal pos
        if pos >= len(tokens):
            raise GroupExpressionError(f"unexpected end of expression: {expr!r}")
        tok = tokens[pos]
        if tok == "(":
            pos += 1
            value = parse_or()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise GroupExpressionError(f"unbalanced parentheses in {expr!r}")
            pos += 1
            return value
        if tok in (")", "&", "|"):
            raise GroupExpressionError(f"unexpected {tok!r} in {expr!r}")
        pos += 1
        return marker_matrix[:, col_of[tok]].astype(bool)

    mask = parse_or()
    if pos != len(tokens):
        raise GroupExpressionError(f"trailing tokens after position {pos} in {expr!r}")
    return mask


def _tokenize_lenient(expr: str) -> list[str]:
    """Tokenize without knowing the marker names.

    Used when reconstructing a saved expression before any spreadsheet has been
    read (the GUI can be opened on a saved parameter file with no data loaded).
    Any maximal run of characters that are not operators or whitespace is taken
    to be a marker name — correct for the ``NeuN+`` / ``GAD+`` style names these
    spreadsheets use, though it would split a name containing a space.
    """
    tokens: list[str] = []
    current = ""
    for ch in expr:
        if ch in "&|~()" or ch.isspace() or ch == "!":
            if current:
                tokens.append(current)
                current = ""
            if ch == "!":
                tokens.append("~")
            elif not ch.isspace():
                tokens.append(ch)
        else:
            current += ch
    if current:
        tokens.append(current)
    return tokens


def build_group_expression(
    include: list[str], exclude: list[str], match: str = "any",
) -> str:
    """Compose a group expression from included/excluded markers.

    ``match`` applies to *include* only: ``"any"`` joins them with ``|``,
    ``"all"`` with ``&``. Excluded markers are always AND-ed as ``~marker``, so
    "any of these, but none of those" and "all of these, but none of those" are
    both expressible — which is what the GUI's include/exclude grid offers.

    Round-trips with :func:`parse_group_expression_terms`.
    """
    parts: list[str] = []
    if include:
        if len(include) == 1:
            parts.append(include[0])
        elif match == "all":
            parts.append(" & ".join(include))
        else:
            parts.append(" | ".join(include) if not exclude
                         else "(" + " | ".join(include) + ")")
    parts += [f"~{name}" for name in exclude]
    return " & ".join(parts)


def parse_group_expression_terms(
    expr: str, marker_names: list[str] | None = None,
) -> tuple[str, list[str], list[str]] | None:
    """Inverse of :func:`build_group_expression`.

    Returns ``(match, include, exclude)``, or ``None`` when *expr* is richer
    than the include/exclude form — nested parentheses, mixed ``&``/``|`` at the
    same level, and so on. Callers offering a grid UI should fall back to a
    free-text editor on ``None`` rather than silently dropping the expression.

    ``marker_names`` makes tokenization exact; without it names are guessed
    (see :func:`_tokenize_lenient`).
    """
    tokens = (_tokenize(expr, marker_names) if marker_names
              else _tokenize_lenient(expr))
    if not tokens:
        return None

    # Split on top-level '&'.
    conjuncts: list[list[str]] = [[]]
    depth = 0
    for tok in tokens:
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        if tok == "&" and depth == 0:
            conjuncts.append([])
        else:
            conjuncts[-1].append(tok)
    if any(not c for c in conjuncts):
        return None

    def as_or_chain(part: list[str]) -> list[str] | None:
        """``A | B | C`` → ``[A, B, C]``; anything else → None."""
        if not part or len(part) % 2 == 0:
            return None
        names, ops = part[0::2], part[1::2]
        if any(n in ("&", "|", "~", "(", ")") for n in names):
            return None
        return names if all(op == "|" for op in ops) else None

    include_any: list[str] | None = None
    include_all: list[str] = []
    exclude: list[str] = []

    for part in conjuncts:
        if part[0] == "(" and part[-1] == ")":
            part = part[1:-1]
            names = as_or_chain(part)
            if names is None or include_any is not None:
                return None
            include_any = names
        elif len(part) == 2 and part[0] == "~":
            exclude.append(part[1])
        elif len(part) == 1:
            include_all.append(part[0])
        elif len(conjuncts) == 1:
            names = as_or_chain(part)
            if names is None:
                return None
            include_any = names
        else:
            return None

    if include_any is not None:
        return None if include_all else ("any", include_any, exclude)
    if not include_all and not exclude:
        return None
    return ("all", include_all, exclude)


def default_ei_groups(marker_names: list[str]) -> dict[str, str] | None:
    """Build an excitatory/inhibitory group spec from the markers available.

    Returns ``None`` when the spreadsheet has no inhibitory marker (in which
    case an E/I split is not derivable and the caller should fall back to
    one group per column).
    """
    inhibitory = [n for n in INHIBITORY_MARKERS if n in marker_names]
    if not inhibitory:
        return None
    inh_expr = " | ".join(inhibitory)
    not_inh = " & ".join(f"~{n}" for n in inhibitory)
    exc_expr = f"{NEURON_MARKER} & {not_inh}" if NEURON_MARKER in marker_names else not_inh
    return {"Excitatory": exc_expr, "Inhibitory": inh_expr}


@dataclass
class CellTypeGroups:
    """Resolved subnetwork groups for one recording.

    Attributes
    ----------
    names : group names, in output order.
    masks : ``(n_channels, n_groups)`` boolean membership; columns may overlap.
    marker_names, marker_matrix : the underlying spreadsheet columns.
    definitions : group name → the expression it was built from.
    """

    names: list[str]
    masks: np.ndarray
    marker_names: list[str]
    marker_matrix: np.ndarray
    definitions: dict[str, str] = field(default_factory=dict)

    @property
    def n_groups(self) -> int:
        return len(self.names)

    def indices(self, group: str, within: np.ndarray | None = None) -> np.ndarray:
        """0-based node indices belonging to *group*.

        ``within`` restricts to (and re-indexes against) a subset of channels —
        pass ``metrics["activeChannelIndex"]`` to get positions into the active
        subgraph rather than into the full channel list.
        """
        mask = self.masks[:, self.names.index(group)]
        if within is None:
            return np.nonzero(mask)[0]
        return np.nonzero(mask[np.asarray(within, dtype=int)])[0]

    def counts(self) -> dict[str, int]:
        return {name: int(self.masks[:, i].sum()) for i, name in enumerate(self.names)}

    def subset(self, indices: np.ndarray) -> "CellTypeGroups":
        """Same groups, restricted to a subset of nodes (e.g. the active ones).

        Group names are kept even if a group ends up empty, so a subsetted
        object still lines up column-for-column with the original.
        """
        idx = np.asarray(indices, dtype=int)
        return CellTypeGroups(list(self.names), self.masks[idx], list(self.marker_names),
                              self.marker_matrix[idx], dict(self.definitions))


def resolve_groups(
    cell_type_df: pd.DataFrame,
    channels: np.ndarray,
    group_spec: dict[str, str] | str | None = None,
) -> CellTypeGroups:
    """Turn a cell-type table into named node groups.

    ``group_spec`` may be:

    - ``None`` (default) — one group per spreadsheet column;
    - ``"E/I"`` — the excitatory/inhibitory split derived from the markers
      present (:func:`default_ei_groups`), falling back to per-column when no
      inhibitory marker exists;
    - a dict of ``{group name: boolean marker expression}``.

    Groups that end up empty are dropped (with the rest kept), so a spec
    written for a richer marker panel still works on a sparser recording.
    """
    marker_matrix, marker_names = build_marker_matrix(cell_type_df, channels)

    if isinstance(group_spec, str):
        if group_spec.strip().upper() not in ("E/I", "EI", "E_I"):
            raise GroupExpressionError(
                f"unknown group preset {group_spec!r}; use 'E/I', None, or a dict"
            )
        group_spec = default_ei_groups(marker_names)

    if not group_spec:
        definitions = {name: name for name in marker_names}
    else:
        definitions = dict(group_spec)

    names: list[str] = []
    columns: list[np.ndarray] = []
    kept: dict[str, str] = {}
    for name, expr in definitions.items():
        mask = eval_group_expression(expr, marker_matrix, marker_names)
        if not mask.any():
            continue
        names.append(name)
        columns.append(mask)
        kept[name] = expr

    masks = (np.column_stack(columns) if columns
             else np.zeros((len(np.asarray(channels).ravel()), 0), dtype=bool))
    return CellTypeGroups(names, masks, marker_names, marker_matrix, kept)


# ── Induced-subgraph metrics ──────────────────────────────────────────────────

# Label used for the reference row/panel covering every node, regardless of type.
WHOLE_NETWORK = "Whole network"


def compute_subnetwork_metrics(
    adj_m: np.ndarray,
    spike_counts: np.ndarray,
    duration_s: float,
    groups: CellTypeGroups,
    params,
    *,
    min_nodes: int = 25,
    rng: np.random.Generator | None = None,
    full_metrics: dict | None = None,
) -> dict[str, dict]:
    """Re-run the shared step-4 metric suite on each group's induced subgraph.

    The subgraph keeps only the group's nodes and the edges *among* them;
    ``compute_network_metrics`` then applies its usual active-node filter
    (nonzero strength + minimum activity) inside that subgraph, so a cell with
    no within-group partners drops out — which is the intended semantics.

    ``full_metrics`` (the already-computed whole-network result) is echoed back
    under :data:`WHOLE_NETWORK` as a reference row rather than recomputed, since
    the small-worldness null models are the expensive part.

    Returns ``{group name: metrics dict}``; groups smaller than *min_nodes*
    still appear but carry only ``aN`` / ``activeChannelIndex``, exactly as
    ``compute_network_metrics`` does for a too-small network.
    """
    from meanap.pipeline.step4 import compute_network_metrics

    results: dict[str, dict] = {}
    if full_metrics is not None:
        results[WHOLE_NETWORK] = full_metrics

    for name in groups.names:
        idx = groups.indices(name)
        if idx.size == 0:
            continue
        sub = adj_m[np.ix_(idx, idx)]
        metrics = compute_network_metrics(
            sub, np.asarray(spike_counts, dtype=float)[idx], duration_s,
            params.min_activity_level, min_nodes,
            exclude_edges_below_threshold=params.exclude_edges_below_threshold,
            params=params, rng=rng,
        )
        # activeChannelIndex is relative to the subgraph; also record where
        # those nodes sit in the full network so callers can map back.
        metrics["subnetworkNodeIndex"] = idx
        metrics["fullNetworkIndex"] = idx[metrics["activeChannelIndex"]]
        results[name] = metrics

    return results


# ── Edge mixing ───────────────────────────────────────────────────────────────

def compute_edge_mix(
    adj_m: np.ndarray, groups: CellTypeGroups, edge_thresh: float = 0.0,
) -> pd.DataFrame:
    """Group × group connectivity summary.

    One row per ordered-but-unique group pair (``A–A``, ``A–B``, ``B–B``) with:

    - ``nPossible`` / ``nEdges`` / ``Density`` — how many of the possible node
      pairs in that block carry an edge above *edge_thresh*;
    - ``MeanWeightNonzero`` — mean weight over the edges that exist;
    - ``MeanWeightAll`` — mean over every possible pair (zeros included), the
      quantity that scales with both density and strength.

    Self-connections are excluded throughout; within-group blocks count each
    undirected pair once. Between-group blocks count each pair once when the
    groups are disjoint; where two groups overlap, a pair of shared nodes is
    counted in both directions (it belongs to the block twice over), which
    leaves the density and mean-weight ratios unchanged.
    """
    adj = np.asarray(adj_m, dtype=float).copy()
    np.fill_diagonal(adj, 0.0)

    rows = []
    for i, gi in enumerate(groups.names):
        for j, gj in enumerate(groups.names[i:], start=i):
            idx_i = np.nonzero(groups.masks[:, i])[0]
            idx_j = np.nonzero(groups.masks[:, j])[0]
            block = adj[np.ix_(idx_i, idx_j)]
            if i == j:
                # Upper triangle only — each undirected pair once, no diagonal.
                weights = block[np.triu_indices(block.shape[0], k=1)]
            else:
                # Groups may overlap; drop the self-pairs a shared node creates.
                weights = block[idx_i[:, None] != idx_j[None, :]]
            n_possible = weights.size
            present = weights > edge_thresh
            rows.append({
                "GroupA": gi,
                "GroupB": gj,
                "Kind": "within" if i == j else "between",
                "nNodesA": int(idx_i.size),
                "nNodesB": int(idx_j.size),
                "nPossible": int(n_possible),
                "nEdges": int(present.sum()),
                "Density": float(present.sum() / n_possible) if n_possible else np.nan,
                "MeanWeightNonzero": float(weights[present].mean()) if present.any() else np.nan,
                "MeanWeightAll": float(weights.mean()) if n_possible else np.nan,
            })
    return pd.DataFrame(rows)


def within_group_strength_fraction(
    adj_m: np.ndarray, groups: CellTypeGroups,
) -> dict[str, np.ndarray]:
    """Per-node fraction of connection strength going to same-group partners.

    ``{group name: (n_nodes_in_group,) array}``. A value near 1 means the cell
    wires almost exclusively within its own type; near 0 means it is dominated
    by cross-type connections. NaN for nodes with zero total strength.
    """
    adj = np.asarray(adj_m, dtype=float).copy()
    np.fill_diagonal(adj, 0.0)
    total = adj.sum(axis=1)

    out: dict[str, np.ndarray] = {}
    for i, name in enumerate(groups.names):
        mask = groups.masks[:, i]
        idx = np.nonzero(mask)[0]
        within = adj[np.ix_(idx, idx)].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.where(total[idx] > 0, within / total[idx], np.nan)
        out[name] = frac
    return out


# ── Splitting whole-network node metrics by group ─────────────────────────────

# Keys of a metrics dict that are bookkeeping rather than per-node measurements.
_NON_METRIC_KEYS = {
    "aN", "activeChannelIndex", "adjMsub", "subnetworkNodeIndex", "fullNetworkIndex",
}


def node_metric_names(metrics: dict) -> list[str]:
    """Node-level (length-``aN``) numeric metric names present in *metrics*."""
    a_n = int(metrics.get("aN", 0))
    names = []
    for key, value in metrics.items():
        if key in _NON_METRIC_KEYS or not isinstance(value, (list, np.ndarray)):
            continue
        arr = np.asarray(value)
        if arr.ndim == 1 and arr.size == a_n and np.issubdtype(arr.dtype, np.number):
            names.append(key)
    return sorted(names)


def split_node_metrics(
    metrics: dict,
    groups: CellTypeGroups,
    channels: np.ndarray,
    *,
    adj_m: np.ndarray | None = None,
    include_unassigned: bool = True,
) -> pd.DataFrame:
    """Long-format table of whole-network node metrics tagged by cell type.

    One row per (active node × group it belongs to). Because groups overlap, a
    node positive for two markers contributes two rows — deliberate, so that
    per-group distributions are each complete. Nodes in no group are emitted
    once under ``"Unassigned"`` when *include_unassigned*.

    ``adj_m`` (the **full**, unsubsetted adjacency matrix) adds a
    ``WithinGroupStrengthFrac`` column.
    """
    active = np.asarray(metrics.get("activeChannelIndex", []), dtype=int)
    if active.size == 0:
        return pd.DataFrame()

    channels = np.asarray(channels).ravel()
    metric_names = node_metric_names(metrics)

    frac_by_group = (within_group_strength_fraction(adj_m, groups)
                     if adj_m is not None else {})
    # Map full-network node index → its within-group fraction, per group.
    frac_lookup: dict[str, dict[int, float]] = {}
    for name, values in frac_by_group.items():
        idx = groups.indices(name)
        frac_lookup[name] = dict(zip(idx.tolist(), values.tolist()))

    rows = []
    for pos, node in enumerate(active):
        base = {"Channel": int(channels[node]), "NodeIndex": int(node)}
        base.update({m: float(np.asarray(metrics[m])[pos]) for m in metric_names})
        memberships = [n for i, n in enumerate(groups.names) if groups.masks[node, i]]
        if not memberships and include_unassigned:
            memberships = ["Unassigned"]
        for name in memberships:
            row = dict(base, Group=name)
            row["WithinGroupStrengthFrac"] = frac_lookup.get(name, {}).get(int(node), np.nan)
            rows.append(row)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    lead = ["Group", "Channel", "NodeIndex"]
    return df[lead + [c for c in df.columns if c not in lead]]


def subnetwork_summary_rows(results: dict[str, dict]) -> list[dict]:
    """Flatten :func:`compute_subnetwork_metrics` output to scalar rows.

    Node-level arrays are collapsed to their mean (suffixed ``_mean``) so a
    single row fully summarises each group's subgraph.
    """
    rows = []
    for name, metrics in results.items():
        row: dict = {"Group": name, "aN": int(metrics.get("aN", 0))}
        node_metrics = set(node_metric_names(metrics))
        for key, value in metrics.items():
            if key in _NON_METRIC_KEYS:
                continue
            if key in node_metrics:
                arr = np.asarray(value, dtype=float)
                if arr.size:
                    row[f"{key}_mean"] = float(np.nanmean(arr))
                continue
            if isinstance(value, (list, np.ndarray)):
                arr = np.asarray(value)
                if arr.size == 1:
                    row[key] = arr.ravel()[0]
                continue
            row[key] = value
        rows.append(row)
    return rows
