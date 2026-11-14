---
key: SW
name: Small-world coefficient σ
level: recording
family: network
image: SW.png
related: SWw, CC, PL, nullmodels
---
Whether the network combines the high clustering of local circuits with the short paths of a random network: the "small-world" signature. This is method 1, σ.

## What it measures

Small-world networks have tightly clustered neighbourhoods that are linked together by a few shortcuts. This lets them handle local processing and network-wide integration at the same time. σ compares the real network with a random network that has the same number of connections per node.

σ = (C ÷ C_random) ÷ (L ÷ L_random)

where C is mean clustering and L is characteristic path length.

## Reading the values

- No units, always 0 or above.
- **σ > 1** is the usual rule of thumb for a small-world network: clustering is well above random while path length stays close to random.
- σ ≈ 1 means the network looks no more organised than random wiring. σ < 1 means it is less clustered than random, or has relatively long paths.
- σ tends to get larger as networks get bigger and sparser, because C_random shrinks. Compare it between networks of similar size, and use SWw (ω) as a check.

## How MEA-NAP calculates it

In `compute_network_metrics` (`meanap.pipeline.step4`), on the weighted active-node network:

- one degree-preserving random null model is built with `randmio_und_v2` (`meanap.pipeline.null_models`, 5,000 rewiring iterations);
- `small_worldness_rl_wu` (`meanap.pipeline.network_metrics`) computes mean weighted clustering (`clustering_coef_wu`) and weighted path length (lengths = 1/weight, `charpath`) for the real and random networks, then combines them as above.

The random-network clustering is used only for σ. The CC value MEA-NAP saves is normalised to a lattice instead.

σ is only computed when there are more than `{{param:min_number_of_nodes_to_cal_net_met}}` active nodes.

## Things to watch for

- σ relies on one random null model per recording and lag, so it varies a little from run to run unless `{{param:random_seed}}` is set.
- Very dense networks leave little room for rewiring, and the null model ends up close to the original. σ then drifts towards 1 whatever the real structure.
- If the null model has no triangles, C_random is 0 and σ becomes infinite or missing.

## References

- Watts DJ, Strogatz SH (1998) Nature 393:440–442. doi:10.1038/30918
- Humphries MD, Gurney K (2008) PLoS ONE 3:e0002051. doi:10.1371/journal.pone.0002051
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
