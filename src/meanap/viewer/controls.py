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
"""

from __future__ import annotations

from dataclasses import dataclass, field

from meanap.network_plot import (
    EDGE_THRESHOLD_METHODS, LAYOUT_OPTIONS, NetworkStyle,
)

__all__ = ["CONTROLS", "Control", "control_schema", "parse_overrides"]

#: Colormaps offered for the node-colour metric. Perceptually uniform ones
#: first — they are the defensible choice for a continuous metric — with the
#: common diverging and legacy options after.
COLORMAPS = [
    "viridis", "plasma", "inferno", "magma", "cividis",
    "coolwarm", "RdBu_r", "Spectral_r", "turbo", "jet",
]

NODE_SCALING_METHODS = ["Linear", "Log2", "Log10", "Square", "Cube", "Power"]


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
    Control("node_size_scale", "Node size scale", "number", 1.0,
            minimum=0.05, maximum=20.0, step=0.05),
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


def control_schema() -> list[dict]:
    """The controls as plain data, for the page to build its form from."""
    return [
        {
            "key": c.key, "label": c.label, "kind": c.kind, "default": c.default,
            "options": c.options, "min": c.minimum, "max": c.maximum,
            "step": c.step, "help": c.help,
        }
        for c in CONTROLS
    ]


def parse_overrides(query: dict[str, list[str]]) -> dict:
    """Extract and coerce styling overrides from a parsed query string.

    Only values that differ from the default are returned. That matters for
    more than tidiness: an empty override dict means *no* ``NetworkStyle`` is
    built, which is what keeps the viewer's default view byte-identical to the
    figure the pipeline drew.
    """
    overrides: dict = {}
    for control in CONTROLS:
        raw = query.get(control.key, [None])[0]
        if raw is None or raw == "":
            continue
        value = control.coerce(raw)
        if value == control.default:
            continue
        # 0 means "unlimited" in the UI; NetworkStyle spells that None.
        if control.key == "max_edges" and not value:
            continue
        overrides[control.key] = value
    return overrides
