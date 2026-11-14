---
key: Eglob
name: Global efficiency
level: recording
family: network
image: Eglob.png
related: PL, Eloc, Dens, SW
---
How efficiently, on average, any active node could pass activity to any other through the network's strongest routes.

## What it measures

Global efficiency averages the inverse of the shortest path between every pair of active nodes. Short routes along strong connections give high efficiency. It measures the same idea of network-wide integration as path length, but turned upside down, so pairs that cannot reach each other count as zero efficiency instead of being dropped.

## Reading the values

- A number from 0 to 1. Edges are STTC weights of at most 1, so every edge is at least 1 long, and efficiency cannot go above 1.
- 1 would mean every pair is directly joined by an edge of weight 1. Values near 0 mean sparse, weak or fragmented connectivity.
- Higher efficiency means activity at one site is more likely to be shared quickly across the culture. In developing cultures it tends to rise along with density and synchrony.
- Global efficiency is **not** normalised against a null model, so it goes up with density and with edge strength. Compare it only between networks of similar size and density, or alongside Dens.

## How MEA-NAP calculates it

`efficiency_wei_global` (`meanap.pipeline.network_metrics`), called from `compute_network_metrics` (`meanap.pipeline.step4`) on the weighted active-node network:

- each weight is turned into a length, 1/weight (`weight_conversion_lengths`);
- shortest weighted paths between all pairs are found with Dijkstra's algorithm (`distance_wei`);
- the inverse of each shortest path is summed over all ordered pairs and divided by n(n − 1), where n is the number of active nodes. Unreachable pairs add 0.

The network is the thresholded STTC network at each lag in `{{param:func_con_lag_val}}` ms.

## Things to watch for

- Global efficiency is not exactly 1 ÷ path length. Path length leaves unreachable pairs out, while efficiency counts them as zero, so the two can disagree for fragmented networks.
- Because the value scales with edge strength, cultures with higher overall STTC values will look more efficient even if the wiring pattern is the same.

## References

- Latora V, Marchiori M (2001) Physical Review Letters 87:198701. doi:10.1103/PhysRevLett.87.198701
- Rubinov M, Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
