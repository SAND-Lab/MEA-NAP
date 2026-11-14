---
key: nullmodels
name: Null models (lattice and random)
level: concept
family: network
related: CC, PL, SW, SWw, PC
---
Null models are artificial "control" networks built from each real network. They keep its size and the number of connections at each node but rearrange the wiring, so MEA-NAP can tell genuine structure from what size and density alone would produce.

## What it measures

Many network metrics change simply because a network has more nodes or edges. Comparing each network with rewired copies of itself removes much of that effect, so cultures and ages whose networks differ in size and density can be compared.

MEA-NAP uses two kinds:

- **Random (degree-preserving)**: edges are repeatedly swapped between pairs of nodes. Each node keeps its number of connections, but the pattern becomes random. Random networks have **short paths and low clustering**.
- **Lattice-like**: the same swaps, but a swap is only accepted if it moves connection weight towards "closer" pairs of nodes. This builds a more regular network with **high clustering and long paths**.

## Reading the values

Normalised metrics are ratios to these references:

- **CC** = real clustering ÷ lattice clustering (usually 0–1, where 1 means as clustered as a lattice);
- **PL** = real path length ÷ random path length (usually about 1 or a little above);
- **SW (σ)** uses the random model for both clustering and path length;
- **SWw (ω)** uses random for path length and lattice for clustering.

## How MEA-NAP calculates it

For each recording and lag, `compute_network_metrics` (`meanap.pipeline.step4`) builds, from the weighted active-node network (functions in `meanap.pipeline.null_models`):

- **one** random network with `randmio_und_v2` (5,000 rewiring iterations);
- **one** lattice-like network with `latmio_und_v2` (10,000 rewiring iterations), where "distance" is how different two nodes' connection profiles are, not electrode distance.

Edges carry their weights with them when swapped. The normalised participation coefficient uses a separate set of 100 networks from `null_model_und_sign`, which keep each node's degree and roughly its strength.

Null models are only built when there are more than `{{param:min_number_of_nodes_to_cal_net_met}}` active nodes.

## Things to watch for

- Each normalised value relies on a single random draw, so expect small run-to-run differences. Set `{{param:random_seed}}` for reproducible results.
- In very dense networks there is little room to rewire, so the null models look like the real network and normalised values drift towards 1 (σ) or 0 (ω).
- In tiny networks rewiring may stop early if no valid swap exists.

## References

- Maslov S, Sneppen K (2002) Science 296:910–913. doi:10.1126/science.1065103
- Sporns O, Zwi JD (2004) Neuroinformatics 2:145–162.
- Rubinov M, Sporns O (2010) NeuroImage 52:1059–1069. doi:10.1016/j.neuroimage.2009.10.003
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
