"""Resuming a run from a previous analysis (``Params.prior_analysis``).

MATLAB's ``MEApipeline.m`` lets you skip already-completed work: set
``Params.priorAnalysis = 1``, point ``Params.priorAnalysisPath`` at an earlier
``OutputData…`` folder and ``Params.startAnalysisStep`` at the step to resume
from. Results still go to a *fresh* output folder — the prior run is only ever
read — which is the behaviour mirrored here.

Because this port writes discrete per-recording files rather than MATLAB's one
chained ``.mat`` per recording, resuming reduces to a search path. Only three
artefacts cross step boundaries:

===========================  ================================================
Step 1 → Steps 2, 3, 4       ``1_SpikeDetection/1A_SpikeDetectedData/<rec>_spikes.npz``
Step 3 → Step 4              ``ExperimentMatFiles/<rec>_adjM.npz``
CAT-NAP step 2 → step 4      ``ExperimentMatFiles/<rec>_catnap.npz``
===========================  ================================================

The CAT-NAP (``suite2pMode``) path has no step 1 or 3 — adjacency is built in
step 2, as it is in MATLAB — so step 4 is its only resumable boundary. Its file
is deliberately named differently from the ephys ``_adjM.npz``: the two hold
different things, and pointing a CAT-NAP resume at an ephys output folder (or
the reverse) should report a missing input rather than fail deep inside a load.

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
    "CATNAP_SUFFIX",
    "ADJM_SUFFIX",
]

SPIKE_SUBDIR = Path("1_SpikeDetection") / "1A_SpikeDetectedData"
ADJM_SUBDIR = Path("ExperimentMatFiles")
#: Per-recording array files inside :data:`ADJM_SUBDIR`. Both suffixes are
#: owned here rather than by the pipelines that write them, so this module
#: stays the single place describing the output layout.
ADJM_SUFFIX = "_adjM.npz"       # electrophysiology, step 3
CATNAP_SUFFIX = "_catnap.npz"   # CAT-NAP, step 2


@dataclass(frozen=True)
class InputLocator:
    """Where each step should look for the outputs of the steps before it."""

    output_root: Path
    #: Previous runs to read from, in order. More than one lets a spreadsheet
    #: name recordings analysed in *different* runs and have them come out as
    #: one batch — see ``Params.prior_analysis_paths``. A tuple because this is
    #: frozen and gets pickled into spawned workers.
    prior_roots: tuple[Path, ...] = ()
    spike_dir: Path | None = None

    @property
    def prior_root(self) -> Path | None:
        """The first prior run, for callers that only ever expected one."""
        return self.prior_roots[0] if self.prior_roots else None

    # ── lookups ──────────────────────────────────────────────────────────────

    def spike_file(self, recording_name: str) -> Path | None:
        """Path to a recording's Step-1 spike file, or ``None`` if absent."""
        name = f"{recording_name}_spikes.npz"
        candidates = [self.output_root / SPIKE_SUBDIR / name]
        if self.spike_dir is not None:
            candidates.append(self.spike_dir / name)
        candidates += [root / SPIKE_SUBDIR / name for root in self.prior_roots]
        return _first_existing(candidates)

    def adjm_file(self, recording_name: str) -> Path | None:
        """Path to a recording's Step-3 adjacency file, or ``None`` if absent."""
        name = f"{recording_name}{ADJM_SUFFIX}"
        candidates = [self.output_root / ADJM_SUBDIR / name]
        candidates += [root / ADJM_SUBDIR / name for root in self.prior_roots]
        return _first_existing(candidates)

    def catnap_file(self, recording_name: str) -> Path | None:
        """Path to a recording's CAT-NAP step-2 file, or ``None`` if absent.

        ``spike_dir`` is not consulted: it holds externally *spike-detected*
        MEA data, which has nothing to say about a suite2p recording.
        """
        name = f"{recording_name}{CATNAP_SUFFIX}"
        candidates = [self.output_root / ADJM_SUBDIR / name]
        candidates += [root / ADJM_SUBDIR / name for root in self.prior_roots]
        return _first_existing(candidates)

    # ── reporting ────────────────────────────────────────────────────────────

    @property
    def is_resuming(self) -> bool:
        return bool(self.prior_roots) or self.spike_dir is not None

    def describe(self) -> list[str]:
        """Human-readable lines describing the search path, for the run log."""
        lines = [f"Reading step inputs from: {self.output_root}"]
        if self.spike_dir is not None:
            lines.append(f"  … then spike data from: {self.spike_dir}")
        # Numbered only when there is more than one to distinguish — the
        # ordinary single-folder case reads better without an index on it.
        multiple = len(self.prior_roots) > 1
        for i, root in enumerate(self.prior_roots, start=1):
            label = f"prior analysis {i}:" if multiple else "prior analysis: "
            lines.append(f"  … then {label} {root}")
        return lines


def _first_existing(candidates: list[Path]) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


#: Bundles unpacked this process, keyed by source path. Held for the process
#: lifetime because :class:`InputLocator` is a plain-paths dataclass that gets
#: pickled into spawned workers — the extracted directory has to outlive the
#: locator, and re-unpacking per worker would be both slower and a different
#: path in each one.
_UNPACKED_BUNDLES: dict[Path, Path] = {}


def _unpack_prior_bundle(path: Path) -> Path:
    """Resolve a ``.meanap`` prior-analysis path to the folder it unpacks to."""
    from meanap.pipeline.bundle import BUNDLE_SUFFIX, open_bundle

    resolved = path.resolve()
    if resolved in _UNPACKED_BUNDLES:
        return _UNPACKED_BUNDLES[resolved]
    if resolved.suffix != BUNDLE_SUFFIX:
        raise ValueError(
            f"Previous analysis path is a file, not a folder: {resolved}. Point it "
            f"at an OutputData… folder or a '{BUNDLE_SUFFIX}' bundle."
        )
    # Deliberately not closed: the run reads from it throughout, and the OS
    # reclaims the temp directory. Bundles are ~1 MB.
    bundle = open_bundle(resolved)
    _UNPACKED_BUNDLES[resolved] = bundle.root
    return bundle.root


def _resolve_prior(entry: str) -> Path:
    """One previous-analysis path, validated and unpacked if it is a bundle."""
    root = Path(entry).expanduser()
    # A ``.meanap`` bundle is an output folder in a zip, so resuming from one is
    # just resuming from where it unpacks to — no lookup needs to know the
    # difference. This is what lets the file you share double as the file you
    # re-run from.
    if root.is_file():
        root = _unpack_prior_bundle(root)
    if not root.is_dir():
        raise ValueError(f"Previous analysis folder does not exist: {root}")
    if not (root / SPIKE_SUBDIR).is_dir() and not (root / ADJM_SUBDIR).is_dir():
        raise ValueError(
            f"{root} does not look like a MEA-NAP output folder — expected it to "
            f"contain '{SPIKE_SUBDIR}' and/or '{ADJM_SUBDIR}'. Point this at the "
            "OutputData… folder itself, not at its parent."
        )
    return root


def build_input_locator(params: Params, output_root: Path) -> InputLocator:
    """Build the locator for a run, validating the configured paths up front.

    Raises :class:`ValueError` with an actionable message rather than letting a
    typo'd path degrade into "every recording skipped", which is how a missing
    input used to present.
    """
    prior_roots: list[Path] = []
    if params.prior_analysis:
        configured = [params.prior_analysis_path, *params.prior_analysis_paths]
        configured = [c for c in configured if c]
        if not configured:
            raise ValueError(
                "'Use prior analysis' is enabled but no previous analysis folder is set. "
                "Set Params.prior_analysis_path to a previous OutputData… folder, or "
                "disable prior analysis."
            )
        for entry in configured:
            prior_roots.append(_resolve_prior(entry))

    spike_dir: Path | None = None
    if params.spike_detected_data:
        spike_dir = Path(params.spike_detected_data).expanduser()
        if not spike_dir.is_dir():
            raise ValueError(f"Spike-detected data folder does not exist: {spike_dir}")

    return InputLocator(
        output_root=Path(output_root), prior_roots=tuple(prior_roots),
        spike_dir=spike_dir,
    )


def already_done(
    params: Params, output_root: Path, artefact: Path, log=None,
) -> bool:
    """Whether this recording's result for the current step is already there.

    Only true when the run was asked to continue an interrupted one. The file
    must be in *this* output folder, not in a prior run's — continuing means
    filling the gaps in one folder, while a prior-analysis resume deliberately
    reads an older run and writes somewhere new.

    An artefact that will not open is deleted and reported rather than trusted:
    writes are atomic (:mod:`meanap.pipeline.atomic`), so an unreadable file
    means it predates that or came from somewhere else, and either way redoing
    it is cheaper than discovering the problem two steps later.
    """
    from meanap.pipeline.atomic import guard_readable

    if not params.continue_interrupted:
        return False
    artefact = Path(artefact)
    if not artefact.is_file():
        return False
    # Guard against a half-written file from before atomic writes existed.
    return guard_readable(artefact, log)


def missing_step_inputs(
    locator: InputLocator,
    recordings: list[RecordingInfo],
    start_step: int,
    *,
    suite2p_mode: bool = False,
) -> dict[str, list[str]]:
    """Which recordings lack the inputs the *starting* step needs.

    Only the starting step is checked: later steps consume what earlier ones
    produce during this run. Returns ``{recording_name: [missing artefact, …]}``
    for recordings that would be skipped, so the caller can fail fast (nothing
    resolvable) or warn (only some missing).

    ``suite2p_mode`` selects the CAT-NAP artefacts instead of the ephys ones —
    a different file, and only one resumable boundary (step 4).
    """
    missing: dict[str, list[str]] = {}
    for rec in recordings:
        gaps: list[str] = []
        if suite2p_mode:
            if start_step >= 4 and locator.catnap_file(rec.filename) is None:
                gaps.append("adjacency matrices + activity stats (step 2)")
        else:
            if start_step >= 2 and locator.spike_file(rec.filename) is None:
                gaps.append("spike times (step 1)")
            if start_step >= 4 and locator.adjm_file(rec.filename) is None:
                gaps.append("adjacency matrices (step 3)")
        if gaps:
            missing[rec.filename] = gaps
    return missing
