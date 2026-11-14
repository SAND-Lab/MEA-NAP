---
key: Dens
name: Network density
level: recording
family: network
image: Dens.png
related: aN, ND, edges, CC
---
The fraction of all possible connections between active nodes that actually exist after thresholding.

## What it measures

Density counts how many pairs of active nodes share a significant functional connection, out of every pair that could have one. It is a basic description of how interconnected the network is, and ignores how strong each connection is.

## Reading the values

- A proportion from 0 (no edges) to 1 (every active node connected to every other). Multiply by 100 for a percentage.
- High density means activity is widely shared across the culture, for example during strongly synchronised network bursts. Low density means coupling is restricted to a few pairs.
- In developing cortical cultures, density usually rises as synchronous bursting develops.
- Density depends on the lag: longer lags give more chance coincidences to beat the null model, so networks tend to be denser.

## How MEA-NAP calculates it

`density_und` (`meanap.pipeline.network_metrics`) works on the active-node sub-network built in `compute_network_metrics` (`meanap.pipeline.step4`). It counts the non-zero entries in the upper triangle of the thresholded adjacency matrix (each pair once), and divides by the number of possible pairs, n(n − 1)/2, where n is the number of active nodes. Edge weights are not used: any edge that survived probabilistic thresholding counts as 1.

The network comes from the STTC at each lag in `{{param:func_con_lag_val}}` ms, thresholded against `{{param:prob_thresh_rep_num}}` circular-shift surrogates.

## Things to watch for

- The denominator only includes active nodes, and a node needs at least one edge to be active. Silent or unconnected electrodes are left out, so density describes the connected network, not the whole array.
- Many other metrics (clustering, path length, efficiency, modularity) change with density. Check whether a group difference in those metrics is simply a difference in density.
- Small networks give coarse values: with 4 active nodes there are only 6 possible pairs.

## References

- Rubinov M, Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
