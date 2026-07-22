"""Remove stimulation-artifact & stim-electrode spikes.

Port of ``Functions/batchProcessSpikesFromStim.m``. Runs between detection and
analysis:

1. Empties spike times on every stimulating electrode (``elecStimTimes`` > 0).
2. Removes spikes falling in any stim electrode's artifact window
   ``[blankStart, blankStart + blankDurMode + postStimWindowDur/1000]``
   (inclusive both ends), across **all** channels/methods.

For blanked recordings this is close to a no-op on the analyzed (non-stim)
channels — the blank flattens the signal so no spikes are detected there
anyway — but it is applied for faithfulness and to empty the stim electrode
(which is excluded from analysis regardless).
"""

from __future__ import annotations

import numpy as np

from .detection import StimChannelInfo, _matlab_mode


def clean_spikes_from_stim(
    spike_times: dict[int, dict[str, np.ndarray]],
    stim_info: list[StimChannelInfo],
    params: dict,
) -> dict[int, dict[str, np.ndarray]]:
    """Return a cleaned copy of ``spike_times`` (does not mutate the input).

    ``spike_times`` : ``{channel_index: {method: times_s}}``.
    """
    out = {c: {m: np.asarray(t, dtype=float).copy() for m, t in methods.items()}
           for c, methods in spike_times.items()}

    n_ch = len(stim_info)
    stim_blank_starts: list[np.ndarray] = []
    non_stim_durs: list[np.ndarray] = []

    for c in range(n_ch):
        info = stim_info[c]
        is_stim = info.elec_stim_times.shape[0] > 0
        if is_stim and c in out:
            for m in out[c]:
                out[c][m] = np.array([])   # empty stim-electrode spikes
        if info.blank_starts is not None and is_stim:
            stim_blank_starts.append(np.asarray(info.blank_starts, dtype=float).ravel())
        if info.non_stim_blank_starts is not None and info.non_stim_blank_ends is not None:
            d = np.asarray(info.non_stim_blank_ends, dtype=float).ravel() \
                - np.asarray(info.non_stim_blank_starts, dtype=float).ravel()
            non_stim_durs.append(d)

    all_non_stim = np.concatenate(non_stim_durs) if non_stim_durs else np.array([])
    blank_dur_mode = _matlab_mode(all_non_stim) if all_non_stim.size else 0.0
    ignore = float(params.get("postStimWindowDur") or 0.0) / 1000.0

    win_start = np.concatenate(stim_blank_starts) if stim_blank_starts else np.array([])
    win_end = win_start + blank_dur_mode + ignore

    if win_start.size:
        for c in out:
            for m in out[c]:
                sp = out[c][m]
                if sp.size == 0:
                    continue
                remove = np.zeros(sp.shape[0], dtype=bool)
                for ws, we in zip(win_start, win_end):
                    remove |= (sp >= ws) & (sp <= we)
                out[c][m] = sp[~remove]

    return out
