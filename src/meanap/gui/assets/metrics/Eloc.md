---
key: Eloc
name: Local efficiency
also: ElocMean
level: node
family: network
image: Eloc.png
related: CC, Eglob, PL, ND
---
Local efficiency measures how well a node's neighbours are connected to each other: how easily information could still flow around the node's neighbourhood without it.

## What it measures
Take the nodes directly connected to a node. If they are also strongly connected to each other, the neighbourhood is tightly knit and efficient for local processing. Local efficiency is closely related to the clustering coefficient, but it also credits indirect routes between neighbours, not just direct links.

## Reading the values
- No units, range 0 to 1.
- High: the node sits in a dense, strongly interconnected cluster. Low: its neighbours are not connected to each other, so the node may be a bridge between otherwise separate groups.
- Values tend to rise with network density, since denser networks give neighbours more chances to connect.
- **ElocMean**: the average local efficiency over all nodes in the recording, a measure of how much local, clustered processing the network supports.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.efficiency_wei_local`, called from `meanap.pipeline.step4.compute_network_metrics`:
1. Use the thresholded, weighted sub-network of active nodes for each lag (`{{param:func_con_lag_val}}` ms): nodes with at least one edge and a firing rate of at least `{{param:min_activity_level}}` spikes/s.
2. Divide all weights by the largest weight in the network, so they run from 0 to 1.
3. For each node, find the weighted shortest paths among its neighbours (lengths are 1/weight) and average their inverse, weighting each pair by the node's own (cube-rooted) connections to them. This is the modified weighted local efficiency of the Brain Connectivity Toolbox (`efficiency_wei` with option 2).
4. ElocMean is the mean over nodes.

## Things to watch for
- A node with fewer than two neighbours has local efficiency 0.
- Rescaling by the largest weight means values depend on the single strongest edge in the recording.

## References
- Latora V & Marchiori M (2001) Physical Review Letters 87:198701. doi:10.1103/PhysRevLett.87.198701
- Rubinov M & Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
- Wang Y et al. (2017) Neural Computation 29:313–331
