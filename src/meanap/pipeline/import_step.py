"""Step 1 when the spikes are already sorted: ``spike_source = "import"``.

For each recording: find its sorter output, take the sampling rate, exact
duration and electrode positions from the raw recording's metadata where there
is one, and write the sorted ``_spikes.npz`` the rest of the pipeline reads.
Nothing here loads voltage. See :mod:`meanap.pipeline.sorted_import`.
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
            continue
        fmt, path = found

        raw = find_maxwell_raw(raw_dirs, rec.filename)
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
        progress.item_done(rec.filename)

    progress.phase_done()
