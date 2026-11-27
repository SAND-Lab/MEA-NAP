"""Axion stimulation from the ``.raw`` file (port of ``axionStimEventsTool.m``).

For the ``axionStimEvents`` detection method, stimulation times *and* the
stimulated electrodes come from the ``StimulationEvents`` AxIS records in the
plate's ``.raw`` (read by :func:`meanap.pipeline.axion_raw.read_axion_stim_events`),
not from the voltage trace. Each event names the well(s) and electrode(s) it
was delivered to, so no CSV is needed.

A recording named ``<file>_<well>`` (``Plate1_DIV14_A1``, the name Axion file
conversion gives each well) comes from ``<file>.raw``, looked for in the raw
data folder. Every electrode of that well that an event names becomes a
stimulating electrode with the times of its events; electrodes driven by the
same waveform block share their times, so :func:`get_stim_patterns` groups them
into one pattern.

Files whose events name no electrode (LED stimulation, missing channel tags)
can't be assigned to electrodes; :class:`WellStimulation` then carries the
event times for the caller to analyse the way the event-driven methods do
(no stimulating electrode).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

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
    event_times_by_channel : ``{channel_index: event_times_s}``.
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


# ── Per-well stimulation ──────────────────────────────────────────────────────

#: What a well's events amount to.
ELECTRODES = "electrodes"        # events name electrodes in this well
NO_ELECTRODE = "no_electrode"    # the file's events name no electrode at all
NONE = "none"                    # no event reaches this well


@dataclass
class WellStimulation:
    """A recording's (one well's) stimulation, from its plate's ``.raw``."""

    recording: str
    raw: Path
    well: str
    kind: str
    #: Electrode ID (``column * 10 + row``) → its stimulation times (s), for
    #: :data:`ELECTRODES`.
    times_by_electrode: dict[int, np.ndarray] = field(default_factory=dict)
    #: Event times for :data:`NO_ELECTRODE`: the events lighting this well when
    #: they say which wells they lit (LED), otherwise every event in the file.
    event_times: np.ndarray = field(default_factory=lambda: np.zeros(0))
    #: One line for the log saying what was found.
    summary: str = ""


def find_axion_raw(folders, recording: str) -> tuple[Path, str] | None:
    """``(<file>.raw, well)`` for a recording named ``<file>_<well>``.

    The first folder holding ``<file>.raw`` wins (the name compared without
    regard to case, as MATLAB does). ``None`` when the name has no well
    suffix or no folder holds the file.
    """
    from meanap.pipeline.axion_raw import split_well_suffix

    split = split_well_suffix(recording)
    if split is None:
        return None
    stem, well = split
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        # The name as it is on disk, so one file is always the same path (a
        # case-insensitive disk would otherwise answer to any spelling).
        matches = [c for c in folder.iterdir()
                   if c.suffix.lower() == ".raw" and c.stem.lower() == stem.lower()
                   and c.is_file()]
        if matches:
            exact = [c for c in matches if c.stem == stem]
            return (exact or sorted(matches))[0], well
    return None


@functools.lru_cache(maxsize=8)
def _read_events(raw: Path, mtime_ns: int, size: int):
    """A plate's events, read once while the file is unchanged: step 1 asks
    for every well of a plate in turn, each through its own source."""
    from meanap.pipeline import axion_raw

    return axion_raw.read_axion_stim_events(raw)


class AxionStimSource:
    """Reads each plate's stimulation events once per run, for every well of it.

    File-level warnings (unlinked events, events naming no electrode) are
    logged once per file, when it is first read.
    """

    def __init__(self, folders, log=print):
        self.folders = [Path(f) for f in dict.fromkeys(str(f) for f in folders if f)]
        self.log = log
        self._events: dict[Path, object] = {}

    def events(self, raw: Path):
        raw = Path(raw)
        if raw not in self._events:
            st = raw.stat()
            ev = _read_events(raw, st.st_mtime_ns, st.st_size)
            self._events[raw] = ev
            self._warn_once(ev)
        return self._events[raw]

    def _warn_once(self, ev) -> None:
        name = ev.path.name
        total = len(ev.events) + ev.n_unlinked
        if ev.n_unlinked:
            self.log(f"  ! {name}: {ev.n_unlinked} of {total} stimulation event(s) lack the "
                     "tags that say where they were delivered (unlinked)")
        unlabelled = sum(1 for e in ev.events if not e.electrodes)
        if ev.names_electrodes() and (unlabelled or ev.n_unlinked):
            self.log(f"  ! {name}: {unlabelled + ev.n_unlinked} of {total} stimulation "
                     "event(s) do not record their electrode and are not assigned to any well")

    def for_recording(self, recording: str) -> WellStimulation | None:
        """The stimulation of one recording, or ``None`` (logged) when its
        ``.raw`` can't be found or its name says no well."""
        from meanap.pipeline.axion_raw import split_well_suffix

        if split_well_suffix(recording) is None:
            self.log(f"  ! [{recording}] axionStimEvents needs the recording name to end in "
                     "_<well> (for example _A1), as Axion file conversion names them. Skipping.")
            return None
        found = find_axion_raw(self.folders, recording)
        if found is None:
            stem = split_well_suffix(recording)[0]
            where = ", ".join(map(str, self.folders)) or "no folder set"
            self.log(f"  ! [{recording}] {stem}.raw not found in {where}; axionStimEvents reads "
                     "the stimulation from the .raw, so keep it in the raw data folder. Skipping.")
            return None
        raw, well = found
        return well_stimulation(self.events(raw), recording, well)


def well_stimulation(ev, recording: str, well: str) -> WellStimulation:
    """What the events of a plate (an :class:`~meanap.pipeline.axion_raw.AxionStimEvents`)
    say about one of its wells."""
    raw, well = Path(ev.path), well.upper()
    if not ev.events and not ev.n_unlinked:
        return WellStimulation(recording, raw, well, NONE,
                               summary=f"{raw.name} has no stimulation events; {well}: "
                                       "no stimulation")

    if not ev.names_electrodes():
        lit = [e.time_s for e in ev.events if well in e.led_wells]
        say_wells = any(e.led_wells for e in ev.events)
        if say_wells:
            times = np.array(sorted(lit), dtype=float)
            how = f"{len(times)} lighting {well}" if len(times) else f"none lighting {well}"
        else:
            times = np.array(sorted([e.time_s for e in ev.events] + list(ev.unlinked_times)),
                             dtype=float)
            how = "which wells they reached is not recorded"
        kind = NO_ELECTRODE if len(times) else NONE
        return WellStimulation(
            recording, raw, well, kind, event_times=times,
            summary=(f"{raw.name}: {len(ev.events) + ev.n_unlinked} stimulation event(s), none "
                     f"recording an electrode (LED stimulation or missing channel tags); {how}"))

    times: dict[int, set[float]] = {}
    for e in ev.events:
        for w, electrode in e.electrodes:
            if w == well:
                times.setdefault(electrode, set()).add(e.time_s)
    if not times:
        return WellStimulation(recording, raw, well, NONE,
                               summary=f"{well}: no stimulation (stimulated wells in {raw.name}: "
                                       f"{', '.join(ev.stimulated_wells())})")
    by_electrode = {k: np.array(sorted(v), dtype=float) for k, v in sorted(times.items())}
    counts = ", ".join(f"{k} ({len(v)})" for k, v in by_electrode.items())
    return WellStimulation(recording, raw, well, ELECTRODES, times_by_electrode=by_electrode,
                           summary=f"{well}: stimulated electrode(s) {counts} from {raw.name}")


def stim_info_for_well(ws: WellStimulation, channel_names: np.ndarray, coords: np.ndarray,
                       params: dict, log=print) -> list[StimChannelInfo]:
    """``StimChannelInfo`` per channel of the recording, from its well's events.

    A stimulated electrode the recording has no channel for is reported and
    left out. Every channel gets no stimulation for a well of kind
    :data:`NONE` (or :data:`NO_ELECTRODE`, which the caller handles apart).
    """
    names = [int(c) for c in np.asarray(channel_names).ravel()]
    by_index: dict[int, np.ndarray] = {}
    missing = []
    for electrode, times in ws.times_by_electrode.items():
        if electrode in names:
            by_index[names.index(electrode)] = times
        else:
            missing.append(electrode)
    if missing:
        log(f"  ! [{ws.recording}] electrode(s) {', '.join(map(str, missing))} of well {ws.well} "
            f"were stimulated according to {ws.raw.name} but are not channels of the "
            "recording; their stimulation times are ignored")
    return build_stim_info_from_events(by_index, channel_names, coords, params)
