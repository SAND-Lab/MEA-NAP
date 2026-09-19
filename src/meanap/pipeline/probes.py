"""Electrode geometry for spike sorting: a ``probeinterface.Probe`` per
MEA channel layout.

Spike sorters need every channel's position in micrometres — to decide which
channels a spike can appear on together, and to whiten over neighbours. The
pipeline's own coordinates (:mod:`meanap.pipeline.channel_layout`) are a
unit-less grid scaled to ``[0, 8]`` for plotting, so this module is the one
place that turns them into physical distance. On the low-density arrays
MEA-NAP supports (200–350 µm pitch) a spike is seen on one electrode only,
so the absolute pitch matters little to the sorters; what matters is that
every neighbour is *further* than the sorters' detection and whitening radii,
which the presets in :mod:`meanap.pipeline.spike_sorting` are chosen against.
"""

from __future__ import annotations

import numpy as np

from meanap.pipeline.channel_layout import get_coords_from_layout

#: Centre-to-centre electrode spacing of each supported layout, in µm.
#: MCS 60MEA200/30: 200 µm. Axion CytoView 48/12-well plates: 350 µm.
DEFAULT_PITCH_UM: dict[str, float] = {
    "MCS60": 200.0,
    "MCS60old": 200.0,
    "MCS59": 200.0,
    "Axion64": 350.0,
    "Axion16": 350.0,
}

#: Electrode contact radius drawn on the probe, in µm — MCS 30 µm diameter
#: electrodes. Cosmetic: no sorter used here reads it.
_CONTACT_RADIUS_UM = 15.0


def layout_grid_step(channel_layout: str) -> float:
    """Distance between adjacent electrodes in *layout units*.

    Both MCS and Axion layouts space their grid with ``linspace(0, 1, n) * 8``,
    so one electrode step is ``8 / (n - 1)`` rather than 1. Derived from the
    coordinates rather than assumed, so a new layout with a different scale
    still converts correctly.
    """
    _, coords = get_coords_from_layout(channel_layout)
    xs = np.unique(np.round(coords[:, 0], 6))
    return float(np.min(np.diff(xs))) if len(xs) > 1 else 1.0


def electrode_pitch_um(channel_layout: str, override: float | None = None) -> float:
    """The pitch to use for *channel_layout*: the user's value if given."""
    if override is not None and override > 0:
        return float(override)
    try:
        return DEFAULT_PITCH_UM[channel_layout]
    except KeyError:
        raise ValueError(
            f"No default electrode pitch for layout {channel_layout!r}; "
            "set the pitch explicitly to sort spikes on it.") from None


def layout_coords_for_channels(
    channel_layout: str, channels: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Layout coordinates for a recording's channel list.

    Returns ``(coords, known)``: ``coords`` is ``(n_channels, 2)`` in layout
    units, ``known`` marks channels the layout places. A channel the layout
    does not know (a grounded corner electrode on a full-grid file) gets NaN
    coordinates, and it is the caller's business whether to drop it.
    """
    layout_channels, layout_coords = get_coords_from_layout(channel_layout)
    lookup = {int(c): xy for c, xy in zip(layout_channels, layout_coords)}
    coords = np.full((len(channels), 2), np.nan)
    known = np.zeros(len(channels), dtype=bool)
    for i, ch in enumerate(np.asarray(channels).ravel()):
        xy = lookup.get(int(ch))
        if xy is not None:
            coords[i] = xy
            known[i] = True
    return coords, known


def build_probe(
    channel_layout: str,
    channels: np.ndarray,
    pitch_um: float | None = None,
):
    """A ``probeinterface.Probe`` for the channels of one recording.

    Returns ``(probe, kept)`` where ``kept`` is the 0-based index of every
    channel the probe carries, in probe order. Channels the layout cannot
    place are left off the probe rather than given a made-up position: a
    sorter would otherwise treat them as real electrodes somewhere.

    Positions are the layout grid scaled so one electrode step is
    :func:`electrode_pitch_um`, with y flipped to match the layout's
    top-row-first convention (``probeinterface`` draws y upwards, the layout
    puts row 1 at the top; flipping keeps the probe picture matching the MEA
    heatmaps).
    """
    from probeinterface import Probe

    coords, known = layout_coords_for_channels(channel_layout, channels)
    kept = np.flatnonzero(known)
    if len(kept) == 0:
        raise ValueError(
            f"None of the recording's channels are in layout {channel_layout!r}")

    step = layout_grid_step(channel_layout)
    pitch = electrode_pitch_um(channel_layout, pitch_um)
    positions = coords[kept] / step * pitch
    positions[:, 1] = -positions[:, 1]

    probe = Probe(ndim=2, si_units="um")
    probe.set_contacts(positions=positions, shapes="circle",
                       shape_params={"radius": _CONTACT_RADIUS_UM})
    probe.set_contact_ids([str(int(channels[i])) for i in kept])
    # Device channel index is the column of the traces array the contact
    # reads: the sub-recording handed to the sorter has only the kept
    # channels, in this order, so it is 0..n-1 here.
    probe.set_device_channel_indices(np.arange(len(kept)))
    return probe, kept
