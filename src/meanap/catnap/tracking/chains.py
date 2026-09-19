"""Group recordings into chains: the same field of view across DIVs.

A chain is one field of view followed over days. Working out which recordings
belong together is pure string handling, but there is one trap in it: **both
naming conventions in this dataset put the imaging date in the name alongside
the DIV**, and the date changes with the DIV. Dropping only the DIV therefore
leaves every day looking like a different field, and the chains never form.

    >>> parse_recording("20230518_9_OPME230505_P1_pup5B_KO_MOI25000_DIV13").chain
    '9_OPME230505_P1_pup5B_KO_MOI25000'
    >>> parse_recording("OPME240517_17_20240602_P1_pup2D_WT_MOI50000_DIV16").chain
    'OPME240517_17_P1_pup2D_WT_MOI50000'

A shared chain name is a hypothesis, not a guarantee. Whether two days really
show the same field is decided per day-pair from the ROI layout
(:func:`meanap.catnap.tracking.footprint.displacement`), and chains do exist
where one day is a genuinely different field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: ``DIV13``, ``DIV7`` -- days in vitro, the thing that varies along a chain.
DIV_RE = re.compile(r"^DIV(\d+)$")

#: An 8-digit ``YYYYMMDD`` token. Present in both naming conventions and
#: *changes with the DIV*, so it has to come out of the chain key too.
DATE_RE = re.compile(r"^\d{8}$")

#: ``OPME230505`` -- the culture prep. Worth carrying separately because
#: genotype covaries with it in this dataset, which matters for any group
#: comparison built on tracked cells.
PREP_RE = re.compile(r"^OPME\d+$")

GENOTYPES = ("WT", "Het", "KO")


@dataclass(frozen=True)
class TrackedRecording:
    """One recording, split into the parts that identify its field of view."""

    name: str
    chain: str
    div: int
    date: str
    prep: str
    genotype: str


@dataclass
class Chain:
    """One field of view, followed across DIVs."""

    key: str
    recordings: list[TrackedRecording] = field(default_factory=list)

    @property
    def divs(self) -> list[int]:
        return [r.div for r in self.recordings]

    @property
    def genotype(self) -> str:
        return self.recordings[0].genotype if self.recordings else ""

    @property
    def prep(self) -> str:
        return self.recordings[0].prep if self.recordings else ""


def parse_recording(name: str) -> TrackedRecording:
    """Split a recording name into its field-of-view identity and its DIV."""
    tokens = name.split("_")

    div = None
    for token in tokens:
        m = DIV_RE.match(token)
        if m:
            div = int(m.group(1))
            break
    if div is None:
        raise ValueError(f"no DIV in recording name: {name!r}")

    dates = [t for t in tokens if DATE_RE.match(t)]
    preps = [t for t in tokens if PREP_RE.match(t)]
    genotypes = [t for t in tokens if t in GENOTYPES]

    # the chain key is the name with *both* the date and the DIV removed
    kept = [t for t in tokens if not DATE_RE.match(t) and not DIV_RE.match(t)]
    return TrackedRecording(
        name=name,
        chain="_".join(kept),
        div=div,
        date=dates[0] if dates else "",
        prep=preps[0] if preps else "",
        genotype=genotypes[0] if genotypes else "",
    )


def build_chains(names: list[str], *, min_divs: int = 2) -> dict[str, Chain]:
    """Group recording names into chains of at least ``min_divs`` distinct DIVs.

    A chain listing the same DIV twice is a duplicate share of one recording --
    this dataset has eleven byte-identical pairs -- so only the first is kept.
    """
    by_chain: dict[str, dict[int, TrackedRecording]] = {}
    for name in names:
        try:
            rec = parse_recording(name)
        except ValueError:
            continue  # not a DIV-stamped recording; not part of any chain
        by_chain.setdefault(rec.chain, {}).setdefault(rec.div, rec)

    out: dict[str, Chain] = {}
    for key, by_div in by_chain.items():
        if len(by_div) < min_divs:
            continue
        out[key] = Chain(key=key, recordings=[by_div[d] for d in sorted(by_div)])
    return out
