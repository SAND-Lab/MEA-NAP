"""Surfacing the per-recording acquisition rate of a CAT-NAP run.

CAT-NAP reads each recording's frame rate out of its own ``ops.npy`` and
ignores the GUI's sampling-rate field — which is what MATLAB does too
(``suite2pToAdjm.m`` assigns ``Params.fs`` from the file). The consequence is
that a batch has no single sampling rate, ``params.json`` cannot record one,
and a run spanning culture preps routinely spans rates. That went unsaid
anywhere in the output, so a reader had no way to know the batch was mixed —
and frame rate covaries with prep, which can covary with genotype.

Checked here: the rate survives a save/load of the step-2 state, it reaches
disk as a column both recording-level tables carry, it reads back from either
of them, and the summary distinguishes a one-rate batch from a mixed one.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from meanap.catnap.rates import (  # noqa: E402
    RATE_COLUMN, read_sampling_rates, summarise_rates,
)
from meanap.catnap.store import (  # noqa: E402
    FORMAT_VERSION, RecordingState, load_recording_state, save_recording_state,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def _state(fs: float) -> RecordingState:
    return RecordingState(
        adjMs={"10mslag": np.eye(3)},
        coords=np.zeros((3, 2)), channels=np.arange(1, 4),
        spike_counts=np.ones(3), duration_s=60.0, fs=fs,
        plane0=Path("/nowhere"),
    )


# ── The rate survives being written and read back ────────────────────────────

print("Step-2 state carries the rate")

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "rec_catnap.npz"
    save_recording_state(path, _state(15.0), {"FR": np.ones(3)})
    back, _ = load_recording_state(path, Path("/nowhere"))
    check("fs round-trips through the npz", back.fs == 15.0, str(back.fs))

    with np.load(path) as data:
        check("the format stamp was bumped for the new key",
              int(data["catnap_format"]) == FORMAT_VERSION == 5,
              str(int(data["catnap_format"])))
        check("fs is stored under its own key", "fs" in data.files)

    # A file written before format 5 has no fs key. It must still open: a
    # bundle recipient has no raw data, so "re-run it" is not advice they can
    # take (same reasoning as the marker/group bumps before this one).
    with np.load(path) as data:
        older = {k: data[k] for k in data.files if k != "fs"}
    older["catnap_format"] = np.array(4)
    old_path = Path(tmp) / "old_catnap.npz"
    np.savez(old_path, **older)
    old_state, _ = load_recording_state(old_path, Path("/nowhere"))
    check("a pre-format-5 file still loads, with fs unset",
          old_state.fs == 0.0, str(old_state.fs))


# ── Reading the rates back off a finished folder ─────────────────────────────

print("\nReading rates from an output folder")


def _write_folder(root: Path, rows: list[dict], *, which: str) -> None:
    """Write one recording-level table, with a lag column for the network one."""
    if which == "activity":
        out = root / "2_NeuronalActivity" / "TwoPhotonActivity_RecordingLevel.csv"
        frame = pd.DataFrame(rows)
    else:
        out = root / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv"
        # The network table repeats each recording once per lag.
        frame = pd.DataFrame([dict(r, Lag=lag) for r in rows for lag in (10, 25)])
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)


ROWS = [
    {"FileName": "recA", "Grp": "WT", "DIV": 21, RATE_COLUMN: 15.0},
    {"FileName": "recB", "Grp": "KO", "DIV": 21, RATE_COLUMN: 33.3},
    {"FileName": "recC", "Grp": "KO", "DIV": 28, RATE_COLUMN: 15.0},
]

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    _write_folder(root, ROWS, which="activity")
    rates = read_sampling_rates(root)
    check("every recording's rate comes back",
          rates == {"recA": 15.0, "recB": 33.3, "recC": 15.0}, str(rates))

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    _write_folder(root, ROWS, which="network")
    rates = read_sampling_rates(root)
    check("the network table works too, with the per-lag rows collapsed",
          rates == {"recA": 15.0, "recB": 33.3, "recC": 15.0}, str(rates))

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    _write_folder(root, [{k: v for k, v in r.items() if k != RATE_COLUMN}
                         for r in ROWS], which="activity")
    check("a folder written before the column reads as 'nothing to say'",
          read_sampling_rates(root) == {}, str(read_sampling_rates(root)))

check("so does a folder with no tables at all",
      read_sampling_rates(Path(tempfile.gettempdir()) / "definitely-not-a-run") == {})


# ── The summary a reader actually sees ───────────────────────────────────────

print("\nSummarising for the report and the viewer")

mixed = summarise_rates({"a": 15.0, "b": 33.3, "c": 15.0})
check("a mixed batch is flagged as mixed", mixed["mixed"] is True)
check("rates are counted and ordered",
      mixed["rates"] == [{"fs": 15.0, "count": 2}, {"fs": 33.3, "count": 1}],
      str(mixed["rates"]))
check("the recording count is the number of recordings, not of rates",
      mixed["n_recordings"] == 3, str(mixed["n_recordings"]))
check("each recording is listed, so a rate can be traced to its files",
      mixed["byRecording"] == {"a": 15.0, "b": 33.3, "c": 15.0})

single = summarise_rates({"a": 15.0, "b": 15.0})
check("one rate is not flagged as mixed", single["mixed"] is False)
check("and is still shown, so 'no confound possible' can be said out loud",
      single["rates"] == [{"fs": 15.0, "count": 2}], str(single["rates"]))

check("nothing to summarise gives None, not an empty panel",
      summarise_rates({}) is None)


# ── The run log ──────────────────────────────────────────────────────────────

print("\nThe run says so while it is running")

from meanap.catnap.pipeline import _log_sampling_rates  # noqa: E402

lines: list[str] = []
_log_sampling_rates({"a": _state(15.0), "b": _state(33.3), "c": _state(15.0)},
                    lines.append)
joined = "\n".join(lines)
check("a mixed batch is called out", "mixes 3 acquisition rates" not in joined
      and "mixes 2 acquisition rates" in joined, joined)
check("with the counts", "15 Hz x2" in joined and "33.3 Hz x1" in joined, joined)
check("and why it matters", "confounded" in joined, joined)

lines = []
_log_sampling_rates({"a": _state(15.0), "b": _state(15.0)}, lines.append)
check("a single-rate batch says so in one quiet line",
      len(lines) == 1 and "15 Hz (all 2 recordings)" in lines[0], str(lines))

lines = []
_log_sampling_rates({}, lines.append)
check("and a run that produced no states says nothing", lines == [], str(lines))


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All sampling-rate checks passed.")
