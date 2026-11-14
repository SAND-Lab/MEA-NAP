---
key: wavelets
name: Wavelet spike detection
tab: Spike detection
labels: Wavelet; Wavelet methods; Wavelet cost
params: wname_list, cost_list
image: sd_wavelets.png
related: spike_method, thresholds, bandpass, refractory, templates
---
The wavelet detector looks for stretches of the filtered trace that have the shape of a spike, rather than for dips below a fixed voltage. **bior1.5** is MEA-NAP's default and the only wavelet the Python pipeline runs.

## What it does
A wavelet is a short wiggle with a set shape (the blue curves above). The detector slides it along the bandpass-filtered trace, stretched to five widths between 0.4 and 0.8 ms (the width range of a typical spike), and at each point measures how well the trace matches. A spike gives a large match; noise gives small, random ones. Detection then decides, scale by scale, which matches are large enough to be spikes, merges detections closer than about 0.6 ms, and moves each spike to the bottom of its trough.

**Wavelet methods** are the shapes to try. **bior1.3** and **db2** are other standard wavelets; **mea** is a custom wavelet built from the median spike that a threshold detector finds on each electrode (see the template settings). Each selected wavelet is saved as its own result (`bior1p5`, …).

**Wavelet cost** (default −0.12) tilts that decision. It sets how the Bayesian decision rule of Nenadic & Burdick weighs missed spikes against false ones: more negative values lower the bar and find more spikes; zero or positive values raise it and find fewer.

![How the cost changes the count](sd_wavelet_cost.png)

## Choosing a value
Keep bior1.5 and −0.12 unless the spike check figures show a problem. If small, real spikes are missed, try −0.2; if the detector picks up noise on quiet electrodes, try 0 or a little above. On the synthetic data above, lowering the cost mostly adds false detections.

## How MEA-NAP uses it
Step 1 runs every selected wavelet on every electrode and stores each result in the spike file. Only the method chosen in **Spike method for analysis** is used by steps 2–4.

## Things to watch for
- **In the Python pipeline only bior1.5 works.** Selecting bior1.3, db2 or mea stops step 1 with "Unsupported wavelet for scale determination". These three run only in MATLAB MEA-NAP.
- The cost applies to every selected wavelet.
- The width range (0.4–0.8 ms) and number of scales (5) are fixed, not settings.

## References
Nenadic Z, Burdick JW (2005). Spike detection using the continuous wavelet transform. *IEEE Trans Biomed Eng* 52(1):74–87.
