"""Cutts & Eglen's necessary properties, run on pairwise correlation measures.

Cutts & Eglen (2014, *J Neurosci* 34:14288, Table 2) list what a measure of
spike-time correlation must do before correlations can be compared across
recordings whose other statistics differ:

N1  symmetric: C(A, B) = C(B, A);
N2  robust to firing rate: doubling both rates with the correlation
    structure kept should leave it unchanged;
N3  robust to the amount of data (recording length);
N4  bounded: +1 for identical trains, 0 for no correlation, −1 for
    anti-correlation;
N5  robust to Δt: small changes of the window introduce no artefacts;
N6  tells anti-correlation from no correlation.

They tested each by line search on synthetic pairs. Their two main models
are reproduced here: **Poisson spiking** (each train Poisson, a share of
spikes shared with the other, Table 1: rates 0.01–5 Hz) and **Poisson
bursting** (a master train of burst centres, copied to the second with
probability *p* and offset, each burst Poisson(*N*) spikes spread over σ).
For N6 they used integrate-and-fire and map-based models of out-of-phase
firing; here the stand-in is two Poisson trains that fire in alternating
half-cycles, which has the same property (each is silent while the other
fires) without their extra parameters.

Measures tested: STTC (Cutts & Eglen's proposal), STTC as MEA-NAP stores it
(negative values set to 0 by ``get_sttc``), the correlation index (Wong et
al. 1993, the measure the paper set out to replace), the spike count
correlation (Pearson's r of counts in bins Δt wide, as in the paper), the
Schreiber et al. (2003) similarity and the normalised cross-correlation peak
of Pasquale et al. (2008) — the last two from :mod:`meanap.sim.estimators`.

Verdicts use tolerances that are settings, not truths: the paper judged
dependence by eye from line-search plots, so each test reports the number it
judged by alongside the pass/fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "PAIR_MEASURES", "PROPERTIES", "poisson_pair", "burst_pair", "antiphase_pair",
    "pair_value", "PairTestSettings", "PropertyResult", "run_property", "run_all",
]

PAIR_MEASURES = {
    "sttc": "STTC",
    "sttc_stored": "STTC as MEA-NAP stores it (< 0 → 0)",
    "corr_index": "Correlation index (Wong 1993)",
    "count_corr": "Pearson correlation of counts",
    "schreiber": "Schreiber similarity",
    "cch": "Cross-correlation peak (Pasquale)",
}

PROPERTIES = {
    "N1": "Symmetric",
    "N2": "Robust to firing rate",
    "N3": "Robust to recording length",
    "N4": "Bounded: 1 identical, 0 independent",
    "N5": "Robust to small changes of Δt",
    "N6": "Tells anti-correlation from none",
}


# ── models ────────────────────────────────────────────────────────────────────


def _poisson(rate: float, T: float, rng) -> np.ndarray:
    if rate <= 0:
        return np.empty(0)
    return rng.uniform(0, T, rng.poisson(rate * T))


def poisson_pair(rate_a: float, rate_b: float, rate_sync: float, T: float, rng,
                 jitter_s: float = 0.002) -> tuple[np.ndarray, np.ndarray]:
    """Cutts & Eglen's Poisson spiking model: rate ``rate_sync`` of each train's
    spikes is shared (jittered by ``jitter_s``), the rest independent."""
    rs = min(rate_sync, rate_a, rate_b)
    s = _poisson(rs, T, rng)
    a = np.concatenate([_poisson(rate_a - rs, T, rng), s])
    b = np.concatenate([_poisson(rate_b - rs, T, rng), s + rng.normal(0, jitter_s, s.size)])
    return np.sort(a[(a >= 0) & (a < T)]), np.sort(b[(b >= 0) & (b < T)])


def burst_pair(burst_rate: float, p: float, offset_s: float, n_spikes: float,
               sigma_s: float, T: float, rng) -> tuple[np.ndarray, np.ndarray]:
    """Cutts & Eglen's Poisson burst model (uniform offsets and spike positions)."""
    ca = _poisson(burst_rate, T, rng)
    keep = rng.random(ca.size) < p
    cb = ca[keep] + rng.uniform(-offset_s / 2, offset_s / 2, keep.sum())

    def spikes(centres):
        k = rng.poisson(n_spikes, centres.size)
        c = np.repeat(centres, k)
        return c + rng.uniform(-sigma_s / 2, sigma_s / 2, c.size)

    a, b = spikes(ca), spikes(cb)
    return np.sort(a[(a >= 0) & (a < T)]), np.sort(b[(b >= 0) & (b < T)])


def antiphase_pair(rate: float, period_s: float, T: float, rng
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Two trains firing in alternating half-cycles: anti-correlated by construction."""
    a, b = _poisson(2 * rate, T, rng), _poisson(2 * rate, T, rng)
    phase = lambda t: (t % period_s) < period_s / 2   # noqa: E731
    return np.sort(a[phase(a)]), np.sort(b[~phase(b)])


# ── measures ──────────────────────────────────────────────────────────────────


def _n_close(a: np.ndarray, b: np.ndarray, dt: float) -> int:
    """Number of (a, b) spike pairs within ±dt."""
    if a.size == 0 or b.size == 0:
        return 0
    return int((np.searchsorted(b, a + dt, "right") - np.searchsorted(b, a - dt, "left")).sum())


def pair_value(measure: str, a: np.ndarray, b: np.ndarray, dt: float, T: float) -> float:
    from meanap.pipeline.sttc import sttc_pair

    if measure in ("sttc", "sttc_stored"):
        v = sttc_pair(a, b, dt, 0.0, T)
        if measure == "sttc_stored":   # get_sttc: adjM(adjM<0)=0; adjM(isnan)=0
            v = 0.0 if not np.isfinite(v) or v < 0 else v
        return float(v)
    if measure == "corr_index":
        if a.size == 0 or b.size == 0:
            return np.nan
        return _n_close(a, b, dt) * T / (a.size * b.size * 2 * dt)
    if measure in ("schreiber", "cch"):
        from meanap.sim.estimators import estimate

        return float(estimate(measure, [a, b], T, dt * 1000.0)[0, 1])
    if measure == "count_corr":
        edges = np.arange(0.0, T + dt, dt)
        ca, cb = np.histogram(a, edges)[0], np.histogram(b, edges)[0]
        if ca.std() == 0 or cb.std() == 0:
            return np.nan
        return float(np.corrcoef(ca, cb)[0, 1])
    raise ValueError(f"Unknown pair measure {measure!r}")


# ── tests ─────────────────────────────────────────────────────────────────────


@dataclass
class PairTestSettings:
    dt_ms: float = 10.0
    duration_s: float = 600.0
    repeats: int = 10
    share_sync: float = 0.3          # share of spikes synchronous (Poisson model)
    rate_hz: float = 2.0
    #: Largest relative change across a line search that still counts as robust.
    tolerance: float = 0.25
    seed: int = 1


@dataclass
class PropertyResult:
    prop: str
    measure: str
    passed: bool | None
    detail: str
    #: Line-search curves for the figure: name → (x, mean, sd).
    curves: dict = field(default_factory=dict)
    xlabel: str = ""
    xlog: bool = False


def _line(measure, xs, make, dt_of, T_of, reps, rng):
    """Mean and SD of *measure* over *reps* draws at each x."""
    mean, sd = [], []
    for x in xs:
        v = [pair_value(measure, *make(x, rng), dt_of(x), T_of(x)) for _ in range(reps)]
        v = np.asarray(v, float)
        mean.append(np.nanmean(v) if np.isfinite(v).any() else np.nan)
        sd.append(np.nanstd(v) if np.isfinite(v).any() else np.nan)
    return np.asarray(xs, float), np.asarray(mean), np.asarray(sd)


def _relative_change(mean: np.ndarray) -> float:
    m = mean[np.isfinite(mean)]
    if m.size < 2:
        return np.nan
    scale = np.mean(np.abs(m))
    return float((m.max() - m.min()) / scale) if scale > 0 else 0.0


def run_property(prop: str, measure: str, s: PairTestSettings | None = None) -> PropertyResult:
    s = s or PairTestSettings()
    rng = np.random.default_rng([s.seed, sum(map(ord, prop + measure))])
    dt, T, reps = s.dt_ms / 1000.0, s.duration_s, int(s.repeats)
    const_dt, const_T = (lambda x: dt), (lambda x: T)

    if prop == "N1":
        worst = 0.0
        for _ in range(max(reps, 5)):
            ra, rb = rng.uniform(0.2, 5), rng.uniform(0.2, 5)
            a, b = poisson_pair(ra, rb, s.share_sync * min(ra, rb), T, rng)
            ab, ba = pair_value(measure, a, b, dt, T), pair_value(measure, b, a, dt, T)
            if np.isfinite(ab) and np.isfinite(ba):
                worst = max(worst, abs(ab - ba))
            a, b = burst_pair(0.1, 0.7, 0.5, 6, 0.5, T, rng)
            ab, ba = pair_value(measure, a, b, dt, T), pair_value(measure, b, a, dt, T)
            if np.isfinite(ab) and np.isfinite(ba):
                worst = max(worst, abs(ab - ba))
        return PropertyResult(prop, measure, worst < 1e-9,
                              f"largest |C(A,B) − C(B,A)| = {worst:.2g}")

    if prop == "N2":
        rates = np.geomspace(0.2, 5.0, 7)
        x, m, sd = _line(measure, rates, lambda r, g: poisson_pair(r, r, s.share_sync * r, T, g),
                         const_dt, const_T, reps, rng)
        # Bursting: more bursts, each the same (Table 1's burst-rate range).
        lam = np.geomspace(0.01, 0.2, 6)
        xb, mb, sdb = _line(measure, lam, lambda b, g: burst_pair(b, 0.7, 0.5, 6, 0.5, T, g),
                            const_dt, const_T, reps, rng)
        rel, relb = _relative_change(m), _relative_change(mb)
        worst = np.nanmax([rel, relb])
        return PropertyResult(
            prop, measure, bool(worst <= s.tolerance) if np.isfinite(worst) else None,
            f"changes {rel:.0%} over 0.2–5 Hz (Poisson spiking), {relb:.0%} over "
            f"0.01–0.2 bursts/s (bursting)",
            {"Poisson spiking": (x, m, sd), "Bursting (x = bursts/s × 25)": (xb * 25, mb, sdb)},
            "Firing rate (Hz)", True)

    if prop == "N3":
        Ts = np.geomspace(10, 3000, 7)
        x, m, sd = _line(measure, Ts, lambda t, g: poisson_pair(s.rate_hz, s.rate_hz,
                                                                 s.share_sync * s.rate_hz, t, g),
                         const_dt, lambda t: t, reps, rng)
        rel = _relative_change(m)
        return PropertyResult(prop, measure, bool(rel <= s.tolerance) if np.isfinite(rel) else None,
                              f"mean changes {rel:.0%} over 10–3000 s",
                              {"Poisson spiking": (x, m, sd)}, "Recording length (s)", True)

    if prop == "N4":
        # "0 for no correlation" must hold at every rate, not just on average.
        same, worst, worst_rate = [], 0.0, np.nan
        for r in np.geomspace(0.1, 5.0, 5):
            a = np.sort(_poisson(r, T, rng))
            same.append(pair_value(measure, a, a.copy(), dt, T))
            v = np.array([pair_value(measure, *poisson_pair(r, r, 0.0, T, rng), dt, T)
                          for _ in range(max(reps, 4))], float)
            v = v[np.isfinite(v)]
            if v.size:
                se = v.std() / np.sqrt(v.size)
                off = max(abs(v.mean()) - 3 * se, 0.0)    # beyond sampling noise
                if off > worst:
                    worst, worst_rate = off, r
        same = np.asarray(same, float)
        ok_same = np.all(np.abs(same - 1) < 0.01)
        ok_ind = worst < 0.03
        ok_bound = np.nanmax(same) <= 1 + 1e-9
        ind = ("independent → 0 at every rate" if ok_ind else
               f"independent trains at {worst_rate:.1f} Hz → {worst:+.2f} beyond noise")
        return PropertyResult(
            prop, measure, bool(ok_same and ok_ind and ok_bound),
            f"identical trains → {np.nanmin(same):.3g}–{np.nanmax(same):.3g}; {ind}")

    if prop == "N5":
        # Δt 10% apart: a measure may depend on Δt (STTC is meant to), but a
        # small change of Δt should give a small change of value, no jumps.
        dts = np.geomspace(0.005, 0.2, 40)
        x, m, sd = _line(measure, dts, lambda d, g: poisson_pair(s.rate_hz, s.rate_hz,
                                                                 s.share_sync * s.rate_hz, T, g),
                         lambda d: d, const_T, reps, rng)
        scale = np.maximum(np.abs(m[:-1]), np.abs(m[1:]))
        steps = np.abs(np.diff(m)) / np.where(scale > 0, scale, np.nan)
        worst = float(np.nanmax(steps)) if np.isfinite(steps).any() else np.nan
        return PropertyResult(prop, measure, bool(worst <= s.tolerance) if np.isfinite(worst) else None,
                              f"largest change for a 10% change of Δt (5–200 ms): {worst:.0%}",
                              {"Poisson spiking": (x * 1000, m, sd)}, "Δt (ms)", True)

    if prop == "N6":
        anti, none = [], []
        rate = max(s.rate_hz, 5.0)    # enough spikes that the dip is measurable
        for _ in range(reps):
            anti.append(pair_value(measure, *antiphase_pair(rate, 1.0, T, rng), dt, T))
            # Same alternating rate profile, but the two cycles independent of each other.
            a, _ = antiphase_pair(rate, 1.0, T, rng)
            b, _ = antiphase_pair(rate, 1.0, T, rng)
            b = (b + rng.uniform(0, T)) % T
            none.append(pair_value(measure, a, np.sort(b), dt, T))
        anti, none = np.asarray(anti, float), np.asarray(none, float)
        se = np.sqrt(np.nanvar(anti) / reps + np.nanvar(none) / reps)
        gap = np.nanmean(none) - np.nanmean(anti)
        passed = bool(gap > 3 * se and gap > 1e-6)
        return PropertyResult(prop, measure, passed,
                              f"anti-correlated → {np.nanmean(anti):+.3f}, "
                              f"uncorrelated → {np.nanmean(none):+.3f}")

    raise ValueError(f"Unknown property {prop!r}")


def run_all(s: PairTestSettings | None = None, measures=tuple(PAIR_MEASURES),
            props=tuple(PROPERTIES), progress=None) -> list[PropertyResult]:
    out = []
    total = len(measures) * len(props)
    for i, prop in enumerate(props):
        for j, m in enumerate(measures):
            out.append(run_property(prop, m, s))
            if progress is not None:
                progress(i * len(measures) + j + 1, total)
    return out
