"""What the number in a lag/bin folder name means, and what to call it.

Every functional-connectivity measure in the pipeline has one timescale
parameter, and every output is filed under it — ``1000mslag/``, a ``Lag``
column, a ``Lag1000ms/`` group folder. But the parameter is not the same thing
in each measure:

* **STTC** (all ephys runs, and CAT-NAP with ``twop_activity='peaks'``) reads
  it as a *lag*: the coincidence window either side of a spike.
* **Pearson correlation** (CAT-NAP with ``twop_activity`` in ``F`` / ``spks`` /
  ``denoised F``) reads it as a *bin*: the traces are averaged into bins of
  that length and the correlation is computed between the binned series. There
  is no lag involved — the correlation is at zero lag by construction.

Calling both of them "lag" made the correlation output actively misleading:
``adjM30mslag`` read like a 30 ms coincidence window when it was really "zero
lag, and the frames happened to be 30 ms apart". So the *user-facing* names —
output folders, figure titles, the report and viewer — say "bin" when that is
what the number is.

The structural identifiers deliberately do **not** change: the ``adjMs`` dict
keys stay ``adjM{n}mslag`` and the CSV column stays ``Lag``. Those are shared
with the ephys pipeline, they are the field names MATLAB writes, and they are
recorded in every bundle already on disk. Renaming them would buy a tidier
spelling at the cost of every existing result. Readers here accept both
spellings so a folder written either way still parses.
"""

from __future__ import annotations

#: ``twop_activity`` values whose adjacency is a binned Pearson correlation
#: rather than an STTC. Kept here rather than in ``adjacency`` so the naming
#: and the computation cannot drift apart.
CORRELATION_ACTIVITIES = frozenset({"F", "spks", "denoised F"})

#: The two spellings a timescale folder can carry. Order matters only in that
#: readers try them in turn.
SUFFIXES = ("mslag", "msbin")


def is_correlation_run(params) -> bool:
    """Does this configuration build adjacency by binned correlation?"""
    return (bool(getattr(params, "suite2p_mode", False))
            and getattr(params, "twop_activity", "peaks") in CORRELATION_ACTIVITIES)


def timescale_kind(params) -> str:
    """``'bin'`` for a correlation run, ``'lag'`` otherwise."""
    return "bin" if is_correlation_run(params) else "lag"


def timescale_suffix(params) -> str:
    """The folder suffix this run writes: ``'msbin'`` or ``'mslag'``."""
    return f"ms{timescale_kind(params)}"


def timescale_folder(value, params) -> str:
    """The folder name for one timescale, e.g. ``'1000msbin'``.

    *value* may be the number itself or a name already carrying a suffix, so
    this is safe to call on either a raw lag or a key read back off disk.
    """
    return f"{timescale_value(value)}{timescale_suffix(params)}"


def timescale_label(params) -> str:
    """How to name the parameter in prose: ``'bin'`` or ``'lag'``."""
    return timescale_kind(params)


def timescale_value(name) -> int:
    """The number out of ``'1000msbin'`` / ``'1000mslag'`` / ``1000``.

    Accepts either spelling and a bare number, which is what lets one reader
    serve output written before and after the rename.
    """
    text = str(name).strip()
    for suffix in SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    else:
        if text.endswith("ms"):
            text = text[:-2]
    return int(text)


def strip_timescale_suffix(name) -> str:
    """``'1000msbin'`` → ``'1000'``, leaving anything else alone."""
    text = str(name)
    for suffix in SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text
