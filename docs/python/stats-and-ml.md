# Statistics and machine learning (step 5)

Steps 1–4 measure things. Step 5 asks what they mean: whether a metric differs
by age or genotype, which metrics are really the same measurement, whether the
groups can be told apart from the features at all, and — the part that is
usually the real question — *which* features carry that difference.

It runs over a **finished run**, not over raw recordings, so it works on an
output folder or a `.meanap` bundle, including ones from months ago or from a
collaborator. Nothing needs re-running.

```bash
uv run meanap-stats path/to/OutputData…            # a folder
uv run meanap-stats path/to/OutputData….meanap     # or a bundle
```

In the GUI it is the **Stats & ML** tab, the last one: choose a run, pick the
analyses, press *Run statistics*.

Results land in `5_StatsAndML/<lag>/` — a CSV and a figure for everything
computed, browsable in the HTML report and the bundle viewer like any other
step.

## One thing to know before reading any of it

**A recording is not an independent sample.** The same culture is usually
imaged at several ages, so its recordings are repeated measures. Step 5 works
this out from the recording names (dropping the date and `DIV` tokens) and uses
it throughout:

- mixed models get a random intercept per culture, not per recording;
- cross-validation holds out **whole cultures**, so a classifier is never
  tested on a culture it has already met at another age;
- the permutation null shuffles labels *between* cultures, since in the real
  data a culture has one genotype at every age.

The panel prints what it found — *"378 recordings from 121 cultures"* — before
anything runs, so you can check the culture count is right. If it says every
recording is its own culture, either the design really is cross-sectional or
the names do not encode the culture in a form this can read; either way the
analysis is then conservative rather than wrong.

## What it computes

### Comparisons — does a metric differ by age or genotype?

Per metric: an age slope and genotype contrasts from a mixed model, an omnibus
test across all genotypes, an age×genotype interaction, group contrasts within
each age, and paired age-to-age contrasts on the cultures imaged at both.
Everything carries a Benjamini–Hochberg FDR-corrected p-value alongside the raw
one — with ~50 metrics and several tests each, reading raw p-values guarantees
false positives. Effect sizes are Hedges' *g*.

### Adjusted effects — does an effect survive holding firing rate fixed?

A significant age effect on network density says density rises with age. It
does not say why. If firing rate rises with age too, part or all of the
density effect may be rate passed on: more spikes give the STTC significance
test more power, so more edges pass. To ask whether density rises *beyond*
rate, step 5 refits the comparison model with rate added,

```
metric ~ age + genotype + rate + (1 | culture)
```

and reads the age coefficient again. That coefficient is the age effect at
fixed rate. The same is done for every metric and for each **adjustment set**
you choose. Each effect is then shown beside the unadjusted one, in
`adjusted_effects.csv` and in figure **5A4**.

| Set | Covariates |
|---|---|
| Firing rate (default) | `FRmean` (or `FRmedian`) |
| Firing rate + active units (default) | rate and `numActiveElec` |
| Network size + density | `aN` and `Dens` |
| Network bursting | `NBurstRate` and `fracInNburst` (ephys only) |
| Your own | any columns, joined by `+`. A column that is not a number, such as a plate or batch, enters as a factor. |

Rates and counts that span orders of magnitude are logged before they enter
the model.

How to read it:

- **A dot that moves to zero** was carried by the covariate. One that stays is
  an effect beyond it. The `Retained` column gives the adjusted effect as a
  fraction of the unadjusted one.
- **"Carried by" is not "not real".** If age raises rate and rate raises
  density, rate is a *mediator*. The adjusted effect is the part of the age
  effect that does not pass through rate. Adjusting for something the network
  itself causes, such as bursting or network size, can hide a real effect or
  create a false one.
- **Check the design R².** Each set reports how much of its covariates age and
  genotype explain. When rate climbs in lockstep with age, the model cannot
  tell the two apart, and an effect that disappears is undecided rather than
  absent. The figure flags R² above 0.8 with ⚠.
- **The same recordings throughout.** Every set is fitted on the recordings
  that have every covariate, so a change between sets is the adjustment, not
  the cohort.
- **No self-adjustment.** A metric is not adjusted for itself or for a
  near-copy (|Spearman ρ| ≥ 0.95). Its row says so.

Example: in the published Mecp2 MEA timecourse (DIV 7–35), median firing rate
rises about 100-fold. The age effect on network density falls from +1.39 SD to
+0.30 SD (not significant) with rate in the model. Mean STTC keeps a third of
its effect (+0.58 SD, still significant). Design R² is 0.41, so rate and age
are separable here, if not by much.

From the command line: `meanap-stats RUN --adjust-for rate activity
FRmean+numActiveElec`. Give `--adjust-for` with no sets to skip it.

**Exploring in the results viewer.** Open 5A4 under *Statistics → Group and
age comparisons* and a **Hold fixed** panel appears beside it. Tick or untick
the preset sets, or build your own set by searching for and ticking columns
(they are held fixed together). The figure is refitted and redrawn for each
change, in about a second for a 50-metric run, so you do not need to rerun
step 5 to try another covariate. A set this run cannot resolve is greyed out,
and its tooltip says why. Sets tried before are kept in memory for the
session. What step 5 wrote to `adjusted_effects.csv` is not changed.

Each significant effect gets a verdict. Its row is tinted green if the effect
stays significant, in the same direction, under every set ticked. It is tinted
red if it loses significance under all of them. A count at the right of the
row, such as `2/3`, says how many sets it survives. A set is left out of a
row's count when the metric is, or nearly copies, one of that set's
covariates. The **View** menus at the top of the panel narrow a crowded figure:

- **Effect** shows one panel (Age, or a single genotype contrast).
- **Show** keeps the rows that survive every set, are lost under some, or are
  lost under all.
- **Sort by** orders the rows by unadjusted effect size, by how much of the
  effect is lost (most lost first), or by name.

The random-intercept model is fitted by exact REML. The fit profiles out the
fixed effects and searches a single variance ratio, which is fast enough for
the viewer. Its estimates match statsmodels' `MixedLM` to within 3 × 10⁻⁴ SD,
and its z values to within about 1%.

### Feature structure — which metrics are the same measurement?

Correlation matrices overall and per group × age, the redundant pairs, and the
**effective dimensionality** of the metric set: how many independent
measurements it is actually worth. On a typical run 50 metrics come out worth
about five, which is worth knowing before treating them as 50 findings.

### Decoding — can the groups be told apart?

Six classifiers, culture-grouped cross-validation, a label-permutation null,
and held-out permutation feature importance, plus a discriminant projection.
Reported as **balanced accuracy against a chance line of 1/*n* classes**, not
raw accuracy, which rewards a model for always guessing the biggest group.

Two attributions come with it:

- **per-age attribution** — each feature's Shapley share of the decoding
  accuracy, computed separately within each age and read across ages, so you
  can see *when* in development a feature starts to matter;
- **feature families** — the same split with three whole families as the
  players: activity (firing), correlation strength (density, degree, node
  strength) and network topology (efficiency, clustering, modularity,
  cartography). This is what answers whether an apparent difference in network
  *organisation* is more than a difference in firing and correlation.

### Variance attribution — how much does each feature explain?

Predicts a continuous target (age by default, or any metric) and partitions its
R² across the features. Each feature gets three numbers, because with collinear
metrics one is not enough:

| | meaning |
|---|---|
| **Marginal** | what it explains alone — its ceiling |
| **Unique** | the drop in R² if it is removed — its floor |
| **Shapley** | its share; these sum to the model's R² |

A feature with a large marginal and a near-zero unique is *redundant*, not
unimportant. Reading `Unique` alone is the standard way to wrongly conclude
that none of a set of correlated predictors matters.

## Density sweep — comparing topology fairly

Off by default; tick **Density sweep** in the GUI or pass `--density-sweep`.

Every graph metric depends on how many edges the network has and on how many
nodes it has, and both usually differ between groups and rise with age. A
difference in clustering or efficiency measured at each network's own density
therefore cannot be read as a difference in organisation. Normalising against
null models does not fix this — a degree-preserving null preserves density
exactly, so the ratio is density-*conditioned*, and it saturates as the graph
approaches complete.

The sweep does what the literature does instead
([van Wijk et al. 2010](https://doi.org/10.1371/journal.pone.0013701);
[Ginestet et al. 2011](https://doi.org/10.1371/journal.pone.0021570)):
thresholds every recording to the **same proportion of edges**, 2 % to 40 % in
2 % steps, binarised so connection strength goes too, and repeats across the
range. Networks are also **subsampled to a common node count** first, closing
the size half of the same problem. It writes metric-versus-density curves by
group and by age, and **cost-integrated features** (`<metric>_costInt`) — one
density- and size-controlled number per recording, which feed straight back
into the family decomposition.

```bash
uv run meanap-stats <run> --density-sweep                  # both controls
uv run meanap-stats <run> --density-sweep --sweep-nodes 0  # density only
```

Three things to read it with:

- **It is slow.** Tens of minutes on a few hundred recordings — the work is
  multiplied by both the density grid and the number of node draws. Lower the
  effort preset to shorten it.
- **Check the retention line.** Recordings with fewer nodes than the target are
  dropped, and small networks are not randomly distributed across groups. The
  run reports the kept fraction per group and warns when it differs by more
  than 20 points, because at that point the size confound has been traded for a
  selection one rather than removed.
- **Check `lccFraction`.** Sparse thresholds fragment a network, and path
  length is averaged over connected pairs only — so a *more* fragmented network
  can show a *shorter* path length. Where the largest component is well below
  1, read global efficiency instead of path length.

## Cell types — the X-linked mosaic (CAT-NAP)

On by default; it runs whenever the run has cell-type calls
(`2_NeuronalActivity/CellTypeCalls.csv`) and is skipped otherwise. Untick
**Cell types: Mecp2 mosaic** in the GUI or pass `--no-mosaic` to turn it off.

This is the one analysis in step 5 whose sample is a **cell**, not a
recording. In a culture heterozygous for an X-linked gene such as *Mecp2*,
X-inactivation makes each cell either express the gene or not, and staining
says which. Marker− and marker+ neighbours share one network, so comparing
them separates what the gene does **inside the cell** from what it does
**through the network**:

| | marker+ cell | marker− cell |
|---|---|---|
| WT culture | WT | — |
| Het culture | Het+ | Het− |
| KO culture | — | KO |

Five contrasts per feature, from a mixed model with culture and recording as
random effects:

| contrast | compares | reads as |
|---|---|---|
| cell-autonomous | Het− vs Het+ | the gene's effect inside the cell, network held fixed |
| environment (+) | Het+ vs WT | a marker+ cell in a mutant network |
| environment (−) | KO vs Het− | a marker− cell in a fully mutant network |
| genotype | KO vs WT | the total difference |
| per week | change in Het− vs Het+ with age | when a cell-autonomous gap opens |

Groups are recognised from the calls themselves: a group with 10–90 %
marker+ cells is the mosaic, and groups at ≥95 % or ≤5 % are the references.
In the references the marker state follows from the genotype, so **every** cell
in a WT or KO culture is used, not only the stained ones.

Alongside the contrasts:

- **KO-score**: a classifier trained on WT against KO cells, applied to Het
  cells. If marker− cells score more KO-like than their marker+ neighbours, the
  KO phenotype is partly cell-autonomous.
- **Decoder**: can a cell's marker state be read from its features alone?
  Features are z-scored within each recording and the null shuffles labels
  within each recording, so it cannot succeed from differences between
  networks.
- **Trajectories** of each class across age.

Everything is computed twice: on **all labelled cells**, and on **tracked
cells only**, where the same cell seen on several days adds a random effect.
`--mosaic-marker` picks a marker other than Mecp2.

Two cautions:

- Network features are **not** normalised within each recording for the
  environment and genotype contrasts, since that would force those contrasts to
  zero. Those contrasts therefore carry the network size and density confound
  that the density sweep addresses. The cell-autonomous contrast does not,
  because neighbours share a network.
- When a mixed model does not converge it falls back to ordinary regression
  with errors clustered by culture; the `Fit` column of `mosaic_effects.csv`
  records which.

## Effort and runtime

The **Effort** preset scales the cross-validation repeats, permutation counts
and Shapley orderings together.

| Preset | Roughly |
|---|---|
| Quick look | seconds to a minute; no permutation null, so no p-values |
| Standard | a few minutes |
| Thorough | tens of minutes; worth it when a p-value near 0.005 must be resolved |

The density sweep sits outside this and is the slowest thing by a wide margin.

## Where the outputs go

```
5_StatsAndML/
└── <lag>/
    ├── 5A…  comparisons — effect heatmaps, trajectories, adjusted effects (5A4)
    ├── 5B…  feature structure — correlation, dimensionality
    ├── 5C…  decoding — performance, confusion, importance, attributions
    ├── 5D…  variance attribution
    ├── 5E…  density sweep (when run)
    ├── 5G…  cell-type mosaic (when the run has cell-type calls)
    └── *.csv  every table the figures were drawn from
```

A `.meanap` bundle carries the **tables** and not the pictures: every figure
here is a pure function of the CSVs beside it, so the viewer redraws them on
demand and a bundle stays small. See {doc}`express-mode`.
