---
key: aN
name: Active nodes (network size)
level: recording
family: network
related: Dens, edges, ND, FR
---
The number of electrodes (or units) that take part in the network: they fire often enough and keep at least one significant connection after thresholding.

## What it measures

Every other network metric is computed on a sub-network made only of these active nodes. Network size tells you how much of the array is contributing to coordinated activity, as opposed to being silent or firing independently of everything else.

## Reading the values

- A whole number from 0 up to the number of electrodes (or sorted units) in the recording.
- A higher value means more of the culture is both active and functionally coupled to the rest. A low value can mean a sparse or immature culture, poor electrode coverage, or activity too weak to survive thresholding.
- In developing cortical cultures the active network usually grows as firing and synchrony increase.
- Network size changes with the lag: a longer lag usually lets more pairs pass the significance test, so more nodes count as connected.

## How MEA-NAP calculates it

In `compute_network_metrics` (`meanap.pipeline.step4`), negative and missing weights in the thresholded adjacency matrix are set to zero. A node is then counted as active when both of these hold:

- its node strength (the sum of its edge weights) is not zero, so it has at least one edge that survived thresholding;
- its firing rate (spike count ÷ recording duration) is at least `{{param:min_activity_level}}` Hz.

Network metrics are only computed when there are at least `{{param:min_number_of_nodes_to_cal_net_met}}` active nodes. Small-worldness needs strictly more nodes than that.

## Things to watch for

- An electrode that fires a lot but has no significant edges does **not** count. Firing rate and network size answer different questions.
- Metrics such as density, clustering and path length depend on network size. When groups differ a lot in aN, compare the normalised metrics (CC, PL, SW, SWw) rather than the raw ones.
- Grounded electrodes listed in the spreadsheet are silenced before this step.

## References

- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
