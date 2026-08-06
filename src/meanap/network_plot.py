"""MEA network plotting: Python port of StandardisedNetworkPlot.m."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import scipy.io as sio

if TYPE_CHECKING:
    import matplotlib.axes


# ── Data loading ──────────────────────────────────────────────────────────────

class MatData:
    """Parsed contents of a MEA-NAP output .mat file."""

    def __init__(self, path: str) -> None:
        self.path = path
        raw = sio.loadmat(path, simplify_cells=True)

        self.info: dict = raw.get("Info", {})
        self.params: dict = raw.get("Params", {})
        self.coords: np.ndarray = np.array(raw["coords"])
        self.channels: np.ndarray = np.array(raw["channels"]).ravel()

        self._adjMs: dict = raw.get("adjMs", {})
        self._netmet: dict = raw.get("NetMet", {})

        # Discover available lag keys (e.g. "adjM1000mslag")
        self.lag_keys: list[str] = [
            k for k in self._adjMs if k.startswith("adjM") and k.endswith("mslag")
        ]
        self.lag_keys.sort(key=lambda k: int(k.replace("adjM", "").replace("mslag", "")))

        # Detect whether CellTypes is a readable table (not an opaque MCOS object)
        ct = self.info.get("CellTypes")
        self.has_readable_cell_types = isinstance(ct, (dict, pd.DataFrame, np.ndarray)) and not _is_opaque(ct)

    def lag_ms(self, lag_key: str) -> int:
        return int(lag_key.replace("adjM", "").replace("mslag", ""))

    def get_adjM(self, lag_key: str) -> np.ndarray:
        return np.array(self._adjMs[lag_key])

    def get_netmet(self, lag_key: str) -> dict:
        return self._netmet[lag_key]

    def get_active_indices(self, lag_key: str) -> np.ndarray:
        """Return 0-based active node indices."""
        idx = np.array(self.get_netmet(lag_key)["activeNodeIndices"]).ravel()
        return (idx - 1).astype(int)  # MATLAB 1-indexed → Python 0-indexed

    def get_metric(self, lag_key: str, metric: str) -> np.ndarray | None:
        nm = self.get_netmet(lag_key)
        if metric == "None" or metric not in nm:
            return None
        return np.array(nm[metric]).ravel()

    @property
    def available_node_metrics(self) -> list[str]:
        """Node-level metrics present in the first available lag."""
        if not self.lag_keys:
            return []
        nm = self._netmet[self.lag_keys[0]]
        active_idx = self.get_active_indices(self.lag_keys[0])
        n = len(active_idx)
        return [
            k for k, v in nm.items()
            if isinstance(v, (list, np.ndarray)) and np.array(v).ravel().shape == (n,)
            and np.issubdtype(np.array(v).dtype, np.number)
        ]


def _is_opaque(obj) -> bool:
    """True if obj is a scipy MatlabOpaque (unreadable MATLAB table)."""
    try:
        from scipy.io.matlab._mio5_params import MatlabOpaque
        return isinstance(obj, MatlabOpaque)
    except ImportError:
        return False


# ── Cell-type helpers ─────────────────────────────────────────────────────────

def load_cell_type_file(path: str) -> pd.DataFrame:
    """Load a cell type Excel or CSV file.

    The file should have one column per cell type, with channel numbers listed
    in each column (the same format as the PutativeCellType xlsx files).
    """
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def build_cell_type_matrix(
    cell_type_df: pd.DataFrame,
    channels: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    """Convert a cell-type DataFrame to a binary membership matrix.

    Mirrors MATLAB's getCellTypeMatrix.

    Returns
    -------
    matrix : (n_channels, n_types) int array  — 1 if channel belongs to type
    type_names : list of column names
    """
    channels = np.array(channels).ravel()
    type_names = list(cell_type_df.columns)
    n_types = len(type_names)
    matrix = np.zeros((len(channels), n_types), dtype=int)

    for j, col in enumerate(type_names):
        col_vals = cell_type_df[col].dropna().values
        for raw_val in col_vals:
            try:
                cid = int(raw_val)
            except (ValueError, TypeError):
                continue
            hits = np.where(channels == cid)[0]
            if len(hits):
                matrix[hits[0], j] = 1

    return matrix, type_names


def filter_by_cell_types(
    active_indices: np.ndarray,
    cell_type_matrix: np.ndarray,
    type_names: list[str],
    selected_types: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Return subset of active_indices (and matching rows of cell_type_matrix)
    where nodes belong to ALL selected cell types (intersection logic from MATLAB).

    Returns (subset_active_indices, subset_cell_type_matrix)
    """
    if not selected_types:
        return active_indices, cell_type_matrix

    subset_cols = [j for j, n in enumerate(type_names) if n in selected_types]
    if not subset_cols:
        return active_indices, cell_type_matrix

    row_sums = cell_type_matrix[:, subset_cols].sum(axis=1)
    keep = np.where(row_sums == len(selected_types))[0]
    return active_indices[keep], cell_type_matrix[keep, :]


# ── Node layout ───────────────────────────────────────────────────────────────

# User-facing layout names → the networkx layout used to compute coordinates.
# "Original (electrodes)" keeps the MEA electrode coordinates untouched; the rest
# mirror MATLAB's getNodeCoords / plotType='circular' options, computed here with
# networkx instead of MATLAB's graph plot layouts.
LAYOUT_OPTIONS = [
    "Original (electrodes)",
    "Circular",
    "Spring (force)",
    "Kamada-Kawai",
    "Spectral",
    "Shell",
]


def _rescale_to_box(pts: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Uniformly scale/centre *pts* so they fill the bounding box of *ref*.

    Layout algorithms return coordinates in an arbitrary range (typically
    [-1, 1]). Node radii, edge widths and legend offsets in ``plot_network`` are
    all expressed in data units tuned to the electrode-grid coordinate span, so
    a raw [-1, 1] layout would render nodes the size of the whole plot. Fitting
    every layout into the same box (preserving aspect ratio) keeps the visual
    scale consistent no matter which layout is chosen.
    """
    pts = np.asarray(pts, dtype=float)
    ref = np.asarray(ref, dtype=float)
    ref_min, ref_max = ref.min(axis=0), ref.max(axis=0)
    ref_span = ref_max - ref_min
    ref_span[ref_span == 0] = 1.0

    p_min, p_max = pts.min(axis=0), pts.max(axis=0)
    p_span = p_max - p_min
    p_span[p_span == 0] = 1.0

    scale = float(np.min(ref_span / p_span))  # uniform → preserve aspect ratio
    centred = (pts - (p_min + p_max) / 2) * scale
    return centred + (ref_min + ref_max) / 2


def compute_node_coords(
    adjM: np.ndarray,
    coords: np.ndarray,
    layout: str = "Original (electrodes)",
) -> np.ndarray:
    """Return node coordinates for the chosen *layout*.

    Python port of MATLAB's ``getNodeCoords`` (and the ``plotType='circular'``
    branch of ``StandardisedNetworkPlot``). ``"Original (electrodes)"`` returns
    the electrode coordinates unchanged; every other option derives positions
    from the network topology using networkx, then rescales the result into the
    electrode bounding box so node/edge/legend sizing stays consistent.
    """
    coords = np.asarray(coords, dtype=float)
    if layout in ("Original (electrodes)", "Original", "MEA", None):
        return coords

    import networkx as nx

    n = coords.shape[0]
    A = np.abs(np.asarray(adjM, dtype=float)).copy()
    np.fill_diagonal(A, 0.0)
    A[~np.isfinite(A)] = 0.0
    G = nx.from_numpy_array(A)
    has_edges = G.number_of_edges() > 0

    if layout == "Circular":
        pos = nx.circular_layout(G)
    elif layout == "Spring (force)":
        pos = nx.spring_layout(G, weight="weight", seed=0)
    elif layout == "Kamada-Kawai":
        pos = nx.kamada_kawai_layout(G, weight="weight") if has_edges \
            else nx.circular_layout(G)
    elif layout == "Spectral":
        pos = nx.spectral_layout(G, weight="weight")
    elif layout == "Shell":
        pos = nx.shell_layout(G)
    else:
        return coords

    new = np.array([pos[i] for i in range(n)], dtype=float)
    return _rescale_to_box(new, coords)


# ── Example (synthetic) network ───────────────────────────────────────────────

def make_example_network(
    n_nodes: int = 40, grid: int = 8, seed: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a synthetic MEA-like weighted network for the interactive demo.

    Nodes are placed on a *grid* × *grid* electrode lattice; edge weights fall
    off with inter-electrode distance (plus noise) so the result looks like a
    real functional-connectivity matrix. Returns ``(adjM, coords)`` with the
    weighted symmetric adjacency normalised to ``[0, 1]``.
    """
    rng = np.random.default_rng(seed)
    gx, gy = np.meshgrid(np.arange(1, grid + 1), np.arange(1, grid + 1))
    lattice = np.column_stack([gx.ravel(), gy.ravel()]).astype(float)
    n = min(n_nodes, len(lattice))
    coords = lattice[rng.choice(len(lattice), size=n, replace=False)]

    d = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
    w = np.exp(-d / 2.5) * rng.uniform(0.2, 1.0, size=d.shape)
    w = (w + w.T) / 2.0
    np.fill_diagonal(w, 0.0)

    nz = w[w > 0]
    if nz.size:
        w[w < np.quantile(nz, 0.82)] = 0.0  # keep the strongest ~18% of edges
    if w.max() > 0:
        w = w / w.max()
    return w, coords


# ── Edge subsampling / thresholding ───────────────────────────────────────────

EDGE_THRESHOLD_METHODS = [
    "Absolute value",
    "Percentile",
    "Percentile (nonzero edges)",
]


def limit_edges_for_plotting(
    adjM: np.ndarray,
    max_edges: int | None = None,
    method: str = "HighToLow",
) -> np.ndarray:
    """Keep only the strongest *max_edges* edges, zeroing the rest.

    Python port of MATLAB's ``limitEdgesForPlotting`` — a plotting-only
    subsample so dense networks don't render as an unreadable hairball. The
    ``HighToLow`` method keeps the ``max_edges`` edges with the largest absolute
    weight. Node metrics are unaffected (this only changes which edges are drawn).

    ``max_edges=None`` (or 0) returns a cleaned copy with no limiting.
    """
    A = np.asarray(adjM, dtype=float).copy()
    A[~np.isfinite(A)] = 0.0
    if not max_edges:  # None or 0 → unlimited
        return A

    n = A.shape[0]
    np.fill_diagonal(A, 0.0)
    is_undirected = np.allclose(A, A.T)
    mask = np.triu(np.ones((n, n), dtype=bool), k=1) if is_undirected \
        else ~np.eye(n, dtype=bool)

    weights = A[mask]
    valid = np.nonzero(weights != 0)[0]
    out = np.zeros((n, n), dtype=float)
    if valid.size == 0:
        return out

    if valid.size <= max_edges:
        kept = valid
    elif method.lower().replace("_", "").replace(" ", "") == "hightolow":
        order = np.argsort(np.abs(weights[valid]))[::-1]  # strongest first
        kept = valid[order[:max_edges]]
    else:
        raise ValueError(f"Unknown edge subsampling method: {method}")

    filtered = np.zeros_like(weights)
    filtered[kept] = weights[kept]
    out[mask] = filtered
    if is_undirected:
        out = np.maximum(out, out.T)
    out[~np.isfinite(out)] = 0.0
    return out


def get_edge_threshold(
    adjM: np.ndarray,
    method: str = "Absolute value",
    threshold: float = 0.0,
    percentile: float = 90.0,
) -> float:
    """Return the edge-weight threshold for plotting (port of ``getEdgeThreshold``).

    - ``"Absolute value"`` returns *threshold* verbatim.
    - ``"Percentile"`` returns the *percentile*-th percentile of ALL adjacency
      entries (MATLAB's ``prctile(adjM(:), p)`` — zeros/diagonal included, so a
      low percentile does nothing on a sparse matrix; kept for MATLAB parity).
    - ``"Percentile (nonzero edges)"`` returns the *percentile*-th percentile of
      only the actual (nonzero, finite, off-diagonal) edge weights, so e.g. 80
      keeps the strongest ~20 % of edges — the intuitive behaviour.
    """
    A = np.asarray(adjM, dtype=float)
    if method == "Percentile":
        return float(np.percentile(A.ravel(), percentile))
    if method == "Percentile (nonzero edges)":
        n = A.shape[0]
        offdiag = ~np.eye(n, dtype=bool)
        w = A[offdiag]
        w = w[np.isfinite(w) & (w != 0)]
        if w.size == 0:
            return 0.0
        return float(np.percentile(w, percentile))
    return float(threshold)


def count_edges_shown(adjM: np.ndarray, edge_thresh: float) -> int:
    """Number of undirected edges that will be drawn at *edge_thresh*."""
    A = np.asarray(adjM, dtype=float)
    n = A.shape[0]
    mask = np.triu(np.ones((n, n), dtype=bool), k=1)
    w = A[mask]
    return int(np.count_nonzero(np.isfinite(w) & (w >= edge_thresh) & (w != 0)))


# ── Network rendering ─────────────────────────────────────────────────────────

#: Dash patterns distinguishing cell-type marker rings. Colour is left to encode
#: the node's metric, so identity is carried by line style instead: each marker
#: gets its own pattern, ordered so neighbouring markers look as different as
#: possible (solid → fine dot → long dash → …) rather than shading gradually
#: into one another.
_CELL_TYPE_RING_STYLES = [
    "solid",
    (0, (1, 1.4)),          # fine dotted
    (0, (5, 2)),            # long dashed
    (0, (1.2, 1.2, 4, 1.2)),  # dash-dot
    (0, (2.5, 1.6)),        # short dashed
    (0, (0.8, 2.2)),        # sparse dotted
    (0, (6, 1.4, 1, 1.4)),  # long dash-dot
    (0, (3.5, 1.2, 3.5, 3)),  # uneven dashed
]


#: The largest node's diameter, as a fraction of the median distance between
#: neighbouring nodes. Calibrated so ``"auto"`` reproduces the historic fixed
#: scale of 1.0 exactly on a standard MEA layout (whose median nearest-neighbour
#: spacing is ~1.143 data units), while shrinking nodes on denser fields — a 2P
#: field of ~250 cells packs them ~5x closer, where the fixed scale drew each
#: node 4.6x the inter-cell distance and the network became a solid mass.
_NODE_DIAMETER_PER_SPACING = 0.875


def median_node_spacing(coords: np.ndarray) -> float:
    """Median distance from a node to its nearest neighbour. 0 if undefined."""
    coords = np.asarray(coords, dtype=float)
    if coords.ndim != 2 or len(coords) < 2:
        return 0.0
    from scipy.spatial.distance import pdist, squareform
    d = squareform(pdist(coords))
    np.fill_diagonal(d, np.inf)
    nearest = d.min(axis=1)
    nearest = nearest[np.isfinite(nearest)]
    return float(np.median(nearest)) if nearest.size else 0.0


def auto_node_size_scale(coords: np.ndarray) -> float:
    """Node-size multiplier that keeps nodes from overlapping on dense fields.

    Node sizes are in data units, so a scale tuned for a 60-electrode MEA grid
    draws hugely oversized nodes on a two-photon field of hundreds of cells
    packed into the same coordinate box. Deriving the scale from the actual
    median nearest-neighbour spacing fixes that, and is a no-op on MEA layouts
    by construction (see :data:`_NODE_DIAMETER_PER_SPACING`).
    """
    spacing = median_node_spacing(coords)
    if spacing <= 0:
        return 1.0
    return _NODE_DIAMETER_PER_SPACING * spacing


def _cell_type_styles(k: int) -> list:
    """Ring dash patterns for *k* markers, cycling past the end of the set."""
    return [_CELL_TYPE_RING_STYLES[i % len(_CELL_TYPE_RING_STYLES)] for i in range(k)]


def _ring_radii(k: int) -> np.ndarray:
    """Ring radius per marker as a fraction of node diameter, outermost first.

    Fixed by marker *index*, so the same marker always sits at the same radius
    across every node and every figure — that is what makes a ring readable as
    an identity rather than just a count.
    """
    return np.linspace(0.92, 0.34, k) if k > 1 else np.array([0.7])


def _get_node_size(
    z_i: float,
    node_scale_f: float,
    min_node_size: float = 0.01,
    *,
    method: str = "Linear",
    power: float = 1.0,
    size_mult: float = 1.0,
) -> float:
    """Map a per-node metric value to a node radius-driving size.

    Port of MATLAB's ``getNodeSize``: the scaling *method* (Linear / Log2 /
    Log10 / Square / Cube / Power) reshapes how ``z_i`` maps onto ``[0, 1]``
    relative to ``node_scale_f``, and *size_mult* is a final user-facing
    multiplier (MATLAB's ``maxNodeSize``) for making every node bigger/smaller.
    """
    nsf = max(float(node_scale_f), 1e-9)
    zi = max(float(z_i), 0.0)
    if method == "Log2":
        base = np.log2(zi + 1) / np.log2(nsf + 1)
    elif method == "Log10":
        base = np.log10(zi + 1) / np.log10(nsf + 1)
    elif method == "Square":
        base = (zi ** 2) / (nsf ** 2)
    elif method == "Cube":
        base = (zi ** 3) / (nsf ** 3)
    elif method == "Power":
        base = (zi ** power) / (nsf ** power)
    else:  # Linear
        base = zi / nsf
    return max(min_node_size, size_mult * float(base))


def plot_network(
    ax: "matplotlib.axes.Axes",
    adjM: np.ndarray,
    coords: np.ndarray,
    edge_thresh: float,
    z: np.ndarray,
    z2: np.ndarray | None = None,
    z2_name: str = "None",
    cell_type_matrix: np.ndarray | None = None,
    cell_type_names: list[str] | None = None,
    cell_type_styles: list | None = None,
    background: tuple | None = None,
    min_node_size: float = 0.01,
    title: str = "",
    z_name: str = "node degree",
    z_scale_override: float | None = None,
    z2_bounds_override: tuple[float, float] | None = None,
    edge_bounds_override: tuple[float, float] | None = None,
    min_ew: float = 0.001,
    max_ew: float = 4.0,
    node_size_scale: float | str = 1.0,
    node_scaling_method: str = "Linear",
    node_scaling_power: float = 1.0,
) -> None:
    """Render the MEA network onto *ax*.

    Closely mirrors MATLAB's StandardisedNetworkPlot / StandardisedNetworkPlotNodeColourMap
    (MEA plot-type branch).

    Parameters
    ----------
    adjM : (N, N) adjacency matrix for active nodes
    coords : (N, 2) electrode coordinates for active nodes
    edge_thresh : minimum edge weight to draw
    z : (N,) array driving node SIZE — node degree by default, but any
        non-negative per-node metric works (e.g. node strength)
    z2 : (N,) optional metric driving node COLOR; None / all-NaN = flat cyan
    z2_name : display name for the color metric
    cell_type_matrix : (N, K) binary membership matrix, or None. Drawn as K
        concentric rings per node — marker ``k`` always at radius ``k``, in its
        own dash pattern, solid-drawn when the cell is positive and faint when
        it is negative, so each node carries its full genetic identity. Rings
        are unfilled and uncoloured, so the ``z2`` colormap stays visible
        underneath and colour is not overloaded.
    cell_type_names : length-K list of type names
    cell_type_styles : length-K ring dash patterns; defaults to a fixed set so a
        marker keeps the same pattern across every figure
    background : ``(image_2d, (x0, x1, y0, y1))`` drawn under the network, in
        data coordinates — the CAT-NAP path passes suite2p's mean projection so
        nodes can be checked against the actual field of view. Contrast is
        clipped to the 1st–99th percentile and dimmed, so the image reads as a
        backdrop rather than competing with the edges.
    z_name : display name for the size metric ``z`` (legend label) —
        defaults to "node degree" since that's the Network Viewer GUI's only
        use of this function; pass e.g. "node strength" when ``z`` isn't ND
    z_scale_override : if given, use this as the node-size scale factor
        (``node_scale_f``) instead of this recording's own ``max(z)``. Set it
        to the batch-wide max of the size metric to render the "scaled to
        entire data batch" variant, where node sizes are comparable across
        recordings. Mirrors MATLAB's ``nodeScaleF = max(Params.metricsMinMax.
        (zShortForm))`` under ``useMinMaxBoundsForPlots``.
    z2_bounds_override : if given, ``(min, max)`` for the color normalization
        instead of this recording's own ``z2`` range — the batch-wide color
        scale. Mirrors MATLAB's ``z2_min``/``z2_max`` from ``metricsMinMax``.
    edge_bounds_override : if given, ``(min, max)`` for edge-weight width/shade
        scaling instead of this recording's own nonzero-edge range. MATLAB
        fixes this to ``EW = [0.1, 1]`` for the scaled variants.
    min_ew, max_ew : minimum / maximum edge line width in points. The strongest
        edge is drawn at ``max_ew`` and the weakest at ``min_ew`` (MATLAB
        defaults: 4.0 / 0.001 for the MEA plot type). User-adjustable in the
        interactive viewer.
    node_size_scale : final multiplier applied to every node size (MATLAB's
        ``maxNodeSize``); 1.0 reproduces the original scaling, >1 enlarges
        nodes. Pass ``"auto"`` to derive it from how densely the nodes are
        packed (:func:`auto_node_size_scale`) — necessary for two-photon fields,
        and a no-op on MEA electrode layouts.
    node_scaling_method : one of Linear / Log2 / Log10 / Square / Cube / Power —
        how ``z`` maps onto node size (MATLAB ``nodeScalingMethod``).
    node_scaling_power : exponent used when ``node_scaling_method == "Power"``.
    """
    import matplotlib
    import matplotlib.patches as mpatches
    import matplotlib.colors as mcolors

    ax.clear()
    ax.set_facecolor("white")
    ax.set_aspect("equal")
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=9, color="black")

    n = len(adjM)
    xc = coords[:, 0]
    yc = coords[:, 1]

    if isinstance(node_size_scale, str):
        node_size_scale = (auto_node_size_scale(coords)
                           if node_size_scale == "auto" else 1.0)

    # ── Optional backdrop image ───────────────────────────────────────────────
    if background is not None:
        bg_img, bg_extent = background
        bg_img = np.asarray(bg_img, dtype=float)
        finite = bg_img[np.isfinite(bg_img)]
        if finite.size:
            lo, hi = np.percentile(finite, [1, 99])
            if hi <= lo:
                lo, hi = float(finite.min()), float(finite.max()) or 1.0
            ax.imshow(bg_img, cmap="gray", origin="lower", extent=bg_extent,
                      vmin=lo, vmax=hi, alpha=0.85, zorder=0,
                      interpolation="bilinear", aspect="equal")

    z_max = float(np.nanmax(z)) if np.any(~np.isnan(z)) else 0.0
    # The "at least 3" floor only makes sense for integer-valued node degree
    # (avoids degenerate legend divisions when max ND is 1 or 2) — forcing
    # it on a continuous metric like node strength (typically << 1) makes
    # every node render far smaller than intended, since node_size = z_i /
    # node_scale_f. Only apply the floor when z actually looks degree-like.
    looks_like_degree = z_name == "node degree" or np.allclose(z, np.round(z), equal_nan=True)
    if z_scale_override is not None:
        # Batch-wide scale: node sizes become comparable across recordings.
        node_scale_f = max(float(z_scale_override), 1e-9)
    else:
        node_scale_f = max(z_max, 3.0) if looks_like_degree else max(z_max, 1e-9)

    # ── Determine node coloring ───────────────────────────────────────────────
    use_colormap = (
        z2 is not None
        and z2_name != "None"
        and not np.all(np.isnan(z2))
    )
    if use_colormap:
        cmap = matplotlib.colormaps["viridis"]
        if z2_bounds_override is not None:
            z2_min, z2_max = (float(v) for v in z2_bounds_override)
        else:
            z2_min = float(np.nanmin(z2))
            z2_max = float(np.nanmax(z2))
        z2_range = z2_max - z2_min if z2_max > z2_min else 1.0
        norm = mcolors.Normalize(vmin=z2_min, vmax=z2_max)

        def node_facecolor(i: int):
            return cmap(norm(float(z2[i]))) if not np.isnan(z2[i]) else (0.5, 0.5, 0.5, 1.0)
    else:
        def node_facecolor(i: int):
            return (0.020, 0.729, 0.859)

    default_node_color = (0.020, 0.729, 0.859)

    # ── Node-size helper (captures scaling config) ─────────────────────────────
    def node_size_of(z_i: float) -> float:
        return _get_node_size(
            z_i, node_scale_f, min_node_size,
            method=node_scaling_method, power=node_scaling_power,
            size_mult=node_size_scale,
        )

    # ── Edges ─────────────────────────────────────────────────────────────────
    light_c = np.array([0.8, 0.8, 0.8])

    if edge_bounds_override is not None:
        # Batch-wide edge scale (MATLAB fixes this to EW = [0.1, 1]).
        min_nonzero, thresh_max = (float(v) for v in edge_bounds_override)
    else:
        nonzero_vals = adjM[adjM > 0]
        if len(nonzero_vals) == 0:
            thresh_max = 1.0
            min_nonzero = 1.0
        else:
            thresh_max = float(nonzero_vals.max())
            min_nonzero = float(nonzero_vals.min())

    edge_range = thresh_max - min_nonzero
    if edge_range == 0:
        edge_range = thresh_max - min_ew
        min_nonzero = min_ew

    edges_x, edges_y, edge_lw, edge_colors = [], [], [], []
    for a in range(n):
        for b in range(n):
            w = adjM[a, b]
            if w >= edge_thresh and a != b and not np.isnan(w):
                t = np.clip((w - min_nonzero) / edge_range, 0.0, 1.0)
                lw = min_ew + (max_ew - min_ew) * t
                col = np.clip(1.0 - light_c * t, 0.0, 1.0)
                edges_x.append([xc[a], xc[b]])
                edges_y.append([yc[a], yc[b]])
                edge_lw.append(lw)
                edge_colors.append(col)

    # Sort edges light → dark so darker edges draw last (on top), then render
    # them all as a single LineCollection. Drawing each edge as its own
    # ax.plot() Line2D was the dominant plotting cost — hundreds of artists per
    # figure × 144 figures — profiled as ~500k draw_path calls. One collection
    # is visually identical (same per-edge color/width, same draw order) but an
    # order of magnitude fewer matplotlib objects.
    if edges_x:
        from matplotlib.collections import LineCollection

        order = np.argsort([c[0] for c in edge_colors])[::-1]
        segments = [
            np.array([[edges_x[idx][0], edges_y[idx][0]],
                      [edges_x[idx][1], edges_y[idx][1]]])
            for idx in order
        ]
        lc = LineCollection(
            segments,
            colors=[edge_colors[idx] for idx in order],
            linewidths=[edge_lw[idx] for idx in order],
            capstyle="round",
            zorder=1,
        )
        ax.add_collection(lc)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    has_ct = (
        cell_type_matrix is not None
        and cell_type_names is not None
        and cell_type_matrix.shape[1] > 0
    )

    # Concentric marker rings (MATLAB StandardisedNetworkPlot draws these too,
    # but all solid white, so a marker is identifiable only by which radius its
    # ring sits at). Here each marker gets its own dash pattern at its own fixed
    # radius, and the slots a cell is *negative* for are still drawn, faintly —
    # so a node shows its complete genetic identity rather than only the
    # markers it happens to be positive for. Rings are unfilled and uncoloured,
    # leaving the node's interior and its colour free for the metric colormap.
    if has_ct and cell_type_styles is None:
        cell_type_styles = _cell_type_styles(cell_type_matrix.shape[1])

    outer_patches = []
    halo_patches = []
    inner_patches = []
    absent_patches = []
    for i in range(n):
        zi = float(z[i]) if not np.isnan(z[i]) else 0.0
        if zi <= 0:
            continue

        node_size = node_size_of(zi)
        fc = node_facecolor(i)
        outer_patches.append(mpatches.Circle(
            (xc[i], yc[i]), node_size / 2,
            facecolor=fc, edgecolor="white", linewidth=0.1,
        ))

        if has_ct:
            ct_sizes = _ring_radii(cell_type_matrix.shape[1]) * node_size
            # Ring strokes are in points but node radii are in data units, so a
            # fixed line width swamps a small node — scale them together, with
            # a floor so the thinnest rings stay visible.
            rel = float(np.clip(node_size / max(node_size_scale, 1e-9), 0.3, 1.0))
            for k in range(cell_type_matrix.shape[1]):
                r = ct_sizes[k] / 2
                style = cell_type_styles[k % len(cell_type_styles)]
                if cell_type_matrix[i, k] == 1:
                    # Dark halo under a white dashed ring, so the pattern stays
                    # readable at both ends of viridis — white alone vanishes on
                    # the yellow end, black alone on the blue end.
                    halo_patches.append(mpatches.Circle(
                        (xc[i], yc[i]), r, facecolor="none",
                        edgecolor=(0, 0, 0, 0.55), linewidth=2.2 * rel,
                    ))
                    inner_patches.append(mpatches.Circle(
                        (xc[i], yc[i]), r, facecolor="none",
                        edgecolor="white", linewidth=1.1 * rel, linestyle=style,
                    ))
                else:
                    absent_patches.append(mpatches.Circle(
                        (xc[i], yc[i]), r, facecolor="none",
                        edgecolor=(1, 1, 1, 0.18), linewidth=0.5 * rel, linestyle=style,
                    ))

    # Batch node circles into PatchCollections (match_original keeps each
    # circle's own face/edge/width/style) — same artist-count reduction as the
    # edge LineCollection: one draw call instead of one add_patch per node.
    # Outer circles sit at zorder 2 (above edges); cell-type inner rings at
    # zorder 3 (above the outer circle).
    from matplotlib.collections import PatchCollection

    if outer_patches:
        ax.add_collection(PatchCollection(outer_patches, match_original=True, zorder=2))
    if absent_patches:
        # Negative-marker slots go under the positive rings, so an overlap never
        # hides a marker the cell actually carries.
        ax.add_collection(PatchCollection(absent_patches, match_original=True, zorder=3))
    if halo_patches:
        ax.add_collection(PatchCollection(halo_patches, match_original=True, zorder=4))
    if inner_patches:
        ax.add_collection(PatchCollection(inner_patches, match_original=True, zorder=5))

    # ── Legend: node size metric ────────────────────────────────────────────────
    x_max = float(xc.max())
    y_max = float(yc.max())
    x_min = float(xc.min())
    y_min = float(yc.min())

    legend_x = x_max + 1.5

    ax.text(legend_x, y_max, f"{z_name}:", fontsize=7, va="bottom", color="black")

    leg_divisor = 3
    leg_vals = [node_scale_f * d / leg_divisor for d in range(1, leg_divisor + 1)]
    if looks_like_degree:
        leg_vals = [round(v) for v in leg_vals]
        leg_label = lambda v: f"{int(v):02d}"
    else:
        leg_label = lambda v: f"{v:.4f}"
    leg_y = y_max - 0.5
    for lv in leg_vals:
        ls = node_size_of(lv)
        circ = mpatches.Circle(
            (legend_x + 0.5, leg_y - ls / 2),
            ls / 2,
            facecolor=default_node_color, edgecolor="white", linewidth=0.1, zorder=4,
        )
        ax.add_patch(circ)
        ax.text(legend_x + 1.3, leg_y, leg_label(lv), fontsize=7, va="center", color="black")
        leg_y -= ls + 0.4

    # ── Legend: edge weight ───────────────────────────────────────────────────
    ax.text(legend_x, leg_y - 0.1, "edge weight:", fontsize=7, va="bottom", color="black")
    for frac in [1 / 3, 2 / 3, 1.0]:
        ew_val = min_nonzero + (thresh_max - min_nonzero) * frac
        t = np.clip((ew_val - min_nonzero) / edge_range, 0.0, 1.0)
        lw = min_ew + (max_ew - min_ew) * t
        col = np.clip(1.0 - light_c * t, 0.0, 1.0)
        leg_y -= 0.5
        ax.plot(
            [legend_x, legend_x + 1.0], [leg_y, leg_y],
            color=col, linewidth=lw, zorder=4,
        )
        ax.text(legend_x + 1.3, leg_y, f"{ew_val:.3f}", fontsize=7, va="center", color="black")

    # ── Legend: node color (colorbar) ─────────────────────────────────────────
    if use_colormap:
        leg_y -= 0.6
        ax.text(legend_x, leg_y, f"{z2_name}:", fontsize=7, va="bottom", color="black")
        n_steps = 20
        bar_h = 0.18
        for s in range(n_steps):
            frac_s = s / (n_steps - 1)
            rect = mpatches.Rectangle(
                (legend_x, leg_y - bar_h * (n_steps - s)),
                0.6, bar_h,
                facecolor=cmap(frac_s), edgecolor="none", zorder=4,
            )
            ax.add_patch(rect)
        ax.text(legend_x + 0.8, leg_y - bar_h, f"{z2_max:.3f}", fontsize=6, va="top", color="black")
        ax.text(legend_x + 0.8, leg_y - bar_h * n_steps, f"{z2_min:.3f}", fontsize=6, va="bottom", color="black")
        leg_y -= bar_h * n_steps + 0.4

    # ── Legend: cell-type marker rings ────────────────────────────────────────
    # A single schematic node showing every ring slot in its own colour, with
    # the marker names listed in the same outermost→innermost order — so the
    # reader can map a ring's radius *and* its colour back to a marker.
    if has_ct:
        n_ct = len(cell_type_names)
        leg_node_size = max(node_size_of(leg_vals[-1]), (x_max - x_min) * 0.12)
        cx = x_min + leg_node_size / 2
        leg_y_ct = y_min - 0.8 - leg_node_size / 2

        ax.add_patch(mpatches.Circle(
            (cx, leg_y_ct), leg_node_size / 2,
            facecolor=default_node_color, edgecolor="white", linewidth=0.1, zorder=4,
        ))
        radii = _ring_radii(n_ct) * leg_node_size
        for k in range(n_ct):
            style = cell_type_styles[k % len(cell_type_styles)]
            ax.add_patch(mpatches.Circle(
                (cx, leg_y_ct), radii[k] / 2, facecolor="none",
                edgecolor=(0, 0, 0, 0.55), linewidth=2.6, zorder=5,
            ))
            ax.add_patch(mpatches.Circle(
                (cx, leg_y_ct), radii[k] / 2, facecolor="none",
                edgecolor="white", linewidth=1.4, linestyle=style, zorder=6,
            ))

        label_x = cx + leg_node_size * 0.75
        step = leg_node_size / max(n_ct, 1)
        top = leg_y_ct + leg_node_size / 2 - step / 2
        for k, ct_name in enumerate(cell_type_names):
            ly = top - k * step
            # A long segment: two dash patterns are only telling apart over
            # enough length to show a full repeat of each.
            seg_x = [label_x, label_x + leg_node_size * 0.85]
            ax.plot(seg_x, [ly, ly], color=(0, 0, 0, 0.55), linewidth=3.2, zorder=5)
            ax.plot(seg_x, [ly, ly], color="white", linewidth=1.7, zorder=6,
                    linestyle=cell_type_styles[k % len(cell_type_styles)])
            ax.text(label_x + leg_node_size * 0.95, ly, str(ct_name),
                    fontsize=6, ha="left", va="center", color="black")
        ax.text(cx, leg_y_ct + leg_node_size * 0.62, "genetic identity",
                fontsize=6, ha="center", va="bottom", color="black")
        ax.text(cx, leg_y_ct - leg_node_size * 0.62,
                "bright ring = positive, faint = negative",
                fontsize=5, ha="center", va="top", color="0.45")

    # ── Axis limits ───────────────────────────────────────────────────────────
    ax.set_xlim(x_min - 1, x_max + 4.0)
    y_bottom = (y_min - 1.8) if has_ct else (y_min - 1.0)
    ax.set_ylim(y_bottom, y_max + 1.5)
