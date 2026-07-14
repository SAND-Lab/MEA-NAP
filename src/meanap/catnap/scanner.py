"""Scan a data folder for suite2p recordings."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Suite2pRecording:
    """A discovered suite2p recording."""
    name: str               # top-level folder name (the recording name)
    suite2p_dir: Path       # path to the suite2p/plane0 directory
    has_denoised: bool      # whether Fdenoised.npy already exists


def find_suite2p_recordings(root: str | Path) -> list[Suite2pRecording]:
    """
    Walk *root* and return every sub-folder that contains suite2p/plane0/stat.npy.
    Mirrors the logic in appCheckSuite2pData.m.
    """
    root = Path(root)
    recordings: list[Suite2pRecording] = []

    if not root.is_dir():
        return recordings

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        plane0 = child / "suite2p" / "plane0"
        if (plane0 / "stat.npy").exists():
            recordings.append(Suite2pRecording(
                name=child.name,
                suite2p_dir=plane0,
                has_denoised=(plane0 / "Fdenoised.npy").exists(),
            ))

    return recordings
