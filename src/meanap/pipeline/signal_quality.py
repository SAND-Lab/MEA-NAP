"""Is there spiking in this recording at all? A sorter-free check on raw voltage.

Spike detection and spike sorting both find *something* on any electrode: lower
the threshold far enough and noise crosses it at tens of hertz. Their quality
metrics then describe those crossings, not whether a neuron made them. This
module asks the prior question from the voltage alone.

Spikes are brief, large, rare deflections, so a trace that holds them has heavier
tails than noise with the same power spectrum. For each electrode we compare
the filtered trace with *phase-randomised surrogates* of itself: the same
amplitude spectrum with the Fourier phases scrambled. A surrogate keeps
everything about the electrode's noise — level, colour, line-noise peaks — and
destroys anything time-locked, which is exactly what a spike is. Counting
extrema beyond ``k`` noise SDs in each gives

* the observed count — what a threshold detector at ``k`` would find;
* the surrogate count — what the same detector finds in noise that is *this
  electrode's* noise;
* the excess, its rate, and a Poisson p-value for it.

An electrode "shows spikes" when its excess is significant and at least
:data:`MIN_EXCESS_HZ`. A recording where no electrode does is noise as far as
any threshold-based method can tell, however many units a sorter returns.

The surrogate also gives the figure its "what noise looks like" trace: a window
of the most spike-like electrode beside the same window of its surrogate.

Both signs count: extracellular spikes are mostly negative, but large ones have
a positive after-peak and some units are positive-going. The negative and
positive tallies are kept apart, since artifacts are often one-signed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt
from scipy.stats import poisson

#: Thresholds, in noise SDs, at which extrema are counted. 5 is a common
#: detection threshold; 6 is where Gaussian noise of any colour has essentially
#: no extrema in a minute.
DEFAULT_KS: tuple[float, ...] = (4.0, 5.0, 6.0)
#: The threshold the verdict uses.
VERDICT_K = 5.0
#: An electrode needs at least this many excess events per second at
#: :data:`VERDICT_K` to count as showing spikes (0.1 Hz = 6 a minute).
MIN_EXCESS_HZ = 0.1
#: Per-electrode significance (one-sided Poisson, observed vs surrogate mean).
ALPHA = 1e-3
#: One event per crossing: extrema closer than this are merged (ms).
DEAD_TIME_MS = 1.0
#: Amplitude histogram bins, in noise SDs.
HIST_EDGES = np.arange(3.0, 20.25, 0.25)


@dataclass
class SignalQuality:
    """Per-electrode evidence of spiking, from one window of a recording."""

    channels: np.ndarray            # (n,) channel ids, as the loader gave them
    fs: float
    duration_s: float               # length of the window analysed
    band_hz: tuple[float, float]
    ks: tuple[float, ...]
    sigma: np.ndarray               # (n,) MAD noise SD, in the input's units
    obs_neg: np.ndarray             # (n, len(ks)) extrema below -k*sigma
    obs_pos: np.ndarray             # (n, len(ks)) extrema above +k*sigma
    surr_neg: np.ndarray            # (n, len(ks)) mean over surrogates
    surr_pos: np.ndarray
    kurtosis: np.ndarray            # (n,) excess kurtosis of the filtered trace
    surr_kurtosis: np.ndarray       # (n,)
    n_surrogates: int
    #: Pooled histogram of |extrema| / sigma over all electrodes (HIST_EDGES).
    hist_obs: np.ndarray = field(default_factory=lambda: np.zeros(len(HIST_EDGES) - 1))
    hist_surr: np.ndarray = field(default_factory=lambda: np.zeros(len(HIST_EDGES) - 1))
    #: A short window of the most spike-like electrode and its surrogate, in
    #: noise SDs, for the figure.
    example_channel: int = -1
    example_obs: np.ndarray = field(default_factory=lambda: np.zeros(0))
    example_surr: np.ndarray = field(default_factory=lambda: np.zeros(0))
    units: str = ""

    # ── derived ──────────────────────────────────────────────────────────────

    def _k(self, k: float) -> int:
        try:
            return self.ks.index(k)
        except ValueError:
            raise ValueError(f"k={k} was not counted (counted: {self.ks})") from None

    def _counts(self, k: float, sign: str):
        j = self._k(k)
        if sign == "neg":
            return self.obs_neg[:, j], self.surr_neg[:, j]
        if sign == "pos":
            return self.obs_pos[:, j], self.surr_pos[:, j]
        return self.obs_neg[:, j] + self.obs_pos[:, j], self.surr_neg[:, j] + self.surr_pos[:, j]

    def observed(self, k: float = VERDICT_K, sign: str = "both") -> np.ndarray:
        return self._counts(k, sign)[0]

    def expected(self, k: float = VERDICT_K, sign: str = "both") -> np.ndarray:
        return self._counts(k, sign)[1]

    def excess_hz(self, k: float = VERDICT_K, sign: str = "neg") -> np.ndarray:
        obs, exp = self._counts(k, sign)
        return (obs - exp) / self.duration_s

    def p_value(self, k: float = VERDICT_K, sign: str = "neg") -> np.ndarray:
        """One-sided Poisson p of seeing this many extrema in noise like this.

        The surrogate mean gets a floor of half an event, so an electrode
        whose surrogates never crossed is not called significant on one stray
        crossing of its own.
        """
        obs, exp = self._counts(k, sign)
        return poisson.sf(obs - 1, np.maximum(exp, 0.5))

    def _significant(self, k: float, sign: str) -> np.ndarray:
        return (self.p_value(k, sign) < ALPHA) & (self.excess_hz(k, sign) >= MIN_EXCESS_HZ)

    def spiking(self, k: float = VERDICT_K) -> np.ndarray:
        """Electrodes with more negative-going deflections than their own noise makes.

        Extracellular spikes are negative-going at the electrode nearest the
        cell (a large one's positive after-peak comes with its trough).
        """
        return self._significant(k, "neg")

    def positive_only(self, k: float = VERDICT_K) -> np.ndarray:
        """Electrodes whose excess is all positive-going: usually artifacts.

        Kept apart from :meth:`spiking`: on recordings with no spikes these
        are often most of the electrodes that are not noise. A few real units
        are positive-going too, so they are reported, not discarded.
        """
        return self._significant(k, "pos") & ~self.spiking(k)

    def summary(self) -> dict:
        sp = self.spiking()
        po = self.positive_only()
        exc = self.excess_hz()
        n = len(self.channels)
        obs, exp = self.observed().sum(), self.expected().sum()
        return {
            "n_electrodes": int(n),
            "n_spiking": int(sp.sum()),
            "fraction_spiking": float(sp.mean()) if n else 0.0,
            "n_positive_only": int(po.sum()),
            "window_s": float(self.duration_s),
            "median_noise_sd": float(np.median(self.sigma)) if n else float("nan"),
            "noise_units": self.units,
            f"events_beyond_{VERDICT_K:g}sd_per_electrode_min": float(obs / max(n, 1) * 60 / self.duration_s),
            f"noise_expected_beyond_{VERDICT_K:g}sd_per_electrode_min": float(exp / max(n, 1) * 60 / self.duration_s),
            "tail_ratio": float(obs / exp) if exp > 0 else float("inf") if obs > 0 else 1.0,
            "median_excess_hz_spiking": float(np.median(exc[sp])) if sp.any() else 0.0,
            "kurtosis_p99": float(np.percentile(self.kurtosis, 99)) if n else float("nan"),
            "verdict": verdict(int(sp.sum()), n, int(po.sum())),
        }

    def to_frame(self):
        import pandas as pd

        cols = {"channel": self.channels, "noise_sd": self.sigma,
                "kurtosis": self.kurtosis, "surrogate_kurtosis": self.surr_kurtosis}
        for j, k in enumerate(self.ks):
            cols[f"neg_{k:g}sd"] = self.obs_neg[:, j]
            cols[f"pos_{k:g}sd"] = self.obs_pos[:, j]
            cols[f"noise_expected_{k:g}sd"] = self.surr_neg[:, j] + self.surr_pos[:, j]
        cols["negative_excess_hz"] = self.excess_hz(sign="neg")
        cols["positive_excess_hz"] = self.excess_hz(sign="pos")
        cols["p_value"] = self.p_value()
        cols["spiking"] = self.spiking()
        cols["positive_only"] = self.positive_only()
        return pd.DataFrame(cols)


def verdict(n_spiking: int, n_electrodes: int, n_positive_only: int = 0) -> str:
    """A sentence for the log and the report."""
    if n_electrodes == 0:
        return "no electrodes to assess"
    extra = (f"; {n_positive_only} more have only positive-going excess, "
             "which is usually artifact" if n_positive_only else "")
    if n_spiking == 0:
        return ("no electrode shows spike-like events beyond what its own noise "
                "produces: as far as threshold detection or sorting can tell, "
                "this recording is noise" + extra)
    frac = n_spiking / n_electrodes
    return (f"{n_spiking} of {n_electrodes} electrodes ({frac:.0%}) show spike-like "
            f"events beyond what their own noise produces" + extra)


# ── computation ──────────────────────────────────────────────────────────────

def _bandpass_sos(fs: float, band: tuple[float, float]):
    hi = min(band[1], 0.45 * fs)
    return butter(3, [band[0], hi], btype="bandpass", fs=fs, output="sos")


def phase_randomise(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Same amplitude spectrum as each column of *x*, Fourier phases scrambled.

    *x* is (n_samples, n_channels); each column gets its own phases.
    """
    n = x.shape[0]
    spec = np.fft.rfft(x, axis=0)
    phases = rng.uniform(0, 2 * np.pi, size=spec.shape)
    phases[0] = 0.0
    if n % 2 == 0:
        phases[-1] = 0.0          # Nyquist bin stays real
    return np.fft.irfft(np.abs(spec) * np.exp(1j * phases), n=n, axis=0)


def _extrema(v: np.ndarray, thr: float, dead: int) -> np.ndarray:
    """Indices of local maxima of *v* above *thr*, one per *dead* samples."""
    idx = np.flatnonzero((v[1:-1] > v[:-2]) & (v[1:-1] >= v[2:]) & (v[1:-1] > thr)) + 1
    if len(idx) < 2:
        return idx
    keep = np.empty(len(idx), dtype=bool)
    keep[0] = True
    np.greater(np.diff(idx), dead, out=keep[1:])
    return idx[keep]


def _tally(z: np.ndarray, ks, dead: int, hist: np.ndarray | None):
    """Counts of extrema beyond each k, negative and positive, for one channel in SDs."""
    neg = np.zeros(len(ks))
    pos = np.zeros(len(ks))
    lo = min(min(ks), HIST_EDGES[0])
    i_neg = _extrema(-z, lo, dead)
    i_pos = _extrema(z, lo, dead)
    a_neg, a_pos = -z[i_neg], z[i_pos]
    for j, k in enumerate(ks):
        neg[j] = np.count_nonzero(a_neg > k)
        pos[j] = np.count_nonzero(a_pos > k)
    if hist is not None:
        hist += np.histogram(np.concatenate([a_neg, a_pos]), HIST_EDGES)[0]
    return neg, pos


#: The check is a side task next to detection: past this many threads it saves
#: seconds and costs gigabytes (each thread holds ~1.5 GB of working copies on
#: a minute of 20 kHz data).
MAX_DEFAULT_THREADS = 8


def _default_threads() -> int:
    try:
        from meanap.pipeline.parallel import compute_threads

        return min(MAX_DEFAULT_THREADS, compute_threads())
    except Exception:  # noqa: BLE001
        return 1


#: Working copies one thread holds per block sample: the float64 trace, its
#: filtered copy and sosfiltfilt's padding, the z-scored trace, and per
#: surrogate a spectrum, its phases and the inverse transform.
_BYTES_PER_BLOCK_SAMPLE = 12 * 8


def _memory_thread_cap(block_samples: int) -> int:
    """At most as many threads as free memory holds blocks for (all, without psutil)."""
    try:
        from meanap.pipeline.parallel import _HAVE_PSUTIL, available_ram_gb
    except Exception:  # noqa: BLE001
        return 1 << 30
    if not _HAVE_PSUTIL:
        return 1 << 30
    spare = available_ram_gb() * 1e9 - 2e9
    return max(1, int(spare // max(1, block_samples * _BYTES_PER_BLOCK_SAMPLE)))


def _kurtosis(z: np.ndarray) -> float:
    s2 = np.mean(z * z)
    return float(np.mean(z ** 4) / (s2 * s2) - 3.0) if s2 > 0 else 0.0


def assess_signal_quality(
    dat: np.ndarray,
    fs: float,
    channels: np.ndarray | None = None,
    *,
    band: tuple[float, float] = (600.0, 8000.0),
    ks: tuple[float, ...] = DEFAULT_KS,
    max_seconds: float | None = 60.0,
    start_s: float = 0.0,
    n_surrogates: int = 2,
    seed: int = 0,
    channel_block: int = 16,
    units: str = "",
    example_ms: float = 2000.0,
    n_threads: int | None = None,
) -> SignalQuality:
    """Assess every channel of *dat* ((n_samples, n_channels), any units).

    Only a window of ``max_seconds`` from ``start_s`` is used (``None``: all of
    it): a minute is plenty to see whether spikes exist, and keeps the check
    cheap next to detection. Channels are filtered in blocks of
    ``channel_block``, on ``n_threads`` threads (default: the pipeline's
    compute threads), so memory stays at a few copies of one block per thread.
    """
    ks = tuple(float(k) for k in ks)
    if VERDICT_K not in ks:
        ks = tuple(sorted(ks + (VERDICT_K,)))
    n_samp, n_ch = dat.shape
    a = int(round(start_s * fs))
    b = n_samp if max_seconds is None else min(n_samp, a + int(round(max_seconds * fs)))
    if b - a < int(fs):
        raise ValueError(f"need at least 1 s of data from {start_s} s (have {(n_samp - a) / fs:.2f} s)")
    if channels is None:
        channels = np.arange(n_ch)
    sos = _bandpass_sos(fs, band)
    dead = max(1, int(round(DEAD_TIME_MS * 1e-3 * fs)))
    pad = min(a, int(0.05 * fs))   # filter from a little before the window

    sigma = np.zeros(n_ch)
    kurt = np.zeros(n_ch)
    skurt = np.zeros(n_ch)
    obs_neg = np.zeros((n_ch, len(ks)))
    obs_pos = np.zeros((n_ch, len(ks)))
    surr_neg = np.zeros((n_ch, len(ks)))
    surr_pos = np.zeros((n_ch, len(ks)))

    def block(c0: int):
        """One block of channels; writes its own rows. Returns its histograms."""
        c1 = min(n_ch, c0 + channel_block)
        # Each block draws from its own stream, so results do not depend on
        # how many threads ran or in what order.
        brng = np.random.default_rng([seed, c0])
        h_obs = np.zeros(len(HIST_EDGES) - 1)
        h_surr = np.zeros(len(HIST_EDGES) - 1)
        x = np.asarray(dat[a - pad:b, c0:c1], dtype=np.float64)
        x = sosfiltfilt(sos, x - x.mean(axis=0), axis=0)[pad:]
        s = np.median(np.abs(x), axis=0) / 0.6745
        s[s == 0] = np.inf                       # a flat channel: nothing crosses
        z = x / s
        sigma[c0:c1] = np.where(np.isfinite(s), s, 0.0)
        surrs = [phase_randomise(x, brng) / s for _ in range(n_surrogates)]
        del x
        for i in range(c1 - c0):
            c = c0 + i
            obs_neg[c], obs_pos[c] = _tally(z[:, i], ks, dead, h_obs)
            kurt[c] = _kurtosis(z[:, i])
            sn = np.zeros(len(ks)); sp = np.zeros(len(ks)); sk = 0.0
            for zs in surrs:
                n_, p_ = _tally(zs[:, i], ks, dead, h_surr)
                sn += n_; sp += p_; sk += _kurtosis(zs[:, i])
            surr_neg[c], surr_pos[c] = sn / n_surrogates, sp / n_surrogates
            skurt[c] = sk / n_surrogates
        return h_obs, h_surr

    starts = list(range(0, n_ch, channel_block))
    workers = max(1, min(len(starts), n_threads or _default_threads(),
                         _memory_thread_cap((b - a + pad) * min(channel_block, n_ch))))
    if workers == 1:
        parts = [block(c0) for c0 in starts]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(block, starts))
    hist_obs = np.sum([h for h, _ in parts], axis=0)
    hist_surr = np.sum([h for _, h in parts], axis=0)
    # The example shows the clearest spikes: the most excess beyond the
    # largest threshold, so a busy electrode with spikes just past 5 SD does
    # not win over one with spikes that stand out. Falls back to 5 SD.
    best_ch = -1
    for k in sorted({max(ks), VERDICT_K}, reverse=True):
        j = ks.index(k)
        score = obs_neg[:, j] - surr_neg[:, j]
        if n_ch:
            best_ch = int(np.argmax(score))
            if score[best_ch] > 0:
                break
    rng = np.random.default_rng([seed, n_ch])

    res = SignalQuality(
        channels=np.asarray(channels), fs=float(fs), duration_s=(b - a) / fs,
        band_hz=(float(band[0]), float(min(band[1], 0.45 * fs))), ks=ks, sigma=sigma,
        obs_neg=obs_neg, obs_pos=obs_pos, surr_neg=surr_neg, surr_pos=surr_pos,
        kurtosis=kurt, surr_kurtosis=skurt, n_surrogates=n_surrogates,
        hist_obs=hist_obs / n_ch, hist_surr=hist_surr / (n_ch * n_surrogates),
        units=units,
    )
    _attach_example(res, dat, a, b, pad, sos, best_ch, rng, example_ms)
    return res


def _attach_example(res: SignalQuality, dat, a, b, pad, sos, ch, rng, example_ms):
    """Keep the busiest window of the most spike-like electrode, and its surrogate."""
    if ch < 0:
        return
    x = np.asarray(dat[a - pad:b, ch], dtype=np.float64)
    x = sosfiltfilt(sos, x - x.mean())[pad:]
    s = res.sigma[ch] if res.sigma[ch] > 0 else 1.0
    z = x / s
    zs = phase_randomise(x[:, None], rng)[:, 0] / s
    w = max(1, int(example_ms * 1e-3 * res.fs))
    if len(z) > w:
        # the window with the most negative-going events, the kind that count
        # (a running sum: np.convolve with a w-sample boxcar is O(n*w), which
        # for a 2 s window over a minute at 20 kHz took minutes)
        hits = np.zeros(len(z) + 1)
        hits[_extrema(-z, VERDICT_K, 1) + 1] = 1
        cum = np.cumsum(hits)
        dens = cum[w:] - cum[:-w]          # events in [i, i + w) for each start i
        i0 = int(np.argmax(dens))
    else:
        i0 = 0
    res.example_channel = int(res.channels[ch])
    res.example_obs = z[i0:i0 + w].astype(np.float32)
    res.example_surr = zs[i0:i0 + w].astype(np.float32)


# ── persistence ──────────────────────────────────────────────────────────────

SIGNAL_QUALITY_SUFFIX = "_signal_quality.npz"


def save_signal_quality(path: str | Path, res: SignalQuality) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path, channels=res.channels, fs=res.fs, duration_s=res.duration_s,
        band_hz=np.array(res.band_hz), ks=np.array(res.ks), sigma=res.sigma,
        obs_neg=res.obs_neg, obs_pos=res.obs_pos, surr_neg=res.surr_neg, surr_pos=res.surr_pos,
        kurtosis=res.kurtosis, surr_kurtosis=res.surr_kurtosis, n_surrogates=res.n_surrogates,
        hist_obs=res.hist_obs, hist_surr=res.hist_surr, example_channel=res.example_channel,
        example_obs=res.example_obs, example_surr=res.example_surr, units=np.array(res.units))
    return path


def load_signal_quality(path: str | Path) -> SignalQuality:
    with np.load(path, allow_pickle=False) as z:
        return SignalQuality(
            channels=z["channels"], fs=float(z["fs"]), duration_s=float(z["duration_s"]),
            band_hz=tuple(z["band_hz"].tolist()), ks=tuple(z["ks"].tolist()), sigma=z["sigma"],
            obs_neg=z["obs_neg"], obs_pos=z["obs_pos"], surr_neg=z["surr_neg"],
            surr_pos=z["surr_pos"], kurtosis=z["kurtosis"], surr_kurtosis=z["surr_kurtosis"],
            n_surrogates=int(z["n_surrogates"]), hist_obs=z["hist_obs"], hist_surr=z["hist_surr"],
            example_channel=int(z["example_channel"]), example_obs=z["example_obs"],
            example_surr=z["example_surr"], units=str(z["units"]))


# ── step 1 ───────────────────────────────────────────────────────────────────

SIGNAL_QUALITY_DIR = "1_SpikeDetection/1C_SignalQuality"
SUMMARY_CSV = "signal_quality_summary.csv"
#: Skip this much of the start, where amplifiers settle, when the recording is long enough.
SKIP_START_S = 5.0


def run_signal_quality_check(params, rec, dat, channels, fs, output_root, log) -> SignalQuality | None:
    """Step 1's check: assess, write the CSV/figure/payload, log the verdict.

    Never stops the run: a recording the check cannot read is logged and
    detection goes ahead as before.
    """
    import pandas as pd

    out_dir = Path(output_root) / SIGNAL_QUALITY_DIR
    name = rec.filename
    try:
        dur = dat.shape[0] / fs
        secs = float(params.signal_quality_seconds or 60.0)
        start = SKIP_START_S if dur >= SKIP_START_S + min(secs, 10.0) else 0.0
        res = assess_signal_quality(
            dat, fs, channels, band=(params.filter_low_pass, params.filter_high_pass),
            max_seconds=secs, start_s=start, seed=int(params.random_seed or 0),
            units=getattr(params, "potential_difference_unit", "") or "")
    except Exception as exc:  # noqa: BLE001 — a check, not a step
        log(f"  ! [{name}] signal-quality check failed ({exc}); detection goes ahead")
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    save_signal_quality(out_dir / f"{name}{SIGNAL_QUALITY_SUFFIX}", res)
    res.to_frame().to_csv(out_dir / f"{name}_signal_quality.csv", index=False)
    try:
        plot_signal_quality(res, out_dir / f"{name}_signal_quality.png", title=name)
    except Exception as exc:  # noqa: BLE001
        log(f"  ! [{name}] signal-quality figure failed ({exc})")
    s = res.summary()
    row = {"recording": name, "group": getattr(rec, "group", ""),
           "DIV": getattr(rec, "div", ""), **s}
    path = out_dir / SUMMARY_CSV
    table = pd.read_csv(path) if path.exists() else pd.DataFrame()
    if len(table) and "recording" in table:
        table = table[table["recording"] != name]
    pd.concat([table, pd.DataFrame([row])], ignore_index=True).to_csv(path, index=False)
    mark = "  !" if s["n_spiking"] == 0 else "  "
    log(f"{mark} [{name}] signal quality: {s['verdict']} "
        f"({s['tail_ratio']:.1f}x the >{VERDICT_K:g} SD deflections of its own noise)")
    return res


# ── figure ───────────────────────────────────────────────────────────────────

def _zoom(res: SignalQuality, show_ms: float):
    """The *show_ms* of the stored example with the most negative events, and its start."""
    w = max(1, int(show_ms * 1e-3 * res.fs))
    obs, surr = res.example_obs.astype(float), res.example_surr.astype(float)
    if len(obs) <= w:
        return obs, surr, 0
    hits = np.zeros(len(obs) + 1)
    hits[_extrema(-obs, VERDICT_K, 1) + 1] = 1
    cum = np.cumsum(hits)
    i0 = int(np.argmax(cum[w:] - cum[:-w]))
    return obs[i0:i0 + w], surr[i0:i0 + w], i0


def plot_signal_quality(res: SignalQuality, out_path: str | Path | None = None,
                        title: str = "", axes=None, show_ms: float = 250.0):
    """Three panels: example trace vs its surrogate, tail histogram, excess per electrode.

    The trace panel shows *show_ms* of the stored 2 s example — the stretch
    with the most events — with every extremum beyond 5 SD marked, so the
    count the verdict rests on is visible rather than inferred.
    """
    import matplotlib.pyplot as plt

    own = axes is None
    if own:
        fig, axes = plt.subplots(1, 3, figsize=(13, 3.4),
                                 gridspec_kw={"width_ratios": [2.2, 1.2, 1.2]})
    else:
        fig = axes[0].figure
    s = res.summary()
    ax = axes[0]
    if len(res.example_obs):
        obs, surr, i0 = _zoom(res, show_ms)
        t = (i0 + np.arange(len(obs))) / res.fs * 1e3
        dead = max(1, int(round(DEAD_TIME_MS * 1e-3 * res.fs)))
        # the surrogate goes below, clear of the recorded trace's spikes
        off = min(np.min(obs), -VERDICT_K) - max(np.max(surr), VERDICT_K) - 4.0
        n_hits = []
        for y0, trace, colour in ((0.0, obs, "C0"), (off, surr, "0.5")):
            ax.plot(t, trace + y0, color=colour, lw=0.7)
            for y in (-VERDICT_K, VERDICT_K):
                ax.axhline(y0 + y, color="C3", lw=0.5, ls=":")
            hits = _extrema(-trace, VERDICT_K, dead)
            ax.plot(t[hits], trace[hits] + y0 - 1.2, "^", color="C3", ms=4, mec="none")
            n_hits.append(len(hits))
        ax.set_ylim(off + min(np.min(surr), -VERDICT_K) - 2.5,
                    max(np.max(obs), VERDICT_K) + 1.0)
        ax.set_yticks([])
        ax.set_xlabel("ms"); ax.set_ylabel(f"noise SDs (dotted: ±{VERDICT_K:g})")
        ax.set_title(f"{title} · clearest electrode (ch {res.example_channel}), "
                     f"{len(obs) / res.fs * 1e3:.0f} ms\n"
                     f"▲ below −{VERDICT_K:g} SD: recorded (blue) {n_hits[0]} · its own "
                     f"noise, phases scrambled (grey) {n_hits[1]}",
                     fontsize=8.5, loc="left")
    ax = axes[1]
    centres = (HIST_EDGES[:-1] + HIST_EDGES[1:]) / 2
    per_min = 60.0 / res.duration_s
    ax.semilogy(centres, np.maximum(res.hist_obs * per_min, 1e-4), color="C0", label="recorded")
    ax.semilogy(centres, np.maximum(res.hist_surr * per_min, 1e-4), color="0.55", label="own noise")
    ax.axvline(VERDICT_K, color="C3", lw=0.5, ls=":")
    ax.set_ylim(1e-3, None)
    ax.set_xlabel("|extremum| (noise SDs)"); ax.set_ylabel("per electrode per min")
    ax.set_title("how often each size of deflection occurs", fontsize=9, loc="left")
    ax.legend(fontsize=7, frameon=False)
    ax = axes[2]
    exc = np.sort(res.excess_hz())[::-1]
    ax.plot(np.arange(1, len(exc) + 1), exc, color="C0", lw=1)
    ax.axhline(MIN_EXCESS_HZ, color="C3", lw=0.5, ls=":")
    if len(exc) > 30:   # a log rank axis only pays off with many electrodes
        ax.set_xscale("log")
    ax.set_xlabel("electrodes, ranked"); ax.set_ylabel(f"excess negative events >{VERDICT_K:g} SD (Hz)")
    ax.set_title(f"{s['n_spiking']} of {s['n_electrodes']} electrodes show spikes"
                 + (f"\n+{s['n_positive_only']} with positive-only excess (artifact-like)"
                    if s["n_positive_only"] else ""),
                 fontsize=9, loc="left")
    if own:
        fig.tight_layout()
        if out_path is not None:
            # The shared savefig, so the results viewer can intercept it and
            # show the figure live instead of reading a file back.
            from meanap.pipeline.figure_output import savefig

            savefig(fig, Path(out_path), default_dpi=120)
    return fig


def recordings_without_spikes(output_root: str | Path) -> list[str]:
    """The recordings in a finished run where no electrode showed spikes.

    *output_root* is a run folder or a ``.meanap`` bundle. Empty when the
    check did not run, so callers can warn on a non-empty answer alone.
    """
    import io
    import zipfile

    import pandas as pd

    root = Path(output_root)
    member = f"{SIGNAL_QUALITY_DIR}/{SUMMARY_CSV}"
    try:
        if root.is_dir():
            path = root / member
            if not path.exists():
                return []
            table = pd.read_csv(path)
        elif zipfile.is_zipfile(root):
            with zipfile.ZipFile(root) as zf:
                if member not in zf.namelist():
                    return []
                table = pd.read_csv(io.BytesIO(zf.read(member)))
        else:
            return []
    except Exception:  # noqa: BLE001 - a warning helper never breaks the caller
        return []
    if "n_spiking" not in table or "recording" not in table:
        return []
    return [str(r) for r in table.loc[table["n_spiking"] == 0, "recording"]]
