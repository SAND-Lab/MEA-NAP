"""Run ROICaT over a pre-registered chain.

Everything here is a settled parameter choice rather than a default, and each
one has a measurement behind it.

**Both registration steps are disabled.** ``fit_geometric`` is pinned at
(0, 0) by the stripe artifact anyway, but ``fit_nonrigid`` is *not* idle -- it
applies real ~19 px corrections and on some chains was silently doing the whole
job. Left enabled after pre-registration it re-derives the offset from the
(unshifted) mean image and re-applies it, which took the best chain in the Mecp2
dataset from 0.740 to 0.015. Registration happens once, in ``register.py``.

**Only ``meanImgE`` is read from ``ops.npy``**, so a minimal ops built from the
sidecar is enough and the real 462 MB ``ops.npy`` is never needed. That is what
makes a full-dataset run affordable.

**ROICaT's learned appearance features are near-useless on this data** --
suite2p ROIs here have a median of 13 px and are ~4 px across, far smaller than
ROInet was trained for -- so matching is driven by spatial footprint. Which is
exactly why ``validate.py`` exists: a spatial matcher cannot tell "the same
cell" from "a different cell in the same place", and neither can a spatial
control.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np

#: The identity control's match rate is session-specific and must be measured,
#: not assumed: a 53-ROI session scored 0.849 and a 142-ROI session 1.000. Do
#: not normalise match rates by a constant "ceiling".
UM_PER_PIXEL = 1.5


def build_params(chain_dir: Path, save_dir: Path, name: str,
                 *, pre_registered: bool, n_dataloader_workers: int = 2) -> dict:
    """ROICaT tracking parameters.

    ``pre_registered`` says whether ``register.py`` already aligned this chain.
    It decides who registers, and **exactly one of us must**:

    * pre-registered -- disable both of ROICaT's steps. Its non-rigid step is
      driven by the (unshifted) mean image and would re-apply the offset we just
      removed, which took one chain from 0.740 to 0.015.
    * passed through (offset below the gate) -- leave them enabled. We
      deliberately did not register, so ROICaT's non-rigid step is the only
      correction available, and it is not idle: disabling it here dropped a
      chain's best pair from 0.36 to 0.06.
    """
    from roicat import util

    params = util.get_default_parameters(pipeline="tracking")
    params["general"]["use_GPU"] = False
    params["general"]["random_seed"] = 0
    params["data_loading"]["dir_outer"] = str(chain_dir)
    params["data_loading"]["common"]["um_per_pixel"] = UM_PER_PIXEL

    if pre_registered:
        # These ROIs are registered. Anything ROICaT does now can only undo it.
        params["alignment"]["fit_geometric"]["method"] = "NullRegistration"
        params["alignment"]["fit_nonrigid"]["method"] = "NullRegistration"
    else:
        # Phase correlation and Farneback need no model download, unlike the
        # RoMa/DeepFlow defaults. Both are translation-only, which is all this
        # data needs: rotation and scale were measured and gain 0.0000.
        params["alignment"]["fit_geometric"]["method"] = "PhaseCorrelation"
        params["alignment"]["fit_nonrigid"]["method"] = "OpticalFlowFarneback"

    params["ROInet"]["dataloader"]["numWorkers_dataloader"] = n_dataloader_workers
    params["results_saving"]["dir_save"] = str(save_dir)
    params["results_saving"]["prefix_name_save"] = name
    return params


def stage_session(dest: Path, stat: np.ndarray, mean_img: np.ndarray,
                  height: int, width: int) -> None:
    """Write one session in the layout ROICaT's loader expects.

    The mean image keeps a **shared origin** across sessions rather than moving
    with the ROIs. With registration disabled nothing reads it for alignment, and
    shifting it would only matter if something did -- at which point the stripes
    would move with it and mislead whatever was looking.
    """
    dest.mkdir(parents=True, exist_ok=True)
    np.save(dest / "stat.npy", stat, allow_pickle=True)
    canvas = np.full((height, width), float(np.median(mean_img)), dtype=mean_img.dtype)
    h = min(mean_img.shape[0], height)
    w = min(mean_img.shape[1], width)
    canvas[:h, :w] = mean_img[:h, :w]
    np.save(dest / "ops.npy",
            {"meanImgE": canvas, "meanImg": canvas, "Ly": height, "Lx": width},
            allow_pickle=True)


def run_chain(chain_dir: Path, save_dir: Path, name: str,
              *, pre_registered: bool, n_dataloader_workers: int = 2) -> dict:
    """Run ROICaT and return its per-session cluster labels.

    ROICaT also writes a ``run_data.richfile.zip`` holding its whole internal
    state -- ~400 MB per chain, and nothing downstream reads it. It is deleted
    here; 94 chains of it came to 109 GB.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from roicat import pipelines, tracking

    # A chain with no matches can end with one cluster or none, and ROICaT's
    # quality-metrics plot then crashes on a None silhouette. The figure is not
    # used, so stub it rather than lose the chain.
    tracking.clustering.plot_quality_metrics = lambda *a, **k: (plt.figure(), None)

    params = build_params(chain_dir, save_dir, name,
                          pre_registered=pre_registered,
                          n_dataloader_workers=n_dataloader_workers)
    results, _run_data, _params = pipelines.pipeline_tracking(params)

    for leftover in save_dir.glob("**/*run_data.richfile.zip"):
        leftover.unlink()

    by_session = results["clusters"].get("labels_bySession") or []
    return {"labels_bySession": [np.asarray(s, dtype=int).tolist()
                                 for s in by_session]}


def match_rates(labels: list[np.ndarray], divs: list[int]) -> dict:
    """Per-session tracked fraction and per-day-pair shared-cluster counts.

    ``frac_of_smaller`` divides by the smaller session's cell count, so a pair
    that puts a large session against a small one has an inflated denominator
    sensitivity -- the false-positive floor is worst exactly there.
    """
    sets = [set(int(x) for x in s if x >= 0) for s in labels]
    n_roi = [int(np.asarray(s).size) for s in labels]
    span: dict[int, int] = {}
    for s in sets:
        for cid in s:
            span[cid] = span.get(cid, 0) + 1

    frac = [
        round(sum(1 for x in s if x >= 0 and span.get(int(x), 0) >= 2) / max(len(s), 1), 3)
        for s in labels
    ]
    pairwise = {}
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            shared = len(sets[i] & sets[j])
            pairwise[f"DIV{divs[i]}-DIV{divs[j]}"] = {
                "shared": shared,
                "frac_of_smaller": round(shared / (min(n_roi[i], n_roi[j]) or 1), 3),
                "div_gap": divs[j] - divs[i],
            }
    return {"n_roi": n_roi, "frac_tracked": frac, "pairwise": pairwise}
