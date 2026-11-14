---
key: networkbursts
name: Network bursts
also: NBurstRate, numNbursts, meanNumChansInvolvedInNbursts, meanNBstLengthS, meanISIWithinNbursts_ms, meanISIoutsideNbursts_ms, CVofINBI, fracInNburst
level: recording
family: activity
related: bursts, ISI, FR, Dens, ND
---
A network burst is a brief period when many electrodes fire together in a dense volley. These recording-level metrics describe how often network bursts happen, how large and long they are, and how regular they are.

## What it measures

- **NBurstRate**: network bursts per minute. **numNbursts** is the count.
- **meanNumChansInvolvedInNbursts**: mean number of electrodes that spike during a burst.
- **meanNBstLengthS**: mean burst length, in seconds.
- **meanISIWithinNbursts_ms** / **meanISIoutsideNbursts_ms**: mean interval between consecutive spikes of the whole array, inside and outside bursts (ms).
- **CVofINBI**: coefficient of variation of the gaps between bursts. 0 is perfectly regular; around 1 or more is irregular.
- **fracInNburst**: fraction of the array's spikes that fall inside network bursts (0 to 1).

## Reading the values

Network bursting typically emerges and strengthens as cultures mature. More electrodes per burst and a higher fracInNburst mean more of the activity is synchronised across the array.

## How MEA-NAP calculates it

`burst_detect_network` (`meanap.pipeline.burst_detection`), called by `firing_rates_bursts` (`meanap.pipeline.firing_rates`):

1. Spikes from all electrodes (active or not, grounded ones removed) are pooled into one train. Simultaneous spikes count once.
2. Bakkum's ISI_N method finds runs of at least `{{param:min_spike_network_burst}}` spikes that are closely spaced. The threshold is `{{param:bakkum_network_burst_isi_n_threshold}}`. When automatic, it is the valley of the pooled ISI_N histogram, capped at 100 ms.
3. Bursts less than `{{param:bakkum_network_burst_merge_gap_ms}}` ms apart are merged into one (0 turns merging off). This stops one event being counted as many fragments.
4. Bursts involving fewer than `{{param:min_channel_network_burst}}` electrodes are dropped.

Length is from the first to the last spike of a burst. CVofINBI is the standard deviation of the gaps divided by their mean.

## Things to watch for

- With no network bursts, NBurstRate is 0 and the other metrics are blank. CVofINBI needs at least two bursts.
- The merge gap changes burst count, rate and length, but barely changes fracInNburst.
- On a large, busy array the pooled train is dense, and background firing alone can pass the ISI_N test. The minimum electrode count guards against this.

## References

- Bakkum DJ et al. (2014). Parameters for burst detection. Frontiers in Computational Neuroscience 7:193.
- Pasquale V, Martinoia S, Chiappalone M (2010). A self-adapting approach for the detection of bursts and network bursts in neuronal cultures. Journal of Computational Neuroscience 29:213–229.
- Sit TPH et al. (2024). Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
