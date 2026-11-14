---
key: stats_analyses
name: Statistics and machine learning analyses
tab: Stats & ML
labels: Run to analyse; Analyses; Progress
params:
related: stats_decoding, density_sweep
---
Step 5 analyses a finished run: an output folder or a `.meanap` bundle. It reads the run's metric tables and writes its results to `5_StatsAndML/<lag>/`.

## What it does

**Run to analyse** picks the run. Before anything runs, the panel reports what it found, for example "378 recordings from 121 cultures", along with the metrics, groups and ages. The culture count is worked out from the recording names, with the date and DIV parts removed, and it is used throughout: mixed models get one random intercept per culture, and cross-validation holds out whole cultures. If every recording is counted as its own culture, repeated recordings of one culture will be treated as independent.

**Analyses** (on by default unless marked):

- **Compare groups and ages**: a mixed model for each metric, giving an age slope, genotype contrasts, contrasts within each age and paired contrasts between ages. All p-values are FDR-corrected.
- **Feature correlation structure**: which metrics measure the same thing, and how many independent dimensions the metric set really has.
- **Decoding**: classifies genotype or age from the metrics. Two optional splits of the result go with it. **Per-age attribution** shows which metrics carry the signal at each age. **Activity vs correlation strength vs network topology** asks whether a difference in topology is more than a difference in firing and correlation.
- **Variance attribution**: splits the R² of a continuous target, by default age, across the metrics.
- **Density sweep** (off): compares topology at matched density and network size. See its own card.
- **Compare measures of activity**: CAT-NAP runs with more than one measure only. It is free.
- **Cell types: Mecp2 mosaic**: CAT-NAP runs with cell-type calls only.

**Progress** shows the step's log while it runs.

## Choosing a value

Leave the defaults on for a first pass. They take a few minutes at the Standard effort. Analyses that do not apply to a run are skipped automatically.

## How MEA-NAP uses it

Each analysis writes CSV tables and figures for each lag. A bundle stores only the tables, and the viewer redraws the figures from them.

## Things to watch for

- Decoding needs at least two cultures in each class. Otherwise it is skipped and the log says why.
- The density sweep is greyed out when the run has no `ExperimentMatFiles`, because it needs the adjacency matrices.
