---
key: Z
name: Within-module degree z-score
also: percentZscoreGreaterThanZero, percentZscoreLessThanZero
level: node
family: network
image: WMZ.png
related: PC, NC, nMod, Q, NS
---
The within-module degree z-score says how strongly a node is connected to the rest of its own module, compared with the other members of that module.

## What it measures
After the network is split into modules, each node's connection strength to its own module is compared with the module average. A node far above average is a local hub that holds its module together; one below average sits on the module's edge.

## Reading the values
- Units are standard deviations from the module mean; values usually fall between about −3 and +3.
- Positive: more strongly connected within the module than its typical member. Negative: less. 0: average (also given to nodes in single-node modules or in modules where every node is equal).
- Because it is relative to the module, z does not grow with network size the way degree does.
- **percentZscoreGreaterThanZero**: percentage of nodes (0–100) with z above 0.
- **percentZscoreLessThanZero**: percentage of nodes with z below 0. The two need not add to 100, because nodes with exactly 0 count in neither.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.module_degree_zscore`, called from `meanap.pipeline.step4.compute_network_metrics`:
1. Use the thresholded, weighted sub-network of active nodes for each lag (`{{param:func_con_lag_val}}` ms).
2. Find modules by consensus clustering of repeated Louvain runs (50 repetitions, threshold 0.4).
3. For each node, sum its edge weights to nodes in its own module (weighted within-module strength).
4. Subtract the module's mean and divide by the module's standard deviation.

## Things to watch for
- Small modules give unstable z-scores: with two or three members, one strong edge decides everything.
- Module assignment is random, so z can vary slightly between runs unless a random seed (`{{param:random_seed}}`) is set.
- In node cartography, nodes above the hub boundary (`{{param:hub_boundary_wm_d_deg}}`, or a boundary set from the data when `{{param:auto_set_cartography_boundaries}}` is on) count as hubs.

## References
- Guimerà R & Amaral LAN (2005) Nature 433:895–900. doi:10.1038/nature03288
- Rubinov M & Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
