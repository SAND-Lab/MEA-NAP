"""MEA-Sim: simulated MEA networks with a known answer, for checking metrics.

A network metric is only worth comparing between groups if it measures the
property it is named after, not something that merely travels with it.
Firing rate, recording length, network bursts and slow shared activity all
change between cultures and ages, and every one of them can move a
connectivity estimate on its own. Real recordings cannot separate those
effects; simulations can, because the simulation sets them one at a time.

* :mod:`meanap.sim.model` simulates spike trains from a planted network
  (random, modular, hub or spatial), with each nuisance as a dial.
* :mod:`meanap.sim.measure` runs MEA-NAP's own edge methods (STTC, the
  circular-shift and jitter nulls, a proportional threshold) and step-4
  network metrics on the result, and scores edge recovery against the
  planted graph.
* :mod:`meanap.sim.sweep` varies one dial with everything else held fixed
  (a *line search*, as in Cutts & Eglen 2014) and summarises how far each
  metric moves.
* :mod:`meanap.sim.pairs` runs Cutts & Eglen's necessary properties
  (N1–N6) on pairwise correlation measures.

The GUI is :mod:`meanap.gui.sim_window`.
"""

#: What the tool is called on screen. One place, so renaming it is one edit.
DISPLAY_NAME = "MEA-Sim"
