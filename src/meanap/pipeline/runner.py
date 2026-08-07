"""Top-level pipeline runner, orchestrating steps to mirror ``MEApipeline.m``."""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Callable

from meanap.params import (
    PARAMS_FILENAME, Params, default_cache_dir, is_remote_url, save_params,
)
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import (
    RAW_EXTENSIONS,
    load_raw_recording,
    save_spike_times_npz,
)
from meanap.pipeline.step2 import _run_step2_neuronal_activity
from meanap.pipeline.step3 import _run_step3_functional_connectivity
from meanap.pipeline.step4 import _run_step4_network_metrics
from meanap.pipeline.output_folders import (
    create_output_folders, next_free_output_name, output_name_taken,
)
from meanap.pipeline.progress import (
    ProgressFn, RunProgress, plan_catnap, plan_ephys,
)
from meanap.pipeline.resume import build_input_locator, missing_step_inputs
from meanap.pipeline.spike_detection import SpikeDetectionParams, detect_spikes_recording
from meanap.pipeline.spreadsheet import RecordingInfo, read_recording_csv


def default_output_folder_name() -> str:
    """Default output folder name, matching MATLAB's ``'OutputData' + ddmmmyyyy``."""
    return "OutputData" + datetime.date.today().strftime("%d%b%Y")


def resumes_in_place(params: Params) -> bool:
    """Whether this run *means* to write into an existing output folder.

    Starting mid-pipeline with nothing else configured to read from is the
    "continue where I left off" case: the earlier steps' output is in that
    folder, and the run is going to read it. Renaming there would strand the
    inputs — so the collision check has to know the difference between
    re-entering a run and landing on top of an unrelated one.
    """
    return (
        params.start_analysis_step > 1
        and not params.prior_analysis
        and not params.spike_detected_data
        and bool(params.output_data_folder_name)
    )


def resolve_output_folder_name(
    params: Params, log: Callable[[str], None] = print,
) -> str:
    """The folder name this run writes to, avoiding an existing run's.

    Both the folder and the ``.meanap`` beside it are checked — see
    :func:`~meanap.pipeline.output_folders.output_name_taken`. Set
    ``Params.overwrite_existing_output`` to land on it deliberately.
    """
    name = params.output_data_folder_name or default_output_folder_name()
    parent = Path(params.output_data_folder or ".")

    if resumes_in_place(params) or params.overwrite_existing_output:
        if params.overwrite_existing_output and output_name_taken(parent, name):
            log(f"Overwriting the existing run in {parent / name} (as configured).")
        return name

    if not output_name_taken(parent, name):
        return name

    fresh = next_free_output_name(parent, name)
    log(f"'{name}' already holds a run — writing to '{fresh}' instead so it is "
        f"not overwritten.")
    log(f"  To replace the earlier run instead, delete it or set "
        f"Params.overwrite_existing_output = True.")
    return fresh


def run_pipeline(
    params: Params,
    log: Callable[[str], None] = print,
    should_cancel: CancelCheck = None,
    progress: "ProgressFn | None" = None,
) -> Path:
    """Run the pipeline steps in ``[start_analysis_step, stop_analysis_step]``.

    Creates the same output folder tree as the MATLAB pipeline
    (``CreateOutputFolders.m``) up front, then runs each requested step.
    Steps 1-4 are all implemented (see ``python/PIPELINE_PORT_STATUS.md`` for
    which parts of each step have exact MATLAB parity vs. are deterministic
    approximations / not yet ported).

    ``should_cancel``, if given, is polled at step boundaries and once per
    recording inside each step; when it returns ``True`` the run unwinds by
    raising :class:`~meanap.pipeline.cancellation.PipelineCancelled`. Callers
    that offer a Stop button should catch that and treat it as a clean stop.

    ``progress``, if given, receives a :class:`~meanap.pipeline.progress.Progress`
    snapshot as each recording finishes — a completed fraction and a calibrated
    estimate of the time left. It is called from whichever thread the pipeline
    runs on, so a UI must marshal it (a Qt signal already does).

    When ``params.start_analysis_step > 1`` the inputs the starting step needs
    are resolved through :mod:`meanap.pipeline.resume` — this run's output
    folder first, then ``prior_analysis_path``/``spike_detected_data`` — and
    validated before any compute starts.
    """
    if not params.spreadsheet_file_name:
        raise ValueError("Spreadsheet file must be set")
    if not params.output_data_folder:
        raise ValueError("Output data folder must be set")

    recordings = read_recording_csv(params.spreadsheet_file_name, params.spreadsheet_range)
    if not recordings:
        raise ValueError("No recordings found in the given spreadsheet range")
    group_names = sorted({r.group for r in recordings})

    reporter = RunProgress(progress, express=params.express_mode)
    reporter.plan(
        plan_catnap(n_recordings=len(recordings)) if params.suite2p_mode
        else plan_ephys(
            start_step=params.start_analysis_step,
            stop_step=params.stop_analysis_step,
            n_recordings=len(recordings),
            stimulation=params.stimulation_mode,
        )
    )

    folder_name = resolve_output_folder_name(params, log)
    output_root = create_output_folders(
        Path(params.output_data_folder), folder_name, group_names,
        include_not_box_plots=params.include_not_box_plots,
    )
    log(f"Output folder ready: {output_root}")

    # Snapshot the settings alongside the results. Until this, an output folder
    # recorded nothing about how it was produced — and every plotting routine
    # reads Params, so reconstructing a figure later needs it.
    try:
        save_params(params, output_root)
    except Exception as e:
        log(f"Warning: could not write {PARAMS_FILENAME}: {e}")

    # Raises on a misconfigured prior-analysis/spike-data path, before any work.
    locator = build_input_locator(params, output_root)
    if locator.is_resuming:
        for line in locator.describe():
            log(line)

    if params.random_seed is None:
        log("Random seed: not set — stochastic steps (3, 4) will differ between runs.")
    else:
        log(f"Random seed: {params.random_seed} — stochastic steps are reproducible.")

    # A remote source is checked before any transfer: listing is free, and a
    # batch that silently shrinks is the failure worth spending seconds to avoid.
    if is_remote_url(params.raw_data):
        _check_remote_source(params, recordings, log, reporter)

    # CAT-NAP (suite2p calcium imaging) path. In MATLAB, Params.suite2pMode == 1
    # replaces spike detection + connectivity (steps 1 & 3) with suite2pToAdjm,
    # swaps step-2 stats for calTwopActivityStats, and feeds the shared step-4
    # network metrics. We run that whole flow here instead of the ephys steps —
    # the raw MEA .mat files those steps expect don't exist for 2P data.
    if params.suite2p_mode:
        log("\n=== CAT-NAP (suite2p) pipeline ===")
        from meanap.catnap.pipeline import RESUME_STEP, run_catnap_pipeline

        # CAT-NAP has no step 1 or 3 — adjacency is built in step 2, as in
        # MATLAB — so step 4 is the only boundary the step range can act on.
        # Say so rather than silently ignoring a setting the Pipeline tab
        # happily lets the user change.
        if 1 < params.start_analysis_step < RESUME_STEP:
            log(f"  Note: starting at step {params.start_analysis_step} is the same as "
                "starting at step 1 in CAT-NAP mode — only step 4 can be resumed.")
        if params.stop_analysis_step < RESUME_STEP:
            log(f"  Note: stopping at step {params.stop_analysis_step} has no effect in "
                "CAT-NAP mode — the calcium path runs as one step.")
        if params.start_analysis_step >= RESUME_STEP:
            _check_catnap_resume_inputs(locator, recordings, params, log)

        run_catnap_pipeline(
            params, recordings, output_root, log, should_cancel, locator=locator,
            progress=reporter,
        )
        if params.express_mode:
            _write_run_bundle(params, recordings, output_root, log, mode="catnap",
                              embedded_figures=["2p_traces"] if params.num_2p_traces else [])
        reporter.finish()
        return output_root

    start = params.start_analysis_step
    stop = params.stop_analysis_step
    if start > stop:
        raise ValueError(
            f"Start step ({start}) is after stop step ({stop}) — nothing to run."
        )

    # Fail fast when resuming with nothing to resume from. Without this a bad
    # path just makes every recording log "SKIP: spike data not found" and the
    # run "succeeds" with empty CSVs.
    if start > 1:
        missing = missing_step_inputs(locator, recordings, start)
        if len(missing) == len(recordings):
            detail = "; ".join(f"{name}: {', '.join(gaps)}" for name, gaps in missing.items())
            hint = (
                "Enable 'Use prior analysis' and set the previous analysis folder"
                if not locator.is_resuming
                else "Check that the previous analysis folder holds these recordings"
            )
            raise ValueError(
                f"Cannot start at step {start}: no recording has the inputs it needs "
                f"({detail}). {hint}, or start at step 1."
            )
        for name, gaps in missing.items():
            log(f"  ! {name} will be skipped — missing {', '.join(gaps)}")

    # Port of MEApipeline.m's Params.timeProcesses: tic/toc around each step,
    # gated by the same flag, printed in the same "Step N duration (seconds):
    # X" format at the end of the run. Additionally (MATLAB has no equivalent
    # of this) tracks a total across whichever steps actually ran, and — since
    # this port has no single chained .mat file to eyeball afterward — writes
    # a small step_durations.json into the output folder so timings can be
    # read back programmatically (e.g. for a MATLAB-vs-Python speed
    # comparison) instead of scraped from the log.
    step_durations: dict[int, float] = {}
    pipeline_start = time.perf_counter() if params.time_processes else None

    def _run_timed_step(step_num: int, fn: Callable[[], None]) -> None:
        if not params.time_processes:
            fn()
            return
        t0 = time.perf_counter()
        fn()
        step_durations[step_num] = time.perf_counter() - t0

    if start <= 1 <= stop:
        check_cancel(should_cancel)
        _run_timed_step(1, lambda: _run_step1_spike_detection(
            params, recordings, output_root, log, should_cancel, reporter,
        ))
    else:
        log("Skipping step 1 (spike detection) — outside the selected step range.")

    # Stimulation analysis (MEA-Stim) — runs right after spike detection when
    # enabled, mirroring MATLAB's MEApipeline: batchDetectStim +
    # batchProcessSpikesFromStim run at the end of step 1 and stimActivityAnalysis
    # + saveEphysStatsStim at the end of step 2 — never after step 4. This port's
    # combined step consumes step-1 spike times + the raw voltage and has no
    # dependency on steps 2-4, so it runs here (before the network steps). It
    # self-skips any recording whose step-1 spikes aren't on disk yet.
    if params.stimulation_mode:
        check_cancel(should_cancel)
        from meanap.pipeline.stim_step import run_stim_analysis
        _run_timed_step(5, lambda: run_stim_analysis(
            params, recordings, output_root, log, should_cancel, reporter,
        ))

    if start <= 2 <= stop:
        check_cancel(should_cancel)
        _run_timed_step(2, lambda: _run_step2_neuronal_activity(
            params, recordings, output_root, log, should_cancel, reporter,
        ))
    else:
        log("Skipping step 2 (neuronal activity) — outside the selected step range.")

    if start <= 3 <= stop:
        check_cancel(should_cancel)
        _run_timed_step(3, lambda: _run_step3_functional_connectivity(
            params, recordings, output_root, log, should_cancel, reporter,
        ))
    else:
        log("Skipping step 3 (functional connectivity) — outside the selected step range.")

    if start <= 4 <= stop:
        check_cancel(should_cancel)
        _run_timed_step(4, lambda: _run_step4_network_metrics(
            params, recordings, output_root, log, should_cancel, reporter,
        ))
    else:
        log("Skipping step 4 (network activity) — outside the selected step range.")

    if params.express_mode:
        # Spike-detection checks are the one family here that can't be rebuilt
        # from the bundle — they need the raw voltage — so they are kept as
        # images and named in the manifest.
        _write_run_bundle(
            params, recordings, output_root, log, mode="ephys",
            embedded_figures=["spike_detection_checks"] if start <= 1 <= stop else [],
        )

    if params.time_processes:
        total_duration = time.perf_counter() - pipeline_start
        for step_num in (1, 2, 3, 4, 5):
            if step_num in step_durations:
                label = "Stim analysis" if step_num == 5 else f"Step {step_num}"
                log(f"{label} duration (seconds): {step_durations[step_num]:.1f}")
        log(f"Total pipeline duration (seconds): {total_duration:.1f}")
        try:
            with open(output_root / "step_durations.json", "w") as fh:
                json.dump(
                    {
                        **{f"step{n}": d for n, d in step_durations.items()},
                        "total": total_duration,
                    },
                    fh, indent=2,
                )
        except Exception as e:
            log(f"Warning: could not save step_durations.json: {e}")

    reporter.finish()
    return output_root


def _build_raw_source(params: Params, log):
    """The source step 1 reads recordings from — local folder or remote store."""
    from meanap.params import default_cache_dir
    from meanap.remote import open_store
    from meanap.remote.cache import FileCache, resolve_budget
    from meanap.remote.source import RecordingSource

    store = open_store(params)
    if not store.copies:
        return RecordingSource(store=store, cache=None, log=log)

    cache_dir = default_cache_dir(params)
    budget = resolve_budget(cache_dir, params.cache_budget_gb)
    log(f"Remote data: {store}")
    log(f"  cache {cache_dir}  ({budget / 1e9:.1f} GB budget, "
        f"prefetch depth {params.prefetch_depth})")
    return RecordingSource(
        store=store, cache=FileCache(root=cache_dir, budget_bytes=budget), log=log)


def _check_remote_source(params: Params, recordings, log, progress=None) -> None:
    """Pre-flight a remote source before any transfer starts.

    Listing costs nothing, so there is no reason to discover a missing
    recording after an hour of downloading — and every reason not to: a batch
    that quietly analyses a fraction of what was asked for still produces
    group comparisons and cartography boundaries, computed from the fraction.
    """
    from meanap.remote import open_store, run_preflight

    store = open_store(params)
    names = [r.filename for r in recordings]
    report = run_preflight(
        store, names,
        mode="catnap" if params.suite2p_mode else "ephys",
        spreadsheet=params.spreadsheet_file_name or None,
        cache_dir=default_cache_dir(params),
        cache_budget_gb=params.cache_budget_gb,
        prefetch_depth=params.prefetch_depth,
    )
    log("\n=== Pre-flight ===")
    for line in report.render().splitlines():
        log(line)
    # Listing already established exactly how much will be transferred, so the
    # download figure is exact from the first byte rather than growing as files
    # are discovered.
    if progress is not None and report.fetch_bytes:
        progress.expect_transfer(report.fetch_bytes)
    if not report.ok:
        raise ValueError(
            "The remote source is not ready to run (see the pre-flight report "
            "above). Fix the problems listed, or run meanap-preflight with "
            "--write-spreadsheet to correct recording names.")


def _write_run_bundle(
    params: Params, recordings, output_root: Path, log, *, mode: str,
    embedded_figures: list[str] | None = None,
) -> Path | None:
    """Pack an express run into one shareable ``.meanap`` file.

    Guarded: the output folder is already complete and usable by this point, so
    a packing failure costs the run nothing but the convenience file.
    """
    from meanap.pipeline.bundle import build_manifest, write_bundle

    try:
        manifest = build_manifest(params, recordings, mode=mode,
                                  embedded_figures=embedded_figures)
        path = write_bundle(output_root, manifest)
        size_mb = path.stat().st_size / 1e6
        log(f"\nBundle written: {path}  ({size_mb:.1f} MB)")
        log("  Open it in viewer mode, or pass it as the prior analysis folder "
            "to re-run from it.")
        return path
    except Exception as e:
        log(f"Warning: could not write the run bundle: {e}")
        return None


def _check_catnap_resume_inputs(locator, recordings, params: Params, log) -> None:
    """Fail fast when a CAT-NAP step-4 resume has nothing to resume from.

    Same reasoning as the ephys check in :func:`run_pipeline`: without it a
    mis-set path just logs "SKIP" for every recording and the run "succeeds"
    with empty CSVs.
    """
    missing = missing_step_inputs(
        locator, recordings, params.start_analysis_step, suite2p_mode=True)
    if len(missing) == len(recordings):
        detail = "; ".join(f"{name}: {', '.join(gaps)}" for name, gaps in missing.items())
        hint = (
            "Enable 'Use prior analysis' and set the previous analysis folder"
            if not locator.is_resuming
            else "Check that the previous analysis folder holds these recordings"
        )
        raise ValueError(
            f"Cannot start at step {params.start_analysis_step}: no recording has the "
            f"inputs it needs ({detail}). {hint}, or start at step 1."
        )
    for name, gaps in missing.items():
        log(f"  ! {name} will be skipped — missing {', '.join(gaps)}")


def _run_step1_spike_detection(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log: Callable[[str], None],
    should_cancel: CancelCheck = None,
    progress: RunProgress | None = None,
) -> None:
    if not params.raw_data:
        raise ValueError("Raw data folder must be set to run step 1 (spike detection)")

    progress = progress or RunProgress()
    progress.begin("step1", items=len(recordings))

    spike_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    cost_list = params.cost_list if isinstance(params.cost_list, list) else [params.cost_list]

    # Recordings arrive with the next one already being fetched when the source
    # is remote, and each is released once its spike times are written — so a
    # batch's peak local storage is one or two recordings, not the dataset.
    source = _build_raw_source(params, log)
    # Set rather than passed, so a caller that substitutes its own source
    # factory — the remote tests do — doesn't have to know about progress.
    source.progress = progress

    for rec, raw_path in source.stream(recordings, depth=params.prefetch_depth,
                                       kind="ephys"):
        check_cancel(should_cancel)
        if isinstance(raw_path, BaseException):
            log(f"  ! raw file not found, skipping: {rec.filename}"
                f" (looked for {', '.join(RAW_EXTENSIONS)})")
            continue

        log(f"  [{rec.filename}] loading raw data…")
        dat, channels, fs = load_raw_recording(raw_path)

        detect_params = SpikeDetectionParams(
            fs=fs,
            thresholds=params.thresholds,
            wname_list=params.wname_list,
            cost_list=cost_list,
            filter_low_pass=params.filter_low_pass,
            filter_high_pass=params.filter_high_pass,
            ref_period_ms=params.ref_period,
            min_peak_thr_mult=params.min_peak_thr_multiplier,
            max_peak_thr_mult=params.max_peak_thr_multiplier,
            pos_peak_thr_mult=params.pos_peak_thr_multiplier,
            remove_artifacts=params.remove_artifacts,
        )

        log(f"  [{rec.filename}] detecting spikes ({len(channels)} channels)…")
        result = detect_spikes_recording(
            dat, channels, fs, detect_params,
            max_workers=params.spike_detection_channel_workers,
        )

        out_path = spike_dir / f"{rec.filename}_spikes.npz"
        save_spike_times_npz(
            out_path, result.spike_times, channels, fs,
            duration_s=dat.shape[0] / fs,
        )
        log(f"  [{rec.filename}] saved → {out_path.relative_to(output_root)}")

        # Mirrors MEApipeline.m creating a per-recording checks folder here;
        # the check plots themselves aren't ported yet.
        check_dir = output_root / "1_SpikeDetection" / "1B_SpikeDetectionChecks" / rec.group / rec.filename
        check_dir.mkdir(parents=True, exist_ok=True)
        
        from meanap.pipeline.plotting import plot_spike_detection_checks
        log(f"  [{rec.filename}] generating spike detection check plots…")
        plot_spike_detection_checks(dat, result, params, rec.filename, check_dir)

        # Spike times and the checks are on disk; the raw voltage is no longer
        # needed. An Axion plate shared with other wells is kept until the last
        # of them is done.
        del dat
        source.unpin(rec.filename)
        source.release(rec.filename)
        progress.item_done(rec.filename)

    progress.phase_done()
