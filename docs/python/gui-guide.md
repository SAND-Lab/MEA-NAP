# GUI guide

The `meanap-gui` desktop app (PyQt6) mirrors the MATLAB App Designer
interface: one tab per section of the pipeline. Parameters round-trip to and
from a `Params` dataclass (`meanap.params.Params`, see the
[API reference](api/index.rst)) via each panel's `load()`/`save()` methods, and
can be saved/reloaded as JSON from the toolbar (**New**, **Open params…**,
**Save params…**). To open a `.meanap` run bundle in the viewer without
running anything, use **📦 Open bundle…** on the [Results](#results) tab — see
[Opening a bundle](#opening-a-bundle). To turn a finished run *into* one, use
**📦 Make bundle…** on the same tab.

```{admonition} In a hurry?
:class: tip
[Quickstart](quickstart.md) skips all of this via the **🧪 Test pipeline**
button, which fills in sensible defaults and the bundled example dataset
automatically.
```

(simple-view)=
## Simple view

**✦ Simple view**, at the right-hand end of the status bar, swaps the tabs for
one page that asks only for what a run needs, one question at a time:

1. **Recordings**: the folder with your recordings (for CAT-NAP, the folder
   holding one suite2p folder per recording), or a Dropbox folder link;
2. **Spreadsheet**: checked against that folder, so a recording it names but
   the folder doesn't have is flagged before the run. No spreadsheet yet?
   **Build one from the N recordings in this folder** starts one for you (see
   [Building a spreadsheet](#building-a-spreadsheet));
3. **Recording settings**: the electrode layout and sampling rate, read from
   the recordings themselves, so this step usually fills itself in (see
   [Layout from the files](#layout-from-the-files)). For CAT-NAP it asks for
   the **activity measure** instead, pre-filled and confirmed with **Continue**;
4. **Stimulation** (MEA-Stim only): the detection method and value;
5. **Results folder**.

When an answer checks out, a green tick appears beside it and it folds into a
one-line summary; a warning (an amber **!**) still lets you move on. Click a
folded answer to change it. Clicking the logo switches pipeline, **Run** starts
the run, and the page shows its progress and then **View results**.

While a run is going, the elapsed time and time left update every second, not
only when a recording finishes. If the estimate runs out first, the page says
*should be done shortly*. The Run tab's progress does the same. **Show log**
opens the live status log in a panel on the page.

The percentage is weighted by how long each step usually takes, not by
recordings finished, and spike detection moves it channel by channel. Below
10% it shows a decimal, so the start of a long batch visibly moves. The time
left is measured on your computer as the run goes: each step is estimated
from its own pace once it has done a recording, and steps not reached yet
from the run's pace so far. Recordings the spreadsheet lists but the folder
does not have are left out of both.

Each finished run also remembers how long every step took per recording, in a
small `step_times.json` in this computer's cache folder (`~/.cache/meanap/app-cache`
on Linux, `~/Library/Caches/MEA-NAP` on macOS, `%LOCALAPPDATA%\MEA-NAP\cache` on
Windows). The next run plans with those times instead of the built-in ones, so
the estimate during spike detection already knows how long step 4 takes here.
Cancelled and continued runs are not remembered; deleting the file starts
afresh, and setting the `MEANAP_STEP_TIMES` environment variable to `off` turns
it off.

For a computer's first run, the same file holds a short benchmark of the
computer, the one the **System report** and shared runs use. The app runs it
once by itself, in the background a few seconds after it first opens (about
15 s; the status bar says so), unless a run has started. It tells the estimate
how this computer compares at spike detection and at network calculations,
and with the recordings' size, read from their file headers, it gives a time
left from the moment a run starts instead of *estimating time left…*. After
the first run, that run's own spike-detection speed replaces the benchmark's.
Old-style (v7) `.mat` files cannot be sized without loading them, so they are
assumed to be the size of the others.

The version under the logo shows which MEA-NAP is running. When a newer one
is out it says so, and clicking it opens **Versions and updates**.

**Run on**, above the Run button, chooses what Run starts. It is the same switch
as the Run tab's:

- **This computer** (the default): one run of these settings.
- **A queue of saved runs**: several saved settings files, one after another.
- **Several computers (shared folder)**: the recordings shared out across
  computers that can reach a common folder (see [Shared runs](#run)).

Choosing a queue or several computers opens that page in a side panel to set
it up. **Set up…** reopens it. The Run button then takes that page's label
(*Run queue (3)*), and stays disabled until there is something to start. The
progress bar follows a queue as a whole (*Run 2 of 3 · Spike detection*).

The fields on the page are the same settings as the ones on the tabs, so
switching back with **Classic view** (top right of the page) loses nothing. The
window remembers which view you used last; the tabs are the default.

### Other settings

Below the questions, an **Other settings** card is always on the page. It gets
a green tick once every question above it is answered, changed settings or not. It has
one row for each settings tab the pipeline uses: Recordings and output, Spike
detection (or Calcium imaging), Connectivity and networks, Stimulation (MEA-Stim
only), and Pipeline steps and output. Each row shows:

- a short summary of its key values, for example *bior1.5 · thresholds 4, 5 ·
  active from 0.01 Hz*;
- an amber count of the settings in that area that differ from the pipeline's
  defaults. Hover over the row to see which ones, with their old and new
  values. The settings the questions ask for (folders, layout, sampling rate,
  stimulation detection, activity measure) are not counted.

**Express mode** is on by default in the simple view, so a run writes the quick
figures and a `.meanap` bundle (see [Express mode and run bundles](express-mode.md)).
The Pipeline steps and output row says *express mode on* or *off*. Untick it
there, and the choice is kept. A settings file you load, or ticking it either
way yourself, also takes precedence. The classic view's default is unchanged.

Click a row to unfold its sections, the same group boxes as on the tab. Click a
section to open it in a panel on the right. The panel holds the tab's own
fields, not copies, so anything changed there is changed everywhere. Close it
with **Done**, **Esc**, or a click beside it.

The search field at the top left (see [Finding a setting](#search)) opens a
setting's section in the same panel. A setting that only the tabs have, such as
the network viewer's, opens in the classic view instead.

### View results

The switch under the logo goes from **Analyse recordings** to **View results**,
for looking at a run that has already finished, yours or one someone sent you.
Drop a `.meanap` bundle or a results folder on the dashed box (or use **Open
bundle…** / **Open results folder…**), and the results viewer opens in your
browser. Under it are the other viewers the current pipeline has:

| Pipeline | Viewers |
|---|---|
| MEA-NAP | Results viewer; network viewer; spike and burst viewer |
| MEA-Stim | Results viewer; stimulation response (ΔFR); network viewer; stimulation preview; spike and burst viewer |
| CAT-NAP | Results viewer; network viewer; cell tracking (only for a run with tracking results) |

The [network viewer](network-viewer.md) opens in a window of its own on the run
you have open, with a list to pick the recording from; it is enabled once a run
has reached the network step. The spike and burst viewer and the stimulation
preview read raw recordings, not a finished run, so they use the recordings
folder and settings from **Analyse recordings**. Runs you have opened are
listed under **Recent**. **View results** at the end of a run brings you here
with that run open.

The viewer is served by MEA-NAP itself, so keep MEA-NAP open while you look.

(double-click-bundles)=
### Opening `.meanap` files by double-clicking

Once set up, double-clicking a `.meanap` file opens MEA-NAP on **View results**
with that run open, or hands it to the MEA-NAP window already open.

- **Windows and macOS desktop app**: set up by the installer.
- **Linux, or MEA-NAP run from Python**: click **Set up** at the bottom of
  **View results**, or run `meanap-gui --register-file-type` once
  (`--unregister-file-type` undoes it). It changes only your own user's
  settings; on Linux it writes a MIME type, a launcher and an icon under
  `~/.local/share`. Setting it up again is needed only if you move to a
  different copy of MEA-NAP (another virtual environment, say), and the page
  tells you when that is the case.

`meanap-gui path/to/run.meanap` opens a run the same way from a terminal.

(search)=
## Finding a setting

Both views have a search field: beside the tabs in the classic view, and at the
top left of the simple view. **Ctrl+F** (**⌘F** on a Mac) puts the cursor in it.
Type part of a setting's name, or a word for what it does, and pick a match
with the mouse or with the arrow keys and Return.

- **A setting** opens its tab, unfolds the advanced section it is in, scrolls
  to it and outlines it for a moment, with the cursor in the field.
- **A button or toolbar action** (Make bundle, Tutorial, This computer, …)
  takes you to the button, or runs the toolbar action.
- **In the simple view**, its own questions, viewers and pages come first. Any
  other setting opens in the [Other settings](#other-settings) panel, without
  leaving the page. A setting that only the tabs have switches to the classic
  view to show it. That is a detour: the simple view still opens next time.

The search covers only the tabs the current mode shows, and only the rows they
are showing. CAT-NAP's tabs are not offered in MEA-NAP mode, for example. It
also matches tooltips and a few common alternative words, so *sampling rate*
finds **Sampling frequency**, and *fs* finds it too. Matches are on the start
of a word, so *rate* does not find *separate*.

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
| **CAT-NAP · Calcium imaging** | Network analysis of suite2p calcium imaging | Data, Connectivity, CAT-NAP (calcium imaging), Run, Results |

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

## Versions and updates

The version number beside the Mode selector is also a button. It opens
**MEA-NAP versions**, which shows which copy of MEA-NAP is running and lets you
choose another.

**Cutting edge** is the `main` branch on GitHub. New features and fixes land
there between releases. When the window opens it checks GitHub in the
background, and if your clone has fallen behind, the button changes to
**v1.11.0 ⬆ update**. **Download update** fast-forwards your clone to GitHub's
`main`, and **Restart MEA-NAP** reopens the window on the new code. If the
update changes `pyproject.toml` or `uv.lock`, the dialog tells you to run
`uv sync` before restarting.

The update only ever moves forward. It changes nothing, and tells you why, if:

- you have edited a file that the update also changes. Commit or stash your
  edit first.
- your `main` has commits of its own. Merge or rebase them yourself.
- your clone is on a branch other than `main`.

**A release** is a tagged version (`v1.10.2`, …) that stays exactly as it was
published. Use one to reproduce an analysis. Choosing one checks it out into
its own folder under `~/.meanap/versions/`, using the history already in your
clone, so nothing is downloaded again. Set `MEANAP_VERSIONS_DIR` to use a
different folder. Your MEA-NAP folder is not touched, and the release opens in
a new window. Releases marked **(MATLAB)** predate the Python GUI. They open in
MATLAB (`runPipelineApp`) if `matlab` is on your PATH. Otherwise the dialog
shows the folder and tells you what to run in it.

**A development build** (`v1.11.0-dev.23`, …) is `main` as it was right after
one change was merged. A build is made automatically for every merge, and it
has no written release notes. The dialog lists them under **Development
builds**, between cutting edge and the official releases. It shows the five newest, plus the one
you're running and your default. Open one, or set it as the default, the same
way as a release. Use one to go back to "the version from before that last
change", or to pin a result made between official releases. If you're running
an official release, you're only told about newer official releases. If you're
running a development build, you're told about newer builds too.

Every Python run records the exact build it ran with, as well as the version
number. The record goes in `params.json` and the bundle manifest, under
`_meanap.build`: the nearest tag, the commit, and whether the code had
uncommitted edits. In the results viewer, hover over the version to see it.

**The default version** is the one `meanap-gui` opens. The last version you
open from the dialog becomes the default. To choose one without opening it,
use **Set as default**. The default is marked **★ default** in the list. When
MEA-NAP starts in a different copy, it switches to the default before any
window appears, setting the release up first if needed. Run
`meanap-gui --here` to open the copy you started just once, ignoring the
default. Only versions with the Python GUI can be the default. Opening a
**(MATLAB)** release leaves the default unchanged, so MEA-NAP never opens
MATLAB on its own at startup. Until you choose a version, there is no default
and `meanap-gui` opens whichever copy you run it from.

Untick **Check for updates when MEA-NAP starts** to stop the startup check. You
can still check from the dialog at any time.

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
(layout-from-the-files)=
### Layout from the files

Both views read each recording's header to fill in the electrode layout and
show the sampling rate, once the raw data folder is set. On the Data tab, each
of the two settings says where its value came from:

- **Sampling frequency** shows the rate read from the files, such as
  *12.5 kHz — read from the recordings*. Without a folder it shows *Read from
  each recording when the run starts*. It can't be edited, because no step uses
  a single rate.
- **Channel layout** carries a note beneath it:
  - *✓ Detected from the recordings*, with what it was read from;
  - an amber warning, with a **Use …** button to switch back, if you pick a
    layout the files don't match;
  - a reminder to check it when the files can't say, such as a Dropbox link
    before the run.

  The detected layout fills the setting the first time a folder is read.
  After that your choice is kept. `FromFile` is never replaced.

The simple view's **Recording settings** step shows the same, and folds to a
summary (`Axion64 · 12.5 kHz`):

| What the files show | Layout |
|---|---|
| Multi Channel Systems `.h5` | MCS60 (MCS59 at 59 channels) |
| Axion `.raw` | Axion64, or Axion16 at 16 electrodes per well |
| `.mat` with 16 / 59 / 60 channels | Axion16 / MCS59 / MCS60 |
| `.mat` with 64 channels | Axion64 if the corner electrodes (11, 18, 81, 88) carry signal, MCS60 if they are empty |

An MCS 60-electrode array has no corner electrodes, which is what tells a
64-channel Axion well from an MCS recording padded to the full grid. Reading
the corners takes a few seconds of data, which an older (v7) `.mat` can't give
without being read whole; there the sampling rate decides (Axion records at
12.5 kHz) and the step is marked **!** as a best guess. It is also marked if
the recordings disagree, or if you pick a different layout from the one the
files suggest. A batch recorded at several sampling rates is fine, since each
recording is analysed at its own rate; the summary shows the range
(`10–25 kHz`).

**🧪 Test pipeline** sets the layout the same way, so the example dataset runs
as Axion64.

(building-a-spreadsheet)=
### Building a spreadsheet

**Edit…** beside the spreadsheet field (**Build one from the N recordings…** in
the simple view) opens a table editor. If there is no spreadsheet yet, it
starts with one row per recording in the raw-data folder, named exactly as the
files are, so every row matches a recording.

It also fills in what the names say. Labs usually name recordings after what
they are: `SYN_20260904_WT_DIV14_A1` is a synapsin culture, plated
4 Sep 2026, wild type, 14 days in vitro, well A1. So:

- **Genotype** is taken from the part of the names that looks like a group: a
  word such as WT, KO, Het or Ctrl; otherwise a part that splits the
  recordings into a few repeating values; otherwise, if every name starts with
  the same word, that word (one group). Batch, date, well and animal ids are
  passed over.
- **DIV** is taken from the part that reads as an age: `DIV14`, `d7`, `day21`.

These are **suggestions**, shown in amber italics until you edit a cell or
save. A wrong group doesn't make a run fail; it quietly splits or merges the
comparisons the analysis is built on, so check them. Two tools help:

- **From the names** splits the first name into its parts. Click a part to
  fill the genotype or DIV column from that position in every name instead.
- **Call each genotype** renames a suggested value everywhere at once:
  `WT` → `Wildtype`, say.

If your DIVs are grouped (recordings at DIV 36 analysed as DIV 35, say), the
DIV read from the name is the exact day, so change those cells to the group.

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
| **Sampling frequency** | Shown, not set: read from the recordings (see [Layout from the files](#layout-from-the-files)) and saved with the run's settings for the record. Every step reads each recording's own rate from its file, so a batch recorded at different rates is fine. |
| **Downsample frequency** ⚙ | Rate used for some plots/metrics that don't need full resolution (e.g. `1000`). |
| **Potential difference unit** ⚙ | `uV`, `mV`, or `V` — must match your raw data's units. |
| **Channel layout** | Detected from the recordings, with a note saying so (see [Layout from the files](#layout-from-the-files)). Electrode grid layout: `MCS60`, `Axion64`, `Mea256`, `Custom`, or `FromFile` (each recording's own electrode positions, as written by an [import of sorted data](sorted-import.md) — use it for MaxWell HD-MEAs). See [MATLAB vs. Python](matlab-vs-python.md) for which layouts have confirmed coordinate parity. |

## Spike detection

| Field | Description |
|---|---|
| **Spike source** | *Detect spikes on each electrode* (default); *Sort spikes into units*, each unit becoming a node (see [Spike sorting](spike-sorting.md)); or *Import units sorted elsewhere* — SpyKING CIRCUS, Kilosort/phy or SpikeInterface output, set up in the **Importing sorted units** section (see [Importing spike-sorted data](sorted-import.md)). |
| **Detect spikes** | Whether to run spike detection at all (uncheck if step 1 was already run and you only want steps 2+). |
| **Re-check previous spike data** ⚙ | Re-run detection checks against existing spike-time output without redetecting. |
| **Relative thresholds** | MAD-multiplier thresholds below the median, comma-separated (e.g. `3, 4, 5`). |
| **Absolute thresholds (µV)** ⚙ | Fixed voltage thresholds instead of relative ones — leave blank to use relative thresholds. |
| **Min activity level (spikes/s)** | The firing rate an electrode must reach to count as active (default `0.01`, as in the MATLAB app). Applied after detection: it decides the number of active electrodes and which electrodes enter the firing rate statistics and the network, not which spikes are found. At `0` every electrode counts as active, even a silent one. Also on the Connectivity tab; the two fields are one setting. |
| **Wavelet methods** | One or more of `bior1.5`, `bior1.3`, `db2`, `mea` (multi-select list). |
| **Wavelet cost** ⚙ | Cost parameter for the continuous wavelet transform (default `-0.12`). |
| **Spike method for analysis** | Which detection method's output feeds steps 2–4: `bior1p5`, `bior1p3`, `mergedAll`, `mergedWavelet`, `thr4p5`, `thr5p0`, `thr3p5`. |
| **Low-pass / high-pass cutoff** ⚙ | Bandpass filter applied before detection (default 600–8000 Hz). |
| **Refractory period** ⚙ | Minimum inter-spike interval (ms) enforced during detection. |
| **Max spikes for template** ⚙ | Cap on spikes used to build the spike-shape template. |
| **Multiple templates** / **Template method** ⚙ | Whether to cluster spikes into multiple templates, and by which method (`PCA`, `spikeWidthAndAmplitude`, `amplitudeAndWidthAndSymmetry`). |

:::{dropdown} Which spike detection method should I use?
`bior1.5` (a biorthogonal wavelet CWT) is MEA-NAP's flagship method and the
default `spikes_method`. The Python port reproduces MATLAB's `bior1.5`
detection exactly, as do the threshold methods (`thr4`, `thr5`). The one
deliberate difference is a 0.5 ms refractory period on the wavelet detectors
that removes double-detections of the same trough; set **Refractory period
(wavelet detectors)** to 0 for MATLAB's output — see [MATLAB vs. Python](matlab-vs-python.md).
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
| **Min activity level** | The rate an electrode or cell must reach to count as active and enter the network (default `0.01`; spikes/s for ephys, events/s in CAT-NAP). The same setting as on the Spike detection tab. |

:::{dropdown} Why does step 3 take so long?
Probabilistic thresholding runs `Iterations` circular-shift surrogates *per
lag, per recording* to build a null distribution for each edge — this is the
dominant cost of a full pipeline run. It's also inherently non-deterministic:
even two MATLAB runs of the same recording won't produce bit-identical
thresholded matrices. See [MATLAB vs. Python](matlab-vs-python.md).
:::

## CAT-NAP (calcium imaging)

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
- **📦 Make bundle…** — packs the run's output folder into a single `.meanap`
  file you can email or attach to a paper, typically around 25× smaller because
  every figure the viewer can redraw is left out. Nothing is recomputed and the
  output folder is left as it is. See [Packing a folder you already
  have](express-mode.md#packing-a-folder-you-already-have).
- **📦 Open bundle…** — for a bundle from anywhere, with no run of your own
  needed. See [Opening a bundle](#opening-a-bundle).
- **Network viewer** — interactive exploration of a completed run's functional
  connectivity network, with optional cell-type overlays. Full walkthrough:
  [Network Viewer](network-viewer.md).

**Make bundle…** stays live even with no run in the session — the reason to
want it is usually a run that finished weeks ago. It packs the folder named
below when there is one, and otherwise asks which folder to pack, the way
**Open bundle…** asks for a file.

A line under the buttons names what **View report** would open and in which
form. With no run in this session it falls back to the output folder the Data
tab describes, including the dated default name (`OutputData<ddMonyyyy>`) used
when **Output folder name** is blank — so that line is worth reading before
pressing it.

### Opening a bundle

A `.meanap` bundle does not need a run, or even the data it came from — it is a
file people email each other. Ways to open one:

- **📦 Open bundle…** on the Results tab;
- **drag the `.meanap` file onto the window**, anywhere;
- **View results** in the [simple view](#simple-view);
- **double-click it**, once [set up](#double-click-bundles).

Each starts the viewer and opens a browser on it. Each bundle gets its own
viewer, all of them shut down when MEA-NAP closes, and opening the same bundle
twice reuses the page already serving it.

```{note}
The bundle is written **beside** the output folder, not inside it —
`OutputData07Aug2026/` and `OutputData07Aug2026.meanap` sit side by side. The
status log repeats the full path in a framed block at the end of an express
run, after the timing lines. A bundle made from a finished folder with **📦 Make
bundle…** lands in the same place, under the same name.
```
