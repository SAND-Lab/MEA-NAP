"""Draw docs/python/imgs/unit_quality_example.png from simulated units.

Sixty simulated units of a ten-minute MEA recording: clean neurons (a
refractory period, a Gaussian amplitude distribution, a clean spike), units
contaminated by a second neuron, units cut off at the detection threshold,
and noise clusters with no spike shape. Simulated so the docs show no one's
unpublished recordings.
"""
from pathlib import Path

import numpy as np

from meanap.pipeline.unit_quality import (
    UnitQualityInputs, compute_unit_quality, plot_unit_quality,
)

FS = 20000.0
DURATION = 600.0
OUT = Path(__file__).resolve().parents[1] / "docs/python/imgs/unit_quality_example.png"


def train(rate, rng, dead=0.0025):
    isi = rng.exponential(1.0 / rate, int(rate * DURATION * 1.5) + 10) + dead
    t = np.cumsum(isi)
    return t[t < DURATION]


def spike(depth, rng, n=60, trough=20):
    t = (np.arange(n) - trough) / FS * 1e3
    peak = depth * rng.uniform(0.2, 0.45)
    width = rng.uniform(0.09, 0.16)
    return -depth * np.exp(-(t / width) ** 2) + peak * np.exp(-((t - 0.45) / 0.25) ** 2)


def main() -> None:
    rng = np.random.default_rng(0)
    trains, waves, amps = [], [], []
    for k in range(60):
        kind = ("good", "contaminated", "cut off", "noise")[k % 4] if k % 4 else "good"
        rate = rng.lognormal(np.log(2.0), 0.7)
        depth = rng.uniform(30, 150)
        if kind == "contaminated":
            tr = np.sort(np.concatenate([train(rate, rng),
                                         rng.uniform(0, DURATION, int(rate * DURATION))]))
        else:
            tr = train(rate, rng)
        a = rng.normal(depth, 0.15 * depth, len(tr))
        if kind == "cut off":
            keep = a > depth * 1.05
            tr, a = tr[keep], a[keep]
        w = spike(depth, rng) if kind != "noise" else rng.normal(0, depth / 3, 60)
        trains.append(tr), waves.append(w), amps.append(np.abs(a))
    inputs = UnitQualityInputs(
        unit_ids=[f"u{k}" for k in range(60)], spike_trains=trains, duration_s=DURATION,
        fs=FS, amplitudes=amps, templates=np.stack(waves)[:, :, None], in_uv=True,
        noise_levels=np.array([6.0]))
    df = compute_unit_quality(inputs, "mea")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    plot_unit_quality(df, OUT, title="Simulated recording", thresholds="mea",
                      amplitude_in_uv=True)
    print(df.label.value_counts().to_dict(), "→", OUT)


if __name__ == "__main__":
    main()
