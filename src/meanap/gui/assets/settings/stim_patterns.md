---
key: stim_patterns
name: Grouping pulses into conditions
tab: Stimulation
labels: Pattern time-diff threshold; Sequence gap
params: stim_time_diff_threshold, stim_group_sequences, stim_sequence_gap
related: stim_detection, stim_windows
---
How detected pulses become stimulation conditions, the "patterns" that every response figure and table is split by.

## What it does

There are two ways to group, chosen by the **Group pulses into sequences** box.

**Unticked (default; MATLAB's grouping).** Electrodes are grouped, not pulses. Electrodes are taken in order of how many pulses they received. Each one joins an existing pattern only if both conditions hold:

- it has the same number of pulses as that pattern;
- the mean absolute difference between its pulse times and the pattern's is below **Pattern time-diff threshold** (default 0.005 s).

Otherwise it starts a new pattern. Electrodes that were always stimulated together therefore form one condition, named after its electrodes (e.g. `12+13`).

**Ticked.** Pulses are grouped, not electrodes. Every pulse on every stimulating electrode is put in time order. Pulses that follow each other within **Sequence gap** (default 50 ms) form one stimulus. Within a stimulus, pulses less than 1 ms apart count as simultaneous. Stimuli with the same steps (the same electrodes, in the same order) are trials of one condition, named like `12>13>14`. The condition's event time is its first pulse, and its last pulse sets where the response can start to be measured. A condition seen fewer than 3 times is dropped.

## Choosing a value

- Keep the default for sets of electrodes pulsed together.
- Tick the box for temporal patterns, such as a sweep from left to right and back. Under electrode grouping, a sweep becomes one pattern per electrode, and two sweep directions over the same electrodes get mixed.
- Set **Sequence gap** longer than the longest delay within a sequence and shorter than the pause between stimuli.

## How MEA-NAP uses it

Each condition is analysed separately. It gets its own `pattern_id` rows in `StimActivity_NodeLevel.csv`, its own `…_pattern_<k>` figures and its own stimulus-triggered networks. A `StimConditions` column in the batch spreadsheet renames conditions, e.g. `LtoR=12>13>14; RtoL=14>13>12`. That is how different electrodes in different wells can count as the same condition in group comparisons.

## Things to watch for

- Under the default grouping, an electrode that missed a single pulse has a different pulse count, so it becomes a pattern of its own.
- Pulses are detected per electrode, after the refractory period has been applied. A pulse dropped there cannot be recovered by either grouping.
