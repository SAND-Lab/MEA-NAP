---
key: stats_decoding
name: Targets, effort and cross-validation
tab: Stats & ML
labels: Classify:; Explain:; Effort:; CV folds:
params:
image: stats_folds.png
related: stats_analyses, density_sweep
---
These rows set what the decoding and variance-attribution analyses predict, how many repeats and permutations they use, and how the data are split for cross-validation.

## What it does

- **Classify:** is the label the classifiers predict. **Automatic** uses genotype, or age when the run has only one genotype. The list offers the run's own group and age columns.
- **Explain:** is the continuous target whose R² is split across the metrics. The default is **Age (DIV)**. Choose a metric instead to ask what explains that metric.
- **Effort:** sets the repeats, permutations and attribution orderings together:

| Preset | CV repeats | Permutations | Shapley orderings |
|---|---|---|---|
| Quick look | 1 | 0 (no p-values) | 20 |
| Standard (default) | 5 | 200 | 100 |
| Thorough | 10 | 1000 | 300 |

- **CV folds:** (default 5) is the number of cross-validation folds. Each fold holds out **whole cultures**, so a classifier is never tested on a culture it saw at another age (picture).

## Choosing a value

- Start with **Standard**. Use **Quick look** to check the pipeline end to end, and **Thorough** when a p-value near 0.005 has to be resolved. With 200 permutations the smallest p-value possible is 1/201.
- Five folds suit most designs. With few cultures the number of folds is lowered automatically, to the number of cultures in the smallest class for decoding and to the number of cultures for regression. More folds give larger training sets but noisier test scores.

## How MEA-NAP uses it

Decoding reports balanced accuracy for six classifiers against a chance level of 1/number of classes. It also reports a label-permutation null, which shuffles labels between cultures, and held-out feature importance. Variance attribution gives each metric a marginal, a unique and a Shapley share of the cross-validated R².

## Things to watch for

- Quick look skips the permutation null, so decoding reports no p-values.
- Effort also scales the density sweep's node draws and the mosaic permutations.
- Everything uses a fixed seed (0), so running again on the same run gives the same numbers.
