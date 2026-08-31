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
    ├── 5A…  comparisons — effect heatmaps, trajectories
    ├── 5B…  feature structure — correlation, dimensionality
    ├── 5C…  decoding — performance, confusion, importance, attributions
    ├── 5D…  variance attribution
    ├── 5E…  density sweep (when run)
    └── *.csv  every table the figures were drawn from
```

A `.meanap` bundle carries the **tables** and not the pictures: every figure
here is a pure function of the CSVs beside it, so the viewer redraws them on
demand and a bundle stays small. See {doc}`express-mode`.
