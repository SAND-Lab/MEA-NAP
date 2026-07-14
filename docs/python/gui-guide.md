# GUI guide

The `meanap-gui` desktop app (PyQt6) mirrors the MATLAB App Designer
interface: one tab per section of the pipeline. Parameters round-trip to and
from a `Params` dataclass (`meanap.params.Params`, see the
[API reference](api/index.rst)) via each panel's `load()`/`save()` methods, and
can be saved/reloaded as JSON from the toolbar (**New**, **Open params…**,
**Save params…**).

```{admonition} In a hurry?
:class: tip
[Quickstart](quickstart.md) skips all of this via the **🧪 Test pipeline**
button, which fills in sensible defaults and the bundled example dataset
automatically.
```

## Paths

Where MEA-NAP reads your data from and writes results to.

| Field | Description |
|---|---|
| **MEA-NAP folder** | Location of your MEA-NAP clone. |
| **Raw data folder** | Folder containing your recordings in `.mat` format. All recordings for one batch analysis should live in the same folder. |
| **Spreadsheet file** | `.csv` or `.xlsx` listing each recording's filename, group, and age/DIV — see [Setting up MEA-NAP](../setting-up-meanap.rst) for the required columns (that guide applies equally to the Python port). |
| **Spreadsheet range** | Which rows of the spreadsheet to read, e.g. `A2:A100000` (1-indexed file lines, header = line 1). |
| **Custom group order** | Optional comma-separated group names (e.g. `WT,KO`) to control display/plot order instead of alphabetical. |
| **Spike data folder** | Only needed if you're starting from step 2+ using previously-detected spike times instead of raw data. |
| **Output data folder** / **Output folder name** | Where results are written, and the name of the run's output subfolder. |
| **Previous analysis folder** | Only needed when re-using a prior run (**Use prior analysis** on the Pipeline tab). |

## Recording

Sampling and hardware settings, used during spike detection and for mapping
channels to spatial electrode coordinates.

| Field | Description |
|---|---|
| **Sampling frequency** | The recording's native sampling rate in Hz (e.g. `25000`). |
| **Downsample frequency** | Rate used for some plots/metrics that don't need full resolution (e.g. `1000`). |
| **Potential difference unit** | `uV`, `mV`, or `V` — must match your raw data's units. |
| **Channel layout** | Electrode grid layout: `MCS60`, `Axion64`, `Mea256`, or `Custom`. See [MATLAB vs. Python](matlab-vs-python.md) for which layouts have confirmed coordinate parity. |

## Spike detection

| Field | Description |
|---|---|
| **Detect spikes** | Whether to run spike detection at all (uncheck if step 1 was already run and you only want steps 2+). |
| **Re-check previous spike data** | Re-run detection checks against existing spike-time output without redetecting. |
| **Relative thresholds** | MAD-multiplier thresholds below the median, comma-separated (e.g. `3, 4, 5`). |
| **Absolute thresholds (µV)** | Fixed voltage thresholds instead of relative ones — leave blank to use relative thresholds. |
| **Wavelet methods** | One or more of `bior1.5`, `bior1.3`, `db2`, `mea` (multi-select list). |
| **Wavelet cost** | Cost parameter for the continuous wavelet transform (default `-0.12`). |
| **Spike method for analysis** | Which detection method's output feeds steps 2–4: `bior1p5`, `bior1p3`, `mergedAll`, `mergedWavelet`, `thr4p5`, `thr5p0`, `thr3p5`. |
| **Low-pass / high-pass cutoff** | Bandpass filter applied before detection (default 600–8000 Hz). |
| **Refractory period** | Minimum inter-spike interval (ms) enforced during detection. |
| **Max spikes for template** | Cap on spikes used to build the spike-shape template. |
| **Multiple templates** / **Template method** | Whether to cluster spikes into multiple templates, and by which method (`PCA`, `spikeWidthAndAmplitude`, `amplitudeAndWidthAndSymmetry`). |

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
| **Lag values (ms)** | One or more STTC synchronicity windows to compute, comma-separated (e.g. `10, 15, 25`). Each lag produces its own adjacency matrix and downstream network metrics. |
| **Truncate recording** / **Truncation length** | Optionally analyze only the first *N* seconds of each recording (useful for very long recordings). |
| **Weighted / Binary** | Whether the adjacency matrix keeps STTC values as edge weights or collapses to a 0/1 connection. |
| **Iterations** | Number of circular-shift surrogates used for significance thresholding (default `200`). |
| **Tail percentile** | Upper-tail cutoff for significance (default `0.05`). |
| **Plot random checks** / **Number of checks to plot** | Optionally save diagnostic plots for a few random thresholding surrogates. |

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

## Network Viewer

Interactive exploration of a completed run's functional connectivity network,
with optional cell-type overlays. Full walkthrough:
[Network Viewer](network-viewer.md).

## Pipeline

Run controls and step selection.

| Field | Description |
|---|---|
| **Start at step** / **Stop at step** | Which of the 4 steps to run, inclusive (1–4). Moving one past the other drags the other along, so the range always stays valid. |
| **Use prior analysis** | Load results from **Previous analysis folder** (Paths tab) instead of recomputing. |
| **Optional steps** | Extra steps to run alongside the core 4, e.g. `generateCSV`. |
| **Verbose level** | `Normal`, `Verbose`, or `Debug` logging detail in the status log. |
| **Time each step** | Records per-step wall-clock time to `step_durations.json` in the output folder. |

The four buttons under **Run**:

- **🧪 Test pipeline** — downloads the bundled example dataset and runs the
  full pipeline against it (see [Quickstart](quickstart.md)).
- **▶ Run pipeline** — runs against whatever's configured in Paths/Recording/etc.
- **■ Stop** — cancels a running pipeline at the next step boundary.
- **🌐 View report** — (re)generates `report.html` for the current output
  folder and opens it — see [Output report](output-report.md).
