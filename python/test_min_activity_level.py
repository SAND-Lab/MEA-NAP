"""What counts as an active electrode, and where that is set (issue #181).

At a threshold of 0, ``rate >= 0`` holds for a silent electrode, so every
electrode on the array counted as active. The default now matches the MATLAB
app, and the setting appears on two tabs that must never disagree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline.firing_rates import firing_rates_bursts  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


DURATION_S = 600.0
N_SILENT, N_ONE_SPIKE, N_ACTIVE = 4, 4, 8
N_CHANNELS = N_SILENT + N_ONE_SPIKE + N_ACTIVE


def spike_trains() -> dict[int, np.ndarray]:
    """Silent channels, one-spike channels (0.0017 Hz) and ~1 Hz channels."""
    rng = np.random.default_rng(0)
    trains: dict[int, np.ndarray] = {}
    for ch in range(N_CHANNELS):
        if ch < N_SILENT:
            trains[ch] = np.array([])
        elif ch < N_SILENT + N_ONE_SPIKE:
            trains[ch] = rng.uniform(0, DURATION_S, 1)
        else:
            trains[ch] = np.sort(rng.uniform(0, DURATION_S, int(DURATION_S)))
    return trains


def activity(params: Params) -> dict:
    return firing_rates_bursts(spike_trains(), N_CHANNELS, 12500, DURATION_S,
                               params)


print("\nThe default")

check("matches the MATLAB app's 0.01 spikes/s",
      Params().min_activity_level == 0.01, str(Params().min_activity_level))

default = activity(Params())
check("only the electrodes above it count as active",
      default["numActiveElec"] == N_ACTIVE, str(default["numActiveElec"]))
check("FRactive is NaN for the silent and one-spike electrodes",
      np.isnan(default["FRactive"][:N_SILENT + N_ONE_SPIKE]).all()
      and np.isfinite(default["FRactive"][N_SILENT + N_ONE_SPIKE:]).all(), "")
check("a threshold of 0 still counts every electrode, if asked for",
      activity(Params(min_activity_level=0.0))["numActiveElec"] == N_CHANNELS, "")


print("\nThe two fields in the window")

window = MainWindow("meanap")
spike = window._spike_panel.min_activity_level
connectivity = window._connectivity_panel.min_activity_level

check("both start on the default",
      spike.value() == connectivity.value() == Params.min_activity_level,
      f"{spike.value()} / {connectivity.value()}")

spike.setValue(0.25)
check("an edit on Spike detection reaches Connectivity",
      connectivity.value() == 0.25, str(connectivity.value()))
check("and reaches the run",
      window._collect_params().min_activity_level == 0.25,
      str(window._collect_params().min_activity_level))

connectivity.setValue(0.5)
check("an edit on Connectivity reaches Spike detection",
      spike.value() == 0.5, str(spike.value()))
check("and reaches the run",
      window._collect_params().min_activity_level == 0.5,
      str(window._collect_params().min_activity_level))

window._load_params(Params(min_activity_level=0.0))
check("a parameter file's explicit 0 is kept on both",
      spike.value() == connectivity.value() == 0.0,
      f"{spike.value()} / {connectivity.value()}")
check("and reaches the run",
      window._collect_params().min_activity_level == 0.0,
      str(window._collect_params().min_activity_level))

window._apply_mode("catnap")
connectivity.setValue(0.05)
check("CAT-NAP, with no Spike detection tab, still runs the visible value",
      window._collect_params().min_activity_level == 0.05,
      str(window._collect_params().min_activity_level))
window.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All min activity level checks passed.")
