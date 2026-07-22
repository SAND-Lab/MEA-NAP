"""Parity test: Python ssvkernel adaptive KDE vs MATLAB ssvkernel.m.

Ground truth from ``python/test_fixtures/gen_ssvkernel_reference.m`` (MATLAB run
on three fixed PSTH-sample inputs — many/medium/few spikes). ssvkernel is
deterministic for the 3-output call MEA-NAP uses; parity is exact to ~1e-13.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import scipy.io as sio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.stim.ssvkernel import ssvkernel  # noqa: E402

FIX = Path(__file__).resolve().parent / "test_fixtures"

RTOL = 1e-9


def main() -> int:
    inp = sio.loadmat(FIX / "ssvkernel_inputs.mat")
    ref = sio.loadmat(FIX / "ssvkernel_reference.mat")
    tin = inp["tin"].ravel()
    fails = 0
    for lab in ["big", "mid", "small"]:
        x = inp[f"x_{lab}"].ravel()
        y, t, optw = ssvkernel(x, tin)
        yml = ref[f"y_{lab}"].ravel()
        oml = ref[f"optw_{lab}"].ravel()
        ry = np.max(np.abs(y - yml)) / (np.max(np.abs(yml)) + 1e-30)
        ro = np.max(np.abs(optw - oml)) / (np.max(np.abs(oml)) + 1e-30)
        ok = ry < 1e-9 and ro < 1e-9
        fails += 0 if ok else 1
        print(f"  {lab:6s} n={x.size:4d}  y rel|Δ|={ry:.2e}  optw rel|Δ|={ro:.2e}  "
              f"{'OK' if ok else 'FAIL'}")
    print("PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
