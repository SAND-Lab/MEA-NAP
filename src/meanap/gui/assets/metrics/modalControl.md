---
key: modalControl
name: Modal controllability
also: modalControlMean, modalControlPrctLessThanThreshold
level: node
family: network
related: aveControl, ND, NS, BC
---
Modal controllability estimates how well input at a node could push the network into unusual, hard-to-reach activity states.

## What it measures
This comes from network control theory. The network is treated as a simple linear system in which activity spreads along the connections. Some patterns of network activity fade quickly and are hard to drive; modal controllability scores how much a node takes part in those patterns. In brain networks, weakly connected or peripheral nodes often score highest, which is the opposite of average controllability.

## Reading the values
- No units, range 0 to 1.
- Close to 1: the node can reach hard-to-drive states (typically a weakly connected node). Lower: the node mainly takes part in the network's dominant, slowly fading patterns, typical of strongly connected nodes.
- It usually falls as node strength rises, so it often mirrors average controllability.
- **modalControlMean**: the mean over all included nodes in the recording.
- **modalControlPrctLessThanThreshold**: the fraction of included nodes with modal controllability below 0.975. Despite the name it is a fraction from 0 to 1, not a percentage. A higher value means more nodes are well connected into the dominant activity patterns.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.modal_controllability`, a port of the Bassett lab's `modal_control.m`, called from `meanap.pipeline.step4.compute_network_metrics`:
1. Take the full weighted adjacency matrix for each lag (`{{param:func_con_lag_val}}` ms), with negative and missing weights set to 0. All electrodes are used, not only active ones.
2. Divide the matrix by 1 + its largest singular value.
3. Decompose it into eigenvalues λ and eigenvectors u. For node i, modal controllability is Σ (1 − λⱼ²) uᵢⱼ² over all modes j.
4. Keep the values for nodes that pass the activity and connection filter (firing rate ≥ `{{param:min_activity_level}}` spikes/s, at least one edge), then take the mean and the fraction below 0.975.

## Things to watch for
- The 0.975 cut-off is fixed in the code, not a run setting.
- The linear model is a strong simplification; treat the value as a structural index, not a prediction of what stimulating a node would do.

## References
- Gu S et al. (2015) Nature Communications 6:8414. doi:10.1038/ncomms9414
- Pasqualetti F, Zampieri S & Bullo F (2014) IEEE Transactions on Control of Network Systems 1:40–52
