"""Test the labels and y-axis ranges of the group-comparison violins.

Run from the repo root::

    uv run python python/test_comparison_axes.py

MATLAB's ``plotHalfViolinByX.m`` draws every comparison violin on the metric's
feasible range (``Params.networkLevelNetMetCustomBounds``): density on [0, 1],
node degree from zero, and so on. ``PlotEphysStats.m`` does the same for the
activity metrics. The Python port drew everything autoscaled, and a few of its
axis labels named the wrong quantity. These checks pin both, at the level the
viewer and the pipeline share — the metric tables, the bounds lookup, and the
axis a drawn figure actually ends up with.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline import plotting_step2 as p2  # noqa: E402
from meanap.pipeline import plotting_step4 as p4  # noqa: E402
from meanap.pipeline.render import comparison_bounds  # noqa: E402

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── A. Labels ─────────────────────────────────────────────────────────────────

def _label_checks() -> list[Check]:
    rec = p4.NETMET_REC_METRICS
    checks: list[Check] = []
    for key in ("sigEdgesMean", "sigEdgesTop10"):
        checks.append((f"{key} is labelled as an edge *weight*",
                       "edge weight" in rec[key].lower(), rec[key]))
    for i in range(1, 7):
        lab = rec[f"NCpn{i}"]
        checks.append((f"NCpn{i} is a proportion, not a percent: {lab!r}",
                       "%" not in lab and "proportion" in lab.lower(), lab))
    return checks


# ── B. Bounds lookup ──────────────────────────────────────────────────────────

def _bounds_checks() -> list[Check]:
    checks: list[Check] = []
    known = set(p4.NETMET_REC_METRICS) | set(p4.NETMET_NODE_METRICS)
    stray = sorted(set(p4.NETMET_BOUNDS) - known)
    checks.append(("every network bound names a metric the plotter draws",
                   not stray, f"unknown: {stray}"))
    known2 = set(p2.EPHYS_REC_METRICS) | set(p2.EPHYS_NODE_METRICS)
    stray2 = sorted(set(p2.EPHYS_BOUNDS) - known2)
    checks.append(("every activity bound names a metric the plotter draws",
                   not stray2, f"unknown: {stray2}"))

    unit = ("Dens", "Eglob", "ElocMean", "PCmean", "Eloc", "PC", "BC", "MEW",
            "NCpn1", "NCpn6", "nComponentsRelNS")
    for m in unit:
        checks.append((f"{m} is drawn on [0, 1]", p4.netmet_bounds(m) == (0, 1),
                       repr(p4.netmet_bounds(m))))
    for m in ("sigEdgesMean", "sigEdgesTop10", "NDmean", "NS", "PL", "Q"):
        checks.append((f"{m} starts at 0, top left to the data",
                       p4.netmet_bounds(m) == (0, None), repr(p4.netmet_bounds(m))))
    checks.append(("ND is capped at (largest network - 1)",
                   p4.netmet_bounds("ND", n_nodes=24) == (0, 23),
                   repr(p4.netmet_bounds("ND", n_nodes=24))))
    checks.append(("ND without a node count is left to the data on top",
                   p4.netmet_bounds("ND") == (0, None), repr(p4.netmet_bounds("ND"))))
    for m in ("Z", "SW", "SWw", "aN"):
        checks.append((f"{m} has no pinned range", p4.netmet_bounds(m) is None,
                       repr(p4.netmet_bounds(m))))
    checks.append(("fraction of bursts in network bursts on [0, 1]",
                   p2.ephys_bounds("fracInNburst") == (0, 1), ""))
    checks.append(("unit fraction of spikes in bursts on [0, 1]",
                   p2.ephys_bounds("channelFracSpikesInBursts") == (0, 1), ""))
    checks.append(("mean firing rate from 0",
                   p2.ephys_bounds("FRmean") == (0, None), ""))

    # The viewer's lookup resolves the same answers, with the node-degree cap
    # read from the batch's node frame.
    df_node = pd.DataFrame({"Channel": [1, 2, 3, 7, 5]})
    checks.append(("viewer lookup: network ND capped from the node frame",
                   comparison_bounds("network", "ND", df_node) == (0, 6), ""))
    checks.append(("viewer lookup: network Dens",
                   comparison_bounds("network", "Dens", df_node) == (0, 1), ""))
    checks.append(("viewer lookup: activity FR",
                   comparison_bounds("ephys_activity", "FR", pd.DataFrame()) == (0, None), ""))
    return checks


# ── C. The drawn axis ─────────────────────────────────────────────────────────

def _drawn_axis_checks() -> list[Check]:
    """Draw a violin whose data sit well inside [0, 1] and read the axis back."""
    checks: list[Check] = []
    rng = np.random.default_rng(0)
    rows = []
    for grp in ("WT", "KO"):
        for div in ("14", "21"):
            for i in range(6):
                rows.append({"FileName": f"{grp}_{div}_{i}", "Grp": grp, "DIV": div,
                             "Dens": 0.4 + 0.05 * rng.standard_normal(),
                             "NS": 3.0 + rng.standard_normal()})
    df = pd.DataFrame(rows)

    captured: list[tuple[float, float]] = []
    real_savefig = p4.savefig

    def spy(fig, path, **kw):
        captured.append(tuple(fig.axes[0].get_ylim()))
        real_savefig(fig, path, **kw)

    p4.savefig = spy
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p4.plot_half_violin_by_x(df, "Dens", "Density", "group", out / "a.png",
                                     ylim=(0, 1))
            p4.plot_half_violin_by_x(df, "Dens", "Density", "DIV", out / "b.png",
                                     ylim=(0, 1))
            p4.plot_half_violin_by_x(df, "NS", "Node Strength", "group", out / "c.png",
                                     ylim=(0, None))
            p4.plot_half_violin_by_x(df, "NS", "Node Strength", "group", out / "d.png")
            written = sorted(p.name for p in out.iterdir())
    finally:
        p4.savefig = real_savefig

    checks.append(("all four figures written", written == ["a.png", "b.png", "c.png", "d.png"],
                   str(written)))
    if len(captured) == 4:
        a, b, c, d = captured
        checks.append(("Dens by group drawn on exactly [0, 1]", a == (0.0, 1.0), repr(a)))
        checks.append(("Dens by age drawn on exactly [0, 1]", b == (0.0, 1.0), repr(b)))
        checks.append(("NS (0, None): bottom pinned at 0", c[0] == 0.0, repr(c)))
        checks.append(("NS (0, None): top is the autoscaled top", c[1] == d[1], f"{c} vs {d}"))
        checks.append(("no ylim: autoscaled bottom is not 0 (so the pin did something)",
                       d[0] != 0.0, repr(d)))
    else:
        checks.append(("four axes captured", False, f"got {len(captured)}"))
    return checks


def main() -> int:
    total_pass = total_n = 0
    for title, fn in (("Section A — labels:", _label_checks),
                      ("Section B — bounds lookup:", _bounds_checks),
                      ("Section C — the drawn axis:", _drawn_axis_checks)):
        n_pass, n = _report(title, fn())
        total_pass += n_pass
        total_n += n
    print(f"\n{'ALL PASSED' if total_pass == total_n else 'FAILURES'}: {total_pass}/{total_n}")
    return 0 if total_pass == total_n else 1


if __name__ == "__main__":
    sys.exit(main())
