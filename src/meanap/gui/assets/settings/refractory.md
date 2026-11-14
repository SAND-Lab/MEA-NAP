---
key: refractory
name: Refractory periods
tab: Spike detection
labels: Spike templates and refractory period; Refractory period (threshold detectors); Refractory period (wavelet detectors)
params: ref_period, wavelet_ref_period_ms
image: sd_refractory.png
related: thresholds, wavelets, templates
---
After a spike, the detector ignores the trace for a short time so that one spike is not counted twice. There are two settings because the two kinds of detector need different values: **2 ms** for the threshold detectors and **0.5 ms** for the wavelet detectors.

## What it does
**Refractory period (threshold detectors)** (default 2 ms). A spike's trough stays below the threshold for several samples, and each sample below the line is a crossing. The threshold detector keeps the first and skips everything within this period after it. The period also discards any real second spike that comes sooner, as in the picture, where a second spike 1 ms later is lost at 2 ms but kept at 0.5 ms.

**Refractory period (wavelet detectors)** (default 0.5 ms). The wavelet detector can fire twice on one spike: once on the falling edge and once on the trough, or at two widths. After each spike is moved to its trough, any spike less than this period after the previous one is dropped. On a dense culture, 5–6 % of a busy electrode's bior1.5 spikes were such doubles, all under 0.5 ms apart; spikes 0.5–2 ms apart were almost all real, from different neurons firing during a burst.

## Choosing a value
Keep the defaults. One electrode usually records several neurons, so neither period is the refractory period of a single neuron: it only sets how close two detections on the same electrode may be. Lengthen the threshold period if the spike check figures show one spike counted twice. Set the wavelet period to 0 ("off") to reproduce MATLAB MEA-NAP exactly, which has no such step.

## How MEA-NAP uses it
Both are applied in step 1, per electrode and per method, before the spike times are saved. They change spike counts, and therefore firing rates, bursts and connectivity.

## Things to watch for
- A long threshold refractory period caps the firing rate an electrode can show (2 ms → at most 500 spikes/s) and removes spikes in dense bursts.
- The two settings do not interact: the threshold period never applies to wavelet results, and the wavelet period never applies to threshold results.
