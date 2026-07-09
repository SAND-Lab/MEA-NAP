"""CAT-NAP figures.

Port of ``Functions/twoPhoton/plot2ptraces.m`` — the per-unit raw/denoised
trace figures saved during a run (the interactive GUI preview in
``gui/panels/catnap.py`` is separate). The spatial network plots reuse the
shared step-4 renderer via its ``coords_override`` path (see
``pipeline/plotting_step4.py``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from meanap.catnap.loader import Suite2pData


def plot_2p_traces(
    data: Suite2pData,
    out_dir: Path,
    recording_name: str,
    num_traces: int | str = 20,
) -> list[Path]:
    """Save a 3-panel raw/denoised trace figure per unit (``plot2ptraces.m``).

    Panels: (1) raw F, (2) min-max-scaled F over the denoised trace, (3) the
    denoised trace with detected event-start markers. Operates on the labelled
    (``iscell``) ROIs using their **original** 1-indexed ROI numbers, matching
    MATLAB's ``unit_<roi>_2ptraces`` naming — i.e. before any
    ``removeNodesWithNoPeaks`` subsetting.

    ``num_traces`` is ``'all'`` or an integer count. Unlike MATLAB (which
    ``randsample``s), we take the first ``num_traces`` labelled ROIs so the
    output is deterministic/reproducible.
    """
    if data.F_denoised is None or data.peak_start_frames is None:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    fs = float(data.fs)
    n_frames = data.F.shape[1]
    t = (np.arange(n_frames) + 1) / fs
    duration_s = t[-1]

    iscell_rois = np.nonzero(data.cell_mask)[0]  # 0-indexed ROI ids
    if isinstance(num_traces, str):
        selected = iscell_rois if num_traces == "all" else iscell_rois
    else:
        selected = iscell_rois[: max(0, int(num_traces))]

    saved: list[Path] = []
    for roi in selected:
        f_cell = data.F[roi]
        den_cell = data.F_denoised[roi]
        peak_frames = data.peak_start_frames[roi]
        peak_frames = peak_frames[~np.isnan(peak_frames)].astype(int)

        fig, axes = plt.subplots(3, 1, figsize=(7, 5.5), sharex=True)

        # 1: raw fluorescence
        axes[0].plot(t, f_cell, color="k", lw=1.5, label="Original")
        axes[0].set_title(f"{recording_name}  cell {roi + 1}", fontsize=9)
        axes[0].set_ylabel("Fluorescence")

        # 2: min-max-scaled raw over the denoised trace
        rng = f_cell.max() - f_cell.min()
        f_scaled = ((f_cell - f_cell.min()) / rng * den_cell.max()
                    if rng > 0 else np.zeros_like(f_cell))
        axes[1].plot(t, f_scaled, color="k", lw=1.5, label="Scaled")
        axes[1].plot(t, den_cell, color="r", lw=1.5, label="Denoised")
        axes[1].set_ylabel("Arbitrary units")

        # 3: denoised trace + event-start markers
        axes[2].plot(t, den_cell, color="r", lw=1.5, label="Denoised")
        if peak_frames.size:
            axes[2].scatter((peak_frames + 1) / fs, den_cell[peak_frames],
                            marker="x", color="b", zorder=5, label="Event start")
        axes[2].set_ylabel("Arbitrary units")
        axes[2].set_xlabel("Time (s)")

        for ax in axes:
            ax.set_xlim(0, duration_s)
            ax.spines[["top", "right"]].set_visible(False)
            ax.tick_params(direction="out")
            ax.legend(loc="upper right", fontsize=7, frameon=False)

        fig.tight_layout()
        out_path = out_dir / f"unit_{roi + 1}_2ptraces.png"
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        saved.append(out_path)

    return saved
