# Running from the command line

The GUI is the easiest place to set up a run. You don't need it to *run*
one. On an HPC node, a server you reach over ssh, or a script that analyses
each new plate as it arrives, `meanap run` takes the parameters you saved
from the GUI and runs the same pipeline without a window.

```bash
meanap run my_params.json
```

It is installed with the package, alongside `meanap-gui`. From a clone, use
`uv run meanap …`, as in [Installation](installation.md).

## Set up in the GUI, run anywhere

1. Set the run up in the GUI as usual.
2. **File → Save parameters** writes a `.json` file holding every setting.
3. Run that file, on this computer or any other with MEA-NAP installed:

   ```bash
   meanap run my_params.json
   ```

The run's log, progress and results are the ones the GUI would give, and the
output folder is identical. Press **Ctrl-C** once to stop at the next
recording, with everything finished so far kept. Press it twice to stop
immediately.

The data is often somewhere else on the other machine, so the paths can be
given on the command line rather than editing the file:

```bash
meanap run my_params.json \
    --raw-data /scratch/me/plates \
    --spreadsheet /scratch/me/plates/recordings.csv \
    --output /scratch/me/results
```

Every output folder also carries the `params.json` that produced it, and so
does every `.meanap` bundle. Either can stand in for the parameter file, so
a run can be repeated, or redone with one change, from its own results:

```bash
meanap run OutputData07Aug2026/ --lags 10,25,50 --name OutputData-newLags
```

## Changing settings

The options cover what usually changes between runs of the same analysis:

| Option | Sets |
|---|---|
| `--raw-data PATH` | the raw data folder, or a [Dropbox share link](remote-data.md) |
| `--spreadsheet FILE` | the recording spreadsheet |
| `-o, --output PATH` | the folder the run's output folder is made in |
| `--name NAME` | the output folder's name; an existing one is continued, or replaced with `--overwrite` |
| `--steps 1-4` | which steps (`3`, `2-4`, …) |
| `--lags 10,25,50` | the STTC lags, in ms |
| `--resume` | carry on with an interrupted run, skipping finished recordings |
| `--express` | [express mode](express-mode.md): the data and a `.meanap` bundle, not every figure |
| `--workers N` | how many recordings are processed at once (default: sized to your CPU and RAM) |
| `--seed N` | a random seed, for a run that can be repeated exactly |
| `-v`, `--debug` | a more detailed log |
| `-n, --dry-run` | check the settings and say what would run, without running it |

Any other setting is changed with `--set`, using its name in
{py:class}`~meanap.params.Params`. It can be repeated:

```bash
meanap run my_params.json --set spikes_method=thr4 --set prob_thresh_rep_num=500
```

Values are read as the setting's type. Lists take commas (`--set
custom_grp_order=WT,KO`), true/false settings take `true`/`false`, and an
optional setting is cleared with `none`. A misspelt name is refused, with a
suggestion, rather than silently ignored.

To find a setting's name, list the ones a file changes, or every one with
`--all`:

```bash
meanap params show my_params.json
meanap params show my_params.json --all
```

## Without the GUI at all

`meanap params new` writes a file of defaults to edit by hand, for the
electrophysiology pipeline, MEA-Stim or CAT-NAP:

```bash
meanap params new -o my_params.json --mode catnap
```

`meanap example` downloads the two example recordings and runs steps 1–4 on
them. It is the GUI's **Test pipeline** button, and a quick check that an
installation on a new machine works:

```bash
meanap example --express
```

## Several runs in a row

Name several files and they run one after another, like the GUI's queue. A
run that fails is reported and the rest carry on. The summary at the end
says which ones finished and where their results are.

```bash
meanap run plate1.json plate2.json plate3.json --express
```

Options given on the command line apply to every run in the list.

## On a cluster

A minimal Slurm job:

```bash
#!/bin/bash
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=04:00:00

meanap run "$HOME/params/plate1.json" \
    --raw-data "$SCRATCH/plate1" --output "$SCRATCH/results" --express
```

MEA-NAP sizes its workers to the CPUs and memory it can see. See
[Running MEA-NAP on HPC](../running-MEANAP-on-HPC.rst) for cluster setup,
and [Sharing a run](shared-run.md) to split one batch across machines that
don't share a scheduler.

The exit code says how a run ended, for scripts that check it:

| Code | Meaning |
|---|---|
| 0 | finished |
| 1 | a run failed (in a queue: at least one did) |
| 2 | the settings were incomplete or wrong; nothing ran |
| 130 | stopped with Ctrl-C |

## The other tools

The other command-line tools are available under `meanap` too, and take the
same arguments as their standalone forms:

| Command | Same as | Does |
|---|---|---|
| `meanap gui` | `meanap-gui` | the desktop app |
| `meanap viewer` | `meanap-viewer` | the [network viewer](network-viewer.md) |
| `meanap stats` | `meanap-stats` | [statistics and machine learning](stats-and-ml.md) on a finished run |
| `meanap shared` | `meanap-shared` | [split a run across computers](shared-run.md) |
| `meanap preflight` | `meanap-preflight` | check a [remote data source](remote-data.md) before a run |
| `meanap version` | | the versions of MEA-NAP, CAT-NAP and MEA-Stim |

`meanap <command> --help` lists each one's options.
