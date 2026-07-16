# `parityRun/` — MATLAB vs Python parity harness

Scaffolding used to verify that the Python port reproduces MATLAB MEA-NAP's
numbers on the Test-pipeline dataset. **Read [`PARITY_REPORT.md`](PARITY_REPORT.md)
first** — it has the findings; this file is just how to re-run them.

Nothing here is part of the shipped pipeline. It exists so the parity claims can
be re-checked rather than taken on trust.

## Why the runs are configured explicitly

The two ports' *defaults* don't agree (thresholds, wavelet list, refractory
period, lag values, cartography bounds, …), so comparing "Test pipeline" to
"Test pipeline" out of the box measures parameter drift, not port fidelity. Both
sides here are driven from one matched parameter set.

Also note the bundled example data is **Axion64 @ 12500 Hz**, not MCS60 @ 25000 Hz
(channels 11–88, 8×8). MATLAB's Test-pipeline button doesn't set the layout or
`fs`, so getting this wrong silently detects spikes against the wrong rate.

## Re-running

Requires MATLAB on `PATH` (`which matlab`) and `uv` for the Python side.
Order matters: the MATLAB run produces the reference the others compare against.

```bash
# 1. MATLAB, steps 1-4  (~15 min; writes parityRun/OutputData_MATLAB_parity/)
matlab -batch "addpath('$PWD/parityRun'); MEApipeline_parity('$PWD/parityRun/params_matlab_parity.mat')"

# 2. Python, steps 1-4, params matched to the above  (~7 min)
uv run python parityRun/run_python_parity.py

# 3. Compare
uv run python parityRun/compare_spike_detection.py          # step 1
uv run python parityRun/compare_parity.py OutputData_Python_parity   # all four CSVs
```

Two extra controls, each isolating one variable:

```bash
# Python steps 2-4 on MATLAB's OWN spike times -> removes spike detection
uv run python parityRun/run_python_from_matlab_spikes.py
uv run python parityRun/compare_parity.py OutputData_Python_fromMatlabSpikes

# Both sides' step-4 metrics on the SAME adjacency -> removes step 3's RNG too.
# This is the clean test of the metric arithmetic.
matlab -batch "run('parityRun/gen_step4_parity_reference.m')"
uv run python parityRun/compare_step4_same_adjacency.py
```

The layering matters: step 3's probabilistic thresholding is RNG-driven, so even
identical spike times yield slightly different graphs (different `aN`) and hence
different network metrics. Only the same-adjacency comparison isolates the
metric code itself.

## Files

| File | Purpose |
|---|---|
| `PARITY_REPORT.md` | **The findings.** |
| `params_matlab_parity.mat` | MATLAB parameter set (matched to `run_python_parity.py`) |
| `MEApipeline_parity.m` | Headless copy of `MEApipeline.m` — 2 additive lines, no numeric changes (`diff` it against the original to confirm) |
| `FakeApp.m` | Sink for the GUI status writes `MEApipeline.m` makes when `guiMode=1` |
| `exampleData_parity.csv` | 2-row spreadsheet (see "Gotchas") |
| `run_python_parity.py` | Python steps 1-4 |
| `run_python_from_matlab_spikes.py` | Python steps 2-4 on MATLAB's spikes |
| `gen_step4_parity_reference.m` | MATLAB's own BCT metrics on this run's adjacency |
| `compare_*.py` | The three comparisons |
| `results_*.txt`, `parity_comparison_*.json` | Captured output, as committed evidence |

`OutputData_*/` and `*.log` are regenerated, and git-ignored.

## Gotchas (all hit while building this)

- `MEApipeline.m` **ignores `Params.spreadSheetRange`** when invoked as
  `MEApipeline(paramsFile)` — line 33's `csvRange = [2, Inf]` default wins, so it
  reads every spreadsheet row. Hence the 2-row `exampleData_parity.csv`.
- That same path forces `Params.guiMode = 1` and then dereferences `app`, which
  doesn't exist headless. Hence `FakeApp.m`.
- `Params.electrodesToGroundPerRecording` is `[]` when the spreadsheet has no
  `Ground` column, but the step 2/3/4 loops brace-index it `{ExN}` — a real
  MEA-NAP bug, worked around in `MEApipeline_parity.m` (see also
  `MEApipeline_timingBenchmark.m`, which documents 5 more headless traps).
- `Params.singleChannelIsiThreshold` is only ever set by `getParamsFromApp.m`, so
  it's missing from older saved param files and crashes `firingRatesBursts.m`.
- Don't set `detectSpikes = 0` to reuse spike files: MATLAB then adds the
  *spike* folder to the path instead of the raw-data folder, and the step-1
  check plots fail to find the raw `.mat`.
