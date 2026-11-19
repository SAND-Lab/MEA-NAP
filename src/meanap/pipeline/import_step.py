"""Step 1 when the spikes are already sorted: ``spike_source = "import"``.

For each recording: find its sorter output, take the sampling rate, exact
duration and electrode positions from the raw recording's metadata where there
is one, and write the sorted ``_spikes.npz`` the rest of the pipeline reads.
The import itself loads no voltage; when the raw file is there and
``signal_quality_check`` is on, the unit-quality report reads each unit's
electrode to test it against that electrode's noise
(:mod:`meanap.pipeline.unit_noise`). See :mod:`meanap.pipeline.sorted_import`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from meanap.params import Params
from meanap.pipeline.cancellation import CancelCheck, check_cancel
from meanap.pipeline.io import save_spike_times_npz
from meanap.pipeline.progress import RunProgress
from meanap.pipeline.resume import already_done
from meanap.pipeline.sorted_import import (
    ElectrodeTable, find_sorted_output, read_sorted_output, to_spike_file,
)
from meanap.pipeline.spreadsheet import RecordingInfo
from meanap.pipeline.verbosity import as_run_log

#: How a MaxWell raw file is named relative to the recording: MaxLab writes
#: ``<name>.raw.h5``, and some exports drop the ``.raw``.
_MAXWELL_NAMES = ("{}.raw.h5", "{}.h5")


def find_maxwell_raw(folders: list[Path], recording: str) -> Path | None:
    """The recording's MaxWell ``.h5``, if one is in any of *folders*."""
    from meanap.pipeline.maxwell import is_maxwell_h5

    for folder in folders:
        for pattern in _MAXWELL_NAMES:
            candidate = folder / pattern.format(recording)
            if candidate.is_file() and is_maxwell_h5(candidate):
                return candidate
    return None


def _signal_quality_from_raw(params: Params, rec: RecordingInfo, raw: Path,
                             output_root: Path, log) -> None:
    """Step 1's electrode-level check, on the raw file a sorting came from.

    The same check spike detection runs, so an imported sorting gets the same
    signal-quality figure, summary and map. Reads only the window the check
    uses (its seconds after the settling time), as compact counts. Never
    stops the import.
    """
    from meanap.pipeline.maxwell import electrode_table, load_maxwell_traces, node_ids, read_maxwell_meta
    from meanap.pipeline.signal_quality import SKIP_START_S, run_signal_quality_check

    try:
        meta = read_maxwell_meta(raw)
        secs = float(params.signal_quality_seconds or 60.0)
        frames = int((SKIP_START_S + secs + 1.0) * meta.fs)
        log(f"  [{rec.filename}] checking {raw.name} for spikes…")
        dat, _ = load_maxwell_traces(raw, meta=meta, compact=True, max_frames=frames)
    except Exception as exc:  # noqa: BLE001 — a check, not a step
        log(f"  ! [{rec.filename}] signal-quality check skipped ({exc})")
        return
    run_signal_quality_check(params, rec, dat, node_ids(meta), meta.fs, output_root, log,
                             xy=electrode_table(meta)["coords"])


def run_sorted_import(
    params: Params,
    recordings: list[RecordingInfo],
    output_root: Path,
    log,
    should_cancel: CancelCheck = None,
    progress: RunProgress | None = None,
) -> None:
    """Write every recording's sorted spike file from its sorter output."""
    from meanap.pipeline.maxwell import read_maxwell_meta

    log = as_run_log(log, params.verbose_level)
    progress = progress or RunProgress()
    progress.begin("step1", items=len(recordings))

    sorted_dir = Path(params.sorted_data_folder or params.raw_data or "")
    if not str(sorted_dir) or not sorted_dir.is_dir():
        raise ValueError("Set the sorted data folder (or the raw data folder) to "
                         "import spike-sorted data")
    raw_dirs = [Path(d) for d in dict.fromkeys(
        [params.raw_data, params.sorted_data_folder]) if d]
    spike_dir = output_root / "1_SpikeDetection" / "1A_SpikeDetectedData"
    drop = tuple(params.sorted_drop_labels or ())
    names = tuple(r.filename for r in recordings)

    for rec in recordings:
        check_cancel(should_cancel)
        out_path = spike_dir / f"{rec.filename}_spikes.npz"
        if already_done(params, output_root, out_path, log):
            log(f"  [{rec.filename}] already imported — skipping")
            progress.item_done(rec.filename)
            continue

        found = find_sorted_output(sorted_dir, rec.filename, params.sorted_data_format,
                                   others=names)
        if found is None:
            log(f"  ! [{rec.filename}] no sorter output found in {sorted_dir} "
                f"(format {params.sorted_data_format}) — skipping")
            progress.item_done(rec.filename)
            continue
        fmt, path = found

        # Beside the sorter output too: a raw file is usually kept next to its
        # sort (``Plate/<rec>.raw.h5`` and ``Plate/<rec>/``), and the sorted
        # folder is searched recursively where the raw folder is not.
        raw = find_maxwell_raw(list(dict.fromkeys(
            raw_dirs + [path.parent, path.parent.parent])), rec.filename)
        electrodes = fs = duration_s = None
        if raw is not None:
            meta = read_maxwell_meta(raw)
            electrodes = ElectrodeTable.from_maxwell(meta)
            fs, duration_s = meta.fs, meta.duration_s
            log.detail(f"      raw metadata from {raw.name}: {len(meta.electrodes)} "
                       f"electrodes, {fs / 1000:g} kHz, {duration_s:.2f} s")

        log(f"  [{rec.filename}] importing {fmt} output ({path.name})…")
        try:
            imp = read_sorted_output(fmt, path, electrodes=electrodes, fs=fs,
                                     duration_s=duration_s)
        except (ValueError, FileNotFoundError, ImportError) as e:
            log(f"  ! [{rec.filename}] could not import: {e} — skipping")
            progress.item_done(rec.filename)
            continue
        if imp.n_units == 0:
            # Nothing to make nodes of, and an empty spike file would only fail
            # later, in a step that has no way to say why.
            log(f"  ! [{rec.filename}] {imp.sorter} found no units in {path.name} — skipping")
            progress.item_done(rec.filename)
            continue

        content = to_spike_file(imp, drop_labels=drop)
        n_units = len(content.channels)
        labels, counts = np.unique(imp.labels, return_counts=True)
        log(f"  [{rec.filename}] {imp.n_units} unit(s) from {imp.sorter}, "
            f"{n_units} kept as nodes on {len(np.unique(content.channels))} electrode(s)"
            + (f" (labels: {', '.join(f'{l} {c}' for l, c in zip(labels, counts))})"
               if len(labels) > 1 or labels[0] != "unsorted" else ""))

        save_spike_times_npz(
            out_path, content.spike_times, content.channels, imp.fs,
            duration_s=imp.duration_s, units=content.units,
            electrodes=content.electrodes,
            params={
                "spike_source": "import", "sorter": imp.sorter, "format": fmt,
                "sorted_output": str(path), "raw_file": str(raw) if raw else "",
                "drop_labels": list(drop), "fs": imp.fs, "duration": imp.duration_s,
            })
        log(f"  [{rec.filename}] saved → {out_path.relative_to(output_root)}")
        # Report only: which units are nodes is still the sorter's labels.
        from meanap.pipeline.unit_quality import run_unit_quality

        check_raw = raw if params.signal_quality_check else None
        if check_raw is not None:
            _signal_quality_from_raw(params, rec, check_raw, output_root, log)
        run_unit_quality(rec.filename, imp, output_root,
                         analyzer_path=path if fmt == "spikeinterface" else None,
                         drop_labels=drop, raw_path=check_raw, log=log)
        if check_raw is not None:
            from meanap.pipeline.signal_quality import draw_signal_quality_map

            draw_signal_quality_map(output_root, rec.filename, log=log)   # now with units
        progress.item_done(rec.filename)

    progress.phase_done()
