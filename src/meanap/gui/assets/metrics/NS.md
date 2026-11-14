---
key: NS
name: Node strength
also: NSmean
level: node
family: network
image: NS.png
related: ND, MEW, edges, aN
---
Node strength is the sum of the weights of all a node's connections: it combines how many partners a node has with how tightly it is coupled to each.

## What it measures
Where node degree counts connections, strength adds up their weights. On MEA data each weight is a spike time tiling coefficient (STTC), so a node scores highly when its spikes reliably coincide with those of many other electrodes. Strength is the weighted counterpart of degree.

## Reading the values
- No units. The range is from just above 0 up to N − 1, where N is the number of nodes (`aN`), because each weight is at most 1.
- High strength: many strong connections, a node closely tied into network activity. Low strength: few or weak connections.
- Strength rises with network size and with density, like degree. Dividing strength by degree gives the node's mean edge weight (`MEW`), which separates "many links" from "strong links".
- **NSmean**: the average node strength over all nodes in the recording.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.strengths_und`, called from `meanap.pipeline.step4.compute_network_metrics`:
1. Take the thresholded, weighted adjacency matrix for each lag (`{{param:func_con_lag_val}}` ms), with negative and missing weights set to 0. Only edges that passed significance testing (`{{param:prob_thresh_tail}}` tail, `{{param:prob_thresh_rep_num}}` surrogates) have non-zero weight.
2. Keep nodes with at least one edge and a firing rate of at least `{{param:min_activity_level}}` spikes/s; skip the recording if fewer than `{{param:min_number_of_nodes_to_cal_net_met}}` nodes remain.
3. Sum each node's column of edge weights in this sub-network.
4. NSmean is the mean over nodes.

## Things to watch for
- Strength mixes count and weight, so two nodes with equal strength can have very different degrees.
- Weights are only as good as the connectivity measure: STTC depends on the lag used, so strength at a 10 ms lag and a 25 ms lag are not directly comparable.

## References
- Barrat A et al. (2004) PNAS 101:3747–3752. doi:10.1073/pnas.0400087101
- Rubinov M & Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
- Cutts CS & Eglen SJ (2014) Journal of Neuroscience 34:14288–14303. doi:10.1523/JNEUROSCI.2767-14.2014
