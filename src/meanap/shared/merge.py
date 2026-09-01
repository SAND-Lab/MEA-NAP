"""Pooling every machine's part into one output folder.

Each machine's part is an ordinary output folder for its share of the batch.
Bringing them together is a file-level union of the things that belong to
*one recording* — its spike times, adjacency, checks, and figures — plus a
key-level union of step 4's ``netmet_results.json``, which holds one entry
per recording in a single file.

Nothing computed *across* the batch is carried over: the group comparisons,
the summary CSVs, the cartography boundaries, the report. Each part computed
those over its own share, which is not the batch, and the pooled run redoes
every one of them over all of it — that is what a *continued* run is
(``docs/python/changing-a-batch.md``), and it is what the main computer runs
on the merged folder. So this module only has to be right about which files
are per-recording, and it takes that list from the same place the rest of the
pipeline does: :mod:`meanap.pipeline.roster`.

A part may be a ``.meanap`` bundle rather than a folder — an express-mode
share leaves one in place of its folder — and is read the same way.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from meanap.pipeline.atomic import atomic_write_json
from meanap.pipeline.roster import _DATA_FILES, _FIGURE_ROOTS

__all__ = ["MergeReport", "merge_outputs", "recordings_in"]

#: ``<root>/<group>/<recording>/`` trees of per-recording figures. The
#: roster's three plus step 3's thresholding checks, which use the layout but
#: are not a place a removed recording's figures would be looked for.
FIGURE_ROOTS: tuple[Path, ...] = tuple(_FIGURE_ROOTS) + (Path("3_EdgeThresholdingCheck"),)

#: Directories whose every file belongs to one recording. Derived from the
#: roster's data patterns so a new per-recording artefact registered there is
#: merged without this module hearing about it.
DATA_DIRS: tuple[Path, ...] = tuple(dict.fromkeys(d for d, _ in _DATA_FILES))

#: Suffixes that identify a recording by its data file, for the report.
_NAME_SUFFIXES = tuple(
    pattern.replace("{rec}", "") for _, pattern in _DATA_FILES)

NETMET_PATH = Path("4_NetworkActivity") / "netmet_results.json"


@dataclass
class MergeReport:
    sources: int = 0
    files_copied: int = 0
    figure_dirs_copied: int = 0
    netmet_entries: int = 0
    already_present: int = 0
    recordings: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def describe(self) -> list[str]:
        lines = [
            f"Merged {self.sources} part(s): {len(self.recordings)} recording(s), "
            f"{self.files_copied} data file(s), {self.figure_dirs_copied} figure "
            f"folder(s), {self.netmet_entries} network-metric entr(y/ies)",
        ]
        if self.already_present:
            lines.append(f"  {self.already_present} item(s) were already in place "
                         "and were left as they were")
        lines.extend(f"  {note}" for note in self.notes)
        return lines


def recordings_in(root: Path | str) -> set[str]:
    """The recordings a part holds data for, by their data files."""
    root = Path(root)
    found: set[str] = set()
    for rel in DATA_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in base.iterdir():
            if not path.is_file():
                continue
            for suffix in _NAME_SUFFIXES:
                if path.name.endswith(suffix):
                    found.add(path.name[: -len(suffix)])
                    break
    return found


def merge_outputs(
    sources: Iterable[Path | str], dest: Path | str,
    *, log: Callable[[str], None] | None = None,
) -> MergeReport:
    """Union every part in *sources* into *dest*, which need not exist yet.

    First writer wins: a recording already in *dest* — from an earlier part,
    or from the main computer's own share when *dest* is that folder — is
    left alone. Parts only ever hold the recordings they were given, so the
    case is rare and either copy would be a complete result.
    """
    from meanap.pipeline.bundle import is_bundle, open_bundle

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    report = MergeReport()
    for source in sources:
        source = Path(source)
        if is_bundle(source):
            with open_bundle(source) as bundle:
                _merge_folder(bundle.root, dest, report, log)
        elif source.is_dir():
            _merge_folder(source, dest, report, log)
        else:
            report.notes.append(f"skipped {source}: not an output folder or bundle")
            continue
        report.sources += 1
    if log:
        for line in report.describe():
            log(line)
    return report


def _merge_folder(src: Path, dest: Path, report: MergeReport, log) -> None:
    if src.resolve() == dest.resolve():
        # The main computer's own share, when it is merged in place.
        report.recordings |= recordings_in(src)
        return
    names = recordings_in(src)
    report.recordings |= names
    if log:
        log(f"  {src}: {len(names)} recording(s)")

    for rel in DATA_DIRS:
        base = src / rel
        if not base.is_dir():
            continue
        (dest / rel).mkdir(parents=True, exist_ok=True)
        for path in sorted(base.iterdir()):
            if not path.is_file():
                continue
            target = dest / rel / path.name
            if target.exists():
                report.already_present += 1
                continue
            shutil.copy2(path, target)
            report.files_copied += 1

    for rel in FIGURE_ROOTS:
        base = src / rel
        if not base.is_dir():
            continue
        for group_dir in sorted(base.iterdir()):
            if not group_dir.is_dir():
                continue
            for rec_dir in sorted(group_dir.iterdir()):
                if not rec_dir.is_dir():
                    continue
                target = dest / rel / group_dir.name / rec_dir.name
                if target.exists():
                    report.already_present += 1
                    continue
                shutil.copytree(rec_dir, target)
                report.figure_dirs_copied += 1

    report.netmet_entries += _merge_netmet(src / NETMET_PATH, dest / NETMET_PATH)


def _merge_netmet(src: Path, dest: Path) -> int:
    """Add *src*'s per-recording entries to *dest*, keeping what is there."""
    if not src.is_file():
        return 0
    try:
        with open(src) as fh:
            incoming = json.load(fh)
    except (OSError, ValueError):
        return 0
    if not isinstance(incoming, dict):
        return 0
    existing: dict = {}
    if dest.is_file():
        try:
            with open(dest) as fh:
                existing = json.load(fh)
        except (OSError, ValueError):
            existing = {}
        if not isinstance(existing, dict):
            existing = {}
    added = 0
    for name, entry in incoming.items():
        if name not in existing and entry:
            existing[name] = entry
            added += 1
    if added:
        dest.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(dest, existing, indent=2)
    return added
