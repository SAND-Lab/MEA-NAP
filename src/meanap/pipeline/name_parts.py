"""Read a batch's group and DIV out of its recording names, as suggestions.

Labs name recordings after what they are: ``SYN_20260904_WT_DIV14_A1`` is a
synapsin culture, plated 4 Sep 2026, wild type, 14 days in vitro, well A1. A
new spreadsheet can start from that instead of from blank columns, but only as
a suggestion the person confirms: a group read from the wrong part of a name
does not fail. It silently splits or merges the group comparisons the whole
analysis is built on. So this module only proposes; the spreadsheet editor
shows what it proposed as unconfirmed until the person accepts it.

A name is split into *parts* at underscores, hyphens, dots and spaces. Parts are
compared by position across the batch, which is how naming schemes work: the
genotype is "the third part", not "whichever part says WT".
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

__all__ = [
    "NamePartSuggestion", "div_from_part", "name_parts", "part_values",
    "suggest_name_parts",
]

_SPLIT_RE = re.compile(r"[\s_\-.]+")
#: A part that is an age: ``DIV14``, ``div7``, ``D21``, ``day35``.
_DIV_PART_RE = re.compile(r"^(?:DIV|D|day)(\d{1,3})$", re.IGNORECASE)
#: Plate wells (``A1`` … ``H12``) and MEA well positions: never a group.
_WELL_RE = re.compile(r"^[A-H]\d{1,2}$", re.IGNORECASE)
#: Words that name a group in the datasets MEA-NAP has seen. Matching one is
#: the strongest evidence a part is the group: a batch id varies across files
#: just as a genotype does, and only the vocabulary tells them apart.
GROUP_WORDS = frozenset({
    "wt", "wildtype", "ko", "het", "hom", "homo", "ki", "cko", "tg", "ntg",
    "mut", "mutant", "ctrl", "ctl", "control", "sham", "veh", "vehicle",
    "treated", "untreated", "drug", "dmso", "pbs", "saline", "kd", "oe",
    "scr", "scrambled", "shctrl", "isogenic", "patient", "healthy",
})


def name_parts(name: str) -> list[str]:
    """*name* split at ``_``, ``-``, ``.`` and spaces, empty parts dropped."""
    return [p for p in _SPLIT_RE.split(str(name).strip()) if p]


def part_values(names, index: int) -> list[str]:
    """Part *index* of every name; ``""`` where a name has fewer parts."""
    out = []
    for name in names:
        parts = name_parts(name)
        out.append(parts[index] if index < len(parts) else "")
    return out


def div_from_part(part: str) -> str:
    """The number in a DIV part (``DIV14`` → ``14``, ``21`` → ``21``), else ``""``."""
    match = _DIV_PART_RE.match(part) or re.fullmatch(r"(\d{1,3})", part)
    return str(int(match.group(1))) if match else ""


@dataclass(frozen=True)
class NamePartSuggestion:
    """Which name parts look like the group and the DIV, and why."""

    group_part: int | None
    div_part: int | None
    #: One sentence for the person, saying what was picked and on what grounds.
    group_reason: str = ""


def _shared_length(names) -> int:
    """How many leading parts every name has."""
    lengths = [len(name_parts(n)) for n in names]
    return min(lengths) if lengths else 0


def _looks_like_group(values: list[str]) -> bool:
    """Whether a part could be a group at all: not a number, date, well or age."""
    return not any(
        v.isdigit() or _WELL_RE.match(v) or _DIV_PART_RE.match(v) or not v
        for v in values
    )


def suggest_name_parts(names) -> NamePartSuggestion:
    """Guess which part of the names is the group and which the DIV.

    The DIV is the part that reads as an age (``DIV14``, ``D21``) in every
    name. The group, in order of preference:

    1. a part where some name uses a known group word (WT, KO, Het, Ctrl…);
    2. a part that varies across the batch but repeats, so each value is
       shared by several recordings, preferring the fewest distinct values and
       parts without digits (batch and animal ids carry digits; genotypes
       mostly don't);
    3. with more than one recording and nothing varying, the first part with
       letters in it, as the name of a single-group batch (``NGN2_…``).

    Nothing is suggested when there is no part to point at.
    """
    names = [str(n) for n in names if str(n).strip()]
    n_parts = _shared_length(names)
    if not names or not n_parts:
        return NamePartSuggestion(None, None)

    columns = [part_values(names, i) for i in range(n_parts)]

    div_part = next((i for i, values in enumerate(columns)
                     if all(_DIV_PART_RE.match(v) for v in values)), None)

    candidates = [i for i, values in enumerate(columns)
                  if i != div_part and _looks_like_group(values)]

    for i in candidates:
        if any(v.lower() in GROUP_WORDS for v in columns[i]):
            distinct = sorted(set(columns[i]), key=str.lower)
            return NamePartSuggestion(
                i, div_part, f"Part {i + 1} names a group: {', '.join(distinct)}.")

    def varies(i: int) -> bool:
        counts = Counter(columns[i])
        return len(counts) >= 2 and min(counts.values()) >= 2

    varying = [i for i in candidates if varies(i)]
    if varying:
        best = min(varying, key=lambda i: (
            any(ch.isdigit() for v in columns[i] for ch in v),
            len(set(columns[i])), i))
        distinct = sorted(set(columns[best]), key=str.lower)
        return NamePartSuggestion(
            best, div_part,
            f"Part {best + 1} splits the recordings into {len(distinct)} groups: "
            f"{', '.join(distinct)}.")

    if len(names) > 1:
        constant = [i for i in candidates if len(set(columns[i])) == 1
                    and any(ch.isalpha() for ch in columns[i][0])]
        if constant:
            i = constant[0]
            return NamePartSuggestion(
                i, div_part,
                f"Every recording shares part {i + 1}, {columns[i][0]}, so they "
                "may all be one group.")

    return NamePartSuggestion(None, div_part)
