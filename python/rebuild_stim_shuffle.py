#!/usr/bin/env python3
"""Add the stim shuffle-test results to a run made before they were saved.

Older Python runs ran the shuffle test only to draw the ``12_shuffle_test_*``
figures and never saved the numbers. This rebuilds them from each recording's
``ExperimentMatFiles/<rec>_stimFigures.npz`` (the cleaned spike times, the
patterns and the seed the figures were drawn from), and writes what a run
writes now:

* ``trial_prop_obs`` and ``is_sig_hi`` columns in ``StimActivity_NodeLevel.csv``
  (the original is kept once as ``StimActivity_NodeLevel.csv.bak``);
* ``shuffleResults_pattern_{k}.mat`` in each recording's folder under
  ``2_NeuronalActivity/2A_IndividualNeuronalAnalysis/<Grp>/<rec>/``, with
  MATLAB's variable and field names (``patternShuffleResults.isSigHi`` …).

The test is seeded exactly as the figures were, so the results are the ones
the run's ``12_shuffle_test_*`` figures show. Running it twice is harmless.
Neither the raw recordings nor the spike files are needed.

Usage:
    uv run python python/rebuild_stim_shuffle.py <run folder> [<run folder> ...]

where a run folder is the one holding ``StimActivity_NodeLevel.csv`` and
``ExperimentMatFiles/``.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from meanap.pipeline.atomic import atomic_path  # noqa: E402
from meanap.stim.activity import CSV_COLUMNS  # noqa: E402
from meanap.stim.redraw import (  # noqa: E402
    FIGURES_SUFFIX, load_figure_payload, shuffle_tests_from_payload,
)
from meanap.stim.shuffle import SHUFFLE_CSV_COLUMNS, save_shuffle_results_mat  # noqa: E402

CSV_NAME = "StimActivity_NodeLevel.csv"
INDIV_DIR = Path("2_NeuronalActivity") / "2A_IndividualNeuronalAnalysis"


def rebuild_run(root: Path, log=print) -> bool:
    """Rebuild the shuffle outputs of the run in *root*. False if nothing could be."""
    import pandas as pd

    root = Path(root)
    payloads = sorted((root / "ExperimentMatFiles").glob(f"*{FIGURES_SUFFIX}"))
    if not payloads:
        log(f"! {root}: no ExperimentMatFiles/*{FIGURES_SUFFIX} — nothing to rebuild from")
        return False

    # (recording, pattern_id, file_index) -> (trial_prop_obs, is_sig_hi)
    results: dict[tuple[str, int, int], tuple[float, bool]] = {}
    for path in payloads:
        rec = path.name[: -len(FIGURES_SUFFIX)]
        try:
            payload = load_figure_payload(path)
            shuffles = shuffle_tests_from_payload(payload)
        except Exception as e:
            log(f"! [{rec}] skipped: {e}")
            continue
        for pidx, sr in shuffles.items():
            for c in range(len(sr.trial_prop_obs)):
                results[(rec, pidx, c + 1)] = (float(sr.trial_prop_obs[c]),
                                               bool(sr.is_sig_hi[c]))
        dest = root / INDIV_DIR / str(payload["info"].get("Grp", "")) / rec
        if dest.is_dir():
            n = len(save_shuffle_results_mat(dest, shuffles, payload["patterns"]))
            log(f"  [{rec}] {len(shuffles)} pattern(s); wrote {n} shuffleResults_pattern_*.mat")
        else:
            log(f"  [{rec}] {len(shuffles)} pattern(s); recording folder not found "
                f"({dest.relative_to(root)}), .mat files not written")

    csv = root / CSV_NAME
    if not csv.is_file():
        log(f"! {root}: no {CSV_NAME} to add the columns to")
        return bool(results)
    df = pd.read_csv(csv, dtype={"FileName": str})
    keys = zip(df["FileName"], df["pattern_id"].astype(int), df["file_index"].astype(int))
    found = [results.get(k) for k in keys]
    obs = [np.nan if f is None else f[0] for f in found]
    sig = pd.array([pd.NA if f is None else f[1] for f in found], dtype="boolean")
    for name in SHUFFLE_CSV_COLUMNS:
        if name in df.columns:
            df = df.drop(columns=name)
    # Right after MATLAB's columns, where a run puts them.
    at = max((df.columns.get_loc(c) for c in CSV_COLUMNS if c in df.columns), default=-1) + 1
    df.insert(at, "trial_prop_obs", obs)
    df.insert(at + 1, "is_sig_hi", sig)

    backup = csv.with_name(csv.name + ".bak")
    if not backup.exists():
        shutil.copy2(csv, backup)
    with atomic_path(csv, suffix=".csv") as tmp:
        df.to_csv(tmp, index=False)
    n_found = sum(f is not None for f in found)
    n_sig = int(sig.sum())
    log(f"  {CSV_NAME}: {n_found} of {len(df)} rows filled, {n_sig} significant"
        + (f"; {len(df) - n_found} left blank (no saved payload for them)"
           if n_found < len(df) else ""))
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="+", type=Path,
                    help="run folder(s) holding StimActivity_NodeLevel.csv and ExperimentMatFiles/")
    args = ap.parse_args(argv)
    ok = True
    for root in args.runs:
        print(f"{root}:")
        ok &= rebuild_run(root)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
