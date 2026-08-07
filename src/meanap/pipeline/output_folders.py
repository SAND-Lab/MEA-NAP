"""Create the MEA-NAP output folder tree, mirroring ``CreateOutputFolders.m``.

Also decides *where* that tree goes. The default folder name is today's date,
so a second run on the same day lands exactly on the first one and — until this
— overwrote it silently, results, figures, bundle and all. Naming a run
``…_v2`` instead costs nothing and is trivially undone; the overwrite is not.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

#: Appended, with an increasing number, when a name is taken: ``…_v2``, ``…_v3``.
#: The first run carries no suffix, so the second is *_v2* — calling it *_v1*
#: would suggest the run before it was something else.
_VERSION_RE = re.compile(r"^(?P<stem>.*)_v(?P<n>\d+)$")

#: After this many versions, fall back to a timestamp. A folder with a hundred
#: same-named runs beside it is not a naming problem any more, and a
#: hundred-deep scan on every launch is not worth paying for.
MAX_VERSIONS = 99

# Relative to <output_data_folder>/<output_data_folder_name>
_RELATIVE_FOLDERS = [
    "ExperimentMatFiles",
    "1_SpikeDetection",
    "1_SpikeDetection/1A_SpikeDetectedData",
    "1_SpikeDetection/1B_SpikeDetectionChecks",
    "2_NeuronalActivity",
    "2_NeuronalActivity/2A_IndividualNeuronalAnalysis",
    "2_NeuronalActivity/2B_GroupComparisons",
    "2_NeuronalActivity/2B_GroupComparisons/1_NodeByGroup",
    "2_NeuronalActivity/2B_GroupComparisons/2_NodeByAge",
    "2_NeuronalActivity/2B_GroupComparisons/3_RecordingsByGroup",
    "2_NeuronalActivity/2B_GroupComparisons/3_RecordingsByGroup/HalfViolinPlots",
    "2_NeuronalActivity/2B_GroupComparisons/4_RecordingsByAge",
    "2_NeuronalActivity/2B_GroupComparisons/4_RecordingsByAge/HalfViolinPlots",
    "3_EdgeThresholdingCheck",
    "4_NetworkActivity",
    "4_NetworkActivity/4A_IndividualNetworkAnalysis",
    "4_NetworkActivity/4B_GroupComparisons",
    "4_NetworkActivity/4B_GroupComparisons/1_NodeByGroup",
    "4_NetworkActivity/4B_GroupComparisons/2_NodeByAge",
    "4_NetworkActivity/4B_GroupComparisons/3_RecordingsByGroup",
    "4_NetworkActivity/4B_GroupComparisons/3_RecordingsByGroup/HalfViolinPlots",
    "4_NetworkActivity/4B_GroupComparisons/4_RecordingsByAge",
    "4_NetworkActivity/4B_GroupComparisons/4_RecordingsByAge/HalfViolinPlots",
    "4_NetworkActivity/4B_GroupComparisons/5_GraphMetricsByLag",
    "4_NetworkActivity/4B_GroupComparisons/6_NodeCartographyByLag",
    "4_NetworkActivity/4B_GroupComparisons/7_DensityLandscape",
]

# Mirrors the (root-level, missing "2_NeuronalActivity" prefix) paths used by
# CreateOutputFolders.m when Params.includeNotBoxPlots is set.
_NOT_BOX_PLOT_FOLDERS = [
    "2B_GroupComparisons/3_RecordingsByGroup/NotBoxPlots",
    "2B_GroupComparisons/4_RecordingsByAge/NotBoxPlots",
]


def output_paths_for(parent: Path | str, name: str) -> tuple[Path, Path]:
    """The folder a run writes, and the bundle that lands beside it.

    ``with_suffix`` rather than appending, because that is what
    :func:`~meanap.pipeline.bundle.write_bundle` actually does — a check that
    guessed a different filename would protect the wrong file.
    """
    from meanap.pipeline.bundle import BUNDLE_SUFFIX

    folder = Path(parent) / name
    return folder, folder.with_suffix(BUNDLE_SUFFIX)


def output_name_taken(parent: Path | str, name: str) -> bool:
    """Whether a run under *name* already exists — as a folder or as a bundle.

    The bundle counts on its own. An express run's whole point is that the
    ``.meanap`` is the artefact worth keeping, so its output folder is often
    deleted once the file is in hand; checking only for the folder would let the
    next run of the day overwrite the one thing that survived.

    An empty folder does not count. A run that died after creating its tree
    leaves one behind, and renaming the retry would be noise.
    """
    folder, bundle = output_paths_for(parent, name)
    if bundle.exists():
        return True
    if not folder.is_dir():
        return False
    return any(p.is_file() for p in folder.rglob("*"))


def next_free_output_name(
    parent: Path | str, name: str, *, now: datetime.datetime | None = None,
) -> str:
    """*name* if nothing is there, else the first free ``name_v2``, ``name_v3``, …

    Re-running from an already-versioned name counts on from it rather than
    stacking suffixes, so a third run is ``…_v3`` and never ``…_v2_v2``.
    """
    if not output_name_taken(parent, name):
        return name

    match = _VERSION_RE.match(name)
    stem = match.group("stem") if match else name
    start = int(match.group("n")) + 1 if match else 2

    for n in range(start, start + MAX_VERSIONS):
        candidate = f"{stem}_v{n}"
        if not output_name_taken(parent, candidate):
            return candidate

    stamp = (now or datetime.datetime.now()).strftime("%H%M%S")
    return f"{stem}_{stamp}"


def create_output_folders(
    output_data_folder: Path | str,
    output_data_folder_name: str,
    group_names: list[str],
    include_not_box_plots: bool = False,
) -> Path:
    """Create the MEA-NAP output folder structure and return its root path.

    Root path is ``output_data_folder/output_data_folder_name``. One
    ``4_NetworkActivity/4A_IndividualNetworkAnalysis/<group>`` folder is created
    per entry in ``group_names``.
    """
    root = Path(output_data_folder) / output_data_folder_name
    root.mkdir(parents=True, exist_ok=True)

    for rel in _RELATIVE_FOLDERS:
        (root / rel).mkdir(parents=True, exist_ok=True)

    for group in group_names:
        (root / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis" / group).mkdir(
            parents=True, exist_ok=True
        )

    if include_not_box_plots:
        for rel in _NOT_BOX_PLOT_FOLDERS:
            (root / rel).mkdir(parents=True, exist_ok=True)

    return root
