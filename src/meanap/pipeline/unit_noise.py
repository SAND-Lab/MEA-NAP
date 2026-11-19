"""Does a sorted unit stand out from its own electrode's noise? A raw-voltage test.

A spike sorter run on a noisy electrode still returns units: it finds the
times the noise peaked and clusters them. Those "units" can look plausible on
every metric that only sees spike times or a template — a refractory gap
(the sorter enforces one), a trough-shaped mean waveform (an average of
noise peaks *is* a trough) — so they pass. This module asks the question the
raw voltage alone can answer: **could this electrode's noise, with no neuron
on it, have produced spikes this large this often?**

For each unit, on its peak electrode, over a window of the recording:

1. Band-pass the trace (as :mod:`meanap.pipeline.signal_quality` does) and
   scale it by its noise level (median absolute deviation / 0.6745), so
   values are in noise SDs.
2. Measure every spike in the window: the extreme value, in the direction of
   the unit's mean waveform, within ±``align_ms`` of the spike time. The
   median of these is the unit's **raw SNR**; times the noise level, its
   amplitude in µV.
3. Make *phase-randomised surrogates* of the same filtered trace — the same
   power spectrum (noise level, colour, line noise), with anything time-locked
   destroyed — and count their local extrema, in the same direction and at
   least ``dead_ms`` apart, beyond the unit's median amplitude. That is how
   many events of at least this size noise alone makes per second
   (``noise_rate_hz``).
4. Compare with the unit's own rate of spikes at least that large
   (``unit_rate_hz``, about half its firing rate, by the median's definition):

   ``noise_fraction = noise_rate_hz / unit_rate_hz``

   — roughly what share of the unit's large spikes the electrode's noise could
   account for by itself. ``noise_p`` is the Poisson probability of seeing
   at least the unit's count if noise were all there was.

Why extrema of the surrogate, not snippets at random times: the sorter chose
the unit's spike times *because* the voltage peaked there. A noise-only unit's
spikes are noise peaks, so they are larger than noise at random times, and a
random-time comparison would pass it. Peaks against peaks is the fair test.

A unit whose ``noise_fraction`` is at least
:attr:`~meanap.pipeline.unit_quality.QualityThresholds.max_noise_fraction`
(0.5: noise could have made half its large spikes or more) is labelled
**noise** ("noise-like") by :mod:`meanap.pipeline.unit_quality`.

The surrogate keeps the power of any real spikes on the electrode, so its
noise is, if anything, slightly too large: the test leans towards calling a
unit noise-like, never towards passing it. Other units on the same electrode
are not subtracted, for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import sosfiltfilt
from scipy.stats import poisson

from meanap.pipeline.signal_quality import _bandpass_sos, _extrema, phase_randomise

#: The columns :func:`unit_noise_metrics` adds to a unit-quality table.
COLUMNS = ("raw_n_spikes", "raw_sign", "raw_amp_uv", "raw_snr",
           "noise_rate_hz", "unit_rate_hz", "noise_fraction", "noise_p")

#: Default analysis window: two minutes holds hundreds of spikes for any unit
#: worth scoring, and keeps the read to a fraction of a long recording.
DEFAULT_MAX_SECONDS = 120.0


@dataclass(frozen=True)
class NoiseTestSettings:
    #: The band sorters filter with (SpikeInterface's and SpyKING CIRCUS's
    #: default), so amplitudes and SNRs compare with the sorter's own.
    #: signal_quality's 600-8000 Hz, tuned for *finding* spikes, cuts part of
    #: a broad MEA spike's energy and reads SNRs low.
    band: tuple[float, float] = (300.0, 6000.0)
    #: Search window around each spike time for its extreme value. Sorters
    #: report times at the trough, the threshold crossing or the template's
    #: centre, so ±0.5 ms finds the extreme whichever they used.
    align_ms: float = 0.5
    #: Minimum gap between counted surrogate extrema — one event, not every
    #: sample of its peak.
    dead_ms: float = 1.0
    n_surrogates: int = 2
    #: Fewer spikes in the window than this and the unit is not scored.
    min_spikes: int = 10


def _samples(ms: float, fs: float) -> int:
    return max(1, int(round(ms * 1e-3 * fs)))


def _prepare(trace, fs: float, s: NoiseTestSettings, seed: int):
    """The filtered trace in noise SDs, its noise SD and its surrogates — or
    ``None`` for a flat or too-short trace."""
    x = np.asarray(trace, dtype=np.float64)
    if len(x) < fs:
        return None
    pad = int(0.05 * fs)
    x = sosfiltfilt(_bandpass_sos(fs, s.band), x - x.mean(), padlen=min(len(x) - 1, 3 * pad))
    sigma = float(np.median(np.abs(x)) / 0.6745)
    if sigma <= 0:
        return None
    z = x / sigma
    del x
    rng = np.random.default_rng(seed)
    surrs = [phase_randomise(z[:, None], rng)[:, 0] for _ in range(s.n_surrogates)]
    return z, sigma, surrs


def _spike_index(train, fs: float, n: int, half: int) -> np.ndarray:
    idx = np.round(np.asarray(train, dtype=float) * fs).astype(np.int64)
    return idx[(idx >= half) & (idx < n - half)]


def _spike_sizes(z: np.ndarray, fs: float, train, s: NoiseTestSettings):
    """``(sample indices, sign, sizes in SDs)`` of a unit's spikes, or ``None``
    when it has fewer than ``s.min_spikes`` in the window."""
    half = _samples(s.align_ms, fs)
    idx = _spike_index(train, fs, len(z), half)
    if len(idx) < s.min_spikes:
        return None
    offsets = np.arange(-half, half + 1)
    snips = z[idx[:, None] + offsets[None, :]]
    mean_wave = snips.mean(axis=0)
    sign = -1 if -mean_wave.min() >= mean_wave.max() else 1
    return idx, sign, (sign * snips).max(axis=1)


def _noise_events(surrs, sign: int, threshold: float, dead: int) -> float:
    """Mean count, over the surrogates, of events beyond *threshold* SDs.

    Counted at the threshold itself, not once at a low one and then cut:
    :func:`_extrema` merges a peak into the candidate before it when they are
    closer than the dead time, and at a low threshold noise has a candidate
    every few samples, so nearly every event would merge away.
    """
    return sum(len(_extrema(sign * zs, threshold, dead)) for zs in surrs) / len(surrs)


def _row_seed(seed: int, row: int) -> int:
    return int(np.random.SeedSequence([seed, row]).generate_state(1)[0])


def electrode_noise_test(trace: np.ndarray, fs: float, units: list[np.ndarray], *,
                         settings: NoiseTestSettings = NoiseTestSettings(),
                         seed: int = 0) -> list[dict]:
    """Score every unit on one electrode.

    *trace* is the electrode's raw voltage over the analysis window (µV);
    *units* holds each unit's spike times in seconds **from the start of that
    window**. Returns one dict of :data:`COLUMNS` per unit (NaN where a unit
    has too few spikes to score).
    """
    s = settings
    prep = _prepare(trace, fs, s, seed)
    nan_row = {c: np.nan for c in COLUMNS}
    if prep is None:
        return [dict(nan_row, raw_n_spikes=0) for _ in units]
    z, sigma, surrs = prep
    n = len(z)
    T = n / fs
    dead = _samples(s.dead_ms, fs)

    out = []
    for train in units:
        got = _spike_sizes(z, fs, train, s)
        if got is None:
            idx = _spike_index(train, fs, n, _samples(s.align_ms, fs))
            out.append(dict(nan_row, raw_n_spikes=len(idx)))
            continue
        idx, sign, amps = got
        a_med = float(np.median(amps))
        k_unit = int(np.count_nonzero(amps >= a_med))
        k_noise = _noise_events(surrs, sign, a_med, dead)
        noise_rate = k_noise / T
        unit_rate = k_unit / T
        out.append({
            "raw_n_spikes": len(idx), "raw_sign": sign,
            "raw_amp_uv": a_med * sigma, "raw_snr": a_med,
            "noise_rate_hz": noise_rate, "unit_rate_hz": unit_rate,
            "noise_fraction": noise_rate / unit_rate if unit_rate > 0 else np.nan,
            "noise_p": float(poisson.sf(k_unit - 1, k_noise)),
        })
    return out


def unit_noise_metrics(traces: np.ndarray, row_of_unit: np.ndarray, spike_trains: list,
                       fs: float, *, start_s: float = 0.0,
                       settings: NoiseTestSettings = NoiseTestSettings(),
                       seed: int = 0, n_threads: int | None = None):
    """The test for every unit: a DataFrame of :data:`COLUMNS`, one row per unit.

    *traces* is ``(n_rows, n_samples)`` µV, the analysis window starting at
    ``start_s`` seconds into the recording; ``row_of_unit[i]`` is the row of
    *traces* holding unit *i*'s peak electrode (-1: not available, NaN row).
    Spike times are seconds into the recording.
    """
    import pandas as pd

    row_of_unit = np.asarray(row_of_unit, dtype=np.int64)
    n_units = len(spike_trains)
    rows: list[dict | None] = [None] * n_units
    by_row: dict[int, list[int]] = {}
    for u, r in enumerate(row_of_unit):
        if r >= 0:
            by_row.setdefault(int(r), []).append(u)
    T = traces.shape[1] / fs

    def one(r: int):
        us = by_row[r]
        trains = []
        for u in us:
            t = np.asarray(spike_trains[u], dtype=float) - start_s
            trains.append(t[(t >= 0) & (t < T)])
        return us, electrode_noise_test(traces[r], fs, trains, settings=settings,
                                        seed=_row_seed(seed, r))

    workers = max(1, min(len(by_row), n_threads or _default_threads()))
    if workers == 1:
        results = [one(r) for r in by_row]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, list(by_row)))
    for us, scored in results:
        for u, d in zip(us, scored):
            rows[u] = d
    blank = {c: np.nan for c in COLUMNS}
    return pd.DataFrame([r if r is not None else blank for r in rows], columns=list(COLUMNS))


def _default_threads() -> int:
    try:
        from meanap.pipeline.parallel import compute_threads

        return min(8, compute_threads())
    except Exception:  # noqa: BLE001
        return 1


def maxwell_unit_noise(raw_path: str | Path, imp, *, max_seconds: float | None = DEFAULT_MAX_SECONDS,
                       start_s: float = 0.0, seed: int = 0, common_median: bool = False,
                       settings: NoiseTestSettings = NoiseTestSettings(),
                       examples: bool = False, log=print):
    """:func:`unit_noise_metrics` for an imported sorting of a MaxWell recording.

    Units are matched to the raw file's routed rows by electrode number, so
    this works whatever row order the sorter's electrode table had. A unit
    whose electrode is not in the raw file (a sort of a different routing)
    gets a NaN row — which is also what protects against a raw file that is
    not the one that was sorted, as long as the routings differ.

    With ``examples``, returns ``(table, examples)``: the
    :func:`unit_example` of each unit :func:`choose_examples` picks.
    """
    from meanap.pipeline.maxwell import read_maxwell_meta, read_maxwell_rows

    meta = read_maxwell_meta(raw_path)
    if abs(meta.fs - float(imp.fs)) > 1e-6 * meta.fs:
        raise ValueError(f"sampling rates differ: raw {meta.fs} Hz, sorting {imp.fs} Hz")
    row_in_raw = {int(e): i for i, e in enumerate(meta.electrodes)}
    unit_elec = np.asarray(imp.electrodes.ids)[np.asarray(imp.peak_index, dtype=np.int64)]
    raw_rows = np.array([row_in_raw.get(int(e), -1) for e in unit_elec], dtype=np.int64)
    needed = np.unique(raw_rows[raw_rows >= 0])
    if len(needed) == 0:
        raise ValueError("none of the units' electrodes are in the raw file")
    start = int(round(start_s * meta.fs))
    n = None if max_seconds is None else int(round(max_seconds * meta.fs))
    log(f"      reading {len(needed)} electrode(s) of {meta.path.name} "
        f"({'all' if n is None else f'{min(n, meta.n_frames - start) / meta.fs:.0f} s'})…")
    traces, _ = read_maxwell_rows(raw_path, needed, start_frame=start, n_frames=n, meta=meta,
                                  common_median=common_median)
    local = np.full(len(raw_rows), -1, dtype=np.int64)
    pos = {int(r): i for i, r in enumerate(needed)}
    for u, r in enumerate(raw_rows):
        if r >= 0:
            local[u] = pos[int(r)]
    trains = list(imp.spike_trains)
    df = unit_noise_metrics(traces, local, trains, meta.fs,
                            start_s=start / meta.fs, seed=seed, settings=settings)
    if not examples:
        return df
    ids = [str(u) for u in imp.sorter_unit_ids]
    picked = []
    for u in choose_examples(df):
        t = np.asarray(trains[u], dtype=float) - start / meta.fs
        t = t[(t >= 0) & (t < traces.shape[1] / meta.fs)]
        ex = unit_example(traces[local[u]], meta.fs, t, settings=settings,
                          seed=_row_seed(seed, int(local[u])))
        if ex is not None:
            ex.update(unit_id=ids[u], electrode=int(unit_elec[u]),
                      noise_fraction=float(df.noise_fraction[u]))
            picked.append(ex)
    return df, picked


# ── Examples, for the figure ──────────────────────────────────────────────────

#: Snippet window drawn around each spike, ms.
SNIPPET_MS = (-1.0, 2.0)
#: How many snippets an example keeps (a random choice of the unit's spikes).
N_SNIPPETS = 60
#: Thresholds the rate curves are evaluated at.
N_THRESHOLDS = 40


def choose_examples(df, max_noise_fraction: float = 0.5) -> list[int]:
    """Up to three units that show what the test does, by row of *df*:

    the clearest (highest raw SNR), the one closest to the cutoff, and a
    typical noise-like one (the median ``noise_fraction`` of those flagged).
    """
    nf = np.asarray(df["noise_fraction"], dtype=float)
    snr = np.asarray(df["raw_snr"], dtype=float)
    scored = np.flatnonzero(np.isfinite(nf))
    if len(scored) == 0:
        return []
    picks = [int(scored[np.argmax(snr[scored])])]
    pos = scored[nf[scored] > 0]
    if len(pos):
        picks.append(int(pos[np.argmin(np.abs(np.log10(nf[pos] / max_noise_fraction)))]))
    flagged = scored[nf[scored] >= max_noise_fraction]
    if len(flagged):
        order = flagged[np.argsort(nf[flagged])]
        picks.append(int(order[len(order) // 2]))
    return list(dict.fromkeys(picks))


def unit_example(trace, fs: float, train, *, settings: NoiseTestSettings = NoiseTestSettings(),
                 seed: int = 0, n_snippets: int = N_SNIPPETS) -> dict | None:
    """Everything the example figure draws for one unit, or ``None``.

    *train* is in seconds from the start of *trace*. Rates are per second;
    sizes and snippets are in noise SDs (``sigma_uv`` converts).
    """
    s = settings
    prep = _prepare(trace, fs, s, seed)
    if prep is None:
        return None
    z, sigma, surrs = prep
    got = _spike_sizes(z, fs, train, s)
    if got is None:
        return None
    idx, sign, amps = got
    T = len(z) / fs
    a_med = float(np.median(amps))
    a0, a1 = (int(round(m * 1e-3 * fs)) for m in SNIPPET_MS)
    ok = idx[(idx + a0 >= 0) & (idx + a1 < len(z))]
    rng = np.random.default_rng(seed)
    pick = np.sort(rng.choice(ok, size=min(n_snippets, len(ok)), replace=False))
    offsets = np.arange(a0, a1 + 1)
    snippets = z[pick[:, None] + offsets[None, :]].astype(np.float32)
    mean = z[ok[:, None] + offsets[None, :]].mean(axis=0)
    top = max(float(np.percentile(amps, 99)), 1.5 * a_med, 4.0)
    ks = np.linspace(1.5, top, N_THRESHOLDS)
    dead = _samples(s.dead_ms, fs)
    unit_rate = np.array([np.count_nonzero(amps >= k) for k in ks]) / T
    noise_rate = np.array([_noise_events(surrs, sign, k, dead) for k in ks]) / T
    return {"t_ms": offsets / fs * 1e3, "snippets": snippets, "mean": mean, "sign": sign,
            "median_size": a_med, "sigma_uv": sigma, "thresholds": ks,
            "unit_rate": unit_rate, "noise_rate": noise_rate, "n_spikes": len(idx),
            "window_s": T}


EXAMPLES_SUFFIX = "_unit_noise_examples.npz"
FIGURE_NAME = "5_UnitNoiseExamples"


def save_examples(path: str | Path, examples: list[dict]) -> Path:
    """Write :func:`unit_example` dicts to one ``.npz`` (``e<i>_<field>`` keys)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"n": np.array(len(examples))}
    for i, ex in enumerate(examples):
        for key, value in ex.items():
            arrays[f"e{i}_{key}"] = np.asarray(value)
    np.savez_compressed(path, **arrays)
    return path


def load_examples(path: str | Path) -> list[dict]:
    with np.load(path, allow_pickle=False) as z:
        out = []
        for i in range(int(z["n"])):
            ex = {}
            for key in z.files:
                if key.startswith(f"e{i}_"):
                    v = z[key]
                    ex[key[len(f"e{i}_"):]] = v.item() if v.ndim == 0 else v
            out.append(ex)
    return out


def unit_examples_chart(examples: list[dict], labels: dict | None = None, title: str = "",
                        max_noise_fraction: float = 0.5):
    """Each example unit in a column: its raw spikes over the noise, then how
    often spikes, and noise, reach each size."""
    from meanap.native.chart import Chart, Legend, LegendItem, Line, Panel, Rule, rgba
    from meanap.pipeline.quality_maps import LABEL_COLOURS

    labels = labels or {}
    panels = []
    for c, ex in enumerate(examples):
        uid = str(ex["unit_id"])
        lab = labels.get(uid, "")
        colour = LABEL_COLOURS.get(lab, "#1f4e79")
        t = np.asarray(ex["t_ms"], dtype=float)
        sn = np.asarray(ex["snippets"], dtype=float)
        xs = np.concatenate([np.append(t, np.nan) for _ in range(len(sn))])
        ys = np.concatenate([np.append(row, np.nan) for row in sn])
        size = float(ex["median_size"])
        sign = int(ex["sign"])
        nf = float(ex["noise_fraction"])
        verdict = ("cannot be told from noise" if nf >= max_noise_fraction
                   else "stands out from noise")
        head = (f"unit {uid}" + (f" ({lab})" if lab else "") + f", electrode {int(ex['electrode'])}"
                f"\nmedian spike {size:.1f} SD = {size * float(ex['sigma_uv']):.0f} µV: {verdict}")
        lim = max(6.0, float(np.nanmax(np.abs(sn))) * 1.05) if sn.size else 6.0
        panels.append(Panel(
            cell=(0, c), title=head, xlabel="time from spike (ms)",
            ylabel="noise SDs" if c == 0 else "", ylim=(-lim, lim), grid="", spines=True,
            title_size=9, label_size=8,
            marks=[Line(xs, ys, colour=rgba("#9a9a9a", 0.35), width=0.6),
                   Line(t, np.asarray(ex["mean"], dtype=float), colour=rgba(colour), width=2.0,
                        key="mean"),
                   Rule(sign * size, axis="y", colour=rgba("#d62728"), width=1.0, dash="--")]))
        ks = np.asarray(ex["thresholds"], dtype=float)
        ur = np.asarray(ex["unit_rate"], dtype=float)
        nr = np.asarray(ex["noise_rate"], dtype=float)
        ur = np.where(ur > 0, ur, np.nan)
        nr = np.where(nr > 0, nr, np.nan)
        ratio = ("noise makes none that large" if not np.isfinite(nf) or nf == 0
                 else f"noise makes {nf:.2g}× as many")
        panels.append(Panel(
            cell=(1, c), title=f"at the median size: {ratio}",
            xlabel=f"spike size, {'negative' if sign < 0 else 'positive'}-going (noise SDs)",
            ylabel="events per second this large or larger" if c == 0 else "",
            ylog=True, grid="y", spines=True, title_size=9, label_size=8,
            marks=[Line(ks, nr, colour=rgba("#6e6e6e"), width=1.6, dash="--", key="noise",
                        hover=[f"noise: {v:.3g}/s ≥ {k:.1f} SD" for k, v in zip(ks, nr)]),
                   Line(ks, ur, colour=rgba(colour), width=2.0, key="unit",
                        hover=[f"unit: {v:.3g}/s ≥ {k:.1f} SD" for k, v in zip(ks, ur)]),
                   Rule(size, axis="x", colour=rgba("#d62728"), width=1.0, dash="--")]))
    if panels:
        panels[1].legend = Legend([
            LegendItem("the unit's spikes (in its label's colour)", rgba("#333333"), key="unit"),
            LegendItem("its electrode's noise (phases scrambled)", rgba("#6e6e6e"), key="noise"),
            LegendItem("the unit's median spike size", rgba("#d62728"))], loc="best", size=8)
    n = max(len(examples), 1)
    head = (title + "\n" if title else "") + (
        "Is each unit more than its electrode's noise? Top: 60 of its raw spikes (grey) and "
        "their mean. Bottom: how often its spikes, and the noise alone, reach each size.")
    return Chart(panels, size=(4.4 * n + 0.6, 7.4), grid=(2, n), title=head, title_size=10)


def draw_saved_unit_examples(root: str | Path, rec_name: str, out_path: str | Path):
    """Draw *rec_name*'s example figure from its saved examples, or ``None``."""
    import pandas as pd

    from meanap.native.chart_paint import save_chart
    from meanap.pipeline.unit_quality import UNIT_QUALITY_CSV, UNIT_QUALITY_DIR

    base = Path(root) / UNIT_QUALITY_DIR
    ex_path = base / f"{rec_name}{EXAMPLES_SUFFIX}"
    if not ex_path.exists():
        return None
    examples = load_examples(ex_path)
    if not examples:
        return None
    labels = {}
    table = base / f"{rec_name}{UNIT_QUALITY_CSV}"
    if table.exists():
        df = pd.read_csv(table, dtype={"unit_id": str})
        labels = dict(zip(df["unit_id"].astype(str), df["label"].astype(str)))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_chart(unit_examples_chart(examples, labels, title=rec_name), out_path)
    return out_path
