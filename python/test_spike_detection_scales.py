"""Wavelet scale selection across sampling rates.

The expected scales are MATLAB ground truth, produced by replicating
``determine_scales()`` from ``Functions/WATERS-master/detectSpikesWavelet.m``
verbatim under MATLAB R2024b with ``Wid = [0.4 0.8]``, ``Ns = 5``,
``wname = 'bior1.5'``.

The 10 kHz row is the interesting one: MATLAB returns ``[NaN 2 3 4 5]`` there
and then dies with ``MATLAB:colon:nonFiniteEndpoint``, because 0.4 ms is
*exactly* the narrowest width 10 kHz can express and ``determine_scales``
nudges its lookup table 1e-15 upward to keep it monotonic. We take the scale
MATLAB's own interpolation would have given without that nudge.
"""

from __future__ import annotations

import io
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from meanap.pipeline.spike_detection import _determine_scales  # noqa: E402

WID = (0.4, 0.8)
NS = 5
WNAME = "bior1.5"

# fs (Hz) -> (expected scales, note)
CASES = {
    25000.0: ([7, 8, 10, 12, 14], "MATLAB exact"),
    12500.0: ([2, 3, 4, 6, 7], "MATLAB exact"),
    10000.0: ([2, 2, 3, 4, 5], "MATLAB gives [NaN 2 3 4 5] then crashes"),
}


def main() -> int:
    fail = 0
    for fs, (expected, note) in CASES.items():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = _determine_scales(WNAME, WID, fs, NS).tolist()
        status = "ok " if got == expected else "FAIL"
        fail += got != expected
        print(f"{status} fs={fs:>7.0f}  scales={got}  expected={expected}  ({note})")

    # A rate that genuinely cannot express the requested widths must adjust and
    # carry on rather than raise — 0.4 ms is below anything 5 kHz can resolve.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        got = _determine_scales(WNAME, WID, 5000.0, NS).tolist()
    notice = buf.getvalue().strip()
    if not got or len(got) != NS:
        print(f"FAIL fs=5000 returned {got}"); fail += 1
    else:
        print(f"ok  fs=   5000  scales={got}  (clamped, no exception)")

    # The notice is emitted once per distinct condition, not once per channel.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for _ in range(60):
            _determine_scales(WNAME, WID, 10000.0, NS)
    repeats = len([ln for ln in buf.getvalue().splitlines() if ln.strip()])
    if repeats > 1:
        print(f"FAIL notice repeated {repeats}x across 60 channel-equivalent calls"); fail += 1
    else:
        print(f"ok  notice printed {repeats}x across 60 calls (deduplicated)")

    print(f"\nFAILURES: {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
