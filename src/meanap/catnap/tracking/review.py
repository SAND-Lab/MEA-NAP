"""What reviewing tracked cells by eye needs from a chain's payload, without Qt.

The tracking page in the app (:mod:`meanap.gui.tracking_view`) is where someone
goes through a chain cell by cell. Two kinds of review drove what is here:

* **Recovering missed ROIs.** A tracked cell that suite2p did not find on some
  day has no ROI there, so there is no ID to hand over: what is useful is
  *where to look* on that day's image. :func:`expected_positions` answers that
  in the day's own suite2p pixels — the coordinates of its TIFF, which is what
  someone re-running suite2p or drawing an ROI by hand works in.
* **Cell-type conflicts.** A cell whose immunostain label changes across days
  is either a wrong match or a wrong label; the calls here are the web page's
  (``recCall`` / ``finalCall`` / ``isFlip`` in :mod:`.viewer`), so a decision
  made in one place reads the same in the other.

**Coordinates.** The payload keeps every day in its own frame — centroids are
the raw suite2p ``med`` and the mean image is that recording's own — even for a
chain the tracker registered. Fields of view drift between days (by up to tens
of pixels), so a cell's position on a day it was found does not say where it
sits on a day it was missed. The drift between two days is measured here from
the cells tracked on both: their median displacement. That needs nothing the
payload does not carry, so it works on bundles made before this existed, and on
chains passed through unregistered, whose solved offsets were never stored.
Fields slide without rotating or warping (see FINDINGS in the tracking work),
so one translation per pair of days is the whole model.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import numpy as np

from meanap.catnap.tracking.celltypes import final_call as _final_call

__all__ = [
    "MIN_SHARED", "Expected", "day_shifts", "expected_positions", "missing_sessions",
    "nearest_roi", "roi_number", "session_rows", "recommended_call", "final_call",
    "is_flip", "needs_decision",
]

#: Fewest cells two days must share before their displacement is trusted. A
#: median of a handful of matches is already robust to one wrong match; fewer
#: than this and one bad match can move it.
MIN_SHARED = 5


def _f32(text: str) -> np.ndarray:
    if not text:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(base64.b64decode(text), dtype=np.float32)


def _yx(session: dict) -> tuple[np.ndarray, np.ndarray]:
    return _f32(session.get("cy", "")), _f32(session.get("cx", ""))


@dataclass(frozen=True)
class Expected:
    """Where a cell should be on a day it was not found."""

    y: float
    x: float
    #: Days the cell *was* found on that the estimate is built from.
    n_days: int
    #: Furthest any one of those days' estimates lies from the median, in
    #: pixels: 0 with one day, small when the days agree.
    spread_px: float


def session_rows(session: dict) -> dict[int, int]:
    """``{cluster: row}`` for the tracked ROIs on one day."""
    return {int(c): i for i, c in enumerate(session.get("cluster", [])) if int(c) >= 0}


def roi_number(session: dict, row: int) -> int:
    """The raw suite2p index of a row: what suite2p's own GUI calls the ROI.

    The payload's rows are the day's ``iscell`` ROIs in order; ``roi`` maps
    them back to ``stat.npy``. Payloads without it predate the mapping, and
    their rows are the only numbering there is.
    """
    roi = session.get("roi")
    return int(roi[row]) if roi is not None and row < len(roi) else int(row)


def day_shifts(sessions: list[dict], *, min_shared: int = MIN_SHARED
               ) -> dict[tuple[int, int], tuple[float, float, int]]:
    """``{(a, b): (dy, dx, n)}``: how far the field moved from day *a* to *b*.

    The median, over the *n* cells tracked on both days, of each cell's
    position on *b* minus its position on *a*. Only pairs sharing at least
    *min_shared* cells are kept.
    """
    rows = [session_rows(s) for s in sessions]
    coords = [_yx(s) for s in sessions]
    shifts = {}
    for a in range(len(sessions)):
        for b in range(len(sessions)):
            if a == b:
                continue
            shared = sorted(set(rows[a]) & set(rows[b]))
            if len(shared) < min_shared:
                continue
            ia = np.array([rows[a][c] for c in shared])
            ib = np.array([rows[b][c] for c in shared])
            (ya, xa), (yb, xb) = coords[a], coords[b]
            shifts[(a, b)] = (float(np.median(yb[ib] - ya[ia])),
                              float(np.median(xb[ib] - xa[ia])), len(shared))
    return shifts


def missing_sessions(cell: dict, n_sessions: int) -> list[int]:
    """Indices of the days a tracked cell was not found on."""
    present = {int(p[0]) for p in cell.get("positions", [])}
    return [k for k in range(n_sessions) if k not in present]


def expected_positions(payload: dict, *, min_shared: int = MIN_SHARED
                       ) -> dict[int, dict[int, Expected]]:
    """``{cluster: {session: Expected}}`` for every cell's missing days.

    Each day the cell was found on gives one estimate: its position there,
    moved by that day's measured displacement to the missing day. The median
    of those estimates is the answer. A missing day sharing too few cells
    with every day the cell was found on gets no estimate rather than a guess.
    """
    sessions = payload.get("sessions", [])
    shifts = day_shifts(sessions, min_shared=min_shared)
    out: dict[int, dict[int, Expected]] = {}
    for cell in payload.get("cells", []):
        here = {int(s): (float(y), float(x)) for s, y, x in cell.get("positions", [])}
        found = {}
        for m in missing_sessions(cell, len(sessions)):
            guesses = [(y + shifts[(k, m)][0], x + shifts[(k, m)][1])
                       for k, (y, x) in here.items() if (k, m) in shifts]
            if not guesses:
                continue
            g = np.asarray(guesses)
            centre = np.median(g, axis=0)
            spread = float(np.max(np.hypot(*(g - centre).T)))
            found[m] = Expected(y=float(centre[0]), x=float(centre[1]),
                                n_days=len(guesses), spread_px=spread)
        if found:
            out[int(cell["cluster"])] = found
    return out


def nearest_roi(session: dict, y: float, x: float) -> tuple[int, float] | None:
    """``(row, distance in px)`` of the ROI centred closest to ``(y, x)``."""
    ys, xs = _yx(session)
    if not len(ys):
        return None
    d = np.hypot(ys - y, xs - x)
    row = int(np.argmin(d))
    return row, float(d[row])


# ── cell types: the web page's rules, in Python ──────────────────────────────


def recommended_call(cell: dict, marker: str) -> str | None:
    """The recommendation: the genotype rule or the vote; ``None`` if tied."""
    rec = (cell.get("typeRec") or {}).get(marker)
    if rec:
        return rec.get("call")
    raw = (cell.get("typeCall") or {}).get(marker)   # payloads before recommendations
    return None if raw == "~" else (raw or None)


def final_call(cell: dict, marker: str, overrides: dict) -> str | None:
    """A person's decision if there is one, else the recommendation."""
    decided = (overrides.get(str(int(cell["cluster"]))) or {}).get(marker)
    return _final_call(recommended_call(cell, marker), decided)


def is_flip(cell: dict, marker: str) -> bool:
    """Whether the cell's labelled days disagree for *marker*."""
    return (cell.get("typeCall") or {}).get(marker) == "~"


def needs_decision(cell: dict, markers: list[str], overrides: dict) -> bool:
    """A flip that neither the recommendation nor a person has settled."""
    decided = overrides.get(str(int(cell["cluster"]))) or {}
    return any(is_flip(cell, m) and m not in decided and recommended_call(cell, m) is None
               for m in markers)
