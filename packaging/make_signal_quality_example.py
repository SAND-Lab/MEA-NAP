"""Draw docs/python/imgs/signal_quality_example.png from simulated data.

Coloured Gaussian noise (1/f, with line noise) on 32 electrodes; the top
recording also has spikes (12 noise SDs, 0.5-3 Hz) on 20 of them. Simulated so
the docs show no one's unpublished recordings.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from meanap.pipeline.signal_quality import assess_signal_quality, plot_signal_quality

FS = 20000.0
OUT = Path(__file__).resolve().parents[1] / "docs/python/imgs/signal_quality_example.png"


def noise(n_s, n_ch, rng):
    n = int(n_s * FS)
    f = np.fft.rfftfreq(n, 1 / FS)
    amp = 1 / np.sqrt(np.maximum(f, 50))
    amp[np.argmin(np.abs(f - 50))] *= 30
    x = np.fft.irfft(amp[:, None] * (rng.standard_normal((len(f), n_ch))
                                     + 1j * rng.standard_normal((len(f), n_ch))), n=n, axis=0)
    return (x / x.std(axis=0) * 6.0).astype(np.float32)          # ~6 uV noise


def add_spikes(x, rng):
    t = np.arange(-20, 40)
    wave = -np.exp(-(t / 4.0) ** 2) + 0.35 * np.exp(-((t - 14) / 8.0) ** 2)
    sd = np.median(np.abs(x), axis=0) / 0.6745
    for ch in range(20):
        rate = rng.uniform(0.5, 3.0)
        amp = rng.uniform(7, 14) * sd[ch]
        for s in rng.choice(np.arange(100, len(x) - 100), int(rate * len(x) / FS), replace=False):
            x[s - 20:s + 40, ch] += amp * wave
    return x


rng = np.random.default_rng(0)
spiky = add_spikes(noise(60, 32, rng), rng)
quiet = noise(60, 32, rng)
fig, axs = plt.subplots(2, 3, figsize=(13, 6.6), gridspec_kw={"width_ratios": [2.2, 1.2, 1.2]})
for x, title, ax in ((spiky, "Simulated: spikes on 20 of 32 electrodes", axs[0]),
                     (quiet, "Simulated: the same kind of noise, no spikes", axs[1])):
    plot_signal_quality(assess_signal_quality(x, FS, band=(300, 6000), max_seconds=None, units="uV"),
                        title=title, axes=ax)
    ax[1].set_xlim(3, 20); ax[1].set_ylim(1e-3, 3e3); ax[2].set_ylim(-0.3, 3.5)
fig.tight_layout()
fig.savefig(OUT, dpi=100)
print(OUT)
