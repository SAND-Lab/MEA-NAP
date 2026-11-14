---
key: density_sweep
name: Density sweep and size matching
tab: Stats & ML
labels: Match size:
params:
related: stats_analyses, stats_decoding, adjacency
---
The density sweep compares network topology between recordings at the same edge density and, by default, the same number of nodes. Without it, differences in density and network size get mistaken for differences in organisation.

## What it does

Every graph metric depends on how many edges and how many nodes a network has, and both usually differ between groups and rise with age. The sweep removes that confound. It thresholds every recording's adjacency matrix so the same proportion of edges survives, binarises the result, and repeats this from 2% to 40% in 2% steps. From the resulting curves it writes metric-against-density figures by group and age, and one **cost-integrated** value for each recording and metric (`<metric>_costInt`).

**Match size:** decides whether each network is also cut down to a common number of nodes first:

- **Automatic (recommended)** sets the target at the 20th percentile of this run's node counts. Each network is subsampled to that many randomly drawn nodes and averaged over several draws (5, 20 or 40, depending on the Effort preset).
- **Off — control density only** leaves network size uncontrolled.

## Choosing a value

Keep **Automatic**. Size is often the bigger of the two confounds: recordings whose networks differ in node count are not comparable even at matched density. Choose **Off** only as a check of what matching size changes.

## How MEA-NAP uses it

The sweep reads the per-recording adjacency matrices in `ExperimentMatFiles`, not the metric tables, so it needs a run that kept them. The cost-integrated features are fed back into the family decomposition of decoding.

## Things to watch for

- **It is slow.** It takes tens of minutes on a few hundred recordings, because the work multiplies the density grid by the number of node draws. A lower Effort preset shortens it.
- **Recordings with fewer nodes than the target are dropped,** and small networks are rarely spread evenly across groups. The log prints how many were kept in each group and warns when the groups differ a lot. In that case the size confound has been swapped for a selection confound rather than removed.
- Sparse thresholds break networks into pieces. Path length is averaged only over connected pairs, so a more fragmented network can show a shorter path length. Where `lccFraction` is well below 1, read global efficiency instead.
