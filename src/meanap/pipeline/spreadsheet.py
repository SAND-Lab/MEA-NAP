"""Read the recording list spreadsheet, mirroring ``pipelineReadCSV.m``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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
