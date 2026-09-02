"""Persisting CAT-NAP's step-2 products so a later run can resume at step 4.

``MEApipeline.m`` appends ``adjMs`` (and the activity data it was derived from)
to each recording's ``ExperimentMatFiles/<rec>_<folder>.mat`` at the end of
step 2 — that append is what lets ``Params.priorAnalysis = 1`` +
``Params.startAnalysisStep = 4`` re-run the network analysis without redoing
``suite2pToAdjm``. This module is the port of it: one
``ExperimentMatFiles/<rec>_catnap.npz`` per recording, holding exactly what
phases 2 and 3 of :func:`~meanap.catnap.pipeline.run_catnap_pipeline` need and
nothing else.

What is deliberately *not* stored:

- **the fluorescence matrices** (``F`` / ``denoisedF`` / ``spks``) — hundreds of
  MB per recording, and phase 3 already re-reads them from the suite2p folder
  for the trace figures, so a copy here would be dead weight. MATLAB does store
  them, because its one chained ``.mat`` is also how step 4 gets the activity
  matrix; this port keeps the derived per-node quantities (``spike_counts``)
  instead, which is all that step 4 actually consumes.
- **cell-type groups and markers** — cheap to re-read from the spreadsheet, and
  re-reading means a resumed run picks up an edited grouping rather than
  freezing whatever the first run happened to use.

The file therefore stays small (adjacency is ``n_units²``), which matters: a
resumed run rewrites it into the new output folder so that folder is itself
resumable, and chains of resumes shouldn't each cost a full data copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from meanap.pipeline.atomic import atomic_savez

__all__ = [
    "RecordingState",
    "save_recording_state",
    "load_recording_state",
    "save_background",
    "load_background",
    "lag_from_adjm_key",
    "sorted_adjm_items",
    "BACKGROUND_SUFFIX",
]

#: Bumped when the stored key set changes incompatibly. A mismatch raises
#: rather than silently half-loading a file from an older port.
#:
#: 2 — added the cell-type marker matrix, so a shared bundle can draw the
#:     marker rings without the recipient having the spreadsheet.
#: 3 — added the resolved cell-type groups, needed by the by-cell-type activity
#:     comparisons (the grouping is a user choice, not derivable from markers).
#: 4 — added the lag-independent activity metrics (effRank, NMF). Recovering
#:     them otherwise means re-reading the raw fluorescence, which a resumed
#:     run or a bundle recipient may not have.
#: 5 — added the acquisition frame rate. It comes from each recording's own
#:     ops.npy and varies *within* a batch, so it is a property of the
#:     recording rather than of the run — and neither params.json nor anything
#:     else in the output folder recorded it.
FORMAT_VERSION = 5

_ADJ_PREFIX = "adj__"
_STAT_PREFIX = "stat__"
_LAGINDEP_PREFIX = "lagindep__"

#: Suffix of the optional per-recording mean-projection file (CAT-NAP only).
BACKGROUND_SUFFIX = "_background.npz"


@dataclass
class RecordingState:
    """What phases 2 and 3 need about a recording, without its activity matrices.

    ``suite2p_to_adjm`` returns the full ``(n_frames, n_units)`` fluorescence,
    denoised-fluorescence and spks matrices — hundreds of MB per recording, so
    holding them for a whole batch across the cartography barrier is not an
    option. Everything here is small (adjacency matrices are ``n_units²``); the
    trace figures re-read the suite2p folder at ``plane0`` instead.
    """

    adjMs: dict[str, np.ndarray]
    coords: np.ndarray
    channels: np.ndarray
    spike_counts: np.ndarray
    duration_s: float
    plane0: Path
    #: Acquisition frame rate (Hz), read from this recording's own ``ops.npy``.
    #: Held per recording, not per run, because a 2P batch routinely mixes
    #: rates — every seconds-valued setting (denoising windows, event
    #: interval) is converted to frames with *this* number, and every rate
    #: metric is divided by a duration derived from it. 0.0 when read back
    #: from a file written before format 5.
    fs: float = 0.0
    #: User-defined cell-type groups (E/I, per-marker, …) — drives the
    #: subnetwork analysis and the by-cell-type activity comparisons.
    groups: object | None = None
    #: ``(n_channels, n_markers)`` raw marker membership + names, straight from
    #: the spreadsheet. Distinct from ``groups``: this is the cell's full
    #: genetic identity, drawn as concentric rings on the network plots, and it
    #: is not collapsed into whatever grouping the user chose.
    markers: tuple[np.ndarray, list[str]] | None = None
    #: ``(min, max)`` used to normalise the pixel centroids onto ``coords`` —
    #: needed to map the mean projection image into the same frame.
    coord_norm: tuple[float, float] = (0.0, 1.0)
    #: ``(image, extent)`` field-of-view backdrop, captured in phase 1 while the
    #: suite2p data is already open and persisted separately (see
    #: :func:`save_background`). Held here so phase 3 need not re-read the raw
    #: folder for it — the difference between one pass over the raw data and two.
    background: tuple | None = None
    #: Metrics read off the *activity* matrix rather than any adjacency matrix,
    #: so they are computed once per recording and copied onto every lag —
    #: ``effRank`` always, the NMF fields when enabled. Held on the state (and
    #: persisted) so a step-4 resume does not have to re-read the raw
    #: fluorescence to recover them.
    lag_independent: dict = field(default_factory=dict)


def lag_from_adjm_key(key: str) -> int:
    """``'adjM25mslag'`` → ``25``."""
    return int(key[len("adjM"):-len("mslag")])


def sorted_adjm_items(adjMs: dict[str, np.ndarray]) -> list[tuple[int, np.ndarray]]:
    """``adjMs`` as ``(lag_ms, matrix)`` pairs, ascending by lag.

    Sorting rather than trusting dict order keeps a resumed run's log lines,
    CSV row order and figure order identical to the run that produced the file,
    regardless of how the lags were listed in Params or how the ``.npz`` stored
    them.
    """
    return sorted(
        ((lag_from_adjm_key(k), v) for k, v in adjMs.items()),
        key=lambda pair: pair[0],
    )


def save_recording_state(path: Path, state: RecordingState, stats: dict) -> None:
    """Write one recording's step-2 products to ``path`` (an ``.npz``).

    ``stats`` is a :func:`~meanap.catnap.stats.calc_twop_activity_stats` dict;
    its ``None`` values (the 2P-specific metrics, absent for the non-``peaks``
    activity types) are recorded by name and restored as ``None``, since
    downstream code distinguishes "not applicable" from NaN.
    """
    arrays: dict[str, np.ndarray] = {
        "catnap_format": np.array(FORMAT_VERSION),
        "coords": np.asarray(state.coords, dtype=float),
        "channels": np.asarray(state.channels),
        "spike_counts": np.asarray(state.spike_counts, dtype=float),
        "duration_s": np.array(float(state.duration_s)),
        "fs": np.array(float(state.fs)),
        "coord_norm": np.asarray(state.coord_norm, dtype=float),
    }
    for key, adj in state.adjMs.items():
        arrays[f"{_ADJ_PREFIX}{key}"] = np.asarray(adj, dtype=float)

    # Cell-type markers. A local re-run re-reads these from the spreadsheet
    # (see the loader), but a bundle shared with someone who has no spreadsheet
    # still needs them to draw the marker rings.
    if state.markers is not None:
        marker_matrix, marker_names = state.markers
        arrays["marker_matrix"] = np.asarray(marker_matrix, dtype=float)
        arrays["marker_names"] = np.asarray(list(marker_names), dtype=str)

    # The resolved grouping (E/I, per-marker, a custom expression …) is a user
    # choice that markers alone don't determine, and the by-cell-type activity
    # comparisons need it. Stored flat so this module keeps no dependency on
    # catnap.subnetwork.
    groups = state.groups
    if groups is not None and getattr(groups, "n_groups", 0):
        arrays["group_names"] = np.asarray(list(groups.names), dtype=str)
        arrays["group_masks"] = np.asarray(groups.masks, dtype=bool)
        # The expression each group was built from ("NeuN+ & ~GAD+"). Not needed
        # to redraw anything, but it is how a reader knows what a group *means*
        # — and the spreadsheet it came from won't travel with the bundle.
        arrays["group_definitions"] = np.asarray(
            [str(groups.definitions.get(n, "")) for n in groups.names], dtype=str)

    for key, value in (state.lag_independent or {}).items():
        if value is not None:
            arrays[f"{_LAGINDEP_PREFIX}{key}"] = np.asarray(value)

    none_keys: list[str] = []
    for key, value in stats.items():
        if value is None:
            none_keys.append(key)
        else:
            arrays[f"{_STAT_PREFIX}{key}"] = np.asarray(value)
    # dtype=str keeps this a plain unicode array, so loading never needs
    # allow_pickle (which we don't want enabled on files a user may be
    # pointing at from an arbitrary prior-analysis folder).
    arrays["stat_none"] = np.asarray(none_keys, dtype=str)

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_savez(path, **arrays)


def load_recording_state(path: Path, plane0: Path) -> tuple[RecordingState, dict]:
    """Read back what :func:`save_recording_state` wrote.

    Returns ``(state, stats)``. ``plane0`` is supplied by the caller rather than
    stored, so a resumed run looks for the suite2p folder under the *current*
    ``Params.rawData`` — the prior run's raw data may not even be mounted, and
    the figures that want it already degrade gracefully when it isn't.

    ``groups`` / ``markers`` are left unset; the caller re-reads them from the
    cell-type spreadsheet.
    """
    with np.load(path) as data:
        keys = set(data.files)
        # Older files are readable: every bump so far has *added* optional keys
        # (markers in 2, groups in 3), and the reads below already treat those
        # as optional. Refusing them would be actively wrong for a shared
        # bundle — the recipient has no raw data, so "re-run from step 1" is
        # advice they cannot take. Only a file from the future is refused,
        # because its keys may mean something different.
        fmt = int(data["catnap_format"]) if "catnap_format" in keys else 0
        if fmt > FORMAT_VERSION:
            raise ValueError(
                f"{path.name} is a CAT-NAP step-2 file in format {fmt}; this "
                f"version reads up to format {FORMAT_VERSION}. Update MEA-NAP "
                "to open it."
            )
        if fmt < 1:
            raise ValueError(
                f"{path.name} does not look like a CAT-NAP step-2 file "
                "(no format marker)."
            )

        adjMs = {k[len(_ADJ_PREFIX):]: data[k]
                 for k in data.files if k.startswith(_ADJ_PREFIX)}

        stats: dict = {}
        for k in data.files:
            if not k.startswith(_STAT_PREFIX):
                continue
            value = data[k]
            stats[k[len(_STAT_PREFIX):]] = value.item() if value.ndim == 0 else value
        for name in data["stat_none"]:
            stats[str(name)] = None

        lag_independent: dict = {}
        for k in data.files:
            if not k.startswith(_LAGINDEP_PREFIX):
                continue
            value = data[k]
            lag_independent[k[len(_LAGINDEP_PREFIX):]] = (
                value.item() if value.ndim == 0 else value)

        markers = None
        if "marker_matrix" in keys:
            markers = (data["marker_matrix"], [str(n) for n in data["marker_names"]])

        groups = None
        if "group_names" in keys:
            from meanap.catnap.subnetwork import CellTypeGroups

            marker_matrix, marker_names = (
                markers if markers is not None
                else (np.zeros((len(data["channels"]), 0)), []))
            names = [str(n) for n in data["group_names"]]
            definitions = {}
            if "group_definitions" in keys:
                definitions = {n: str(d) for n, d in
                               zip(names, data["group_definitions"]) if str(d)}
            groups = CellTypeGroups(
                names=names,
                masks=np.asarray(data["group_masks"], dtype=bool),
                marker_names=list(marker_names),
                marker_matrix=np.asarray(marker_matrix),
                definitions=definitions,
            )

        state = RecordingState(
            adjMs=adjMs,
            coords=data["coords"],
            channels=data["channels"],
            spike_counts=data["spike_counts"],
            duration_s=float(data["duration_s"]),
            fs=float(data["fs"]) if "fs" in keys else 0.0,
            plane0=plane0,
            groups=groups,
            markers=markers,
            coord_norm=tuple(float(v) for v in data["coord_norm"]),
            lag_independent=lag_independent,
        )

    return state, stats


#: Longest edge kept for the stored mean projection. One figure displays it, a
#: few inches wide at 150 dpi — under 1000 px on screen — so anything beyond
#: this is bytes nobody can see. suite2p projections are routinely 1280² or
#: larger, where the full-precision array is 6.5 MB against ~350 KB here.
MAX_BACKGROUND_PX = 1024


def quantize_background(background: tuple | None) -> tuple | None:
    """Reduce a mean projection to what actually gets stored and drawn.

    Decimates to :data:`MAX_BACKGROUND_PX` and rounds to 256 grey levels. The
    pipeline runs its backdrop through this *before* plotting, so the figure it
    draws and the figure a viewer redraws from the bundle come from a
    bit-identical array — a lossy backdrop that differed between the two would
    make the reconstruction impossible to verify.
    """
    if background is None:
        return None
    image, extent = background
    img = np.asarray(image, dtype=float)
    if img.ndim != 2 or img.size == 0:
        return None

    step = max(1, -(-max(img.shape) // MAX_BACKGROUND_PX))  # ceil division
    img = img[::step, ::step]

    lo, hi = float(np.nanmin(img)), float(np.nanmax(img))
    span = hi - lo
    if not np.isfinite(span) or span <= 0:
        return np.zeros_like(img), extent
    levels = np.round((img - lo) / span * 255.0)
    return lo + levels / 255.0 * span, extent


def save_background(path: Path, background: tuple | None) -> None:
    """Store a recording's mean-projection backdrop and its coordinate extent.

    Kept out of the state file because it is produced in a later phase (the
    image is only read when the plotting phase re-opens the suite2p folder) and
    because it is optional — one figure depends on it.

    Expects an already-:func:`quantize_background`-ed image; the 256 levels are
    stored as ``uint8`` plus the range needed to restore them exactly.
    """
    if background is None:
        return
    image, extent = background
    img = np.asarray(image, dtype=float)
    lo, hi = float(np.nanmin(img)), float(np.nanmax(img))
    span = hi - lo
    levels = (np.round((img - lo) / span * 255.0).astype(np.uint8) if span > 0
              else np.zeros(img.shape, dtype=np.uint8))

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_savez(
        path, compressed=True,
        levels=levels, value_range=np.array([lo, hi], dtype=float),
        extent=np.asarray(extent, dtype=float),
    )


def load_background(path: Path) -> tuple | None:
    """Read back what :func:`save_background` wrote, or ``None`` if absent.

    Restores the exact float array the pipeline plotted, because the pipeline
    quantized before plotting (see :func:`quantize_background`).
    """
    if not path.exists():
        return None
    with np.load(path) as data:
        lo, hi = (float(v) for v in data["value_range"])
        span = hi - lo
        levels = np.asarray(data["levels"], dtype=float)
        image = lo + levels / 255.0 * span if span > 0 else levels
        return image, tuple(float(v) for v in data["extent"])
