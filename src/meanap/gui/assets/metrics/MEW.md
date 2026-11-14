---
key: MEW
name: Mean edge weight
also: sigEdgesMean, sigEdgesTop10
level: node
family: network
image: EW.png
related: NS, ND, edges, Dens
---
Mean edge weight is the average strength of a node's connections: how tightly, on average, its activity is coupled to the partners it is connected to.

## What it measures
Each edge weight is the strength of functional connectivity between two nodes; on MEA data this is the spike time tiling coefficient (STTC), which is 1 when spikes always coincide within the lag window. Mean edge weight averages a node's weights, separating "strong links" from "many links" (node degree).

## Reading the values
- No units, range 0 to 1.
- High: the node's connections are strong and reliable. Low: its connections only just passed significance.
- Unlike degree and strength, the mean weight does not automatically grow with network size.
- **sigEdgesMean**: the mean weight of every significant edge in the recording, a recording-level summary of connection strength.
- **sigEdgesTop10**: the mean weight of the strongest 10% of significant edges (at or above the 90th percentile).

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.find_node_deg_edge_weight` for MEW, and `meanap.pipeline.step4.compute_network_metrics` for the summaries:
1. Take the thresholded adjacency matrix for each lag (`{{param:func_con_lag_val}}` ms); edges that did not beat the `{{param:prob_thresh_tail}}` tail of `{{param:prob_thresh_rep_num}}` surrogates are already 0. Negative and missing weights are set to 0.
2. Keep nodes with at least one edge and a firing rate of at least `{{param:min_activity_level}}` spikes/s (at least `{{param:min_number_of_nodes_to_cal_net_met}}` nodes needed).
3. MEW: average each node's weights to the other nodes. With `{{param:exclude_edges_below_threshold}}` on, only its non-zero (significant) edges are averaged; with it off, absent connections count as zeros and pull the mean down.
4. sigEdgesMean and sigEdgesTop10 take all non-zero entries of the sub-network matrix and average them, or those ≥ the 90th percentile.

## Things to watch for
- MEW is an average, so a node with a single strong edge can score higher than a hub with many moderate ones.
- STTC depends on the lag; compare weights only within one lag.

## References
- Cutts CS & Eglen SJ (2014) Journal of Neuroscience 34:14288–14303. doi:10.1523/JNEUROSCI.2767-14.2014
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
