"""Colours for the group-level comparison plots: ages and groups.

Two palettes run through every 2B/4B figure, and they are different kinds of
thing. **Ages** are ordered, so they take a sequential colormap sampled across
its range — a reader should be able to see which way time runs without reading
the legend. **Groups** are not ordered, so they take a categorical list, where
neighbouring colours being far apart is the whole point.

Both are configurable, with the defaults reproducing what the pipeline has
always drawn: ``flipud(viridis)`` for ages (``plotHalfViolinByX.m`` line 16) and
MATLAB's ``groupColors`` for groups. That default matters beyond taste — the
viewer's pixel-parity tests assert that an unstyled render equals the figure the
pipeline wrote, so :class:`ColorScheme` with no arguments must be a no-op.

A custom list always wins over a scheme, and cycles when it is shorter than the
number of ages or groups — running out of colours should repeat, not crash a
run twelve hours in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "AGE_SCHEMES", "GROUP_SCHEMES", "ColorScheme", "parse_colors",
]

RGB = tuple[float, float, float]

#: Sequential colormaps offered for ages. Perceptually uniform ones only: an
#: ordered variable read through a non-uniform map (jet, rainbow) invents
#: structure that isn't in the data. ``_r`` reverses the direction.
AGE_SCHEMES: dict[str, str] = {
    "viridis": "viridis",
    "viridis_r": "viridis_r",
    "plasma": "plasma",
    "plasma_r": "plasma_r",
    "cividis": "cividis",
    "magma": "magma",
    "inferno": "inferno",
    "grey": "Greys",
}

#: MATLAB's ``groupColors`` — the pipeline's historical default.
_MEANAP_GROUPS: tuple[RGB, ...] = (
    (0.996, 0.670, 0.318),
    (0.780, 0.114, 0.114),
    (0.459, 0.000, 0.376),
    (0.027, 0.306, 0.659),
    (0.5, 0.5, 0.5),
)

#: Okabe-Ito: eight hues distinguishable under all common colour-vision
#: deficiencies. Worth offering because a genotype comparison printed in a
#: paper will be read by someone who cannot separate the default red and green.
_OKABE_ITO: tuple[RGB, ...] = (
    (0.000, 0.447, 0.698),   # blue
    (0.902, 0.624, 0.000),   # orange
    (0.000, 0.620, 0.451),   # bluish green
    (0.800, 0.475, 0.655),   # reddish purple
    (0.337, 0.706, 0.914),   # sky blue
    (0.835, 0.369, 0.000),   # vermillion
    (0.941, 0.894, 0.259),   # yellow
    (0.000, 0.000, 0.000),   # black
)

_TAB10: tuple[RGB, ...] = (
    (0.122, 0.467, 0.706), (1.000, 0.498, 0.055), (0.173, 0.627, 0.173),
    (0.839, 0.153, 0.157), (0.580, 0.404, 0.741), (0.549, 0.337, 0.294),
    (0.890, 0.467, 0.761), (0.498, 0.498, 0.498), (0.737, 0.741, 0.133),
    (0.090, 0.745, 0.812),
)

#: Greyscale, for a figure that has to survive a black-and-white print.
_GREYS: tuple[RGB, ...] = (
    (0.15, 0.15, 0.15), (0.45, 0.45, 0.45), (0.65, 0.65, 0.65),
    (0.80, 0.80, 0.80), (0.30, 0.30, 0.30),
)

GROUP_SCHEMES: dict[str, tuple[RGB, ...]] = {
    "meanap": _MEANAP_GROUPS,
    "okabe-ito": _OKABE_ITO,
    "tab10": _TAB10,
    "grey": _GREYS,
}


def parse_colors(colors) -> list[RGB]:
    """Turn user-supplied colours into RGB triples.

    Accepts anything matplotlib names — ``#1f77b4``, ``#abc``, ``red``,
    ``tab:blue`` — as a list, or as one comma/space-separated string, which is
    how a query string and a text box deliver it.

    Raises :class:`ValueError` naming the offending entry. A mistyped colour
    should say so at the edge, not surface as a matplotlib traceback halfway
    through a batch.
    """
    from matplotlib.colors import to_rgb

    if colors is None:
        return []
    if isinstance(colors, str):
        colors = [c for c in colors.replace(",", " ").split() if c]
    out = []
    for c in colors:
        if isinstance(c, (tuple, list)):
            if len(c) not in (3, 4):
                raise ValueError(f"{c!r} is not a colour: expected 3 or 4 components")
            out.append(tuple(float(v) for v in c[:3]))
            continue
        try:
            out.append(tuple(to_rgb(c)))
        except (ValueError, TypeError):
            raise ValueError(
                f"{c!r} is not a colour. Use a hex code like '#1f77b4' or a "
                f"name like 'crimson'.") from None
    return out


def _sample(cmap_name: str, n: int, *, reverse_start: bool) -> list[RGB]:
    """*n* colours spread across a colormap.

    ``reverse_start`` samples 1→0, which is what ``flipud`` does in the MATLAB
    original: the bright end lands on the first (youngest) age.
    """
    import numpy as np
    from matplotlib import colormaps

    if n <= 0:
        return []
    cmap = colormaps[cmap_name]
    xs = np.linspace(1, 0, n) if reverse_start else np.linspace(0, 1, n)
    return [tuple(cmap(float(x))[:3]) for x in xs]


@dataclass(frozen=True)
class ColorScheme:
    """Which colours the age and group axes get.

    The no-argument instance reproduces the pipeline's historical palettes
    exactly, so passing one where none was passed before changes nothing.
    """

    age_scheme: str = "viridis"
    group_scheme: str = "meanap"
    #: Explicit colours, winning over the scheme when non-empty.
    age_colors: tuple = ()
    group_colors: tuple = ()

    def __post_init__(self):
        if self.age_scheme not in AGE_SCHEMES:
            raise ValueError(
                f"Unknown age colour scheme {self.age_scheme!r}; expected one of "
                f"{sorted(AGE_SCHEMES)}")
        if self.group_scheme not in GROUP_SCHEMES:
            raise ValueError(
                f"Unknown group colour scheme {self.group_scheme!r}; expected one "
                f"of {sorted(GROUP_SCHEMES)}")
        # Validate here rather than at draw time: the run should fail on the
        # bad colour, not after an hour of computation.
        object.__setattr__(self, "age_colors", tuple(parse_colors(self.age_colors)))
        object.__setattr__(self, "group_colors", tuple(parse_colors(self.group_colors)))

    @classmethod
    def from_params(cls, params) -> "ColorScheme":
        """Read the scheme off a :class:`~meanap.params.Params`."""
        return cls(
            age_scheme=getattr(params, "age_color_scheme", "viridis") or "viridis",
            group_scheme=getattr(params, "group_color_scheme", "meanap") or "meanap",
            age_colors=tuple(getattr(params, "age_colors", ()) or ()),
            group_colors=tuple(getattr(params, "group_colors", ()) or ()),
        )

    def ages(self, n: int) -> list[RGB]:
        """*n* colours for the ages, youngest first."""
        if self.age_colors:
            return _cycle(self.age_colors, n)
        return _sample(AGE_SCHEMES[self.age_scheme], n, reverse_start=True)

    def groups(self, n: int) -> list[RGB]:
        """*n* colours for the groups, in the batch's group order."""
        if self.group_colors:
            return _cycle(self.group_colors, n)
        return _cycle(GROUP_SCHEMES[self.group_scheme], n)


def _cycle(colors, n: int) -> list[RGB]:
    return [tuple(colors[i % len(colors)]) for i in range(n)]


#: The default, shared so callers that were passed nothing don't each build one.
DEFAULT_SCHEME = ColorScheme()
