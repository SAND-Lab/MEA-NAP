"""Cross-day cell tracking for CAT-NAP.

Follows the same cells through a culture's DIVs by matching suite2p ROIs with
ROICaT, and says how much each match can be trusted.

Design and the evidence behind every constant here: ``python/CATNAP_CELLTRACKING_PLAN.md``.

The short version of what that document establishes, because it is what the
code below is shaped around:

* These recordings carry a **fixed-pattern stripe artifact bound to the
  detector**. ROICaT aligns on ``meanImgE``, so when the sample slides the
  stripes do not and its geometric step returns 0.000 px. Matching then happens
  on unregistered coordinates and collapses above a ~16 px offset.
* So we register first, from the **ROI footprints** (never the mean image), and
  then tell ROICaT not to register again -- its *non-rigid* step is not idle and
  will otherwise re-apply the offset we just removed.
* Only translation matters. Rotation, scale and non-rigid warping were measured
  and are absent.
* Matching is spatial, so it is validated with activity the matcher never saw.
"""

from meanap.catnap.tracking.chains import Chain, build_chains, parse_recording
from meanap.catnap.tracking.footprint import (
    DENSITY_BIN_PX,
    density_map,
    displacement,
)
from meanap.catnap.tracking.pipeline import (
    ChainResult,
    SessionSource,
    track_chain,
    track_dataset,
)
from meanap.catnap.tracking.register import (
    MIN_SHIFT_PX,
    RELIABLE_NCC,
    ChainOffsets,
    solve_offsets,
)
from meanap.catnap.tracking.validate import NEUCOEFF, auc_vs_null, fingerprints

__all__ = [
    "Chain",
    "ChainOffsets",
    "ChainResult",
    "DENSITY_BIN_PX",
    "MIN_SHIFT_PX",
    "NEUCOEFF",
    "RELIABLE_NCC",
    "SessionSource",
    "auc_vs_null",
    "build_chains",
    "density_map",
    "displacement",
    "fingerprints",
    "parse_recording",
    "solve_offsets",
    "track_chain",
    "track_dataset",
]
