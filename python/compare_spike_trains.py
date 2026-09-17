"""Compare two step-1 outputs of the same recording spike by spike — a
detected file (bior1.5 / thr) against a sorted one, or any two methods.

    uv run python python/compare_spike_trains.py \\
        <run_A>/1_SpikeDetection/1A_SpikeDetectedData/<rec>_spikes.npz \\
        <run_B>/1_SpikeDetection/1A_SpikeDetectedData/<rec>_spikes.npz \\
        [--method-a bior1p5] [--method-b sorted] [--raw <rec>.mat] [--lag-ms 10]

Prints, per method and for the pair:

- spike totals, and the electrodes only one of them has spikes on;
- **ISI structure** on the busiest electrodes (fraction of intervals under
  0.5 / 1.5 / 3 ms) — where a detector without a refractory period shows
  double counts and where a bursting population shows sub-2 ms intervals;
- **agreement**: the share of A's spikes with a B spike within ±0.5 ms and
  vice versa, pooled over the electrodes both have;
- with ``--raw``, what the *unmatched* spikes look like: their trough depth
  in noise σ and how many sit inside a burst — which says whether one
  method is finding smaller spikes or just more noise;
- the correlation of the two STTC matrices at ``--lag-ms`` over the shared
  electrodes, and their mean — whether the difference reaches the network.

Units of a sorted file are pooled onto their parent electrode so the two
sides compare electrode to electrode. The numbers this printed for
HP_tc043_DIV21 (bior1.5 vs Tridesclous2) are in python/SPIKE_SORTING_PLAN.md
§5.4 and docs/python/spike-sorting.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from meanap.pipeline.io import load_raw_recording, load_spike_file
from meanap.pipeline.spike_detection import bandpass_filter, trace_noise
from meanap.pipeline.sttc import sttc_pair


def trains_by_electrode(path: Path, method: str | None) -> tuple[dict[int, np.ndarray], str, float, float | None]:
    sf = load_spike_file(path)
    method = method or ("sorted" if sf.sorted else sf.methods[0])
    if method not in sf.methods:
        raise SystemExit(f"{path.name}: no method {method!r} (has {sf.methods})")
    out: dict[int, list] = {}
    for idx, per in sf.spike_times.items():
        if method in per and idx < len(sf.channels):
            out.setdefault(int(sf.channels[idx]), []).append(np.asarray(per[method], float))
    trains = {e: np.sort(np.concatenate(v)) for e, v in out.items()}
    return trains, method, sf.fs, sf.duration_s


def match_fraction(a: np.ndarray, b: np.ndarray, tol_s: float) -> float:
    if len(a) == 0 or len(b) == 0:
        return np.nan
    j = np.clip(np.searchsorted(b, a), 1, len(b) - 1)
    d = np.minimum(np.abs(a - b[j - 1]), np.abs(a - b[j]))
    return float((d <= tol_s).mean())


def isi_line(t: np.ndarray) -> str:
    if len(t) < 2:
        return "n<2"
    isi = np.diff(t) * 1000
    return (f"n={len(t):6d}  ISI<0.5ms {np.mean(isi < 0.5):5.1%}  <1.5ms {np.mean(isi < 1.5):5.1%}  "
            f"<3ms {np.mean(isi < 3):5.1%}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--method-a", default=None)
    ap.add_argument("--method-b", default=None)
    ap.add_argument("--raw", type=Path, default=None, help="raw recording, for amplitudes of unmatched spikes")
    ap.add_argument("--lag-ms", type=float, default=10.0)
    ap.add_argument("--tol-ms", type=float, default=0.5)
    ap.add_argument("--top", type=int, default=4, help="busiest electrodes to detail")
    args = ap.parse_args(argv)

    A, ma, fs, dur = trains_by_electrode(args.a, args.method_a)
    B, mb, _, dur_b = trains_by_electrode(args.b, args.method_b)
    dur = dur or dur_b or max(t.max() for t in list(A.values()) + list(B.values()) if len(t))
    na, nb = sum(map(len, A.values())), sum(map(len, B.values()))
    print(f"A = {args.a.name} [{ma}]: {na} spikes on {sum(len(t) > 0 for t in A.values())} electrodes")
    print(f"B = {args.b.name} [{mb}]: {nb} spikes on {sum(len(t) > 0 for t in B.values())} electrodes")
    only_a = sorted(e for e in A if len(A[e]) and not len(B.get(e, [])))
    only_b = sorted(e for e in B if len(B[e]) and not len(A.get(e, [])))
    if only_a:
        print(f"  electrodes with spikes only in A: {only_a} ({sum(len(A[e]) for e in only_a)} spikes)")
    if only_b:
        print(f"  electrodes with spikes only in B: {only_b} ({sum(len(B[e]) for e in only_b)} spikes)")

    shared = [e for e in A if e in B and len(A[e]) and len(B[e])]
    busiest = sorted(shared, key=lambda e: -len(A[e]))[: args.top]
    print(f"\nISI structure on the {len(busiest)} busiest shared electrodes:")
    for e in busiest:
        print(f"  e{e:<3d} A  {isi_line(A[e])}\n  e{e:<3d} B  {isi_line(B[e])}")

    tol = args.tol_ms / 1000
    wa = wb = ca = cb = 0.0
    for e in shared:
        wa += match_fraction(A[e], B[e], tol) * len(A[e]); ca += len(A[e])
        wb += match_fraction(B[e], A[e], tol) * len(B[e]); cb += len(B[e])
    print(f"\nagreement (±{args.tol_ms:g} ms, {len(shared)} shared electrodes): "
          f"{wa / ca:.2f} of A's spikes have a B spike; {wb / cb:.2f} of B's spikes have an A spike")

    if args.raw is not None:
        dat, channels, fs_raw = load_raw_recording(args.raw)
        col = {int(c): i for i, c in enumerate(channels)}
        print(f"\nunmatched spikes on the busiest electrodes (trough depth in noise σ; 'in burst' = "
              f"within 3 ms of the previous spike of the same method):")
        for e in busiest:
            if e not in col:
                continue
            x = bandpass_filter(dat[:, col[e]].astype(float), fs_raw, 600, 8000)
            sig = trace_noise(x)[0]
            for name, T, U in (("A", A[e], B[e]), ("B", B[e], A[e])):
                j = np.clip(np.searchsorted(U, T), 1, len(U) - 1)
                d = np.minimum(np.abs(T - U[j - 1]), np.abs(T - U[j]))
                um = d > tol
                if not um.any():
                    continue
                frames = np.clip(np.round(T * fs_raw).astype(int), 0, len(x) - 1)
                amp = x[frames] / sig
                prev = np.r_[np.inf, np.diff(T) * 1000]
                print(f"  e{e:<3d} {name}: {um.sum():5d} unmatched of {len(T)} — median trough "
                      f"{np.median(amp[um]):5.1f}σ (matched {np.median(amp[~um]):5.1f}σ); "
                      f"{np.mean(amp[um] > -5):4.0%} shallower than 5σ; {np.mean(prev[um] < 3):4.0%} in burst")

    lag = args.lag_ms / 1000
    n = len(shared)
    if n >= 3:
        Ma, Mb = np.eye(n), np.eye(n)
        for i in range(n):
            for k in range(i + 1, n):
                Ma[i, k] = Ma[k, i] = sttc_pair(A[shared[i]], A[shared[k]], lag, 0.0, dur)
                Mb[i, k] = Mb[k, i] = sttc_pair(B[shared[i]], B[shared[k]], lag, 0.0, dur)
        iu = np.triu_indices(n, 1)
        ok = np.isfinite(Ma[iu]) & np.isfinite(Mb[iu])
        r = np.corrcoef(Ma[iu][ok], Mb[iu][ok])[0, 1]
        print(f"\nSTTC at {args.lag_ms:g} ms over the {n} shared electrodes: corr(A, B) = {r:.3f}; "
              f"mean STTC A {np.nanmean(Ma[iu]):.3f}, B {np.nanmean(Mb[iu]):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
