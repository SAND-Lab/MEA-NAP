---
key: stim_networks
name: Stimulus-triggered networks
tab: Stimulation
labels: Evoked window start; Evoked window end; Post window start; Post window end; STTC; Edge test; Surrogates
params: stim_network, stim_network_window, stim_network_post_window, stim_network_sttc, stim_network_null, stim_network_rep_num
image: stim_networks.png
related: stim_significance, stim_windows, stim_events
---
Functional networks built only from the time around each stimulus. They separate electrodes that interact from electrodes that merely respond to the same stimulus.

## What it does

With *Evoked vs baseline networks and noise correlations* ticked (the default), each condition gets its own networks.

- **Evoked**: every node's spikes are cut to the window from **Evoked window start** to **Evoked window end** after each event (default 0 to 0.5 s).
- **Baseline**: an equally long window just before each event.
- **Post**: a third epoch. With *Post-stimulus window: as long as the evoked one* ticked (the default), it is as long as the evoked window and starts where it ends. Unticked, it runs from **Post window start** to **Post window end**, in seconds after the event.

An STTC network is built for each epoch at every lag on the Connectivity tab. Noise correlations come alongside: the Pearson correlation of trial-by-trial spike counts in the evoked window.

**STTC** sets how a pair's STTC is computed:

- *Within each trial, averaged over trials* (default): computed per trial and averaged over the trials in which both nodes fired. A pair needs 5 such trials. Slow shared activity states then do not pass for edges.
- *Joined end to end*: one STTC over all the windows laid end to end.

**Edge test** decides which edges are significant:

- *Trial shuffle* (default): each node's trials are reordered independently. Each node keeps its stimulus-locked response, so an edge survives only if the pair is coupled beyond the shared stimulus drive.
- *Circular shift*: step 3's test. It measures total co-activity, stimulus-locked firing included.

Each edge's p-value is (1 + surrogates ≥ observed) / (1 + **Surrogates**), with Surrogates defaulting to 200. Edges are kept when p is below **Alpha**.

## Choosing a value

Keep the epochs equally long, since STTC depends on window length. For electrical stimulation, MEA-NAP starts the evoked window after the last pulse's artifact and logs the shift. Choose windows that fit between stimuli. With 200 surrogates the smallest possible p is about 0.005, so use more surrogates for a stricter alpha.

## How MEA-NAP uses it

Results go to `StimNetwork_RecordingLevel.csv` and `StimNetwork_NodeLevel.csv`, and are drawn in figures 13–16. Stimulating electrodes are left out of every network.

## Things to watch for

- An event whose windows would reach into a neighbour's is dropped from all three epochs. With fewer than 3 usable events, the networks are skipped.
- *Within each trial* needs the trial shuffle. With *Circular shift* chosen, MEA-NAP joins the windows instead and says so in the log.
