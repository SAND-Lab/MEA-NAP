---
key: SWw
name: Small-world coefficient ω
level: recording
family: network
image: SW.png
related: SW, CC, PL, nullmodels
---
Where the network sits between a regular lattice and a random network. Values near 0 are small-world. This is method 2, ω.

## What it measures

ω compares the network's path length with a random network's, and its clustering with a lattice's:

ω = (L_random ÷ L) − (C ÷ C_lattice)

A small-world network has paths almost as short as a random network (first term close to 1) and clustering almost as high as a lattice (second term close to 1), so ω comes out close to 0. Unlike σ, it says which way a network departs from small-world.

## Reading the values

- No units, usually between −1 and 1.
- **Near 0**: small-world.
- **Towards +1**: random-like, with short paths but little clustering.
- **Towards −1**: lattice-like, highly clustered but with long paths.
- Because each term is compared with its own reference network, ω depends less on network size than σ does. That makes it better for comparing cultures with different numbers of active nodes.

## How MEA-NAP calculates it

In `compute_network_metrics` (`meanap.pipeline.step4`), on the weighted active-node network, two null models are built:

- a random one with `randmio_und_v2` (5,000 rewiring iterations);
- a lattice-like one with `latmio_und_v2` (10,000 rewiring iterations), where the "distance" that guides it is how different each pair of nodes' connection profiles are, not how far apart the electrodes are. Both functions are in `meanap.pipeline.null_models`.

`small_worldness_rl_wu` (`meanap.pipeline.network_metrics`) then computes PL_random ÷ PL − CC, where CC is the lattice-normalised clustering coefficient (C ÷ C_lattice). Clustering is weighted (`clustering_coef_wu`) and path length uses lengths of 1/weight.

ω is only computed when there are more than `{{param:min_number_of_nodes_to_cal_net_met}}` active nodes.

## Things to watch for

- Each recording and lag uses a single random and a single lattice null model, so ω varies a little between runs unless `{{param:random_seed}}` is set.
- Values can fall slightly outside −1 to 1, because the null models only approximate a true lattice or random network.
- In very dense networks both null models end up close to the original, which squeezes ω towards 0.

## References

- Telesford QK, Joyce KE, Hayasaka S, Burdette JH, Laurienti PJ (2011) Brain Connectivity 1:367–375. doi:10.1089/brain.2011.0038
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
