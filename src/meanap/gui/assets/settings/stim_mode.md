---
key: stim_mode
name: Stimulation mode
tab: Stimulation
labels: Stimulation mode; Enable
params: stimulation_mode
related: stim_detection, stim_events, stim_windows, stim_networks
---
Turns MEA-Stim's stimulation analysis on: find when the culture was stimulated, then measure how each electrode (or sorted unit) responded.

## What it does

Ticking **Run stimulation analysis (after spike detection)** sets `stimulation_mode`. Switching the window to MEA-Stim mode ticks it for you. If you untick it in that mode, the run is the ordinary MEA-NAP pipeline: no stimulation analysis and no artifact removal.

For each recording the analysis:

1. finds the stimuli. Electrical pulses are found in the raw voltage; light or other external stimuli come from a TTL log or an events CSV (see **Detection method**);
2. groups them into conditions (stimulation patterns);
3. empties the stimulating electrodes and removes every spike that falls in a pulse's blanked artifact;
4. computes each electrode's response to each condition (PSTH peak rate and time, AUC, d′, z-score, first-spike latency), runs a shuffle significance test and draws the per-recording figures;
5. builds evoked vs baseline networks, if those are switched on.

## Choosing a value

Off by default in MEA-NAP mode, and on in MEA-Stim mode. Leave it on for any batch that contains stimulation. Turn it off to run steps 1–4 on stimulated recordings as if their activity were spontaneous.

## How MEA-NAP uses it

The stimulation step runs straight after step 1 and before the network steps. It runs whatever step range is selected on the Run tab. It reads the step-1 spike times (`<recording>_spikes.npz`) from this run or an earlier one, and skips any recording whose spikes are not on disk. Electrical detection also needs the **raw data folder**, because the pulses are found in the voltage.

Outputs:

- `StimActivity_NodeLevel.csv`, plus the `StimNetwork…` and `StimConsistency…` tables, in the output folder;
- per-recording figures in `2_NeuronalActivity/2A_IndividualNeuronalAnalysis/<group>/<recording>/`;
- stimulus detection checks in `1_SpikeDetection/1C_StimDetectionChecks/`.

With this on and electrical detection, step 1 also drops the detections that fall in each stimulation blank. That is the *Spike detection drops detections in the stimulation blank* box under **Response analysis**, ticked by default. It keeps the blank-release artifact, which looks like a spike on every electrode after every pulse, out of steps 2–4.

## Things to watch for

- Apart from that artifact drop, steps 2–4 still treat the whole recording as one stretch of activity. Evoked firing counts towards firing rates and bursts, and the whole-recording network mixes coupling between electrodes with responses to a shared stimulus. The stimulus-triggered networks separate the two.
- Check the detection-check figures before trusting any response metric. A missed or doubled pulse changes every trial-based number.
