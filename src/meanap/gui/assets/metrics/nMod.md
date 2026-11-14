---
key: nMod
name: Number of modules
level: recording
family: network
image: nMod.png
related: Q, PC, Z, NC
---
How many communities (modules) the network splits into: groups of nodes that are more strongly connected to each other than to the rest of the network.

## What it measures

Modules are sub-networks whose nodes mostly interact among themselves. In a culture they can reflect spatially or functionally distinct assemblies that fire together. The module assignment also feeds the participation coefficient, the within-module z-score and node cartography.

## Reading the values

- A whole number from 1 (no community structure: one big module) up to the number of active nodes (every node on its own).
- More modules means activity is broken up into more separate assemblies. Fewer modules means more of the network acts as one unit, as during strong network-wide bursts.
- The count depends on network size and density. Larger networks can support more modules. Very dense, uniformly coupled networks tend to collapse into one or two.
- Every active node has at least one edge, but a small fragment cut off from the rest (even a single connected pair) counts as a module of its own, so sparse, fragmented networks can show inflated counts.

## How MEA-NAP calculates it

`mod_consensus_cluster_iterate` (`meanap.pipeline.modularity`), called from `compute_network_metrics` (`meanap.pipeline.step4`) on the weighted active-node network:

1. Run the Louvain algorithm (`community_louvain`, `meanap.pipeline.louvain`, resolution γ = 1) 50 times. Louvain is randomised, so the runs can disagree.
2. Build a consensus matrix: for each pair of nodes, the fraction of runs in which they ended up in the same module. Set entries below 0.4 to zero.
3. Run Louvain 50 times on the consensus matrix, rebuild and threshold it, and repeat until every run agrees, so the matrix contains only 0s and 1s (capped at 50 rounds).
4. nMod is the number of modules in the final agreed partition.

## Things to watch for

- Louvain is randomised, so nMod can differ by one or two between runs on borderline networks. Set `{{param:random_seed}}` for reproducible results.
- The 50-run and 0.4 settings are fixed in the code and cannot be changed in the GUI.
- nMod says nothing about how strong the community structure is. Read it together with Q.

## References

- Blondel VD et al. (2008) Journal of Statistical Mechanics P10008. doi:10.1088/1742-5468/2008/10/P10008
- Lancichinetti A, Fortunato S (2012) Scientific Reports 2:336. doi:10.1038/srep00336
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
