---
key: stim_detection
name: Detecting stimulation pulses
tab: Stimulation
labels: Detection; Detection method; Raw data processing; Detection value; Refractory period; Min blanking duration; Stim duration; Axion stim CSV
params: stim_detection_method, stim_raw_data_processing, stim_detection_val, stim_refractory_period, min_blanking_duration, stim_duration, axion_stim_csv
image: stim_detection.png
related: stim_patterns, stim_events, stim_windows
---
How MEA-Stim finds electrical stimulation pulses in the raw voltage, one channel at a time.

## What it does

**Detection method** chooses the rule:

- **longblank** (default): during each pulse the amplifier holds the stimulating electrode at a constant value. A run of identical samples at least **Min blanking duration** long (default 0.004 s) is a pulse, and its first sample is the onset. **Detection value** is not used.
- **blanking**: samples whose deviation from the channel median, divided by a spread estimate, exceeds **Detection value**. Each one snaps to the nearest earlier blank onset in a template built from all channels.
- **absPosThreshold** / **absNegThreshold**: samples above or below **Detection value**, in the raw data's units (µV). For the negative threshold, enter a negative number.
- **stdNeg**: samples below the channel mean minus **Detection value** × SD.
- **axionStimEvents**: times from Axion stimulation events, selected by the rows (rawName, well, electrode) of **Axion stim CSV**.
- **maxwellTTL** / **eventsCSV**: stimuli from a log rather than the voltage. These hide this box (see *Stimulus events*).

On every channel, **Refractory period** (default 2.9 s) then keeps the first candidate and drops any other candidate within that time of it.

## Choosing a value

Use longblank for blanked MCS-style recordings. Set **Refractory period** a little shorter than the shortest interval between pulses on one electrode. The threshold methods flag every sample of a pulse, so they depend on it completely. **Stim duration** (default 0.00012 s) is the pulse width. It is stored with each pulse but changes no result.

## How MEA-NAP uses it

Electrodes with detected pulses are the stimulating electrodes. They are left out of every response metric and network. On longblank data, the other electrodes show shorter constant runs, from 1 ms up to the minimum blanking duration. The most common of those lengths, plus the post-stimulus ignore duration, gives the artifact window (red in the picture). Spikes in that window are removed from all electrodes.

## Things to watch for

- **Raw data processing** (`medianAbs`: |x − channel median|) is applied only on the Stim Preview tab. The pipeline run detects on the unprocessed voltage.
- **axionStimEvents** is not wired into the run. No Axion `.raw` reader is ported, so every recording logs "no stimulation detected".
- A minimum blanking duration longer than the stimulator's blank finds nothing. One shorter than the blank on the other electrodes makes every electrode look like a stimulating one.
- Check the detected onsets on the Stim Preview tab or in `1C_StimDetectionChecks`.
