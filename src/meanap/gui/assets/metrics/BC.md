---
key: BC
name: Betweenness centrality
level: node
family: network
image: BC.png
related: Hub, ND, PC, PL, Eglob
---
Betweenness centrality is the share of the network's shortest paths that pass through a node: how much of a "bridge" it is between other nodes.

## What it measures
Picture signals travelling between every pair of nodes along the shortest, strongest route. A node with high betweenness sits on many of these routes, so it links parts of the network that are otherwise poorly connected. Removing such a node would lengthen many paths.

## Reading the values
- No units, range 0 to 1 after normalisation.
- 0: the node is never on another pair's shortest path (often a peripheral node, or one inside a tightly knit cluster). Higher values: a bridge or bottleneck.
- Most nodes in a culture usually have values near 0, with a few clear outliers; the distribution is very skewed.
- Normalising by network size makes values more comparable between recordings, but they still depend on how modular and how dense the network is.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.betweenness_wei` (Brandes' algorithm), called from `meanap.pipeline.step4.compute_network_metrics`:
1. Take the thresholded, weighted sub-network of active nodes for each lag (`{{param:func_con_lag_val}}` ms): nodes with at least one edge and a firing rate of at least `{{param:min_activity_level}}` spikes/s.
2. Turn weights into lengths with 1 / (weight + 0.01), so strong connections are short.
3. Find the shortest weighted paths between all pairs and count how many go through each node.
4. Divide by (N − 1)(N − 2), where N is the number of nodes.

## Things to watch for
- The weighted version is sensitive to small weight differences: a slightly stronger route can capture all paths.
- Because of the + 0.01 term, node pairs with no edge get a very long (length 100) link rather than none, so they still count; it is almost never used as a shortcut.
- High betweenness is one of the four criteria for hub nodes (`Hub3`, `Hub4`).

## References
- Freeman LC (1977) Sociometry 40:35–41. doi:10.2307/3033543
- Brandes U (2001) Journal of Mathematical Sociology 25:163–177. doi:10.1080/0022250X.2001.9990249
- Rubinov M & Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
