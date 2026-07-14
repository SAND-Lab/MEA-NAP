"""Electrode channel-ID -> spatial coordinate lookup, port of
``getCoordsFromLayout.m``.

MEA-NAP doesn't compute coordinates from the recording itself — they come
from a fixed lookup table keyed by ``Params.channelLayout`` (the MEA
hardware type, e.g. ``'Axion64'`` or ``'MCS60'``). Needed for any spatial
network plot.
"""

from __future__ import annotations

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
    raise ValueError(
        f"Unsupported channel layout: {channel_layout!r} "
        "(supported: MCS60old, MCS60, MCS59, Axion64, Axion16; "
        "MATLAB's 'Custom' layout uses random coordinates and isn't ported)"
    )
