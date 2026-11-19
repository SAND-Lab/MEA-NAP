"""Line searches: move one dial, hold everything else, see what each metric does.

This is Cutts & Eglen's procedure (2014, *J Neurosci* 34:14288) carried from
pairs of trains up to whole networks. Each dial is either

* a **nuisance** — something that differs between cultures but is not
  connectivity (firing rate, recording length, bursts, slow states). A
  metric that should describe the network ought to stay put; or
* a **signal** — the planted connectivity itself (coupling strength,
  density, modularity). Here the metric ought to move.

The same seeds are used at every point of a sweep, so replicate *k* has the
same planted graph and the same random draws at every value: the curve shows
the dial's effect, not a new network at each point.

How far a metric moves is reported two ways:

``shift``     range of the per-value means, in units of the replicate-to-
              replicate SD (how many "culture-to-culture spreads" the dial
              moves it);
``relative``  the same range as a fraction of the metric's mean size.

Verdicts go by the shift: a nuisance is harmless below 1 SD and "followed"
from 3 SD (with one replicate there is no SD, so the relative change decides:
below 5% / from 25%). The relative change is reported beside it, because a
tiny but very consistent change can be many SDs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from meanap.sim.measure import DEFAULT_METRICS, EdgeSettings, measure
from meanap.sim.model import SimSpec, simulate

__all__ = [
    "Dial", "DIALS", "SCORECARD_DIALS", "sweep_values", "run_job", "jobs_for",
    "summarise", "score", "VERDICT_COLOURS",
]


@dataclass(frozen=True)
class Dial:
    field: str
    label: str
    low: float
    high: float
    kind: str            # "nuisance" | "signal"
    log: bool = False
    integer: bool = False
    unit: str = ""
    #: The Cutts & Eglen property this dial is the network version of, if any.
    criterion: str = ""
    #: Its role when correlation includes bursts (``None``: the same as ``kind``).
    coactivation_kind: str | None = None

    def kind_for(self, view: str = "coupling") -> str:
        if view == "coactivation" and self.coactivation_kind:
            return self.coactivation_kind
        return self.kind


DIALS: dict[str, Dial] = {d.field: d for d in (
    Dial("rate_hz", "Firing rate", 0.5, 8.0, "nuisance", log=True, unit="Hz",
         criterion="N2 (firing rate)"),
    Dial("duration_s", "Recording length", 30.0, 600.0, "nuisance", log=True, unit="s",
         criterion="N3 (amount of data)"),
    Dial("rate_spread", "Rate spread across nodes", 0.0, 1.2, "nuisance", unit="SD log"),
    Dial("burst_rate_hz", "Network bursts", 0.0, 0.3, "nuisance", unit="/s",
         criterion="co-activation, not coupling", coactivation_kind="signal"),
    Dial("burst_spikes", "Spikes per burst", 1.0, 12.0, "nuisance",
         coactivation_kind="signal"),
    Dial("burst_leak", "Bursts spilling across regions", 0.0, 1.0, "nuisance",
         coactivation_kind="signal", unit="share"),
    Dial("burst_cluster_size", "Burst clustering", 1.0, 10.0, "nuisance", unit="per episode"),
    Dial("state_amplitude", "Slow shared state", 0.0, 1.0, "nuisance", unit="log-SD"),
    Dial("n_nodes", "Number of nodes", 12, 60, "nuisance", integer=True),
    Dial("stim_spikes", "Stimulus response size", 0.0, 4.0, "nuisance", unit="spikes"),
    Dial("coupling", "Coupling strength", 0.0, 0.3, "signal", unit="P(spike)"),
    Dial("density", "Planted density", 0.05, 0.4, "signal"),
    Dial("within_module", "Share of edges in modules", 0.34, 1.0, "signal"),
    Dial("inhibitory_frac", "Share of inhibitory edges", 0.0, 0.8, "signal"),
    Dial("inhibition", "Inhibition strength", 0.0, 1.0, "signal", unit="P(delete)"),
)}

#: The preset run of the scorecard: each nuisance once, and two signals.
SCORECARD_DIALS = ("rate_hz", "duration_s", "rate_spread", "burst_rate_hz",
                   "state_amplitude", "coupling", "density")

#: Verdict → colour for the scorecard (the pipeline palette's traffic lights).
VERDICT_COLOURS = {"robust": "#2e8b57", "moves": "#e0a526", "follows": "#c0392b",
                   "responds": "#2e8b57", "weak": "#e0a526", "blind": "#c0392b",
                   "n/a": "#bbbbbb"}


def sweep_values(dial: Dial, low: float | None = None, high: float | None = None,
                 steps: int = 6) -> list[float]:
    lo = dial.low if low is None else float(low)
    hi = dial.high if high is None else float(high)
    steps = max(int(steps), 2)
    if dial.log and lo > 0 and hi > 0:
        vals = np.geomspace(lo, hi, steps)
    else:
        vals = np.linspace(lo, hi, steps)
    if dial.integer:
        vals = np.unique(np.round(vals).astype(int))
    return [float(v) for v in vals]


def jobs_for(base: SimSpec, dial: str, values, repeats: int, methods, settings: EdgeSettings,
             metrics=DEFAULT_METRICS) -> list[dict]:
    """One picklable task per (value, replicate)."""
    jobs = []
    for v in values:
        val = int(round(v)) if DIALS.get(dial) and DIALS[dial].integer else float(v)
        for rep in range(int(repeats)):
            spec = base.with_(**{dial: val, "seed": int(base.seed) * 1000 + rep})
            jobs.append({"spec": spec.to_dict(), "dial": dial, "value": float(v), "rep": rep,
                         "methods": list(methods), "settings": settings.to_dict(),
                         "metrics": list(metrics)})
    return jobs


def run_job(job: dict) -> list[dict]:
    """Simulate and measure one task; long-format rows. Module level for worker processes."""
    spec = SimSpec.from_dict(job["spec"])
    sim = simulate(spec)
    rates = sim.rates_hz()
    res = measure(sim, job["methods"], EdgeSettings(**job["settings"]), seed=spec.seed)
    rows = []
    base = {"dial": job["dial"], "value": job["value"], "rep": job["rep"]}
    for m, r in res.items():
        for k in job["metrics"]:
            rows.append({**base, "method": m, "metric": k, "val": r.metrics.get(k, np.nan)})
        rows.append({**base, "method": m, "metric": "meanRate",
                     "val": float(rates.mean()) if rates.size else np.nan})
    return rows


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Mean, SD and count per dial value, method and metric."""
    g = df.groupby(["dial", "value", "method", "metric"])["val"]
    return g.agg(mean="mean", sd="std", n="count").reset_index()


def _verdict(kind: str, shift: float, rel: float) -> str:
    if np.isnan(shift) and np.isnan(rel):
        return "n/a"
    if np.isfinite(shift) or np.isinf(shift):
        small, big = shift < 1.0, shift >= 3.0
    else:   # one replicate: no SD to scale by, so judge by the relative change
        small, big = rel < 0.05, rel >= 0.25
    if kind == "signal":
        return "blind" if small else ("responds" if big else "weak")
    return "robust" if small else ("follows" if big else "moves")


def score(df: pd.DataFrame, view: str = "coupling") -> pd.DataFrame:
    """How far each metric moves along each dial: one row per dial × method × metric.

    *view* decides which dials are signal (``Dial.kind_for``): with
    ``"coactivation"`` the burst dials are the thing to measure, not a nuisance.
    """
    from scipy.stats import spearmanr

    rows = []
    for (dial, method, metric), sub in df.groupby(["dial", "method", "metric"]):
        if metric == "meanRate":
            continue
        sub = sub[np.isfinite(sub["val"])]
        means = sub.groupby("value")["val"].mean()
        sds = sub.groupby("value")["val"].std()
        if len(means) < 2:
            shift = rel = rho = np.nan
        else:
            rng_ = float(means.max() - means.min())
            sd = float(np.sqrt(np.nanmean(sds.to_numpy() ** 2))) if sds.notna().any() else np.nan
            shift = rng_ / sd if np.isfinite(sd) and sd > 0 else (0.0 if rng_ == 0 else np.inf)
            scale = float(np.nanmean(np.abs(means)))
            rel = rng_ / scale if scale > 0 else (0.0 if rng_ == 0 else np.inf)
            rho = (float(spearmanr(sub["value"], sub["val"]).statistic)
                   if sub["val"].nunique() > 1 else 0.0)
        kind = DIALS[dial].kind_for(view) if dial in DIALS else "nuisance"
        rows.append({"dial": dial, "method": method, "metric": metric, "kind": kind,
                     "shift_sd": shift, "relative": rel, "rho": rho,
                     "verdict": _verdict(kind, shift, rel)})
    return pd.DataFrame(rows)
