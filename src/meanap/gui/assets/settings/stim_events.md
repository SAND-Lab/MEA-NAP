---
key: stim_events
name: Stimulus events (light, TTL, event log)
tab: Stimulation
labels: Stimulus events (light, TTL, event log); Events folder; TTL rule; Conditions; Condition labels; Merge events closer than
params: stim_events_folder, stim_event_ttl_rule, stim_event_condition_mode, stim_event_condition_labels, stim_event_min_interval
related: stim_detection, stim_windows, stim_networks
---
For stimuli that leave no mark in the voltage, such as light, sound or anything logged as events. The stimulus times come from a TTL log or a CSV file.

## What it does

This box replaces the Detection box when **Detection method** is `maxwellTTL` or `eventsCSV`.

- **Events folder**:
  - *eventsCSV*: where to find `<recording>_events.csv` (or `_stim_events.csv`, `.events.csv`). The file has a time column (`time_s`, `onset_s`, `time` or `onset`, in seconds from the start of the recording) and an optional `condition` column.
  - *maxwellTTL*: where the MaxWell raw file is.
  - If empty, MEA-NAP looks in the raw data folder, then the sorted data folder.
- **TTL rule** (maxwellTTL only): which TTL changes count as stimuli.
  - `auto` (default): of every bit that changes, take the rising or falling edges, whichever kind is rarest (at least two). A projector's frame sync toggles every frame; the stimulus marker is the rare bit. The verbose log lists each bit's edge counts and says which one was picked.
  - `rise:<bit>` / `fall:<bit>`: that bit going high or low, e.g. `fall:7` for the bit worth 128.
  - `value:<word>`: every change *to* that TTL word.
- **Merge events closer than** (default 0.05 s): a TTL marker this close to the previous kept one is dropped, so a bouncing marker counts once.
- **Conditions** and **Condition labels** (maxwellTTL only):
  - *All events one condition*: every event gets the first label, or `stim` if no label is given.
  - *Alternate labels*: the comma-separated labels are given in turn, e.g. `ON, OFF` for a flash marked at both transitions. With no labels, `A, B` is used.

## Choosing a value

Run once with `auto` and check in the log that the bit it picked is the one your protocol uses. A TTL marker does not say which transition is ON, so take the label order from the stimulus protocol.

## How MEA-NAP uses it

Each condition is analysed like an electrical stimulation pattern, with the same PSTHs, response metrics, figures and networks. No electrode counts as stimulating and nothing is blanked. Events too close to the start or end of the recording for the analysis window are dropped. The events used are saved as `stim_events.csv` beside the figures.

## Things to watch for

- The electrical defaults do not suit light. Set **Post-stim ignore duration** to 0, and widen the analysis window (e.g. −0.5 to 1.0 s).
- With eventsCSV, the CSV's own `condition` column sets the conditions. Merging is not applied.
