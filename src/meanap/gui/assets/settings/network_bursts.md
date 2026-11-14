---
key: network_bursts
name: Network bursts
tab: Spike detection
labels: Network burst: min spikes; Network burst: min channels; Network burst: automatic ISIn threshold; Network burst: ISIn threshold; Network burst: merge bursts closer than
params: min_spike_network_burst, min_channel_network_burst, bakkum_network_burst_isi_n_threshold, bakkum_network_burst_merge_gap_ms
image: sd_network_bursts.png
related: bursts, active_electrodes, spike_method
---
A network burst is a moment when many electrodes fire together: the synchronised events typical of cultured networks. MEA-NAP finds them by pooling all electrodes' spikes into one train and looking for dense runs: **at least 10 spikes**, on **at least 3 electrodes**, with bursts **closer than 20 ms** joined into one.

## What it does
1. Every electrode's spikes are combined into a single train.
2. The ISIn method (as for single-channel bursts) marks runs where N = **min spikes** consecutive spikes fit within the **ISIn threshold**. With **automatic** on, the threshold comes from the histogram of the pooled train, capped at 100 ms.
3. Bursts less than **merge bursts closer than** apart are joined, because on a densely firing array one event often comes out as several fragments a few milliseconds apart.
4. A burst is kept only if spikes from at least **min channels** different electrodes fall inside it (picture: the local event on two electrodes is not counted).

## Choosing a value
- **Min spikes** (default 10): counted across the whole array, so on a large, busy array a higher value keeps background firing from forming "bursts".
- **Min channels** (default 3): raise it on large arrays so that only events spreading across a real share of the array count.
- **Automatic ISIn threshold** (default on), or a fixed **ISIn threshold** (default 0.1 s, used only when automatic is off).
- **Merge gap** (default 20 ms): set to 0 to report every fragment. A larger gap can join separate events.

## How MEA-NAP uses it
Step 2 reports the number and rate (per minute) of network bursts, their mean duration, the mean number of electrodes involved, the inter-spike intervals inside and outside them, the fraction of spikes they contain, and the variability (CV) of the intervals between them.

## Things to watch for
- Min channels counts any electrode with a spike inside the burst's span, including stray background spikes. On a busy array this is easily met, so min spikes and the threshold do most of the work.
- Every electrode's spikes are pooled, whether or not the electrode counts as active.
- Merging only joins bursts already found; it never adds time the detector called quiet.
- The spike and burst viewer shows the bursts on a recording, and how many fragments merging joined.

## References
Bakkum DJ, et al. (2014). Parameters for burst detection. *Front Comput Neurosci* 7:193.
