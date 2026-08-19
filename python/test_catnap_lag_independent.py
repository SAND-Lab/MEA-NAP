"""Test the lag-independent activity metrics on the CAT-NAP path.

Run from the repo root::

    uv run python python/test_catnap_lag_independent.py

``effRank`` and the NMF fields are read off the *activity* matrix, not off any
adjacency matrix, so they live outside ``compute_network_metrics`` — the piece
CAT-NAP and electrophysiology genuinely share. That is exactly why they went
missing: the CAT-NAP runner calls ``compute_network_metrics`` directly and
never went through ``_step4_compute_one``, where the electrophysiology path
computes them. A 53-hour batch finished with no ``effRank`` column at all.

MATLAB has no such gap — ``MEApipeline.m`` calls ``ExtractNetMet`` identically
in ``suite2pMode``, and ``effRank`` is in the default ``netMetToCal`` — so this
was a port omission, not a setting.

Checked here:
  A. the maths: the refactor that split the matrix path out of the spike-times
     path is exact, and the ``eff_fs > fs`` clamp matches ExtractNetMet.m;
  B. the wiring: a CAT-NAP run emits ``effRank`` on every lag, NMF only when
     asked, and one bad recording degrades to NaN rather than failing;
  C. persistence: both survive a save/load round trip, so a step-4 resume or a
     bundle recipient keeps them without the raw fluorescence.

Synthetic data throughout; no dataset needed.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import meanap.pipeline.network_metrics as nm  # noqa: E402
from meanap.catnap.store import (  # noqa: E402
    RecordingState, load_recording_state, save_recording_state,
)

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


def _spike_matrix(spike_times, fs, duration_s):
    """Bin events to samples, **counting** rather than flagging.

    Coincident events in one bin sum, which is what both sides do: MATLAB via
    ``histcounts`` (``spikeTimeToMatrix.m``) and this port via ``csc_matrix``,
    which adds duplicate coordinates. Writing 1.0 instead would silently
    disagree wherever two events share a bin — impossible at a 25 kHz ephys
    sampling rate, entirely possible at a 15 Hz imaging frame rate.
    """
    n = int(np.ceil(duration_s * fs))
    a = np.zeros((n, len(spike_times)))
    for i, st in enumerate(spike_times):
        s = np.round(np.asarray(st) * fs).astype(int)
        np.add.at(a, (s[(s >= 0) & (s < n)], i), 1.0)
    return a


def _maths_checks() -> list[Check]:
    checks: list[Check] = []
    rng = np.random.default_rng(0)
    fs, dur = 15.0, 600.0
    st = [np.sort(rng.uniform(0, dur, rng.integers(3, 40))) for _ in range(25)]

    # The split must be exact: same inputs, same number, to the last bit.
    from_times = nm.effective_rank(st, fs, dur, 10.0, "ordinary")
    from_matrix = nm.effective_rank_from_activity(
        _spike_matrix(st, fs, dur), fs, 10.0, "ordinary")
    checks.append(("the matrix path reproduces the spike-times path exactly",
                   from_times == from_matrix, f"{from_times} vs {from_matrix}"))
    checks.append(("…and gives a plausible rank (1 <= r <= n_units)",
                   1.0 <= from_times <= 25.0, f"{from_times}"))

    # ExtractNetMet.m clamps rather than upsampling. At a 2P frame rate this is
    # reachable with ordinary settings, unlike at 25 kHz.
    a = _spike_matrix(st, fs, dur)
    checks.append(("eff_fs above fs is clamped to fs, not upsampled",
                   nm.effective_rank_from_activity(a, fs, 25.0, "ordinary")
                   == nm.effective_rank_from_activity(a, fs, fs, "ordinary"), ""))

    # Structure must move the number: a network of copies has rank ~1.
    same = np.tile(_spike_matrix(st[:1], fs, dur), (1, 20))
    checks.append(("20 identical units give an effective rank near 1",
                   nm.effective_rank_from_activity(same, fs, 10.0, "ordinary") < 1.5,
                   f"{nm.effective_rank_from_activity(same, fs, 10.0, 'ordinary'):.3f}"))
    indep = _spike_matrix(
        [np.sort(rng.uniform(0, dur, 200)) for _ in range(20)], fs, dur)
    r_indep = nm.effective_rank_from_activity(indep, fs, 10.0, "ordinary")
    checks.append(("20 independent units give a much higher rank",
                   r_indep > 10.0, f"{r_indep:.3f}"))

    checks.append(("the correlation method is accepted too",
                   np.isfinite(nm.effective_rank_from_activity(
                       indep, fs, 10.0, "correlation")), ""))
    return checks


class _Res:
    """The parts of a Suite2pAdjmResult the lag-independent metrics read."""

    def __init__(self, spike_times, fs, n_frames, n_units):
        self.spike_times = spike_times
        self.fs = fs
        self.F = np.zeros((n_frames, n_units))
        self.spks = np.abs(np.random.default_rng(1).normal(size=(n_frames, n_units)))
        self.denoised_F = self.spks.copy()


def _wiring_checks() -> list[Check]:
    from meanap.catnap import pipeline as cp
    from meanap.params import Params

    checks: list[Check] = []
    rng = np.random.default_rng(0)
    fs, dur, n_units = 15.0, 600.0, 20
    st = [np.sort(rng.uniform(0, dur, rng.integers(3, 40))) for _ in range(n_units)]
    res = _Res(st, fs, int(dur * fs), n_units)

    logs: list[str] = []
    p = Params()
    p.twop_activity = "peaks"
    out = cp._lag_independent_metrics(res, p, dur, logs.append, "rec1", rng)
    checks.append(("a peaks recording produces effRank",
                   "effRank" in out and np.isfinite(out["effRank"]), f"{out}"))
    checks.append(("…matching a direct call on the same events",
                   out["effRank"] == nm.effective_rank(
                       st, fs, dur, p.eff_rank_downsample_freq,
                       p.eff_rank_cal_method), ""))
    checks.append(("NMF is off by default on this path",
                   "num_nnmf_components" not in out, f"{sorted(out)}"))

    p.twop_nmf = True
    out_nmf = cp._lag_independent_metrics(res, p, dur, logs.append, "rec1", rng)
    checks.append(("…and computed when twop_nmf is set",
                   "num_nnmf_components" in out_nmf, f"{sorted(out_nmf)}"))

    # A continuous activity type has no event times; MATLAB resamples the
    # matrix, so this path must too rather than skipping the metric.
    p2 = Params(); p2.twop_activity = "spks"
    out2 = cp._lag_independent_metrics(res, p2, dur, logs.append, "rec2", rng)
    checks.append(("a continuous activity type still produces effRank",
                   np.isfinite(out2["effRank"]), f"{out2.get('effRank')}"))
    checks.append(("…via the matrix, not the (absent) event times",
                   out2["effRank"] == nm.effective_rank_from_activity(
                       res.spks, fs, p2.eff_rank_downsample_freq,
                       p2.eff_rank_cal_method), ""))

    # A recording with nothing to measure must cost the metric, not the
    # recording: the network metrics beside it are entirely unaffected.
    empty = _Res([], fs, 10, 0)
    p3 = Params(); p3.twop_activity = "peaks"
    out3 = cp._lag_independent_metrics(empty, p3, dur, logs.append, "empty", rng)
    checks.append(("a recording with no units yields NaN, not an exception",
                   "effRank" in out3 and np.isnan(out3["effRank"]), f"{out3}"))

    # …and when the computation genuinely raises, it is caught and reported
    # rather than taking the run down.
    logs.clear()
    original = nm.effective_rank
    try:
        nm.effective_rank = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        out4 = cp._lag_independent_metrics(res, p3, dur, logs.append, "bad", rng)
    finally:
        nm.effective_rank = original
    checks.append(("a raising computation is caught and becomes NaN",
                   np.isnan(out4["effRank"]), f"{out4}"))
    checks.append(("…and is reported against the recording in the log",
                   any("bad" in m and "effective rank" in m for m in logs),
                   f"{logs}"))
    return checks


def _persistence_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rec_catnap.npz"
        state = RecordingState(
            adjMs={"adjM1000mslag": np.eye(4)},
            coords=np.zeros((4, 2)), channels=np.arange(4),
            spike_counts=np.ones(4), duration_s=600.0, plane0=Path(tmp),
            lag_independent={"effRank": 3.25, "num_nnmf_components": 2},
        )
        save_recording_state(path, state, {"FRmean": 0.5})
        back, _stats = load_recording_state(path, Path(tmp))
        checks.append(("effRank survives a save/load round trip",
                       back.lag_independent.get("effRank") == 3.25,
                       f"{back.lag_independent}"))
        checks.append(("…as a float, not a 0-d array",
                       isinstance(back.lag_independent.get("effRank"), float), ""))
        checks.append(("NMF fields round-trip alongside it",
                       back.lag_independent.get("num_nnmf_components") == 2, ""))

        # A recording from before this existed must still load.
        state.lag_independent = {}
        save_recording_state(path, state, {"FRmean": 0.5})
        back2, _ = load_recording_state(path, Path(tmp))
        checks.append(("a recording with no lag-independent metrics loads fine",
                       back2.lag_independent == {}, f"{back2.lag_independent}"))
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP: effective rank and NMF (lag-independent activity metrics)")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — the maths and the matrix/event-time split:", _maths_checks),
        ("B — wiring into the CAT-NAP runner:", _wiring_checks),
        ("C — persistence across resume and bundles:", _persistence_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
