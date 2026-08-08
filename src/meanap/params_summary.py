"""The settings a run used, arranged for a person to read.

``params.json`` is the authoritative record of how a result was produced, and
it is unreadable: a flat object of ~180 keys in declaration order, most of them
at their defaults. The question a reader actually has is narrower — *what was
different about this run?* — and the answer is usually a dozen fields.

So this groups the fields the way :class:`~meanap.params.Params` groups them,
marks the ones that differ from the defaults, and hides paths that should not
travel. Both the static ``report.html`` and the interactive viewer render the
same structure, so the two cannot disagree about what a run was.

**The grouping comes from the dataclass source**, not from a list kept here.
``Params`` marks its sections with ``# ── Spike detection ──`` comments and
declares its fields in order, so walking the source assigns every field to the
section it was written under — and a field added tomorrow lands in the right
place with nothing to update. If the source is unavailable (a frozen build),
everything falls into one group rather than nothing being shown.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from meanap.params import Params, SECRET_URL_FIELDS, is_remote_url

__all__ = [
    "ParamEntry", "ParamGroup", "ParamsSummary",
    "summarise_params", "summary_from_file", "field_sections",
]

#: Shown instead of a value that should not travel with a shared report.
REDACTED = "‹remote source hidden›"

#: ``# ── Spike detection ──────────`` in the dataclass body.
_SECTION_RE = re.compile(r"^\s*#\s*──\s*(?P<name>.+?)\s*─+\s*$")

#: ``fs: float = 25000.0`` — a field declaration, not a comment or a method.
_FIELD_RE = re.compile(r"^\s{4}(?P<name>[a-z_][a-z0-9_]*)\s*:")

#: Where a field with no section of its own is put.
_UNGROUPED = "Other"


@dataclass(frozen=True)
class ParamEntry:
    """One setting, and whether the run changed it."""

    name: str
    value: Any
    default: Any
    changed: bool
    #: True when the value was replaced because it names a remote source.
    redacted: bool = False

    def as_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "default": self.default,
                "changed": self.changed, "redacted": self.redacted}


@dataclass(frozen=True)
class ParamGroup:
    """One section of the settings, in declaration order."""

    name: str
    entries: list[ParamEntry]

    @property
    def changed(self) -> int:
        return sum(1 for e in self.entries if e.changed)

    def as_dict(self) -> dict:
        return {"name": self.name, "changed": self.changed,
                "entries": [e.as_dict() for e in self.entries]}


@dataclass
class ParamsSummary:
    """Every setting, grouped, plus what the file held that we don't know."""

    groups: list[ParamGroup] = field(default_factory=list)
    #: Keys present in the file that this version has no field for — a
    #: version-skew signal, and the reason it is surfaced rather than dropped.
    unknown: dict[str, Any] = field(default_factory=dict)

    @property
    def changed(self) -> int:
        return sum(g.changed for g in self.groups)

    @property
    def total(self) -> int:
        return sum(len(g.entries) for g in self.groups)

    def as_dict(self) -> dict:
        return {"groups": [g.as_dict() for g in self.groups],
                "unknown": self.unknown,
                "changed": self.changed, "total": self.total}


def field_sections() -> dict[str, str]:
    """``field name → section heading``, read off the dataclass source.

    Empty when the source cannot be read, which callers treat as "one group".
    """
    try:
        source = inspect.getsource(Params)
    except (OSError, TypeError):
        return {}

    sections: dict[str, str] = {}
    current = _UNGROUPED
    for line in source.splitlines():
        match = _SECTION_RE.match(line)
        if match:
            current = match.group("name")
            continue
        match = _FIELD_RE.match(line)
        if match:
            sections.setdefault(match.group("name"), current)
    return sections


def _defaults() -> dict[str, Any]:
    """Each field's default, with the factory ones actually called."""
    out: dict[str, Any] = {}
    for f in dataclasses.fields(Params):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            out[f.name] = f.default_factory()               # type: ignore[misc]
    return out


def _display(name: str, value: Any) -> tuple[Any, bool]:
    """The value to show, and whether it was hidden.

    A report is a thing people attach to papers and email around. A share link
    in it is a credential — see :data:`~meanap.params.SECRET_URL_FIELDS`, which
    exists for the same reason on the bundle side.
    """
    if name in SECRET_URL_FIELDS and is_remote_url(str(value)):
        return REDACTED, True
    if isinstance(value, Path):
        return str(value), False
    return value, False


def summarise_params(
    params: Params | dict, *, unknown: dict[str, Any] | None = None,
) -> ParamsSummary:
    """Group *params* by section and mark what differs from the defaults."""
    if isinstance(params, Params):
        values = dataclasses.asdict(params)
    else:
        values = dict(params)

    defaults = _defaults()
    sections = field_sections()

    # Declaration order, which is the order a reader of Params would meet them.
    known = [f.name for f in dataclasses.fields(Params)]
    grouped: dict[str, list[ParamEntry]] = {}
    order: list[str] = []

    for name in known:
        if name not in values:
            continue                      # an older file simply lacks the field
        raw = values[name]
        default = defaults.get(name)
        shown, redacted = _display(name, raw)
        section = sections.get(name, _UNGROUPED)
        if section not in grouped:
            grouped[section] = []
            order.append(section)
        grouped[section].append(ParamEntry(
            name=name, value=shown, default=default,
            changed=raw != default, redacted=redacted,
        ))

    extra = {k: v for k, v in values.items() if k not in set(known)}
    if unknown:
        extra.update(unknown)

    return ParamsSummary(
        groups=[ParamGroup(name=s, entries=grouped[s]) for s in order],
        unknown=extra,
    )


def summary_from_file(path: Path | str) -> ParamsSummary | None:
    """Summarise a ``params.json``, or ``None`` if it isn't there or is broken.

    Returns ``None`` rather than raising: a report missing its parameter table
    is worth less than one that fails to build.
    """
    import json

    path = Path(path)
    if not path.is_file():
        return None
    try:
        with open(path) as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    return summarise_params(raw)
