---
key: NC
name: Node cartography roles
also: NCpn1, NCpn2, NCpn3, NCpn4, NCpn5, NCpn6, NCpn1count, NCpn2count, NCpn3count, NCpn4count, NCpn5count, NCpn6count
level: recording
family: network
image: NodeCartographyDiagram.jpg
related: PC, Z, nMod, Q, Hub
---
Each active node gets one of six roles, based on how strongly it connects within its own module (Z) and how evenly it spreads its connections across modules (PC). The NCpn values give the share of nodes in each role.

## What it measures

Node cartography sorts nodes into roles on a map with two axes:

- **Z**, the within-module degree z-score: how strongly a node is connected inside its own module, compared with other members of that module. High-Z nodes are **hubs**.
- **PC**, the participation coefficient: how evenly a node's connections are spread across modules. 0 means all connections stay in its own module, and values near 1 mean they are spread evenly.

The six roles are:

1. **Peripheral node**: non-hub with most links inside its module.
2. **Non-hub connector**: non-hub with many links to other modules.
3. **Non-hub kinless node**: non-hub with links spread across all modules.
4. **Provincial hub**: hub with most links inside its module.
5. **Connector hub**: hub with many links to other modules.
6. **Kinless hub**: hub with links spread across all modules.

**NCpn1–NCpn6** give the fraction of active nodes in roles 1–6 (from 0 to 1, and they add up to 1). **NCpn1count–NCpn6count** give the number of nodes.

## Reading the values

Mostly peripheral nodes and provincial hubs means segregated modules. More connector or kinless roles means modules are becoming integrated. Roles depend on the module partition, so read them with nMod and Q.

## How MEA-NAP calculates it

In `compute_network_metrics` (`meanap.pipeline.step4`), modules come from consensus Louvain clustering. Z comes from `module_degree_zscore` (weighted, within module), and PC comes from `participation_coef_norm` (normalised against 100 randomised networks). `classify_node_cartography` (`meanap.pipeline.network_metrics`) then assigns roles. A node is a hub if Z ≥ the hub boundary. Non-hubs are split at two PC boundaries (peripheral / connector / kinless), and hubs at two others.

The fixed boundaries are Z = `{{param:hub_boundary_wm_d_deg}}`, non-hub PC = `{{param:peri_part_coef}}` and `{{param:non_hub_connector_part_coef}}`, and hub PC = `{{param:pro_hub_part_coef}}` and `{{param:connector_hub_part_coef}}`.

When `{{param:auto_set_cartography_boundaries}}` is on, `_apply_cartography_boundaries` re-derives **all five** boundaries from the data and reclassifies every node. `trial_landscape_density` pools PC and Z from every recording in the run, then uses exact one-dimensional k-means to split Z into two groups (the hub boundary), and the PC of hubs and of non-hubs into three groups each. If there are too few values, the fixed boundaries are kept. With `{{param:auto_set_cartography_boundaries_per_lag}}` on, each lag gets its own boundaries. Otherwise, boundaries from lag `{{param:cartography_lag_val}}` (the first value) are applied to all lags.

## Things to watch for

- Data-driven boundaries depend on **which recordings are in the run**. Adding or removing recordings can shift every recording's roles.
- The data-driven hub boundary is often much lower than the classic 2.5, giving more hubs than in the original scheme.
- Guimerà & Amaral defined seven roles. MEA-NAP merges ultra-peripheral and peripheral nodes into one role, giving six.

## References

- Guimerà R, Nunes Amaral LA (2005) Nature 433:895–900. doi:10.1038/nature03288
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
