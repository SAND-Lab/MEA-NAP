---
key: signalquality
name: Signal quality
also: 0_SignalQuality
level: concept
family: activity
related: FR
---
Whether a recording holds spikes at all, judged from the voltage alone, before any spike is detected. A detector or spike sorter always finds *something*: with the threshold low enough, noise crosses it tens of times a second. This check says when noise is all there is.

## What it measures

Spikes are brief, large and rare, so a trace that holds them has more large deflections than noise of the same power. The check compares each electrode with a **phase-scrambled copy** of itself, and counts how many more large deflections the real trace has.

**What phase scrambling means.** Any trace can be written as a sum of sine waves, each with an amplitude and a phase (where in its cycle it starts). The amplitudes set how much power the trace has at each frequency: its noise level, its colour (more low than high frequency, say) and any line noise at 50 or 60 Hz. The phases set *when* things happen. A spike is many frequencies peaking together at the same moment, which takes their phases to line up.

Scrambling keeps every amplitude and replaces every phase with a random one. The copy has exactly the electrode's own spectrum, so the same noise level, colour and line noise. But nothing in it lines up in time any more, so it has no spikes. It is what that electrode would look like if it recorded only noise. Large deflections the real trace has and the copy lacks are spikes (or artifacts).

## Reading the values

The figure has three panels.

- **Left: one electrode, recorded and scrambled.** 250 ms of the electrode with the clearest spikes (ink, top) above the same stretch of its scrambled copy (grey, below). Both are in units of that electrode's noise SD, with ±5 SD dotted. Each red dot marks a deflection below −5 SD, and the count is written above each trace. A good recording has dots on the top trace and few or none on the grey one.
- **Middle: how often each size of deflection occurs.** Every local peak or trough on every electrode, by its size in noise SDs, as a rate per electrode per minute (log scale). Noise falls off steeply, and the scrambled copy (grey) shows how steeply for this recording. Spikes are the ink tail that carries on to the right after the grey curve has dropped away. With no spikes, the two curves lie on top of each other.
- **Right: the excess on every electrode, ranked.** For each electrode, how many more deflections below −5 SD per second the recording has than its scrambled copy, sorted from most to least. The dotted line is the 0.1 Hz an electrode needs to count as showing spikes; the title says how many do. A long shoulder above the line means spikes on many electrodes; a curve along 0 means none.

A recording where **no electrode shows spikes** is noise as far as threshold detection or sorting can tell. Spikes found in it, and the networks built from them, describe noise. Lowering the threshold does not change that.

## How MEA-NAP calculates it

In step 1, before detection, `assess_signal_quality` (`meanap.pipeline.signal_quality`) reads `{{param:signal_quality_seconds}}` s of each recording, from 5 s in when it is long enough, where amplifiers have settled (check on: `{{param:signal_quality_check}}`). For each electrode it:

1. filters the trace with the detection bandpass and measures the noise SD as median absolute deviation / 0.6745, as the threshold detector does;
2. makes phase-scrambled copies: the Fourier transform of the trace, every phase replaced by a uniformly random one, transformed back;
3. counts local extrema beyond 4, 5 and 6 SD in the trace and in the copies, negative and positive separately, at least 1 ms apart.

An electrode **shows spikes** when its negative-going extrema beyond 5 SD outnumber the copies' significantly (one-sided Poisson test, p < 0.001) and by at least 0.1 per second. Extracellular spikes are negative-going at the nearest electrode, so an electrode whose excess is only positive-going is counted apart, as likely artifact.

Each electrode gets its own copy because electrodes differ in noise level and colour. A single reference for the whole array would flag the noisier electrodes as spiking.

## Things to watch for

- It sees spikes larger than about 5 noise SDs. Smaller spikes may exist, but no threshold method can tell them from noise either.
- Large artifacts count too. An excess that is mostly positive-going (the `pos_` columns of `<recording>_signal_quality.csv`) is a warning sign.
- A few electrodes with a weak excess can be a handful of sparse cells or a few faulty electrodes. An electrode that recurs across recordings of the same preparation is the better candidate for a cell.
- The verdict covers the stretch it read. Very sparse or intermittent activity may need a longer window.
- Passing does not replace checking the detected spikes or sorted units.
