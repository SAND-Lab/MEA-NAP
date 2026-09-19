"""Compare a spike-*sorted* run of MEA-NAP with a *detected* run of the same
recordings: did making neurons the nodes change the network?

    uv run python python/compare_sorted_vs_detected.py <detected_root> <sorted_root> [--out fig.png]

Writes one figure and prints one table:

- **units per electrode** — how the node set changed;
- **same-electrode vs other-electrode STTC** — units sharing an electrode
  should not be strongly correlated at short lags; if they are, the sorter
  split by amplitude rather than by neuron (the diagnostic from
  python/SPIKE_SORTING_PLAN.md §5.2);
- **recording-level network metrics, both runs** — density, modularity,
  clustering, path length, efficiency, small-worldness at each lag, so the
  effect of sorting on the conclusion is a number rather than an impression.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

METRICS = ["aN", "Dens", "CC", "nMod", "Q", "PL", "Eglob", "SW", "SWw", "NDmean", "NSmean"]


def _netmet(root: Path) -> dict:
    with open(root / "4_NetworkActivity" / "netmet_results.json") as fh:
        return json.load(fh)


def _scalar(v):
    if isinstance(v, list):
        return float(v[0]) if len(v) == 1 else np.nan
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def compare(detected: Path, sorted_: Path, out: Path | None) -> pd.DataFrame:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    det, srt = _netmet(detected), _netmet(sorted_)
    recs = [r for r in srt if r in det]
    rows = []
    for rec in recs:
        for lag in srt[rec]:
            if lag not in det[rec]:
                continue
            for m in METRICS:
                rows.append({"recording": rec, "lag": lag, "metric": m,
                             "detected": _scalar(det[rec][lag].get(m)),
                             "sorted": _scalar(srt[rec][lag].get(m))})
    table = pd.DataFrame(rows)
    table["change"] = table["sorted"] - table["detected"]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))

    # 1. units per electrode, pooled over recordings
    counts = []
    same, other = [], []
    for rec in recs:
        spk = np.load(sorted_ / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{rec}_spikes.npz")
        ch = spk["channels"]
        counts.extend(np.unique(ch, return_counts=True)[1].tolist())
        adj_path = sorted_ / "ExperimentMatFiles" / f"{rec}_adjM.npz"
        if adj_path.exists():
            adj = np.load(adj_path)
            key = next((k for k in adj.files if k.endswith("mslag_raw")), None)
            if key:
                a = adj[key]
                for i in range(len(ch)):
                    for j in range(i + 1, len(ch)):
                        (same if ch[i] == ch[j] else other).append(a[i, j])
    ax = axes[0]
    hist = np.bincount(counts)[1:]
    ax.bar(np.arange(1, len(hist) + 1), hist, color="#4c78a8")
    ax.set_xlabel("units on an electrode")
    ax.set_ylabel("electrodes")
    ax.set_title(f"{sum(counts)} units on {len(counts)} electrodes", fontsize=10)

    ax = axes[1]
    if same:
        ax.hist(np.asarray(other, float), bins=40, density=True, alpha=0.6, label=f"different electrodes ({len(other)})", color="0.6")
        ax.hist(np.asarray(same, float), bins=20, density=True, alpha=0.7, label=f"same electrode ({len(same)})", color="#e45756")
        ax.legend(frameon=False, fontsize=8)
        ax.set_title(f"STTC (raw, first lag): same-electrode median "
                     f"{np.nanmedian(same):.2f} vs other {np.nanmedian(other):.2f}", fontsize=10)
    else:
        ax.set_title("no electrode carries two units", fontsize=10)
    ax.set_xlabel("STTC")

    ax = axes[2]
    lags = sorted(table.lag.unique(), key=lambda k: int(k.replace("mslag", "")))
    show = ["Dens", "CC", "Q", "PL", "Eglob", "SW"]
    x = np.arange(len(show))
    w = 0.8 / (2 * len(lags))
    for li, lag in enumerate(lags):
        sub = table[table.lag == lag].groupby("metric")[["detected", "sorted"]].mean()
        ax.bar(x + (2 * li) * w - 0.4 + w / 2, [sub.loc[m, "detected"] for m in show], w,
               color=plt.cm.Blues(0.4 + 0.4 * li / max(1, len(lags) - 1)), label=f"detected {lag}")
        ax.bar(x + (2 * li + 1) * w - 0.4 + w / 2, [sub.loc[m, "sorted"] for m in show], w,
               color=plt.cm.Oranges(0.4 + 0.4 * li / max(1, len(lags) - 1)), label=f"sorted {lag}")
    ax.set_xticks(x)
    ax.set_xticklabels(show)
    ax.set_yscale("symlog", linthresh=1.0)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    ax.set_title("recording-level network metrics", fontsize=10)
    for a in axes:
        a.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"{detected.name} (electrodes) vs {sorted_.name} (units)", fontsize=11)
    plt.tight_layout()
    if out is not None:
        fig.savefig(out, dpi=160)
        print(f"figure → {out}")
    plt.close(fig)
    return table


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("detected", type=Path)
    ap.add_argument("sorted", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    table = compare(args.detected, args.sorted, args.out)
    pivot = table.pivot_table(index=["lag", "metric"], values=["detected", "sorted", "change"], aggfunc="mean")
    pivot = pivot[["detected", "sorted", "change"]]
    print(pivot.to_string(float_format=lambda v: f"{v:.3f}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
