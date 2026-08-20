"""The styling controls a viewer exposes, and how a request maps onto them.

One declaration, used three ways: the page builds its form from it, the server
coerces and validates query parameters against it, and the tests check that
every knob is reachable. Keeping those in one place is what stops a control
from existing in the UI but doing nothing on the backend — the failure mode
that makes an interactive viewer untrustworthy.

The values map onto :class:`~meanap.network_plot.NetworkStyle`, so they apply
to the spatial network plots only. Violin plots and cartography scatters don't
read them, which is why the family gallery hides this panel outright rather
than showing controls that quietly do nothing.

**Defaults belong to the run, not to this module.** Each control's ``default``
is the value *the run being viewed* was drawn with — :meth:`NetworkStyle.for_run`
— so opening a bundle shows the settings that produced its figures rather than
a generic set that may never have applied. That matters beyond display: the
page sends only values that differ from the default it was given, so a baseline
taken from the wrong place would make a request that changes the colormap also
quietly reset node sizing to a value the run never used. The declarations below
carry the *class* defaults purely as a fallback for callers with no run in hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from meanap.network_plot import (
    EDGE_THRESHOLD_METHODS, LAYOUT_OPTIONS, NetworkStyle,
)

__all__ = [
    "COMPARISON_CONTROLS", "CONTROLS", "Control", "comparison_control_schema",
    "control_schema", "parse_comparison_overrides", "parse_overrides",
]

#: Imported lazily-by-value so this module stays importable without matplotlib
#: being touched at import time; the names are a closed set either way.
_AGE_SCHEME_NAMES = (
    "viridis", "viridis_r", "plasma", "plasma_r", "cividis", "magma",
    "inferno", "grey",
)
_GROUP_SCHEME_NAMES = ("meanap", "okabe-ito", "tab10", "grey")

#: Colormaps offered for the node-colour metric. Perceptually uniform ones
#: first — they are the defensible choice for a continuous metric — with the
#: common diverging and legacy options after.
COLORMAPS = [
    "viridis", "plasma", "inferno", "magma", "cividis",
    "coolwarm", "RdBu_r", "Spectral_r", "turbo", "jet",
]

NODE_SCALING_METHODS = ["Linear", "Log2", "Log10", "Square", "Cube", "Power"]

#: How ``NetworkStyle.node_size_scale`` is arrived at. "Auto" is the string
#: ``"auto"`` in the style; "Manual" means take the number beside it.
NODE_SIZE_MODES = ["Auto", "Manual"]


@dataclass(frozen=True)
class Control:
    """One control: how to render it, and how to coerce what comes back."""

    key: str
    label: str
    kind: str                      # "number" | "select"
    default: object
    options: list = field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    #: Shown under the control in the page.
    help: str = ""

    def coerce(self, raw: str):
        """Turn a query-string value into the type the style expects."""
        if self.kind == "select":
            if raw not in self.options:
                raise ValueError(
                    f"{self.key}: {raw!r} is not one of {self.options}")
            return raw
        if self.kind == "colors":
            # A list of colours, however the user typed it. Validated here so a
            # typo comes back as a 400 naming it, not a matplotlib traceback.
            from meanap.pipeline.palette import parse_colors

            try:
                parse_colors(raw)
            except ValueError as e:
                raise ValueError(f"{self.key}: {e}") from None
            return [c for c in raw.replace(",", " ").split() if c]
        value = float(raw)
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{self.key}: {value} is below {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{self.key}: {value} is above {self.maximum}")
        return int(value) if isinstance(self.default, int) else value


_defaults = NetworkStyle()

CONTROLS: tuple[Control, ...] = (
    Control("layout", "Node layout", "select", _defaults.layout,
            options=list(LAYOUT_OPTIONS),
            help="Electrode/cell positions, or a layout derived from topology."),
    Control("colormap", "Node colour map", "select", _defaults.colormap,
            options=list(COLORMAPS),
            help="Applied to the node-colour metric."),
    Control("edge_threshold_method", "Edge threshold by", "select",
            _defaults.edge_threshold_method, options=list(EDGE_THRESHOLD_METHODS),
            help="How the threshold below is interpreted."),
    Control("edge_threshold", "Edge threshold", "number", 0.0,
            minimum=0.0, maximum=100.0, step=0.01,
            help="A weight for 'Absolute value', otherwise a percentile."),
    Control("max_edges", "Max edges drawn", "number", 0,
            minimum=0, maximum=100000, step=25,
            help="Keeps only the strongest N edges. 0 draws all of them."),
    # CAT-NAP draws with node_size_scale="auto", which no number box can hold.
    # Splitting the mode out is what lets the panel show what the run did, and
    # lets someone switch off a sizing they could not previously see.
    Control("node_size_mode", "Node size", "select", "Manual",
            options=list(NODE_SIZE_MODES),
            help="'Auto' sizes nodes from how densely they are packed, which "
                 "two-photon fields need. CAT-NAP runs use it by default."),
    Control("node_size_scale", "Node size scale", "number", 1.0,
            minimum=0.05, maximum=20.0, step=0.05,
            help="Ignored while node size is on 'Auto'."),
    Control("node_scaling_method", "Node scaling", "select",
            _defaults.node_scaling_method, options=NODE_SCALING_METHODS,
            help="How the size metric maps onto node radius."),
    Control("node_scaling_power", "Scaling power", "number",
            _defaults.node_scaling_power, minimum=0.1, maximum=6.0, step=0.1,
            help="Exponent used when scaling is 'Power'."),
    Control("min_node_size", "Min node size", "number", _defaults.min_node_size,
            minimum=0.0, maximum=10.0, step=0.01),
    Control("min_edge_width", "Min edge width", "number", _defaults.min_edge_width,
            minimum=0.0, maximum=10.0, step=0.001),
    Control("max_edge_width", "Max edge width", "number", _defaults.max_edge_width,
            minimum=0.1, maximum=30.0, step=0.1),
)


#: Controls for the group-level (2B/4B) comparison figures. A separate set from
#: :data:`CONTROLS` because they map onto ``Params`` fields the violin and line
#: plots read, not onto ``NetworkStyle`` — the two panels are never shown at
#: once, and mixing them would offer node-size knobs on a violin plot.
COMPARISON_CONTROLS: tuple[Control, ...] = (
    Control("age_color_scheme", "Age colours", "select", "viridis",
            options=list(_AGE_SCHEME_NAMES),
            help="Ages are ordered, so they take a sequential colormap. "
                 "'_r' reverses which end is oldest."),
    Control("age_colors", "Custom age colours", "colors", [],
            help="Overrides the scheme. Hex codes or names, comma-separated, "
                 "oldest last. Cycles if you give fewer than there are ages."),
    Control("group_color_scheme", "Group colours", "select", "meanap",
            options=list(_GROUP_SCHEME_NAMES),
            help="Groups are unordered, so they take a categorical palette. "
                 "'okabe-ito' stays distinguishable with colour-vision deficiency."),
    Control("group_colors", "Custom group colours", "colors", [],
            help="Overrides the scheme, in the group order on the Data tab."),
)


def control_default(control: Control, style: NetworkStyle):
    """What *control* reads when a figure was drawn with *style*.

    Two controls do not map one-to-one onto a style field: ``max_edges``
    spells "unlimited" as ``None`` in the style and ``0`` in the UI, and the
    single ``node_size_scale`` field is presented as a mode plus a number.
    """
    if control.key == "max_edges":
        return style.max_edges or 0
    if control.key == "node_size_mode":
        return "Auto" if style.node_size_scale == "auto" else "Manual"
    if control.key == "node_size_scale":
        # An auto run has no meaningful number to show, so the box keeps the
        # neutral 1.0 it would start from on switching to Manual.
        return (1.0 if style.node_size_scale == "auto"
                else float(style.node_size_scale))
    return getattr(style, control.key, control.default)


def control_schema(style: NetworkStyle | None = None) -> list[dict]:
    """The controls as plain data, for the page to build its form from.

    *style* is the run's own styling (:meth:`NetworkStyle.for_run`); each
    control's ``default`` is read from it, so the panel opens showing what the
    run used. Omitting it falls back to the class defaults, which is only right
    when there is no run to speak of.
    """
    style = style if style is not None else NetworkStyle()
    return _schema(CONTROLS, style)


def comparison_control_schema() -> list[dict]:
    """The comparison-figure controls, as plain data.

    No style argument: these map onto ``Params`` colour fields rather than onto
    a ``NetworkStyle``, and the run's values for them already reach the page
    through the parameters panel.
    """
    return _schema(COMPARISON_CONTROLS)


def _schema(controls, style: NetworkStyle | None = None) -> list[dict]:
    return [
        {
            "key": c.key, "label": c.label, "kind": c.kind,
            "default": c.default if style is None else control_default(c, style),
            "options": c.options, "min": c.minimum, "max": c.maximum,
            "step": c.step, "help": c.help,
        }
        for c in controls
    ]


def parse_comparison_overrides(query: dict[str, list[str]]) -> dict:
    """Extract the colour overrides for a comparison or across-lag figure.

    Same contract as :func:`parse_overrides`: only non-default values come
    back, so an unstyled request builds no override at all and stays
    byte-identical to the pipeline's figure.
    """
    overrides: dict = {}
    for control in COMPARISON_CONTROLS:
        raw = query.get(control.key, [None])[0]
        if raw is None or raw == "":
            continue
        value = control.coerce(raw)
        if value == control.default:
            continue
        overrides[control.key] = value
    return overrides


def parse_overrides(query: dict[str, list[str]],
                    style: NetworkStyle | None = None) -> dict:
    """Extract and coerce styling overrides from a parsed query string.

    *style* is the run's own styling, and is the baseline the request is read
    against — the same one :func:`control_schema` built the form from. Only
    values that differ from it come back, which is what keeps the viewer's
    untouched view byte-identical to the figure the pipeline drew: an empty
    dict means no ``NetworkStyle`` is built at all.

    Reading against the *class* defaults instead was the bug this argument
    exists to prevent. A page that sends one changed control sends only that
    control; anything absent has to mean "as the run drew it", and it did not
    when the two sides disagreed about what that was.
    """
    style = style if style is not None else NetworkStyle()

    # Start from what the run used, then let the query speak. Absent or blank
    # is not "no opinion" here — it is the run's value, which is the same thing
    # once the baseline is right.
    chosen: dict = {}
    for control in CONTROLS:
        raw = query.get(control.key, [None])[0]
        chosen[control.key] = (control.coerce(raw) if raw not in (None, "")
                               else control_default(control, style))

    # Fold the two node-size controls back into the one style field. An
    # explicit scale is manual intent even when the mode is absent, so that a
    # caller (or an older URL) saying only `node_size_scale=2` still gets 2
    # rather than having it overwritten by the run's automatic sizing.
    asked_mode = query.get("node_size_mode", [None])[0]
    asked_scale = query.get("node_size_scale", [None])[0]
    chosen.pop("node_size_mode", None)   # not a style field; it only picks one
    if asked_mode == "Auto" or (asked_mode is None and not asked_scale
                                and style.node_size_scale == "auto"):
        chosen["node_size_scale"] = "auto"
    # 0 means "unlimited" in the UI; NetworkStyle spells that None.
    chosen["max_edges"] = chosen["max_edges"] or None

    return {k: v for k, v in chosen.items() if v != getattr(style, k)}
