---
key: templates
name: Spike templates (custom wavelet)
tab: Spike detection
labels: Template threshold; Template refractory period; Max spikes for template; Multiple templates; Template method
params: template_multiplier, get_template_ref_period, n_spikes, multiple_templates, multi_template_method
related: wavelets, refractory, thresholds
---
These settings control how the **mea** wavelet is built from each electrode's own spikes. They matter only when mea is one of the wavelet methods.

## What it does
The mea wavelet is built from your data rather than taken from a textbook. On each electrode, MEA-NAP first finds spikes with a threshold detector, cuts out their waveforms, and takes the median waveform as a template. It then smooths the template and turns it into a wavelet with the same shape (the "mea" panel in the Wavelet card's picture). That wavelet then searches the electrode for spikes like the template.

- **Template threshold** (default 3.5): the threshold detector's multiplier, in noise standard deviations, for the spikes the template is made from. This is MATLAB's "Wavelet multiplier". It is separate from the thresholds above, which are detectors in their own right.
- **Template refractory period** (default 2 ms): the shortest gap between two of those spikes.
- **Max spikes for template** (default 100): how many of the threshold detector's spikes, spread evenly through the recording, go into the median waveform. If the electrode has fewer, all of them are used.
- **Multiple templates** (default off): instead of one median waveform, group the spikes into clusters of similar shape and build one wavelet per cluster, so an electrode recording two types of neuron gets a wavelet for each.
- **Template method** (default PCA): how the spikes are grouped when Multiple templates is on. PCA groups spikes by their main shape components; the other two group them by amplitude and width, or by amplitude, width and symmetry.

## Choosing a value
Keep the defaults. Raise the template threshold if the template comes out noisy (on quiet electrodes, a low threshold lets noise into the median); lower it if electrodes with small spikes get no mea spikes at all. The median of 100 spikes is already stable, so raising Max spikes for template changes little.

## How MEA-NAP uses it
Step 1 builds one template per electrode, then the mea wavelet from it, then detects with that wavelet. The template and wavelet are the same as MATLAB MEA-NAP's for the same spikes.

## Things to watch for
- **Multiple templates and Template method are not used by the Python pipeline yet.** It always builds one template per electrode.
- The Template method option "spikeWidthAndAmplitude" does not match the name MATLAB's `getTemplate.m` checks for ("amplitudeAndWidth"). MATLAB prints "invalid multi_template method" and cannot cluster the spikes.
- MATLAB's default for Max spikes for template is 10 000, MEA-NAP's 100. Both take the median of whatever spikes there are, so the template barely differs.
- An electrode with fewer than four spikes above the template threshold gets no mea spikes.
