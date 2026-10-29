"""Draw the run-time figures for docs/python/performance.md.

Run from the repo root::

    uv run python python/plot_performance_figures.py

Every number is the bundled example run (``ExampleData/``, recordings A2/A3:
64 electrodes, 10 min at 12.5 kHz; lags 10/25/50 ms; 200 shuffles; steps 1-4)
on the same 16-core AMD Ryzen AI Max+ 395. Where each came from is noted beside
it. Writes a light and a dark version of each figure, for the docs theme's
light/dark switch.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).parent.parent / "docs" / "python" / "imgs" / "performance"

STEPS = ["Step 1: spikes", "Step 2: activity", "Step 3: connectivity", "Step 4: networks"]

#: (label, [step 1, step 2, step 3, step 4] in seconds)
MATLAB_VS_PYTHON = [
    # python/parityRun/MEApipeline_timingBenchmark.m, R2025b, 16-worker parpool, 2026-10-25
    ("MATLAB", [445, 62, 9, 377]),
    # MEA-NAP 1.18.0, 2026-10-29, all 16 cores
    ("Python", [17.1, 7.0, 2.4, 55.1]),
    ("Python, express mode", [15.5, 0.0, 2.5, 12.5]),
]

#: (label, full run steps, express-mode steps or None if the version had no
#: express mode). Express mode arrived in August 2026.
VERSIONS = [
    # 76da1ed, 2026-07-09: the first complete port (PIPELINE_PORT_STATUS.md, "Original comparison")
    ("July 2026: first complete port", [568.8, 6.2, 80.2, 511.7], None),
    # d91ccb3, 2026-07-09 ("Optimization pass — 3.3x faster end-to-end")
    ("July 2026: threads, numba, faster plots", [103.6, 6.4, 42.7, 197.3], None),
    # 356fc0f (1.14.1), full and express re-run 2026-10-29
    ("1.14.1: dense-network fixes", [38.8, 7.3, 4.9, 185.4], [37.6, 0.0, 4.9, 137.9]),
    # b82d62e (1.15.0): full run 2026-10-25, back to back with the MATLAB run above;
    # express re-run 2026-10-29
    ("1.15.0: parallel STTC, NMF, null models", [39.6, 7.6, 1.8, 76.6], [37.3, 0.0, 3.1, 12.5]),
    # 423e892 (1.15.1), re-run 2026-10-29
    ("1.15.1: faster spike detection", [16.3, 7.1, 3.1, 56.0], [14.8, 0.0, 2.3, 12.3]),
    # 1.18.0, 2026-10-29 (same runs as MATLAB_VS_PYTHON's)
    ("1.18.0: current", [17.1, 7.0, 2.4, 55.1], [15.5, 0.0, 2.5, 12.5]),
]

MATLAB_TOTAL = sum(MATLAB_VS_PYTHON[0][1])

#: The reference palette's first four categorical slots, one per step, with
#: their dark-mode steps; checked with the dataviz validator in both modes.
THEMES = {
    "light": dict(surface="#fcfcfb", text="#0b0b0b", muted="#52514e", grid="#e4e3df",
                  series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]),
    "dark": dict(surface="#1a1a19", text="#f0efec", muted="#c3c2b7", grid="#3a3936",
                 series=["#3987e5", "#d95926", "#199e70", "#c98500"]),
}


def _fmt(seconds: float) -> str:
    if seconds >= 120:
        return f"{seconds:.0f} s ({seconds / 60:.1f} min)"
    return f"{seconds:.0f} s"


def _stacked(ax, rows, theme, *, reference: float | None = None) -> None:
    """Horizontal stacked bars, first row on top, total written at each bar's end."""
    labels = [r[0] for r in rows]
    # An express row sits just under the full run it belongs to.
    y, pos = [], 0.0
    for label in labels:
        pos -= 0.55 if label == "express mode" else (1.0 if y else 0.0)
        y.append(pos)
    top, bottom = y[0], y[-1]
    xmax = max(sum(r[1]) for r in rows)
    for yi, (label, steps) in zip(y, rows):
        sub = label == "express mode"
        left = 0.0
        for k, value in enumerate(steps):
            if value > 0:
                # A surface-coloured edge is the 2px gap between segments.
                ax.barh(yi, value, left=left, height=0.45 if sub else 0.62,
                        color=theme["series"][k], edgecolor=theme["surface"],
                        linewidth=1.5, hatch="////" if sub else None)
            left += value
        ax.text(left + xmax * 0.012, yi, _fmt(left), va="center", ha="left",
                color=theme["text"], fontsize=10)
    if reference is not None:
        ax.axvline(reference, color=theme["muted"], linestyle=(0, (4, 3)), linewidth=1.2)
        ax.text(reference, top + 0.55, f"MATLAB {reference:.0f} s ", ha="right",
                va="bottom", color=theme["muted"], fontsize=9)
    ax.set_yticks(y, labels, color=theme["text"], fontsize=10)
    for tick, label in zip(ax.get_yticklabels(), labels):
        if label == "express mode":
            tick.set_color(theme["muted"])
            tick.set_fontstyle("italic")
    ax.set_xlim(0, xmax * 1.3)
    ax.set_ylim(bottom - 0.6, top + 0.8)
    ax.set_xlabel("Run time (seconds)", color=theme["muted"], fontsize=10)
    ax.tick_params(axis="x", colors=theme["muted"], labelsize=9)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=theme["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(theme["grid"])


def _legend(ax, theme) -> None:
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in theme["series"]]
    ax.legend(handles, STEPS, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=4,
              frameon=False, fontsize=9, labelcolor=theme["text"], handlelength=1.0,
              columnspacing=1.4, borderaxespad=0.3)


def _figure(rows, name: str, title: str, mode: str, *, reference=None) -> Path:
    theme = THEMES[mode]
    fig, ax = plt.subplots(figsize=(8.5, 0.5 * len(rows) + 1.6), dpi=150)
    fig.patch.set_facecolor(theme["surface"])
    ax.set_facecolor(theme["surface"])
    _stacked(ax, rows, theme, reference=reference)
    ax.set_title(title, loc="left", pad=26, color=theme["text"], fontsize=12,
                 fontweight="bold")
    _legend(ax, theme)
    fig.tight_layout()
    path = OUT / f"{name}-{mode}.png"
    fig.savefig(path, facecolor=theme["surface"], bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return path


def _version_rows() -> list:
    """One bar per run: each version's full run, then its express run if any."""
    rows = []
    for label, full, express in VERSIONS:
        rows.append((label, full))
        if express is not None:
            rows.append(("express mode", express))
    return rows


def main() -> None:
    missing = [label for label, *runs in VERSIONS
               if any(isinstance(r, str) for r in runs)]
    if missing:
        raise SystemExit(f"fill in VERSIONS first: {missing}")
    OUT.mkdir(parents=True, exist_ok=True)
    for mode in THEMES:
        print(_figure(MATLAB_VS_PYTHON, "matlab-vs-python",
                      "Same two recordings, same settings, same computer", mode))
        print(_figure(_version_rows(), "speedup-by-version",
                      "The same run through each version of the Python port", mode,
                      reference=MATLAB_TOTAL))


if __name__ == "__main__":
    main()
