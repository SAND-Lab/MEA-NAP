---
key: CC
name: Clustering coefficient
also: CC_rawMean
level: recording
family: network
image: CC.png
related: PL, SW, SWw, Eloc, nullmodels
---
How often a node's partners are also connected to each other (forming triangles), compared with a lattice-like version of the same network.

## What it measures

Clustering describes local, tightly knit groups: if electrodes A and B are both coupled to C, are A and B coupled too? High clustering suggests local processing within small neighbourhoods of the culture.

MEA-NAP reports two versions:

- **CC**: the mean clustering coefficient divided by that of a lattice-like null model. This is the value used in small-world analysis.
- **CC_rawMean**: the mean clustering coefficient of the real network, with no normalisation.

## Reading the values

- CC_rawMean runs from 0 to 1 and, because it is weighted, is pulled down by weak edges as well as by missing triangles.
- CC is usually between 0 and 1, because a lattice is about as clustered as a network with that degree sequence can get. Values near 1 mean the network is nearly as clustered as a lattice. It can go above 1, since the lattice is only an approximation.
- CC_rawMean rises with density, so compare it only between networks of similar size and density. CC is designed for comparing networks that differ in size and density.

## How MEA-NAP calculates it

In `compute_network_metrics` (`meanap.pipeline.step4`), on the weighted active-node network:

- `clustering_coef_wu` (`meanap.pipeline.network_metrics`) gives each node's weighted clustering coefficient (the geometric mean of the edge weights around each triangle, Onnela et al.). Their mean is **CC_rawMean**.
- A lattice-like null model is built with `latmio_und_v2` (`meanap.pipeline.null_models`, 10,000 rewiring iterations). `small_worldness_rl_wu` divides the real mean clustering by the lattice's to give **CC**.

CC is only computed when there are more than `{{param:min_number_of_nodes_to_cal_net_met}}` active nodes.

## Things to watch for

- CC relies on a single lattice null model per recording and lag, so it varies a little between runs unless `{{param:random_seed}}` is set.
- In the BCT and much of the literature, "normalised clustering" means C divided by a **random** network's value. MEA-NAP's CC divides by a **lattice** value, so the numbers are not directly comparable to those.

## References

- Watts DJ, Strogatz SH (1998) Nature 393:440–442. doi:10.1038/30918
- Onnela JP et al. (2005) Physical Review E 71:065103. doi:10.1103/PhysRevE.71.065103
- Telesford QK et al. (2011) Brain Connectivity 1:367–375. doi:10.1089/brain.2011.0038
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
