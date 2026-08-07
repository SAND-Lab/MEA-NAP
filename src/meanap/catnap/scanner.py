"""Find the suite2p recordings in a data folder — or behind a share link.

The scan asks one question of every top-level folder: does it hold a
``suite2p/plane0/stat.npy``? Locally that is a stat call; over a share link it
is one folder listing, which returns names *and* sizes without transferring
anything. So the same walk works either way, and pointing the GUI at a Dropbox
link lists the same recordings a synced copy would — no download, and no second
code path that could disagree with the one a run uses.

What a remote scan cannot give you is a *path*: there is nothing on disk to
load traces from or write denoising output beside. Such a recording carries
``suite2p_dir=None`` and its store-relative :attr:`~Suite2pRecording.rel_path`
instead, and callers that need local bytes are expected to check
:attr:`~Suite2pRecording.is_remote` rather than discover it from a path that
stringifies to ``"None"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

#: Where suite2p puts its output inside a recording's folder.
SUITE2P_SUBDIR = "suite2p/plane0"

#: Present in every suite2p output, so its presence is what marks a recording.
STAT_FILE = "stat.npy"

#: Written by CAT-NAP's denoising step, not by suite2p.
DENOISED_FILE = "Fdenoised.npy"

#: Called with ``(folders_checked, folders_total)`` as a scan proceeds.
ProgressFn = Callable[[int, int], None]

__all__ = [
    "Suite2pRecording", "find_suite2p_recordings", "scan_store",
    "SUITE2P_SUBDIR",
]


@dataclass
class Suite2pRecording:
    """A discovered suite2p recording."""

    name: str                    # top-level folder name (the recording name)
    suite2p_dir: Path | None     # local suite2p/plane0, or None if not on disk
    has_denoised: bool           # whether Fdenoised.npy already exists
    rel_path: str = ""           # "<name>/suite2p/plane0" within its source

    @property
    def is_remote(self) -> bool:
        """Whether the data still has to be fetched to be read."""
        return self.suite2p_dir is None


def find_suite2p_recordings(
    root: str | Path, *, progress: ProgressFn | None = None,
) -> list[Suite2pRecording]:
    """Every recording under *root* that has ``suite2p/plane0/stat.npy``.

    *root* is a local folder or a Dropbox folder share link. Mirrors the logic
    in ``appCheckSuite2pData.m``. A root that is neither a readable folder nor a
    usable link yields an empty list; a link that *is* well-formed but fails to
    read raises, since "the folder looks empty" and "the request failed" must
    not be reported the same way.
    """
    from meanap.params import is_remote_url

    if is_remote_url(str(root)):
        from meanap.remote import store_for
        return scan_store(store_for(str(root)), progress=progress)

    root = Path(root)
    if not root.is_dir():
        return []
    return _scan_local(root, progress=progress)


def _scan_local(root: Path, progress: ProgressFn | None = None) -> list[Suite2pRecording]:
    """The filesystem walk: two stat calls per folder, no listing of plane0."""
    folders = [c for c in sorted(root.iterdir()) if c.is_dir()]
    recordings: list[Suite2pRecording] = []

    for i, child in enumerate(folders):
        if progress is not None:
            progress(i, len(folders))
        plane0 = child / "suite2p" / "plane0"
        if (plane0 / STAT_FILE).exists():
            recordings.append(Suite2pRecording(
                name=child.name,
                suite2p_dir=plane0,
                has_denoised=(plane0 / DENOISED_FILE).exists(),
                rel_path=f"{child.name}/{SUITE2P_SUBDIR}",
            ))

    if progress is not None:
        progress(len(folders), len(folders))
    return recordings


def scan_store(store, *, progress: ProgressFn | None = None) -> list[Suite2pRecording]:
    """The same scan over any :class:`~meanap.remote.base.RemoteStore`.

    Costs one folder listing per candidate, which against a share link is one
    HTTP request each — hence *progress*, so a scan of a hundred-folder dataset
    can say how far it has got rather than appearing to hang.
    """
    # A LocalStore knows where it is, so recordings found through one stay
    # loadable. Only a store with no local root produces remote recordings.
    local_root = getattr(store, "root", None)

    folders = sorted((e for e in store.list() if e.is_dir), key=lambda e: e.name)
    recordings: list[Suite2pRecording] = []

    for i, folder in enumerate(folders):
        if progress is not None:
            progress(i, len(folders))
        rel = f"{folder.path}/{SUITE2P_SUBDIR}"
        names = {e.name for e in store.list(rel) if not e.is_dir}
        if STAT_FILE in names:
            recordings.append(Suite2pRecording(
                name=folder.name,
                suite2p_dir=Path(local_root) / rel if local_root else None,
                has_denoised=DENOISED_FILE in names,
                rel_path=rel,
            ))

    if progress is not None:
        progress(len(folders), len(folders))
    return recordings
