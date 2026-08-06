"""Test resuming a CAT-NAP run from a previous run's output ("start at step 4").

Run from the repo root::

    uv run python python/test_catnap_resume.py

MATLAB's ``MEApipeline.m`` appends ``adjMs`` to each recording's
``ExperimentMatFiles/<rec>_<folder>.mat`` at the end of step 2, and its
``priorAnalysis == 1 && startAnalysisStep == 4`` branch loads that back instead
of calling ``suite2pToAdjm`` again. This checks the port of that:

  - **round-trip** — everything phases 2/3 need survives a save/load, including
    the ``None``-valued 2P metrics that the non-``peaks`` activity types leave
    unset (``None`` is not NaN downstream);
  - **wiring** — a resumed run reads the prior file and never touches the
    suite2p folder, and a fresh run writes one file per recording;
  - **fail fast** — resuming with nothing to resume from raises instead of
    quietly producing empty CSVs, which is how a mis-set path used to present;
  - **lag selection** — the network-metric loop is driven by the adjacency
    matrices that were actually built, not by ``Params.funcConLagval``, which
    for the ``corr`` activity types is a different list entirely.

All sections run on synthetic data — no MATLAB and no example dataset needed.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap.store import (  # noqa: E402
    RecordingState, load_recording_state, save_recording_state, sorted_adjm_items,
)
from meanap.params import Params  # noqa: E402
from meanap.pipeline.resume import (  # noqa: E402
    CATNAP_SUFFIX, build_input_locator, missing_step_inputs,
)
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402

Check = tuple[str, bool, str]

N_UNITS = 8


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _state(lags=(25, 10)) -> RecordingState:
    """A state with lags deliberately out of order, to pin down the sort."""
    rng = np.random.default_rng(0)
    adjMs = {f"adjM{lag}mslag": rng.random((N_UNITS, N_UNITS)) for lag in lags}
    return RecordingState(
        adjMs=adjMs,
        coords=rng.random((N_UNITS, 2)) * 8.0,
        channels=np.arange(1, N_UNITS + 1),
        spike_counts=rng.integers(0, 50, N_UNITS).astype(float),
        duration_s=612.5,
        plane0=Path("/nonexistent/suite2p/plane0"),
        coord_norm=(3.0, 511.0),
    )


def _stats() -> dict:
    """Stats shaped like the non-``peaks`` path: scalars, arrays, ints, Nones."""
    return {
        "FR": np.linspace(0.1, 2.0, N_UNITS),
        "FRactive": np.full(N_UNITS, np.nan),
        "FRmean": 1.05,
        "FRstd": 0.5,
        "numActiveElec": 6,
        "ISImean": float("nan"),
        "ISI": np.full(N_UNITS, np.nan),
        # The 2P-specific metrics are None (not NaN) for F/spks/denoised F.
        "unitHeightMean": None,
        "unitPeakDurMean": None,
        "unitEventAreaMean": None,
        "unitEventAreaSum": None,
        "recHeightMean": float("nan"),
    }


def _recordings(n: int = 2) -> list[RecordingInfo]:
    return [RecordingInfo(filename=f"rec{i}", div=21.0, group="WT") for i in range(n)]


# ── Section A: store round-trip ───────────────────────────────────────────────


def _roundtrip_checks() -> list[Check]:
    checks: list[Check] = []
    state, stats = _state(), _stats()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"rec0{CATNAP_SUFFIX}"
        save_recording_state(path, state, stats)
        checks.append(("save writes the .npz", path.exists(), ""))

        plane0 = Path("/some/other/place/plane0")
        got, got_stats = load_recording_state(path, plane0)

    checks.append(("adjacency keys preserved",
                   set(got.adjMs) == set(state.adjMs),
                   f"{sorted(got.adjMs)}"))
    checks.append(("adjacency values exact",
                   all(np.array_equal(got.adjMs[k], state.adjMs[k]) for k in state.adjMs),
                   ""))
    checks.append(("coords exact", np.array_equal(got.coords, state.coords), ""))
    checks.append(("channels exact", np.array_equal(got.channels, state.channels), ""))
    checks.append(("spike_counts exact",
                   np.array_equal(got.spike_counts, state.spike_counts), ""))
    checks.append(("duration_s exact", got.duration_s == state.duration_s,
                   f"{got.duration_s}"))
    checks.append(("coord_norm exact", got.coord_norm == state.coord_norm,
                   f"{got.coord_norm}"))
    checks.append(("plane0 comes from the caller, not the file",
                   got.plane0 == Path("/some/other/place/plane0"), f"{got.plane0}"))
    checks.append(("groups/markers left for the caller to re-read",
                   got.groups is None and got.markers is None, ""))

    checks.append(("stat keys preserved", set(got_stats) == set(stats),
                   f"{sorted(set(stats) ^ set(got_stats))}"))
    checks.append(("stat arrays exact",
                   np.array_equal(got_stats["FR"], stats["FR"]), ""))
    checks.append(("NaN-filled stat arrays survive as NaN",
                   np.isnan(got_stats["FRactive"]).all(), ""))
    checks.append(("scalar floats stay scalar floats",
                   isinstance(got_stats["FRmean"], float)
                   and got_stats["FRmean"] == 1.05, f"{got_stats['FRmean']!r}"))
    checks.append(("ints stay ints (numActiveElec)",
                   isinstance(got_stats["numActiveElec"], int)
                   and got_stats["numActiveElec"] == 6,
                   f"{got_stats['numActiveElec']!r}"))
    checks.append(("None stats restore as None, not NaN",
                   all(got_stats[k] is None for k in
                       ("unitHeightMean", "unitPeakDurMean",
                        "unitEventAreaMean", "unitEventAreaSum")), ""))
    checks.append(("NaN scalars stay NaN (not confused with None)",
                   got_stats["recHeightMean"] is not None
                   and np.isnan(got_stats["recHeightMean"]), ""))

    # Version handling is asymmetric on purpose. A file from the *future* is
    # refused — its keys may mean something else. An *older* file is read, its
    # newer fields simply absent: every bump so far only added optional keys,
    # and a bundle's recipient has no raw data, so "re-run from step 1" would
    # be advice they cannot take.
    def _restamp(path: Path, version: int) -> None:
        with np.load(path) as data:
            arrays = {k: data[k] for k in data.files}
        arrays["catnap_format"] = np.array(version)
        np.savez(path, **arrays)

    with tempfile.TemporaryDirectory() as tmp:
        newer = Path(tmp) / f"rec0{CATNAP_SUFFIX}"
        save_recording_state(newer, state, stats)
        _restamp(newer, 99)
        try:
            load_recording_state(newer, Path("."))
            msg = ""
        except ValueError as e:
            msg = str(e)
        checks.append(("a newer format is refused", bool(msg), ""))
        checks.append(("…with an upgrade hint, not 'rerun from step 1'",
                       "Update MEA-NAP" in msg, msg[:70]))

        older = Path(tmp) / f"rec1{CATNAP_SUFFIX}"
        save_recording_state(older, state, stats)
        _restamp(older, 1)
        try:
            back, _ = load_recording_state(older, Path("."))
            ok = np.array_equal(back.coords, state.coords)
        except Exception as e:
            ok, back = False, e
        checks.append(("an older format still loads", ok, f"{back}"))

        unmarked = Path(tmp) / f"rec2{CATNAP_SUFFIX}"
        save_recording_state(unmarked, state, stats)
        _restamp(unmarked, 0)
        try:
            load_recording_state(unmarked, Path("."))
            msg2 = ""
        except ValueError as e:
            msg2 = str(e)
        checks.append(("a file with no format marker is rejected",
                       "format marker" in msg2, msg2[:60]))

    return checks


def _lag_order_checks() -> list[Check]:
    """The metric loop must follow the adjacency that was built.

    ``suite2p_to_adjm`` derives a *single* lag ``round(1000 / fs)`` for the
    ``F``/``spks``/``denoised F`` paths and ignores ``funcConLagval`` entirely
    (``suite2pToAdjm.m`` even overwrites ``Params.FuncConLagval`` with it), so
    driving the loop from Params produced no metrics at all for those types.
    """
    checks: list[Check] = []
    state = _state(lags=(25, 10))

    pairs = sorted_adjm_items(state.adjMs)
    checks.append(("lags come back ascending, not in dict order",
                   [lag for lag, _ in pairs] == [10, 25],
                   f"{[lag for lag, _ in pairs]}"))
    checks.append(("each lag carries its own matrix",
                   all(np.array_equal(m, state.adjMs[f"adjM{lag}mslag"])
                       for lag, m in pairs), ""))

    # The corr-path case: a derived lag that appears in no Params list.
    derived = RecordingState(
        adjMs={"adjM33mslag": np.zeros((2, 2))}, coords=np.zeros((2, 2)),
        channels=np.array([1, 2]), spike_counts=np.zeros(2), duration_s=1.0,
        plane0=Path("."),
    )
    params_lags = [10, 25, 50]
    checks.append(("a derived lag absent from funcConLagval is still analysed",
                   [lag for lag, _ in sorted_adjm_items(derived.adjMs)] == [33]
                   and 33 not in params_lags, ""))
    return checks


# ── Section B: locator + fail-fast wiring ─────────────────────────────────────


def _locator_checks() -> list[Check]:
    checks: list[Check] = []
    recordings = _recordings(2)

    with tempfile.TemporaryDirectory() as tmp:
        prior = Path(tmp) / "OutputData01Jan2026"
        (prior / "ExperimentMatFiles").mkdir(parents=True)
        (prior / "1_SpikeDetection" / "1A_SpikeDetectedData").mkdir(parents=True)
        out = Path(tmp) / "OutputData02Jan2026"
        (out / "ExperimentMatFiles").mkdir(parents=True)

        params = Params(suite2p_mode=True, prior_analysis=True,
                        prior_analysis_path=str(prior), start_analysis_step=4)
        locator = build_input_locator(params, out)

        checks.append(("nothing saved yet → catnap_file is None",
                       locator.catnap_file("rec0") is None, ""))
        missing = missing_step_inputs(locator, recordings, 4, suite2p_mode=True)
        checks.append(("all recordings reported missing",
                       set(missing) == {"rec0", "rec1"}, f"{sorted(missing)}"))
        checks.append(("the gap names CAT-NAP step 2, not step 3",
                       "step 2" in missing["rec0"][0], f"{missing['rec0']}"))

        # An ephys _adjM.npz must NOT satisfy a CAT-NAP resume.
        np.savez(prior / "ExperimentMatFiles" / "rec0_adjM.npz", channels=np.arange(4))
        checks.append(("an ephys _adjM.npz does not satisfy CAT-NAP",
                       locator.catnap_file("rec0") is None, ""))
        checks.append(("…and the ephys locator still finds it",
                       locator.adjm_file("rec0") is not None, ""))

        # Now save a real CAT-NAP file for one of the two recordings.
        save_recording_state(
            prior / "ExperimentMatFiles" / f"rec0{CATNAP_SUFFIX}", _state(), _stats())
        checks.append(("prior CAT-NAP file is found",
                       locator.catnap_file("rec0") is not None, ""))
        missing = missing_step_inputs(locator, recordings, 4, suite2p_mode=True)
        checks.append(("only the unsaved recording is missing",
                       set(missing) == {"rec1"}, f"{sorted(missing)}"))

        # This run's own output wins over the prior run's copy.
        save_recording_state(
            out / "ExperimentMatFiles" / f"rec0{CATNAP_SUFFIX}", _state(), _stats())
        checks.append(("this run's output shadows the prior run",
                       locator.catnap_file("rec0").parent.parent == out,
                       f"{locator.catnap_file('rec0')}"))

        # start_step < 4 never asks for the file.
        checks.append(("start step 1 reports nothing missing",
                       missing_step_inputs(locator, recordings, 1, suite2p_mode=True) == {},
                       ""))
    return checks


def _fail_fast_checks() -> list[Check]:
    """A step-4 resume with nothing to resume from must raise, not run empty."""
    from meanap.pipeline.runner import _check_catnap_resume_inputs

    checks: list[Check] = []
    recordings = _recordings(2)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "OutputData02Jan2026"
        (out / "ExperimentMatFiles").mkdir(parents=True)
        params = Params(suite2p_mode=True, start_analysis_step=4)
        locator = build_input_locator(params, out)

        try:
            _check_catnap_resume_inputs(locator, recordings, params, lambda m: None)
            err = ""
        except ValueError as e:
            err = str(e)
        checks.append(("no inputs at all → ValueError", bool(err), ""))
        checks.append(("the message says how to fix it",
                       "prior analysis" in err.lower() and "start at step 1" in err,
                       err[:80]))

        # One of two present → warn and continue, not raise.
        save_recording_state(
            out / "ExperimentMatFiles" / f"rec0{CATNAP_SUFFIX}", _state(), _stats())
        logs: list[str] = []
        try:
            _check_catnap_resume_inputs(locator, recordings, params, logs.append)
            raised = False
        except ValueError:
            raised = True
        checks.append(("partial inputs warn rather than raise", not raised, ""))
        checks.append(("the skipped recording is named",
                       any("rec1" in line for line in logs), f"{logs}"))
    return checks


# ── Section C: pipeline reads the prior run instead of suite2p ────────────────


def _pipeline_resume_checks() -> list[Check]:
    """Drive ``run_catnap_pipeline`` itself with no suite2p folder on disk.

    That is the point of the check: if the resume path touched the raw data at
    all, this would skip every recording. The recordings' plane0 paths do not
    exist, so a run that produces metrics can only have got them from the
    prior ``.npz``.
    """
    from meanap.catnap import pipeline as cat
    from meanap.pipeline.output_folders import create_output_folders

    checks: list[Check] = []
    recordings = _recordings(1)

    with tempfile.TemporaryDirectory() as tmp:
        prior = create_output_folders(tmp, "OutputPrior", ["WT"])
        # A small, dense, symmetric adjacency so the network metrics are
        # well-defined without needing a real recording behind them.
        rng = np.random.default_rng(1)
        adj = rng.random((N_UNITS, N_UNITS))
        adj = (adj + adj.T) / 2
        np.fill_diagonal(adj, 0)
        state = _state(lags=(25,))
        state.adjMs = {"adjM25mslag": adj}
        state.spike_counts = np.full(N_UNITS, 100.0)
        save_recording_state(
            prior / "ExperimentMatFiles" / f"rec0{CATNAP_SUFFIX}", state, _stats())

        out = create_output_folders(tmp, "OutputResumed", ["WT"])
        params = Params(
            suite2p_mode=True, prior_analysis=True, prior_analysis_path=str(prior),
            start_analysis_step=4, raw_data=str(Path(tmp) / "no-raw-data-here"),
            func_con_lag_val=[25], min_activity_level=0.0,
            min_number_of_nodes_to_cal_net_met=2, twop_subnetwork_analysis=False,
            num_2p_traces=0, twop_network_background=False,
            auto_set_cartography_boundaries=False, random_seed=7,
        )
        logs: list[str] = []
        cat.run_catnap_pipeline(params, recordings, out, logs.append)

        text = "\n".join(logs)
        checks.append(("resumed run logs that it reused the prior adjacency",
                       "reusing adjacency matrices" in text, text[:200]))
        checks.append(("no suite2p folder was read",
                       "loading suite2p data" not in text
                       and "building adjacency matrices" not in text, ""))
        checks.append(("network metrics still ran",
                       "network metrics (lag=25ms)" in text, ""))

        rec_csv = out / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv"
        checks.append(("recording-level CSV written", rec_csv.exists(), ""))
        if rec_csv.exists():
            import pandas as pd
            df = pd.read_csv(rec_csv)
            checks.append(("CSV holds the resumed recording",
                           len(df) == 1 and df["FileName"][0] == "rec0",
                           f"{len(df)} rows"))

        twop_csv = (out / "2_NeuronalActivity"
                    / "TwoPhotonActivity_RecordingLevel.csv")
        checks.append(("activity stats came back too (step-2 CSV written)",
                       twop_csv.exists(), ""))

        # The resumed run re-seeds its own folder, so it is itself resumable.
        reseeded = out / "ExperimentMatFiles" / f"rec0{CATNAP_SUFFIX}"
        checks.append(("resumed run rewrites the state into its own folder",
                       reseeded.exists(), ""))
        if reseeded.exists():
            again, _ = load_recording_state(reseeded, Path("."))
            checks.append(("re-seeded adjacency is unchanged",
                           np.allclose(again.adjMs["adjM25mslag"], adj), ""))

    return checks


def _determinism_checks() -> list[Check]:
    """A seeded resume must reproduce the numbers of the run it resumed from.

    CAT-NAP used to draw every stochastic stage from one batch-wide generator,
    so a recording's metrics depended on how much randomness the recordings
    (and lags) before it had consumed. A resumed run skips the thresholding
    draws entirely, which would have shifted every metric — the resume would
    "work" while quietly changing the answers. Per-recording streams derived
    from ``random_seed`` (as ``step3``/``step4`` already do) remove that
    coupling, which is what this pins down.

    Two recordings with *different* adjacency, so a stream shared across the
    batch would show up as the second recording's metrics moving when the
    first's inputs are reordered.
    """
    from meanap.catnap import pipeline as cat
    from meanap.pipeline.output_folders import create_output_folders

    import pandas as pd

    checks: list[Check] = []
    recordings = _recordings(2)

    def _adj(seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        a = rng.random((N_UNITS, N_UNITS))
        a = (a + a.T) / 2
        np.fill_diagonal(a, 0)
        return a

    def _run(tmp: Path, name: str, order: list[RecordingInfo]) -> "pd.DataFrame":
        prior = create_output_folders(tmp, f"{name}Prior", ["WT"])
        for rec in order:
            st = _state(lags=(25,))
            # Keyed by name, not batch position, so reversing the order changes
            # only the order — each recording keeps its own adjacency.
            st.adjMs = {"adjM25mslag": _adj(10 + int(rec.filename[-1]))}
            st.spike_counts = np.full(N_UNITS, 100.0)
            save_recording_state(
                prior / "ExperimentMatFiles" / f"{rec.filename}{CATNAP_SUFFIX}",
                st, _stats())
        out = create_output_folders(tmp, name, ["WT"])
        params = Params(
            suite2p_mode=True, prior_analysis=True, prior_analysis_path=str(prior),
            start_analysis_step=4, raw_data=str(tmp / "no-raw"),
            func_con_lag_val=[25], min_activity_level=0.0,
            min_number_of_nodes_to_cal_net_met=2, twop_subnetwork_analysis=False,
            num_2p_traces=0, twop_network_background=False,
            auto_set_cartography_boundaries=False, random_seed=7,
        )
        cat.run_catnap_pipeline(params, order, out, lambda m: None)
        return pd.read_csv(out / "4_NetworkActivity" / "NetworkActivity_NodeLevel.csv")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        first = _run(tmp, "RunA", recordings)
        second = _run(tmp, "RunB", recordings)
        reversed_ = _run(tmp, "RunC", list(reversed(recordings)))

    num = [c for c in first.columns if first[c].dtype.kind == "f"]
    checks.append(("two seeded resumes agree exactly",
                   first[num].equals(second[num]), ""))

    # Same recording, same seed, different position in the batch.
    key = ["FileName", "Channel"]
    a = first.sort_values(key).reset_index(drop=True)
    c = reversed_.sort_values(key).reset_index(drop=True)
    checks.append(("recording order does not change the metrics",
                   np.allclose(a[num].to_numpy(), c[num].to_numpy(), equal_nan=True),
                   "batch-wide RNG stream leaking between recordings"))
    return checks


def _missing_prior_checks() -> list[Check]:
    """A recording with no saved state is skipped, and says so."""
    from meanap.catnap import pipeline as cat
    from meanap.pipeline.output_folders import create_output_folders

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        out = create_output_folders(tmp, "OutputResumed", ["WT"])
        params = Params(suite2p_mode=True, start_analysis_step=4,
                        raw_data=str(Path(tmp) / "nope"), func_con_lag_val=[25],
                        auto_set_cartography_boundaries=False,
                        twop_subnetwork_analysis=False, num_2p_traces=0)
        logs: list[str] = []
        cat.run_catnap_pipeline(params, _recordings(1), out, logs.append)
        text = "\n".join(logs)
        checks.append(("missing prior state → SKIP, not a crash",
                       "SKIP: no saved step-2 data" in text, text[:200]))
        checks.append(("run still completes",
                       "CAT-NAP pipeline complete." in text, ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP resume from a previous run (start at step 4)")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [
        ("Section A1 — step-2 state round-trip:", _roundtrip_checks),
        ("Section A2 — lag selection follows the adjacency built:", _lag_order_checks),
        ("Section B1 — locator finds the right file:", _locator_checks),
        ("Section B2 — fail fast with nothing to resume from:", _fail_fast_checks),
        ("Section C1 — pipeline resumes without the raw data:", _pipeline_resume_checks),
        ("Section C2 — a resume reproduces the original numbers:", _determinism_checks),
        ("Section C3 — a recording with no saved state:", _missing_prior_checks),
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
