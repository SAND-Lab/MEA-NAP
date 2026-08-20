"""The viewer's controls describe the run, not the viewer.

Opening a bundle used to show a generic control set: every default read off a
fresh ``NetworkStyle``. That was wrong as *display* — the panel claimed a
node-size scale of 1.0 for a CAT-NAP run drawn on ``"auto"`` — and worse as
*behaviour*, because the page sends only the controls that differ from the
defaults it was handed. Change the colormap and the request carried a colormap
and nothing else, so the figure was rebuilt from class defaults and the node
sizing the run used was silently thrown away.

So the baseline has to come from the run, in all three places that touch it:
the schema the page builds its form from, the parser that reads a request
against it, and the merge that turns overrides into a style.

Everything here runs on the synthetic bundle from ``test_bundle_render``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "python"))

import numpy as np  # noqa: E402

from meanap.network_plot import NetworkStyle  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline.render import (  # noqa: E402
    available_figures, render_figure, style_from_overrides,
)
from meanap.viewer.controls import control_schema, parse_overrides  # noqa: E402
from meanap.viewer.server import ViewerService  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def catnap_params() -> Params:
    p = Params()
    p.suite2p_mode = True
    return p


# ── What the run drew with ────────────────────────────────────────────────────

print("\nNetworkStyle.for_run")

check("a CAT-NAP run sizes nodes automatically",
      NetworkStyle.for_run(catnap_params()).node_size_scale == "auto", "")
check("an ephys run does not, whatever twop_auto_node_size says",
      NetworkStyle.for_run(Params()).node_size_scale == 1.0
      and Params().twop_auto_node_size is True,
      "twop_auto_node_size defaults True but applies only to suite2p runs")

manual = catnap_params()
manual.twop_auto_node_size = False
check("turning the setting off is respected",
      NetworkStyle.for_run(manual).node_size_scale == 1.0, "")


# ── The form shows it ─────────────────────────────────────────────────────────

print("\nThe control schema")

cat_style = NetworkStyle.for_run(catnap_params())
schema = {c["key"]: c["default"] for c in control_schema(cat_style)}

check("node sizing is shown as the mode it actually is",
      schema["node_size_mode"] == "Auto", str(schema.get("node_size_mode")))
check("an ephys run shows Manual instead",
      {c["key"]: c["default"] for c in
       control_schema(NetworkStyle.for_run(Params()))}["node_size_mode"] == "Manual",
      "")
check("'unlimited edges' is shown as the 0 the UI means by it",
      schema["max_edges"] == 0, str(schema["max_edges"]))
check("a control with no run-specific value still has one",
      schema["colormap"] == NetworkStyle().colormap, str(schema["colormap"]))
check("omitting the style falls back to the class defaults",
      {c["key"]: c["default"] for c in control_schema()}["node_size_mode"] == "Manual",
      "")


# ── A request is read against it ──────────────────────────────────────────────

print("\nReading a request")

check("an untouched panel asks for nothing at all",
      parse_overrides({}, cat_style) == {}, str(parse_overrides({}, cat_style)))

# The heart of it: the page sends only what changed.
only_colour = parse_overrides({"colormap": ["plasma"]}, cat_style)
check("changing the colormap asks only for the colormap",
      only_colour == {"colormap": "plasma"}, str(only_colour))

merged = style_from_overrides(only_colour, catnap_params())
check("…and merging it keeps the run's node sizing",
      merged.node_size_scale == "auto", str(merged.node_size_scale))
check("…while actually applying the colormap",
      merged.colormap == "plasma", merged.colormap)

# Switching off an automatic sizing you can now see.
to_manual = parse_overrides(
    {"node_size_mode": ["Manual"], "node_size_scale": ["2"]}, cat_style)
check("switching to Manual reaches the style as a number",
      to_manual == {"node_size_scale": 2.0}, str(to_manual))
back_to_auto = parse_overrides({"node_size_mode": ["Auto"]},
                               NetworkStyle.for_run(Params()))
check("and an ephys run can be switched to Auto",
      back_to_auto == {"node_size_scale": "auto"}, str(back_to_auto))

check("0 edges still means unlimited rather than none",
      parse_overrides({"max_edges": ["0"]}, cat_style) == {}, "")
check("a real edge cap still comes through",
      parse_overrides({"max_edges": ["25"]}, cat_style) == {"max_edges": 25}, "")

# Without a baseline the old behaviour is still what you get, which is right
# for a caller with no run in hand.
check("no baseline given falls back to the class defaults",
      style_from_overrides({"colormap": "plasma"}).node_size_scale == 1.0, "")


# ── And the pixels agree ──────────────────────────────────────────────────────

print("\nEnd to end, on a real bundle")

from test_bundle_render import _run  # noqa: E402

tmp = Path(tempfile.mkdtemp())
root = _run(tmp, "RunStyle", express=True)
svc = ViewerService(root)
try:
    ctx = svc.ctx
    rec = next(iter(ctx.recordings))
    lag = ctx.lags(rec)[0]
    net = next(f.name.format(lag=lag) for f in available_figures(ctx, rec, lag)
               if "NetworkPlot" in f.name)

    served = {c["key"]: c["default"] for c in svc.manifest()["controls"]}
    check("the bundle's own manifest carries the run's sizing",
          served["node_size_mode"] == "Auto"
          and ctx.params.suite2p_mode, str(served["node_size_mode"]))

    out = Path(tempfile.mkdtemp())

    def render(tag: str, overrides) -> Path:
        d = out / tag
        d.mkdir()
        return render_figure(ctx, rec, lag, net, d, fmt="png",
                             overrides=overrides or None)

    def geometry(path: Path) -> np.ndarray:
        """Which pixels are drawn on — the shape of the figure, not its colours."""
        import matplotlib.image as mpimg

        a = mpimg.imread(path)[..., :3]
        return (a.max(axis=2) - a.min(axis=2) > 0.02) | (a.mean(axis=2) < 0.97)

    as_run = geometry(render("as_run", {}))
    recoloured = geometry(render("recoloured",
                                 parse_overrides({"colormap": ["plasma"]},
                                                 svc.run_style())))
    # What the viewer used to send: a style rebuilt from class defaults.
    old_way = geometry(render("old_way",
                              {"colormap": "plasma", "node_size_scale": 1.0}))

    check("recolouring leaves every node and edge exactly where it was",
          int((as_run != recoloured).sum()) == 0,
          f"{int((as_run != recoloured).sum())} pixels moved")
    check("…which is the bug: the old baseline moved thousands of them",
          int((as_run != old_way).sum()) > 1000,
          f"only {int((as_run != old_way).sum())} pixels differ — "
          "the regression this guards may no longer be reachable")
finally:
    svc.close()


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All run-styling checks passed.")
