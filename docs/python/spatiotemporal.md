# Spatial and temporal autocorrelation

Shinn et al. (2023) showed that two low-level properties of recorded signals
explain a large share of the graph metrics usually read as network topology in
fMRI. The first is how smooth each node's timeseries is (**temporal
autocorrelation**). The second is how correlation falls off with distance
(**spatial autocorrelation**). Two recordings can differ in clustering,
path length or modularity simply because their signals differ in these
properties, with no difference in how the network is wired.

> Shinn, M., Hu, A., Turner, L. *et al.* Functional brain networks reflect
> spatial and temporal autocorrelation. *Nat Neurosci* **26**, 867–878 (2023).
> <https://doi.org/10.1038/s41593-023-01299-3>

The Python pipeline computes the paper's statistics for every network, in both
MEA-NAP and CAT-NAP. It can also run the paper's **spatiotemporal model**,
which tests how much of each graph metric those statistics alone predict.

## The metrics

| Column | Level | What it is |
|---|---|---|
| `TA_regional` | node | **TA-Δ₁**: the lag-1 autocorrelation of the node's timeseries. |
| `TA_global` | recording | Mean `TA_regional` over the network's nodes. |
| `SA_lambda` | recording | **SA-λ**: the length scale over which correlation decays with distance. |
| `SA_inf` | recording | **SA-∞**: the floor that long-range correlation settles to. |
| `SA_lambda_free` | recording | SA-λ from the free-start fit (below). Not in the paper. |
| `SA_amp` | recording | How far above the floor coupling starts, just above zero distance. Not in the paper. |
| `SA_inf_free` | recording | SA-∞ from the free-start fit. Not in the paper. |

SA-λ and SA-∞ come from fitting

    corr(d) = (1 − SA-∞) · exp(−d / SA-λ) + SA-∞

to the mean pairwise coupling at each distance (20 equal-width distance bins).
The fit uses the **unthresholded** coupling matrix: raw STTC on an MEA, plain
correlation or raw STTC on CAT-NAP. Thresholding would zero out the weak
long-range pairs the floor is fitted to. Like every other metric, it uses only
the network's active nodes.

### The free-start fit

The paper's curve equals 1 as distance goes to 0. That is not just the
diagonal (a node with itself, which the fit never uses). It assumes coupling
between two *distinct* sites approaches 1 as they get closer. In fMRI that
holds: neighbouring voxels sample one smooth signal. On an MEA or in calcium
imaging it does not. Two electrodes, however close, record different neurons
with independent noise, and two units sorted onto the same electrode are at
distance 0 with STTC nowhere near 1. Coupling between distinct sites starts
well below 1: a jump at zero distance, which geostatistics calls the *nugget*.

The pinned curve can only reach that lower start by decaying faster, so SA-λ
comes out short, and it mixes **how strongly** neighbours couple into **how
far** coupling reaches. On an 8×8 grid, coupling starting 0.3 above a 0.05
floor gave a pinned SA-λ of 0.71 for a true λ of 2, and 0.85 for a true λ
of 4: doubling the real length scale barely moved it.

The free-start fit leaves the start as a third parameter:

    corr(d) = SA_amp · exp(−d / SA_lambda_free) + SA_inf_free,   d > 0

with `SA_amp ≥ 0` and `SA_amp + SA_inf_free ≤ 1` (distinct sites never couple
more than a node with itself). When coupling really does start at 1 the two
fits agree. `SA_lambda_free` is the column to read as a length scale on
electrode or calcium data; `SA_amp` is neighbour coupling strength on its own.
The spatiotemporal model still uses the paper's `SA_lambda`/`SA_inf`.

The free fit is NaN where the profile cannot separate its parameters:

- **No spatial structure** (the best `SA_amp` is 0): `SA_lambda_free` is NaN,
  `SA_amp` is 0.
- **Decay over before the nearest pair** (less than 10 % of `SA_amp` left at
  the closest distance bin): only the product of amplitude and decay is seen,
  so `SA_lambda_free` and `SA_amp` are NaN. The floor is still reported.
- **Decay barely begun across the array** (`SA_lambda_free` more than 10× the
  largest distance): the profile is a straight line, so all three are NaN.

### Units

- **MEA-NAP:** SA-λ is in **electrode pitches** (nearest-neighbour spacing = 1),
  on every layout. Multiply by your array's pitch to get µm (e.g. 200 µm for an
  MCS 60MEA200/30).
- **CAT-NAP:** SA-λ is in **imaging pixels**. Multiply by µm per pixel to get
  µm. Only compare SA-λ across recordings imaged at the same zoom.

### What the timeseries is

TA-Δ₁ needs a timeseries, and spike trains and calcium events are not one. So:

- **Spikes (MEA-NAP) and `peaks` (CAT-NAP):** counts in bins of
  `ta_bin_ms` (default 100 ms; the value MATLAB's unfinished stub chose).
  TA-Δ₁ depends on this bin. Compare it only between runs that used the same
  bin.
- **Continuous traces (CAT-NAP `F`, `spks`, `denoised F`):** the traces
  averaged into each lag's correlation bin. That is the same timeseries the
  network was correlated from, so TA-Δ₁ is per lag.

## The spatiotemporal model

Switch on **Spatiotemporal model** (Connectivity tab → Spatial & temporal
autocorrelation → Advanced). For every network the pipeline then:

1. draws surrogate timeseries with the network's own SA-λ, SA-∞ and per-node
   TA-Δ₁, and nothing else. This uses the paper's correlated spectral sampling:
   brown noise correlated by the SA curve, plus white noise sized per node to
   reach its TA-Δ₁;
2. correlates them, and keeps as many edges as the data network has (the
   model's strongest pairs), giving them the data's own edge weights in rank
   order. The two networks then share nodes, density and weight distribution,
   and differ only in *where* the edges are;
3. computes the same graph metrics on it, with the same code the data uses.

This is repeated `spatiotemporal_null_reps` times (default 3) and averaged.

Outputs:

- **`ST_<metric>`** (recording level): the model's value of `NDtop25`,
  `CC_rawMean`, `PL_raw`, `Eglob`, `ElocMean` and `Q`. These are the *raw*
  clustering coefficient and path length, because `CC` and `PL` are already
  normalised by their own null networks.
- **`STrho_<metric>`** (recording level): Spearman ρ, across the network's
  nodes, between the data's and the model's `ND`, `NS`, `CC_raw`, `Eloc` and
  `BC`. Says whether the model also identifies *which* nodes are
  high-degree, central and so on.
- **`4_NetworkActivity/4B_GroupComparisons/10_SpatiotemporalModel/`**:
  `SpatiotemporalModel_Concordance.csv`, with Lin's concordance (the paper's
  measure) and Pearson's r between data and model across recordings for each
  metric and lag, and the median `STrho_*`. Also one scatter figure per lag.

**Reading it:** high concordance for a metric means that, in this batch, the
metric tells recordings apart mostly through their spatial and temporal
autocorrelation. A group difference in that metric may then be a difference in
signal smoothness or spatial spread, not in network organisation. Check whether
the group difference also shows in `SA_lambda`, `SA_inf` or `TA_global`.

The `ST_*`/`STrho_*` columns are left out of the stats module's feature set:
they are predictions of other metrics, not measurements of the culture.

## Caveats

- **The SA curve is pinned to 1 at zero distance.** That is the paper's
  definition and `SA_lambda` keeps it; `SA_lambda_free` does not (see
  [the free-start fit](#the-free-start-fit)). Coupling that starts lower is fitted with a
  shorter SA-λ: neighbouring-electrode STTC rarely approaches 1, and a curve
  that starts at 0.6 instead of 1 came back at 0.46–0.76 of its true λ on an
  MCS60 grid.
  So a difference in `SA_lambda` between groups can be a difference in how
  strongly neighbours couple, with no change in spatial extent. Check
  `SA_lambda_free` and `SA_amp` before reading it as a length.
- **STTC is not a correlation coefficient.** The model's networks are built
  from Pearson correlations. Density and rank-matched weights keep the
  comparison fair for topology, but `ST_*` values of strength-like quantities
  carry the data's weights by construction, so they test only arrangement.
- **Small arrays limit SA.** A 4×4 Axion well has distances from 1 to 4.2
  pitches, which leaves few distance bins to fit. SA is reported as NaN when
  fewer than three bins have pairs.
- **No MATLAB parity.** MATLAB lists these metrics as optional, but the
  functions it calls for them are not in the repository, so there is no MATLAB
  output to compare against.

## Implementation

`src/meanap/pipeline/spatiotemporal.py` reimplements the reference
[`spatiotemporal`](https://github.com/mwshinn/spatiotemporal) package (MIT
licence) rather than depending on it, with three changes for MEA and calcium
data. The SA fit excludes the diagonal and NaN pairs. Distance bins and the
bounds on λ scale with the data rather than being fixed in fMRI millimetres.
And SA-∞ is solved in closed form inside a grid search over λ, so the fit is
deterministic. Tests: `python/test_spatiotemporal.py`.
