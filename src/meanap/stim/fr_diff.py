"""Percentage change in firing rate from a pre-stimulation baseline, per channel.

Port of the lab script ``fr_diff.py`` (and the parts of ``fr_boxplots.py`` it
borrows). It reads step 2's ``NeuronalActivity_NodeLevel.csv`` and compares
each slice recorded under stimulation against that same slice's own
pre-stimulation recording, channel by channel::

    percentage difference = 100 x (stim FR - baseline FR) / baseline FR

It is a diagnostic: did stimulating change how the slice fired at all? Only the
arithmetic and the pairing live here. The figure and the GUI view draw from
the :class:`FrDiffResult` this returns.

Pairing
-------
The condition is the token after ``DIV<n>_`` in the file name. The baseline is
``prestim`` and the stimulation patterns ``stim1``, ``stim3``, ``stimLR`` and
``stimRL`` by default (see :class:`FrDiffConfig`); any other condition is
ignored with a note.

A stim recording pairs with a baseline recording when the run ID *and* the
slice match, so ``R250929CT1A_DIV250_stim1`` pairs with
``R250929CT1A_DIV250_prestim`` but never with ``R250929CT1B_…`` (another slice)
or ``R250930CT1A_…`` (another run). The slice is the token fused onto the run
ID (``CT1A``); ``Grp`` plays no part in pairing, since its spelling varies
between exports of the same organoid (``CTL``, ``BCTL``).

By default only complete experiments become panels: a slice needs its baseline
and every pattern. A slice with a condition recorded twice (e.g. at two DIVs)
never does, since there is no telling which recording a reading belongs with.

Excluded channels
-----------------
A grounded channel is left out of every pattern, and a stimulating one out of
the patterns that drove it. A channel whose baseline is 0 Hz has no percentage
and is left out too. A channel that falls silent under stimulation is *not*
assumed to be a stimulating electrode: it is kept, at -100 %.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from natsort import natsort_keygen

__all__ = [
    "FrDiffConfig", "Record", "Diff", "Excluded", "Panel", "Unpaired", "Note",
    "FrDiffResult", "compute_fr_diff", "compute_fr_diff_csv", "load_records",
    "build_panels", "describe", "format_note", "parse_run", "parse_slice",
    "parse_condition", "pct_diff", "log2_ratio", "multi_run", "panel_title",
    "EXCLUDED_GROUNDED", "EXCLUDED_STIMULATING", "EXCLUDED_ZERO_BASE",
    "REASON_NO_STIM", "REASON_NO_BASE", "REASON_INCOMPLETE", "REASON_TWICE",
    "REASON_UNPARSED", "UNKNOWN",
]

_natural_key = natsort_keygen()

UNKNOWN = "unknown"

# Channels 21, 31, 41, 51, 61 and 71 were the stimulating electrodes in the
# experiments this was written for, and were left out of spike counting, so
# they read 0 Hz by design. Listed under every pattern until a pattern that
# drives only some of them says otherwise.
_LAB_STIM_ELECTRODES = frozenset({21, 31, 41, 51, 61, 71})


@dataclass(frozen=True)
class FrDiffConfig:
    """What counts as a baseline, a pattern, and a channel to leave out.

    The defaults are the SAND Lab stimulation protocol the original script was
    written for.
    """

    baseline: str = "prestim"
    #: Condition token -> the name shown in the legend, in legend order.
    stim_labels: dict[str, str] = field(default_factory=lambda: {
        "stim1": "Spatial 1", "stim3": "Spatial 3",
        "stimLR": "Temporal LR", "stimRL": "Temporal RL",
    })
    #: Channels left out of every recording.
    grounded: frozenset[int] = frozenset({15})
    #: Condition token -> the channels that pattern drove, left out of it only.
    stimulated: dict[str, frozenset[int]] = field(default_factory=lambda: {
        t: _LAB_STIM_ELECTRODES for t in ("stim1", "stim3", "stimLR", "stimRL")
    })
    #: When True a slice needs every pattern in ``stim_labels`` to be plotted;
    #: when False any one of them alongside the baseline will do.
    require_all_patterns: bool = True

    @property
    def stims(self) -> tuple[str, ...]:
        return tuple(self.stim_labels)

    def label(self, token: str) -> str:
        return self.stim_labels.get(token, token)


@dataclass(frozen=True)
class Record:
    """One (FileName, Grp, Channel, FR) row of the node-level CSV, parsed."""

    filename: str
    grp: str
    channel: int
    fr: float
    run: str | None          # e.g. R250929
    organoid: str            # e.g. CT1
    slice: str               # e.g. CT1A
    condition: str | None    # e.g. prestim, stim1


@dataclass(frozen=True)
class Diff:
    """One channel's change under one stimulation pattern."""

    channel: int
    stim: str                # condition token, e.g. stim1
    pct: float               # 100 * (stim_fr - base_fr) / base_fr
    base_fr: float
    stim_fr: float
    log2: float | None       # log2(stim_fr / base_fr); None when stim_fr is 0 (-inf)


EXCLUDED_GROUNDED = "grounded"
EXCLUDED_STIMULATING = "stimulating"
EXCLUDED_ZERO_BASE = "0 Hz baseline"


@dataclass(frozen=True)
class Excluded:
    """Readings of one channel left out of the plot, and why.

    ``readings`` holds what each pattern recorded on that channel and was set
    aside: every pattern for a grounded channel or a 0 Hz baseline, only the
    driving patterns for a stimulating one.
    """

    channel: int
    reason: str                                 # one of the EXCLUDED_* constants
    base_fr: float
    readings: tuple[tuple[str, float], ...]     # ((token, stim_fr), ...), never empty


@dataclass
class Panel:
    """One slice with its baseline and its stimulation patterns."""

    run: str
    slice: str
    organoid: str
    grp: str
    base_file: str
    stim_files: dict[str, str]                  # condition token -> FileName
    diffs: list[Diff] = field(default_factory=list)
    excluded: list[Excluded] = field(default_factory=list)
    missing_base: list[int] = field(default_factory=list)   # in a stim, absent from baseline
    missing_stim: list[int] = field(default_factory=list)   # in baseline, absent from a stim

    @property
    def id(self) -> str:
        return f"{self.run}/{self.slice}"

    @property
    def stims(self) -> list[str]:
        return sorted(self.stim_files, key=_natural_key)

    @property
    def channels(self) -> list[int]:
        return sorted({d.channel for d in self.diffs} | {e.channel for e in self.excluded})

    @property
    def unplotted(self) -> list[int]:
        """Excluded channels left with no point at all: the ones marked in red."""
        plotted = {d.channel for d in self.diffs}
        return sorted({e.channel for e in self.excluded} - plotted)


REASON_NO_STIM = "no stim recording"
REASON_NO_BASE = "no baseline recording"
REASON_INCOMPLETE = "incomplete"
REASON_TWICE = "a condition recorded twice"
REASON_UNPARSED = "condition not parsed"


@dataclass(frozen=True)
class Unpaired:
    """A slice that produced no panel, and why."""

    run: str
    slice: str
    conditions: tuple[str, ...]
    reason: str                                 # one of the REASON_* constants
    missing: tuple[str, ...] = ()               # the patterns an incomplete slice lacks


@dataclass(frozen=True)
class Note:
    """Something about the input worth saying, and a few of the files it is about."""

    message: str
    examples: tuple[str, ...] = ()


@dataclass
class FrDiffResult:
    panels: list[Panel]
    unpaired: list[Unpaired]
    notes: list[Note]
    config: FrDiffConfig


# ── parsing ──────────────────────────────────────────────────────────────────

def parse_run(filename: str) -> str | None:
    """The run ID ``R250929`` from ``R250929CT1A_DIV250_prestim``, or None."""
    m = re.match(r"(R\d+)", filename)
    return m.group(1) if m else None


def parse_slice(filename: str) -> tuple[str, str]:
    """(organoid, slice) from a file name, or (UNKNOWN, UNKNOWN).

    The slice is the token fused onto the run ID: ``R250929MO7B_DIV250_stim1``
    gives ``("MO7", "MO7B")``.
    """
    m = re.match(r"R\d+([A-Za-z]+\d+)([A-Za-z])(?=_|$)", filename)
    if not m:
        return UNKNOWN, UNKNOWN
    organoid, letter = m.group(1), m.group(2).upper()
    return organoid, f"{organoid}{letter}"


def parse_condition(filename: str) -> str | None:
    """The condition token after ``DIV<n>_`` (``stim1``, ``prestim``), or None."""
    m = re.search(r"DIV\d+_(.+)$", filename)
    return m.group(1).rsplit("_", 1)[-1] if m else None


def _div(filename: str) -> str | None:
    m = re.search(r"(DIV\d+)_", filename)
    return m.group(1) if m else None


def _group_of(grp: str) -> str:
    """The experimental group: the last three characters, so BCTL == CTL."""
    return grp.strip().upper()[-3:]


def pct_diff(base_fr: float, stim_fr: float) -> float:
    """Percentage change from ``base_fr`` to ``stim_fr``. ``base_fr`` must be > 0."""
    return 100.0 * (stim_fr - base_fr) / base_fr


def log2_ratio(base_fr: float, stim_fr: float) -> float | None:
    """log2(stim_fr / base_fr), or None when ``stim_fr`` is 0 and the ratio is -inf.

    Symmetric where the percentage is not: halving is -1 and doubling +1.
    ``base_fr`` must be above 0.
    """
    return math.log2(stim_fr / base_fr) if stim_fr > 0 else None


_REQUIRED_COLUMNS = ("filename", "grp", "channel", "fr")


def load_records(table: pd.DataFrame) -> tuple[list[Record], list[Note]]:
    """Parse the node-level table's rows, skipping those without a usable FR/Channel.

    Column names are matched case-insensitively.
    """
    lookup = {str(c).strip().lstrip("﻿").lower(): c for c in table.columns}
    missing = [c for c in _REQUIRED_COLUMNS if c not in lookup]
    if missing:
        raise ValueError(f"The table is missing column(s) {', '.join(missing)} "
                         f"(found {', '.join(map(str, table.columns))}).")
    cols = {c: lookup[c] for c in _REQUIRED_COLUMNS}

    fr = pd.to_numeric(table[cols["fr"]], errors="coerce")
    channel = pd.to_numeric(table[cols["channel"]], errors="coerce")
    bad_fr = fr.isna()
    bad_channel = channel.isna() & ~bad_fr

    records = []
    for name, grp, ch, rate in zip(table[cols["filename"]][~(bad_fr | bad_channel)],
                                   table[cols["grp"]][~(bad_fr | bad_channel)],
                                   channel[~(bad_fr | bad_channel)],
                                   fr[~(bad_fr | bad_channel)]):
        name = "" if pd.isna(name) else str(name).strip()
        organoid, slc = parse_slice(name)
        records.append(Record(
            filename=name, grp="" if pd.isna(grp) else str(grp).strip(),
            channel=int(ch), fr=float(rate), run=parse_run(name),
            organoid=organoid, slice=slc, condition=parse_condition(name)))

    notes = []
    if bad_fr.any():
        notes.append(Note(f"skipped {int(bad_fr.sum())} row(s) with a missing or "
                          f"non-numeric FR."))
    if bad_channel.any():
        notes.append(Note(f"skipped {int(bad_channel.sum())} row(s) with a non-numeric "
                          f"Channel."))
    return records, notes


# ── pairing ──────────────────────────────────────────────────────────────────

def _bucket(records: list[Record], config: FrDiffConfig,
            notes: list[Note]) -> tuple[dict, dict, list[Unpaired]]:
    """Group usable records by (run, slice) -> condition -> channel -> (fr, filename).

    Also returns (run, slice, condition) -> the FileNames seen for it, so a
    condition recorded twice can be caught. Records that cannot be paired, and
    conditions outside the analysis, are reported and left out.
    """
    by_key: dict[tuple[str, str], dict[str, dict[int, tuple[float, str]]]] = defaultdict(
        lambda: defaultdict(dict))
    files_of: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    unpaired: list[Unpaired] = []
    wanted = {config.baseline, *config.stims}

    no_run: set[str] = set()
    no_condition: set[str] = set()
    no_slice: set[str] = set()
    ignored: dict[str, set[str]] = defaultdict(set)     # token -> FileNames
    duplicates: set[str] = set()

    for r in records:
        if r.run is None:
            no_run.add(r.filename)
            continue
        if r.condition is None:
            no_condition.add(r.filename)
            unpaired.append(Unpaired(r.run, r.slice, (r.filename,), REASON_UNPARSED))
            continue
        if r.condition not in wanted:
            ignored[r.condition].add(r.filename)
            continue
        # Every unparseable name shares the slice UNKNOWN, so keeping them would
        # let two unrelated recordings pair with each other.
        if r.slice == UNKNOWN:
            no_slice.add(r.filename)
            continue
        files_of[(r.run, r.slice, r.condition)].add(r.filename)
        channels = by_key[(r.run, r.slice)][r.condition]
        if r.channel in channels:
            duplicates.add(r.filename)
            continue
        channels[r.channel] = (r.fr, r.filename)

    if no_run:
        notes.append(Note(f"no run ID in {len(no_run)} file name(s); they cannot be paired:",
                          tuple(sorted(no_run))))
    if no_condition:
        notes.append(Note(f"no condition after 'DIV<n>_' in {len(no_condition)} file "
                          f"name(s); they cannot be paired:", tuple(sorted(no_condition))))
    if ignored:
        names = sorted(n for files in ignored.values() for n in files)
        notes.append(Note(
            f"{len(names)} recording(s) of condition(s) "
            f"{', '.join(sorted(ignored, key=_natural_key))} were ignored; this analysis "
            f"uses {config.baseline} and {', '.join(config.stims)} only:", tuple(names)))
    if no_slice:
        notes.append(Note(f"no organoid slice in {len(no_slice)} file name(s); they "
                          f"cannot be paired:", tuple(sorted(no_slice))))
    if duplicates:
        notes.append(Note(f"{len(duplicates)} recording(s) list a channel on more than "
                          f"one row; the first value was kept:", tuple(sorted(duplicates))))

    # One Unpaired per recording, not one per row.
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for u in unpaired:
        key = (u.run, u.slice, u.conditions[0])
        if key not in seen:
            seen.add(key)
            deduped.append(u)
    return by_key, files_of, deduped


def _classify(panel: Panel, channel: int, base_fr: float,
              readings: tuple[tuple[str, float], ...], config: FrDiffConfig) -> None:
    """Add one channel's percentages, or its exclusion, to ``panel``."""
    if channel in config.grounded:
        panel.excluded.append(Excluded(channel, EXCLUDED_GROUNDED, base_fr, readings))
        return
    # A known stimulating electrode is named as such before its baseline is
    # looked at: it reads 0 Hz by design, and "0 Hz baseline" is kept for the
    # zeros nothing explains.
    driving = tuple((t, fr) for t, fr in readings
                    if channel in config.stimulated.get(t, ()))
    if driving:
        panel.excluded.append(Excluded(channel, EXCLUDED_STIMULATING, base_fr, driving))
    driven_by = {t for t, _ in driving}
    rest = tuple((t, fr) for t, fr in readings if t not in driven_by)
    if not rest:
        return
    if base_fr == 0:
        panel.excluded.append(Excluded(channel, EXCLUDED_ZERO_BASE, base_fr, rest))
        return
    for token, stim_fr in rest:
        panel.diffs.append(Diff(channel, token, pct_diff(base_fr, stim_fr),
                                base_fr, stim_fr, log2_ratio(base_fr, stim_fr)))


def build_panels(records: list[Record], config: FrDiffConfig | None = None,
                 notes: list[Note] | None = None) -> tuple[list[Panel], list[Unpaired]]:
    """Pair each slice's stim recordings against its own baseline.

    Returns the panels that can be plotted and the slices that could not be,
    with why. Anything worth saying about the input is appended to ``notes``.
    """
    config = config or FrDiffConfig()
    notes = notes if notes is not None else []
    required = config.stims
    by_key, files_of, unpaired = _bucket(records, config, notes)

    grps_of: dict[tuple[str | None, str], set[str]] = defaultdict(set)
    organoid_of: dict[tuple[str | None, str], str] = {}
    for r in records:
        grps_of[(r.run, r.slice)].add(_group_of(r.grp))
        organoid_of[(r.run, r.slice)] = r.organoid

    panels: list[Panel] = []
    negative_base: set[str] = set()
    mixed_div: list[str] = []
    mixed_grp: list[str] = []

    for (run, slc) in sorted(by_key, key=lambda k: (_natural_key(k[0]), _natural_key(k[1]))):
        conditions = by_key[(run, slc)]
        present = tuple(t for t in required if t in conditions)
        missing = tuple(t for t in required if t not in conditions)
        twice = [t for t in conditions if len(files_of[(run, slc, t)]) > 1]

        if twice:
            unpaired.append(Unpaired(run, slc, tuple(sorted(twice, key=_natural_key)),
                                     REASON_TWICE))
            continue
        if config.baseline not in conditions:
            unpaired.append(Unpaired(run, slc, present, REASON_NO_BASE))
            continue
        if not present:
            unpaired.append(Unpaired(run, slc, (config.baseline,), REASON_NO_STIM))
            continue
        if missing and config.require_all_patterns:
            unpaired.append(Unpaired(run, slc, (config.baseline, *present),
                                     REASON_INCOMPLETE, missing))
            continue

        base_channels = conditions[config.baseline]
        base_file = next(iter(files_of[(run, slc, config.baseline)]))
        stim_files = {t: next(iter(files_of[(run, slc, t)])) for t in present}

        # The pairing rule is run + slice, so a pair whose DIV tokens differ is
        # still a pair -- but it is worth saying out loud.
        base_div = _div(base_file)
        for token, name in stim_files.items():
            if base_div and _div(name) and _div(name) != base_div:
                mixed_div.append(f"{run} {slc}: {base_div}_{config.baseline} with "
                                 f"{_div(name)}_{token}")

        grps = grps_of.get((run, slc), set())
        if len(grps) > 1:
            mixed_grp.append(f"{run} {slc}: {', '.join(sorted(grps))}")

        panel = Panel(run=run, slice=slc, organoid=organoid_of.get((run, slc), UNKNOWN),
                      grp="/".join(sorted(grps)), base_file=base_file, stim_files=stim_files)

        # Channel-major: whether a channel is excluded is a fact about the
        # channel across every condition, not about one stim recording.
        stim_channels = {c for t in present for c in conditions[t]}
        for channel in sorted(stim_channels | set(base_channels)):
            if channel not in base_channels:
                panel.missing_base.append(channel)
                continue
            readings = tuple((t, conditions[t][channel][0])
                             for t in present if channel in conditions[t])
            if len(readings) < len(present):
                panel.missing_stim.append(channel)
            if not readings:
                continue
            base_fr = base_channels[channel][0]
            if base_fr < 0:
                negative_base.add(base_channels[channel][1])
                continue
            _classify(panel, channel, base_fr, readings, config)

        panels.append(panel)

    if negative_base:
        notes.append(Note(f"{len(negative_base)} recording(s) have a negative baseline FR, "
                          f"which is not a firing rate; those channels were skipped:",
                          tuple(sorted(negative_base))))
    if mixed_div:
        notes.append(Note("a pair spans two DIVs (run ID and slice still match, so it is "
                          "a pair):", tuple(sorted(set(mixed_div)))))
    if mixed_grp:
        notes.append(Note("a slice's recordings disagree on its group (compared on the "
                          "last three characters of Grp):", tuple(mixed_grp)))
    return panels, unpaired


def compute_fr_diff(table: pd.DataFrame, config: FrDiffConfig | None = None) -> FrDiffResult:
    """Pair every slice in a node-level table and compute its per-channel changes."""
    config = config or FrDiffConfig()
    records, notes = load_records(table)
    panels, unpaired = build_panels(records, config, notes)
    return FrDiffResult(panels, unpaired, notes, config)


def compute_fr_diff_csv(path: Path | str, config: FrDiffConfig | None = None) -> FrDiffResult:
    """:func:`compute_fr_diff` on a ``NeuronalActivity_NodeLevel.csv`` on disk."""
    return compute_fr_diff(pd.read_csv(path, encoding="utf-8-sig"), config)


# ── description ──────────────────────────────────────────────────────────────

def multi_run(panels: list[Panel]) -> bool:
    return len({p.run for p in panels}) > 1


def panel_title(panel: Panel, multi: bool) -> str:
    """``CT1A``, or ``R250929 CT1A`` when the table holds more than one run."""
    return f"{panel.run} {panel.slice}" if multi else panel.slice


def format_note(note: Note, max_examples: int = 5) -> list[str]:
    """A note as log lines, naming at most ``max_examples`` of its files."""
    lines = [f"Note: {note.message}"]
    lines += [f"  {name}" for name in note.examples[:max_examples]]
    if len(note.examples) > max_examples:
        lines.append(f"  ... and {len(note.examples) - max_examples} more")
    return lines


def describe(result: FrDiffResult) -> list[str]:
    """What paired, what did not, and why, one line each.

    Always names the run: the point is to explain why two recordings that look
    alike did not pair.
    """
    config = result.config
    lines = []
    for p in result.panels:
        counts = [f"{len({d.channel for d in p.diffs})} channels paired"]
        if p.excluded:
            named = ", ".join(f"{e.channel} ({e.reason}"
                              + (f": {', '.join(t for t, _ in e.readings)})"
                                 if e.reason == EXCLUDED_STIMULATING else ")")
                              for e in p.excluded)
            counts.append(f"{len(p.excluded)} excluded: {named}")
        if p.missing_base:
            counts.append(f"{len(p.missing_base)} stim-only")
        if p.missing_stim:
            counts.append(f"{len(p.missing_stim)} missing from a stim recording")
        lines.append(f"{p.run} {p.slice}: {config.baseline} + {', '.join(p.stims)}"
                     f"   |   {', '.join(counts)}")

    if result.unpaired:
        lines.append("Not plotted:")
        for u in sorted(result.unpaired,
                        key=lambda u: (_natural_key(u.run), _natural_key(u.slice))):
            if u.reason == REASON_UNPARSED:
                lines.append(f"  {u.run}: condition not parsed from the file name "
                             f"({u.conditions[0]})")
            elif u.reason == REASON_INCOMPLETE:
                lines.append(f"  {u.run} {u.slice}: {', '.join(u.conditions)} "
                             f"(incomplete: no {', '.join(u.missing)})")
            elif u.reason == REASON_TWICE:
                lines.append(f"  {u.run} {u.slice}: {', '.join(u.conditions)} recorded "
                             f"more than once (e.g. at two DIVs)")
            elif u.reason == REASON_NO_BASE:
                lines.append(f"  {u.run} {u.slice}: {', '.join(u.conditions)} only "
                             f"(no {config.baseline} recording)")
            else:
                lines.append(f"  {u.run} {u.slice}: {', '.join(u.conditions)} only "
                             f"({u.reason})")

    total = len(result.panels) + len(result.unpaired)
    lines.append(f"{len(result.panels)} of {total} slice(s) plotted.")
    return lines
