"""Where CAT-NAP's *derived* per-recording files live.

suite2p's own outputs (``F.npy``, ``ops.npy``, …) are inputs: read-only, and
often not ours to modify. But denoising produces six more ``.npy`` files that
have always been written *into the same folder*, and :func:`load_suite2p` reads
them back from there. That is fine on a local copy and wrong everywhere else:

- a shared or archived dataset may be genuinely read-only;
- a remote source (a mounted or fetched Dropbox folder) either rejects the
  write or silently uploads ~48 MB per recording back to the remote;
- two runs with different denoising thresholds overwrite each other's outputs
  inside the *raw data*, which is the last place a re-runnable artefact should
  be.

So derived files get their own root, configured by
``Params.derived_data_folder``. Reads look in the derived location first and
fall back to the suite2p folder, so datasets that already carry in-folder
denoising outputs — every dataset produced before this change — keep working
untouched. Leaving the setting empty preserves the old behaviour exactly.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "DENOISING_OUTPUTS",
    "OPS_CACHE_NAME",
    "derived_dir",
    "resolve_read",
    "resolve_write_dir",
]

#: The files denoising produces. Named here rather than in ``denoising.py`` so
#: the loader and the writer agree on the set without importing each other.
DENOISING_OUTPUTS = (
    "Fdenoised.npy",
    "timePoints.npy",
    "peakStartFrames.npy",
    "peakEndFrames.npy",
    "peakHeights.npy",
    "eventAreas.npy",
)

#: Sidecar holding the two fields the pipeline needs out of ``ops.npy``.
OPS_CACHE_NAME = "ops_fields.npz"


def derived_dir(derived_root: str | Path | None, recording: str) -> Path | None:
    """Where this recording's derived files go, or ``None`` for "beside the inputs".

    One folder per recording under the root, mirroring how the raw data is
    organised, so a derived tree can be read alongside a raw one without a name
    map.
    """
    if not derived_root:
        return None
    return Path(derived_root) / recording / "plane0"


def resolve_write_dir(
    plane0: Path, derived_root: str | Path | None, recording: str,
) -> Path:
    """Directory to write derived files into, created if needed.

    Falls back to the suite2p folder when no derived root is configured — the
    behaviour every existing run has.
    """
    target = derived_dir(derived_root, recording)
    if target is None:
        return Path(plane0)
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_read(
    plane0: Path, derived_root: str | Path | None, recording: str, name: str,
) -> Path | None:
    """Locate one derived file: derived root first, then the suite2p folder.

    Derived-first matters when both exist — a dataset shipped with denoising
    outputs baked in, re-denoised locally at a different threshold, should use
    the local ones. Returns ``None`` when neither has it.
    """
    candidates = []
    target = derived_dir(derived_root, recording)
    if target is not None:
        candidates.append(target / name)
    candidates.append(Path(plane0) / name)
    for path in candidates:
        if path.exists():
            return path
    return None
