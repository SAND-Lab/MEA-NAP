"""Create the MEA-NAP output folder tree, mirroring ``CreateOutputFolders.m``."""

from __future__ import annotations

from pathlib import Path

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
