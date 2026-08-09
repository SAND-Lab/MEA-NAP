"""Keeping an output folder honest about which recordings it analysed.

The spreadsheet decides what a run covers, and it changes: a sixth recording
arrives, or one turns out to be bad and is taken out. Continuing a run
(``Params.continue_interrupted``) handles both for the *numbers* — a new
recording is computed, a removed one is left out of every pooled statistic, and
the CSVs are rewritten from what remains.

The **figures** are the problem. They are written per recording into their own
folders and nothing goes back for them, so a removed recording leaves its plots
sitting in the output tree and in ``report.html``, indistinguishable from the
ones that are still part of the analysis. A folder that shows twenty-three
figures for a recording its own CSVs never mention is worse than one that is
merely out of date, because nothing about it looks wrong.

So a continued run reconciles the two: anything the folder holds that the
spreadsheet no longer names is reported by name, and pruned when the run asks
for it. Reporting is the default because this deletes results, and a run that
quietly removed the wrong thing would be discovered much later, if ever.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

__all__ = ["StaleRecording", "find_stale_recordings", "prune_recordings"]

#: Per-recording *figure* directories, relative to the run root. Each holds one
#: subfolder per group, then one per recording.
_FIGURE_ROOTS = (
    Path("4_NetworkActivity") / "4A_IndividualNetworkAnalysis",
    Path("2_NeuronalActivity") / "2A_IndividualNeuronalAnalysis",
    Path("1_SpikeDetection") / "1B_SpikeDetectionChecks",
)

#: Per-recording *data* files, as ``(directory, filename pattern)``. Kept apart
#: from the figures because they are worth different things: the data is what
#: makes a recording cheap to add back, the figures are pure output.
_DATA_FILES = (
    (Path("ExperimentMatFiles"), "{rec}_adjM.npz"),
    (Path("ExperimentMatFiles"), "{rec}_catnap.npz"),
    (Path("ExperimentMatFiles"), "{rec}_background.npz"),
    (Path("ExperimentMatFiles"), "{rec}_edgecheck.npz"),
    (Path("1_SpikeDetection") / "1A_SpikeDetectedData", "{rec}_spikes.npz"),
    (Path("1_SpikeDetection") / "1A_SpikeDetectedData", "{rec}_step1checks.npz"),
)


@dataclass
class StaleRecording:
    """A recording the folder still holds but the spreadsheet no longer names."""

    name: str
    figure_dirs: list[Path] = field(default_factory=list)
    data_files: list[Path] = field(default_factory=list)

    @property
    def n_figures(self) -> int:
        return sum(len(list(d.rglob("*.png"))) for d in self.figure_dirs)

    def describe(self) -> str:
        bits = []
        if self.n_figures:
            bits.append(f"{self.n_figures} figure(s)")
        if self.data_files:
            bits.append(f"{len(self.data_files)} data file(s)")
        return f"{self.name}: " + (", ".join(bits) if bits else "nothing on disk")


def find_stale_recordings(
    output_root: Path | str, keep: Iterable[str],
) -> list[StaleRecording]:
    """Recordings with work in *output_root* that *keep* does not name.

    ``keep`` is the spreadsheet's recording list. Directory names are matched
    exactly against it, so a recording is only ever called stale because the
    spreadsheet stopped naming it — never because of a near-miss.
    """
    output_root = Path(output_root)
    keep = set(keep)
    found: dict[str, StaleRecording] = {}

    def entry(name: str) -> StaleRecording:
        return found.setdefault(name, StaleRecording(name=name))

    for rel in _FIGURE_ROOTS:
        base = output_root / rel
        if not base.is_dir():
            continue
        # <family>/<group>/<recording>/ — the group layer is the pipeline's, and
        # groups are not recordings, so only the second level is considered.
        for group_dir in base.iterdir():
            if not group_dir.is_dir():
                continue
            for rec_dir in group_dir.iterdir():
                if rec_dir.is_dir() and rec_dir.name not in keep:
                    entry(rec_dir.name).figure_dirs.append(rec_dir)

    for rel, pattern in _DATA_FILES:
        base = output_root / rel
        if not base.is_dir():
            continue
        suffix = pattern.replace("{rec}", "")
        for path in base.glob(pattern.replace("{rec}", "*")):
            name = path.name[: -len(suffix)] if suffix else path.stem
            if name and name not in keep:
                entry(name).data_files.append(path)

    return [found[name] for name in sorted(found)]


def prune_recordings(
    stale: list[StaleRecording],
    *,
    data: bool = False,
    log: Callable[[str], None] = print,
) -> int:
    """Delete stale recordings' figures, and their data files if asked.

    Figures are removed by default because they are the misleading part — they
    show up in the output tree and the report as though they belonged to the
    analysis. The data files are kept unless ``data`` is set: they are what
    makes putting a recording *back* cheap, and they mislead nobody.

    Returns how many recordings were touched.
    """
    touched = 0
    for item in stale:
        removed = False
        for directory in item.figure_dirs:
            try:
                shutil.rmtree(directory)
                removed = True
            except OSError as e:
                log(f"  Could not remove {directory}: {e}")
        if data:
            for path in item.data_files:
                try:
                    path.unlink()
                    removed = True
                except OSError as e:
                    log(f"  Could not remove {path}: {e}")
        if removed:
            touched += 1
            log(f"  Removed {item.name}'s figures"
                + (" and data" if data else "")
                + " — it is no longer in the spreadsheet.")
    return touched


def report_stale(
    stale: list[StaleRecording], *, pruned: bool, log: Callable[[str], None],
) -> None:
    """Say what was found, in terms of what it means for the folder."""
    if not stale:
        return
    names = ", ".join(item.name for item in stale)
    log(f"{len(stale)} recording(s) in this folder are no longer in the "
        f"spreadsheet: {names}")
    if pruned:
        return
    figures = sum(item.n_figures for item in stale)
    if figures:
        log(f"  Their {figures} figure(s) are still on disk and will appear in "
            f"the output folder and report, though they are excluded from every "
            f"CSV and pooled statistic.")
        log("  Set Params.prune_removed_recordings = True to delete them.")
