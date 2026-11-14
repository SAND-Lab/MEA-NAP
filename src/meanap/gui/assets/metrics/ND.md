---
key: ND
name: Node degree
also: NDmean, NDtop25
level: node
family: network
image: ND.png
related: NS, MEW, Dens, aN, Hub, edges
---
Node degree is the number of significant functional connections a node has: how many other electrodes (or cells) its activity is reliably coupled to.

## What it measures
Each node is an active electrode (or cell in CAT-NAP). Two nodes are connected when their correlated firing passes the significance test that builds the network. Degree simply counts those connections, ignoring how strong each one is. Highly connected nodes are in a position to influence, or be influenced by, much of the network.

## Reading the values
- Units are connections. The range is 1 to N − 1, where N is the number of nodes in the network (`aN`): nodes with no connections are left out of the network, so every included node has at least one.
- High degree: a well-connected node, a candidate hub. Low degree: a node coupled to only a few partners.
- Degree grows with network size and density, so compare cultures with similar numbers of active electrodes, or look at density (`Dens`) alongside it.
- **NDmean**: the average degree over all nodes in the recording.
- **NDtop25**: the average degree of the most connected quarter of nodes (those at or above the 75th percentile). It tracks the hubs rather than the typical node.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.find_node_deg_edge_weight`, called from `meanap.pipeline.step4.compute_network_metrics`:
1. Start from the thresholded adjacency matrix for each lag (`{{param:func_con_lag_val}}` ms). Edges were kept if their weight beat the `{{param:prob_thresh_tail}}` tail of `{{param:prob_thresh_rep_num}}` shuffled surrogates; negative and missing weights are set to 0.
2. Keep only nodes with at least one edge and a firing rate of at least `{{param:min_activity_level}}` spikes/s. If fewer than `{{param:min_number_of_nodes_to_cal_net_met}}` nodes remain, no metrics are computed.
3. Count, for each node, the other nodes with an edge weight above zero (the network is binarised for this count).
4. NDmean is the mean of these counts; NDtop25 is the mean of counts ≥ the 75th percentile (linear interpolation).

## Things to watch for
- Degree depends heavily on thresholding: a stricter tail gives fewer edges and lower degree.
- Degree ignores weight: a node with many weak connections can outrank one with a few strong ones. Look at node strength (`NS`) too.

## References
- Rubinov M & Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
