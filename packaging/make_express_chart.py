"""The run-time chart in the express-mode News post.

Run from the repo root::

    uv run python packaging/make_express_chart.py

The times are the measurements in docs/python/express-mode.md ("What it costs
and what it saves"): ExampleData's two recordings, Axion64, lags 10, 25 and
50 ms, 200 thresholding shuffles, both modes run back to back on one machine.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "news" / "imgs" / "express-mode" / "run-times.png"

STEPS = ["1. Spike detection", "2. Neuronal activity", "3. Functional connectivity",
         "4. Network activity", "Whole run"]
FULL = [69.8, 7.7, 14.6, 159.0, 251.1]
EXPRESS = [69.9, 0.0, 14.6, 113.4, 198.0]

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
FULL_COLOUR, EXPRESS_COLOUR = "#a8a7a1", "#2a78d6"


def main() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.9), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    height = 0.36
    rows = list(range(len(STEPS)))[::-1]
    for offset, values, colour, label in ((height / 2 + 0.02, FULL, FULL_COLOUR, "Full (every figure)"),
                                          (-height / 2 - 0.02, EXPRESS, EXPRESS_COLOUR, "Express")):
        ys = [r + offset for r in rows]
        ax.barh(ys, values, height=height, color=colour, label=label, zorder=2)
        for y, v in zip(ys, values):
            ax.text(v + 3, y, "0 s" if v == 0 else f"{v:.0f} s", va="center",
                    fontsize=8, color=MUTED)
    ax.set_yticks(rows, STEPS, fontsize=9, color=INK)
    ax.get_yticklabels()[-1].set_fontweight("bold")
    ax.axhline(0.5, color=GRID, lw=1)
    ax.set_xlabel("Run time on the example data (seconds)", fontsize=9, color=MUTED)
    ax.set_xlim(0, 285)
    ax.grid(axis="x", color=GRID, lw=0.8, zorder=0)
    ax.tick_params(axis="x", colors=MUTED, labelsize=8)
    ax.tick_params(axis="y", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.86), frameon=False, fontsize=9, labelcolor=INK)
    ax.set_title("Express mode skips drawing figures during the run: 21% faster",
                 fontsize=10.5, color=INK, loc="left", pad=10)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=SURFACE)
    print(OUT)


if __name__ == "__main__":
    main()
