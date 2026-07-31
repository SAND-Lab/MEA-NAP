"""Resuming a run from a previous analysis (``Params.prior_analysis``).

MATLAB's ``MEApipeline.m`` lets you skip already-completed work: set
``Params.priorAnalysis = 1``, point ``Params.priorAnalysisPath`` at an earlier
``OutputData…`` folder and ``Params.startAnalysisStep`` at the step to resume
from. Results still go to a *fresh* output folder — the prior run is only ever
read — which is the behaviour mirrored here.

Because this port writes discrete per-recording files rather than MATLAB's one
chained ``.mat`` per recording, resuming reduces to a search path. Only two
artefacts cross step boundaries:

===========================  ================================================
Step 1 → Steps 2, 3, 4       ``1_SpikeDetection/1A_SpikeDetectedData/<rec>_spikes.npz``
Step 3 → Step 4              ``ExperimentMatFiles/<rec>_adjM.npz``
===========================  ================================================

:class:`InputLocator` resolves those two lookups against, in order:

1. **this run's output folder** — so a step that just ran always wins;
2. **``Params.spike_detected_data``** (spike files only) — an explicit
   externally-detected-spikes folder, MATLAB's ``spikeDetectedData``;
3. **``Params.prior_analysis_path``** — the previous run.

Order 1-before-2 matters only in theory (the output folder is created fresh per
run, so it holds nothing but this run's own results) but it keeps the rule
simple to state: *nothing already produced this run is ever shadowed by an
older file.*

The class is a frozen dataclass of plain paths so it pickles cleanly into the
``spawn``ed worker processes Steps 3 and 4 use.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meanap.params import Params
from meanap.pipeline.spreadsheet import RecordingInfo

__all__ = [
    "InputLocator",
    "build_input_locator",
    "missing_step_inputs",
    "SPIKE_SUBDIR",
    "ADJM_SUBDIR",
]

SPIKE_SUBDIR = Path("1_SpikeDetection") / "1A_SpikeDetectedData"
ADJM_SUBDIR = Path("ExperimentMatFiles")


@dataclass(frozen=True)
class InputLocator:
    """Where each step should look for the outputs of the steps before it."""

    output_root: Path
    prior_root: Path | None = None
    spike_dir: Path | None = None

    # ── lookups ──────────────────────────────────────────────────────────────

    def spike_file(self, recording_name: str) -> Path | None:
        """Path to a recording's Step-1 spike file, or ``None`` if absent."""
        name = f"{recording_name}_spikes.npz"
        candidates = [self.output_root / SPIKE_SUBDIR / name]
        if self.spike_dir is not None:
            candidates.append(self.spike_dir / name)
        if self.prior_root is not None:
            candidates.append(self.prior_root / SPIKE_SUBDIR / name)
        return _first_existing(candidates)

    def adjm_file(self, recording_name: str) -> Path | None:
        """Path to a recording's Step-3 adjacency file, or ``None`` if absent."""
        name = f"{recording_name}_adjM.npz"
        candidates = [self.output_root / ADJM_SUBDIR / name]
        if self.prior_root is not None:
            candidates.append(self.prior_root / ADJM_SUBDIR / name)
        return _first_existing(candidates)

    # ── reporting ────────────────────────────────────────────────────────────

    @property
    def is_resuming(self) -> bool:
        return self.prior_root is not None or self.spike_dir is not None

    def describe(self) -> list[str]:
        """Human-readable lines describing the search path, for the run log."""
        lines = [f"Reading step inputs from: {self.output_root}"]
        if self.spike_dir is not None:
            lines.append(f"  … then spike data from: {self.spike_dir}")
        if self.prior_root is not None:
            lines.append(f"  … then prior analysis:  {self.prior_root}")
        return lines


def _first_existing(candidates: list[Path]) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def build_input_locator(params: Params, output_root: Path) -> InputLocator:
    """Build the locator for a run, validating the configured paths up front.

    Raises :class:`ValueError` with an actionable message rather than letting a
    typo'd path degrade into "every recording skipped", which is how a missing
    input used to present.
    """
    prior_root: Path | None = None
    if params.prior_analysis:
        if not params.prior_analysis_path:
            raise ValueError(
                "'Use prior analysis' is enabled but no previous analysis folder is set. "
                "Set Params.prior_analysis_path to a previous OutputData… folder, or "
                "disable prior analysis."
            )
        prior_root = Path(params.prior_analysis_path).expanduser()
        if not prior_root.is_dir():
            raise ValueError(f"Previous analysis folder does not exist: {prior_root}")
        if not (prior_root / SPIKE_SUBDIR).is_dir() and not (prior_root / ADJM_SUBDIR).is_dir():
            raise ValueError(
                f"{prior_root} does not look like a MEA-NAP output folder — expected it to "
                f"contain '{SPIKE_SUBDIR}' and/or '{ADJM_SUBDIR}'. Point this at the "
                "OutputData… folder itself, not at its parent."
            )

    spike_dir: Path | None = None
    if params.spike_detected_data:
        spike_dir = Path(params.spike_detected_data).expanduser()
        if not spike_dir.is_dir():
            raise ValueError(f"Spike-detected data folder does not exist: {spike_dir}")

    return InputLocator(
        output_root=Path(output_root), prior_root=prior_root, spike_dir=spike_dir
    )


def missing_step_inputs(
    locator: InputLocator,
    recordings: list[RecordingInfo],
    start_step: int,
) -> dict[str, list[str]]:
    """Which recordings lack the inputs the *starting* step needs.

    Only the starting step is checked: later steps consume what earlier ones
    produce during this run. Returns ``{recording_name: [missing artefact, …]}``
    for recordings that would be skipped, so the caller can fail fast (nothing
    resolvable) or warn (only some missing).
    """
    missing: dict[str, list[str]] = {}
    for rec in recordings:
        gaps: list[str] = []
        if start_step >= 2 and locator.spike_file(rec.filename) is None:
            gaps.append("spike times (step 1)")
        if start_step >= 4 and locator.adjm_file(rec.filename) is None:
            gaps.append("adjacency matrices (step 3)")
        if gaps:
            missing[rec.filename] = gaps
    return missing
