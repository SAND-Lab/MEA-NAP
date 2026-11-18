"""Electrode channel-ID -> spatial coordinate lookup, port of
``getCoordsFromLayout.m``.

MEA-NAP doesn't compute coordinates from the recording itself — they come
from a fixed lookup table keyed by ``Params.channelLayout`` (the MEA
hardware type, e.g. ``'Axion64'`` or ``'MCS60'``). Needed for any spatial
network plot.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

# Row-major 8x8 grid channel IDs, e.g. 11, 12, ..., 18, 21, ..., 88 —
# matches the literal channel lists in getCoordsFromLayout.m's MCS branches.
_MCS_GRID_CHANNELS = [row * 10 + col for row in range(1, 9) for col in range(1, 9)]

_MCS_CORNER_CHANNELS = {11, 81, 18, 88}

# channelsOrdering arrays, transcribed verbatim from getCoordsFromLayout.m
_MCS60OLD_ORDERING = [
    21, 31, 41, 51, 61, 71, 12, 22, 32, 42, 52, 62, 72, 82, 13, 23, 33, 43, 53, 63,
    73, 83, 14, 24, 34, 44, 54, 64, 74, 84, 15, 25, 35, 45, 55, 65, 75, 85, 16, 26,
    36, 46, 56, 66, 76, 86, 17, 27, 37, 47, 57, 67, 77, 87, 28, 38, 48, 58, 68, 78,
]

_MCS60_ORDERING = [
    47, 48, 46, 45, 38, 37, 28, 36, 27, 17, 26, 16, 35, 25,
    15, 14, 24, 34, 13, 23, 12, 22, 33, 21, 32, 31, 44, 43, 41, 42,
    52, 51, 53, 54, 61, 62, 71, 63, 72, 82, 73, 83, 64, 74, 84, 85, 75,
    65, 86, 76, 87, 77, 66, 78, 67, 68, 55, 56, 58, 57,
]

# MCS59 uses the same base ordering as MCS60, then additionally drops
# channel 82 (the grounded electrode on that MEA variant).
_MCS59_ORDERING = _MCS60_ORDERING
_MCS59_EXCLUDE_CHANNEL = 82


def _mcs_grid_coords() -> np.ndarray:
    """(64, 2) coords for the row-major 8x8 grid, before corner removal."""
    y = np.tile(np.linspace(1, 0, 8), 8)
    x = np.repeat(np.linspace(0, 1, 8), 8)
    return np.column_stack([x, y])


def _mcs_layout(ordering: list[int], exclude_channel: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    grid_channels = np.array(_MCS_GRID_CHANNELS)
    grid_coords = _mcs_grid_coords()

    keep = np.array([c not in _MCS_CORNER_CHANNELS for c in grid_channels])
    coord_by_channel = {
        int(c): tuple(xy) for c, xy in zip(grid_channels[keep], grid_coords[keep])
    }

    channels = np.array(ordering)
    if exclude_channel is not None:
        channels = channels[channels != exclude_channel]
    coords = np.array([coord_by_channel[int(c)] for c in channels])
    return channels, coords * 8


def _axion_layout(grid_size: int) -> tuple[np.ndarray, np.ndarray]:
    spacing = np.linspace(0, 1, grid_size)
    channels = []
    coords = []
    for row in range(1, grid_size + 1):
        for col in range(1, grid_size + 1):
            channels.append(col * 10 + row)
            coords.append((spacing[col - 1], spacing[row - 1]))
    return np.array(channels), np.array(coords) * 8


def get_coords_from_layout(channel_layout: str) -> tuple[np.ndarray, np.ndarray]:
    """Returns (channels, coords) for a known MEA channel layout name.

    ``coords`` is ``(len(channels), 2)``, scaled to roughly ``[0, 8]`` (matches
    MATLAB's final ``coords = coords * 8``). Callers should look up
    coordinates by channel ID (``dict(zip(channels, coords))``) rather than
    relying on array order/length matching a recording's own channel list —
    MCS layouts drop grounded corner electrodes, so their returned
    ``channels`` is shorter than a full-grid recording's channel array.
    """
    if channel_layout == "MCS60old":
        return _mcs_layout(_MCS60OLD_ORDERING)
    if channel_layout == "MCS60":
        return _mcs_layout(_MCS60_ORDERING)
    if channel_layout == "MCS59":
        return _mcs_layout(_MCS59_ORDERING, exclude_channel=_MCS59_EXCLUDE_CHANNEL)
    if channel_layout == "Axion64":
        return _axion_layout(8)
    if channel_layout == "Axion16":
        return _axion_layout(4)
    if isinstance(channel_layout, str) and channel_layout.startswith(_CUSTOM_PREFIX):
        channels, coords_um = _parse_custom(channel_layout)
        return channels.copy(), _custom_drawing_coords(coords_um)
    if channel_layout == CUSTOM_LAYOUT:
        raise ValueError(
            "The channel layout is Custom, but no layout file has been read: choose "
            "one under Channel layout on the Data tab (a CSV of channel, x, y).")
    raise ValueError(
        f"Unsupported channel layout: {channel_layout!r} "
        "(supported: MCS60, Axion64, Axion16, Custom, FromFile)"
    )


# ── Custom layouts ────────────────────────────────────────────────────────────
#
# MATLAB's 'Custom' layout is a stub to edit in getCoordsFromLayout.m. Here it
# is a table — one row per electrode: channel ID, x and y in micrometres, as
# the array's drawing gives them — that a person loads from a CSV and that is
# saved with the run's settings (Params.custom_layout), so a run, its worker
# processes and its bundle opened on another computer all have it.
#
# Everything that places electrodes takes a layout *name*. So that all of it
# works on a custom layout unchanged, :func:`layout_of` writes the table into
# the name itself — ``"Custom:11:0,0;12:200,0;…"`` — which survives pickling
# into workers and being saved in a spike file as any name does.

#: ``Params.channel_layout`` for a layout read from a file.
CUSTOM_LAYOUT = "Custom"
_CUSTOM_PREFIX = "Custom:"


def encode_custom_layout(rows) -> str:
    """The layout name that carries *rows* (``[channel, x_um, y_um]``)."""
    parts = [f"{int(ch)}:{float(x):g},{float(y):g}" for ch, x, y in rows]
    return _CUSTOM_PREFIX + ";".join(parts)


@lru_cache(maxsize=16)
def _parse_custom(name: str) -> tuple[np.ndarray, np.ndarray]:
    """``(channels, coords_um)`` from an encoded custom layout name."""
    channels, coords = [], []
    for part in name[len(_CUSTOM_PREFIX):].split(";"):
        ch, xy = part.split(":")
        x, y = xy.split(",")
        channels.append(int(ch))
        coords.append((float(x), float(y)))
    return np.array(channels, dtype=np.int64), np.array(coords, dtype=float)


def _custom_drawing_coords(coords_um: np.ndarray) -> np.ndarray:
    """Micrometres → the drawing units every layout uses: the array's longer
    side spans [0, 8], and y counts *up* (the file's y counts down from the
    top, as the rows of an array's drawing do)."""
    xy = np.asarray(coords_um, dtype=float).copy()
    xy[:, 1] = -xy[:, 1]
    xy -= xy.min(axis=0)
    extent = float(xy.max()) if xy.size else 0.0
    return xy * (8.0 / extent) if extent > 0 else xy


def custom_pitch_um(layout: str) -> float:
    """The median distance from each electrode to its nearest, in µm."""
    from scipy.spatial.distance import cdist

    _, xy = _parse_custom(layout)
    if len(xy) < 2:
        raise ValueError("A custom layout with one electrode has no pitch")
    d = cdist(xy, xy)
    np.fill_diagonal(d, np.inf)
    return float(np.median(d.min(axis=1)))


def is_custom_layout(layout) -> bool:
    return isinstance(layout, str) and (layout == CUSTOM_LAYOUT
                                        or layout.startswith(_CUSTOM_PREFIX))


def layout_of(params) -> str:
    """The layout to place a run's electrodes with: ``params.channel_layout``,
    or, for a custom one, the name that carries its table."""
    layout = getattr(params, "channel_layout", "")
    if layout == CUSTOM_LAYOUT and getattr(params, "custom_layout", None):
        return encode_custom_layout(params.custom_layout)
    return layout


def layout_label(layout: str) -> str:
    """A layout as a log line names it: a custom one by its size, not its table."""
    if isinstance(layout, str) and layout.startswith(_CUSTOM_PREFIX):
        return f"Custom ({len(_parse_custom(layout)[0])} electrodes)"
    return str(layout)


def read_layout_file(path: str | Path) -> list[list[float]]:
    """``[channel, x_um, y_um]`` rows from a layout CSV (or .xlsx).

    Columns are found by name — ``channel`` (or ``electrode``/``id``), ``x``
    and ``y``, any case — or else taken as the first three. Raises a
    ``ValueError`` that says what is wrong: a missing column, a value that is
    not a number, a channel listed twice, two electrodes in one place.
    """
    import pandas as pd

    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        table = pd.read_excel(path)
    else:
        table = pd.read_csv(path)
    table = table.dropna(how="all")
    names = {str(c).strip().lower(): c for c in table.columns}

    def column(options, position):
        for option in options:
            if option in names:
                return table[names[option]]
        if table.shape[1] <= position:
            raise ValueError(f"{path.name} needs three columns: channel, x and y")
        return table.iloc[:, position]

    columns = [column(("channel", "channels", "electrode", "channel id", "id"), 0),
               column(("x", "x (um)", "x_um", "x (µm)"), 1),
               column(("y", "y (um)", "y_um", "y (µm)"), 2)]
    numbers = [pd.to_numeric(c, errors="coerce") for c in columns]
    bad = numbers[0].isna() | numbers[1].isna() | numbers[2].isna()
    if bad.any():
        row = int(np.flatnonzero(bad.to_numpy())[0]) + 2
        raise ValueError(f"{path.name}, row {row}: channel, x and y must all be numbers")
    channels = numbers[0].to_numpy()
    if np.any(channels != np.round(channels)):
        raise ValueError(f"{path.name}: channel IDs must be whole numbers")
    if len(channels) < 2:
        raise ValueError(f"{path.name} lists fewer than two electrodes")
    unique, counts = np.unique(channels.astype(np.int64), return_counts=True)
    if (counts > 1).any():
        raise ValueError(f"{path.name} lists channel {int(unique[counts > 1][0])} "
                         f"more than once")
    xy = np.column_stack([numbers[1].to_numpy(), numbers[2].to_numpy()])
    if len(np.unique(xy, axis=0)) < len(xy):
        raise ValueError(f"{path.name} puts two electrodes in the same place")
    return [[int(c), float(x), float(y)] for c, (x, y) in zip(channels, xy)]


#: The layout of an array with no fixed one — a MaxWell HD-MEA routes its own
#: electrodes per recording — read from each recording's spike file, where an
#: import writes its electrode table (``electrode_ids`` / ``electrode_coords``).
FROM_FILE_LAYOUT = "FromFile"


def recording_layout(channel_layout: str, spike_data=None
                     ) -> tuple[np.ndarray, np.ndarray] | None:
    """``(channels, coords)`` for one recording when its layout is its own.

    Returns ``None`` for the fixed layouts, so callers keep using
    :func:`get_coords_from_layout` and their output is unchanged. For
    :data:`FROM_FILE_LAYOUT`, *spike_data* is the recording's ``_spikes.npz``
    (an open ``NpzFile``, or anything with ``.files`` and item access).
    """
    if channel_layout != FROM_FILE_LAYOUT:
        return None
    files = getattr(spike_data, "files", ())
    if "electrode_ids" not in files or "electrode_coords" not in files:
        raise ValueError(
            f"channel_layout {FROM_FILE_LAYOUT!r} needs the electrode table a "
            "spike-sorted import writes, and this spike file has none")
    return (np.asarray(spike_data["electrode_ids"]).astype(np.int64),
            np.asarray(spike_data["electrode_coords"], dtype=float))


def node_distances_in_pitches(
    channel_layout: str,
    channels: np.ndarray,
    spike_data=None,
    node_coords: np.ndarray | None = None,
) -> np.ndarray:
    """Pairwise distances between a recording's nodes, in electrode pitches.

    The coordinates every layout returns are drawing units (an 8×8 grid spans
    ``[0, 8]``, a 4×4 one too), so a length measured in them means nothing
    across layouts. Dividing by the layout's own electrode pitch — the median
    distance from each electrode to its nearest neighbour — makes it one. That
    is exact for the fixed grids and holds for a MaxWell routing too, whose
    electrodes sit on a regular sub-grid.

    *node_coords* overrides the per-channel lookup (a sorted run's units sit on
    rings round their electrode, one row per node, already in layout units).
    Otherwise *channels* are looked up in the layout by ID; a channel the layout
    does not have (a grounded MCS corner) gets NaN distances, which callers drop.
    """
    from scipy.spatial.distance import cdist

    own = recording_layout(channel_layout, spike_data)
    layout_channels, layout_coords = own if own is not None else get_coords_from_layout(channel_layout)
    layout_coords = np.asarray(layout_coords, dtype=float)
    ok = np.all(np.isfinite(layout_coords), axis=1)
    elec = layout_coords[ok]
    d = cdist(elec, elec)
    np.fill_diagonal(d, np.inf)
    nn = d.min(axis=1)
    pitch = float(np.median(nn[np.isfinite(nn) & (nn > 0)]))

    if node_coords is not None:
        xy = np.asarray(node_coords, dtype=float)
    else:
        by_id = dict(zip(np.asarray(layout_channels).tolist(), map(tuple, layout_coords)))
        xy = np.array([by_id.get(int(c), (np.nan, np.nan))
                       for c in np.asarray(channels).ravel()], dtype=float)
    return cdist(xy, xy) / pitch


def fixed_electrode_count(params) -> int | None:
    """Electrodes on the array, when every node of the run is one of a fixed set.

    That is a detected-spikes MEA run on a built-in layout: nodes are
    electrodes, so no network can have more nodes than the layout has. ``None``
    otherwise — a spike-sorted or imported run (nodes are units, several to an
    electrode), CAT-NAP (cells), or a layout read from each file.
    """
    if getattr(params, "suite2p_mode", False) or getattr(params, "spike_source", "detect") != "detect":
        return None
    try:
        channels, _ = get_coords_from_layout(layout_of(params))
    except ValueError:
        return None
    return len(channels)
