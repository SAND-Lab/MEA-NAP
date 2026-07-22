"""Axion-event-driven stimulation times (partial port of ``axionStimEventsTool.m``).

For the ``axionStimEvents`` detection method, stimulation times come from the
Axion `.raw` file's ``StimulationEvents`` (selected via a CSV that maps
``rawName, well, electrode`` rows to recordings), **not** from the voltage trace.

**Scope**: the CSV→electrode assembly (`build_stim_info_from_events`) is ported
here and produces the same ``StimChannelInfo`` shape that ``detectStimTimes``
yields, so the rest of the stim pipeline consumes it unchanged. The part that
reads ``StimulationEvents`` out of the Axion binary `.raw` (MATLAB's ``AxisFile``
class) is **not** ported — it needs an Axion file-format reader, and the bundled
test data uses ``longblank`` rather than this path, so there is no parity fixture
to validate a `.raw` reader against. Supply event times from your own Axion
reader (e.g. a future port of ``AxionFileLoader``) and this module assembles them.
"""

from __future__ import annotations

import numpy as np

from .detection import StimChannelInfo


def build_stim_info_from_events(
    event_times_by_channel: dict[int, np.ndarray],
    channel_names: np.ndarray,
    coords: np.ndarray,
    params: dict,
) -> list[StimChannelInfo]:
    """Assemble per-channel ``StimChannelInfo`` from Axion stimulation-event times.

    Port of ``axionStimEventsTool``'s ``buildStimInfo``: each electrode's
    stimulation times become its ``elec_stim_times``; blank starts/ends mirror
    the stim times with zero blank duration, and non-stim blanks are empty (so
    ``blankDurMode`` = 0, ``artifactDuration`` = ``postStimWindowDur/1000``).

    Parameters
    ----------
    event_times_by_channel : ``{channel_index: event_times_s}`` — from an Axion
        reader (out of scope here; see module docstring).
    channel_names, coords : as for :func:`detection.detect_stim_times`.
    params : needs ``stimDuration``.
    """
    stim_dur = float(params["stimDuration"])
    n_channels = len(channel_names)
    stim_info: list[StimChannelInfo] = []
    for c in range(n_channels):
        times = np.asarray(event_times_by_channel.get(c, []), dtype=float).ravel()
        times = np.sort(times)
        stim_info.append(StimChannelInfo(
            elec_stim_times=times,
            elec_stim_dur=np.full(times.shape[0], stim_dur),
            channel_name=int(channel_names[c]),
            coords=np.asarray(coords[c], dtype=float),
            blank_starts=times.copy(),
            blank_ends=times.copy(),                       # zero-duration blanks
            non_stim_blank_starts=np.array([]),
            non_stim_blank_ends=np.array([]),
            blank_durations=np.zeros(times.shape[0]),
        ))
    return stim_info


def read_axion_stim_csv(csv_path):
    """Parse the stim-event CSV (``rawName, well, electrode`` rows).

    Returns a list of ``(raw_name, well, electrode)`` tuples. Matching a row to a
    recording (``<rawName>_<well>``) and pulling event times from the `.raw`
    binary is left to the caller + an Axion reader (see module docstring).
    """
    import csv
    rows = []
    with open(csv_path, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        for r in reader:
            if len(r) >= 3:
                rows.append((r[0].strip(), r[1].strip(), r[2].strip()))
    return rows
