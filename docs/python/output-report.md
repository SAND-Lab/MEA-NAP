# Output report

After a pipeline run (or against any existing MEA-NAP output folder), the
**🌐 View report** button on the Pipeline tab generates `report.html` at the
root of that output folder and opens it in your browser.

```python
# You can also generate it directly, without the GUI:
from meanap.pipeline.report import generate_report
generate_report("/path/to/OutputData...")  # writes report.html there, returns its path
```

## What it looks like

- A **folder-tree sidebar** on the left, matching the same output structure
  MATLAB's `CreateOutputFolders.m` builds (`1_SpikeDetection`,
  `2_NeuronalActivity`, `3_EdgeThresholdingCheck`, `4_NetworkActivity`, ...).
- A **captioned image gallery** on the right for whichever folder is
  selected.
- **Data files** (`.npz`/`.json`/`.csv`/`.mat`) are listed with a short
  caption rather than embedded — clicking one opens/downloads it via your
  browser's normal `file://` handling.

It is a **single self-contained HTML file**: no server, no external
JavaScript or CSS, no new dependencies beyond a browser. It works entirely
offline and can be emailed, zipped, or committed alongside the rest of an
output folder.

## Where captions come from

Figure captions are adapted from MEA-NAP's own figure-legend reference
([MATLAB outputs](../meanap-outputs.rst)) wherever that page documents a
matching figure, reworded to describe what the *Python port's* version of the
plot actually shows (MATLAB's originals sometimes also render additional
"scaled to whole dataset" or "combined" variants the Python port doesn't
produce). A handful of step-2 burst-heatmap figures have no MATLAB
documentation anywhere in the repository; their captions were written from
scratch to match the documented semantics of their sibling figures.

## Deep links

Every plot lives at a URL fragment you can share directly:

```text
report.html#4_NetworkActivity/4A_IndividualNetworkAnalysis/<group>/<recording>/<lag>mslag
```

Opening a link like this auto-expands the sidebar tree and navigates straight
to that folder — useful for pointing a labmate at one specific plot without
walking them through the tree by hand.
