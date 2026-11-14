---
key: bursts
name: Single-electrode bursts
also: channelBurstRate, channelBurstDur, channelFracSpikesInBursts, channelWithinBurstFr, channelAveBurstRate, channelAveBurstDur, channelAveFracSpikesInBursts
level: node
family: activity
related: networkbursts, ISI, FR
---
Bursts are short runs of closely spaced spikes on one electrode. These metrics describe how often each electrode bursts, how long its bursts last, and how much of its firing happens inside them.

## What it measures

- **channelBurstRate**: bursts per minute.
- **channelBurstDur**: mean burst duration, in ms, from first to last spike.
- **channelFracSpikesInBursts**: fraction of the electrode's spikes that fall inside bursts (0 to 1).
- **channelWithinBurstFr**: mean firing rate inside bursts (spikes ÷ burst duration, Hz).
- **channelAveBurstRate** and **channelAveBurstDur** (per recording): the **median** of the electrode values, over electrodes that burst.
- **channelAveFracSpikesInBursts** (per recording): all spikes in bursts divided by all spikes on the array.

## Reading the values

Bursting usually increases as cultures mature. A high fraction of spikes in bursts with a low burst rate means rare but large bursts.

## How MEA-NAP calculates it

`single_channel_burst_detection` (`meanap.pipeline.burst_detection`) uses Bakkum's ISI_N method on each electrode separately:

- Only electrodes with at least `{{param:single_channel_burst_min_spike}}` spikes are tested.
- A burst is a run of at least N = `{{param:single_channel_burst_min_spike}}` spikes in which every spike belongs to some window of N consecutive spikes spanning no more than the ISI_N threshold.
- The threshold is `{{param:single_channel_isi_threshold}}` (seconds, or automatic). When automatic, `get_isin_threshold` places it at the valley between the burst and background peaks of that electrode's ISI_N histogram, capped at 100 ms. Where no valley can be found it falls back to a fixed value, usually 100 ms.
- Rate uses the full recording duration. Electrodes with no bursts are left blank.

## Things to watch for

- The automatic threshold is set per electrode, so electrodes are not judged by the same rule.
- Single-electrode bursts are not merged when they are close together, unlike network bursts.
- The burst-detection method setting is recorded but only Bakkum is implemented.

## References

- Bakkum DJ et al. (2014). Parameters for burst detection. Frontiers in Computational Neuroscience 7:193.
- Pasquale V, Martinoia S, Chiappalone M (2010). A self-adapting approach for the detection of bursts and network bursts in neuronal cultures. Journal of Computational Neuroscience 29:213–229.
- Sit TPH et al. (2024). Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
