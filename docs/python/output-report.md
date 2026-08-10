# Output report

After a pipeline run (or against any existing MEA-NAP output folder), the
**🌐 View report** button on the Results tab generates `report.html` at the
root of that output folder and opens it in your browser.

```{note}
If the run used {doc}`express-mode`, that button opens the run's `.meanap`
bundle in the interactive viewer instead — an express run keeps only the bundle,
so there is no folder to build a report from. The viewer's **Export output
folder** writes one, `report.html` included. See [Related: the interactive
viewer](#related-the-interactive-viewer) below.
```

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

## Run parameters

The sidebar's **⚙ Run parameters** entry shows the settings the run used, read
from `params.json` and grouped the way `Params` groups them — Recording, Spike
detection, Connectivity, and so on. It opens on **only what differs from the
defaults**, which on a typical run is a dozen fields out of ~140, with the
default each one departed from shown beside it; a toggle expands to all of them.

Remote share links are replaced with a placeholder. A report is a file people
attach to papers and email onward, and a Dropbox link in one is a credential.

The entry is absent for an output folder with no `params.json` — an older run,
or one that failed before writing it.

## Related: the interactive viewer

`report.html` shows the figures a run *wrote*. If you ran with
{doc}`express-mode`, none were — use `meanap-viewer` instead, which redraws them
on demand and can export SVG. The two are complementary: `report.html` needs
nothing installed, the viewer needs Python running but can restyle and
re-export.

To get a `report.html` out of an express run, open the bundle and press
**Export output folder**: it draws every figure into a normal output folder and
generates the report alongside them. That folder is what you send to someone
without MEA-NAP.

The GUI picks between them for you: **🌐 View report** opens the viewer for an
express run and builds `report.html` for a full one. You can also open any
bundle directly with **📦 Open bundle…** on the Results tab, or by dragging the
`.meanap` file onto the window.
