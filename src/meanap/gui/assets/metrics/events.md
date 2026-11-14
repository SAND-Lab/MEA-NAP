---
key: events
name: Calcium event size and duration
also: unitHeightMean, unitPeakDurMean, unitEventAreaMean, unitEventAreaSum, recHeightMean, recPeakDurMean, recEventAreaMean
level: node
family: catnap
related: FR, ISI
---
How large and how long each cell's calcium transients are (CAT-NAP only). Amplitude, duration and area have no MEA equivalent.

## What it measures

- **unitHeightMean**: mean event amplitude per cell (a.u.).
- **unitPeakDurMean**: mean event duration per cell (s).
- **unitEventAreaMean**: mean area under each event per cell (a.u.·s), which combines amplitude and duration.
- **unitEventAreaSum**: total event area per cell over the recording (a.u.·s), which also grows with the number of events.
- **recHeightMean**, **recPeakDurMean**, **recEventAreaMean**: the mean of the per-cell values over the recording's cells.

## Reading the values

Larger, longer events usually reflect stronger or longer bursts of firing in the cell. Amplitude is roughly ΔF/F, relative to each cell's own baseline, so it is broadly comparable between cells.

## How MEA-NAP calculates it

1. `process_suite2p_folder` (`meanap.catnap.denoising`) fits a baseline to each cell's suite2p F trace, keeps only stretches rising more than `{{param:twop_denoising_threshold}}` × the trace's largest dip below baseline (plus `{{param:twop_denoising_time_before_peak}}` s before and `{{param:twop_denoising_time_after_peak}}` s after), converts them to ΔF/F, and denoises them with OASIS, keeping its reconstructed calcium trace.
2. `scipy.signal.find_peaks` detects events on that trace: height and prominence at least 0.0015, width at least 1.13 s, and events at least `{{param:twop_min_event_interval}}` s apart (None means 50 frames).
3. Each event runs from where the trace rises past 5 % of the way from its base to its peak, to where it falls back to that level. The event's start is also the time used for event rate, intervals and STTC. Its height is the trace value at the peak; its area is the integral over that span.
4. `calc_twop_activity_stats` (`meanap.catnap.stats`) averages per cell, converts frames to seconds, then averages over cells.

## Things to watch for

- Only defined under the `peaks` measure (this run: `{{param:twop_activity}}`); otherwise these metrics are absent.
- Cells with no events are blank and left out of the recording means.
- Existing denoising outputs are reused unless redo is on (`{{param:twop_redo_denoising}}`), so they may reflect earlier settings.
- The default 50-frame spacing is a different time at each frame rate.
- Neuropil is not subtracted from F before denoising.

## References

- Friedrich J, Zhou P, Paninski L (2017). Fast online deconvolution of calcium imaging data. PLoS Computational Biology 13:e1005423.
- Pachitariu M et al. (2017). Suite2p: beyond 10,000 neurons with standard two-photon microscopy. bioRxiv.
