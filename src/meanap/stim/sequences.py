"""Stimulation conditions: what was stimulated, named the same in every recording.

:func:`~meanap.stim.detection.get_stim_patterns` (the MATLAB port) groups
*electrodes*: those whose pulse times agree within ``stimTimeDiffThreshold``
are one pattern. That is right for sets of electrodes stimulated together, but
not for **temporal** patterns. A left-to-right sweep with 10 ms between pulses
makes each electrode its own pattern, and when the same electrodes are also
swept right-to-left, each of those patterns mixes both directions.

**Sequence grouping** groups *pulses* instead. Every pulse on every
stimulating electrode is put in time order, and pulses that follow each other
within ``gap_s`` form one stimulus. A stimulus is identified by its steps:
which electrodes were pulsed together, in what order, and with what delays.
Stimuli with the same steps are trials of one condition; the condition's
event time is the first pulse, and its last pulse sets where the response can
start to be measured.

**Names.** A condition is named by its electrodes: ``12+13`` for a set
pulsed together, ``12>13>14`` for a sequence. A recording that stimulates the
same electrodes as another therefore has the same condition names, with no
labelling needed. The ``StimConditions`` spreadsheet column (see
:func:`parse_condition_labels`) renames them, which is how different
electrodes in different wells — the hub of each culture, say — become one
condition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

#: Pulses closer than this (s) are one step: electrodes stimulated together.
SIMULTANEOUS_S = 0.001
#: A stimulus seen fewer times than this is left out (a pulse the detection missed).
MIN_TRIALS = 3


@dataclass
class StimCondition:
    """One stimulation condition of a recording."""

    name: str
    steps: tuple[tuple[int, ...], ...]  # channel IDs per step, in stimulation order
    delays_s: np.ndarray                # (n_steps,) onset of each step after the first
    onsets_s: np.ndarray                # (n_trials,) first pulse of every trial
    channel_index: tuple[int, ...]      # stim_info indices of the electrodes involved
    label: str | None = None            # from the spreadsheet, when given

    @property
    def last_pulse_s(self) -> float:
        """Last pulse after the first one: 0 for a set pulsed together."""
        return float(self.delays_s[-1]) if self.delays_s.size else 0.0

    @property
    def display_name(self) -> str:
        return self.label or self.name

    @property
    def channel_ids(self) -> set[int]:
        return {c for step in self.steps for c in step}


def steps_name(steps: tuple[tuple[int, ...], ...]) -> str:
    """``((12, 13),)`` → ``"12+13"``; ``((12,), (13,), (14,))`` → ``"12>13>14"``."""
    return ">".join("+".join(str(c) for c in step) for step in steps)


def _steps(times: np.ndarray, channels: np.ndarray) -> tuple[tuple[tuple[int, ...], ...], np.ndarray]:
    """One stimulus's pulses as steps (channel IDs pulsed together) and step delays."""
    steps, delays = [], []
    start = None
    for t, c in zip(times, channels):
        if start is None or t - start > SIMULTANEOUS_S:
            start = t
            steps.append([])
            delays.append(t - times[0])
        steps[-1].append(int(c))
    return tuple(tuple(sorted(set(s))) for s in steps), np.array(delays)


def group_sequences(stim_info: list, gap_s: float, *, delay_tol_s: float = SIMULTANEOUS_S,
                    min_trials: int = MIN_TRIALS, log=None) -> list[StimCondition]:
    """Group every stimulating electrode's pulses into stimuli, and stimuli into conditions.

    Two stimuli are the same condition when they have the same steps and every
    step's delay agrees within *delay_tol_s*. A sweep run at two speeds is
    therefore two conditions, named with their delays. Conditions with fewer
    than *min_trials* trials are left out and logged.
    """
    times, chans, idxs = [], [], {}
    for i, info in enumerate(stim_info):
        t = np.asarray(info.elec_stim_times, float).ravel()
        if t.size:
            times.append(t)
            chans.append(np.full(t.size, int(info.channel_name)))
            idxs[int(info.channel_name)] = i
    if not times:
        return []
    t = np.concatenate(times)
    c = np.concatenate(chans)
    order = np.lexsort((c, t))
    t, c = t[order], c[order]
    breaks = np.flatnonzero(np.diff(t) > gap_s) + 1
    starts = np.r_[0, breaks]
    ends = np.r_[breaks, t.size]

    groups: dict[tuple, list[tuple[float, np.ndarray]]] = {}
    for a, b in zip(starts, ends):
        steps, delays = _steps(t[a:b], c[a:b])
        groups.setdefault(steps, []).append((float(t[a]), delays))

    conditions: list[StimCondition] = []
    for steps, trials in groups.items():
        clusters: list[list[tuple[float, np.ndarray]]] = []
        for onset, delays in trials:
            for cl in clusters:
                if np.max(np.abs(cl[0][1] - delays)) <= delay_tol_s:
                    cl.append((onset, delays))
                    break
            else:
                clusters.append([(onset, delays)])
        for cl in clusters:
            delays = np.median(np.array([d for _, d in cl]), axis=0)
            name = steps_name(steps)
            if len(clusters) > 1:
                name += " (" + "/".join(f"{d * 1000:g}" for d in np.round(delays[1:], 4)) + " ms)"
            conditions.append(StimCondition(
                name=name, steps=steps, delays_s=delays,
                onsets_s=np.array(sorted(o for o, _ in cl)),
                channel_index=tuple(sorted(idxs[ch] for step in steps for ch in step))))

    rare = [cd for cd in conditions if cd.onsets_s.size < min_trials]
    if rare and log:
        log(f"    {sum(cd.onsets_s.size for cd in rare)} stimulus/stimuli in "
            f"{len(rare)} sequence(s) seen fewer than {min_trials} times left out: "
            + ", ".join(f"{cd.name} ({cd.onsets_s.size})" for cd in rare[:5])
            + (" …" if len(rare) > 5 else ""))
    kept = [cd for cd in conditions if cd.onsets_s.size >= min_trials]
    kept.sort(key=lambda cd: cd.onsets_s[0])
    return kept


def conditions_from_patterns(stim_info: list, patterns: list[np.ndarray]) -> list[StimCondition]:
    """The MATLAB-port patterns as conditions, named by their electrodes.

    Pattern *k*'s electrodes are those with ``pattern == k``; they were pulsed
    together (within ``stimTimeDiffThreshold``), so the condition is one step.
    """
    out = []
    for k, onsets in enumerate(patterns, start=1):
        idx = tuple(i for i, s in enumerate(stim_info) if s.pattern == k)
        steps = (tuple(sorted(int(stim_info[i].channel_name) for i in idx)),)
        out.append(StimCondition(name=steps_name(steps), steps=steps, delays_s=np.zeros(1),
                                 onsets_s=np.sort(np.asarray(onsets, float).ravel()),
                                 channel_index=idx))
    return out


def assign_patterns(stim_info: list, conditions: list[StimCondition]) -> None:
    """Record on each electrode which conditions (1-based) it is part of.

    ``pattern`` keeps one id (> 0 marks a stimulating electrode for the code
    ported from MATLAB); ``pattern_ids`` holds them all, since an electrode
    swept in both directions belongs to two conditions.
    """
    for info in stim_info:
        info.pattern_ids = ()
    for k, cd in enumerate(conditions, start=1):
        for i in cd.channel_index:
            stim_info[i].pattern_ids = (*stim_info[i].pattern_ids, k)
    for info in stim_info:
        info.pattern = info.pattern_ids[0] if info.pattern_ids else 0


# ── StimConditions spreadsheet column ─────────────────────────────────────────

_ENTRY = re.compile(r"^\s*([^=]+?)\s*=\s*(.+?)\s*$")


def parse_condition_steps(spec: str) -> tuple[tuple[int, ...], ...]:
    """``"12>13+14"`` → ``((12,), (13, 14))``: ``>`` orders steps, ``+`` joins a step."""
    try:
        return tuple(tuple(sorted(int(float(x)) for x in step.split("+")))
                     for step in spec.split(">"))
    except ValueError:
        raise ValueError(f"cannot read electrodes {spec!r}: expected IDs joined by "
                         f"'+' (together) and '>' (in order), e.g. 12+13 or 12>13>14") from None


def parse_condition_labels(value: str | None) -> dict[tuple, str] | str | None:
    """Read one recording's ``StimConditions`` value.

    * blank → ``None``: electrode names are kept;
    * ``hub`` → that label, for a recording with one condition;
    * ``A=12+13; B=45+46`` or ``LtoR=12>13>14; RtoL=14>13>12`` → a mapping
      from steps to label, entries separated by ``;``.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() == "nan":
        return None
    if "=" not in value:
        return value
    out: dict[tuple, str] = {}
    for entry in filter(str.strip, value.split(";")):
        m = _ENTRY.match(entry)
        if not m:
            raise ValueError(f"cannot read StimConditions entry {entry!r}: "
                             f"expected label=electrodes, e.g. hub=45 or LtoR=12>13>14")
        out[parse_condition_steps(m.group(2))] = m.group(1)
    return out


def apply_labels(conditions: list[StimCondition], value: str | None, log=None) -> None:
    """Label *conditions* from a ``StimConditions`` value; unmatched ones keep their names."""
    labels = parse_condition_labels(value)
    if labels is None:
        return
    if isinstance(labels, str):
        if len(conditions) != 1:
            raise ValueError(
                f"StimConditions is the single label {labels!r}, but this recording has "
                f"{len(conditions)} conditions ({', '.join(c.name for c in conditions)}); "
                f"name each, e.g. {labels}={conditions[0].name if conditions else '12'}")
        conditions[0].label = labels
        return
    used = set()
    for cd in conditions:
        if cd.steps in labels:
            cd.label = labels[cd.steps]
            used.add(cd.steps)
    for steps in labels.keys() - used:
        if log:
            log(f"    ! StimConditions names {labels[steps]}={steps_name(steps)}, "
                f"which was not stimulated in this recording")
    seen: dict[str, str] = {}
    for cd in conditions:
        if cd.display_name in seen:
            raise ValueError(f"StimConditions gives two conditions the label "
                             f"{cd.display_name!r} ({seen[cd.display_name]} and {cd.name})")
        seen[cd.display_name] = cd.name
