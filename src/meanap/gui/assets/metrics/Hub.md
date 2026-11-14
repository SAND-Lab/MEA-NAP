---
key: Hub
name: Hub nodes
also: Hub3, Hub4
level: node
family: network
related: ND, PC, BC, NC, Z, aN
---
Hub nodes are the network's most central nodes: those that rank in the top 10% on several different measures of importance at once. Hub3 and Hub4 give the fraction of nodes that qualify.

## What it measures
No single metric captures "importance". MEA-NAP scores each node on four: node degree (how many connections), participation coefficient (how widely connections spread across modules), betweenness centrality (how often it lies on shortest paths) and nodal efficiency (how close it is to every other node). A node that is in the top 10% for most of these is a hub.

## Reading the values
- Both are fractions of the recording's nodes, from 0 to 1.
- **Hub3**: the fraction of nodes in the top 10% on at least 3 of the 4 measures.
- **Hub4**: the fraction in the top 10% on all 4. Hub4 is never larger than Hub3.
- Because the top 10% is a fixed share, the maximum is roughly 0.1. A value near 0.1 means the same few nodes dominate every measure (a hub-centred network); near 0 means importance is spread among different nodes.
- In small networks the top 10% is only one or two nodes, so the values jump in large steps.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.hub_classification`, called from `meanap.pipeline.step4.compute_network_metrics`:
1. Use the thresholded, weighted sub-network of active nodes for each lag (`{{param:func_con_lag_val}}` ms), with N nodes.
2. Take node degree, the normalised participation coefficient, normalised betweenness centrality, and nodal efficiency (the inverse of a node's mean weighted shortest-path distance, lengths = 1/weight).
3. For each measure, mark the nodes whose values are among the top round(N/10) values; ties at the cut-off are all included.
4. Count how many of the four lists each node is in; Hub3 and Hub4 are the fractions with counts ≥ 3 and = 4.

## Things to watch for
- The participation coefficient depends on random module detection and null models, so Hub3/Hub4 can shift slightly between runs unless a random seed (`{{param:random_seed}}`) is set.
- Hub3/Hub4 need module detection, so they are missing when modules could not be computed.

## References
- Schroeter MS et al. (2015) Journal of Neuroscience 35:5459–5470
- van den Heuvel MP & Sporns O (2013) Trends in Cognitive Sciences 17:683–696. doi:10.1016/j.tics.2013.09.012
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
