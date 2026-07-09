# MATLAB vs. Python: what's ported, what's approximate, what's missing

The Python port is a genuine reimplementation of MEA-NAP's core analysis
steps, actively validated against real MATLAB output. This page summarizes
that validation honestly, so you know what to trust and what to
double-check before using the Python port for a publication figure.

```{admonition} For contributors
:class: seealso
This page is the short, user-facing summary. The full engineering log — with
exact test names, fixture files, and line-by-line gotchas for anyone touching
`src/meanap/pipeline/` — lives in
[`python/PIPELINE_PORT_STATUS.md`](https://github.com/SAND-Lab/MEA-NAP/blob/main/python/PIPELINE_PORT_STATUS.md)
in the repository.
```

## Three kinds of "parity" with MATLAB

Not every metric *can* match MATLAB bit-for-bit, and that's expected rather
than a bug — it's worth understanding the three categories before reading the
table below:

::::{grid} 1
:gutter: 2

:::{grid-item-card} ✅ Exact parity
Deterministic computations validated to match MATLAB's own output to
floating-point precision (e.g. `~1e-15`). Spike time tiling coefficient,
electrode coordinate lookup, core graph metrics (degree, density, clustering,
path length, efficiency, betweenness centrality) all fall here.
:::

:::{grid-item-card} 🎲 Deterministic given the same random input
Some MATLAB steps use randomization that is *never seeded* — even two MATLAB
runs of the same recording produce different numbers here. For these, the
Python port validates that its **formulas** match MATLAB exactly when fed the
*same* random intermediate result, without trying to reproduce MATLAB's
specific RNG stream (which isn't reproducible even between two MATLAB runs).
This covers significance thresholding (step 3), community detection and the
normalized participation coefficient, and small-worldness's null models.
:::

:::{grid-item-card} 🧮 Algorithm differs, not just RNG
Non-negative matrix factorization (NMF) uses `scikit-learn`'s coordinate
descent solver rather than MATLAB's Alternating Least Squares — a genuinely
different algorithm, not just a different random seed. Treat
`num_nnmf_components` and related outputs as approximate.
:::

::::

## Step-by-step status

| Step | Status |
|---|---|
| **1. Spike detection** | Threshold-based methods (`thr4`, `thr5`) match MATLAB exactly. The flagship `bior1.5` wavelet method reaches ~82–84% F1 agreement with MATLAB — PyWavelets approximates the wavelet differently than MATLAB's native CWT. |
| **2. Neuronal activity** (firing rates, bursts) | Exact parity confirmed field-by-field against MATLAB's own summary CSVs, when fed the same spike times. |
| **3. Functional connectivity** (STTC) | The STTC computation itself has exact parity. Significance thresholding is inherently non-reproducible between runs (see above) — this is true of MATLAB too. |
| **4. Network metrics** | Core graph metrics (ND, NS, density, clustering, path length, global/local efficiency, betweenness centrality) have exact parity. Modularity-dependent metrics (participation coefficient, module z-score, rich club, node cartography, hub classification, small-worldness) have exact parity *given the same community assignment* — the community assignment itself is stochastic in both MATLAB and Python. Controllability metrics are fully ported. NMF-based metrics are approximate (different algorithm, see above). |

## Known gaps

- **No group-level statistical comparisons yet.** MATLAB's step 5 (comparing
  network features across ages/genotypes with statistics) is not implemented
  — the Python port currently produces per-recording, per-lag results plus
  batch-scaled plot variants, not MATLAB's full `RecordingsByGroup`/
  `GraphMetricsByLag` group-comparison figures and CSVs.
- **`Custom` channel layout is not supported.** MATLAB's user-drawn custom
  electrode layout has no Python equivalent yet; the port supports
  `MCS60old`, `MCS60`, `MCS59`, `Axion64`, and `Axion16`, all with confirmed
  exact coordinate parity against MATLAB.
- **No single combined output `.mat` file.** MATLAB writes one
  `<recording>_<output>.mat` per recording containing `Info`/`Params`/
  `spikeTimes`/`Ephys`/`adjMs` together. The Python port instead writes
  `.npz`/`.json`/`.csv` per step (see the [output report](output-report.md)
  page for the full folder layout) plus a per-recording adjacency `.npz`.
- **Spatial/temporal autocorrelation metrics are not implemented** — these
  aren't in MATLAB's own default metric list either, and MATLAB's own code
  path for temporal autocorrelation is an explicit unfinished stub, so
  there's no complete reference behavior to port yet.
- **Some diagnostic-only plots are not ported**: the null-model-iteration
  convergence plot, and log-scaling on two of the step-2 burst heatmaps
  (cosmetic axis transform, not exercisable on the bundled example data since
  it has no detected bursts).

## Performance expectations

The slowest parts of a full pipeline run are, by design, the parts that are
doing genuine repeated-sampling statistics rather than being slow to
implement:

- **Step 3** re-runs STTC significance thresholding (default 200 circular-shift
  surrogates) per lag, per recording.
- **Step 4**'s normalized participation coefficient runs 100 degree-preserving
  network randomizations per (recording, lag).

Neither of these is a Python-vs-MATLAB speed question — MATLAB pays the same
cost for the same statistical rigor. A full run on the bundled two-recording
example dataset takes a few minutes; see [Quickstart](quickstart.md) if you
just want to see steps 1–2 (fast) without waiting for 3–4.
