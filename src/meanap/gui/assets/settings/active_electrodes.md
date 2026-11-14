---
key: active_electrodes
name: Active electrodes
tab: Spike detection
also_tabs: Connectivity
labels: Active electrodes; Min activity level (spikes/s)
params: min_activity_level
image: sd_active_electrodes.png
related: spike_method, bursts, network_bursts
---
An electrode counts as **active** when its firing rate over the whole recording is at least this many spikes per second. The default is **0.01** (one spike every 100 s), as in the MATLAB app.

## What it does
Many electrodes on an MEA record little or nothing: no neurons nearby, or a broken contact. Including them would lower average firing rates and add empty nodes to the network. This setting draws the line (picture): electrodes at or above it are active, electrodes below it are left out.

The firing rate is the electrode's spike count, using the method chosen in **Spike method for analysis**, divided by the recording length (or by the truncated length if you analyse only part of each recording).

## Choosing a value
0.01 removes only electrodes that are essentially silent. Raise it (0.1 or more) if you want the network to include only electrodes with enough spikes for reliable connectivity estimates: with very few spikes, correlations between electrodes are noisy. At 0, every electrode counts as active, even one that never fired.

## How MEA-NAP uses it
- **Step 2:** the number of active electrodes, and the firing-rate summaries (mean, median, standard deviation, IQR across electrodes), use active electrodes only.
- **Step 4:** a node enters the network analysis only if it is active **and** has at least one connection. A network with too few such nodes gets no network metrics.

It is applied after spike detection and does not change which spikes are found. Burst detection still uses every electrode's spikes.

## Things to watch for
- This is one setting shown in two places: the same field is on the Connectivity tab, and changing either changes both.
- When the spike source is sorting or import, each node is a sorted unit, and the floor applies per unit.
- Because the number of active electrodes is itself a reported result, compare it between groups only when all groups used the same floor.
