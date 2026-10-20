<!--
  Release note: MEA-NAP Python beta.

  How to use this file:
  - The HTML comments (like this one) are prompts and facts for you; GitHub doesn't
    render them, but delete them before publishing anyway so the source is clean.
  - Text outside the comments is a placeholder in square brackets for you to
    rewrite, or mechanical content (install commands, links) you can keep.
  - When done, paste everything into a GitHub Release (pre-release, suggested
    tag e.g. python-v0.1.0-beta; pyproject.toml already says version 0.1.0),
    then put the release URL into the README banner's RELEASE_LINK.
  - Preview in VS Code with Ctrl+Shift+V.
-->

# MEA-NAP in Python: beta release

<!--
  1. HEADLINE — one or two sentences: what is being released, and that it is a beta.
-->

[Your opening: what's out today and that it's a beta.]

## Why a Python version?

<!--
  2. WHY — in your own words; this is the part people will remember.
  Possible threads:
  - no MATLAB licence needed (labs / students / clinics without one)
  - easier install, runs on any laptop or HPC node
  - opens MEA-NAP to the Python ecosystem (SpikeInterface, suite2p, scikit-learn, notebooks)
  - easier for others to contribute
-->

[Your reasons.]

## What's in it

<!--
  3. WHAT'S IN IT — pick highlights, don't list everything.

  The core pipeline (steps 1-4), same as MATLAB:
  - spike detection, neuronal activity (firing rates, bursts), functional
    connectivity (STTC + probabilistic thresholding), network metrics
    (graph metrics, node cartography, small-worldness, controllability, NMF)
  - same output folder structure as MATLAB
  - GUI: launch with `meanap-gui`

  Things that are new / only in Python (docs/python/ has a page for most):
  - No file conversion: reads MCS .h5, Axion .raw and .mat v7/v7.3 directly
    (traces bit-exact vs the MATLAB converters / Axion's own toolbox);
    Axion plates are read one well at a time, not the whole plate in memory
  - CAT-NAP: calcium imaging / suite2p network analysis (catnap.md)
  - MEA-Stim: electrical stimulation detection + analysis
  - Spike-sorted input: SpikeInterface sorting, units as nodes (spike-sorting.md)
  - Step 5 statistics & machine learning (stats-and-ml.md)
  - HTML output report + interactive network viewer (output-report.md, network-viewer.md)
  - Express mode (express-mode.md)
  - Resume from a previous run without the raw recordings
  - Fixed random seed -> byte-identical repeat runs (MATLAB can't do this)
  - Shared runs: split one batch across several computers (shared-run.md)
  - Refractory period for the wavelet spike detectors
-->

[Your highlights.]

## How it compares with the MATLAB version

<!--
  4. PARITY — reassure, briefly, then link matlab-vs-python.md for detail.
  Facts (from docs/python/matlab-vs-python.md):
  - Exact match (to ~1e-15): threshold spike detection (thr4/thr5),
    firing rates and bursts (same spike times), STTC, core graph metrics
    (ND, NS, density, clustering, path length, efficiency, betweenness).
  - Match given the same random draw: significance thresholding, community
    detection, participation coefficient, small-worldness. These are
    unseeded in MATLAB too, so two MATLAB runs differ as well.
  - Different algorithm: NMF (scikit-learn coordinate descent vs MATLAB ALS),
    so num_nnmf_components is approximate.
-->

[Your summary.] See [MATLAB vs Python](https://github.com/SAND-Lab/MEA-NAP/blob/main/docs/python/matlab-vs-python.md) for the full comparison.

## What "beta" means: known differences and limitations

<!--
  5. LIMITATIONS — be upfront; it builds trust.
  Candidates:
  - bior1.5 wavelet spike detection agrees ~82-84% (F1) with MATLAB, because
    PyWavelets approximates the wavelet differently from MATLAB's CWT.
    Worth stating clearly: it's the default/flagship method.
  - Axion electrode layout: Python uses the correct mapping; MATLAB's
    setUpSpreadSheet.m misplaces Axion 64-electrode positions in spatial
    plots. Decide how loudly to say this; MATLAB users may want a fix there too.
  - Plots look different from MATLAB's (styling, some layouts).
  - MC_Rack .raw / .mcd still need MATLAB's File Conversion tab.
  - Spatial/temporal autocorrelation metrics not ported (optional in MATLAB too).
  - Not on PyPI yet: install from a clone of the repo.
  - Python docs not on readthedocs yet (links below go to GitHub).
  - [anything else you know is rough]
-->

[Your list.]

## Is MATLAB going away?

<!--
  6. MATLAB — existing users will ask this first. Say plainly what happens:
  still supported? bug fixes only? new features Python-first? any timeline?
-->

[Your answer.]

## Try it

Requires Python 3.11 or later. From a terminal:

```bash
git clone https://github.com/SAND-Lab/MEA-NAP.git
cd MEA-NAP
uv sync              # or: python3 -m venv .venv && source .venv/bin/activate && pip install -e .
uv run meanap-gui    # or: meanap-gui
```

macOS users need a few build tools first (Homebrew, CMake, LLVM). See the [installation guide](https://github.com/SAND-Lab/MEA-NAP/blob/main/docs/python/installation.md). Then follow the [quickstart](https://github.com/SAND-Lab/MEA-NAP/blob/main/docs/python/quickstart.md).

## Feedback

<!--
  7. FEEDBACK — where to go (Discussions thread? issues?) and what to include
  (OS, Python version, recording format, the log / error, a screenshot).
-->

[Where and how to send feedback.]

## Citing MEA-NAP

If you use MEA-NAP (Python or MATLAB), please cite:

Timothy PH Sit, Rachael C Feord, Alexander WE Dunn, Jeremi Chabros, David Oluigbo, Hugo H Smith, Lance Burn, Elise Chang, Alessio Boschi, Yin Yuan, George M Gibbons, Mahsa Khayat-Khoei, Francesco De Angelis, Erik Hemberg, Martin Hemberg, Madeline A Lancaster, Andras Lakatos, Stephen J Eglen, Ole Paulsen, Susanna B Mierau. **MEA-NAP: A flexible network analysis pipeline for neuronal 2D and 3D organoid multielectrode recordings.** Cell Reports Methods, 4, 100901, 2024. [doi:10.1016/j.crmeth.2024.100901](https://www.cell.com/cell-reports-methods/fulltext/S2667-2375(24)00291-1)

## Thanks

<!--
  8. THANKS — contributors, beta testers, collaborators who shared data.
-->

[Your thanks.]
