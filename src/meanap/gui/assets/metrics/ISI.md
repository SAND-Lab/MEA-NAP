---
key: ISI
name: Inter-spike and inter-event interval
also: ISImean, channelISIwithinBurst, channeISIoutsideBurst, channelAveISIwithinBurst, channelAveISIoutsideBurst
level: node
family: activity
related: FR, bursts, networkbursts, events
---
The typical time between one spike (MEA) or calcium event (CAT-NAP) and the next. Short intervals mean dense firing.

## What it measures

- **ISI** (CAT-NAP, per cell): the mean time between consecutive calcium events, in **seconds**. **ISImean** is its mean over cells.
- **channelISIwithinBurst** (MEA, per electrode): the mean spike interval inside that electrode's bursts, in **ms**.
- **channeISIoutsideBurst** (MEA, per electrode): the mean interval between spikes that are not in a burst, in **ms**. (The key is spelled this way in the output tables.)
- **channelAveISIwithinBurst** / **channelAveISIoutsideBurst** (MEA, per recording): the **median** of the electrode values above, over bursting electrodes.

## Reading the values

A short within-burst ISI means tightly packed bursts. A long outside-burst ISI means quiet periods between bursts. For calcium events, ISI is roughly the inverse of the event rate for regularly active cells.

## How MEA-NAP calculates it

- **CAT-NAP:** `calc_twop_activity_stats` (`meanap.catnap.stats`) takes each cell's event times, which are event **onsets** (start frames), and averages the differences. Cells with fewer than two events have no ISI. ISImean averages every cell with an ISI, active or not. It exists only under the `peaks` measure (this run: `{{param:twop_activity}}`).
- **MEA:** `single_channel_burst_detection` (`meanap.pipeline.burst_detection`) finds single-electrode bursts (see the bursts card). For each burst it averages the intervals between its spikes, then averages over the electrode's bursts. The outside-burst value averages the gaps between consecutive spikes that belong to no burst. Electrodes with no bursts are left blank.

## Things to watch for

- The units differ: MEA intervals are in ms, CAT-NAP intervals in seconds.
- On MEA, the outside-burst gaps include the gap that spans a burst, from the last spike before it to the first spike after it.
- The recording-level MEA values are medians over bursting electrodes only. They do not describe electrodes that never burst.

## References

- Bakkum DJ et al. (2014). Parameters for burst detection. Frontiers in Computational Neuroscience 7:193.
- Sit TPH et al. (2024). Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
