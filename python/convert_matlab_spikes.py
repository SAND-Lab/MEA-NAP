"""Convert MATLAB MEApipeline ``*_spikes.mat`` files to the Python port's ``*_spikes.npz``.

    uv run python python/convert_matlab_spikes.py <file-or-folder>... [-o DEST]
        [--mode TOKEN] [--times-only] [--fs HZ] [--overwrite]

Each <rec>_spikes.mat is written as <rec>_spikes.npz.

    inputs          *_spikes.mat files and/or folders of them  (folders: top level only)
    -o, --out       output folder                default: next to each .mat
    --mode          only files containing TOKEN  default: all files
    --times-only    skip waveforms/thresholds    default: off (they are kept)
    --fs            sampling rate (Hz) fallback  default: none; files lacking fs fail
    --overwrite     replace existing .npz        default: off (existing are skipped)

Then run steps 2+ on them:

    meanap run params.json --set spike_detected_data=<DEST> \\
        --set start_analysis_step=2 --set spikes_method=<MATLAB Params.SpikesMethod>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.pipeline.io import load_spike_file, save_spike_times_npz  # noqa: E402

MAT_SUFFIX = "_spikes.mat"
UNIT_TO_SECONDS = {"s": 1.0, "ms": 1e-3}


def find_inputs(paths: list[str]) -> list[Path]:
    """Expand folders to their ``*_spikes.mat`` files; keep files as given."""
    found: list[Path] = []
    for entry in map(Path, paths):
        if entry.is_dir():
            found += sorted(entry.glob(f"*{MAT_SUFFIX}"))
        else:
            found.append(entry)
    return found


def read_detection_param(f: h5py.File, name: str):
    """``spikeDetectionResult.params.<name>`` as a float or str, or ``None``."""
    result = f.get("spikeDetectionResult")
    if result is None:
        return None
    # Older MEA-NAP versions saved the struct as ``Params``.
    group = result.get("params", result.get("Params"))
    if group is None or name not in group:
        return None
    dset = group[name]
    if int(dset.attrs.get("MATLAB_empty", 0)):
        return None
    values = np.asarray(dset[()]).ravel()
    if dset.attrs.get("MATLAB_class", b"") in (b"char", "char"):
        return "".join(map(chr, values))
    return float(values[0]) if values.size else None


def convert(mat: Path, out: Path, fs_override: float | None, times_only: bool) -> str:
    """Write *mat* as *out*; return a one-line summary."""
    try:
        with h5py.File(mat, "r") as f:
            fs = read_detection_param(f, "fs")
            duration = read_detection_param(f, "duration")
            unit = read_detection_param(f, "unit") or "s"
    except OSError as exc:
        raise ValueError("not a v7.3 MAT-file; re-save it in MATLAB with "
                         "save(..., '-v7.3')") from exc

    fs = fs or fs_override
    if not fs:
        raise ValueError("no sampling rate in the file; pass --fs")
    if unit == "frames":
        scale = 1.0 / fs
    elif unit in UNIT_TO_SECONDS:
        scale = UNIT_TO_SECONDS[unit]
    else:
        raise ValueError(f"unknown spike time unit {unit!r}")

    sf = load_spike_file(mat)
    if len(sf.channels) != len(sf.spike_times):
        raise ValueError(f"{len(sf.channels)} channels but "
                         f"{len(sf.spike_times)} spikeTimes entries")

    spike_times = {
        ch: {m: np.asarray(t, dtype=np.float64).ravel() * scale for m, t in methods.items()}
        for ch, methods in sf.spike_times.items()
    }
    electrodes = None
    if sf.coords is not None and len(sf.coords) == len(sf.channels):
        electrodes = {"ids": sf.channels, "coords": sf.coords}

    save_spike_times_npz(
        out, spike_times, sf.channels, fs,
        duration_s=duration,
        waveforms=None if times_only else sf.waveforms,
        thresholds=None if times_only else sf.thresholds,
        electrodes=electrodes,
    )

    counts: dict[str, list[int]] = {}
    for methods in spike_times.values():
        for m, t in methods.items():
            counts.setdefault(m, []).append(len(t))
    per_method = ", ".join(f"{m}: {sum(c)} spikes on {sum(n > 0 for n in c)} ch"
                           for m, c in counts.items())
    dur = f"{duration:.1f} s" if duration else "duration unknown (step 2 will need raw_data)"
    return f"{len(sf.channels)} channels, {fs / 1000:g} kHz, {dur}; {per_method}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="*_spikes.mat files or folders of them")
    parser.add_argument("-o", "--out", help="output folder (default: next to each .mat)")
    parser.add_argument("--mode", metavar="TOKEN", help="only files whose name contains TOKEN")
    parser.add_argument("--times-only", action="store_true",
                        help="skip waveforms and thresholds")
    parser.add_argument("--fs", type=float, help="sampling rate (Hz) if the file lacks one")
    parser.add_argument("--overwrite", action="store_true", help="replace existing .npz files")
    args = parser.parse_args(argv)

    mats = find_inputs(args.inputs)
    if args.mode:
        mats = [m for m in mats if args.mode in m.name]
    if not mats:
        print(f"No *{MAT_SUFFIX} files found"
              + (f" containing '{args.mode}'." if args.mode else "."))
        return 1

    done = skipped = failed = 0
    for mat in mats:
        name = mat.name.removesuffix(MAT_SUFFIX).removesuffix(".mat") + "_spikes.npz"
        out = (Path(args.out) if args.out else mat.parent) / name
        if out.exists() and not args.overwrite:
            print(f"SKIP {mat.name}: {out} exists (use --overwrite)")
            skipped += 1
            continue
        try:
            summary = convert(mat, out, args.fs, args.times_only)
        except (ValueError, OSError, KeyError) as exc:
            print(f"FAIL {mat.name}: {exc}")
            failed += 1
            continue
        print(f"OK   {mat.name} -> {out}\n     {summary}")
        done += 1

    print(f"\n{done} converted, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
