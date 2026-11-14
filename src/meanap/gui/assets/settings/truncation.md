---
key: truncation
name: Truncating recordings
tab: Data
labels: Truncate recording; Truncation length; Keep
params: trunc_rec, trunc_length, trunc_keep
related: data_input, sttc
---
Analyse only part of each recording, so recordings of different lengths are compared over a window of the same length.

## What it does

When **Truncate recording** is on, MEA-NAP keeps only **Truncation length** seconds of each recording (default 120 s; off by default). **Keep** chooses which end:

- **First part of the recording** keeps 0 s to the truncation length. This is the only option in MATLAB.
- **Last part of the recording** keeps the final stretch and shifts it to start at 0 s. Rasters, rates and every later figure then cover only the kept window.

A recording no shorter than the truncation length is not changed.

## Choosing a value

- Leave it off when all recordings are about the same length.
- Turn it on when lengths differ a lot. Counts, burst numbers and the number of edges that pass thresholding all depend on duration: a longer recording gives the surrogate test more spikes to work with, so it keeps more edges. Set the length to the shortest recording you want to keep.
- Keep the **last** part if the start of each recording is unsettled, for example after a medium change or after moving the plate onto the headstage.
- Shorter windows also make step 3 faster.

## How MEA-NAP uses it

Spike detection (step 1) still runs on the whole raw recording. The cut is made on the spike times when steps 2, 3 and 4 load them, and the duration used for rates and for STTC is reset to the kept window. In CAT-NAP, the suite2p traces are cut to the same window, in frames, before anything is computed.

## Things to watch for

- Firing rates are spikes divided by the kept duration. Rates from a truncated run cannot be compared directly with an untruncated run of the same data.
- The step-1 spike-detection check figures still show the whole recording.
