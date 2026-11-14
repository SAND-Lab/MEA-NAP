---
key: PL
name: Characteristic path length
also: PL_raw
level: recording
family: network
image: PL.png
related: Eglob, CC, SW, SWw, nullmodels
---
The typical shortest route between two active nodes, where strong connections count as short, compared with a randomised version of the same network.

## What it measures

Path length describes how easily activity could spread across the whole network. A short path length means any node can reach any other through a few strong connections, which supports network-wide integration.

MEA-NAP reports two versions:

- **PL**: the real path length divided by that of a degree-preserving random null model. This is the value used in small-world analysis.
- **PL_raw**: the path length of the real network, with no normalisation.

## Reading the values

- PL_raw has no units. Each edge's length is 1 ÷ its STTC weight, so a strong edge (weight near 1) has length near 1 and weak edges are long. It is not a count of steps.
- PL is usually close to 1 or a little above it, because random networks have short paths. A value of about 1 means the network integrates about as efficiently as a random one. Clearly higher values mean longer routes, as in a more lattice-like or fragmented network.
- PL_raw falls as density and edge strength increase, so compare raw values only between similar networks.

## How MEA-NAP calculates it

In `compute_network_metrics` (`meanap.pipeline.step4`), on the weighted active-node network:

- `weight_conversion_lengths` turns weights into lengths (1/weight), `distance_wei` finds every shortest path (Dijkstra), and `charpath` (all in `meanap.pipeline.network_metrics`) averages them. Pairs of nodes that cannot reach each other are left out. The result is **PL_raw**.
- A random null model is built with `randmio_und_v2` (`meanap.pipeline.null_models`, 5,000 rewiring iterations), and `small_worldness_rl_wu` divides the real path length by the random network's to give **PL**.

PL is only computed when there are more than `{{param:min_number_of_nodes_to_cal_net_met}}` active nodes.

## Things to watch for

- Unreachable pairs are excluded rather than counted as infinitely far. A network split into separate pieces can still have a short path length. Global efficiency handles this better.
- PL relies on a single random null model per recording and lag, so it varies slightly between runs unless `{{param:random_seed}}` is set.

## References

- Watts DJ, Strogatz SH (1998) Nature 393:440–442. doi:10.1038/30918
- Rubinov M, Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
