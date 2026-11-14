---
key: inclusion
name: Node and edge inclusion
tab: Connectivity
labels: Node and edge inclusion; Exclude edges below threshold; Min activity level (events/s)
params: exclude_edges_below_threshold, min_activity_level
related: prob_threshold, adjacency, sttc
---
These settings decide which electrodes (or cells) count as network nodes, and whether an edge that thresholding set to zero counts as missing or as an edge of weight 0.

## What it does

**Which nodes.** Step 4 keeps a node only if both of these hold:

1. Its activity rate over the whole recording is at least the minimum activity level (default 0.01 spikes/s, or events/s in CAT-NAP).
2. It has at least one edge that survived thresholding.

All other nodes are removed from the matrix before any metric is calculated, so the network size (aN) counts only the nodes that remain. In MEA-NAP mode the threshold is shared with the Spike detection tab, where it also sets which electrodes count as active. In CAT-NAP mode the field reads **Min activity level (events/s)** and applies to cells.

**Exclude edges below threshold** (on by default) treats a pair that thresholding set to 0 as having no edge. Turn it off and those pairs count as edges of weight 0. In the Python pipeline this changes:

- **MEW**, each node's mean edge weight. With the setting off, absent edges count as zeros and pull the mean down.
- The edge-weight histogram and mean in the connectivity figure for each lag.
- The edge cut-off in the circular node-cartography plot.
- MEW in the spatiotemporal-model networks.

Density, node degree and node strength stay the same either way. They count or sum non-zero entries, and adding zeros changes neither a count nor a sum.

## Choosing a value

- Raise the minimum activity level to keep near-silent electrodes out of the network. A node whose STTC rests on a handful of spikes has edges that mean little. Set it to 0 to keep every electrode that has an edge.
- Leave **Exclude edges below threshold** on. It is how MEA-NAP has always worked. Turn it off only to match an analysis that averaged over every pair.

## How MEA-NAP uses it

`compute_network_metrics` in step 4 takes the sub-network of included nodes first. Every metric, every null model and every network plot works on that sub-network.

## Things to watch for

- A recording with fewer than 3 nodes left (`min_number_of_nodes_to_cal_net_met`) gets no network metrics, only aN.
- The tooltip on Exclude edges below threshold says it changes density, mean node degree and mean node strength. In the current code it does not.
