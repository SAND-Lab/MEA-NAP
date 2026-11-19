"""Draw docs/python/imgs/signal_quality_example.png from simulated data.

Coloured Gaussian noise (1/f, with line noise) on 32 electrodes; the top
recording also has spikes (12 noise SDs, 0.5-3 Hz) on 20 of them. Simulated so
the docs show no one's unpublished recordings.
"""
import sys
from pathlib import Path

import numpy as np

from meanap.native.chart import Chart
from meanap.native.chart_paint import save_chart
from meanap.pipeline.figure_output import figure_dpi
from meanap.pipeline.signal_quality import assess_signal_quality, signal_quality_panels

FS = 20000.0
OUT = (Path(sys.argv[1]) if len(sys.argv) > 1 else
       Path(__file__).resolve().parents[1] / "docs/python/imgs/signal_quality_example.png")


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
panels = []
for row, (x, title) in enumerate(((spiky, "Simulated: spikes on 20 of 32 electrodes"),
                                  (quiet, "Simulated: the same kind of noise, no spikes"))):
    res = assess_signal_quality(x, FS, band=(300, 6000), max_seconds=None, units="uV")
    trace, hist, ranked = signal_quality_panels(res, row, title=title)
    # The same scales on both rows, so the two recordings compare at a glance.
    hist.xlim, hist.ylim, ranked.ylim = (3, 20), (1e-3, 3e3), (-0.3, 3.5)
    panels += [trace, hist, ranked]
with figure_dpi(110):              # docs size, not print size
    save_chart(Chart(panels, size=(13, 7.2), grid=(2, 3), widths=[2.2, 1.2, 1.2],
                     gap=(30.0, 30.0)), OUT)
print(OUT)
