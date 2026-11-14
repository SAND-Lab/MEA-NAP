---
key: adjacency
name: Adjacency matrix type
tab: Connectivity
labels: Adjacency matrix
params: adj_m_type
related: prob_threshold, inclusion
---
Weighted networks keep each edge's STTC as its strength. Binary networks treat every edge that survives thresholding as equal. **In the Python pipeline this switch has no effect: networks are always weighted.**

## What it does

In MATLAB MEA-NAP, choosing **Binary** turns the thresholded matrix into 0s and 1s before the network metrics are calculated, so a weak edge and a strong edge count the same. In the Python pipeline the choice (`adj_m_type`, default weighted) is saved with the run's settings and shown in the settings summary, but no step reads it. Step 4 always works on the weighted, thresholded STTC matrix.

## Choosing a value

Leave it on **Weighted**, which is the only behaviour the Python pipeline has. Weighted metrics keep the information about connection strength. Binarising throws that away, and makes every metric depend even more on how many edges survived thresholding.

For a fair binary comparison of topology, use the **Density sweep** on the Stats & ML tab instead. It thresholds every recording to the same proportion of edges and binarises the result, so differences in density do not drive the comparison.

## How MEA-NAP uses it

It does not. The weighted metrics (node strength, mean edge weight, weighted clustering, path length and efficiency, modularity on the weighted graph) are computed from STTC weights whatever this switch says. Node degree and density count edges, so they are binary measures already.

## Things to watch for

- A run made with **Binary** selected gives exactly the same numbers as one made with **Weighted**. Its saved settings still say "binary", which can mislead someone reading them later.
- A MATLAB run made with Binary is not comparable with a Python run of the same data. The Python run is weighted whatever the setting says.
