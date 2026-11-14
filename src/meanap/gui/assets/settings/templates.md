---
key: templates
name: Spike templates (custom wavelet)
tab: Spike detection
labels: Max spikes for template; Multiple templates; Template method
params: n_spikes, multiple_templates, multi_template_method
related: wavelets, refractory, thresholds
---
These three settings control how MATLAB MEA-NAP builds the **mea** wavelet from each electrode's own spikes. **The Python pipeline does not use them.**

## What it does
The mea wavelet is built from your data rather than taken from a textbook. On each electrode, MATLAB MEA-NAP first finds spikes with a threshold detector, cuts out their waveforms, and takes the median waveform as a template. It then smooths the template and turns it into a wavelet with the same shape (the "mea" panel in the Wavelet card's picture). That wavelet then searches the electrode for spikes like the template.

- **Max spikes for template** (default 100): how many of the threshold detector's spikes, spread evenly through the recording, go into the median waveform. If the electrode has fewer, all of them are used.
- **Multiple templates** (default off): instead of one median waveform, group the spikes into clusters of similar shape and build one wavelet per cluster, so an electrode recording two types of neuron gets a wavelet for each.
- **Template method** (default PCA): how the spikes are grouped when Multiple templates is on. PCA groups spikes by their main shape components; the other two group them by amplitude and width, or by amplitude, width and symmetry.

## Choosing a value
In the Python pipeline, nothing: leave the defaults. In MATLAB, they matter only when **mea** is one of the wavelet methods.

## How MEA-NAP uses it
The settings are saved with your other settings, but the Python pipeline cannot run the mea wavelet: selecting it stops step 1 with an error (see the Wavelet card), and none of these three values reaches the detector.

## Things to watch for
- The Template method option "spikeWidthAndAmplitude" does not match the name MATLAB's `getTemplate.m` checks for ("amplitudeAndWidth"). MATLAB prints "invalid multi_template method" and cannot cluster the spikes.
- A template is only as good as the threshold spikes it comes from. On an electrode with few or noisy spikes, the mea wavelet can match noise.
