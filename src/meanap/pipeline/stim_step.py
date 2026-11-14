"""Stimulation-analysis step of the pipeline (MEA-Stim).

Runs right after spike detection (step 1) when ``params.stimulation_mode`` is
set, mirroring MATLAB's ``MEApipeline.m`` — where ``batchDetectStim`` +
``batchProcessSpikesFromStim`` run at the end of step 1 and
``stimActivityAnalysis`` + ``saveEphysStatsStim`` at the end of step 2 (never
after step 4). This port folds all of it into one step. For each recording it
detects stimulation on the raw voltage, groups patterns, cleans the Python
step-1 spike times, computes the electrode-level response metrics + reservoir
matrices + shuffle test, writes the per-recording figures, and finally
aggregates every recording's rows into ``StimActivity_NodeLevel.csv``.

See ``src/meanap/stim/`` and ``python/MEASTIM_PORT_PLAN.md``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from meanap.params import Params, active_spike_method
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import (
    RAW_EXTENSIONS,
    find_raw_file,
    load_raw_recording,
    load_spike_times_npz,
    require_spike_method,
)
from meanap.pipeline.channel_layout import get_coords_from_layout
from meanap.pipeline.progress import RunProgress
from meanap.pipeline.resume import build_input_locator
from meanap.pipeline.rng import make_rng
from meanap.pipeline.spreadsheet import RecordingInfo
from meanap.stim.detection import detect_stim_times, get_stim_patterns, _matlab_mode
from meanap.stim.cleaning import clean_spikes_from_stim
from meanap.stim.psth import get_stim_artifact_duration
from meanap.stim.activity import stim_activity_analysis, write_stim_activity_csv
from meanap.stim.events import EVENT_METHODS


def _coords_for_channels(layout: str, channels: np.ndarray) -> np.ndarray:
    """Electrode coords ordered to match ``channels`` (unknown IDs → NaN)."""
    try:
        ids, xy = get_coords_from_layout(layout)
        by_id = {int(c): p for c, p in zip(ids, xy)}
    except Exception:
        by_id = {}
    return np.array([by_id.get(int(c), (np.nan, np.nan)) for c in channels], dtype=float)


def _blank_dur_mode(stim_info: list) -> float:
    durs = [np.asarray(si.non_stim_blank_ends, float).ravel()
            - np.asarray(si.non_stim_blank_starts, float).ravel()
            for si in stim_info if si.non_stim_blank_starts is not None]
    durs = np.concatenate(durs) if durs else np.array([])
    return _matlab_mode(durs) if durs.size else 0.0


def run_stim_analysis(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log=print,
    should_cancel: CancelCheck = None,
    progress: "RunProgress | None" = None,
) -> None:
    """Run the stim analysis over all recordings and write the aggregate CSV."""
    log("\n=== Stimulation analysis (MEA-Stim) ===")
    progress = progress or RunProgress()
    progress.begin("stim", items=len(recordings))
    if params.stim_detection_method in EVENT_METHODS:
        _run_event_stim_analysis(params, recordings, output_root, log,
                                 should_cancel, progress)
        return
    if not params.raw_data:
        log("  ! Raw data folder not set — stim detection needs the raw voltage. Skipping.")
        progress.phase_done()
        return

    raw_dir = Path(params.raw_data)
    # Same resolution as the numbered steps, so stim analysis can run against a
    # previous run's spike detection rather than only this run's.
    locator = build_input_locator(params, output_root)
    indiv_dir = output_root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
    method = active_spike_method(params)
    base = params.to_stim_params_dict()

    all_rows: list[dict] = []
    tables: dict[str, list[dict]] = {}
    n_done = 0
    for rec in recordings:
        check_cancel(should_cancel)
        raw_path = find_raw_file(raw_dir, rec.filename)
        npz_path = locator.spike_file(rec.filename)
        if raw_path is None:
            log(f"  ! [{rec.filename}] raw file not found, skipping"
                f" (looked for {', '.join(RAW_EXTENSIONS)})")
            continue
        if npz_path is None:
            log(f"  ! [{rec.filename}] spike times not found ({rec.filename}_spikes.npz); "
                f"run step 1 first. Skipping.")
            continue

        log(f"  [{rec.filename}] detecting stimulation…")
        dat, channels, fs = load_raw_recording(raw_path)
        dat = dat.astype(np.float64)
        coords = _coords_for_channels(params.channel_layout, channels)
        sp_params = {**base, "fs": fs}

        stim_info = detect_stim_times(dat, sp_params, channels, coords)
        stim_info, patterns = get_stim_patterns(stim_info, sp_params)
        _stim_detection_checks(params, rec, dat, stim_info, sp_params, output_root, log)
        conditions, patterns = _recording_conditions(params, rec, stim_info, patterns, log)
        n_stim_elec = sum(1 for s in stim_info if s.pattern and s.pattern > 0)
        log(f"    {len(patterns)} pattern(s), {n_stim_elec} stimulating electrode(s)")
        for k, cd in enumerate(conditions, start=1):
            label = f" = {cd.label}" if cd.label else ""
            last = f", last pulse at {cd.last_pulse_s * 1000:.1f} ms" if cd.last_pulse_s else ""
            log(f"      pattern {k}: {cd.name}{label} ({cd.onsets_s.size} trials{last})")
        if not patterns:
            log(f"    no stimulation detected on [{rec.filename}] — skipping analysis.")
            continue

        # Python step-1 spikes for this recording, filtered to the analysis method
        spikes_full = load_spike_times_npz(npz_path)
        require_spike_method(spikes_full, method, rec.filename)
        spikes = {c: {method: m[method]} for c, m in spikes_full.items() if method in m}
        spikes = clean_spikes_from_stim(spikes, stim_info, sp_params)

        info = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div,
                "FN": [rec.filename], "duration_s": dat.shape[0] / fs}

        log(f"  [{rec.filename}] computing stim response metrics…")
        rows = stim_activity_analysis(spikes, stim_info, patterns, sp_params, info)
        for r in rows:
            cd = conditions[r["pattern_id"] - 1]
            r["condition"] = cd.display_name
            r["condition_electrodes"] = cd.name
        all_rows.extend(rows)
        log(f"    {len(rows)} electrode rows")

        blank_dur_mode = _blank_dur_mode(stim_info)
        artifact_dur = get_stim_artifact_duration({**sp_params, "blankDurMode": blank_dur_mode})
        dest = indiv_dir / rec.group / rec.filename
        if params.stim_network:
            check_cancel(should_cancel)
            dest.mkdir(parents=True, exist_ok=True)
            trains = [np.asarray(spikes.get(c, {}).get(method, []), float)
                      for c in range(len(channels))]
            events = _electrical_events(conditions)
            _write_events_table(events, dest / "stim_events.csv", conditions)
            stim_nodes = np.array([s.elec_stim_times.shape[0] > 0 for s in stim_info])
            windows = {cd.display_name: _post_artifact_window(
                           params.stim_network_window, cd.last_pulse_s + artifact_dur, log,
                           cd.display_name)
                       for cd in conditions}
            _extend_tables(tables, _stim_networks(
                params, rec, info, trains, events, channels, None,
                dest, output_root / "ExperimentMatFiles", log,
                windows=windows, exclude=stim_nodes, coords=coords,
                condition_electrodes={cd.display_name: sorted(cd.channel_ids)
                                      for cd in conditions}))

        # per-recording figures
        check_cancel(should_cancel)
        _stim_figures(params, rec, dest, output_root, stim_info, patterns, spikes,
                      sp_params, artifact_dur, info, method, log)
        n_done += 1
        progress.item_done(rec.filename)

    progress.phase_done()

    if all_rows:
        csv_path = output_root / "StimActivity_NodeLevel.csv"
        write_stim_activity_csv(all_rows, csv_path)
        log(f"  Wrote {csv_path.name} ({len(all_rows)} rows across {n_done} recording(s))")
    else:
        log("  No stim rows produced (no stimulation detected in any recording).")
    _write_network_tables(tables, output_root, log)
    _stim_group_figures(params, tables, output_root, log)


def _stim_figures(params: Params, rec: RecordingInfo, dest: Path, output_root: Path,
                  stim_info, patterns, spikes, sp_params, artifact_dur, info,
                  method: str, log) -> None:
    """Save what the per-recording stim figures are drawn from, then draw them
    from that saved copy, the way the viewer will (meanap.stim.redraw)."""
    from meanap.stim.redraw import (
        FIGURES_SUFFIX, draw_activity_figures, load_figure_payload, record_figure_names,
        save_figure_payload,
    )

    try:
        path = save_figure_payload(
            output_root / "ExperimentMatFiles" / f"{rec.filename}{FIGURES_SUFFIX}",
            stim_info=stim_info, patterns=patterns, spike_times=spikes, method=method,
            params=sp_params, artifact_s=artifact_dur, info=info,
            seed=params.random_seed or 1, recording=rec.filename)
        figs = draw_activity_figures(load_figure_payload(path), dest)
        record_figure_names(path, figs, dest)
        log(f"  [{rec.filename}] wrote {len(figs)} stim figures")
    except Exception as e:   # plotting must never sink the numeric results
        log(f"  [{rec.filename}] Warning: stim plotting failed: {e}")


def _stim_detection_checks(params: Params, rec: RecordingInfo, dat: np.ndarray, stim_info: list,
                           sp_params: dict, output_root: Path, log) -> None:
    """MATLAB's stimulus detection checks (``plotStimDetectionChecks.m``), into
    ``1_SpikeDetection/1C_StimDetectionChecks/<group>/<recording>/``, drawn
    from the small file they are kept in for a bundle to redraw them."""
    from meanap.stim.detection_checks import (
        STIM_CHECKS_DIR, STIM_CHECKS_SUFFIX, compute_stim_check_data, draw_stim_check_figures,
        load_stim_check_data, save_stim_check_data,
    )

    try:
        data = compute_stim_check_data(
            dat, stim_info, sp_params, rec.filename,
            make_rng(params.random_seed or 1, "stim-checks", rec.filename))
        path = save_stim_check_data(
            output_root / "ExperimentMatFiles" / f"{rec.filename}{STIM_CHECKS_SUFFIX}", data)
        dest = output_root / STIM_CHECKS_DIR / str(rec.group) / rec.filename
        draw_stim_check_figures(load_stim_check_data(path), dest)
    except Exception as e:   # plotting must never sink the numeric results
        log(f"  [{rec.filename}] Warning: stimulus detection checks failed: {e}")


# ── Event-driven stimulation (light, TTL, event logs) ─────────────────────────

#: Where an ``eventsCSV`` run looks for a recording's events.
_EVENT_CSV_NAMES = ("{}_events.csv", "{}_stim_events.csv", "{}.events.csv")


def _find_events_csv(folders: list[Path], recording: str) -> Path | None:
    for folder in folders:
        for pattern in _EVENT_CSV_NAMES:
            candidate = folder / pattern.format(recording)
            if candidate.is_file():
                return candidate
    return None


def load_recording_events(params: Params, recording: str, log=print):
    """The recording's stimulus events, by ``params.stim_detection_method``.

    Returns a :class:`~meanap.stim.events.StimEvents`, or ``None`` (logged)
    when the source is missing.
    """
    from meanap.pipeline.import_step import find_maxwell_raw
    from meanap.pipeline.maxwell import read_maxwell_ttl
    from meanap.stim.events import (
        StimEvents, assign_conditions, describe_ttl, events_from_ttl, read_events_csv,
    )

    folders = [Path(d) for d in dict.fromkeys(
        [params.stim_events_folder, params.raw_data, params.sorted_data_folder]) if d]
    if params.stim_detection_method == "eventsCSV":
        path = _find_events_csv(folders, recording)
        if path is None:
            log(f"  ! [{recording}] no events CSV ({_EVENT_CSV_NAMES[0].format(recording)}) "
                f"in {', '.join(map(str, folders)) or 'no folder set'}")
            return None
        return read_events_csv(path)

    raw = find_maxwell_raw(folders, recording)
    if raw is None:
        log(f"  ! [{recording}] no MaxWell raw file to read TTL events from")
        return None
    times, words = read_maxwell_ttl(raw)
    detail = getattr(log, "detail", log)   # a RunLog's verbose channel, else log
    for line in describe_ttl(times, words):
        detail(f"      TTL {line}")
    ev, how = events_from_ttl(times, words, params.stim_event_ttl_rule,
                              params.stim_event_min_interval)
    conds = assign_conditions(ev, params.stim_event_condition_mode,
                              list(params.stim_event_condition_labels) or None)
    return StimEvents(ev, conds, f"{raw.name} TTL {how}")


def _baseline_windows_that_fit(events, window: tuple[float, float], default: int) -> int:
    """How many baseline windows fit between an event and the one before it.

    The baseline-AUC correction steps back ``window[1]`` at a time from
    ``window[0]``; past the previous stimulus it would measure that
    stimulus's response as baseline. At least one window is kept.
    """
    times = np.sort(np.asarray(events.times_s, float))
    if len(times) < 2 or window[1] <= 0:
        return default
    gap = float(np.min(np.diff(times)))
    fit = int(np.floor((gap + window[0]) / window[1]))
    return int(np.clip(fit, 1, default))


def _run_event_stim_analysis(params: Params, recordings: list[RecordingInfo],
                             output_root: Path, log, should_cancel, progress) -> None:
    """Stim analysis with events as the patterns and no stimulating node."""
    from meanap.pipeline.channel_layout import recording_layout
    from meanap.stim.events import stim_info_without_stim_nodes

    locator = build_input_locator(params, output_root)
    indiv_dir = output_root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
    method = active_spike_method(params)
    base = params.to_stim_params_dict()
    window = tuple(float(x) for x in params.stim_analysis_window)

    all_rows: list[dict] = []
    tables: dict[str, list[dict]] = {}
    n_done = 0
    for rec in recordings:
        check_cancel(should_cancel)
        npz_path = locator.spike_file(rec.filename)
        if npz_path is None:
            log(f"  ! [{rec.filename}] spike times not found ({rec.filename}_spikes.npz); "
                f"run step 1 first. Skipping.")
            continue
        events = load_recording_events(params, rec.filename, log)
        if events is None:
            continue

        with np.load(npz_path) as data:
            channels = np.asarray(data["channels"])
            fs = float(data["fs"][0])
            duration_s = float(data["duration_s"][0]) if "duration_s" in data.files else None
            unit_ids = np.asarray(data["unit_id"]).astype(str) if "unit_id" in data.files else None
            if "unit_coords" in data.files:
                coords = np.asarray(data["unit_coords"], float)
            else:
                layout = recording_layout(params.channel_layout, data)
                coords = (_coords_from(layout, channels) if layout is not None
                          else _coords_for_channels(params.channel_layout, channels))
        if duration_s is None:
            duration_s = max((float(t.max()) for m in load_spike_times_npz(npz_path).values()
                              for t in m.values() if len(t)), default=0.0)

        # A trial whose window runs off either end of the recording would be
        # counted as silence there.
        events = events.within(-window[0], duration_s - window[1])
        names, patterns = events.condition_names, events.patterns()
        log(f"  [{rec.filename}] {len(events.times_s)} event(s) from {events.description}; "
            f"condition(s) {', '.join(f'{n} ({len(p)})' for n, p in zip(names, patterns))}")
        if not len(events.times_s):
            log(f"    no events inside the recording — skipping analysis.")
            continue

        n_baseline = _baseline_windows_that_fit(events, window, 30)
        if n_baseline < 30:
            log(f"    baseline AUC from {n_baseline} window(s) — as many as fit "
                f"between consecutive events")
        sp_params = {**base, "fs": fs, "numBaselinePSTHs": n_baseline}

        spikes_full = load_spike_times_npz(npz_path)
        require_spike_method(spikes_full, method, rec.filename)
        spikes = {c: {method: m[method]} for c, m in spikes_full.items() if method in m}
        stim_info = stim_info_without_stim_nodes(channels, coords)
        info = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div,
                "FN": [rec.filename], "duration_s": duration_s}

        log(f"  [{rec.filename}] computing stim response metrics…")
        rows = stim_activity_analysis(spikes, stim_info, patterns, sp_params, info)
        for r in rows:
            r["condition"] = names[r["pattern_id"] - 1]
            if unit_ids is not None:
                r["unit_id"] = unit_ids[r["file_index"] - 1]
        all_rows.extend(rows)
        log(f"    {len(rows)} node rows")

        dest = indiv_dir / rec.group / rec.filename
        dest.mkdir(parents=True, exist_ok=True)
        _write_events_table(events, dest / "stim_events.csv")

        if params.stim_network:
            check_cancel(should_cancel)
            trains = [np.asarray(spikes.get(c, {}).get(method, []), float)
                      for c in range(len(channels))]
            _extend_tables(tables, _stim_networks(
                params, rec, info, trains, events, channels, unit_ids,
                dest, output_root / "ExperimentMatFiles", log,
                coords=np.array([s.coords for s in stim_info], float)))
        check_cancel(should_cancel)
        artifact_dur = get_stim_artifact_duration({**sp_params, "blankDurMode": 0.0})
        _stim_figures(params, rec, dest, output_root, stim_info, patterns, spikes,
                      sp_params, artifact_dur, info, method, log)
        n_done += 1
        progress.item_done(rec.filename)

    progress.phase_done()
    if all_rows:
        csv_path = output_root / "StimActivity_NodeLevel.csv"
        write_stim_activity_csv(all_rows, csv_path)
        log(f"  Wrote {csv_path.name} ({len(all_rows)} rows across {n_done} recording(s))")
    else:
        log("  No stim rows produced.")
    _write_network_tables(tables, output_root, log)
    _stim_group_figures(params, tables, output_root, log)


def _coords_from(layout: tuple[np.ndarray, np.ndarray], channels: np.ndarray) -> np.ndarray:
    by_id = {int(c): p for c, p in zip(*layout)}
    return np.array([by_id.get(int(c), (np.nan, np.nan)) for c in channels], dtype=float)


def _write_events_table(events, path: Path, conditions=None) -> None:
    """The events the analysis used, with their pattern number, beside its figures."""
    import pandas as pd

    names = events.condition_names
    table = {"time_s": events.times_s, "condition": events.conditions,
             "pattern_id": [names.index(c) + 1 for c in events.conditions]}
    if conditions is not None:
        by_name = {cd.display_name: cd for cd in conditions}
        table["electrodes"] = [by_name[c].name for c in events.conditions]
        table["last_pulse_ms"] = [by_name[c].last_pulse_s * 1000 for c in events.conditions]
    pd.DataFrame(table).to_csv(path, index=False)


#: The CSVs the stimulus-network analysis writes, in the order they are logged.
NETWORK_TABLES = ("StimNetwork_RecordingLevel.csv", "StimNetwork_NodeLevel.csv",
                  "StimNetworkSplitHalf_RecordingLevel.csv",
                  "StimConsistency_RecordingLevel.csv", "StimConsistency_NodeLevel.csv")


def _recording_conditions(params: Params, rec: RecordingInfo, stim_info: list,
                          patterns: list[np.ndarray], log):
    """The recording's stimulation conditions, and their onsets as the pattern list.

    With ``stim_group_sequences`` the patterns are rebuilt from pulses
    (:func:`~meanap.stim.sequences.group_sequences`); otherwise MATLAB's
    electrode grouping stands and only gains electrode names. Either way the
    ``StimConditions`` spreadsheet value labels them.
    """
    from meanap.stim.sequences import (
        apply_labels, assign_patterns, conditions_from_patterns, group_sequences,
    )

    if params.stim_group_sequences:
        conditions = group_sequences(stim_info, params.stim_sequence_gap / 1000.0, log=log)
        assign_patterns(stim_info, conditions)
        patterns = [cd.onsets_s for cd in conditions]
    else:
        conditions = conditions_from_patterns(stim_info, patterns)
    apply_labels(conditions, rec.stim_conditions, log)
    return conditions, patterns


def _electrical_events(conditions):
    """Electrical stimulation as events, one condition per stimulation pattern."""
    from meanap.stim.events import StimEvents

    times = [cd.onsets_s for cd in conditions]
    names = [np.full(len(cd.onsets_s), cd.display_name, dtype=object) for cd in conditions]
    return StimEvents(np.concatenate(times) if times else np.zeros(0),
                      np.concatenate(names) if names else np.zeros(0, object),
                      "electrical stimulation (detected)")


def _post_artifact_window(window, artifact_end: float, log,
                          condition: str = "") -> tuple[float, float]:
    """The evoked window, starting no earlier than the end of the last artifact.

    Cleaning removed every spike from each pulse's blanked artifact; an evoked
    window reaching into one would count it as silence. *artifact_end* is the
    last pulse's offset from the first plus the artifact duration.
    """
    w0, w1 = (float(x) for x in window)
    who = f"{condition}: " if condition else ""
    if w0 < artifact_end:
        if artifact_end >= w1:
            raise ValueError(f"{who}the stimulus artifact (until {artifact_end * 1000:.1f} ms) "
                             f"covers the whole evoked window {w0:g}–{w1:g} s")
        log(f"    {who}evoked window starts at {artifact_end * 1000:.2f} ms, after the "
            f"blanked artifact, rather than {w0 * 1000:g} ms")
        w0 = artifact_end
    return (w0, w1)


def _extend_tables(tables: dict[str, list[dict]], new: dict[str, list[dict]]) -> None:
    for name, rows in new.items():
        tables.setdefault(name, []).extend(rows)


def _write_network_tables(tables: dict[str, list[dict]], output_root: Path, log) -> None:
    import pandas as pd

    for name in NETWORK_TABLES:
        rows = tables.get(name)
        if rows:
            pd.DataFrame(rows).to_csv(output_root / name, index=False)
            log(f"  Wrote {name} ({len(rows)} rows)")


def _stim_group_figures(params: Params, tables: dict[str, list[dict]],
                        output_root: Path, log) -> None:
    """Half-violins of the stimulus networks by group, DIV and condition."""
    if not (params.stim_network and params.stim_group_plots) or params.express_mode:
        return
    from meanap.pipeline.channel_layout import fixed_electrode_count
    from meanap.pipeline.palette import ColorScheme
    from meanap.stim.group_plots import plot_stim_group_comparisons

    try:
        plot_stim_group_comparisons(
            tables, output_root, group_order=params.custom_grp_order or None,
            colors=ColorScheme.from_params(params),
            n_electrodes=fixed_electrode_count(params), log=log)
    except Exception as e:   # figures must never sink the numeric results
        log(f"  Warning: stimulation group-comparison plots failed: {e}")


def _embed(m: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """A node-subset matrix (or vector) back at full size, NaN for the nodes left out."""
    n = keep.size
    if m.ndim == 1:
        out = np.full(n, np.nan)
        out[keep] = m
        return out
    out = np.full((n, n), np.nan)
    out[np.ix_(keep, keep)] = m
    return out


def _embed_net(net, keep: np.ndarray):
    from dataclasses import replace

    if keep.all():
        return net
    return replace(net, sttc=_embed(net.sttc, keep), sttc_thr=_embed(net.sttc_thr, keep),
                   null_mean=_embed(net.null_mean, keep), p=_embed(net.p, keep),
                   spike_counts=_embed(net.spike_counts, keep))


def _stim_networks(params: Params, rec: RecordingInfo, info: dict, trains: list[np.ndarray],
                   events, channels: np.ndarray, unit_ids: np.ndarray | None,
                   fig_dir: Path, mat_dir: Path, log, *,
                   windows: dict[str, tuple[float, float]] | None = None,
                   exclude: np.ndarray | None = None, coords: np.ndarray | None = None,
                   condition_electrodes: dict[str, list[int]] | None = None,
                   ) -> dict[str, list[dict]]:
    """Evoked/baseline networks, noise correlations, trial consistency and
    split-half networks for one recording.

    *windows* overrides ``params.stim_network_window`` per condition (the
    electrical path starts each after its last pulse's artifact). Nodes flagged in *exclude* (stimulating
    electrodes) are left out of every network and appear as NaN in the saved
    matrices, flagged in the node-level CSVs. *coords* (electrode positions)
    and *condition_electrodes* (each condition's stimulating electrodes) are
    only for drawing the networks on the array (figure 16).

    Returns rows for each of :data:`NETWORK_TABLES`; writes the matrices to
    ``ExperimentMatFiles/<rec>_stimNetwork.npz`` and the figures beside the
    other stim figures.
    """
    from meanap.pipeline.atomic import atomic_savez
    from meanap.stim.consistency import trial_consistency
    from meanap.stim.events import StimEvents
    from meanap.stim.redraw import PAYLOAD_VERSION, _dumps, draw_network_figures
    from meanap.stim.evoked_network import (
        baseline_window, epoch_network, network_summary, noise_correlations,
        noise_summary, post_window, separated_events,
    )

    window = tuple(float(x) for x in params.stim_network_window)
    windows = {c: tuple(float(x) for x in w) for c, w in (windows or {}).items()}
    if windows:   # separate events by the longest evoked + baseline span of any condition
        window = (min(w[0] for w in windows.values()), max(w[1] for w in windows.values()))
    posts = {c: post_window(w, params.stim_network_post_window)
             for c, w in (windows or {None: window}).items()}
    reach = max(w[1] for w in posts.values())
    order = np.argsort(events.times_s, kind="stable")
    events = StimEvents(events.times_s[order], events.conditions[order], events.description)
    keep_ev = separated_events(events.times_s, window, after=reach)
    if not keep_ev.all():
        log(f"    {int((~keep_ev).sum())} event(s) too close to a neighbour for the baseline, "
            f"evoked and post-stimulus windows ({baseline_window(window)[0]:g} to "
            f"{reach:g} s) — left out of the networks")
        events = StimEvents(events.times_s[keep_ev], events.conditions[keep_ev],
                            events.description)
    if len(events.times_s) < 3:
        log(f"  ! [{rec.filename}] stimulus networks skipped: fewer than 3 usable events")
        return {}

    n_all = len(trains)
    keep = np.ones(n_all, bool) if exclude is None else ~np.asarray(exclude, bool)
    if not keep.all():
        log(f"    leaving out {int((~keep).sum())} stimulating electrode(s): "
            f"{', '.join(str(int(c)) for c in channels[~keep])}")
    sub = [t for t, k in zip(trains, keep) if k]

    rng = make_rng(params.random_seed or 1, "stim-network", rec.filename)
    # The post epoch's surrogates come from their own stream, so adding it
    # left every baseline/evoked/split-half result exactly as it was.
    post_rng = make_rng(params.random_seed or 1, "stim-network-post", rec.filename)
    base = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div}
    tables: dict[str, list[dict]] = {name: [] for name in NETWORK_TABLES}
    arrays = {}
    # What figures 13-15 are drawn from, beside the matrices: drawn from this
    # (draw_network_figures) rather than from the objects below, so a viewer
    # opening the bundle draws exactly what the run did.
    sttc_mode = params.stim_network_sttc
    if sttc_mode == "trial_mean" and params.stim_network_null != "trial_shuffle":
        log(f"  [{rec.filename}] Trial-averaged STTC needs the trial-shuffle null; "
            f"pooling the windows instead for the {params.stim_network_null} null.")
        sttc_mode = "pooled"
    meta = {"version": PAYLOAD_VERSION, "title": rec.filename,
            "null": params.stim_network_null, "sttc_mode": sttc_mode, "conditions": []}
    node_ids = unit_ids if unit_ids is not None else channels.astype(str)
    reps, alpha = params.stim_network_rep_num, params.stim_network_alpha
    log(f"  [{rec.filename}] stimulus-triggered networks ({params.stim_network_null} null, "
        f"{reps} surrogates, window {window[0]:g}–{window[1]:g} s)…")

    def node_base(i: int) -> dict:
        row = {**base, "node": i + 1, "channel_id": int(channels[i]),
               "stim_electrode": bool(not keep[i])}
        if unit_ids is not None:
            row["unit_id"] = node_ids[i]
        return row

    def epoch_net(ev, win, lag, epoch, cond, rng_=None):
        return epoch_network(sub, ev, win, lag, condition=cond, epoch=epoch,
                             null=params.stim_network_null, rep_num=reps, tail=alpha,
                             rng=rng_ or rng, sttc_mode=sttc_mode)

    for cond, ev in zip(events.condition_names, events.patterns()):
        win_c = windows.get(cond, window)
        arrays[f"{cond}__window_s"] = np.array(win_c)
        nc = noise_correlations(sub, ev, win_c, condition=cond, rep_num=reps, rng=rng)
        ns = noise_summary(nc, alpha)
        tables["StimNetwork_RecordingLevel.csv"].append(
            {**base, "condition": cond, "epoch": "noise_corr", "lag_ms": np.nan,
             "n_trials": nc.n_trials, **ns})
        arrays[f"{cond}__noise_r"] = _embed(nc.r, keep)
        arrays[f"{cond}__noise_p"] = _embed(nc.p, keep)
        post_c = posts.get(cond, posts.get(None, post_window(win_c)))
        cmeta = {"name": cond, "window_s": list(win_c), "noise_n_trials": nc.n_trials,
                 "consistency": None, "lags": [],
                 "electrodes": [int(e) for e in (condition_electrodes or {}).get(cond, [])]}
        meta["conditions"].append(cmeta)

        if params.stim_trial_consistency:
            tc = trial_consistency(sub, ev, win_c, condition=cond, alpha=alpha, rng=rng)
            tables["StimConsistency_RecordingLevel.csv"].append(
                {**base, "condition": cond, "window_s_1": win_c[0],
                 "window_s_2": win_c[1], **tc.summary})
            rho, p = _embed(tc.node_rho, keep), _embed(tc.node_p, keep)
            resp = _embed(tc.response.mean(axis=0), keep)
            for i in range(n_all):
                tables["StimConsistency_NodeLevel.csv"].append(
                    {**node_base(i), "condition": cond, "meanResponse": resp[i],
                     "driftRho": rho[i], "driftP": p[i]})
            arrays[f"{cond}__trial_evoked"] = _embed_rows(tc.evoked, keep)
            arrays[f"{cond}__trial_baseline"] = _embed_rows(tc.baseline, keep)
            arrays[f"{cond}__trial_latency"] = _embed_rows(tc.latency_s, keep)
            arrays[f"{cond}__node_rho"], arrays[f"{cond}__node_p"] = rho, p
            cons = {"summary": tc.summary}
            for kind, d in (("evoked", tc.evoked_drift), ("baseline", tc.baseline_drift)):
                arrays[f"{cond}__{kind}_drift__similarity"] = d.similarity
                arrays[f"{cond}__{kind}_drift__lag_similarity"] = d.lag_similarity
                arrays[f"{cond}__{kind}_drift__lag_null"] = d.lag_null
                cons[f"{kind}_slope"], cons[f"{kind}_slope_p"] = d.slope, d.slope_p
            cmeta["consistency"] = cons
            s = tc.summary
            log(f"    {cond}: population response ρ = {s['popResponseRho']:.2f} vs trial "
                f"(p = {s['popResponseP']:.3g}); {s['fracNodesDrifting']:.0%} of nodes "
                f"drift; pattern similarity slope p = {s['similarityLagSlopeP']:.3g} "
                f"(baseline {s['baselineSimilarityLagSlopeP']:.3g})")

        for lag in params.func_con_lag_val:
            nets = {}
            lmeta = {"lag": lag, "epochs": {}, "split_rows": None}
            cmeta["lags"].append(lmeta)
            for epoch, win in (("baseline", baseline_window(win_c)), ("evoked", win_c),
                               ("post", post_c)):
                ep_rng = post_rng if epoch == "post" else rng
                net = epoch_net(ev, win, lag, epoch, cond, ep_rng)
                summary = network_summary(net, params, params.min_activity_level, rng=ep_rng)
                tables["StimNetwork_RecordingLevel.csv"].append(
                    {**base, "condition": cond, "epoch": epoch, "lag_ms": lag,
                     "null": net.null, "sttc_mode": net.sttc_mode, "n_trials": net.n_trials,
                     "window_s_1": win[0], "window_s_2": win[1], **summary})
                lmeta["epochs"][epoch] = {"window_s": list(win), "n_trials": net.n_trials,
                                          "duration_s": net.duration_s,
                                          "n_pairs": summary["nPairs"],
                                          "n_defined_pairs": summary["nDefinedPairs"]}
                nets[epoch] = net = _embed_net(net, keep)
                key = f"{cond}__{epoch}__{lag}ms"
                arrays[f"{key}__sttc"], arrays[f"{key}__sttc_thr"] = net.sttc, net.sttc_thr
                arrays[f"{key}__null_mean"] = net.null_mean
            for i in range(n_all):
                row = {**node_base(i), "condition": cond, "lag_ms": lag}
                for epoch, net in nets.items():
                    row[f"{epoch}_degree"] = (int(np.count_nonzero(net.sttc_thr[i]
                                                                   [np.isfinite(net.sttc_thr[i])]))
                                              if keep[i] else np.nan)
                    row[f"{epoch}_strength"] = float(np.nansum(net.sttc_thr[i])) if keep[i] else np.nan
                    row[f"{epoch}_rate_hz"] = net.spike_counts[i] / net.duration_s
                tables["StimNetwork_NodeLevel.csv"].append(row)
            b, e = nets["baseline"], nets["evoked"]
            log(f"    {cond}, {lag} ms: significant edges baseline "
                f"{np.count_nonzero(np.triu(np.nan_to_num(b.sttc_thr), 1))}, evoked "
                f"{np.count_nonzero(np.triu(np.nan_to_num(e.sttc_thr), 1))}; noise "
                f"correlations: mean {ns['meanNoiseCorr']:.3f}, "
                f"{ns['fracSigNoiseCorr']:.1%} of pairs significant")

            if params.stim_split_half:
                halves, rows = _split_half_networks(sub, ev, win_c, lag, epoch_net, cond, rng)
                tables["StimNetworkSplitHalf_RecordingLevel.csv"].extend(
                    {**base, "condition": cond, "lag_ms": lag, **r} for r in rows)
                for (split, epoch, half), net in halves.items():
                    hkey = f"{cond}__{epoch}__{lag}ms__{split}_{half}"
                    arrays[f"{hkey}__sttc"] = _embed(net.sttc, keep)
                    arrays[f"{hkey}__null_mean"] = _embed(net.null_mean, keep)
                    arrays[f"{hkey}__spike_counts"] = _embed(
                        np.asarray(net.spike_counts, float), keep)
                lmeta["split_rows"] = rows
                for r in rows:
                    if r["epoch"] == "evoked":
                        log(f"      split {r['split']}: evoked edge r = {r['r_sttc']:.2f} "
                            f"(Mantel p = {r['mantel_p_sttc']:.3g}), above-null r = "
                            f"{r['r_excess']:.2f} (p = {r['mantel_p_excess']:.3g})")
    mat_dir.mkdir(parents=True, exist_ok=True)
    meta["has_coords"] = coords is not None
    arrays.update(channels=channels, node_ids=np.asarray(node_ids).astype(str),
                  stim_electrode=~keep, conditions=np.array(events.condition_names),
                  window_s=np.array(window), figure_meta=_dumps(meta))
    if coords is not None:
        arrays["coords"] = np.asarray(coords, float)
    atomic_savez(mat_dir / f"{rec.filename}_stimNetwork.npz", **arrays)
    try:
        draw_network_figures(arrays, fig_dir)
    except Exception as e:   # plotting must never sink the numeric results
        log(f"  [{rec.filename}] Warning: stimulus-network plotting failed: {e}")
    return {name: rows for name, rows in tables.items() if rows}


def _embed_rows(m: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """A ``(trials, subset)`` array at ``(trials, all nodes)``, NaN for the nodes left out."""
    out = np.full((m.shape[0], keep.size), np.nan)
    out[:, keep] = m
    return out


def _split_half_networks(trains, events, window, lag, epoch_net, cond, rng):
    """Epoch networks of each half of the trials, for each split, and how well
    the halves agree. Returns ``({(split, epoch, "A"|"B"): net}, rows)``."""
    from meanap.stim.consistency import SPLITS, edge_overlap, mantel, split_trials
    from meanap.stim.evoked_network import _corr, baseline_window, trial_counts

    events = np.sort(np.asarray(events, float))
    halves, rows = {}, []
    for split in SPLITS:
        ia, ib = split_trials(len(events), split)
        if min(len(ia), len(ib)) < 3:
            continue
        for epoch, win in (("baseline", baseline_window(window)), ("evoked", window)):
            a = epoch_net(events[ia], win, lag, epoch, cond)
            b = epoch_net(events[ib], win, lag, epoch, cond)
            halves[(split, epoch, "A")], halves[(split, epoch, "B")] = a, b
            # A node silent in either half has STTC 0 to everything there;
            # those zeros would agree with each other and inflate r.
            on = np.ix_(*(2 * [(a.spike_counts > 0) & (b.spike_counts > 0)]))
            r_raw, p_raw = mantel(a.sttc[on], b.sttc[on], rng=rng)
            r_ex, p_ex = mantel((a.sttc - a.null_mean)[on], (b.sttc - b.null_mean)[on],
                                rng=rng)
            jac, jac_chance = edge_overlap(a.sttc_thr[on], b.sttc_thr[on])
            rows.append({"split": split, "epoch": epoch, "n_trials_A": len(ia),
                         "n_trials_B": len(ib), "nNodesActiveBoth": int(len(on[0])),
                         "r_sttc": r_raw, "mantel_p_sttc": p_raw,
                         "r_excess": r_ex, "mantel_p_excess": p_ex,
                         "nSigEdges_A": int(np.count_nonzero(np.triu(a.sttc_thr, 1))),
                         "nSigEdges_B": int(np.count_nonzero(np.triu(b.sttc_thr, 1))),
                         "jaccardSigEdges": jac, "jaccardChance": jac_chance})
        ca = _corr(trial_counts(trains, events[ia], window))
        cb = _corr(trial_counts(trains, events[ib], window))
        r_nc, p_nc = mantel(ca, cb, rng=rng)   # a silent node's r is NaN, so skipped
        rows.append({"split": split, "epoch": "noise_corr", "n_trials_A": len(ia),
                     "n_trials_B": len(ib), "r_noise_corr": r_nc, "mantel_p_noise_corr": p_nc})
    return halves, rows


def _plot_stim_network(nets: dict, nc, path: Path, title: str, names=None) -> None:
    """Baseline and evoked networks, the change in raw STTC, and noise correlations.

    *names* labels the nodes (electrode or unit) for a view to name the pair
    under the pointer; without it they are numbered.
    """
    from meanap.native.chart import Cells, Chart, ColourBar, Panel
    from meanap.native.chart_paint import save_chart

    b, e = nets["baseline"], nets["evoked"]
    vmax = max(float(np.nanmax(b.sttc_thr)), float(np.nanmax(e.sttc_thr)), 1e-6)
    diff = e.sttc - b.sttc
    dlim = max(float(np.nanmax(np.abs(diff))), 1e-6)
    n = len(diff)
    names = [str(x) for x in names] if names is not None and len(names) == n else \
        [str(i) for i in range(n)]
    quads = (
        (b.sttc_thr, "viridis", 0, vmax, "STTC",
         f"Baseline {b.window_s[0]:g}–{b.window_s[1]:g} s (significant STTC)"),
        (e.sttc_thr, "viridis", 0, vmax, "STTC",
         f"Evoked {e.window_s[0]:g}–{e.window_s[1]:g} s (significant STTC)"),
        (diff, "RdBu_r", -dlim, dlim, "change in STTC", "Evoked − baseline (raw STTC)"),
        (nc.r, "RdBu_r", -1, 1, "r", f"Noise correlation ({nc.n_trials} trials)"),
    )
    panels = []
    for k, (mat, cmap, lo, hi, what, label) in enumerate(quads):
        mat = np.asarray(mat, float)

        def hover(i, j, mat=mat, what=what):
            v = mat[i, j]
            if i == j:
                return ""
            return (f"{names[i]} ↔ {names[j]}\n"
                    + (f"{what} {v:+.3f}" if np.isfinite(v) else f"{what}: no value"))

        panels.append(Panel(
            cell=divmod(k, 2), marks=[Cells(mat, cmap=cmap, low=lo, high=hi, hover=hover)],
            title=label, title_size=10, xlabel="Node", ylabel="Node", label_size=10,
            tick_size=9, y_down=True, equal=True, grid="",
            colour_bar=ColourBar(cmap, lo, hi, fraction=0.046, tick_size=9)))
    how = ("STTC within each trial, averaged over trials" if e.sttc_mode == "trial_mean"
           else "STTC over the trial windows joined end to end")
    chart = Chart(panels, size=(11, 10), grid=(2, 2), title_size=12,
                  title=f"{title}\n{how}; {e.null.replace('_', ' ')} null, {e.n_trials} trials")
    save_chart(chart, path)
