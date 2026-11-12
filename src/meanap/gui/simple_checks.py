"""The checks behind the simple view's green ticks.

Each function looks at one input and says whether a run could use it, in words a
person can act on. They are kept free of Qt so they can be tested on their own,
and they only read the local disk: a Dropbox link is accepted as it is and
checked when the run starts, so typing one never waits on the network.

A check returns ``None`` while its input is empty (nothing to say yet), or a
:class:`Check` whose ``state`` is one of:

* ``"ok"``: usable as it is;
* ``"warn"``: usable, but something the person should know about;
* ``"error"``: the run would fail or analyse the wrong data, so the simple view
  does not move on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from meanap.params import is_remote_url

__all__ = [
    "Check", "check_output_folder", "check_recording_settings",
    "check_recordings_folder", "check_spreadsheet", "describe_rates",
    "recording_names",
]


@dataclass(frozen=True)
class Check:
    state: str
    #: One line, shown under the field while it is being filled in.
    message: str
    #: A few words, shown beside the field once it is done.
    summary: str = ""

    @property
    def complete(self) -> bool:
        """Whether the simple view can move past this input."""
        return self.state in ("ok", "warn")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def check_recordings_folder(path: str, mode: str) -> Check | None:
    """Whether *path* holds recordings the *mode* pipeline can read."""
    path = path.strip()
    if not path:
        return None
    if is_remote_url(path):
        return Check("ok", "Dropbox link. The recordings are listed when the run starts.",
                     "Dropbox link")
    folder = Path(path)
    if not folder.is_dir():
        return Check("error", "This folder doesn't exist.")

    if mode == "catnap":
        from meanap.catnap.scanner import find_suite2p_recordings

        n = len(find_suite2p_recordings(folder))
        if not n:
            return Check("error",
                         "No suite2p recordings found. Choose the folder that holds "
                         "one sub-folder per recording, each with suite2p/plane0 inside.")
        found = _plural(n, "suite2p recording")
        return Check("ok", f"{found} found", found)

    from meanap.pipeline.spreadsheet import raw_recording_names

    n = len(raw_recording_names(folder))
    if not n:
        return Check("error",
                     "No recordings found. MEA-NAP reads .mat, .h5 and .raw files "
                     "directly inside this folder.")
    found = _plural(n, "recording file")
    return Check("ok", f"{found} found", found)


def recording_names(folder: str, mode: str) -> list[str]:
    """The recordings in a local *folder*, by name; ``[]`` if it has none or is a link."""
    if not folder or is_remote_url(folder) or not Path(folder).is_dir():
        return []
    if mode == "catnap":
        from meanap.catnap.scanner import find_suite2p_recordings

        return sorted(r.name for r in find_suite2p_recordings(folder))
    from meanap.pipeline.spreadsheet import raw_recording_names

    return raw_recording_names(folder)


def _available_names(folder: str, mode: str):
    """A test for whether a spreadsheet name has a recording, or ``None`` if unknown."""
    if not folder or is_remote_url(folder) or not Path(folder).is_dir():
        return None
    if mode == "catnap":
        from meanap.catnap.scanner import find_suite2p_recordings

        names = {r.name for r in find_suite2p_recordings(folder)}
        return names.__contains__

    from meanap.pipeline.io import find_raw_file

    return lambda name: find_raw_file(folder, name) is not None


def check_spreadsheet(path: str, recordings_folder: str, mode: str,
                      spreadsheet_range: str = "A2:A100000") -> Check | None:
    """Whether the spreadsheet at *path* is readable and matches the recordings."""
    from meanap.pipeline.spreadsheet import (
        read_recording_names, read_recording_table, validate_recording_table,
    )

    path = path.strip()
    if not path:
        return None
    if not Path(path).is_file():
        return Check("error", "This file doesn't exist.")
    try:
        table = read_recording_table(path)
        names = read_recording_names(path, spreadsheet_range)
    except Exception as exc:  # any parse failure is the same problem to the user
        return Check("error", f"Couldn't read this file ({exc}).")
    if not names:
        return Check("error", "This spreadsheet doesn't list any recordings.")

    # A missing group only weakens the group comparisons; everything else
    # validate_recording_table reports makes the run fail or misread the data.
    problems = validate_recording_table(table)
    blocking = [p for p in problems if "genotype/group" not in p]
    if blocking:
        return Check("error", blocking[0])

    total = _plural(len(names), "recording")
    has_recording = _available_names(recordings_folder, mode)
    if has_recording is not None:
        missing = [n for n in names if not has_recording(n)]
        if len(missing) == len(names):
            return Check("error",
                         "None of these recordings are in the recordings folder. "
                         "Check the names match the files.")
        if missing:
            return Check("warn",
                         f"{len(missing)} of {total} aren't in the recordings folder "
                         f"and will be skipped (first: {missing[0]}).",
                         f"{len(names) - len(missing)} of {total} found")

    if problems:
        return Check("warn", problems[0], total)
    message = (f"{total}, all in the recordings folder" if has_recording is not None
               else total)
    return Check("ok", message, total)


def check_output_folder(path: str) -> Check | None:
    """Whether results can be written under *path*."""
    path = path.strip()
    if not path:
        return None
    folder = Path(path)
    if folder.is_dir():
        if not os.access(folder, os.W_OK):
            return Check("error", "You don't have permission to write to this folder.")
        return Check("ok", "Results will go in a new folder inside this one.",
                     folder.name or path)
    if folder.parent.is_dir():
        return Check("ok", "This folder will be created when the run starts.",
                     f"{folder.name} (new)")
    return Check("error", "Neither this folder nor the one containing it exists.")


def describe_rates(rates) -> str:
    """``12.5 kHz``, or ``10–25 kHz`` for a batch recorded at several rates."""
    def khz(hz: float) -> str:
        return f"{hz / 1000:g} kHz"
    distinct = sorted(set(rates))
    if not distinct:
        return ""
    if len(distinct) == 1:
        return khz(distinct[0])
    return f"{distinct[0] / 1000:g}–{khz(distinct[-1])}"


def check_recording_settings(guess, chosen_layout: str) -> Check | None:
    """The layout and sampling rate, as read from the recordings.

    *guess* is a :class:`~meanap.pipeline.recording_probe.LayoutGuess`, or
    None when the files couldn't be read (a share link, say). ``None`` back
    means "nothing to go on": the step asks instead.

    Recordings at different rates are fine, since each is analysed at its own,
    so that is noted rather than warned about. A layout read indirectly, or
    one the person changed away from what the files say, is flagged.
    """
    if guess is None or guess.layout is None:
        return None
    rates = describe_rates(guess.rates)
    summary = f"{chosen_layout} · {rates}" if rates else chosen_layout
    note = ""
    if len(set(guess.rates)) > 1:
        note = (f" The recordings were made at different sampling rates ({rates}); "
                "each is analysed at its own.")
    if chosen_layout != guess.layout:
        return Check("warn", f"You chose {chosen_layout}, but the files look like "
                             f"{guess.layout}. {guess.reason}{note}", summary)
    return Check("ok" if guess.sure else "warn", guess.reason + note, summary)

