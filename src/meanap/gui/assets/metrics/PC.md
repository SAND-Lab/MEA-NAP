---
key: PC
name: Participation coefficient
also: PCmean, PCmeanTop10, PCmeanBottom10
level: node
family: network
image: PC.png
related: Z, NC, nMod, Q, Hub
---
The participation coefficient describes how evenly a node's connections are spread across the network's modules: near 0 if they all stay in its own module, higher if they reach many modules.

## What it measures
MEA-NAP first splits the network into modules (groups of nodes more strongly connected to each other than to the rest). A node whose connections all fall in one module is a local, "provincial" node; one whose connections spread over several modules integrates them. MEA-NAP reports a normalised version that discounts the spread you would expect from module sizes alone.

## Reading the values
- No units, range 0 to 1.
- Low: connections confined to one module. High: connections spread across modules (a connector node).
- With only one module every node scores low; more modules allow higher values.
- **PCmean**: the mean PC over all nodes in the recording.
- **PCmeanTop10**: mean PC of the nodes at or above the 90th percentile, the strongest connectors.
- **PCmeanBottom10**: mean PC of the nodes at or below the 10th percentile, the most module-bound nodes.

## How MEA-NAP calculates it
`meanap.pipeline.network_metrics.participation_coef_norm`, called from `meanap.pipeline.step4.compute_network_metrics`:
1. Use the thresholded, weighted sub-network of active nodes for each lag (`{{param:func_con_lag_val}}` ms).
2. Find modules by consensus clustering of repeated Louvain runs (50 repetitions, consensus threshold 0.4).
3. Build 100 randomised networks that keep each node's degree and roughly its strength.
4. For each node, compare the fraction of its strength going to each module in the real network with that in each randomised network. PC is 1 minus the median of these differences (root of half the summed squared differences).
5. The raw, unnormalised PC (1 − Σ(strength to module ÷ total strength)²) is also saved as `PC_raw`.

## Things to watch for
- Modules and randomisations are random, so PC can differ slightly between runs unless a random seed (`{{param:random_seed}}`) is set.
- PC is half of node cartography: with the within-module z-score (`Z`) it assigns node roles.

## References
- Guimerà R & Amaral LAN (2005) Nature 433:895–900. doi:10.1038/nature03288
- Pedersen M et al. (2020) Network Neuroscience 4:416–431. doi:10.1162/netn_a_00127
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
