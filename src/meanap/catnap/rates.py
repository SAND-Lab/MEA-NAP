"""Reading a finished run's per-recording acquisition rates back off disk.

CAT-NAP takes the frame rate from each recording's own ``ops.npy`` rather than
from a setting — which is what MATLAB does too (``suite2pToAdjm.m`` assigns
``Params.fs`` from the file and discards whatever the GUI held). The
consequence is that a batch has no single sampling rate to report, and
``params.json`` cannot carry one: a 2P dataset spanning several culture preps
routinely spans several rates, because rate tends to be a property of the prep.

That matters to a reader in two ways. Every seconds-valued setting — the
denoising windows, the minimum event interval — is converted to frames with the
recording's own rate, so nothing is *wrong* when rates differ. But rate covaries
with prep, and prep can covary with genotype or condition, so a mixed-rate batch
is worth knowing about before its group comparisons are believed.

The rate therefore reaches disk as a ``samplingRateHz`` column on the
recording-level tables (see ``_save_catnap_results``), and this module reads it
back for the HTML report and the bundle viewer. Both open a finished folder
with no access to the run that made it, so a column in a CSV they already read
beats a new sidecar file neither would find.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

__all__ = ["RATE_COLUMN", "read_sampling_rates", "summarise_rates"]

#: Column name used in both recording-level CSVs.
RATE_COLUMN = "samplingRateHz"

#: Where to look, in order. The 2P activity table is preferred — the rate is an
#: acquisition fact and sits beside the other per-recording ones — but a run
#: stopped after step 4, or one whose activity table failed to write, still has
#: the network table.
_SOURCES = (
    Path("2_NeuronalActivity") / "TwoPhotonActivity_RecordingLevel.csv",
    Path("4_NetworkActivity") / "NetworkActivity_RecordingLevel.csv",
)


def read_sampling_rates(output_root: Path | str) -> dict[str, float]:
    """``{recording filename: rate in Hz}`` for a finished output folder.

    Empty when the folder predates the column, holds an ephys run, or has no
    recording-level table — every caller treats that as "nothing to say"
    rather than as an error, since a report must still render for an older run.
    """
    root = Path(output_root)
    for rel in _SOURCES:
        path = root / rel
        if not path.exists():
            continue
        try:
            import pandas as pd

            df = pd.read_csv(path)
        except Exception:                                  # noqa: BLE001
            continue
        if RATE_COLUMN not in df.columns or "FileName" not in df.columns:
            continue
        # The network table repeats a recording once per lag; the rate is a
        # property of the recording, so the duplicates collapse.
        pairs = (df[["FileName", RATE_COLUMN]].dropna()
                 .drop_duplicates("FileName").values.tolist())
        rates = {str(name): float(fs) for name, fs in pairs if float(fs) > 0}
        if rates:
            return rates
    return {}


def summarise_rates(rates: dict[str, float]) -> dict | None:
    """Shape the rates for display: the distinct values, and how many each.

    Returns ``None`` when there is nothing to show. ``mixed`` is the field
    worth acting on — one rate is unremarkable, several is the case a reader
    should see before comparing groups.
    """
    if not rates:
        return None
    counts = Counter(round(float(fs), 4) for fs in rates.values())
    return {
        "mixed": len(counts) > 1,
        "n_recordings": len(rates),
        "rates": [{"fs": fs, "count": counts[fs]} for fs in sorted(counts)],
        "byRecording": {name: round(float(fs), 4)
                        for name, fs in sorted(rates.items())},
    }
