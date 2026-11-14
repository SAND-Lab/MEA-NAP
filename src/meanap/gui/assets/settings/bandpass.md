---
key: bandpass
name: Bandpass filter
tab: Spike detection
labels: Bandpass filter; Low-pass cutoff; High-pass cutoff
params: filter_low_pass, filter_high_pass
image: sd_bandpass.png
related: thresholds, wavelets
---
Before detecting spikes, MEA-NAP filters each electrode's voltage so only the frequencies spikes are made of remain. The defaults keep **600 to 8000 Hz**.

## What it does
A raw MEA trace mixes fast spikes (around 1 ms, so most of their power lies between a few hundred and a few thousand Hz) with slow local field potentials and drift. The filter removes the slow part, so the trace sits flat around zero and a spike's depth can be measured from a steady baseline (picture, bottom).

The labels name the two edges of the band, not the filters that make them:

- **Low-pass cutoff** (default 600 Hz) is the **lower** edge of the band. Frequencies below it are removed.
- **High-pass cutoff** (default 8000 Hz) is the **upper** edge. Frequencies above it are removed.

So Low-pass cutoff must be smaller than High-pass cutoff. At each edge the gain is one half (picture, top).

## Choosing a value
Keep 600–8000 Hz unless you have a reason to change it. Raising the lower edge (to 800–1000 Hz) removes more field potential and slow artefacts, but makes spikes smaller and narrower. Lowering it (to 300 Hz, the usual choice for spike sorting) keeps more of each spike's slow rebound but lets more of the field potential through.

## How MEA-NAP uses it
Step 1 filters every electrode with a 3rd-order Butterworth bandpass, run forwards and backwards (`filtfilt`) so spikes are not shifted in time. Both the threshold and the wavelet detectors work on the filtered trace, and the noise level is measured from it. The spike check figures use the same filter. Spike sorting has its own band (**Bandpass for sorting**).

## Things to watch for
- The upper edge must be below half the sampling rate. At 25 kHz that limit is 12.5 kHz, so 8000 Hz is fine. At 12.5 kHz (Axion) the limit is 6250 Hz: MEA-NAP then silently moves the upper edge to just below 6250 Hz, so in effect the filter only removes the low frequencies.
- Changing the band changes the noise level and therefore the threshold positions and spike counts. Compare recordings only when they were filtered alike.
