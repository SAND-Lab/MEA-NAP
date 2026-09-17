"""Where tracking reads ROIs, mean images and traces from.

The pipeline talks to a :class:`~meanap.catnap.tracking.pipeline.SessionSource`
rather than to the disk, so a run can track a local suite2p tree, a derived-data
root, or a share link without knowing which. This module supplies the local
implementation and the trace loading that validation needs.

Two things are loaded from different places on purpose. ROIs and the mean image
come from the **suite2p** folder, because that is where ``stat.npy`` lives.
Denoising outputs may have been written to a **derived root** instead, to keep
the raw data read-only, so those are resolved through
:mod:`meanap.catnap.derived`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from meanap.catnap.tracking.validate import NEUCOEFF, correct_neuropil


@dataclass
class LocalSessionSource:
    """Read a recording's ROIs, mean image and traces from a suite2p tree.

    Give it a :class:`~meanap.remote.source.RecordingSource` and it works
    against a remote dataset too: that class's ``plane0()`` materialises the
    files locally, fetching them if needed, so everything below is unchanged.
    Without one it resolves ``raw_data`` directly.
    """

    raw_data: Path
    derived_root: Path | None = None
    #: Optional. When set, file access goes through it rather than ``raw_data``.
    source: object | None = None
    #: Recordings that fell back to ``Fdenoised`` because F/Fneu were missing.
    #: Worth surfacing rather than silently mixing corrected and uncorrected
    #: traces within one run.
    uncorrected: set = field(default_factory=set)

    def plane0(self, recording: str) -> Path:
        if self.source is not None:
            return Path(self.source.plane0(recording))
        return Path(self.raw_data) / recording / "suite2p" / "plane0"

    def release(self, recording: str) -> None:
        """Let a remote source drop a recording's cached files.

        A chain holds several recordings open at once, so releasing has to wait
        until the chain is done rather than happen per file.
        """
        if self.source is None:
            return
        for method in ("unpin", "release"):
            fn = getattr(self.source, method, None)
            if fn is not None:
                fn(recording)

    def _iscell(self, recording: str) -> np.ndarray:
        return np.load(self.plane0(recording) / "iscell.npy")[:, 0].astype(bool)

    def stat(self, recording: str) -> np.ndarray:
        """ROIs, **filtered to iscell**.

        Filtering here rather than at the call site is deliberate: handing
        ROICaT the unfiltered array is the single most damaging mistake
        available, dropping tracking yield from 45% to 6%, and it fails
        silently.
        """
        stat = np.load(self.plane0(recording) / "stat.npy", allow_pickle=True)
        iscell = self._iscell(recording)
        if len(stat) != len(iscell):
            raise ValueError(
                f"{recording}: stat has {len(stat)} ROIs, iscell has {len(iscell)}")
        return stat[iscell]

    def mean_image(self, recording: str) -> np.ndarray:
        ops = np.load(self.plane0(recording) / "ops.npy", allow_pickle=True).item()
        for key in ("meanImgE", "meanImg"):
            if key in ops:
                return np.asarray(ops[key])
        raise KeyError(f"{recording}: ops.npy has no mean image")

    def frame_px(self, recording: str) -> int:
        ops = np.load(self.plane0(recording) / "ops.npy", allow_pickle=True).item()
        return int(max(ops.get("Ly", 0), ops.get("Lx", 0)) or
                   self.mean_image(recording).shape[0])

    # ── validation inputs ─────────────────────────────────────────────────────

    def traces(self, recording: str, *, neucoeff: float = NEUCOEFF
               ) -> tuple[np.ndarray, float]:
        """Neuropil-corrected traces for the iscell ROIs, and the frame rate.

        ``F - neucoeff * Fneu`` when both raw arrays are present, which is
        suite2p's convention and what validation should use. Falls back to
        ``Fdenoised`` when they are not — note that file is built from
        *uncorrected* F, and a silent cell used to come back as NaN there
        (see ``denoising._deconvolve_trace``).
        """
        from meanap.catnap.derived import resolve_read

        plane = self.plane0(recording)
        iscell = self._iscell(recording)
        fs = self.frame_rate(recording)

        f_path, fneu_path = plane / "F.npy", plane / "Fneu.npy"
        if f_path.exists() and fneu_path.exists():
            F = np.load(f_path)[iscell]
            Fneu = np.load(fneu_path)[iscell]
            return correct_neuropil(F, Fneu, neucoeff=neucoeff), fs

        denoised = resolve_read(plane, self.derived_root, recording, "Fdenoised.npy")
        if denoised is None:
            raise FileNotFoundError(f"{recording}: no F/Fneu and no Fdenoised")
        self.uncorrected.add(recording)
        return np.load(denoised)[iscell], fs

    def frame_rate(self, recording: str) -> float:
        ops = np.load(self.plane0(recording) / "ops.npy", allow_pickle=True).item()
        return float(ops.get("fs", 0.0)) or 1.0

    def peak_starts(self, recording: str) -> np.ndarray | None:
        from meanap.catnap.derived import resolve_read

        path = resolve_read(self.plane0(recording), self.derived_root, recording,
                            "peakStartFrames.npy")
        if path is None:
            return None
        return np.load(path)[self._iscell(recording)]
