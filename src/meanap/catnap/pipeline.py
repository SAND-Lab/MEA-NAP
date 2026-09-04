"""CAT-NAP pipeline orchestrator (``Params.suite2pMode == 1`` path).

Mirrors the ``suite2pMode`` branches scattered through ``MEApipeline.m``: for
each suite2p recording it denoises (if needed), builds the adjacency matrices +
activity properties (:func:`~meanap.catnap.adjacency.suite2p_to_adjm`), computes
the two-photon activity stats (:func:`~meanap.catnap.stats.calc_twop_activity_stats`),
and then feeds the **shared** step-4 network-metric routine
(:func:`meanap.pipeline.step4.compute_network_metrics`) — the calcium-imaging
counterpart of running steps 1→4 on electrophysiology data.

Per recording it writes the trace and network figures; across the batch it
writes the JSON/CSVs and the group × age comparison figures
(:mod:`meanap.catnap.group_plots`), mirroring the ``2B_``/``4B_GroupComparisons``
folders the ephys path produces.
"""

from __future__ import annotations

from collections import Counter
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    # Imported as a module so the fully-qualified annotation below resolves;
    # `RecordingSource` alone is ambiguous, being re-exported from
    # `meanap.remote` as well.
    import meanap.remote.source

import numpy as np
import pandas as pd

from meanap.params import Params
from meanap.catnap.activities import (
    BY_ACTIVITY_DIR, activity_slug, activity_subtrees, activity_types,
    is_multi_activity, primary_activity,
)
from meanap.catnap.adjacency import suite2p_to_adjm
from meanap.catnap.group_plots import (
    SUBNET_GRAPH_METRICS, SUBNET_NODE_METRICS, twop_stats_frames,
)
from meanap.catnap.loader import Suite2pOutputMismatch, load_suite2p
from meanap.catnap.subnetwork import WHOLE_NETWORK
from meanap.catnap.stats import calc_twop_activity_stats
from meanap.timescale import (
    timescale_folder, timescale_kind, timescale_label,
)
import meanap.pipeline.network_metrics as nm
from meanap.pipeline.nmf import cal_nmf
from meanap.catnap.store import (
    BACKGROUND_SUFFIX, RecordingState, load_background, load_recording_state,
    quantize_background, save_background, save_recording_state, sorted_adjm_items,
)
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.resume import (
    ADJM_SUBDIR, CATNAP_SUFFIX, InputLocator, already_done,
    build_input_locator,
)
from meanap.pipeline.rng import make_rng
from meanap.pipeline.verbosity import as_run_log
from meanap.remote.source import stream_needing_work
from meanap.pipeline.parallel import StreamingPool, suggest_process_count
from meanap.pipeline.spreadsheet import RecordingInfo
from meanap.pipeline.step4 import (
    _apply_cartography_boundaries, _batch_metric_bounds, _convert_numpy,
    _NMF_NON_NODE_KEYS, compute_network_metrics,
)

_NEEDS_DENOISING = ("peaks", "denoised F", "spks")

#: Peak RSS one metrics worker needs: the adjacency and its null-model copies
#: are a few tens of MB even for a 600-cell recording, so this is dominated by
#: the worker's own numpy/scipy import. Same figure ``step4.py`` uses.
_METRICS_MEM_PER_TASK_GB = 0.6


@dataclass
class _MetricsTask:
    """One recording's network-metrics work, as sent to a pool worker.

    Deliberately carries the arrays rather than a path to the ``_catnap.npz``
    the caller also writes: that write is best-effort (a failure there is a
    warning, not an error), so reading it back would make the metrics depend on
    a file that is allowed not to exist. What travels is small — an adjacency
    matrix is ~3 MB even at 600 cells.
    """

    filename: str
    adjMs: dict
    spike_counts: np.ndarray
    duration_s: float
    lag_independent: dict
    params: Params
    min_nodes: int
    #: Which measure of activity this adjacency was built from. Carried so the
    #: results a worker hands back can be routed to the right measure's tree —
    #: ``params.twop_activity`` says the same thing, but a worker result is
    #: matched on the pair, and reading it off the task is what makes that
    #: explicit rather than implied.
    activity: str = ""


def _metrics_worker(task: _MetricsTask) -> tuple[str, str, dict]:
    """Network metrics for every lag of one recording. Runs in a pool worker.

    Module-level and picklable-in/out because ``spawn`` re-imports this module
    in each worker. The RNG is rebuilt here from the seed rather than passed in,
    so a recording's stream depends only on its own filename — which is what
    makes running recordings concurrently produce byte-identical results to
    running them in order.
    """
    rng = make_rng(task.params.random_seed, "step4", task.filename)
    out: dict = {}
    for lag_ms, adj in sorted_adjm_items(task.adjMs):
        metrics = compute_network_metrics(
            adj, task.spike_counts, task.duration_s,
            task.params.min_activity_level, task.min_nodes,
            exclude_edges_below_threshold=task.params.exclude_edges_below_threshold,
            params=task.params, rng=rng,
        )
        # effRank / NMF describe the recording, not the lag, so every lag
        # carries the same value — as ExtractNetMet.m does by computing them
        # under `if e == 1` and saving them on the first lag field.
        metrics.update(task.lag_independent)
        out[f"{lag_ms}mslag"] = metrics
    return task.activity, task.filename, out


#: ``Params.startAnalysisStep`` at or above which a CAT-NAP run reads the prior
#: run's adjacency instead of rebuilding it. There is no step 1 or 3 on this
#: path (adjacency is built in step 2, as in MATLAB), so 4 is the only boundary
#: that means anything.
RESUME_STEP = 4


def suite2p_plane0_dir(raw_data: str, filename: str) -> Path:
    """Location of a recording's suite2p output (mirrors MEApipeline.m)."""
    return Path(raw_data) / filename / "suite2p" / "plane0"


def _log_bin_rounding(res, log, filename: str) -> None:
    """Say what each requested correlation bin actually became.

    Bins are built out of whole frames, so a request is always rounded — and
    one shorter than a single frame rounds away entirely, leaving the un-binned
    correlation under a folder named for a bin that was never applied. That is
    the one case worth being loud about, since two different requested bins can
    then produce byte-identical results.
    """
    if not res.bin_frames:
        return
    unbinned = [ms for ms, frames in res.bin_frames.items() if frames <= 1]
    clamped = []
    for bin_ms, frames in sorted(res.bin_frames.items()):
        actual = frames / res.fs * 1000
        log(f"  [{filename}] {bin_ms} ms bin → {frames} frame"
            f"{'' if frames == 1 else 's'} ({actual:.1f} ms)")
        # frames_per_bin only rounds, so a realised bin this far off the
        # request can only be the too-long-for-the-recording clamp.
        if frames > 1 and actual < bin_ms * 0.9:
            clamped.append((bin_ms, actual))
    for bin_ms, actual in clamped:
        log(f"  [{filename}] WARNING: a {bin_ms} ms bin leaves fewer than two "
            f"bins in this recording — shortened to {actual:.0f} ms so there is "
            f"something to correlate across.")
    if unbinned:
        log(f"  [{filename}] WARNING: {', '.join(f'{ms} ms' for ms in sorted(unbinned))} "
            f"{'is' if len(unbinned) == 1 else 'are'} shorter than one frame at "
            f"{res.fs:.4g} Hz — no binning applied, so this is the raw "
            f"frame-resolution correlation.")


def _log_sampling_rates(states: dict, log) -> None:
    """Summarise the batch's acquisition rates once phase 1 has seen them all.

    A per-recording line is easy to scroll past; what a reader actually needs
    to know is whether the batch was acquired at one rate or several. It is
    routinely several — frame rate tends to be a property of the culture prep,
    so a dataset spanning preps spans rates — and unlike ephys there is no
    single setting that says so, because CAT-NAP reads the rate out of each
    recording's own ``ops.npy`` (which is also what MATLAB does; the GUI's
    sampling-rate field is not read on this path).

    That is not an error, and nothing here is wrong when it happens: every
    seconds-valued setting is converted with the recording's own rate. It does
    change how the results should be *read*, though — rate covaries with prep,
    so it can covary with whatever the groups are — so it is said plainly
    rather than left to be discovered.
    """
    rates = sorted({round(float(st.fs), 4) for st in states.values() if st.fs})
    if not rates:
        return
    if len(rates) == 1:
        n = len(states)
        log(f"  Acquisition rate: {rates[0]:.4g} Hz "
            + ("(the only recording)" if n == 1 else f"(all {n} recordings)"))
        return
    counts = Counter(round(float(st.fs), 4) for st in states.values() if st.fs)
    log(f"  NOTE: this batch mixes {len(rates)} acquisition rates — "
        + ", ".join(f"{fs:.4g} Hz x{counts[fs]}" for fs in rates))
    log("        Each recording was analysed at its own rate, read from its "
        "ops.npy. Frame rate often tracks the culture prep, so check it is "
        "not confounded with the groups being compared.")


def _validated_measures(params: Params, log) -> Params:
    """Drop measures of activity nothing can build a network from.

    ``suite2p_to_adjm`` raises on an unknown measure, and it would do so partway
    through the first recording — after the loading and the denoising, with the
    run already committed. A typo in a settings file is worth catching here, in
    one line, rather than as a traceback ten minutes in.

    The primary measure is never dropped: if *that* is wrong the run has nothing
    to do, and failing loudly at the first recording is the right outcome.
    """
    import dataclasses

    from meanap.catnap.activities import ACTIVITY_TYPES

    measures = activity_types(params)
    unknown = [a for a in measures[1:] if a not in ACTIVITY_TYPES]
    if not unknown:
        return params
    log(f"  Ignoring unknown measure(s) of activity: {', '.join(map(repr, unknown))} "
        f"— expected one of {', '.join(ACTIVITY_TYPES)}")
    kept = tuple(a for a in measures if a not in unknown)
    return dataclasses.replace(params,
                               twop_activities=kept if len(kept) > 1 else ())


def _any_states(states: dict[str, dict]) -> dict:
    """The first non-empty measure's states, for the facts they all agree on.

    Frame rate, duration and cell count come out of the recording rather than
    out of the measure, so anything reporting them can take whichever measure
    happens to have loaded.
    """
    for by_rec in states.values():
        if by_rec:
            return by_rec
    return {}


def _prepare_activity_subtrees(params: Params, recordings, subtrees, log) -> None:
    """Give each extra measure a complete, self-contained run folder.

    The folder tree, so figures land where every other part of MEA-NAP expects
    them, and a ``params.json`` describing *that measure alone* — which is what
    lets the HTML report, the bundle viewer and ``meanap-stats`` be pointed
    straight at ``ByActivityType/denoisedF/`` and read it as an ordinary run.
    Without the params file they would read the parent run's, and label every
    figure with the primary measure's name.
    """
    from meanap.params import save_params
    from meanap.pipeline.output_folders import create_output_folders

    groups = sorted({rec.group for rec in recordings})
    primary = primary_activity(params)
    for activity, (p_act, root_act) in subtrees.items():
        if activity == primary:
            continue  # the run folder itself, already created by the runner
        try:
            create_output_folders(root_act.parent, root_act.name, groups,
                                  include_not_box_plots=params.include_not_box_plots)
            save_params(p_act, root_act)
        except Exception as e:
            log(f"  Warning: could not prepare the {activity!r} output folder "
                f"({root_act}): {e}")


def _params_for(params: Params, activity: str) -> Params:
    """*params* as a single-measure configuration for *activity*.

    Cached per call site rather than per measure because it is cheap and the
    alternative — threading an ``activity`` argument through every function
    below — would put the same information in two places.
    """
    from meanap.catnap.activities import activity_params

    return activity_params(params, activity)


def _spike_counts(res, twop_activity: str) -> np.ndarray:
    """Per-node activity count used for the active-node inclusion test.

    Peaks → number of detected peaks per unit (matches MATLAB's peak-count
    firing rate); other activity types → column sum of the activity matrix
    (``sum(expData.(twopActivity), 1)`` in ``calTwopActivityStats.m``).
    """
    if twop_activity == "peaks":
        return np.array([np.size(st) for st in res.spike_times], dtype=float)
    src = {"F": res.F, "spks": res.spks, "denoised F": res.denoised_F}[twop_activity]
    return np.asarray(src, dtype=float).sum(axis=0)


def _activity_stats_for(res, params: Params, duration_s: float) -> dict:
    ap = res.activity_properties
    kw = dict(
        twop_activity=params.twop_activity,
        duration_s=duration_s,
        fs=res.fs,
        min_activity_level=params.min_activity_level,
    )
    if params.twop_activity == "peaks":
        kw.update(
            spike_times=res.spike_times,
            peak_heights=ap.get("peakHeights"),
            peak_duration_frames=ap.get("peakDurationFrames"),
            event_areas=ap.get("eventAreas"),
        )
    else:
        src = {"F": res.F, "spks": res.spks, "denoised F": res.denoised_F}[params.twop_activity]
        kw.update(activity_matrix=src)
    return calc_twop_activity_stats(**kw)


def run_catnap_pipeline(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None] = print,
    should_cancel: CancelCheck = None,
    locator: InputLocator | None = None,
    source: "meanap.remote.source.RecordingSource | None" = None,
    progress: "meanap.pipeline.progress.RunProgress | None" = None,
) -> None:
    """Run the CAT-NAP path over all recordings, writing NetMet JSON + CSVs.

    Three phases, mirroring ``step4._run_step4_network_metrics``:

    1. **compute** every recording's adjacency, activity stats and network
       metrics;
    2. **reduce** across the batch — pool participation coefficient and
       within-module z-score to place the node-cartography boundaries where
       the data actually clusters (``autoSetCartographyBoundaries``);
    3. **plot** every recording, then the batch comparisons.

    The barrier matters: cartography roles are re-derived in phase 2, so every
    figure and CSV that shows a role has to be produced after it. Phase 1 keeps
    only a small per-recording state (:class:`~meanap.catnap.store.RecordingState`)
    — the raw fluorescence matrices are hundreds of MB per recording and are
    re-read from disk in phase 3 for the trace figures.

    **Several measures of activity.** With ``Params.twop_activities`` set, all
    three phases carry a measure axis: every per-recording dict below is
    ``{measure: {recording: …}}``, phase 2 places cartography boundaries once
    per measure, and phase 3 draws each measure's figures into its own output
    subtree (:mod:`meanap.catnap.activities`). Only phase 1's *loading* is
    shared — the raw data is read and denoised once per recording however many
    measures are asked for, which is what makes this one run rather than N.
    Nothing else is: an event network and a binned correlation network of the
    same recording are two different networks, and pooling anything across them
    — boundaries, metric ranges, the RNG stream — would make each measure's
    numbers depend on which others happened to be in the run.

    **Resuming.** Phase 1 writes each recording's adjacency + activity stats to
    ``ExperimentMatFiles/<rec>_catnap.npz`` (:mod:`meanap.catnap.store`). When
    ``params.start_analysis_step >= 4`` it reads that back from ``locator``
    instead of recomputing, skipping the expensive part — denoising, STTC and
    the circular-shift thresholding — exactly as MATLAB's
    ``priorAnalysis``/``startAnalysisStep = 4`` branch does. The file is
    rewritten into *this* run's output folder either way, so a resumed run is
    itself resumable. Network metrics, cartography and every figure are always
    recomputed: that is what step 4 *is*.

    Note the batch reduce in phase 2 pools PC/Z over every recording that
    phase 1 produced, so resuming a subset of the batch places the cartography
    boundaries from that subset alone — the roles will not match the original
    run's unless the same recordings are present.

    Stochastic stages draw from per-recording generators derived from
    ``params.random_seed`` (see :mod:`meanap.pipeline.rng`), the same scheme the
    ephys steps use. A single batch-wide stream would make every recording's
    metrics depend on how much randomness the recordings before it consumed —
    which a resumed run, having skipped the thresholding draws entirely, would
    change. With per-recording streams a seeded resume reproduces the numbers
    of the run it resumed from.
    """
    log = as_run_log(log, params.verbose_level)
    from meanap.pipeline.progress import RunProgress

    progress = progress or RunProgress()
    if locator is None:
        locator = build_input_locator(params, output_root)
    if source is None:
        source = _build_source(params, log)
    # Set rather than passed, so a caller that supplies its own source — the
    # remote tests do — reports transfers without having to wire them up.
    source.progress = progress

    min_nodes = params.min_number_of_nodes_to_cal_net_met
    params = _validated_measures(params, log)
    measures = activity_types(params)
    # Each measure's outputs go in a complete run subtree of their own; the
    # primary measure's *is* the run folder, so a one-measure run writes
    # exactly what it always did. See meanap.catnap.activities.
    subtrees = {a: (pa, root)
                for a, pa, root in activity_subtrees(output_root, params)}
    if is_multi_activity(params):
        log("  Measures of activity: " + ", ".join(measures)
            + f" (primary: {measures[0]})")
        log(f"  Each extra measure writes a full run folder under "
            f"{BY_ACTIVITY_DIR}/; the tables in this folder pool all of them "
            "with an ActivityType column.")
        _prepare_activity_subtrees(params, recordings, subtrees, log)

    net_dir = output_root / "4_NetworkActivity"
    net_dir.mkdir(parents=True, exist_ok=True)
    state_dir = output_root / ADJM_SUBDIR
    state_dir.mkdir(parents=True, exist_ok=True)

    resuming = params.start_analysis_step >= RESUME_STEP

    # Every one of these is now ``{measure: {recording: …}}``. Two measures of
    # the same recording are two different networks, so nothing about them —
    # not the cartography boundaries, not the batch metric ranges, not a single
    # figure — may be pooled across the outer key.
    all_results: dict[str, dict[str, dict]] = {a: {} for a in measures}
    all_stats: dict[str, dict[str, dict]] = {a: {} for a in measures}
    all_channels: dict[str, dict[str, np.ndarray]] = {a: {} for a in measures}
    states: dict[str, dict[str, RecordingState]] = {a: {} for a in measures}
    subnetwork_tables: dict[str, dict[str, list]] = {
        a: {"summary": [], "node": [], "mix": []} for a in measures}

    progress.begin("catnap.compute", items=len(recordings))

    # Network metrics are ~90% of a CAT-NAP run's compute (the null-model
    # randomisations behind PC dominate, and they scale with edge count, which
    # a near-complete calcium network has a lot of). Unlike everything else in
    # phase 1 they need only the adjacency matrix — not the suite2p folder — so
    # they can be handed to a pool while the stream carries on fetching,
    # computing and *releasing* recordings one at a time. That is what keeps
    # the bounded-local-storage property intact: workers never touch raw data,
    # so parallelism here costs no extra disk.
    #
    # Each recording's generator is seeded from its own filename, so results do
    # not depend on how the work interleaves — see :func:`_metrics_worker`.
    n_metric_workers = suggest_process_count(
        len(recordings), _METRICS_MEM_PER_TASK_GB,
        max_workers=params.recording_workers,
    )
    if n_metric_workers > 1:
        log(f"  computing network metrics on {n_metric_workers} workers")

    # ── Phase 1: compute (or reload) ──────────────────────────────────────────
    # Recordings arrive with the next one already being fetched (remote sources
    # only), and each is released once its results are on disk — so a batch's
    # peak local storage is one or two recordings, not the whole dataset.
    #
    # A resumed run reads adjacency from the prior analysis and never opens the
    # raw data, so it must not fetch it either: the whole point of resuming is
    # that the recordings need not be present at all. A *continued* run is the
    # same case per recording rather than per run — see below.
    already_computed = _already_computed(params, output_root, measures,
                                         recordings, log)
    if already_computed and source.remote:
        log(f"  {len(already_computed)} recording(s) already computed — their "
            f"raw data will not be fetched.")
    stream = (
        ((rec, suite2p_plane0_dir(params.raw_data, rec.filename))
         for rec in recordings)
        if resuming else
        stream_needing_work(
            source, recordings, already_computed.__contains__,
            depth=params.prefetch_depth, kind="catnap",
            stand_in=lambda rec: suite2p_plane0_dir(params.raw_data, rec.filename),
        )
    )
    # Filled by the pool as workers finish, so in completion order — see the
    # re-ordering into ``all_results`` after the loop.
    metric_results: dict[tuple[str, str], dict] = {}
    # One progress item per recording however many measures it is analysed
    # under, so the bar still counts what the log's per-recording lines count.
    outstanding: dict[str, int] = {}

    def _metrics_done(result: tuple[str, str, dict]) -> None:
        activity, name, rec_results = result
        metric_results[(activity, name)] = rec_results
        outstanding[name] = outstanding.get(name, 0) - 1
        if outstanding.get(name, 0) <= 0:
            progress.item_done(name)

    with StreamingPool(n_metric_workers, on_result=_metrics_done,
                       cancel_check=should_cancel,
                       on_degrade=lambda msg: log(f"  WARNING: {msg}")) as pool:
        for rec, fetched in stream:
            check_cancel(should_cancel)
            if isinstance(fetched, BaseException):
                log(f"  [{rec.filename}] SKIP: {fetched}")
                continue
            plane0 = fetched

            # Continuing an interrupted run: this recording's adjacency and
            # activity stats are already in *this* folder, so load them rather than
            # redoing the STTC and the circular-shift thresholding, which is the
            # expensive half of the CAT-NAP path. Decided before the stream was
            # built, so a remote source never fetched this recording at all.
            continued = rec.filename in already_computed
            if continued:
                log(f"  [{rec.filename}] already computed — loading")

            loaded = (
                _load_recording(locator, params, rec, plane0, log)
                if (resuming or continued)
                else _compute_recording(params, rec, plane0, log)
            )
            if not loaded:
                if not resuming and not continued:
                    source.unpin(rec.filename)
                    source.release(rec.filename)
                continue

            # Always re-read: cheap, and it means a resumed run picks up an edited
            # cell-type spreadsheet instead of freezing the first run's grouping.
            # A bundle carries a copy of the markers for recipients who have no
            # spreadsheet at all, so the live reading only wins when it found one.
            # Read once and shared: cell identity is a property of the field of
            # view, not of how activity in it was measured.
            first_state = next(iter(loaded.values()))[0]
            groups, markers = _resolve_cell_types(
                params, rec, first_state.channels, log)

            outstanding[rec.filename] = len(loaded)
            for activity, (state, stats) in loaded.items():
                if groups is not None or state.groups is None:
                    state.groups = groups
                if markers is not None or state.markers is None:
                    state.markers = markers

                all_stats[activity][rec.filename] = stats
                all_channels[activity][rec.filename] = state.channels
                states[activity][rec.filename] = state

                sub_state_dir = (output_root / (_state_subdir(params, activity) or "")
                                 / ADJM_SUBDIR)
                try:
                    sub_state_dir.mkdir(parents=True, exist_ok=True)
                    save_recording_state(
                        sub_state_dir / f"{rec.filename}{CATNAP_SUFFIX}", state, stats)
                except Exception as e:
                    log(f"  [{rec.filename}] warning: could not save step-2 data for "
                        f"re-runs: {e}")

            # Everything derived from this recording is now on disk, so its raw
            # files are no longer needed — unless the trace figures still want them
            # in phase 3, in which case re-fetching one recording beats holding the
            # whole batch. Nothing was fetched for a recording that was already
            # computed, so there is no hold on it to drop.
            if not resuming and not continued:
                source.unpin(rec.filename)
                source.release(rec.filename)

            # Hand the expensive half off. ``submit`` blocks once the pool is
            # saturated, which is what stops the stream fetching further ahead
            # than the metrics can keep up with.
            for activity, (state, _stats) in loaded.items():
                p_act = subtrees[activity][0]
                kind = timescale_kind(p_act)
                lags = [lag for lag, _ in sorted_adjm_items(state.adjMs)]
                note = f" [{activity}]" if len(loaded) > 1 else ""
                log(f"  [{rec.filename}]{note} network metrics "
                    f"({kind}{'' if len(lags) == 1 else 's'} "
                    f"{', '.join(str(lag) for lag in lags)} ms)…")
                pool.submit(_metrics_worker, _MetricsTask(
                    filename=rec.filename,
                    adjMs=state.adjMs,
                    spike_counts=state.spike_counts,
                    duration_s=state.duration_s,
                    lag_independent=state.lag_independent,
                    params=p_act,
                    min_nodes=min_nodes,
                    activity=activity,
                ))

        pool.drain()

    # A stop requested while the pool was draining lands here: the pool drops
    # what it had not started, and this turns that into the same
    # PipelineCancelled the serial loop raised at its own checkpoint.
    check_cancel(should_cancel)

    # Results arrived in completion order. Re-key them in the batch's own order
    # so everything downstream — the cartography barrier that pools PC/Z across
    # recordings, the batch metric bounds, the CSVs — sees exactly the sequence
    # it saw when this loop was serial.
    for activity in measures:
        for rec in recordings:
            if (activity, rec.filename) in metric_results:
                all_results[activity][rec.filename] = \
                    metric_results[(activity, rec.filename)]

    # Acquisition rate is a property of the recording, so it is the same under
    # every measure — reported once, from whichever measure has the states.
    _log_sampling_rates(_any_states(states), log)

    # ── Phase 2: reduce — data-driven node-cartography boundaries ─────────────
    # Pool PC/Z over the whole batch and re-place the six role boundaries, then
    # re-classify every node (port of MEApipeline.m's autoSetCartographyBoundaries
    # barrier). Without this the roles come from the fixed Params defaults and
    # almost every node lands in role 1.
    #
    # Per measure, never pooled across them: an STTC event network and a binned
    # correlation network have PC/Z distributions that do not live on the same
    # scale, so one shared set of boundaries would put the two measures' roles
    # in different places and then invite the reader to compare them.
    batch_bounds: dict[str, dict] = {}
    for activity in measures:
        p_act, root_act = subtrees[activity]
        results_act = all_results[activity]
        if params.auto_set_cartography_boundaries and results_act:
            check_cancel(should_cancel)
            # ``out_dir=None`` suppresses the pooled PC/Z landscape scatter — a
            # figure, and one the bundle's metrics can redraw.
            _apply_cartography_boundaries(
                p_act, results_act, log,
                out_dir=None if params.express_mode
                else root_act / "4_NetworkActivity")
        # Pooled node-metric ranges, so the ``_scaled`` network plots of
        # different recordings share an axis.
        batch_bounds[activity] = {m: _batch_metric_bounds(results_act, m)
                                  for m in ("ND", "NS", "BC", "PC", "Eloc")}

    # ── Phase 3: plot ─────────────────────────────────────────────────────────
    progress.phase_done()
    progress.begin("catnap.plot", items=len(recordings))
    for rec in recordings:
        # Whichever measures this recording has, not necessarily the primary:
        # resuming a two-measure run against a one-measure prior analysis can
        # leave a recording with only the *other* measure, and dropping it from
        # the figures because the primary is missing would lose work that was
        # done.
        present = [a for a in measures if rec.filename in states[a]]
        if not present:
            continue
        check_cancel(should_cancel)
        # The backdrop came from phase 1; this only re-opens the folder when
        # per-cell trace figures were asked for — once per recording, not once
        # per measure, because the traces it draws are the raw and denoised
        # fluorescence and neither depends on the measure.
        data, _ = _reload_for_plots(
            params, rec, states[present[0]][rec.filename], log, source)
        _plot_traces(params, rec, output_root, log, data)

        for activity in present:
            state = states[activity][rec.filename]
            if rec.filename not in all_results[activity]:
                continue
            p_act, root_act = subtrees[activity]
            # Persisted, not just drawn: figure 12 is the one plot that needs
            # pixels rather than metrics, so a bundle has to carry the
            # projection or it could never be reconstructed. Written into every
            # measure's subtree so each one opens as a complete run folder.
            try:
                save_background(
                    root_act / ADJM_SUBDIR / f"{rec.filename}{BACKGROUND_SUFFIX}",
                    state.background)
            except Exception as e:
                log(f"  [{rec.filename}] warning: could not save mean projection: {e}")

            _plot_recording(p_act, rec, state, all_results[activity][rec.filename],
                            batch_bounds[activity], root_act, log, state.background)

            if params.twop_subnetwork_analysis:
                _run_subnetwork_analysis(
                    p_act, rec, state, all_results[activity][rec.filename],
                    min_nodes, root_act, subnetwork_tables[activity], log,
                    make_rng(params.random_seed, "catnap_subnetwork", rec.filename),
                    state.background,
                )
        progress.item_done(rec.filename)

    progress.phase_done()
    progress.begin("batch", items=1)
    rates = {name: float(st.fs)
             for name, st in _any_states(states).items() if st.fs}
    _save_catnap_results(params, recordings, all_results, all_stats, all_channels,
                         output_root, log, sampling_rates=rates)
    _save_subnetwork_results(params, subnetwork_tables, output_root, log)
    for activity in measures:
        p_act, root_act = subtrees[activity]
        _plot_group_comparisons(
            p_act, recordings, all_results[activity], all_stats[activity],
            all_channels[activity], subnetwork_tables[activity],
            states[activity], root_act, log,
        )
    progress.phase_done()
    log("  CAT-NAP pipeline complete.")


def _compute_recording(
    params: Params, rec: RecordingInfo, plane0: Path, log,
) -> dict[str, tuple[RecordingState, dict]] | None:
    """Build one recording's adjacency + activity stats, for every measure.

    This is the expensive half of the CAT-NAP path — denoising, then STTC with
    ``prob_thresh_rep_num`` circular-shift surrogates per lag — and the half a
    step-4 resume skips. Returns ``None`` (having logged why) when the
    recording has no suite2p output to read; otherwise ``{measure: (state,
    stats)}`` with one entry per measure the run analyses.

    The loading and the denoising happen **once** no matter how many measures
    are asked for. That is the whole reason a multi-measure run is one run
    rather than several: the fluorescence matrices are hundreds of MB and the
    peak detection is not cheap, and every measure is derived from the same
    pass over them. What is genuinely per-measure — the adjacency, the activity
    statistics, the active-node counts — is what the loop below repeats.

    Each measure gets a generator seeded identically, not a shared one drawn
    down in sequence. A stream shared across measures would make ``peaks``
    produce different numbers depending on which other measures were run beside
    it, and the first thing anyone does with a multi-measure run is compare it
    against a single-measure one.
    """
    from meanap.catnap.denoising import process_suite2p_folder

    if not (plane0 / "stat.npy").exists():
        log(f"  [{rec.filename}] SKIP: no suite2p output at {plane0}")
        return None

    derived = params.derived_data_folder or None
    log(f"  [{rec.filename}] loading suite2p data…")
    try:
        data = load_suite2p(plane0, derived, rec.filename)
    except Suite2pOutputMismatch as e:
        # One unusable folder costs the batch that recording, not the run —
        # the same treatment as a folder with no suite2p output at all. The
        # full diagnosis goes to the log so it is actionable afterwards.
        log(f"  [{rec.filename}] SKIP: {e}")
        return None

    log = as_run_log(log, params.verbose_level)
    # Said per recording, not once per run: the rate comes from this
    # recording's own ops.npy and a 2P batch routinely mixes rates. Everything
    # below converts seconds to frames with it, so it belongs in the log
    # *before* the first thing that uses it.
    log(f"  [{rec.filename}] {data.fs:.4g} Hz, {data.n_frames} frames "
        f"({data.duration_s:.0f} s)")
    log.debug(f"      suite2p folder {plane0}")
    log.detail(f"      {data.F.shape[0]} ROIs"
               + ("" if data.F_denoised is None else ", denoised traces already on disk"))

    measures = activity_types(params)
    if any(a in _NEEDS_DENOISING for a in measures) and (
        data.F_denoised is None or params.twop_redo_denoising
    ):
        log(f"  [{rec.filename}] denoising ({data.F.shape[0]} ROIs)…")
        process_suite2p_folder(
            plane0,
            overwrite=params.twop_redo_denoising,
            denoising_threshold=params.twop_denoising_threshold,
            time_before_peak_s=params.twop_denoising_time_before_peak,
            time_after_peak_s=params.twop_denoising_time_after_peak,
            min_event_interval_s=params.twop_min_event_interval,
            derived_root=derived,
            recording=rec.filename,
        )
        data = load_suite2p(plane0, derived, rec.filename)

    out: dict[str, tuple[RecordingState, dict]] = {}
    for activity in measures:
        p_act = _params_for(params, activity)
        label = f"  [{rec.filename}]" + (f" [{activity}]" if len(measures) > 1 else "")
        log(f"{label} building adjacency matrices…")
        res = suite2p_to_adjm(
            data, activity, params.func_con_lag_val,
            remove_nodes_with_no_peaks=params.remove_nodes_with_no_peaks,
            prob_thresh_tail=params.prob_thresh_tail,
            prob_thresh_rep_num=params.prob_thresh_rep_num,
            rng=make_rng(params.random_seed, "catnap", rec.filename),
        )
        _log_bin_rounding(res, log, rec.filename)
        duration_s = res.F.shape[0] / res.fs
        log.detail_lines(_describe_adjms(
            res.adjMs, f" [{activity}]" if len(measures) > 1 else ""))

        state = RecordingState(
            adjMs=res.adjMs, coords=res.coords, channels=res.channels,
            spike_counts=_spike_counts(res, activity),
            duration_s=duration_s, fs=res.fs, plane0=plane0,
            coord_norm=res.coord_norm,
        )
        state.lag_independent = _lag_independent_metrics(
            res, p_act, duration_s, log, rec.filename,
            make_rng(params.random_seed, "catnap", rec.filename))
        # Capture the field-of-view backdrop now, while the (large) suite2p data
        # is already loaded. Phase 3 used to re-open the whole folder just for
        # this; doing it here means the raw data is read once per recording,
        # which is what lets a batch stream through bounded local storage. The
        # normalisation is per measure because ``remove_nodes_with_no_peaks``
        # can drop nodes and move the centroid range with them.
        if params.twop_network_background:
            state.background = quantize_background(
                _mean_image_background(data.mean_img, res.coord_norm))
            if state.background is None and activity == measures[0]:
                log(f"  [{rec.filename}] note: no mean projection in ops — "
                    "network plots drawn without a backdrop")
        out[activity] = (state, _activity_stats_for(res, p_act, duration_s))
    return out


def _describe_adjms(adj_ms: dict[str, np.ndarray], note: str) -> list[str]:
    """One line per lag: how connected the network this measure produced is.

    The equivalent of step 3's edge report on the ephys side. It is the first
    place a measure of activity that found almost nothing — a denoising
    threshold set too high, say — becomes visible, and this is a run where the
    choice of measure is the thing being tested.
    """
    lines = []
    for key, adj in sorted(adj_ms.items()):
        adj = np.asarray(adj)
        if adj.ndim != 2 or adj.shape[0] < 2:
            continue
        n = adj.shape[0]
        possible = n * (n - 1) // 2
        upper = np.triu_indices(n, k=1)
        kept = int(np.count_nonzero(adj[upper] > 0))
        prefix = f"{note.strip()} " if note.strip() else ""
        lines.append(f"      {prefix}{key}: {n} nodes, {kept} edges "
                     f"({kept / possible * 100:.1f}% of {possible} possible)")
    return lines


def _activity_matrix_for(res, twop_activity: str) -> np.ndarray | None:
    """The ``(n_frames, n_units)`` matrix ``ExtractNetMet.m`` is handed.

    In ``suite2pMode`` MEApipeline.m picks this by activity type before calling
    ``ExtractNetMet`` — ``denoisedF``, ``spks``, or (for ``peaks``) the spike
    matrix ``formatSpikeTimes`` builds. ``None`` for ``peaks``, where the
    caller uses the event times directly instead of densifying them here.
    """
    if twop_activity == "peaks":
        return None
    return {"F": res.F, "spks": res.spks, "denoised F": res.denoised_F}[twop_activity]


def _lag_independent_metrics(
    res, params: Params, duration_s: float, log, name: str, rng,
) -> dict:
    """Effective rank and NMF — computed once per recording, not once per lag.

    ``ExtractNetMet.m`` gates both on ``if e == 1`` and stores them on the
    first lag field, because both read the *activity matrix* rather than any
    adjacency matrix. Nothing about them is 2P-specific: MEApipeline.m calls
    ``ExtractNetMet`` identically in ``suite2pMode``, so a MATLAB CAT-NAP run
    produces them and this path did not until now.

    Failures are logged and become NaN rather than losing the recording: these
    are two summary numbers, and the network metrics beside them are unaffected.
    """
    out: dict = {}
    activity = _activity_matrix_for(res, params.twop_activity)

    try:
        if activity is not None:
            out["effRank"] = nm.effective_rank_from_activity(
                np.asarray(activity, dtype=float), res.fs,
                params.eff_rank_downsample_freq, params.eff_rank_cal_method)
        else:
            out["effRank"] = nm.effective_rank(
                res.spike_times, res.fs, duration_s,
                params.eff_rank_downsample_freq, params.eff_rank_cal_method)
    except Exception as e:
        log(f"  [{name}] WARNING: could not compute effective rank: {e}")
        out["effRank"] = float("nan")

    if params.twop_nmf:
        try:
            spike_times = (res.spike_times if res.spike_times is not None
                           else _event_times_from_matrix(activity, res.fs))
            out.update(cal_nmf(
                spike_times, np.asarray(_spike_counts(res, params.twop_activity)),
                duration_s, params.nmf_downsample_freq, res.fs,
                include_nmf_components=params.include_nmf_components, rng=rng))
        except Exception as e:
            log(f"  [{name}] WARNING: could not compute NMF components: {e}")

    return out


def _event_times_from_matrix(activity: np.ndarray, fs: float) -> list[np.ndarray]:
    """Per-unit event times from a continuous activity matrix.

    ``cal_nmf`` takes event times and rebuilds a matrix from them, so a
    continuous activity type has to be expressed that way. Non-zero samples
    become events at their frame time — which for ``spks`` is what the values
    already mean, and for the fluorescence types is the closest available
    reading of "when this unit was active".
    """
    a = np.asarray(activity, dtype=float)
    return [np.nonzero(a[:, i])[0] / fs for i in range(a.shape[1])]


def _load_recording(
    locator: InputLocator, params: Params, rec: RecordingInfo, plane0: Path, log,
) -> dict[str, tuple[RecordingState, dict]] | None:
    """Read one recording's step-2 products back from a previous run.

    Mirrors MEApipeline.m's ``priorAnalysis == 1 && startAnalysisStep == 4``
    branch, which loads ``adjMs`` out of the prior ``ExperimentMatFiles`` rather
    than calling ``suite2pToAdjm`` again. Returns ``None`` (having logged why)
    when *no* measure could be read, so one bad recording costs the batch that
    recording and not the run.

    A measure whose file is missing is dropped with a warning and the others
    still load: resuming a two-measure run against a one-measure prior analysis
    is a reasonable thing to do by accident, and losing the measure that *is*
    there would be the worse answer.
    """
    out: dict[str, tuple[RecordingState, dict]] = {}
    for activity in activity_types(params):
        subdir = _state_subdir(params, activity)
        path = locator.catnap_file(rec.filename, subdir=subdir)
        note = f" [{activity}]" if is_multi_activity(params) else ""
        if path is None:
            log(f"  [{rec.filename}]{note} SKIP: no saved step-2 data "
                f"({rec.filename}{CATNAP_SUFFIX}) to resume from")
            continue
        try:
            state, stats = load_recording_state(path, plane0)
        except Exception as e:
            log(f"  [{rec.filename}]{note} SKIP: could not read {path}: {e}")
            continue
        # Phase 1 didn't run, so the backdrop it would have captured is loaded
        # from whatever the previous run persisted (present in a bundle, absent
        # if that run had backgrounds switched off).
        state.background = load_background(
            path.with_name(f"{rec.filename}{BACKGROUND_SUFFIX}"))
        log(f"  [{rec.filename}]{note} reusing adjacency matrices from {path}")
        out[activity] = (state, stats)
    return out or None


def _already_computed(
    params: Params, output_root: Path, measures, recordings, log,
) -> set[str]:
    """Which recordings a continued run can skip, decided before anything is fetched.

    The natural place for this check is beside the work it skips, inside phase
    1's loop. That is where it used to be, and on a local dataset it costs
    nothing to leave it there. On a remote one it costs the whole download: the
    stream hands over a recording only after fetching it, so the run saved the
    STTC and the thresholding and still paid for every byte — continuing a
    Dropbox-hosted batch took about as long as not continuing at all.

    Every measure has to be present for a recording to count as done. A
    continued run that found only the primary measure's file would quietly drop
    the others, and the recording would be missing from exactly the comparison
    the extra measures were run for.

    Empty unless the run was asked to continue: ``already_done`` returns False
    for every other kind of run, and this is only ever a set of what it found.
    """
    if not params.continue_interrupted:
        return set()
    return {
        rec.filename for rec in recordings
        if all(
            already_done(
                params, output_root,
                output_root / (_state_subdir(params, activity) or "")
                / ADJM_SUBDIR / f"{rec.filename}{CATNAP_SUFFIX}", log)
            for activity in measures)
    }


def _state_subdir(params: Params, activity: str) -> Path | None:
    """Where *activity*'s ``ExperimentMatFiles`` sit, relative to a run root.

    ``None`` for the primary measure, which keeps the top-level folder — see
    :data:`meanap.catnap.activities.BY_ACTIVITY_DIR`.
    """
    if not is_multi_activity(params) or activity == primary_activity(params):
        return None
    return Path(BY_ACTIVITY_DIR) / activity_slug(activity)


def _mean_image_background(mean_img, coord_norm) -> tuple | None:
    """Map suite2p's mean projection into the node coordinate frame.

    ``coords`` are ``stat['med']`` normalised onto ``[0, 8]`` by
    ``(v - min) / (max - min) * 8`` over the *whole* centroid range, so the
    image needs the same affine to line up with the nodes.

    The axis order is the subtle part. suite2p's ``med`` is ``(row, column)`` —
    verified against the ROIs' own ``ypix``/``xpix`` — but ``suite2pToAdjm.m``
    (and this port, for parity) stores it as if it were ``(x, y)``. So the
    plotted x axis is really the pixel *row* and the plotted y axis the pixel
    *column*, and the image has to be transposed to match. Transposing the
    picture rather than fixing ``coords`` keeps exact parity with MATLAB's
    stored coordinates while still putting each node on its own soma.
    """
    if mean_img is None:
        return None
    img = np.asarray(mean_img, dtype=float)
    if img.ndim != 2 or img.size == 0:
        return None
    min_xy, max_xy = coord_norm
    span = float(max_xy) - float(min_xy)
    if not np.isfinite(span) or span <= 0:
        return None

    def to_coord(v: float) -> float:
        return (v - float(min_xy)) / span * 8.0

    n_rows, n_cols = img.shape
    # x axis ← pixel row, y axis ← pixel column (see above).
    extent = (to_coord(0), to_coord(n_rows - 1), to_coord(0), to_coord(n_cols - 1))
    return img.T, extent


def _resolve_cell_types(params, rec, channels, log):
    """Read a recording's cell-type spreadsheet once, for every consumer of it.

    Returns ``(groups, (marker_matrix, marker_names))``, either of which may be
    ``None`` when no usable spreadsheet is found — cell-type features then
    simply don't appear, and the rest of the run is unaffected.

    The two outputs are deliberately different things. ``groups`` is the
    *user's* grouping (excitatory vs inhibitory, or one group per marker) and
    drives the subnetwork analysis and the by-cell-type comparisons.
    ``marker_matrix`` is the raw spreadsheet membership — every marker,
    uncollapsed — and is what the network plots draw as concentric rings, so a
    node shows its full genetic identity regardless of how it was grouped.
    """
    from meanap.catnap import subnetwork as sn

    try:
        path = (Path(params.twop_cell_type_file) if params.twop_cell_type_file
                else sn.find_cell_type_file(params.raw_data, rec.filename))
        if path is None or not Path(path).exists():
            return None, None
        table = sn.load_cell_type_table(path)
        marker_matrix, marker_names = sn.build_marker_matrix(table, channels)
        groups = sn.resolve_groups(table, channels, params.twop_subnetwork_groups)
    except Exception as e:
        log(f"  [{rec.filename}] warning: could not read cell types: {e}")
        return None, None

    counts = ", ".join(f"{k}={v}" for k, v in groups.counts().items())
    log(f"  [{rec.filename}] cell types from {Path(path).name}: "
        f"{len(marker_names)} markers; groups: {counts or 'none'}")
    markers = (marker_matrix, marker_names) if marker_names else None
    return (groups if groups.n_groups else None), markers


def _build_source(params: Params, log):
    """The source a run reads recordings from — local folder or remote store.

    Also fills in the two folders a remote run needs but nobody should have to
    configure: the fetch cache and the derived-data directory both default
    under ``output_data_folder``, shared across runs so neither the download nor
    the denoising is repeated.
    """
    from meanap.remote.source import RecordingSource
    from meanap.params import default_cache_dir, default_derived_dir
    from meanap.remote import open_store
    from meanap.remote.cache import FileCache, resolve_budget

    store = open_store(params)
    params.derived_data_folder = default_derived_dir(params, store.copies)
    if not store.copies:
        return RecordingSource(store=store, cache=None, log=log)

    cache_dir = default_cache_dir(params)
    budget = resolve_budget(cache_dir, params.cache_budget_gb)
    log(f"Remote data: {store}")
    log(f"  cache   {cache_dir}  ({budget / 1e9:.1f} GB budget, "
        f"prefetch depth {params.prefetch_depth})")
    log(f"  derived {params.derived_data_folder}")
    return RecordingSource(
        store=store, cache=FileCache(root=cache_dir, budget_bytes=budget), log=log,
        derived_root=params.derived_data_folder or None)


def _reload_for_plots(params, rec, state, log, source=None):
    """Re-open the recording's suite2p folder, only if something still needs it.

    Phase 1 deliberately drops the fluorescence matrices (hundreds of MB each),
    and it now also captures the mean-projection backdrop (``state.background``)
    while that data is open. So the *only* remaining reason to re-read the raw
    folder is the per-cell trace figures. With ``num_2p_traces = 0`` — express
    mode's usual case — a whole batch touches each recording's raw data exactly
    once, which is what makes streaming it through a bounded cache viable.
    """
    if not params.num_2p_traces:
        return None, state.background
    try:
        # The folder may have been released after phase 1; ask the source for
        # it again rather than assuming the path still resolves.
        plane0 = (source.plane0(rec.filename) if source is not None
                  else state.plane0)
        data = load_suite2p(plane0, params.derived_data_folder or None,
                            rec.filename)
    except Exception as e:
        log(f"  [{rec.filename}] warning: could not re-read suite2p data: {e}")
        return None, state.background
    return data, state.background


def _no_trace_reason(params, data) -> str | None:
    """Why this recording can draw no peak-detection figures, or ``None``.

    Every branch here used to be a silent ``return []`` inside
    :func:`plot_2p_traces` — the figures simply did not appear, in a run that
    reported no error, and the express bundle that travelled afterwards was the
    only record anyone had.
    """
    if data is None:
        return "its suite2p folder could not be re-read (see the warning above)"
    if data.F_denoised is None or data.peak_start_frames is None:
        measures = activity_types(params)
        if not any(a in _NEEDS_DENOISING for a in measures):
            named = " or ".join(repr(a) for a in measures)
            return (f"activity type {named} does not denoise, "
                    "and these figures plot the denoised trace against the "
                    "detected events — use 'peaks' to get them")
        return ("no denoised traces were found for it — denoising did not run "
                "or its output is missing from the derived-data folder")
    if not int(data.cell_mask.sum()):
        return "iscell.npy labels none of its ROIs as cells"
    return None


def _plot_traces(params, rec, output_root, log, data=None) -> None:
    """The per-cell peak-detection trace figures for one recording.

    Split out from the network figures because they are the one family that is
    the same under every measure of activity: they plot the raw and denoised
    fluorescence against the detected events, none of which depends on which
    measure the adjacency was built from. A multi-measure run draws them once,
    into the primary measure's tree.

    They are also the one family a bundle cannot rebuild — they need the full
    fluorescence matrices, which are hundreds of MB and deliberately not
    carried — which is why express mode still draws them.
    """
    from meanap.catnap.plotting import plot_2p_traces

    if not params.num_2p_traces:
        return
    # Say why when there is nothing to draw. These are the one family a bundle
    # cannot rebuild, so a run that quietly skips them leaves the reader looking
    # at an empty section in the viewer with nothing in the log to explain it —
    # and no way to get them back but another run.
    reason = _no_trace_reason(params, data)
    if reason:
        log(f"  [{rec.filename}] no peak-detection trace figures: {reason}")
        return
    try:
        trace_dir = (output_root / "2_NeuronalActivity"
                     / "2A_IndividualNeuronalAnalysis"
                     / rec.group / rec.filename)
        log(f"  [{rec.filename}] plotting 2P traces…")
        drawn = plot_2p_traces(data, trace_dir, rec.filename,
                               num_traces=params.num_2p_traces)
        if not drawn:
            log(f"  [{rec.filename}] warning: 2P trace plots produced no figures")
    except Exception as e:
        log(f"  [{rec.filename}] warning: 2P trace plots failed: {e}")


def _plot_recording(params, rec, state, rec_results, batch_bounds, output_root, log,
                    background=None) -> None:
    """The full step-4A network figure set for one recording and one measure.

    The network figures are the *shared* ``_plot_recording_lag`` — connectivity
    stats, the five spatial network plots (plus their batch-scaled and combined
    variants), node cartography, the two circular plots and graph-metrics-by-node
    — driven through its ``coords_all`` path so node positions come from suite2p
    cell centroids rather than an MEA electrode grid. Nothing here is duplicated
    from the electrophysiology path.

    Runs after the cartography barrier, so the cartography scatter and the
    circular cartography plot show the batch-derived boundaries and the roles
    that the CSVs report.

    Nothing is drawn in express mode: every figure here is a pure function of
    metrics the bundle already carries, so the viewer can rebuild them on
    demand. The trace figures, which it cannot, are drawn by
    :func:`_plot_traces` regardless.
    """
    from meanap.pipeline.step4 import _plot_recording_lag

    if params.express_mode:
        return

    for lag_key, metrics in rec_results.items():
        if "adjMsub" not in metrics:
            continue
        lag_ms = int(lag_key.replace("mslag", ""))
        log(f"  [{rec.filename}] network figures (lag={lag_ms}ms)…")
        try:
            _plot_recording_lag(
                rec, lag_ms, metrics, state.channels, params,
                output_root / "4_NetworkActivity", log, batch_bounds,
                coords_all=state.coords, cell_types=state.markers,
                background=background,
                node_size_scale="auto" if params.twop_auto_node_size else 1.0,
            )
        except Exception as e:
            log(f"  [{rec.filename}] warning: network plots (lag={lag_ms}) failed: {e}")


# Node-level metrics compared across cell types (whole-network role of each
# cell), and graph-level metrics compared across induced subgraphs. Both lists
# are filtered against what a given run actually produced. The names (and their
# axis labels) live in ``group_plots`` so the per-recording figures here and the
# batch comparison figures cover exactly the same metrics.
_SUBNET_NODE_METRICS = list(SUBNET_NODE_METRICS)
_SUBNET_GRAPH_METRICS = list(SUBNET_GRAPH_METRICS)


def _run_subnetwork_analysis(
    params, rec, state, rec_results, min_nodes, output_root, tables, log, rng,
    background=None,
) -> None:
    """Cell-type subnetwork analysis for one recording, across all lags.

    Guarded end-to-end: a missing/unparseable cell-type spreadsheet or a
    failing figure logs a warning and leaves the rest of the run intact — the
    core CAT-NAP outputs never depend on this.

    Runs in phase 3, after the cartography barrier, so the whole-network node
    metrics it splits by cell type carry the batch-derived roles.
    """
    from meanap.catnap import subnetwork as sn
    from meanap.catnap import subnetwork_plotting as snp

    groups = state.groups
    if groups is None or groups.n_groups == 0:
        log(f"  [{rec.filename}] subnetworks: no cell-type groups — skipping")
        return

    for lag_key, full_metrics in rec_results.items():
        if "adjMsub" not in full_metrics:
            continue
        lag_ms = int(lag_key.replace("mslag", ""))
        adj_full = state.adjMs[f"adjM{lag_ms}mslag"]
        base = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div, "Lag": lag_key}
        out_dir = (output_root / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
                   / rec.group / rec.filename / timescale_folder(lag_ms, params)
                   / "cellTypeSubnetworks")

        try:
            log(f"  [{rec.filename}] subnetwork metrics (lag={lag_ms}ms)…")
            results = sn.compute_subnetwork_metrics(
                adj_full, state.spike_counts, state.duration_s, groups, params,
                min_nodes=min_nodes, rng=rng, full_metrics=full_metrics,
            )
            summary = pd.DataFrame(sn.subnetwork_summary_rows(results))
            node_df = sn.split_node_metrics(full_metrics, groups, state.channels,
                                            adj_m=adj_full)

            # Edge mixing is measured on the analysed (active) subgraph, so it
            # describes the same network the whole-network metrics do.
            active = np.asarray(full_metrics["activeChannelIndex"], dtype=int)
            active_groups = groups.subset(active)
            edge_mix = sn.compute_edge_mix(full_metrics["adjMsub"], active_groups)
        except Exception as e:
            log(f"  [{rec.filename}] warning: subnetwork metrics (lag={lag_ms}) failed: {e}")
            continue

        tables["summary"].extend(dict(base, **row) for row in summary.to_dict("records"))
        tables["node"].extend(dict(base, **row) for row in node_df.to_dict("records"))
        tables["mix"].extend(dict(base, **row) for row in edge_mix.to_dict("records"))

        # The metrics above are data and always computed; only the figures below
        # are reconstructable from them, so express mode stops here.
        if params.express_mode:
            continue

        title = f"{rec.filename}  {lag_ms} ms {timescale_label(params)}"
        coords_active = state.coords[active]
        figures = [
            ("1_CellTypeNetwork.png",
             lambda p: snp.plot_subnetwork_spatial(
                 full_metrics["adjMsub"], coords_active, active_groups, p, title)),
            ("2_SubnetworkGraphs.png",
             lambda p: snp.plot_subnetwork_panels(
                 full_metrics["adjMsub"], coords_active, active_groups, p, title)),
            ("3_NodeMetricsByCellType.png",
             lambda p: snp.plot_node_metrics_by_group(
                 node_df, _SUBNET_NODE_METRICS, p,
                 f"{title} — whole-network node metrics by cell type",
                 # Its own stream, not the shared one: the jitter would
                 # otherwise depend on how much randomness the metrics above
                 # happened to consume first, and a viewer rebuilding this
                 # figure could never land on the same offsets.
                 make_rng(params.random_seed, "catnap_subnetwork_plot",
                          rec.filename, lag_key))),
            ("4_SubnetworkMetrics.png",
             lambda p: snp.plot_subnetwork_metric_bars(
                 summary, _SUBNET_GRAPH_METRICS, p,
                 f"{title} — metrics of each cell-type subnetwork")),
            ("5_EdgeMixing.png",
             lambda p: snp.plot_edge_mix_matrix(
                 edge_mix, active_groups, p, f"{title} — connectivity within/between cell types")),
        ]
        for name, draw in figures:
            try:
                draw(out_dir / name)
            except Exception as e:
                log(f"  [{rec.filename}] warning: subnetwork figure {name} failed: {e}")

        if params.twop_subnetwork_network_plots:
            _plot_subnetwork_figure_set(
                params, rec, state, results, full_metrics, lag_ms,
                output_root / "4_NetworkActivity", log, background,
            )


def _plot_subnetwork_figure_set(
    params, rec, state, results, full_metrics, lag_ms, net_dir, log,
    background=None,
) -> None:
    """Draw the whole step-4A figure set again, once per cell-type subnetwork.

    Same renderer as the whole network (``_plot_recording_lag``), pointed at
    each group's induced subgraph and its own nodes' coordinates — so
    ``cellTypeSubnetworks/Inhibitory/2_MEA_NetworkPlot.png`` can be read
    directly against the whole-network figure of the same name.

    Cartography roles inside a subnetwork are re-classified against the
    **whole-network** boundaries. The subgraph's own pooled PC/Z would put its
    boundaries somewhere else entirely, and then a "connector hub" would mean a
    different thing in each panel; sharing the boundaries keeps the roles
    comparable, which is the point of drawing them side by side.
    """
    from meanap.pipeline import network_metrics as nm
    from meanap.pipeline.step4 import _plot_recording_lag

    bounds = full_metrics.get("cartographyBoundaries")

    for name, metrics in results.items():
        if name == WHOLE_NETWORK or "adjMsub" not in metrics:
            continue
        idx = np.asarray(metrics.get("subnetworkNodeIndex", []), dtype=int)
        if idx.size == 0:
            continue

        metrics = dict(metrics)
        if bounds is not None and "PC" in metrics and "Z" in metrics:
            nd_cart_div, pop_num_nc = nm.classify_node_cartography(
                np.asarray(metrics["PC"], dtype=float),
                np.asarray(metrics["Z"], dtype=float), *bounds,
            )
            metrics["NdCartDiv"] = nd_cart_div
            metrics["cartographyBoundaries"] = bounds
            a_n = max(int(metrics.get("aN", 0)), 1)
            for i in range(6):
                metrics[f"NCpn{i + 1}"] = float(pop_num_nc[i] / a_n)
                metrics[f"NCpn{i + 1}count"] = int(pop_num_nc[i])

        markers = None
        if state.markers is not None:
            marker_matrix, marker_names = state.markers
            markers = (np.asarray(marker_matrix)[idx], marker_names)

        try:
            _plot_recording_lag(
                rec, lag_ms, metrics, state.channels[idx], params,
                net_dir, log, {},
                coords_all=state.coords[idx], cell_types=markers,
                sub_dir=f"cellTypeSubnetworks/{_safe_dir(name)}",
                background=background,
                node_size_scale="auto" if params.twop_auto_node_size else 1.0,
            )
        except Exception as e:
            log(f"  [{rec.filename}] warning: subnetwork figures for {name} "
                f"(lag={lag_ms}) failed: {e}")


def _safe_dir(name: str) -> str:
    """Folder-safe cell-type group name (``NeuN+ & ~GAD+`` → ``NeuN+_GAD+``)."""
    import re
    return re.sub(r"[^\w.+-]+", "_", str(name)).strip("_") or "group"


def _plot_group_comparisons(
    params, recordings, all_results, all_stats, all_channels, tables, states,
    output_root, log,
) -> None:
    """Batch group × age comparison figures — the CAT-NAP counterpart of the
    ephys ``2B_``/``4B_GroupComparisons`` folders.

    Three families, each guarded independently: a plotting failure costs the
    run nothing, since every metric and CSV is already on disk by this point.

    - **Two-photon activity** — event rate, amplitude, duration and area, the
      calcium equivalent of step 2's firing-rate comparisons.
    - **Network metrics** — the *shared* step-4 comparison plotter, unchanged:
      CAT-NAP's per-recording results dict has the same shape as the ephys one.
    - **Cell-type subnetworks** — only when the subnetwork analysis ran.
    """
    from meanap.catnap import group_plots as gp
    from meanap.pipeline.plotting_step4 import plot_step4_group_comparisons

    order = params.custom_grp_order or None
    express = params.express_mode
    log("  Writing batch tables…" if express else "  Generating group comparison plots…")

    # The pooled frames are *data*, not figures — express mode still needs them
    # for the CSVs. In full mode the plotter derives the same frames internally
    # (``plot_twop_group_comparisons`` calls ``twop_stats_frames`` itself), so
    # neither path recomputes anything the other doesn't.
    df_node = pd.DataFrame()
    try:
        if express:
            _, df_node = gp.twop_stats_frames(recordings, all_stats, all_channels)
        else:
            _, df_node = gp.plot_twop_group_comparisons(
                recordings, all_stats, output_root / "2_NeuronalActivity",
                custom_grp_order=order, channels_by_rec=all_channels,
            )
    except Exception as e:
        log(f"  Warning: two-photon activity group comparisons failed: {e}")

    # The same activity metrics again, split by cell type, plus how many cells
    # of each type each recording had.
    groups_by_rec = {name: st.groups for name, st in states.items() if st.groups}
    if groups_by_rec:
        try:
            composition = gp.composition_frame(
                recordings, groups_by_rec, all_channels,
                active_by_rec=gp.active_channels(df_node),
            )
            if not express:
                by_type = gp.add_cell_type_column(df_node, groups_by_rec, all_channels)
                gp.plot_activity_by_cell_type(
                    by_type, composition, output_root / "2_NeuronalActivity",
                    custom_grp_order=order,
                )
            if not composition.empty:
                composition.to_csv(
                    output_root / "2_NeuronalActivity" / "CellTypeComposition.csv",
                    index=False,
                )
        except Exception as e:
            log(f"  Warning: by-cell-type activity comparisons failed: {e}")

    if express:
        return

    try:
        plot_step4_group_comparisons(
            recordings, all_results, output_root / "4_NetworkActivity", order,
            timescale=timescale_kind(params),
        )
    except Exception as e:
        log(f"  Warning: network group comparison plots failed: {e}")

    if tables["summary"] or tables["node"]:
        try:
            gp.plot_subnetwork_group_comparisons(
                tables["summary"], tables["node"],
                output_root / "4_NetworkActivity", order,
                timescale=timescale_kind(params),
            )
        except Exception as e:
            log(f"  Warning: cell-type subnetwork group comparison plots failed: {e}")


#: The three batch-level cell-type subnetwork CSVs.
_SUBNETWORK_FILES = {
    "summary": "Subnetwork_RecordingLevel.csv",
    "node": "Subnetwork_NodeLevel.csv",
    "mix": "Subnetwork_EdgeMix.csv",
}


def _save_subnetwork_results(params: Params, tables: dict[str, dict[str, list]],
                             output_root: Path, log) -> None:
    """Write the cell-type subnetwork CSVs, per measure and pooled.

    Each measure's subtree gets its own copy holding only its rows, so the
    subtree reads as a complete run; the top level gets every measure's rows in
    one file with an ``ActivityType`` column, which is the form the statistics
    step compares measures from.
    """
    measures = activity_types(params)
    multi = is_multi_activity(params)
    for key, filename in _SUBNETWORK_FILES.items():
        pooled: list[dict] = []
        for activity in measures:
            rows = tables.get(activity, {}).get(key) or []
            if not rows:
                continue
            tagged = [dict(row, ActivityType=activity) for row in rows] if multi else rows
            pooled.extend(tagged)
            if not multi:
                continue
            sub_dir = (output_root / (_state_subdir(params, activity) or "")
                       / "4_NetworkActivity")
            try:
                sub_dir.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(rows).to_csv(sub_dir / filename, index=False)
            except Exception as e:
                log(f"  Warning: could not save {activity} {filename}: {e}")
        if not pooled:
            continue
        try:
            pd.DataFrame(pooled).to_csv(
                output_root / "4_NetworkActivity" / filename, index=False)
        except Exception as e:
            log(f"  Warning: could not save {filename}: {e}")


def _save_catnap_results(
    params: Params,
    recordings: list[RecordingInfo],
    all_results: dict[str, dict[str, dict]],
    all_stats: dict[str, dict[str, dict]],
    all_channels: dict[str, dict[str, np.ndarray]],
    output_root: Path,
    log: Callable[[str], None],
    sampling_rates: dict[str, float] | None = None,
) -> None:
    """Write netmet_results.json + the NetworkActivity / TwoPhotonActivity CSVs
    (compact port of the save block in ``step4._run_step4_network_metrics``).

    ``sampling_rates`` adds a ``samplingRateHz`` column to the recording-level
    tables. It is the only place the rate reaches disk in a readable form —
    params.json cannot carry it, because it is per recording rather than per
    run — and it is what the HTML report and the bundle viewer read back.

    Each measure's ``netmet_results.json`` goes in that measure's own subtree,
    unchanged in shape, so the viewer and the exporter can read a subtree
    exactly as they read any run. The four CSVs are written twice over: once per
    subtree with that measure's rows alone, and once at the top level with every
    measure's rows carrying an ``ActivityType`` column. The pooled copy is what
    :mod:`meanap.stats.measures` compares, and it is why a multi-measure run is
    one run rather than several that happen to share a parent folder.
    """
    rates = sampling_rates or {}
    measures = activity_types(params)
    multi = is_multi_activity(params)

    def tag(rows: list[dict], activity: str) -> list[dict]:
        """Rows with the measure named, positioned before the metrics."""
        if not multi:
            return rows
        return [dict(ActivityType=activity, **row) for row in rows]

    def write(frame: "pd.DataFrame | list[dict]", root: Path, rel: str) -> None:
        frame = pd.DataFrame(frame) if not isinstance(frame, pd.DataFrame) else frame
        if frame.empty:
            return
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)

    pooled: dict[str, list[dict]] = {
        "net_rec": [], "net_node": [], "act_rec": [], "act_node": []}

    try:
        for activity in measures:
            root_act = output_root / (_state_subdir(params, activity) or "")
            results_act = all_results.get(activity) or {}
            stats_act = all_stats.get(activity) or {}
            channels_act = all_channels.get(activity) or {}

            json_results = {
                rec_name: {
                    lag: {k: v for k, v in metrics.items() if k != "adjMsub"}
                    for lag, metrics in rec_results.items()
                }
                for rec_name, rec_results in results_act.items()
            }
            net_dir = root_act / "4_NetworkActivity"
            net_dir.mkdir(parents=True, exist_ok=True)
            with open(net_dir / "netmet_results.json", "w") as fh:
                json.dump(_convert_numpy(json_results), fh, indent=2)

            rec_rows, node_rows = _network_rows(recordings, results_act, rates)
            act_rows = _activity_rows(recordings, stats_act, rates)
            _, node_stats = twop_stats_frames(recordings, stats_act, channels_act)
            act_node_rows = node_stats.to_dict("records") if not node_stats.empty else []

            pooled["net_rec"].extend(tag(rec_rows, activity))
            pooled["net_node"].extend(tag(node_rows, activity))
            pooled["act_rec"].extend(tag(act_rows, activity))
            pooled["act_node"].extend(tag(act_node_rows, activity))

            if multi:
                write(rec_rows, root_act,
                      "4_NetworkActivity/NetworkActivity_RecordingLevel.csv")
                write(node_rows, root_act,
                      "4_NetworkActivity/NetworkActivity_NodeLevel.csv")
                write(act_rows, root_act,
                      "2_NeuronalActivity/TwoPhotonActivity_RecordingLevel.csv")
                write(act_node_rows, root_act,
                      "2_NeuronalActivity/TwoPhotonActivity_NodeLevel.csv")

        write(pooled["net_rec"], output_root,
              "4_NetworkActivity/NetworkActivity_RecordingLevel.csv")
        write(pooled["net_node"], output_root,
              "4_NetworkActivity/NetworkActivity_NodeLevel.csv")
        write(pooled["act_rec"], output_root,
              "2_NeuronalActivity/TwoPhotonActivity_RecordingLevel.csv")
        write(pooled["act_node"], output_root,
              "2_NeuronalActivity/TwoPhotonActivity_NodeLevel.csv")
    except Exception as e:
        log(f"  Warning: could not save CAT-NAP results: {e}")


def _network_rows(
    recordings: list[RecordingInfo], all_results: dict[str, dict],
    rates: dict[str, float],
) -> tuple[list[dict], list[dict]]:
    """One measure's network metrics as recording-level and node-level rows.

    A metric with one value per recording goes in the first table and one with
    a value per node in the second; ``adjMsub`` and the NMF matrices are neither
    and are skipped.
    """
    rec_rows: list[dict] = []
    node_rows: list[dict] = []
    for rec in recordings:
        if rec.filename not in all_results:
            continue
        for lag, metrics in all_results[rec.filename].items():
            base = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div,
                    "Lag": lag}
            if rec.filename in rates:
                base["samplingRateHz"] = rates[rec.filename]
            rec_row = dict(base)
            node_metrics = {}
            for k, v in metrics.items():
                if k == "adjMsub" or k in _NMF_NON_NODE_KEYS:
                    continue
                is_array = isinstance(v, (list, np.ndarray))
                if not is_array or np.size(v) <= 1:
                    rec_row[k] = v[0] if is_array and np.size(v) == 1 else v
                else:
                    node_metrics[k] = v
            rec_rows.append(rec_row)
            if node_metrics:
                num_nodes = len(next(iter(node_metrics.values())))
                for ch in range(num_nodes):
                    node_row = dict(base, Channel=ch + 1)
                    for k, arr in node_metrics.items():
                        if len(arr) == num_nodes:
                            node_row[k] = arr[ch]
                    node_rows.append(node_row)
    return rec_rows, node_rows


def _activity_rows(
    recordings: list[RecordingInfo], all_stats: dict[str, dict],
    rates: dict[str, float],
) -> list[dict]:
    """One measure's two-photon activity stats, one row per recording.

    ``samplingRateHz`` sits next to DIV rather than among the metrics: it
    describes how the recording was acquired, not something measured in it, and
    every rate below is derived from it.
    """
    return [dict({"FileName": r.filename, "Grp": r.group, "DIV": r.div},
                 **({"samplingRateHz": rates[r.filename]}
                    if r.filename in rates else {}),
                 **{k: v for k, v in all_stats[r.filename].items()
                    if np.size(v) <= 1})
            for r in recordings if r.filename in all_stats]
