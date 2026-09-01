# GUI guide

The `meanap-gui` desktop app (PyQt6) mirrors the MATLAB App Designer
interface: one tab per section of the pipeline. Parameters round-trip to and
from a `Params` dataclass (`meanap.params.Params`, see the
[API reference](api/index.rst)) via each panel's `load()`/`save()` methods, and
can be saved/reloaded as JSON from the toolbar (**New**, **Open params…**,
**Save params…**). To open a `.meanap` run bundle in the viewer without
running anything, use **📦 Open bundle…** on the [Results](#results) tab — see
[Opening a bundle](#opening-a-bundle).

```{admonition} In a hurry?
:class: tip
[Quickstart](quickstart.md) skips all of this via the **🧪 Test pipeline**
button, which fills in sensible defaults and the bundled example dataset
automatically.
```

(advanced-settings)=
## Advanced settings

Most tabs keep their everyday settings in the open and fold the rest into a
collapsible **Advanced settings** group, labelled with how many it holds so
nothing is hidden silently. **⚙ Advanced** in the toolbar opens every one at
once and remembers that between sessions.

Advanced does not mean dangerous or inactive: a collapsed setting loads, holds
and saves its value exactly as an open one does, and every field is documented
in the tables below whether it is folded away or not. The distinction is only
how often a setting is worth looking at.

Fields marked **⚙** in the tables below are the folded ones. Two groups fold
whole — **Bandpass filter** and **Spike templates and refractory period** on the
Spike detection tab — because nothing in either is part of configuring a run.

The guided tutorial opens whatever it is about to point at, so following it
never leaves you looking at a closed header.

(modes)=
## Modes

MEA-NAP is three pipelines sharing one window, and each reads a different slice
of the settings. The **Mode** selector in the toolbar narrows the window to the
tabs its pipeline actually uses, so you aren't reading settings your run will
never consult:

| Mode | Pipeline | Tabs shown |
|---|---|---|
| **MEA-NAP · Ephys** | Spike detection → activity → connectivity → network analysis | Data, Spike detection, Connectivity, Run, Results |
| **MEA-Stim · Stimulation** | The ephys pipeline plus the stimulation analysis that runs after it | the above, plus Stimulation and Stim Preview |
| **CAT-NAP · 2P imaging** | Network analysis of suite2p calcium imaging | Data, Connectivity, CAT-NAP (2P), Run, Results |

Start in a mode from the command line:

```bash
meanap-gui --mode catnap      # meanap (default) | meastim | catnap
```

or switch at any time with the toolbar selector — nothing is lost, since tabs
are only hidden, never reset. Anything you typed into a tab that the current
mode hides is still there when you switch back.

Two things follow the mode automatically, so what runs always matches what you
see: picking a mode sets the pipeline's own switches (`suite2p_mode`,
`stimulation_mode`), and **Open params…** switches the window to whichever mode
that file was saved for. Choosing a pipeline in the guided tutorial switches
mode too — it is the same choice.

CAT-NAP has no Spike detection tab, and the Data tab hides its Recording group,
because `run_catnap_pipeline` never reads sampling rate, electrode layout or
spike-detection settings. It does read the connectivity settings, so that tab
stays — but with different defaults. A calcium transient lasts on the order of
a second where a spike lasts a millisecond, so switching to CAT-NAP lengthens
the STTC **Lag values** from `10, 15, 25` ms to `1000, 2500, 5000` ms (and
switching back shortens them again). This only happens while the field is still
on a default: lags you typed yourself are never overwritten, and neither are
lags that came from a parameter file.

## Data

What you are analysing, what that data is, and where the results go — read top
to bottom.

### Input

| Field | Description |
|---|---|
| **MEA-NAP folder** | Location of your MEA-NAP clone. |
| **Raw data folder** | Folder containing your recordings, either as `.mat` (v7 or v7.3, holding `dat`/`channels`/`fs`) or as Multi Channel Systems `.h5` straight off the recorder — see [Raw data formats](#raw-data-formats). All recordings for one batch analysis should live in the same folder. |
| **Spreadsheet file** | `.csv` or `.xlsx` listing each recording's filename, group, and age/DIV — see [Setting up MEA-NAP](../setting-up-meanap.rst) for the required columns (that guide applies equally to the Python port). |
| **Spreadsheet range** ⚙ | Which rows of the spreadsheet to read, e.g. `A2:A100000` (1-indexed file lines, header = line 1). |
| **Custom group order** ⚙ | Optional comma-separated group names (e.g. `WT,KO`) to control display/plot order instead of alphabetical. |
| **Spike data folder** ⚙ | Only needed if you're starting from step 2+ using previously-detected spike times instead of raw data. |
| **Output data folder** / **Output folder name** | Where results are written, and the name of the run's output subfolder. |
| **Previous analysis folder** | On the Run tab, beside **Use prior analysis** — see [Run](#run). |

(raw-data-formats)=
### Raw data formats

Unlike the MATLAB pipeline, the Python port does not require you to convert your
recordings to MATLAB format first. It picks the format by looking inside each
file, so nothing needs renaming:

| Format | Notes |
|---|---|
| **Multi Channel Systems `.h5`** | Read directly, exactly as exported by Multi Channel DataManager. ADC counts are scaled to µV using each channel's `ConversionFactor`/`ADZero`/`Exponent`, the sampling rate comes from `Tick`, and the electrode number is the last part of the channel label (`Ref` becomes electrode 15) — the same arithmetic as `Functions/convertMCSh5toMat.m`, so results are identical to running on the converted `.mat`. |
| **Axion `.raw`** | Read directly, as exported by AxIS. See [Axion plates](#axion-plates) below — one file holds every well. Samples are scaled to **volts** by the file's own `VoltageScale`, and electrodes are numbered `column * 10 + row`, matching `rawConvertFunc.m`. |
| **`.mat` (v7.3)** | HDF5-based MATLAB file holding `dat`, `channels`, `fs`. What the MEA-NAP converters write for recordings over 2 GB. |
| **`.mat` (v7)** | The older MATLAB format, holding the same variables. What the converters write for smaller recordings. |

In your spreadsheet, list recordings **without** the extension (e.g. `TEST_DIV4`,
not `TEST_DIV4.h5`) — the pipeline finds whichever format is present. If both a
`.h5` and a `.mat` of the same name sit in the folder, the `.mat` is used, since
it holds the same data and is faster to read.

Multi Channel Systems `.mcd` and MC_Rack `.raw` still need converting to `.mat`
first, using the MATLAB GUI's File Conversion tab.

(axion-plates)=
#### Axion plates

An Axion `.raw` holds an entire plate — every well recorded together — but
MEA-NAP analyses one well as one recording. Name each row of your spreadsheet
`<file stem>_<well>`, which is exactly what `rawConvertFunc.m` calls the `.mat`
files it writes, so a spreadsheet built for the converted workflow works
unchanged against the plate itself:

```text
Recording filename,DIV group,Genotype,Ground
Plate2_treated24hrs_DIV75_A1,75,WT,
Plate2_treated24hrs_DIV75_D6,75,WT,
```

Two settings must match the plate:

- **Potential difference unit** → `V`. Axion samples convert to volts, not µV.
- **Channel layout** → `Axion16` for plates with 16 electrodes per well (24-well),
  `Axion64` for 64 electrodes per well (6-well).

Only the wells you list are read, and only their electrodes are converted, so
memory scales with one well instead of the whole plate — well under a gigabyte
for a 5-minute 24-well recording, against roughly 11 GB for MATLAB's
whole-plate `LoadData`. Naming a `.raw` without a well suffix is an error that
lists the wells the file actually contains.

### Recording

Sampling and hardware settings, used during spike detection and for mapping
channels to spatial electrode coordinates. Hidden in CAT-NAP mode, where none of
it applies.

| Field | Description |
|---|---|
| **Sampling frequency** | The recording's native sampling rate in Hz (e.g. `25000`). |
| **Downsample frequency** ⚙ | Rate used for some plots/metrics that don't need full resolution (e.g. `1000`). |
| **Potential difference unit** ⚙ | `uV`, `mV`, or `V` — must match your raw data's units. |
| **Channel layout** | Electrode grid layout: `MCS60`, `Axion64`, `Mea256`, or `Custom`. See [MATLAB vs. Python](matlab-vs-python.md) for which layouts have confirmed coordinate parity. |

## Spike detection

| Field | Description |
|---|---|
| **Detect spikes** | Whether to run spike detection at all (uncheck if step 1 was already run and you only want steps 2+). |
| **Re-check previous spike data** ⚙ | Re-run detection checks against existing spike-time output without redetecting. |
| **Relative thresholds** | MAD-multiplier thresholds below the median, comma-separated (e.g. `3, 4, 5`). |
| **Absolute thresholds (µV)** ⚙ | Fixed voltage thresholds instead of relative ones — leave blank to use relative thresholds. |
| **Wavelet methods** | One or more of `bior1.5`, `bior1.3`, `db2`, `mea` (multi-select list). |
| **Wavelet cost** ⚙ | Cost parameter for the continuous wavelet transform (default `-0.12`). |
| **Spike method for analysis** | Which detection method's output feeds steps 2–4: `bior1p5`, `bior1p3`, `mergedAll`, `mergedWavelet`, `thr4p5`, `thr5p0`, `thr3p5`. |
| **Low-pass / high-pass cutoff** ⚙ | Bandpass filter applied before detection (default 600–8000 Hz). |
| **Refractory period** ⚙ | Minimum inter-spike interval (ms) enforced during detection. |
| **Max spikes for template** ⚙ | Cap on spikes used to build the spike-shape template. |
| **Multiple templates** / **Template method** ⚙ | Whether to cluster spikes into multiple templates, and by which method (`PCA`, `spikeWidthAndAmplitude`, `amplitudeAndWidthAndSymmetry`). |

:::{dropdown} Which spike detection method should I use?
`bior1.5` (a biorthogonal wavelet CWT) is MEA-NAP's flagship method and the
default `spikes_method`. The Python port's wavelet detector currently reaches
~82–84% F1 agreement with MATLAB's native CWT implementation (PyWavelets
approximates the wavelet via a cascade algorithm rather than MATLAB's exact
one) — see [MATLAB vs. Python](matlab-vs-python.md). The simple threshold
methods (`thr4`, `thr5`) match MATLAB exactly.
:::

## Connectivity

Functional connectivity via the spike time tiling coefficient (STTC) and its
significance thresholding.

| Field | Description |
|---|---|
| **Lag values (ms)** / **Bin length (ms)** | One or more connectivity timescales, comma-separated; each produces its own adjacency matrix and downstream network metrics. For STTC these are lags (the coincidence window); in CAT-NAP with a correlation activity type (`F`, `spks`, `denoised F`) the field relabels itself and they are correlation **bin** lengths instead — see [Activity types](catnap.md#activity-types). Defaults to `10, 15, 25` for ephys and `1000, 2500, 5000` in CAT-NAP mode — see [Modes](#modes). |
| **Truncate recording** / **Truncation length** ⚙ | Optionally analyze only the first *N* seconds of each recording (useful for very long recordings). |
| **Weighted / Binary** | Whether the adjacency matrix keeps STTC values as edge weights or collapses to a 0/1 connection. |
| **Iterations** | Number of circular-shift surrogates used for significance thresholding (default `200`). |
| **Tail percentile** ⚙ | Upper-tail cutoff for significance (default `0.05`). |
| **Plot random checks** / **Number of checks to plot** ⚙ | Optionally save diagnostic plots for a few random thresholding surrogates. |

:::{dropdown} Why does step 3 take so long?
Probabilistic thresholding runs `Iterations` circular-shift surrogates *per
lag, per recording* to build a null distribution for each edge — this is the
dominant cost of a full pipeline run. It's also inherently non-deterministic:
even two MATLAB runs of the same recording won't produce bit-identical
thresholded matrices. See [MATLAB vs. Python](matlab-vs-python.md).
:::

## CAT-NAP (2P)

Calcium-imaging analysis, triggered by pointing the pipeline at a folder of
suite2p output rather than raw MEA `.mat` files. Full walkthrough:
[CAT-NAP](catnap.md).

## Run

One tab for starting work, with a switch at the top for what the **Run** button
starts: **This run** — the analysis the other tabs describe; **Queue of
saved runs**, which works through several saved parameter files one after
another; or **Shared with other computers**, which splits this run's
recordings across several computers through a folder they all see and pools
the results here (see [Sharing a run across several computers](shared-run.md)).
Either way there is one Run button, one Stop button, one progress bar and one
log, so a run cannot be started while another is going.

| Field | Description |
|---|---|
| **Start at step** / **Stop at step** | Which of the 4 steps to run, inclusive (1–4). Moving one past the other drags the other along, so the range always stays valid. |
| **Use prior analysis** | Read the steps before **Start at step** from an earlier run instead of recomputing them. Ticking it enables the folder fields underneath. |
| **Previous analysis folder** / **Additional folders** | The earlier run(s) to read. Each may be an `OutputData…` folder or a `.meanap` bundle. Naming more than one combines them: a spreadsheet listing recordings from several runs is analysed as one batch — see [Combining separate runs](changing-a-batch.md#combining-separate-runs). |
| **Optional steps** ⚙ | Extra steps to run alongside the core 4, e.g. `generateCSV`. |
| **Verbose level** ⚙ | `Normal`, `Verbose`, or `Debug` logging detail in the status log. |
| **Time each step** ⚙ | Records per-step wall-clock time to `step_durations.json` in the output folder. |
| **Fixed random seed** ⚙ | Makes the stochastic steps (3 and 4) reproducible. Off — the default, matching MATLAB — gives a fresh seed per run. |
| **Continue previous run** | Picks up a run that stopped partway: writes into the same output folder and skips any recording already finished. Also how you add or remove recordings — edit the spreadsheet, tick this, and only the new ones are analysed. Everything pooled across the batch is redone over whatever the spreadsheet now lists. See [Changing which recordings a run covers](changing-a-batch.md). |
| **…and drop removed recordings' figures** | Only while continuing. Deletes the plots of recordings the spreadsheet no longer names; they are excluded from every CSV either way, but their figures otherwise stay in the output folder and the report. Their data is kept, so putting a recording back stays cheap. See [Removing a recording](changing-a-batch.md#removing-a-recording). |
| **Express mode** | Skips every figure that can be redrawn later and keeps **only** a small `.meanap` bundle — the output folder is removed once the bundle is written and verified. The numbers are identical either way, and the viewer can draw the folder back out again; see [Express mode and run bundles](express-mode.md). |

The buttons under **Start**:

- **🧪 Test pipeline** — downloads the bundled example dataset and runs the
  full pipeline against it (see [Quickstart](quickstart.md)). It works with
  **Express mode** ticked, and bundles the example run like any other.
- **▶ Run pipeline** — runs against whatever the other tabs describe. In queue
  mode this reads **▶ Run queue (n)** and starts the list instead; in shared
  mode it reads **▶ Start shared run on n computers** and is only enabled on
  the main computer once at least one helper has joined.
- **■ Stop** — cancels what is running at the next step boundary. For a queue,
  it finishes the run in flight and does not start the next. For a shared run
  it stops this computer — and, from the main computer, every helper too.

Progress, a time estimate and the status log sit below them, shared by all
three kinds of run.

The shared page itself has two buttons to begin with — **Set up a shared run
on this computer…** (this becomes the main computer) and **Join a shared run
from another computer…** (this becomes a helper) — each a short wizard. Once
a run exists, the page shows its folder and a table of every computer that
has joined: its benchmark **speed**, the number of **recordings** it will do
(editable on the main computer until Start; the main computer's count is the
remainder) and its **status**, refreshed from the shared folder every few
seconds. **Finish now — do the rest here** stops waiting for the others.

## Results

The last tab: what to do once something has finished.

- **🌐 View report** — opens the run in your browser, picking the right artifact
  for it:
  - a **normal run** → (re)generates `report.html` in the output folder — see
    [Output report](output-report.md);
  - an **express run** → opens its `.meanap` bundle in the viewer, which draws
    any figure on demand in PNG or editable SVG, and can export the whole
    output folder back out for sharing.
- **📦 Open bundle…** — for a bundle from anywhere, with no run of your own
  needed. See [Opening a bundle](#opening-a-bundle).
- **Network viewer** — interactive exploration of a completed run's functional
  connectivity network, with optional cell-type overlays. Full walkthrough:
  [Network Viewer](network-viewer.md).

A line under the buttons names what **View report** would open and in which
form. With no run in this session it falls back to the output folder the Data
tab describes, including the dated default name (`OutputData<ddMonyyyy>`) used
when **Output folder name** is blank — so that line is worth reading before
pressing it.

### Opening a bundle

A `.meanap` bundle does not need a run, or even the data it came from — it is a
file people email each other. Two ways to open one:

- **📦 Open bundle…** on the Results tab;
- **drag the `.meanap` file onto the window**, anywhere.

Either starts the viewer and opens a browser on it. Each bundle gets its own
viewer, all of them shut down when MEA-NAP closes, and opening the same bundle
twice reuses the page already serving it.

```{note}
The bundle is written **beside** the output folder, not inside it —
`OutputData07Aug2026/` and `OutputData07Aug2026.meanap` sit side by side. The
status log repeats the full path in a framed block at the end of an express
run, after the timing lines.
```
