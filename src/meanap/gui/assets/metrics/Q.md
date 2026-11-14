---
key: Q
name: Modularity score
level: recording
family: network
image: MS.png
related: nMod, PC, Z, NC
---
How cleanly the network divides into modules: how much more connection weight falls inside modules than you would expect by chance.

## What it measures

The modularity score Q compares the connection weight inside each module with what would be expected if the same node strengths were wired up at random. Strong community structure, with dense links within groups and sparse links between them, gives a high Q.

## Reading the values

- No units. Q can range from about −0.5 to 1. Values at or below 0 mean no community structure.
- In network studies generally, values above about 0.3 are often read as clear community structure.
- High Q suggests segregated assemblies that fire largely independently. Low Q suggests the culture behaves more as one integrated network, for example when network bursts recruit most electrodes together.
- Q depends on network size and density. Sparse networks can reach high Q fairly easily, while dense, uniformly coupled networks give low Q.

## How MEA-NAP calculates it

Q comes out of `mod_consensus_cluster_iterate` (`meanap.pipeline.modularity`), run from `compute_network_metrics` (`meanap.pipeline.step4`) on the weighted active-node network:

1. Louvain (`community_louvain`, `meanap.pipeline.louvain`, resolution γ = 1) is run 50 times on the network.
2. The results are combined into a consensus matrix (how often each pair of nodes shares a module), entries below 0.4 are set to zero, and Louvain is re-run on it, 50 times per round, until every run agrees (at most 50 rounds).
3. The Q that is saved is the score Louvain reports for the first partition of that final round.

## Things to watch for

- The saved Q is scored on the final **consensus matrix**, not re-scored on the original STTC network. Because the consensus matrix is close to block-diagonal by construction, Q tends to be higher than the original network's own modularity. Use it to compare recordings within MEA-NAP, not to compare with Q values from other software.
- Louvain is randomised. Set `{{param:random_seed}}` for reproducible results.
- Read Q together with nMod. One large module plus a few small fragments cut off from it can still give a moderate Q.

## References

- Newman MEJ (2006) PNAS 103:8577–8582. doi:10.1073/pnas.0601602103
- Blondel VD et al. (2008) Journal of Statistical Mechanics P10008. doi:10.1088/1742-5468/2008/10/P10008
- Lancichinetti A, Fortunato S (2012) Scientific Reports 2:336. doi:10.1038/srep00336
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
