"""The three pipelines MEA-NAP ships, and which GUI tabs each one needs.

MEA-NAP is really three pipelines sharing one window, and each reads a different
slice of the settings. Showing every tab regardless means most users spend most
of their time looking at settings their run will never read — worse, at settings
that look like they matter. A *mode* narrows the window to the tabs its pipeline
actually consumes.

Which tabs belong to which mode is derived from what each pipeline reads, not
from taste:

* ``meanap`` — the ephys pipeline: raw traces → spike detection → connectivity
  → network metrics.
* ``meastim`` — the same ephys pipeline plus the stimulation analysis that runs
  after it (see ``runner.py``), so it needs everything ``meanap`` does and the
  two stimulation tabs on top.
* ``catnap`` — suite2p calcium imaging. ``run_catnap_pipeline`` returns before
  the ephys steps, so sampling rate, electrode layout and spike detection never
  apply. It *does* read the connectivity settings (``func_con_lag_val`` and the
  probabilistic-thresholding fields), so that tab stays.

The Data, Run and Results tabs appear in every mode: the first says what to
analyse, the second is how you start work — either this run, or a queue of saved
parameter files — and the third is mode-independent, being about results already
on disk. A queue may mix *different* pipelines, since each file carries its own
mode flags and ``run_pipeline`` decides from those.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Tab keys, in the order tabs are laid out. ``MainWindow`` owns the widgets;
#: this module only decides which keys a mode shows.
TAB_DATA = "data"
TAB_SPIKE = "spike"
TAB_CONNECTIVITY = "connectivity"
TAB_STIM = "stim"
TAB_STIM_PREVIEW = "stim_preview"
TAB_CATNAP = "catnap"
TAB_RESULTS = "results"
TAB_RUN = "run"
TAB_STATS = "stats"


@dataclass(frozen=True)
class Mode:
    """One pipeline: what to call it, which tabs it needs, how it runs."""

    key: str
    label: str          # shown in the mode selector
    blurb: str          # one-line description, used as the selector's tooltip
    tabs: frozenset[str]
    #: The ``Params`` flags that make the pipeline actually run this way.
    #: Keeping them here means picking a mode can't leave the GUI showing one
    #: pipeline while the run does another.
    suite2p_mode: bool = False
    stimulation_mode: bool = False
    #: Default STTC lags (ms). A calcium transient lasts on the order of a
    #: second, where a spike lasts a millisecond, so the coincidence windows
    #: that make sense for 2P are ~100× the ephys ones: carrying the ephys
    #: lags into CAT-NAP finds almost no coincidences at all. ``MainWindow``
    #: swaps these in on a mode switch, but only when the field is still on
    #: the old mode's defaults — see ``ConnectivityPanel.retune_lags_for_mode``.
    default_lags: tuple[int, ...] = (10, 15, 25)


_EPHYS_TABS = (TAB_DATA, TAB_SPIKE, TAB_CONNECTIVITY, TAB_RUN, TAB_RESULTS,
               TAB_STATS)

MODES: dict[str, Mode] = {
    "meanap": Mode(
        key="meanap",
        label="MEA-NAP  ·  Ephys",
        blurb="Spike detection → activity → connectivity → network analysis for MEA recordings.",
        tabs=frozenset(_EPHYS_TABS),
    ),
    "meastim": Mode(
        key="meastim",
        label="MEA-Stim  ·  Stimulation",
        blurb="The ephys pipeline plus detection and analysis of electrical stimulation.",
        tabs=frozenset(_EPHYS_TABS + (TAB_STIM, TAB_STIM_PREVIEW)),
        stimulation_mode=True,
    ),
    "catnap": Mode(
        key="catnap",
        label="CAT-NAP  ·  2P imaging",
        blurb="Network analysis of two-photon calcium imaging processed with suite2p.",
        tabs=frozenset((TAB_DATA, TAB_CONNECTIVITY, TAB_CATNAP,
                        TAB_RUN, TAB_RESULTS, TAB_STATS)),
        suite2p_mode=True,
        # What the MATLAB 2P runs use (see python/CATNAP_PORT_PLAN.md).
        default_lags=(1000, 2500, 5000),
    ),
}

DEFAULT_MODE = "meanap"


def mode_for_params(params) -> str:
    """Which mode the given ``Params`` describes.

    Lets the GUI follow a parameter file that was saved in another mode, so the
    tabs on screen always match the pipeline that would run.
    """
    if getattr(params, "suite2p_mode", False):
        return "catnap"
    if getattr(params, "stimulation_mode", False):
        return "meastim"
    return "meanap"


def apply_mode_to_params(mode_key: str, params) -> None:
    """Set the pipeline flags on ``params`` to match ``mode_key``."""
    mode = MODES[mode_key]
    params.suite2p_mode = mode.suite2p_mode
    params.stimulation_mode = mode.stimulation_mode
