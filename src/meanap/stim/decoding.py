"""Post-stim activity feature matrices + stimulation-pattern decoding.

Port of the ``stimActivityStore`` construction and the ``fitcecoc``-based
pattern-decoding block of ``stimActivityAnalysis.m`` (origin/main).

**Stochastic + degenerate on the test data.** MATLAB decodes *which pattern* was
stimulated from post-stim firing rates using an error-correcting-output-code
multiclass SVM with random node subsets and k-fold CV. It is meaningful only
with >= 2 stimulation patterns; the bundled recordings have a single pattern, so
decoding is degenerate there (one class → accuracy undefined). And even with
multiple patterns it is not bit-reproducible (random node subsets + CV folds).
``sklearn``'s ``OneVsOneClassifier(SVC)`` stands in for MATLAB's ECOC.
"""

from __future__ import annotations

import warnings

import numpy as np

from .detection import StimChannelInfo
from .psth import get_fr_aligned_to_stim


def _spikes_by_channel(spike_times: dict, method: str, n_channels: int) -> list[np.ndarray]:
    return [np.asarray(spike_times.get(c, {}).get(method, []), dtype=float).ravel()
            for c in range(n_channels)]


# default decoding windows (MATLAB overwrites Params.stimDecodingTimeWindows in place)
DEFAULT_DECODING_WINDOWS = np.linspace(0, 0.01, 10)


def build_stim_activity_store(
    spike_times: dict,
    stim_info: list[StimChannelInfo],
    stim_patterns: list[np.ndarray],
    params: dict,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Build per-pattern (trials × channels·windows) firing-rate feature matrices.

    Returns ``(stim_activity_store, pattern_spike_matrix_store)`` — the first for
    decoding (per-trial), the second trial-averaged (per-window heatmap input).

    Reproduces a MATLAB off-by-one: the window-to-raster-bin mapping subtracts 1
    from the matched edge index, so ``patternSpikeMatrixAtWindow`` actually reads
    the raster bin *preceding* the requested decoding window. Faithfully kept.
    """
    method = params["SpikesMethod"]
    n_channels = len(stim_info)
    windows = np.asarray(params.get("stimDecodingTimeWindows", DEFAULT_DECODING_WINDOWS), float)
    # MATLAB forces rasterBinWidth = 0.01 for this section
    fr_params = {**params, "rasterBinWidth": 0.01}
    spikes_by_ch = _spikes_by_channel(spike_times, method, n_channels)

    n_bins = windows.shape[0] - 1
    store, mean_store = [], []
    for st in stim_patterns:
        st = np.asarray(st, dtype=float).ravel()
        if st.size == 0:
            store.append(np.zeros((0, n_channels * n_bins)))
            mean_store.append(np.zeros(n_channels * n_bins))
            continue
        fr, raster_bins = get_fr_aligned_to_stim(spikes_by_ch, st, fr_params)
        n_trials = fr.shape[1]
        mat = np.zeros((n_trials, n_channels * n_bins))
        for w in range(n_bins):
            edge_j = np.flatnonzero((raster_bins >= windows[w]) & (raster_bins <= windows[w + 1]))
            bin_idx = edge_j - 1                      # MATLAB find(...) - 1
            bin_idx = bin_idx[(bin_idx >= 0) & (bin_idx < fr.shape[2])]
            if bin_idx.size:
                at_window = np.nanmean(fr[:, :, bin_idx], axis=2)   # (n_ch, n_trials)
            else:
                at_window = np.full((n_channels, n_trials), np.nan)
            mat[:, w * n_channels:(w + 1) * n_channels] = at_window.T
        store.append(mat)
        # all-NaN columns are expected (the off-by-one window→bin mapping)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            mean_store.append(np.nanmean(mat, axis=0))
    return store, mean_store


def decode_patterns(
    stim_activity_store: list[np.ndarray],
    n_channels: int,
    windows: np.ndarray | None = None,
    n_repeats: int = 10,
    n_kfold: int = 5,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Decode stimulation pattern from post-stim activity (port of the SVM block).

    Returns ``(num_nodes_to_try, decoding_accuracy[len(nodes), n_repeats])``.
    Requires >= 2 patterns with >= 2 trials each; otherwise returns NaNs.
    Not bit-reproducible (stochastic node subsets + CV folds).
    """
    from sklearn.multiclass import OneVsOneClassifier
    from sklearn.svm import SVC
    from sklearn.model_selection import cross_val_score, StratifiedKFold

    if rng is None:
        rng = np.random.default_rng()
    windows = DEFAULT_DECODING_WINDOWS if windows is None else np.asarray(windows)
    n_windows = windows.shape[0] - 1

    X = np.vstack([m for m in stim_activity_store if m.shape[0] > 0])
    y = np.concatenate([np.full(m.shape[0], p + 1)
                        for p, m in enumerate(stim_activity_store) if m.shape[0] > 0])
    with warnings.catch_warnings():          # all-NaN feature columns → 0 after impute
        warnings.simplefilter("ignore", category=RuntimeWarning)
        X = (X - np.nanmean(X, axis=0)) / np.nanstd(X, axis=0)
    X = np.nan_to_num(X, nan=0.0)

    num_nodes_to_try = np.arange(1, n_channels + 1, 5)
    acc = np.zeros((num_nodes_to_try.size, n_repeats))
    n_classes = np.unique(y).size

    for ni, n_use in enumerate(num_nodes_to_try):
        for r in range(n_repeats):
            nodes = rng.choice(n_channels, size=int(n_use), replace=False)
            feat = np.concatenate([w * n_channels + nodes for w in range(n_windows)])
            Xs = X[:, feat]
            if n_classes < 2 or np.all(Xs == 0):
                acc[ni, r] = np.nan
                continue
            try:
                clf = OneVsOneClassifier(SVC(kernel="linear"))
                cv = StratifiedKFold(n_splits=n_kfold, shuffle=True,
                                     random_state=int(rng.integers(1 << 31)))
                scores = cross_val_score(clf, Xs, y, cv=cv)
                acc[ni, r] = float(np.mean(scores))     # accuracy = 1 - kfoldLoss
            except Exception:
                acc[ni, r] = np.nan
    return num_nodes_to_try, acc
