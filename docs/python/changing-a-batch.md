# Changing which recordings a run covers

A batch is rarely right the first time. A sixth culture is recorded a week
after the first five. One recording turns out to be bad and has to come out.
Two batches analysed separately need comparing as one.

None of those require analysing everything again. Adding a recording computes
only that recording, removing one computes nothing at all, and combining
earlier runs recomputes nothing. In every case the result is the same as if you
had analysed that exact set from the start — the pooled statistics,
batch-scaled axes and cartography boundaries are all redone over whatever the
spreadsheet now names.

## The mechanism behind all three

The spreadsheet decides which recordings a run covers. Changing the batch means
editing the spreadsheet and then telling the run it may reuse what is already
on disk — which is **Continue previous run**.

A continued run writes into the *same* output folder and skips any recording
whose result for that step is already there:

| Step | Skipped when present | Cost avoided |
|---|---|---|
| 1 — spike detection | `<rec>_spikes.npz` | ~52 s/recording |
| 3 — connectivity | `<rec>_adjM.npz` | ~21 s/recording |
| 4 — network metrics | that recording's entry in `netmet_results.json` | ~99 s/recording |
| CAT-NAP phase 1 | `<rec>_catnap.npz` | the STTC and thresholding half |

```python
from meanap.params import Params

params = Params(
    ...,
    output_data_folder_name="OutputData09Aug2026",   # the run to continue
    continue_interrupted=True,
)
```

In the GUI it is the **Continue previous run** tick box on the **Run** tab. It
is also offered as **Continue it** on the dialog that appears when a run would
land on a folder that already exists.

```{note}
The same switch is what resumes a run that was cut off partway — a Ctrl-C, a
cluster wall clock, a closed laptop. Continuing and changing the batch are one
mechanism, not two.
```

Every resumable write goes to a temporary name and is `os.replace`d into
position, so a file existing means it is whole. Anything unreadable is deleted
and redone rather than trusted.

Express mode is no exception, though it keeps no folder to skip anything in: the
run's data is unpacked out of the `.meanap` beside it first, and then the same
skipping applies. See {ref}`continuing an express run <express-continue>`.

## Adding a recording

Put it in the spreadsheet and continue.

1. **Data** tab → **Edit…** beside the spreadsheet field. Add a row for the new
   recording. The editor knows the list it was opened with, so on save it tells
   you what changed — *"1 added. Tick 'Continue previous run' on the Run tab…"*
2. **Run** tab → tick **Continue previous run**.
3. Run.

Only the new recording is computed. Everything pooled across the batch — group
comparisons, the batch-scaled axis limits, the node-cartography boundaries — is
redone over all of them, because those are derived from the whole set and a new
member changes them.

From Python, adding needs nothing beyond the continue flag:

```python
Params(
    ...,
    spreadsheet_file_name="batch.csv",               # now lists the new recording
    output_data_folder_name="OutputData09Aug2026",
    continue_interrupted=True,
)
```

## Removing a recording

Take it out of the spreadsheet and continue. The numbers follow on their own:
it drops out of every CSV and every pooled statistic without anything special
being asked for.

The **figures** do not. They are written per recording into their own folders,
and nothing goes back for them — so a removed recording leaves its plots
sitting in the output tree and in `report.html`, indistinguishable from the
recordings that are still part of the analysis. A folder showing twenty-three
figures for a recording its own CSVs never mention is worse than one that is
merely out of date, because nothing about it looks wrong.

So a continued run reconciles the folder against the spreadsheet and says what
it found:

```
1 recording(s) in this folder are no longer in the spreadsheet: rec2
  Their 23 figure(s) are still on disk and will appear in the output folder and
  report, though they are excluded from every CSV and pooled statistic.
  Set Params.prune_removed_recordings = True to delete them.
```

To have them deleted, tick **…and drop removed recordings' figures**, the
sub-option beneath **Continue previous run** on the **Run** tab, or:

```python
Params(
    ...,
    output_data_folder_name="OutputData09Aug2026",
    continue_interrupted=True,
    prune_removed_recordings=True,
)
```

Reporting is the default rather than pruning, because this deletes results and
a run that quietly removed the wrong thing would be discovered much later, if
ever.

```{note}
The recording's **data** files are kept either way — `<rec>_spikes.npz`,
`<rec>_adjM.npz` and the rest. Only figures are pruned. That is what makes
putting a recording back cheap, and data on disk that no CSV references
misleads nobody, where a figure does.
```

## Combining separate runs

Name more than one previous analysis and give the run a spreadsheet listing
recordings from all of them. Nothing is recomputed.

On the **Run** tab, tick **Use prior analysis**, put the first run in
**Previous analysis folder**, and use **Add…** beside **Additional folders**
for the rest. Merging is just naming more than one previous analysis, so the
field that already means "read from an earlier run" grows rather than a second
concept appearing.

```python
Params(
    ...,
    spreadsheet_file_name="combined.csv",     # recordings from both runs
    prior_analysis=True,
    prior_analysis_path="path/to/RunA",
    prior_analysis_paths=["path/to/RunB"],    # searched after the first
    start_analysis_step=4,
)
```

Each entry may equally be a `.meanap` bundle rather than an `OutputData…`
folder, so a run someone sent you can go into the pool without being unpacked
first. Lookups try `prior_analysis_path` first and then each of
`prior_analysis_paths` in order; this run's own output folder always wins over
both, so nothing produced by the current run is ever shadowed by an older file.

Unlike the other two, combining writes to a **fresh** output folder — the
earlier runs are only ever read. This mirrors MATLAB's `priorAnalysis`
behaviour.

## What is redone

Whichever of the three you are doing, anything computed across the batch is
recomputed over the batch as it now stands:

- group and age comparison figures and their statistics;
- batch-scaled axis limits on the network plots;
- node-cartography boundaries, which are derived from the pooled PC/Z of every
  recording that ran;
- every summary CSV.

This is the reason step 4 loads the finished recordings back in rather than
only skipping them. A continued run that saw only what it recomputed would
place the cartography boundaries somewhere the original never would.

`python/test_continue_interrupted.py` checks all three cases against a run of
the same set analysed together from the start, figures included — cheaper is
only worth something if the answer is the same.

## Limits

- Continuing needs the output folder to be the one you are continuing, named
  explicitly. A run left on the default (today's date) will not find yesterday's
  folder — it says `Nothing to continue in …; running from the start.` and does
  exactly that, rather than failing.
- A recording is matched by name. Renaming one in the spreadsheet reads as
  removing one recording and adding another, and it will be recomputed.
- Combining runs assumes the runs share their analysis settings. Nothing checks
  that pooling results computed with different connectivity lags or thresholds
  is meaningful — see the run's parameter summary in `report.html` to compare
  what each used.
