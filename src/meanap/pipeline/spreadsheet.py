"""Read the recording list spreadsheet, mirroring ``pipelineReadCSV.m``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


#: The columns ``read_recording_csv`` expects, in order. Only the position
#: matters to the reader; the names are what a person reads.
SPREADSHEET_COLUMNS = ("Recording Filename", "DIV group", "Genotype")

#: Optional fourth column: electrodes to ground, per recording (ephys only).
GROUND_COLUMN = "Ground"

#: ``DIV14``, ``DIV_21``, ``div 7`` — the conventions that appear in real
#: recording names. Anchored on the letters so a bare number in a name (a date,
#: a plate id) is never mistaken for an age.
_DIV_RE = re.compile(r"DIV[\s_-]*(\d+)", re.IGNORECASE)


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


def _range_slice(n_rows: int, spreadsheet_range: str) -> tuple[int, int]:
    """The 0-indexed ``[start, end)`` data rows *spreadsheet_range* selects."""
    start_line, end_line = parse_spreadsheet_range(spreadsheet_range)
    return max(start_line - 2, 0), min(end_line - 1, n_rows)


def read_recording_csv(path: str | Path, spreadsheet_range: str) -> list[RecordingInfo]:
    """Read the recording list CSV.

    Expects columns: Recording Filename, DIV group, Genotype, [Ground].
    """
    df = pd.read_csv(path, header=0)

    start_idx, end_idx = _range_slice(len(df), spreadsheet_range)
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


# ── Building and editing a spreadsheet ────────────────────────────────────────
#
# A batch spreadsheet is mostly a list of names that must match the data folders
# exactly — the one thing a person retypes badly and a scan already knows. These
# turn a scan into a table, and a table into a file, so the GUI can offer both
# without a second idea of what the format is.


def infer_div(name: str) -> float | None:
    """The DIV a recording's name states, or ``None`` if it doesn't state one."""
    match = _DIV_RE.search(name)
    return float(match.group(1)) if match else None


def read_recording_names(path: str | Path,
                         spreadsheet_range: str = "A2:A100000") -> list[str]:
    """The recording names *path* lists within *spreadsheet_range*.

    Names only, read as text, so this still works on a sheet whose DIV and
    genotype columns are blank — :func:`read_recording_csv` would refuse that
    one, and a batch is usually named before it is annotated. Blank rows drop
    out, since a blank name matches no folder.
    """
    table = read_recording_table(path)
    if table.empty or table.shape[1] < 1:
        return []
    start, end = _range_slice(len(table), spreadsheet_range)
    names = table.iloc[start:end, 0].astype(str).str.strip()
    return [n for n in names if n and n.lower() != "nan"]


def new_recording_table(names, *, ground: bool = False) -> pd.DataFrame:
    """A batch spreadsheet for *names*, ready to be edited.

    DIV is filled in wherever the name says it, since that is stated rather than
    guessed. Genotype is deliberately left blank: it is not derivable from a
    folder name, and a wrong guess doesn't fail — it silently splits or merges
    the group comparisons the whole analysis is built on.
    """
    columns = list(SPREADSHEET_COLUMNS) + ([GROUND_COLUMN] if ground else [])
    rows = []
    for name in names:
        div = infer_div(str(name))
        row = {
            SPREADSHEET_COLUMNS[0]: str(name),
            SPREADSHEET_COLUMNS[1]: "" if div is None else _format_div(div),
            SPREADSHEET_COLUMNS[2]: "",
        }
        if ground:
            row[GROUND_COLUMN] = ""
        rows.append(row)
    return pd.DataFrame(rows, columns=columns, dtype=str)


def _format_div(div: float) -> str:
    """``14`` not ``14.0`` — DIVs are whole days in every dataset that has one."""
    return str(int(div)) if float(div).is_integer() else str(div)


def match_recording_name(name: str, candidates) -> str | None:
    """The candidate naming the same recording as *name*, or ``None``.

    Exact first, then the one near-miss that actually happens: a data folder
    that gained a trailing word ("… David Oluigbo") while the spreadsheet kept
    the short name, or the reverse. Anything looser risks matching two
    different recordings to each other, which is worse than not matching.
    """
    name = str(name).strip()
    if not name:
        return None
    for candidate in candidates:
        if str(candidate).strip() == name:
            return candidate
    for candidate in candidates:
        other = str(candidate).strip()
        if other.startswith(name + " ") or name.startswith(other + " "):
            return candidate
    return None


def fill_from_table(table: pd.DataFrame, source: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Copy DIV and group from *source* into *table*, matched by name.

    Returns the filled table and how many rows matched. The names in *table*
    are never touched — they came from the data, and the whole point is that
    they stay that way while the metadata comes from wherever it was kept.
    """
    filled = table.copy()
    if source.shape[1] < 2 or filled.empty:
        return filled, 0

    source_names = list(source.iloc[:, 0].astype(str))
    lookup = {str(n): i for i, n in enumerate(source_names)}

    matched = 0
    for row in range(len(filled)):
        hit = match_recording_name(filled.iat[row, 0], source_names)
        if hit is None:
            continue
        matched += 1
        src = lookup[str(hit)]
        for column in (1, 2):
            if filled.shape[1] > column and source.shape[1] > column:
                value = source.iat[src, column]
                filled.iat[row, column] = "" if pd.isna(value) else str(value).strip()
    return filled, matched


def read_recording_table(path: str | Path) -> pd.DataFrame:
    """A spreadsheet exactly as it is on disk, for editing.

    Everything is read as text and blanks stay blank — unlike
    :func:`read_recording_csv`, which coerces to the types a run needs. An
    editor must be able to show a malformed file in order to fix it.
    """
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        table = pd.read_excel(path, dtype=str)
    else:
        table = pd.read_csv(path, dtype=str)
    return table.fillna("").astype(str)


def write_recording_table(path: str | Path, table: pd.DataFrame) -> Path:
    """Write *table* in whichever format *path*'s extension asks for."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in (".xlsx", ".xls"):
        table.to_excel(path, index=False)
    else:
        table.to_csv(path, index=False)
    return path


def validate_recording_table(table: pd.DataFrame) -> list[str]:
    """Everything wrong with *table*, worst first; empty when it is usable.

    Each of these produces a run that fails confusingly or, worse, succeeds on
    the wrong data: a blank name matches no folder, a duplicate analyses one
    recording twice, a non-numeric DIV crashes the age axis, and a blank
    genotype collapses every group comparison into one unnamed group.
    """
    problems: list[str] = []
    if table.empty:
        return ["The spreadsheet has no rows."]

    names = table.iloc[:, 0].astype(str).str.strip()

    blank = int((names == "").sum())
    if blank:
        problems.append(f"{blank} row(s) have no recording name.")

    named = names[names != ""]
    duplicates = sorted(named[named.duplicated()].unique())
    if duplicates:
        problems.append("Duplicate recording name(s): " + ", ".join(duplicates[:5])
                        + (" …" if len(duplicates) > 5 else ""))

    if table.shape[1] > 1:
        divs = table.iloc[:, 1].astype(str).str.strip()
        bad = [n for n, d in zip(names, divs) if not _is_number(d)]
        if bad:
            problems.append(f"{len(bad)} row(s) have a missing or non-numeric DIV "
                            f"(first: {bad[0] or '<unnamed>'}).")

    if table.shape[1] > 2:
        groups = table.iloc[:, 2].astype(str).str.strip()
        empty = int((groups == "").sum())
        if empty:
            problems.append(f"{empty} row(s) have no genotype/group — fill this in, "
                            "it is what the group comparisons are built from.")

    return problems


def _is_number(value: str) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


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
