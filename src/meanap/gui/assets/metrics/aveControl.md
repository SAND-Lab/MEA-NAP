---
key: aveControl
name: Average controllability
also: aveControlMean, aveControlTop25
level: node
family: network
related: modalControl, NS, ND, Hub
---
Average controllability estimates how easily input delivered at a node could push the whole network into many different, easily reached activity states.

## What it measures
This comes from network control theory. The network is treated as a simple linear system in which activity spreads along the connections. If you could "stimulate" one node, how much total change could that cause across the network? Nodes with high average controllability are well placed to steer network activity broadly, usually because they are strongly and widely connected.

## Reading the values
- No units; the minimum is 1 and there is no fixed maximum.
- High: input here spreads widely and efficiently. Close to 1: input here mostly stays local.
- It is usually strongly correlated with node strength and degree; a large difference from them is the interesting case.
- **aveControlMean**: the mean over all included nodes in the recording.
- **aveControlTop25**: the mean of the nodes at or above the 75th percentile, the most influential quarter.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.average_controllability`, a port of the Bassett lab's `ave_control.m`, called from `meanap.pipeline.step4.compute_network_metrics`:
1. Take the full weighted adjacency matrix for each lag (`{{param:func_con_lag_val}}` ms), with negative and missing weights set to 0. This uses all electrodes, not only active ones.
2. Divide the matrix by 1 + its largest singular value, which makes the system stable.
3. Decompose it into eigenvalues λ and eigenvectors u. For node i, average controllability is Σ uᵢⱼ² ÷ (1 − λⱼ²) over all modes j (the trace of the controllability Gramian).
4. Keep the values for nodes that pass the activity and connection filter (firing rate ≥ `{{param:min_activity_level}}` spikes/s, at least one edge), then compute the mean and top 25%.

## Things to watch for
- The linear model is a strong simplification of real neuronal dynamics; read it as a structural index of influence, not a prediction of stimulation outcomes.
- Because it is computed on the full matrix, values are not affected by which nodes are excluded later.

## References
- Gu S et al. (2015) Nature Communications 6:8414. doi:10.1038/ncomms9414
- Pasqualetti F, Zampieri S & Bullo F (2014) IEEE Transactions on Control of Network Systems 1:40–52
