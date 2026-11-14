---
key: stim_windows
name: Response analysis windows
tab: Stimulation
labels: Response analysis; Analysis window start; Analysis window end; Post-stim ignore duration; Raster bin width; Stim duration (plotting)
params: stim_analysis_window, post_stim_window_dur, stim_drop_artifact_spikes, stim_raster_bin_width, stim_duration_for_plotting
image: stim_windows.png
related: stim_detection, stim_significance, stim_networks
---
The stretch of time around each stimulus in which MEA-Stim measures a response, and how much of it right after the pulse is skipped as artifact.

## What it does

- **Analysis window start / end** (defaults −0.03 s and 0.03 s) set the window around each stimulus for every per-electrode response measure. Spike times inside it are taken relative to the stimulus. They are binned at 1 ms and smoothed with a 1 ms Gaussian to give the PSTH, from which come the peak firing rate, peak time and AUC.
- The **response window** runs from the end of the artifact to the window end. The **baseline window** is equally long and ends at the stimulus. d′, the z-score, the before/after firing-rate figure and the shuffle test all compare these two windows. The corrected AUC subtracts the mean AUC of 30 earlier windows. Event-driven runs use fewer when stimuli are close together.
- **Post-stim ignore duration** (default 0.5, in **milliseconds**) is added to the blank to give the artifact.
  - Electrical: the blank is the most common blank length on the non-stimulating electrodes. Every spike from a pulse's blank start to blank start + blank + ignore is removed, on every electrode.
  - Event-driven: there is no blank, so the artifact is the ignore duration alone.
- *Spike detection drops detections in the stimulation blank* (ticked by default; electrical only) removes the same windows in step 1, so steps 2–4 never see those detections.
- **Stim duration (plotting)** (default 0.1 s) is only how wide each pulse is drawn in the stimulus-detection check figures.
- **Raster bin width** (default 0.1 s): see *Things to watch for*.

## Choosing a value

The defaults suit electrical stimulation, where early responses fall within about 30 ms. For light or other sensory stimuli, use a window on the scale of the response, e.g. −0.5 to 1.0 s, and set the ignore duration to 0. Raise the ignore duration if the PSTH still shows a sharp spike just after the blank.

## How MEA-NAP uses it

The window sets every column of `StimActivity_NodeLevel.csv` and the PSTH, raster, heatmap and latency figures. The stimulus-triggered networks use their own windows.

## Things to watch for

- The ignore duration is in ms while every other window here is in s.
- If the artifact is as long as the response window or longer, the shuffle test and the before/after figure cannot be computed.
- **Raster bin width** currently changes nothing. Every figure and decoding step that bins spikes overrides it with 0.01 s, as the MATLAB code does.
