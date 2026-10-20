"""Stimulation known from events, not from the voltage: light, sound, TTLs.

MEA-Stim was built for electrical stimulation, which it finds in the voltage
trace and which has a *stimulating electrode*. A light flash has neither: its
times come from a TTL line or an event log, and it stimulates the whole
preparation. Its analysis is the same though. :func:`stim_activity_analysis`
and the plots take **patterns = lists of event times** and skip any node marked
as stimulating, so an event-driven run is:

* :class:`StimEvents` — event times, each with a condition label (``ON``,
  ``OFF``, a stimulus ID). A *condition* plays the role of an electrical
  *pattern*.
* readers: :func:`events_from_ttl` (a TTL word log, e.g. MaxWell's ``bits``,
  see :func:`meanap.pipeline.maxwell.read_maxwell_ttl`) and
  :func:`read_events_csv` (``time_s[,condition]`` — any platform).
* :func:`stim_info_without_stim_nodes` — the per-node records MEA-Stim
  expects, with no node stimulating and no blanking, so nothing is removed or
  skipped.

How events become conditions is the caller's choice
(:func:`assign_conditions`): one condition, alternating labels (a full-field
flash marked at each on/off transition), or the labels a CSV gives.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .detection import StimChannelInfo

#: ``stimDetectionMethod`` values handled here rather than by voltage detection.
EVENT_METHODS = ("maxwellTTL", "eventsCSV")


@dataclass(frozen=True)
class StimEvents:
    """Stimulus events: when, and which condition each one was."""

    times_s: np.ndarray
    conditions: np.ndarray
    #: How the events were found, for the log and the CSV beside the results.
    description: str = ""

    def __post_init__(self):
        if len(self.times_s) != len(self.conditions):
            raise ValueError(f"{len(self.times_s)} event times but "
                             f"{len(self.conditions)} condition labels")

    @property
    def condition_names(self) -> list[str]:
        """Condition labels in order of first appearance."""
        return list(dict.fromkeys(self.conditions.tolist()))

    def patterns(self) -> list[np.ndarray]:
        """Event times per condition, in :attr:`condition_names` order."""
        return [np.sort(self.times_s[self.conditions == c]) for c in self.condition_names]

    def within(self, start_s: float, end_s: float) -> "StimEvents":
        keep = (self.times_s >= start_s) & (self.times_s < end_s)
        return StimEvents(self.times_s[keep], self.conditions[keep], self.description)


# ── TTL words → event times ───────────────────────────────────────────────────

def ttl_edges(times_s: np.ndarray, words: np.ndarray, bit: int
              ) -> tuple[np.ndarray, np.ndarray]:
    """Times *bit* goes high and goes low: ``(rises, falls)``.

    *words* is the TTL word after each change, as logged; the line's state
    before the first entry is taken to be the first entry's, so a log that
    starts mid-pulse does not invent an edge at t = first change.
    """
    words = np.asarray(words, dtype=np.int64)
    state = (words >> bit) & 1
    prev = np.r_[state[:1], state[:-1]]
    t = np.asarray(times_s, dtype=float)
    return t[(prev == 0) & (state == 1)], t[(prev == 1) & (state == 0)]


def _active_bits(words: np.ndarray) -> list[int]:
    changed = np.bitwise_or.reduce(np.asarray(words, np.int64) ^ np.asarray(words, np.int64)[:1]) \
        if len(words) else 0
    return [b for b in range(int(changed).bit_length()) if (changed >> b) & 1]


def describe_ttl(times_s: np.ndarray, words: np.ndarray) -> list[str]:
    """One line per TTL bit that changes: edge counts and median spacing.

    Shown in the log so a user can see which bit is the stimulus and which is
    a frame sync before trusting an automatic choice.
    """
    lines = []
    for b in _active_bits(words):
        rises, falls = ttl_edges(times_s, words, b)
        spacing = np.median(np.diff(rises)) if len(rises) > 1 else np.nan
        lines.append(f"bit {b} (value {1 << b}): {len(rises)} rises, {len(falls)} falls, "
                     f"median spacing {spacing * 1e3:.1f} ms")
    return lines


def events_from_ttl(times_s: np.ndarray, words: np.ndarray, rule: str = "auto",
                    min_interval_s: float = 0.05) -> tuple[np.ndarray, str]:
    """Pick stimulus event times out of a TTL word log.

    ``rule``:

    * ``"rise:<bit>"`` / ``"fall:<bit>"`` — that bit's rising / falling edges.
    * ``"value:<v>"`` — each time the word *becomes* ``v``.
    * ``"auto"`` — the falling or rising edges, whichever are fewer, of the
      changing bit with the fewest edges (at least two). A projector's frame
      sync toggles every frame; the stimulus marker is the rare one. The
      choice is returned so the caller can log it.

    Events closer than ``min_interval_s`` to the previous kept one are merged
    into it (a marker that bounces). Returns ``(times_s, description)``.
    """
    times_s = np.asarray(times_s, dtype=float)
    words = np.asarray(words, dtype=np.int64)
    if rule == "auto":
        best = None
        for b in _active_bits(words):
            rises, falls = ttl_edges(times_s, words, b)
            for kind, edges in (("fall", falls), ("rise", rises)):
                if len(edges) >= 2 and (best is None or len(edges) < len(best[2])):
                    best = (kind, b, edges)
        if best is None:
            return np.zeros(0), "auto: no TTL bit changes at least twice"
        kind, bit, events = best
        how = f"auto → {kind}:{bit}"
    elif rule.startswith(("rise:", "fall:")):
        kind, bit = rule.split(":")
        rises, falls = ttl_edges(times_s, words, int(bit))
        events, how = (rises if kind == "rise" else falls), rule
    elif rule.startswith("value:"):
        v = int(rule.split(":")[1])
        # As for edges, the first logged word is the starting state, not a change.
        prev = np.r_[words[:1], words[:-1]]
        events, how = times_s[(words == v) & (prev != v)], rule
    else:
        raise ValueError(f"Unknown TTL rule {rule!r} (auto, rise:<bit>, fall:<bit>, value:<v>)")
    return _debounce(np.sort(events), min_interval_s), how


def _debounce(times: np.ndarray, min_interval_s: float) -> np.ndarray:
    if len(times) < 2 or min_interval_s <= 0:
        return times
    keep = [0]
    for i in range(1, len(times)):
        if times[i] - times[keep[-1]] >= min_interval_s:
            keep.append(i)
    return times[keep]


# ── Conditions ────────────────────────────────────────────────────────────────

def assign_conditions(times_s: np.ndarray, mode: str = "single",
                      labels: list[str] | None = None) -> np.ndarray:
    """A condition label per event.

    * ``"single"`` — every event is one condition (``labels[0]``, default
      ``"stim"``).
    * ``"alternate"`` — labels cycle in event order: ``ON, OFF, ON, …`` for a
      full-field flash marked at each transition. Which label comes first is
      the user's to say; nothing in a TTL marker tells ON from OFF.
    """
    n = len(times_s)
    if mode == "single":
        return np.full(n, (labels or ["stim"])[0], dtype=object).astype(str)
    if mode == "alternate":
        labels = labels or ["A", "B"]
        return np.array([labels[i % len(labels)] for i in range(n)], dtype=str)
    raise ValueError(f"Unknown condition mode {mode!r} (single, alternate)")


def read_events_csv(path: str | Path) -> StimEvents:
    """Events from a CSV: a time column (``time_s``, ``onset_s``, ``time`` or
    ``onset``, in seconds) and, optionally, ``condition``. Without one every
    event is condition ``stim``."""
    path = Path(path)
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return StimEvents(np.zeros(0), np.zeros(0, dtype=str), f"{path.name}: empty")
    cols = {c.strip().lower(): c for c in rows[0].keys() if c}
    tcol = next((cols[c] for c in ("time_s", "onset_s", "time", "onset") if c in cols), None)
    if tcol is None:
        raise ValueError(f"{path.name}: no time column (time_s, onset_s, time or onset)")
    ccol = cols.get("condition")
    times = np.array([float(r[tcol]) for r in rows])
    conds = np.array([(r[ccol].strip() if ccol else "") or "stim" for r in rows], dtype=str)
    order = np.argsort(times, kind="stable")
    return StimEvents(times[order], conds[order], f"{path.name}: {len(times)} events")


# ── Into MEA-Stim's per-node records ──────────────────────────────────────────

def stim_info_without_stim_nodes(channel_names: np.ndarray, coords: np.ndarray
                                 ) -> list[StimChannelInfo]:
    """One record per node, none of them stimulating.

    With no stimulating node, :func:`~meanap.stim.cleaning.clean_spikes_from_stim`
    removes nothing and :func:`~meanap.stim.activity.stim_activity_analysis`
    skips nothing; the only artifact window left is ``postStimWindowDur``,
    which the user sets (0 for light).
    """
    empty = np.zeros(0)
    return [StimChannelInfo(
        elec_stim_times=empty, elec_stim_dur=empty, channel_name=int(ch),
        coords=np.asarray(xy, dtype=float), pattern=0,
        blank_starts=empty, blank_ends=empty,
        non_stim_blank_starts=empty, non_stim_blank_ends=empty, blank_durations=empty,
    ) for ch, xy in zip(np.asarray(channel_names).ravel(), np.asarray(coords, float))]
