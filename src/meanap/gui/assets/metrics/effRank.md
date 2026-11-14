---
key: effRank
name: Effective rank
level: recording
family: network
related: NMF, aN, FR
---
Roughly how many independent activity patterns the recording contains: a measure of the dimensionality of the network's activity.

## What it measures

If every electrode fired in lock-step, a single pattern would describe the whole recording and the dimensionality would be about 1. If every electrode fired independently, you would need one pattern per electrode. Effective rank puts a number on where a recording sits between these two extremes, using the spread of variance across the principal components of the activity.

It is calculated from the spike trains directly, not from the thresholded network.

## Reading the values

- A continuous number from 1 up to the number of electrodes (or units) in the recording.
- **Low** values mean activity is dominated by a few shared patterns, as in cultures whose firing is mostly synchronous network bursts.
- **High** values mean electrodes contribute more independent, varied activity.
- In developing cortical cultures, the rise of synchronised bursting typically lowers dimensionality relative to the number of active electrodes.
- The maximum possible value grows with the number of channels that fire, so compare recordings with similar numbers of active electrodes, or interpret the value relative to that number.

## How MEA-NAP calculates it

`effective_rank` and `effective_rank_from_activity` (`meanap.pipeline.network_metrics`), called once per recording from `_step4_compute_one` (`meanap.pipeline.step4`):

1. Build a binary spike matrix (time × channel) at the sampling rate, using **every** channel, not only the active network nodes.
2. Resample it to `{{param:eff_rank_downsample_freq}}` Hz with a polyphase anti-aliasing filter.
3. Compute the covariance matrix between channels (or the correlation matrix, depending on `{{param:eff_rank_cal_method}}`) and its eigenvalues.
4. Divide the eigenvalues by their sum, take their Shannon entropy H, and report exp(H).

It can be switched off with `{{param:compute_eff_rank}}`.

## Things to watch for

- The value does not depend on the STTC lag. It is the same in every lag folder.
- Covariance is dominated by the busiest electrodes. A few very active channels can pull the effective rank down even if the others are independent. The correlation option weights every channel equally.
- Silent channels add nothing, but a few spikes on many channels can add small amounts of "dimensionality".

## References

- Roy O, Vetterli M (2007) The effective rank: a measure of effective dimensionality. 15th European Signal Processing Conference (EUSIPCO), 606–610.
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
