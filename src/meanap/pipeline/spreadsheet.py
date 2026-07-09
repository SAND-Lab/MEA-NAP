"""Read the recording list spreadsheet, mirroring ``pipelineReadCSV.m``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class RecordingInfo:
    filename: str
    div: float
    group: str
    ground: str | None = None


def parse_spreadsheet_range(range_str: str) -> tuple[int, int]:
    """Parse a range like ``'A2:A3'`` or ``'2:1000'`` into 1-indexed (start_line, end_line).

    Line numbers count the header as line 1, matching MATLAB's ``DataLines``/
    ``csvRange`` convention (e.g. ``[2, 3]`` reads the first two data rows
    after the header).
    """
    match = re.match(r"^[A-Za-z]*(\d+)\s*:\s*[A-Za-z]*(\d+)$", range_str.strip())
    if not match:
        raise ValueError(f"Invalid spreadsheet range: {range_str!r}")
    return int(match.group(1)), int(match.group(2))


def read_recording_csv(path: str | Path, spreadsheet_range: str) -> list[RecordingInfo]:
    """Read the recording list CSV.

    Expects columns: Recording Filename, DIV group, Genotype, [Ground].
    """
    start_line, end_line = parse_spreadsheet_range(spreadsheet_range)
    df = pd.read_csv(path, header=0)

    start_idx = max(start_line - 2, 0)
    end_idx = min(end_line - 1, len(df))
    subset = df.iloc[start_idx:end_idx]

    has_ground = subset.shape[1] >= 4
    recordings = []
    for _, row in subset.iterrows():
        recordings.append(RecordingInfo(
            filename=str(row.iloc[0]),
            div=float(row.iloc[1]),
            group=str(row.iloc[2]),
            ground=str(row.iloc[3]) if has_ground else None,
        ))
    return recordings


def parse_ground_electrodes(ground: str | None) -> set[int] | None:
    """Parse a recording's ``Ground`` spreadsheet value (comma-separated
    channel IDs) into a set of ints, port of ``groundSpikeTimes.m``'s
    electrode-list parsing. Returns ``None`` if there's nothing to ground —
    including pandas turning an empty cell into the string ``"nan"``, which
    ``read_recording_csv`` doesn't special-case (it just calls ``str()`` on
    whatever pandas gives it).
    """
    if ground is None:
        return None
    ground = ground.strip()
    if not ground or ground.lower() == "nan":
        return None
    return {int(float(x)) for x in ground.split(",") if x.strip()}


def ground_spike_times_dict(
    spike_times_dict: dict[int, np.ndarray],
    channels: np.ndarray,
    ground_electrodes: set[int] | None,
) -> dict[int, np.ndarray]:
    """Zero out spike times for channels listed in ``ground_electrodes``
    (matched by channel ID/name — MATLAB's default
    ``Params.electrodesToGroundPerRecordingUseName = 1`` behavior, the only
    mode this port supports), port of ``groundSpikeTimes.m``.

    ``spike_times_dict`` maps 0-indexed channel *position* (matching
    ``channels[i]``'s position) to that channel's spike times for a single
    already-selected detection method — the shape this is called with in
    ``step2.py``/``step3.py``/``step4.py``.
    """
    if not ground_electrodes:
        return spike_times_dict
    grounded_idx = {i for i, ch in enumerate(channels) if int(ch) in ground_electrodes}
    if not grounded_idx:
        return spike_times_dict
    return {
        ch: (np.array([]) if ch in grounded_idx else times)
        for ch, times in spike_times_dict.items()
    }
