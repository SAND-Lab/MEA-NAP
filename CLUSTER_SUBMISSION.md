# Running MEA-NAP headlessly on a SLURM cluster

This describes how to run MEA-NAP as a batch job (no GUI, no interactive
MATLAB session), using the scripts in this repo:

- `MEApipeline_headless_fromStep2.m` — starts at Step 2 (neuronal activity),
  reusing already spike-detected data. **This is the one you want** if your
  data has already been through spike detection (your own reformatted data,
  or a collaborator's).
- `MEApipeline_headless_full.m` — runs the full pipeline (Step 1 spike
  detection through Step 4 network activity) starting from raw recordings.
  Use this only if you have original, not-yet-spike-detected `.mat` recordings.
- `run_meanap.sh` — the SLURM submission script. Dataset-agnostic; takes the
  MATLAB script name (above) as its argument.
- `make_channel_placeholder_mats.m` — helper for `MEApipeline_headless_fromStep2.m`'s
  `rawData` requirement when you only have spike-detected data (see below).

## 1. Which file to run

Almost always: **`MEApipeline_headless_fromStep2.m`**. Before running it,
open it and edit the block marked `% ============================ EDIT PER
DATASET ============================` near the top:

| Variable | What to set it to |
|---|---|
| `HomeDir` | Path to this MEA-NAP repo checkout |
| `Params.outputDataFolder` | Where to write results |
| `Params.outputDataFolderName` | Name for this run's output subfolder |
| `rawData` | Folder of `<name>.mat` files containing just a `channels` variable (see step 2 below) |
| `spikeDetectedData` | Folder of `<name>_spikes.mat` files |
| `spreadsheet_filename` | Path to the batch CSV (filename, DIV, group[, Ground]) |
| `Params.fs`, `Params.channelLayout`, `Params.potentialDifferenceUnit` | Must match how the existing spike data was recorded/detected |
| `Params.SpikesMethod` | Must match the method used to generate the existing spike files (e.g. `'bior1p5'`) |

Every other line in the file is either a stock MEA-NAP setting (see
`docs/guide-for-advanced-users.rst` for what each one does) or a fix for a
real headless-execution bug — see the comment block at the top of the file
for the full list of what was broken and why, so you're not caught out by
the same things on a different machine.

## 2. The `rawData` / channel-placeholder requirement

MEA-NAP's own `setUpSpreadSheet.m` reads a `channels` variable from
`<rawData>/<name>.mat` for every recording — **even when starting from
Step 2** and even though it never touches the actual voltage trace. If you
don't have the original raw recording (the normal case for reformatted /
collaborator spike data), generate tiny placeholder files instead:

```matlab
make_channel_placeholder_mats('/path/to/SpikeDetectedData', '/path/to/ChannelPlaceholders')
```

This copies `channels` straight out of each recording's own
`<name>_spikes.mat`, then point `rawData` in the pipeline script at
`ChannelPlaceholders` instead of a real raw-data folder.

## 3. Submitting the job

```bash
sbatch run_meanap.sh MEApipeline_headless_fromStep2
```

(or `MEApipeline_headless_full` for a from-raw run). Check progress with:

```bash
squeue -u $USER
tail -f meanap-<jobid>.log
```

`run_meanap.sh`'s SLURM directives (`--partition`, `--mem`, `--cpus-per-task`,
`--time`) and the hardcoded MATLAB binary path are specific to *this*
cluster — see the comments inside the script for what to change when moving
to a different cluster (partition name via `sinfo`, available MATLAB module,
and how Step 3's `parfor`-triggered parallel pool behaves without this
cluster's SLURM-integrated MATLAB Parallel Server profile).

## 4. MATLAB version matters

Use **R2020b** (`/hpc-software/bin/matlab_2020b` on this cluster) or a
version confirmed to have the same two properties:
- Supports `-batch` (R2019a and earlier only have `-r`, which needs an
  explicit `exit` and different error-handling)
- Supports indexing directly into a function's return value, e.g.
  `dir(...).name` (introduced after R2019a) — the real, unmodified
  `MEApipeline.m` uses this syntax in Step 4 and simply fails to parse on
  MATLAB versions before this feature existed.

Also confirm the target MATLAB installation has the **Wavelet Toolbox**,
**Signal Processing Toolbox**, and **Statistics and Machine Learning
Toolbox** licensed — MEA-NAP's spike detection and network metrics need all
three. Check with:

```
matlab -batch "v=ver; disp(any(strcmp({v.Name},'Wavelet Toolbox')))"
```

## 5. Runtime estimate (measured on this cluster, `Axion64`, 64 channels, ~10min recordings)

| Recordings | Step 1 (spike detection) | Step 2 | Step 3 | Step 4 | Steps 2-4 total |
|---|---|---|---|---|---|
| 2  | 877s (~15 min)  | 113s | 66s  | 356s  | 535s (~9 min) |
| 20 | not run (started from existing spikes) | 660s | 132s | 3082s | 3874s (~65 min) |

Notes:
- Steps 2-4 scale **sub-linearly** with recording count here (10x the
  recordings took ~7.2x the time, not 10x) — Step 3 especially, because
  starting the parallel pool is a fixed cost paid once per run and then
  amortised across every recording. Step 1 has no such amortisation (MEA-NAP
  processes recordings serially with no cross-recording parallelism — see
  `Functions/WATERS-master/batchDetectSpikes.m`'s `for recording = ...`
  loop), so **if you ever need to run Step 1 from raw data**, budget close
  to linearly: ~440s/recording from the 2-file measurement above.
- For a rough estimate on a new batch size N (already spike-detected, Steps
  2-4 only): the 20-file run above works out to ~194s/recording all-in: `N x
  194s`. Treat this as an upper bound — the sub-linear trend above suggests
  larger batches should do somewhat better per recording, not worse.
- These numbers are for `Axion64`, 64-channel, ~10-minute recordings with
  3 STTC lags and `ProbThreshRepNum=200`. A collaborator's dataset with a
  different channel count, recording duration, or number of lags will
  scale differently — Step 3/4's cost is driven by the number of possible
  edges (roughly channels²), and Step 1's cost by recording duration.

## 6. A note on parallelizing across recordings (not implemented)

Steps 1-4 all process recordings in a single serial loop (`for ExN = 1:length(ExpName)`)
with no cross-recording parallelism — only Step 3's within-recording shuffles
use the cluster's parallel pool. For Step 1 in particular (spike detection),
which dominates any from-raw run and has zero parallelism today, splitting
the recording list into N SLURM array-job shards (each running this same
pipeline on a subset of the batch CSV, writing to its own output folder,
merged afterward) would likely give a near-linear speedup proportional to
how many array tasks you can run concurrently — without touching MEA-NAP's
own algorithm code at all, since it's purely a difference in how the job is
submitted/orchestrated. This wasn't implemented here since it wasn't asked
for and adds real complexity (correctly sharding the CSV, merging per-shard
`NetworkActivity_*`/`NeuronalActivity_*` CSVs and `ExperimentMatFiles`
afterward for any Step 5 stats that need the full batch). Worth considering
if a real run's Step 1 time becomes a bottleneck.
