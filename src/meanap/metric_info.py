"""What a metric means: the cards the results viewer shows about one.

Each metric is described by one Markdown file in ``meanap/gui/assets/metrics``
with a short front matter::

    ---
    key: BC
    name: Betweenness centrality
    also: BCmean, BCtop10          # other keys the same card explains
    level: node                    # node | recording | concept
    family: network                # network | activity | catnap | spatiotemporal
    image: BC.png                  # optional, beside the file
    related: ND, PC, Eloc
    ---
    One or two sentences: the summary.

    ## What it measures
    ...

``{{param:field}}`` in the text is replaced by the run's value of that
setting, so a card says what *this* run did ("thresholded at the 95th
percentile of 200 shuffles") rather than what the defaults would.

:func:`metrics_for` says which cards a figure in the viewer is about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

__all__ = ["MetricInfo", "METRICS_DIR", "SETTINGS_DIR", "all_metrics", "lookup",
           "render_markdown", "metrics_for"]

METRICS_DIR = Path(__file__).resolve().parent / "gui" / "assets" / "metrics"
#: The same kind of card about the settings of a run, read the same way. Their
#: front matter adds ``tab`` and ``labels`` (the GUI texts the card explains;
#: semicolon-separated) and ``params`` (the Params fields).
SETTINGS_DIR = Path(__file__).resolve().parent / "gui" / "assets" / "settings"

_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)
_PARAM = re.compile(r"\{\{\s*param:([A-Za-z0-9_]+)\s*\}\}")


@dataclass(frozen=True)
class MetricInfo:
    """One card: its keys, its place, and its text (Markdown, placeholders kept)."""

    key: str
    name: str
    body: str
    also: tuple[str, ...] = ()
    level: str = "concept"
    family: str = ""
    image: str | None = None
    related: tuple[str, ...] = ()
    path: Path | None = field(default=None, compare=False)
    #: Every front-matter entry, as written (lower-cased names).
    meta: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def labels(self) -> tuple[str, ...]:
        """The GUI texts a settings card explains (``labels:``, split on ";")."""
        return tuple(t.strip() for t in self.meta.get("labels", "").split(";") if t.strip())

    @property
    def keys(self) -> tuple[str, ...]:
        return (self.key, *self.also)

    @property
    def summary(self) -> str:
        """The text before the first heading."""
        return self.body.split("\n## ", 1)[0].strip()


def _split_list(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(",") if part.strip())


def parse(text: str, path: Path | None = None) -> MetricInfo:
    """A card from its file's text. Raises ``ValueError`` without a key and name."""
    match = _FRONT.match(text.lstrip("﻿"))
    if match is None:
        raise ValueError(f"{path or 'card'}: no front matter")
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.split("  #", 1)[0].rstrip()
        if ":" in line:
            name, value = line.split(":", 1)
            meta[name.strip().lower()] = value.strip()
    if not meta.get("key") or not meta.get("name"):
        raise ValueError(f"{path or 'card'}: front matter needs key and name")
    return MetricInfo(
        key=meta["key"], name=meta["name"], body=match.group(2).strip(),
        also=_split_list(meta.get("also", "")), level=meta.get("level", "concept"),
        family=meta.get("family", ""), image=meta.get("image") or None,
        related=_split_list(meta.get("related", "")), path=path, meta=meta)


@lru_cache(maxsize=4)
def _load(directory: str) -> tuple[dict[str, MetricInfo], dict[str, MetricInfo]]:
    """Every card in *directory*: by key, and by every key and alias."""
    cards: dict[str, MetricInfo] = {}
    index: dict[str, MetricInfo] = {}
    for path in sorted(Path(directory).glob("*.md")):
        try:
            card = parse(path.read_text(encoding="utf-8"), path)
        except (OSError, ValueError):
            continue
        cards[card.key] = card
    # A card's own key wins over another card's alias of the same name.
    for card in cards.values():
        for alias in card.also:
            index.setdefault(alias, card)
    for card in cards.values():
        index[card.key] = card
    return cards, index


def all_metrics(directory: Path | None = None) -> dict[str, MetricInfo]:
    return dict(_load(str(directory or METRICS_DIR))[0])


def lookup(key: str | None, directory: Path | None = None) -> MetricInfo | None:
    """The card for *key* — a card's key or one it lists under ``also`` —
    matched exactly, then ignoring case."""
    if not key:
        return None
    index = _load(str(directory or METRICS_DIR))[1]
    if key in index:
        return index[key]
    folded = {k.lower(): v for k, v in index.items()}
    return folded.get(str(key).lower())


def _param_text(value) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_param_text(v) for v in value) or "none"
    if value is None:
        return "None"
    if value == "":
        return "(empty)"
    return str(value)


def render_markdown(card: MetricInfo, params=None) -> str:
    """The card's text with each ``{{param:x}}`` replaced by the run's value.

    Without *params* (or for a setting the run does not have) the setting's
    name is shown instead, so the text still says which setting it is.
    """
    def value(match: re.Match) -> str:
        name = match.group(1)
        if params is not None:
            got = params.get(name, _MISSING) if isinstance(params, dict) \
                else getattr(params, name, _MISSING)
            if got is not _MISSING:
                return f"`{_param_text(got)}`"
        return f"`{name}`"

    return _PARAM.sub(value, card.body)


_MISSING = object()


# ── which cards a figure is about ─────────────────────────────────────────────

#: Words in a spatial / circular network plot's name → the node measure.
_NETWORK_WORDS = (
    ("Nodedegree", "ND"), ("Nodestrength", "NS"),
    ("Betweennesscentrality", "BC"), ("Participationcoefficient", "PC"),
    ("Localefficiency", "Eloc"), ("Averagecontrollability", "aveControl"),
    ("Modalcontrollability", "modalControl"), ("NodeCartography", "NC"),
    ("Module", "nMod"), ("Zscore", "Z"), ("Withinmodule", "Z"),
    ("TemporalAutocorrelation", "TA"), ("SpatialAutocorrelation", "SA"),
)

#: Words in an activity figure's name → its card, first match wins.
_ACTIVITY_WORDS = (
    ("NetworkBurst", "networkbursts"), ("NBurst", "networkbursts"),
    ("ISI", "ISI"), ("Burst", "bursts"), ("FractSpikes", "bursts"),
    ("Event", "events"), ("Amplitude", "events"),
    ("FiringRate", "FR"), ("Heatmap", "FR"), ("Raster", "FR"), ("Rate", "FR"),
)


def _network_figure(name: str) -> dict[str, str]:
    """Roles of a recording's network figure: its title, and for a spatial
    plot the node size ("size") and node colour ("colour") measures."""
    if "ConnectivityStats" in name or "ProbThresh" in name or "EdgeThreshold" in name:
        return {"title": "edges", "edges": "edges"}
    if "MeanImageAndNetwork" in name:       # CAT-NAP: edges over the cells' image
        return {"title": "edges", "edges": "edges", "size": "ND"}
    if "GraphMetricsByNode" in name:
        return {"title": "ND", "edges": "edges"}
    if "NodeCartography" in name or "Cartography" in name:
        return {"title": "NC", "colour": "NC", "category": "NC", "edges": "edges"}
    if "Autocorrelation" in name or "_SA" in name or "_TA" in name:
        key = "TA" if "Temporal" in name or "_TA" in name else "SA"
        return {"title": key}
    plot = re.split(r"NetworkPlot", name, maxsplit=1)
    if len(plot) == 2:
        rest, found = plot[1], []
        for word, key in _NETWORK_WORDS:
            at = rest.find(word)
            if at >= 0:
                found.append((at, key))
                rest = rest[:at] + " " * len(word) + rest[at + len(word):]
        keys = [key for _at, key in sorted(found)]
        size = keys[0] if keys else "ND"
        colour = keys[1] if len(keys) > 1 else None
        roles = {"title": colour or size, "size": size, "edges": "edges"}
        if colour:
            roles["colour"] = colour
            roles["category"] = colour
        return roles
    return {}


def _activity_figure(name: str) -> dict[str, str]:
    # Case matters: "ISIwithinBurst" holds "nBurst", not "NBurst".
    for word, key in _ACTIVITY_WORDS:
        if word in name:
            return {"title": key, "colour": key}
    return {}


def metrics_for(request: dict | None) -> dict[str, str]:
    """Which card each part of a viewer figure is about, by role.

    *request* is what the results viewer draws a figure from. The roles are
    ``"title"`` (what the figure as a whole shows: also what its ⓘ button
    opens) and, where the figure has them, ``"size"``, ``"colour"``,
    ``"category"`` and ``"edges"`` for parts of its legend. Only roles with a
    card are returned; an empty dict means there is nothing to explain.
    """
    if not request:
        return {}
    kind = request.get("kind")
    name = str(request.get("name", ""))
    roles: dict[str, str] = {}
    if kind == "network":
        roles = _network_figure(name)
    elif kind == "edge_check":
        roles = {"title": "edges"}
    elif kind == "activity":
        roles = _activity_figure(name)
    elif kind == "comparison":
        roles = {"title": str(request.get("metric", ""))}
    elif kind == "lag_series":
        series, key = str(request.get("series", "")), str(request.get("key", ""))
        if series.startswith("cartography") or series == "density_landscape":
            roles = {"title": "NC"}
        else:
            roles = {"title": key}
    elif kind == "stim":
        roles = _network_figure(name) if "NetworkPlot" in name else {}
    out: dict[str, str] = {}
    for role, key in roles.items():
        card = lookup(key)
        if card is not None:
            out[role] = card.key
    return out
