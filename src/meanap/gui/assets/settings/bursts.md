---
key: bursts
name: Single-channel bursts
tab: Spike detection
labels: Burst detection; Single-channel burst: min spikes; Single-channel burst: automatic ISI threshold; Single-channel burst: ISI threshold
params: single_channel_burst_min_spike, single_channel_isi_threshold
image: sd_bursts.png
related: network_bursts, active_electrodes, spike_method
---
A burst is a run of spikes much closer together than an electrode's usual firing. MEA-NAP finds them on each electrode with the ISIn method of Bakkum et al.: by default, **at least 5 spikes** within a window set **automatically** per electrode.

## What it does
For every group of N consecutive spikes (N = **min spikes**), the detector measures how long they span: the ISIn. Inside a burst this span is short; between bursts it is long. Spikes in any group whose span is no longer than the **ISI threshold** belong to a burst, and a burst must contain at least N spikes.

With **automatic ISI threshold** on, MEA-NAP chooses the threshold for each electrode from its own spikes. It draws the histogram of ISIn on a log scale (picture, bottom), which usually has two peaks: inside bursts and between them. The threshold is the lowest point between the first two peaks, capped at 100 ms. If there is only one peak, the threshold is 100 ms (or 0, meaning no bursts, when every gap between spikes is shorter than 100 ms). Electrodes with fewer than about 10 distinct gaps get 100 ms.

## Choosing a value
- **Min spikes** (default 5): larger values only count longer, denser bursts. 3–5 is common for single electrodes.
- **Automatic** (default on): adapts to each electrode's own firing.
- **ISI threshold** (used only when Automatic is off; default 0.1 s): one value for every electrode. Use it to give every recording the same definition of a burst.

## How MEA-NAP uses it
Step 2 runs the detector on every electrode with at least min spikes spikes. For each bursting electrode it reports burst rate, burst duration, firing rate within bursts, inter-spike intervals inside and outside bursts, and the fraction of spikes in bursts, plus their averages across the array.

## Things to watch for
- Automatic thresholds differ between electrodes and recordings, so a change in burst rate can partly reflect a change in threshold. Fix the threshold if this matters for your comparison.
- The spike check viewer (Open spike and burst viewer…) lets you try these values on a recording before a run.

## References
Bakkum DJ, et al. (2014). Parameters for burst detection. *Front Comput Neurosci* 7:193.
Pasquale V, Martinoia S, Chiappalone M (2010). A self-adapting approach for the detection of bursts and network bursts in neuronal cultures. *J Comput Neurosci* 29:213–229.
