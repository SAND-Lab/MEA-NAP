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
        n_stim_elec = sum(1 for s in stim_info if s.pattern and s.pattern > 0)
        log(f"    {len(patterns)} pattern(s), {n_stim_elec} stimulating electrode(s)")
        if not patterns:
            log(f"    no stimulation detected on [{rec.filename}] — skipping analysis.")
            continue

        # Python step-1 spikes for this recording, filtered to the analysis method
        spikes_full = load_spike_times_npz(npz_path)
        spikes = {c: {method: m[method]} for c, m in spikes_full.items() if method in m}
        spikes = clean_spikes_from_stim(spikes, stim_info, sp_params)

        info = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div,
                "FN": [rec.filename], "duration_s": dat.shape[0] / fs}

        log(f"  [{rec.filename}] computing stim response metrics…")
        rows = stim_activity_analysis(spikes, stim_info, patterns, sp_params, info)
        all_rows.extend(rows)
        log(f"    {len(rows)} electrode rows")

        # per-recording figures
        check_cancel(should_cancel)
        try:
            from meanap.stim.pipeline import write_stim_figures
            blank_dur_mode = _blank_dur_mode(stim_info)
            artifact_dur = get_stim_artifact_duration({**sp_params, "blankDurMode": blank_dur_mode})
            dest = indiv_dir / rec.group / rec.filename
            figs = write_stim_figures(dest, stim_info, patterns, spikes, sp_params,
                                      dat, artifact_dur, info,
                                      rng=make_rng(params.random_seed or 1,
                                                   "stim-figures", rec.filename))
            log(f"  [{rec.filename}] wrote {len(figs)} stim figures")
        except Exception as e:   # plotting must never sink the numeric results
            log(f"  [{rec.filename}] Warning: stim plotting failed: {e}")
        n_done += 1
        progress.item_done(rec.filename)

    progress.phase_done()

    if all_rows:
        csv_path = output_root / "StimActivity_NodeLevel.csv"
        write_stim_activity_csv(all_rows, csv_path)
        log(f"  Wrote {csv_path.name} ({len(all_rows)} rows across {n_done} recording(s))")
    else:
        log("  No stim rows produced (no stimulation detected in any recording).")


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
    from meanap.stim.pipeline import write_stim_figures

    locator = build_input_locator(params, output_root)
    indiv_dir = output_root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
    method = active_spike_method(params)
    base = params.to_stim_params_dict()
    window = tuple(float(x) for x in params.stim_analysis_window)

    all_rows: list[dict] = []
    all_net_rows: list[dict] = []
    all_node_rows: list[dict] = []
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
            net_rows, node_rows = _stim_networks(
                params, rec, info, trains, events, channels, unit_ids,
                dest, output_root / "ExperimentMatFiles", log)
            all_net_rows.extend(net_rows)
            all_node_rows.extend(node_rows)
        check_cancel(should_cancel)
        try:
            artifact_dur = get_stim_artifact_duration({**sp_params, "blankDurMode": 0.0})
            figs = write_stim_figures(dest, stim_info, patterns, spikes, sp_params,
                                      None, artifact_dur, info,
                                      rng=make_rng(params.random_seed or 1,
                                                   "stim-figures", rec.filename))
            log(f"  [{rec.filename}] wrote {len(figs)} stim figures")
        except Exception as e:   # plotting must never sink the numeric results
            log(f"  [{rec.filename}] Warning: stim plotting failed: {e}")
        n_done += 1
        progress.item_done(rec.filename)

    progress.phase_done()
    if all_rows:
        csv_path = output_root / "StimActivity_NodeLevel.csv"
        write_stim_activity_csv(all_rows, csv_path)
        log(f"  Wrote {csv_path.name} ({len(all_rows)} rows across {n_done} recording(s))")
    else:
        log("  No stim rows produced.")
    if all_net_rows:
        import pandas as pd
        pd.DataFrame(all_net_rows).to_csv(output_root / "StimNetwork_RecordingLevel.csv", index=False)
        pd.DataFrame(all_node_rows).to_csv(output_root / "StimNetwork_NodeLevel.csv", index=False)
        log(f"  Wrote StimNetwork_RecordingLevel.csv ({len(all_net_rows)} rows) and "
            f"StimNetwork_NodeLevel.csv")


def _coords_from(layout: tuple[np.ndarray, np.ndarray], channels: np.ndarray) -> np.ndarray:
    by_id = {int(c): p for c, p in zip(*layout)}
    return np.array([by_id.get(int(c), (np.nan, np.nan)) for c in channels], dtype=float)


def _write_events_table(events, path: Path) -> None:
    """The events the analysis used, with their pattern number, beside its figures."""
    import pandas as pd

    names = events.condition_names
    pd.DataFrame({
        "time_s": events.times_s, "condition": events.conditions,
        "pattern_id": [names.index(c) + 1 for c in events.conditions],
    }).to_csv(path, index=False)


def _stim_networks(params: Params, rec: RecordingInfo, info: dict, trains: list[np.ndarray],
                   events, channels: np.ndarray, unit_ids: np.ndarray | None,
                   fig_dir: Path, mat_dir: Path, log) -> tuple[list[dict], list[dict]]:
    """Evoked/baseline networks and noise correlations for one recording.

    Returns recording-level rows (one per condition × epoch × lag, plus one
    noise-correlation row per condition) and node-level rows; writes the
    matrices to ``ExperimentMatFiles/<rec>_stimNetwork.npz`` and one figure
    per condition and lag.
    """
    from meanap.pipeline.atomic import atomic_savez
    from meanap.stim.events import StimEvents
    from meanap.stim.evoked_network import (
        baseline_window, epoch_network, network_summary, noise_correlations,
        noise_summary, separated_events,
    )

    window = tuple(float(x) for x in params.stim_network_window)
    order = np.argsort(events.times_s, kind="stable")
    events = StimEvents(events.times_s[order], events.conditions[order], events.description)
    keep = separated_events(events.times_s, window)
    if not keep.all():
        log(f"    {int((~keep).sum())} event(s) too close to a neighbour for a "
            f"{window[1] - window[0]:g} s evoked + baseline window — left out of the networks")
        events = StimEvents(events.times_s[keep], events.conditions[keep], events.description)
    if len(events.times_s) < 3:
        log(f"  ! [{rec.filename}] stimulus networks skipped: fewer than 3 usable events")
        return [], []

    rng = make_rng(params.random_seed or 1, "stim-network", rec.filename)
    base = {"FileName": rec.filename, "Grp": rec.group, "DIV": rec.div}
    rows, node_rows, arrays = [], [], {}
    node_ids = unit_ids if unit_ids is not None else channels.astype(str)
    log(f"  [{rec.filename}] stimulus-triggered networks ({params.stim_network_null} null, "
        f"{params.stim_network_rep_num} surrogates, window {window[0]:g}–{window[1]:g} s)…")
    for cond, ev in zip(events.condition_names, events.patterns()):
        nc = noise_correlations(trains, ev, window, condition=cond,
                                rep_num=params.stim_network_rep_num, rng=rng)
        ns = noise_summary(nc, params.stim_network_alpha)
        rows.append({**base, "condition": cond, "epoch": "noise_corr", "lag_ms": np.nan,
                     "n_trials": nc.n_trials, **ns})
        arrays[f"{cond}__noise_r"], arrays[f"{cond}__noise_p"] = nc.r, nc.p
        for lag in params.func_con_lag_val:
            nets = {}
            for epoch, win in (("baseline", baseline_window(window)), ("evoked", window)):
                net = epoch_network(trains, ev, win, lag, condition=cond, epoch=epoch,
                                    null=params.stim_network_null,
                                    rep_num=params.stim_network_rep_num,
                                    tail=params.stim_network_alpha, rng=rng)
                nets[epoch] = net
                summary = network_summary(net, params, params.min_activity_level, rng=rng)
                rows.append({**base, "condition": cond, "epoch": epoch, "lag_ms": lag,
                             "null": net.null, "n_trials": net.n_trials,
                             "window_s_1": win[0], "window_s_2": win[1], **summary})
                key = f"{cond}__{epoch}__{lag}ms"
                arrays[f"{key}__sttc"], arrays[f"{key}__sttc_thr"] = net.sttc, net.sttc_thr
                arrays[f"{key}__null_mean"] = net.null_mean
            for i, nid in enumerate(node_ids):
                row = {**base, "condition": cond, "lag_ms": lag, "node": i + 1,
                       "channel_id": int(channels[i])}
                if unit_ids is not None:
                    row["unit_id"] = nid
                for epoch, net in nets.items():
                    row[f"{epoch}_degree"] = int(np.count_nonzero(net.sttc_thr[i]))
                    row[f"{epoch}_strength"] = float(net.sttc_thr[i].sum())
                    row[f"{epoch}_rate_hz"] = net.spike_counts[i] / net.duration_s
                node_rows.append(row)
            _plot_stim_network(nets, nc, fig_dir / f"13_StimNetwork_{cond}_{lag}mslag.png",
                               f"{rec.filename} — {cond}, lag {lag} ms")
            b, e = nets["baseline"], nets["evoked"]
            log(f"    {cond}, {lag} ms: significant edges baseline "
                f"{np.count_nonzero(np.triu(b.sttc_thr, 1))}, evoked "
                f"{np.count_nonzero(np.triu(e.sttc_thr, 1))}; noise correlations: mean "
                f"{ns['meanNoiseCorr']:.3f}, {ns['fracSigNoiseCorr']:.1%} of pairs significant")
    mat_dir.mkdir(parents=True, exist_ok=True)
    atomic_savez(mat_dir / f"{rec.filename}_stimNetwork.npz", channels=channels,
                 node_ids=np.asarray(node_ids).astype(str),
                 conditions=np.array(events.condition_names),
                 window_s=np.array(window), **arrays)
    return rows, node_rows


def _plot_stim_network(nets: dict, nc, path: Path, title: str) -> None:
    """Baseline and evoked networks, the change in raw STTC, and noise correlations."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from meanap.pipeline.figure_output import savefig

    b, e = nets["baseline"], nets["evoked"]
    vmax = max(float(np.nanmax(b.sttc_thr)), float(np.nanmax(e.sttc_thr)), 1e-6)
    diff = e.sttc - b.sttc
    dlim = max(float(np.nanmax(np.abs(diff))), 1e-6)
    fig, axes = plt.subplots(2, 2, figsize=(11, 10))
    panels = (
        (axes[0, 0], b.sttc_thr, "viridis", 0, vmax,
         f"Baseline {b.window_s[0]:g}–{b.window_s[1]:g} s (significant STTC)"),
        (axes[0, 1], e.sttc_thr, "viridis", 0, vmax,
         f"Evoked {e.window_s[0]:g}–{e.window_s[1]:g} s (significant STTC)"),
        (axes[1, 0], diff, "RdBu_r", -dlim, dlim, "Evoked − baseline (raw STTC)"),
        (axes[1, 1], nc.r, "RdBu_r", -1, 1,
         f"Noise correlation ({nc.n_trials} trials)"),
    )
    for ax, mat, cmap, lo, hi, label in panels:
        im = ax.imshow(mat, cmap=cmap, vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("Node")
        ax.set_ylabel("Node")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle(f"{title}\n{e.null.replace('_', ' ')} null, {e.n_trials} trials")
    fig.tight_layout()
    savefig(fig, path, default_dpi=150)
    plt.close(fig)
