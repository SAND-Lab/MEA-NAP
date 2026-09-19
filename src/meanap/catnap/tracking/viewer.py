"""An interactive per-cell page: is *this* cell really the same cell?

ROICaT's ``display_cropped_cluster_ims`` shows a tracked cluster as a strip of
footprint crops. That is the right spatial view but it is only the evidence the
matcher already used, so it cannot say whether a match is real. This puts the
independent evidence beside it -- the trace on each day, the activity metrics,
and the fingerprint with its percentile against the nearest-neighbour null --
and lets you move through cells rather than scroll a single long page.

**The page ships data, not pictures.** Traces, footprints and metric
distributions are embedded as arrays and drawn in the browser, so plots are
vector-sharp at any zoom, the field of view can be panned, and selecting a cell
is instant. It is one self-contained file with no network dependency: the charts
here are lines, scatters and strips, which need no plotting library, and a CDN
would stop the page working offline while inlining one would cost ~280 kB a page.

Layout:

* **field of view** -- each day's mean image side by side, every ROI drawn, the
  tracked ones highlighted and the selected cell marked on all days at once.
  This is the view that answers "did it follow the same place?" directly.
* **cell list** -- ordered worst-first by fingerprint, so scrolling until the
  footprints start convincing you calibrates the score on your own data.
* **detail** -- footprint and trace per day, then each metric placed against the
  null (grey) and the other matched cells (blue).
"""

from __future__ import annotations

import base64
import html
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: Mean images are downsampled to this before embedding. 384 px keeps cell-scale
#: structure visible while holding a four-day chain to ~0.7 MB.
FOV_PREVIEW_PX = 384

#: ROI masks are rendered larger than the mean projection. A suite2p ROI is
#: ~4 px in a 1280 px frame, so at the mean image's 384 px each cell collapses
#: to a single pixel and the view is unreadable once zoomed. The masks are
#: sparse and compress well, so the extra resolution is cheap: ~160 kB for both
#: layers against ~55 kB at 384 px.
MASK_PREVIEW_PX = 768

#: Traces are decimated to this many points. Enough to see event structure at
#: full-page width; the raw 20 000 samples would be 6x the payload for detail no
#: screen resolves.
TRACE_POINTS = 1200


@dataclass
class SessionView:
    """One day, as the field-of-view panel needs it."""

    div: int
    mean_png: str                      # base64 PNG, FOV_PREVIEW_PX square
    centroids: np.ndarray              # (n, 2) in full-frame pixels
    cluster_of: np.ndarray             # (n,) cluster id per ROI, -1 if unmatched
    #: ROI footprints as images. The mean projection shows the tissue; these
    #: show what suite2p actually segmented, which is what the matcher saw.
    #: Tracked and untracked are separate layers so "show untracked" applies
    #: here too rather than being ignored on this background.
    masks_tracked_png: str = ""
    masks_other_png: str = ""


@dataclass
class CellCard:
    """One tracked cell's evidence."""

    cluster: int
    divs: list[int]
    crops: list[np.ndarray]
    traces: list[np.ndarray]
    metrics: list[dict]
    fingerprint: float = float("nan")
    percentile: float = float("nan")
    #: ``(session_index, y, x)`` per day, so the cell can be marked on the FOV.
    positions: list[tuple[int, float, float]] = field(default_factory=list)
    comparisons: list = field(default_factory=list)
    #: Days on which this member was added by position rather than by ROICaT.
    rescued_divs: list[int] = field(default_factory=list)
    #: Days that came from a second cluster folded into this one.
    merged_divs: list[int] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# ── encoding ──────────────────────────────────────────────────────────────────

def _f32(values: np.ndarray) -> str:
    return base64.b64encode(np.asarray(values, dtype=np.float32).tobytes()).decode()


def _decimate(trace: np.ndarray, points: int = TRACE_POINTS) -> np.ndarray:
    """Shrink a trace, keeping peaks rather than averaging them away."""
    trace = np.asarray(trace, dtype=float)
    if trace.size <= points:
        return trace
    edges = np.linspace(0, trace.size, points + 1).astype(int)
    out = np.empty(points, dtype=float)
    for i in range(points):
        seg = trace[edges[i]:max(edges[i + 1], edges[i] + 1)]
        finite = seg[np.isfinite(seg)]
        out[i] = finite.max() if finite.size else np.nan
    return out


def mean_image_png(image: np.ndarray, size: int = FOV_PREVIEW_PX) -> str:
    """Contrast-stretched, downsampled mean projection as a base64 PNG."""
    from PIL import Image

    arr = np.asarray(image, dtype=np.float32)
    lo, hi = np.percentile(arr[np.isfinite(arr)], [1, 99.5]) if np.isfinite(arr).any() else (0, 1)
    norm = np.clip((arr - lo) / max(hi - lo, 1e-9), 0, 1)
    im = Image.fromarray((norm * 255).astype(np.uint8))
    if im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def cluster_colour(cluster: int) -> tuple[int, int, int]:
    """A stable colour for one tracked cell.

    suite2p gives each ROI a random hue; here the hue comes from the **cluster
    id**, so the same cell keeps the same colour on every day and correspondence
    across panels can be read directly instead of inferred from position.

    The golden-ratio step spreads consecutive ids far apart in hue, so
    neighbouring clusters do not come out as near-identical colours.
    """
    import colorsys

    hue = (cluster * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.72, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)


def masks_image_png(stat, frame_px: int, cluster_of, *, tracked: bool,
                    size: int = MASK_PREVIEW_PX) -> str:
    """One layer of ROI footprints as a transparent image.

    Tracked cells are drawn in their cluster's colour, suite2p-style; untracked
    ones in a neutral grey, so the two remain distinguishable while the tracked
    set is still individually readable.

    Drawn here rather than in the browser because the footprints themselves are
    far too much data to ship — two images a session, about the cost of the mean
    projection, and they answer "which cells were matched?" directly rather than
    through a scatter of centroids.
    """
    from PIL import Image

    rgb = np.zeros((frame_px, frame_px, 3), dtype=np.float32)
    alpha = np.zeros((frame_px, frame_px), dtype=np.float32)
    cluster_of = np.asarray(cluster_of)

    for i, roi in enumerate(stat):
        cluster = int(cluster_of[i]) if i < cluster_of.size else -1
        if (cluster >= 0) != tracked:
            continue
        ypix = np.asarray(roi["ypix"])
        xpix = np.asarray(roi["xpix"])
        lam = np.asarray(roi["lam"], dtype=np.float32)
        keep = (ypix >= 0) & (xpix >= 0) & (ypix < frame_px) & (xpix < frame_px)
        if not keep.any():
            continue
        weight = lam[keep] / (lam[keep].max() or 1.0)
        colour = cluster_colour(cluster) if tracked else (150, 155, 165)
        yy, xx = ypix[keep], xpix[keep]
        # brightest-wins, so overlapping footprints do not muddy into grey
        take = weight > alpha[yy, xx]
        yy, xx, weight = yy[take], xx[take], weight[take]
        alpha[yy, xx] = weight
        for k in range(3):
            rgb[yy, xx, k] = colour[k]

    out = np.zeros((frame_px, frame_px, 4), dtype=np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)

    im = Image.fromarray(out, mode="RGBA")
    if im.size != (size, size):
        # nearest, not lanczos: interpolating between two cells' hues invents a
        # third colour that belongs to neither
        im = im.resize((size, size), Image.NEAREST)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def crop_footprint(roi, frame_px: int, pad: int = 6) -> np.ndarray:
    """Tight, lam-weighted crop of one ROI, normalised to its own peak."""
    ypix = np.asarray(roi["ypix"])
    xpix = np.asarray(roi["xpix"])
    lam = np.asarray(roi["lam"], dtype=float)
    y0, y1 = max(int(ypix.min()) - pad, 0), min(int(ypix.max()) + pad + 1, frame_px)
    x0, x1 = max(int(xpix.min()) - pad, 0), min(int(xpix.max()) + pad + 1, frame_px)
    im = np.zeros((max(y1 - y0, 1), max(x1 - x0, 1)))
    keep = (ypix >= y0) & (ypix < y1) & (xpix >= x0) & (xpix < x1)
    im[ypix[keep] - y0, xpix[keep] - x0] = lam[keep]
    peak = im.max()
    return im / peak if peak > 0 else im


def select_cards(cards: list[CellCard], max_cells: int) -> list[CellCard]:
    """Order worst-first and sample across the range, keeping the bad end.

    ``max_cells`` <= 0 keeps every card.
    """
    # an unscored cell sorts to the worst end: it is unverified, not good
    ranked = sorted(cards, key=lambda c: c.fingerprint
                    if np.isfinite(c.fingerprint) else -np.inf)
    if max_cells <= 0 or len(ranked) <= max_cells:
        return ranked
    step = len(ranked) / max_cells
    return [ranked[int(i * step)] for i in range(max_cells)]


#: Percentiles summarising each population: 1, 10, 25, 50, 75, 90, 99. A compact
#: strip built from these reads more clearly than a histogram here -- the pools
#: are small (as few as 32 values on a thin chain), where a 28-bin histogram is
#: mostly empty bins and its shape is noise.
QUANTILES = (1, 10, 25, 50, 75, 90, 99)


def _distribution(sides: dict[str, np.ndarray]) -> dict | None:
    """Quantile summary of a metric, on a scale shared by both populations.

    The shared scale is the point: the null and the matched pool have to be read
    against each other, and separately-scaled summaries cannot be.
    """
    clean = {k: np.asarray(v, dtype=float)[np.isfinite(np.asarray(v, dtype=float))]
             for k, v in sides.items()}
    clean = {k: v for k, v in clean.items() if v.size >= 5}
    if not clean:
        return None
    pooled = np.concatenate(list(clean.values()))
    lo, hi = np.percentile(pooled, [1, 99])
    if not np.isfinite(lo) or hi <= lo:
        lo, hi = float(pooled.min()), float(pooled.max())
    if hi <= lo:
        hi = lo + 1e-9
    out = {"lo": round(float(lo), 5), "hi": round(float(hi), 5), "q": {}}
    for kind, values in clean.items():
        out["q"][kind] = [round(float(q), 5)
                          for q in np.percentile(values, QUANTILES)]
        out[kind + "N"] = int(values.size)
    return out


def build_payload(chain: str, subtitle: str, cards: list[CellCard], fs: float,
                  sessions: list[SessionView],
                  pools: dict[str, dict[str, np.ndarray]] | None = None) -> dict:
    """Everything the page draws, as plain data."""
    pools = pools or {}
    payload = {
        "chain": chain,
        "subtitle": subtitle,
        "fs": float(fs),
        "fovPreviewPx": FOV_PREVIEW_PX,
        "maskPreviewPx": MASK_PREVIEW_PX,
        "sessions": [],
        "cells": [],
        "pools": {},
    }
    for view in sessions:
        payload["sessions"].append({
            "div": int(view.div),
            "meanPng": view.mean_png,
            "masksTrackedPng": view.masks_tracked_png,
            "masksOtherPng": view.masks_other_png,
            "cy": _f32(view.centroids[:, 0]) if len(view.centroids) else "",
            "cx": _f32(view.centroids[:, 1]) if len(view.centroids) else "",
            "cluster": [int(c) for c in view.cluster_of],
        })
    for card in cards:
        payload["cells"].append({
            "cluster": int(card.cluster),
            "divs": [int(d) for d in card.divs],
            "rescuedDivs": [int(d) for d in card.rescued_divs],
            "mergedDivs": [int(d) for d in card.merged_divs],
            "fingerprint": (None if not np.isfinite(card.fingerprint)
                            else round(float(card.fingerprint), 4)),
            "percentile": (None if not np.isfinite(card.percentile)
                           else round(float(card.percentile), 1)),
            "positions": [[int(s), float(y), float(x)] for s, y, x in card.positions],
            "crops": [{"h": int(c.shape[0]), "w": int(c.shape[1]), "d": _f32(c.ravel())}
                      for c in card.crops],
            "traces": [_f32(_decimate(t)) for t in card.traces],
            "metrics": [{k: (None if not np.isfinite(v) else round(float(v), 4))
                         for k, v in m.items()} for m in card.metrics],
            "comparisons": [{
                "key": c.key, "label": c.label,
                "value": None if not np.isfinite(c.value) else round(float(c.value), 4),
                "pct": None if not np.isfinite(c.percentile) else round(float(c.percentile), 1),
                "matchedPct": (None if not np.isfinite(c.matched_percentile)
                               else round(float(c.matched_percentile), 1)),
                "higherIsBetter": bool(c.higher_is_better),
                "independent": bool(c.independent),
                "note": c.note,
            } for c in card.comparisons],
        })
    for key, sides in pools.items():
        dist = _distribution(sides)
        if dist is not None:
            payload["pools"][key] = dist
    return payload


# ── the page ──────────────────────────────────────────────────────────────────

_CSS = """
:root{--bg:#fbfbfa;--panel:#fff;--fg:#1f2328;--mut:#5b6570;--line:#e3e5e8;
  --hi:#1a7f37;--lo:#b35900;--sel:#d62728;--match:#2c7fb8;--null:#98a0a8}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
  --bg:#16181c;--panel:#1d2026;--fg:#e8eaed;--mut:#9aa4af;--line:#2b2f36;
  --hi:#4ac26b;--lo:#e8a13a;--sel:#ff6b6b;--match:#5aa9dd;--null:#6b747d}}
:root[data-theme=dark]{--bg:#16181c;--panel:#1d2026;--fg:#e8eaed;--mut:#9aa4af;
  --line:#2b2f36;--hi:#4ac26b;--lo:#e8a13a;--sel:#ff6b6b;--match:#5aa9dd;--null:#6b747d}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,sans-serif;
  margin:0;padding-block:16px;padding-left:16px;padding-right:16px}
h1{font-size:18px;margin:0 0 2px} .sub{color:var(--mut);font-size:13px;margin-bottom:14px}
.wrap{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap}
.side{flex:0 0 232px;min-width:200px}
.main{flex:1 1 560px;min-width:320px}
.box{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:10px;margin-bottom:12px}
.box h2{font-size:12px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--mut);margin:0 0 8px;font-weight:600}
#list{max-height:440px;overflow-y:auto;margin:0;padding:0;list-style:none}
#list li{padding:4px 7px;border-radius:5px;cursor:pointer;display:flex;
  justify-content:space-between;gap:8px;font-size:13px}
#list li:hover{background:var(--line)}
#list li[aria-selected=true]{background:var(--match);color:#fff}
#list li .r{font-variant-numeric:tabular-nums;font-size:12px}
.fov{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px}
.fov figure{margin:0;flex:0 0 auto;text-align:center}
.fov canvas{display:block;border:1px solid var(--line);border-radius:5px;
  cursor:crosshair;background:var(--bg)}
.fov figcaption{font-size:11px;color:var(--mut);margin-top:3px}
.days{display:flex;gap:10px;overflow-x:auto}
.day{flex:0 0 auto;text-align:center;font-size:11px;color:var(--mut)}
.day canvas{display:block;image-rendering:pixelated;border-radius:4px;background:#000}
svg{display:block;width:100%;height:auto;overflow:visible}
.ctl{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12px;
  color:var(--mut);margin-bottom:8px}
.ctl input[type=search]{flex:1 1 120px;min-width:110px;padding:4px 7px;
  border:1px solid var(--line);border-radius:5px;background:var(--bg);color:var(--fg)}
.ctl label{display:flex;gap:4px;align-items:center;cursor:pointer}
.pill{font-variant-numeric:tabular-nums;font-weight:600}
.hi{color:var(--hi)} .lo{color:var(--lo)}
.note{border-left:3px solid var(--line);padding-left:11px;color:var(--mut);
  font-size:12.5px;margin:10px 0 0}
.kbd{border:1px solid var(--line);border-radius:3px;padding:0 4px;font-size:11px}
#tip{position:fixed;z-index:99;display:none;max-width:330px;background:var(--panel);
  color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:8px 10px;
  font-size:12px;line-height:1.45;box-shadow:0 6px 22px rgba(0,0,0,.28);
  pointer-events:none}
.hashelp{cursor:help}
h2.hashelp,span.hashelp{text-decoration:underline dotted;text-underline-offset:2px}
.listhead{display:flex;justify-content:space-between;font-size:11px;color:var(--mut);
  padding:0 7px 4px;border-bottom:1px solid var(--line);margin-bottom:4px}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--mut);
  margin-bottom:8px}
.legend .sw{display:inline-block;width:11px;height:11px;border-radius:2px;
  margin-right:5px;vertical-align:-1px}
.legend .sw.bar{width:18px;height:7px;border-radius:2px;opacity:.55;vertical-align:0}
.legend .sw.sel{background:var(--sel);border-radius:50%}
.legend .sw.dot{border-radius:50%;opacity:.85}
.legend .sw.dot.small{width:7px;height:7px;opacity:.5;margin-left:2px;margin-right:7px}
.legend .sw.ring{border-radius:50%;border:1.5px solid;background:transparent;box-sizing:border-box}
.hist{margin-bottom:14px}
.histhead{font-size:12.5px;margin-bottom:2px}
.warnpill{font-size:10px;background:var(--line);color:var(--mut);
  border-radius:3px;padding:1px 5px;vertical-align:1px}
button{font:inherit;font-size:12px;padding:3px 9px;border:1px solid var(--line);
  border-radius:5px;background:var(--bg);color:var(--fg);cursor:pointer}
button:hover{background:var(--line)}
#zoom{font-variant-numeric:tabular-nums;min-width:38px;display:inline-block}
"""

_JS = r"""
const D = window.__TRACK__;
const $ = s => document.querySelector(s);
const b64f32 = s => {
  if (!s) return new Float32Array(0);
  const bin = atob(s), buf = new ArrayBuffer(bin.length), v = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i++) v[i] = bin.charCodeAt(i);
  return new Float32Array(buf);
};
// magma, sampled; matches the static pages so footprints look the same
const MAGMA = [[0,0,4],[28,16,68],[79,18,123],[129,37,129],[181,54,122],
               [229,80,100],[251,135,97],[254,194,135],[252,253,191]];
function magma(t){
  t = Math.max(0, Math.min(1, t)); const x = t * (MAGMA.length - 1);
  const i = Math.floor(x), f = x - i, a = MAGMA[i], b = MAGMA[Math.min(i + 1, MAGMA.length - 1)];
  return [a[0] + (b[0]-a[0])*f, a[1] + (b[1]-a[1])*f, a[2] + (b[2]-a[2])*f];
}
const css = n => getComputedStyle(document.body).getPropertyValue(n).trim();

/** One tooltip for the page, positioned by the cursor. */
function tipHost(){
  let el = document.getElementById("tip");
  if (!el){ el = document.createElement("div"); el.id = "tip";
            el.setAttribute("role","tooltip"); document.body.appendChild(el); }
  return el;
}
function attachTip(el, html){
  if (!el || !html) return el;
  const show = ev => {
    const t = tipHost();
    t.innerHTML = html; t.style.display = "block";
    const pad = 14, w = t.offsetWidth, h = t.offsetHeight;
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + w > window.innerWidth - 8) x = ev.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = ev.clientY - h - pad;
    t.style.left = Math.max(4, x) + "px"; t.style.top = Math.max(4, y) + "px";
  };
  el.addEventListener("mousemove", show);
  el.addEventListener("mouseenter", show);
  el.addEventListener("mouseleave", () => { tipHost().style.display = "none"; });
  el.classList.add("hashelp");
  return el;
}

/** What each measure is. None of these are guessable from a number. */
const HELP = {
  fingerprint:
    "<b>Functional fingerprint</b><br>Take this cell's correlation with every "
    + "<i>other</i> tracked cell — that vector is its position in the network. "
    + "The fingerprint <i>r</i> is how well that vector agrees between the two "
    + "days.<br><br><b>The matcher never looked at activity</b>, so this is "
    + "independent evidence that the match is real, unlike anything about shape "
    + "or position.<br><br>Compared against the <b>spatial null</b>: the same "
    + "measurement for a <i>different cell in essentially the same place</i> "
    + "(each partner's nearest neighbour). ~0.66 AUC is this dataset's median — "
    + "enough to describe a match, not to decide one.",
  d_event_rate:
    "<b>|Δ event rate|</b><br>Absolute difference in detected calcium events per "
    + "minute between the two days. Small means the cell fired at a similar rate "
    + "on both.<br><br>A cell can be the same cell and still change rate a lot "
    + "with age, so a large difference is weak evidence against a match.",
  d_iei:
    "<b>|Δ inter-event interval|</b><br>Difference in the median gap between "
    + "consecutive events, in seconds. A different view of the same activity as "
    + "event rate, less sensitive to a few extra detections.",
  d_pop_coupling:
    "<b>|Δ population coupling|</b><br>Population coupling is a cell's "
    + "correlation with the mean activity of every other cell in that recording "
    + "— how much it moves with the crowd. This is the difference between the "
    + "two days.",
  footprint_iou:
    "<b>Footprint overlap (IoU)</b><br><b>IoU</b> is <i>intersection over "
    + "union</i>: the pixels in <b>both</b> masks divided by the pixels in "
    + "<b>either</b>, after registration.<br><br>"
    + "<code>100 px on day 1, 100 px on day 2, 60 shared<br>"
    + "→ 60 ÷ (100+100−60) = 0.43</code><br><br>"
    + "0 is no shared pixels, 1 is identical masks. Dividing by the union is "
    + "what makes it fair: plain overlap would reward a large ROI for being "
    + "large, and the union penalises a mask much bigger or smaller than its "
    + "partner, not just a displaced one.<br><br>"
    + "<b>Median across real matches here is 0.45</b> — perfect agreement is "
    + "rare because suite2p re-segments each day independently, so the same "
    + "cell gets a slightly different mask every time. No matched pair has zero "
    + "overlap, so a value near zero is worth a look.<br><br>"
    + "<b>Description, not evidence.</b> ROICaT matched on footprint and "
    + "position, so against a spatial null this separates at AUC 0.997 — which "
    + "only says the matcher did what it was asked. Compare the functional "
    + "fingerprint at 0.66: that gap is how much we actually know.",
  centroid_shift:
    "<b>Centroid shift</b><br>Distance between the two ROIs' centres after "
    + "registration.<br><br><b>Description, not evidence.</b> ROICaT matched on "
    + "footprint and position, so of course matched cells are close — this "
    + "cannot tell a correct match from a plausible one.",
  rate: "<b>Event rate</b><br>Detected calcium events per minute on this day.",
  pop:
    "<b>Population coupling</b><br>This cell's correlation with the mean "
    + "activity of every other cell in the recording, on this day. High means it "
    + "moves with the crowd; near zero means it is doing its own thing.",
  listR:
    "<b>Fingerprint r</b><br>How well this cell's place in the network agrees "
    + "across days — independent of the match itself.<br><br><b>n/a</b> means "
    + "the cell had fewer than six other tracked cells to compare against.",
  fov:
    "<b>Field of view</b><br>Each day's projection with every ROI drawn. The "
    + "selected cell is ringed and crosshaired on <i>all</i> days at once, so "
    + "you can see whether the match landed in the same place.<br><br>Scroll to "
    + "zoom, drag to pan — every day moves together, because they are only "
    + "comparable at the same magnification.<br><br>Click a <b>solid blue</b> dot "
    + "to select that cell. <b>Hollow orange</b> dots are tracked cells with no "
    + "card on the left (the page carries at most 40), so they cannot be "
    + "selected; untick them to hide them. Grey dots are cells tracked on no "
    + "other day.",
  masks:
    "<b>Cell masks</b><br>The footprints suite2p actually segmented. Each "
    + "tracked cell is coloured by its <b>cluster</b>, so the same cell is the "
    + "same colour on every day; untracked cells are grey.",
};

let cells = D.cells.slice(), order = cells.map((_, i) => i), sel = 0, showAll = true;
let showNoCard = true;     // tracked cells that have no card, and so cannot be picked
// clusters that have a card, and so can be selected at all
const selectable = new Set(D.cells.map(c => c.cluster));
let background = "mean";   // mean image · cell masks · none
// one view for every day: zooming one day zooms them all, which is the whole
// point — the days are only comparable at the same magnification and position
let view = {scale: 1, cx: D.frame / 2, cy: D.frame / 2};

// ── field of view ────────────────────────────────────────────────────────────
const fovCanvases = [];
function buildFov(){
  const host = $("#fov"); host.innerHTML = "";
  D.sessions.forEach((s, si) => {
    const fig = document.createElement("figure");
    const cv = document.createElement("canvas");
    const size = Math.min(D.fovPreviewPx, 300);
    const dpr = window.devicePixelRatio || 1;
    cv.width = size * dpr; cv.height = size * dpr;
    cv.style.width = size + "px"; cv.style.height = size + "px";
    const cap = document.createElement("figcaption");
    cap.textContent = "DIV" + s.div;
    fig.append(cv, cap); host.append(fig);
    s._cy = b64f32(s.cy); s._cx = b64f32(s.cx);
    cv.style.cursor = "crosshair";
    cv.addEventListener("wheel", ev => {
      ev.preventDefault();
      const r = cv.getBoundingClientRect();
      const before = toFrame(ev.clientX - r.left, ev.clientY - r.top, size);
      const k = Math.exp(-ev.deltaY * 0.0016);
      view.scale = Math.max(1, Math.min(20, view.scale * k));
      const after = toFrame(ev.clientX - r.left, ev.clientY - r.top, size);
      // keep the point under the cursor fixed while zooming
      view.cx += before.x - after.x; view.cy += before.y - after.y;
      clampView(); redrawFov();
    }, {passive: false});
    // a press that moves is a pan; a press that does not is a pick. Letting
    // the browser's click fire after a pan jumped the selection every time
    // the view was dragged.
    let drag = null;
    cv.addEventListener("pointerdown", ev => {
      drag = {x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, moved: false};
      cv.setPointerCapture(ev.pointerId); });
    cv.addEventListener("pointermove", ev => {
      if (!drag) return;
      if (Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) > 4) drag.moved = true;
      const span = D.frame / view.scale;
      view.cx -= (ev.clientX - drag.x) / size * span;
      view.cy -= (ev.clientY - drag.y) / size * span;
      drag = {...drag, x: ev.clientX, y: ev.clientY};
      clampView(); redrawFov(); });
    cv.addEventListener("pointerup", ev => {
      const wasPick = drag && !drag.moved;
      drag = null;
      if (wasPick) pickFromFov(si, ev, size);
    });
    cv.addEventListener("pointercancel", () => { drag = null; });
    cv.addEventListener("dblclick", () => { resetView(); });
    // register the canvas before the image can call back: a cached or
    // synchronously-decoded data URL fires onload immediately, and drawFov
    // would then read an entry that does not exist yet
    fovCanvases.push({cv, size, dpr});
    // three backgrounds, loaded once each; "show untracked" hides the grey
    // mask layer as well as the grey dots, so the control means one thing
    for (const [key, field] of [["_img", "meanPng"],
                                ["_mTracked", "masksTrackedPng"],
                                ["_mOther", "masksOtherPng"]]) {
      if (!s[field]) continue;
      const im = new Image();
      im.onload = () => { s[key] = im; drawFov(si); };
      im.src = "data:image/png;base64," + s[field];
    }
  });
}
function span(){ return D.frame / view.scale; }
function clampView(){
  const h = span() / 2;
  view.cx = Math.max(h, Math.min(D.frame - h, view.cx));
  view.cy = Math.max(h, Math.min(D.frame - h, view.cy));
}
function resetView(){ view = {scale: 1, cx: D.frame/2, cy: D.frame/2}; redrawFov(); }
function toFrame(px, py, size){   // canvas px -> full-frame coordinates
  const sp = span();
  return {x: view.cx - sp/2 + px / size * sp, y: view.cy - sp/2 + py / size * sp};
}
function redrawFov(){
  D.sessions.forEach((_, si) => drawFov(si));
  const z = $("#zoom"); if (z) z.textContent = view.scale.toFixed(1) + "×";
}
function drawFov(si){
  const s = D.sessions[si], {cv, size, dpr} = fovCanvases[si];
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, size, size);
  const sp = span(), x0 = view.cx - sp/2, y0 = view.cy - sp/2;
  // masks are rendered at their own resolution, so each background scales by
  // its own factor rather than one shared one
  const paint = (im, previewPx) => {
    if (!im) return;
    const t = previewPx / D.frame;
    g.drawImage(im, x0*t, y0*t, sp*t, sp*t, 0, 0, size, size);
  };
  // the mean projection is light-on-dark and wants a dark ground; masks are
  // coloured on transparent and read far better on the page's own background
  g.fillStyle = background === "mean" ? "#000" : css("--bg");
  g.fillRect(0, 0, size, size);
  g.imageSmoothingEnabled = background !== "masks";
  if (background === "mean") paint(s._img, D.fovPreviewPx);
  else if (background === "masks") {
    const mp = D.maskPreviewPx || D.fovPreviewPx;
    if (showAll) paint(s._mOther, mp);
    paint(s._mTracked, mp);
  }
  const k = size / sp;
  const px = v => (v - x0) * k, py = v => (v - y0) * k;
  const cell = cells[order[sel]];
  const here = cell ? cell.positions.find(p => p[0] === si) : null;
  // on the mask background the footprints already show every ROI, so only the
  // selected cell is marked — drawing every dot would just cover them
  // dots grow with the zoom, but slowly (square root), so they stay a
  // marker on the cell rather than becoming the cell: 2.2 px at 1x, ~5 px at
  // 5x, capped at 6 px
  const rDot = Math.max(2.2, Math.min(6, 2.2 * Math.sqrt(view.scale)));
  for (let i = 0; background !== "masks" && i < s._cy.length; i++){
    const tracked = s.cluster[i] >= 0;
    const pickable = tracked && selectable.has(s.cluster[i]);
    if (!tracked && !showAll) continue;
    if (tracked && !pickable && !showNoCard) continue;
    const isSel = cell && s.cluster[i] === cell.cluster;
    const X = px(s._cx[i]), Y = py(s._cy[i]);
    if (X < -12 || Y < -12 || X > size + 12 || Y > size + 12) continue;
    g.beginPath();
    if (isSel){
      g.arc(X, Y, rDot + 3, 0, 6.284);
      g.strokeStyle = css("--sel"); g.lineWidth = 2; g.stroke();
    } else if (pickable){            // solid blue: click to select
      g.arc(X, Y, rDot, 0, 6.284);
      g.fillStyle = css("--match"); g.globalAlpha = .85; g.fill(); g.globalAlpha = 1;
    } else if (tracked){             // hollow orange: tracked, but no card
      g.arc(X, Y, rDot, 0, 6.284);
      g.strokeStyle = css("--lo"); g.lineWidth = 1.5; g.globalAlpha = .8; g.stroke(); g.globalAlpha = 1;
    } else {                         // small grey: not tracked
      g.arc(X, Y, Math.max(1.4, rDot * .55), 0, 6.284);
      g.fillStyle = css("--null"); g.globalAlpha = .4; g.fill(); g.globalAlpha = 1;
    }
  }
  if (background === "masks" && cell){
    for (let i = 0; i < s._cy.length; i++){
      if (s.cluster[i] !== cell.cluster) continue;
      g.beginPath();
      g.arc(px(s._cx[i]), py(s._cy[i]), 6, 0, 6.284);
      g.strokeStyle = css("--sel"); g.lineWidth = 2; g.stroke();
    }
  }
  if (here){  // crosshair, so the cell is findable even at low zoom
    g.strokeStyle = css("--sel"); g.globalAlpha = .45; g.lineWidth = 1;
    g.beginPath();
    g.moveTo(px(here[2]), 0); g.lineTo(px(here[2]), size);
    g.moveTo(0, py(here[1])); g.lineTo(size, py(here[1]));
    g.stroke(); g.globalAlpha = 1;
  }
}
// how far (in screen px) a click may land from a cell and still pick it. In
// frame px this shrinks as the view zooms in, which is what a pointer wants:
// the target is the dot on screen, not the cell's real size
const PICK_RADIUS_PX = 40;
function pickFromFov(si, ev, size){
  const s = D.sessions[si], r = ev.target.getBoundingClientRect();
  const f = toFrame(ev.clientX - r.left, ev.clientY - r.top, size);
  const x = f.x, y = f.y;
  const limit = (PICK_RADIUS_PX * span() / size) ** 2;
  let best = -1, bestD = limit;
  for (let i = 0; i < s._cy.length; i++){
    if (s.cluster[i] < 0 || !selectable.has(s.cluster[i])) continue;
    const d = (s._cy[i]-y)**2 + (s._cx[i]-x)**2;
    if (d < bestD){ bestD = d; best = i; }
  }
  if (best < 0) return;
  const idx = order.findIndex(o => cells[o].cluster === s.cluster[best]);
  if (idx >= 0) select(idx);
}

// ── list ─────────────────────────────────────────────────────────────────────
function buildList(){
  const ul = $("#list"); ul.innerHTML = "";
  order.forEach((ci, i) => {
    const c = cells[ci], li = document.createElement("li");
    li.setAttribute("role", "option");
    const r = c.fingerprint;
    li.title = r === null
      ? "No fingerprint: this cell has too few other tracked cells to compare against."
      : `Fingerprint r = ${r.toFixed(3)} — correlation of this cell's relationship to `
        + "every other tracked cell, compared across days. Higher means more like the same cell.";
    li.innerHTML = `<span>cell ${c.cluster} <span style="opacity:.6">· ${c.divs.length}d</span></span>` +
      `<span class="r ${r === null ? "" : (r >= .5 ? "hi" : "lo")}">` +
      `${r === null ? "n/a" : (r >= 0 ? "+" : "") + r.toFixed(2)}</span>`;
    li.addEventListener("click", () => select(i));
    ul.append(li);
  });
}
function select(i){
  sel = Math.max(0, Math.min(order.length - 1, i));
  [...$("#list").children].forEach((li, k) => li.setAttribute("aria-selected", k === sel));
  const li = $("#list").children[sel];
  if (li) li.scrollIntoView({block: "nearest"});
  redrawFov();
  drawDetail();
}

// ── detail ───────────────────────────────────────────────────────────────────
function drawDetail(){
  const c = cells[order[sel]];
  if (!c) return;
  const r = c.fingerprint, p = c.percentile;
  $("#hdr").innerHTML = `<b>cell ${c.cluster}</b> · ${c.divs.length} days · ` +
    `<span class="pill ${r === null ? "" : (r >= .5 ? "hi" : "lo")}">` +
    `r = ${r === null ? "n/a" : (r >= 0 ? "+" : "") + r.toFixed(2)}</span>` +
    (p === null ? "" : ` · beats <b>${p.toFixed(0)}%</b> of the null`);

  const host = $("#days"); host.innerHTML = "";
  c.crops.forEach((cr, k) => {
    const wrap = document.createElement("div"); wrap.className = "day";
    const cv = document.createElement("canvas");
    const dpr = window.devicePixelRatio || 1, box = 92;
    cv.width = cr.w; cv.height = cr.h;
    cv.style.width = box + "px"; cv.style.height = (box * cr.h / cr.w) + "px";
    const g = cv.getContext("2d"), im = g.createImageData(cr.w, cr.h);
    const d = b64f32(cr.d);
    for (let i = 0; i < d.length; i++){
      const [R,G,B] = magma(d[i]);
      im.data[i*4] = R; im.data[i*4+1] = G; im.data[i*4+2] = B; im.data[i*4+3] = 255;
    }
    g.putImageData(im, 0, 0);
    const m = c.metrics[k] || {};
    const cap = document.createElement("div");
    const rateEl = document.createElement("span");
    rateEl.textContent = m.rate == null ? "–" : m.rate.toFixed(1) + "/min";
    const popEl = document.createElement("span");
    popEl.textContent = "pop " + (m.pop == null ? "n/a"
      : (m.pop >= 0 ? "+" : "") + m.pop.toFixed(2));
    attachTip(rateEl, HELP.rate); attachTip(popEl, HELP.pop);
    const dayEl = document.createElement("span");
    dayEl.textContent = `DIV${c.divs[k]}`;
    if ((c.rescuedDivs || []).includes(c.divs[k])){
      dayEl.textContent += " ·";
      dayEl.style.color = "var(--sel)";
      dayEl.title = "Added by position: ROICaT left this cell unmatched, and it "
        + "was the only unmatched cell within 10 px of where the tracked cell should be.";
    } else if ((c.mergedDivs || []).includes(c.divs[k])){
      dayEl.textContent += " ∙∙";
      dayEl.style.color = "var(--sel)";
      dayEl.title = "Joined: ROICaT tracked this cell as a second cluster on these "
        + "days, at the same position and on days the first cluster lacked.";
    }
    cap.append(dayEl, document.createElement("br"), rateEl,
               document.createElement("br"), popEl);
    wrap.append(cv, cap); host.append(wrap);
  });
  drawTraces(c);
  drawStrips(c);
}

function drawTraces(c){
  const host = $("#traces"); host.innerHTML = "";
  const W = 1000, H = 54, gap = 8;
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${(H + gap) * c.traces.length}`);
  c.traces.forEach((t64, k) => {
    const t = b64f32(t64);
    let lo = Infinity, hi = -Infinity;
    for (const v of t){ if (Number.isFinite(v)){ if (v < lo) lo = v; if (v > hi) hi = v; } }
    if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    if (hi <= lo) hi = lo + 1e-9;
    const y0 = k * (H + gap);
    let d = "";
    for (let i = 0; i < t.length; i++){
      const v = t[i];
      const x = i / (t.length - 1) * W;
      const y = y0 + H - (Number.isFinite(v) ? (v - lo) / (hi - lo) : 0) * H;
      d += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    }
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", d); path.setAttribute("fill", "none");
    path.setAttribute("stroke", css("--match")); path.setAttribute("stroke-width", ".9");
    const lbl = document.createElementNS(svgNS, "text");
    lbl.setAttribute("x", "2"); lbl.setAttribute("y", y0 + 10);
    lbl.setAttribute("font-size", "10"); lbl.setAttribute("fill", css("--mut"));
    lbl.textContent = "DIV" + c.divs[k];
    svg.append(path, lbl);
  });
  host.append(svg);
}

function drawStrips(c){
  const host = $("#strips"); host.innerHTML = "";
  const comps = c.comparisons.filter(x => x.value !== null && D.pools[x.key]);
  if (!comps.length){
    host.innerHTML = '<div class="sub">No metrics scored for this cell — it needs '
      + 'at least six other tracked cells in a shared day-pair to be compared.</div>';
    return;
  }
  const NS = "http://www.w3.org/2000/svg";
  const mk = (t, a) => { const e = document.createElementNS(NS, t);
    for (const k in a) e.setAttribute(k, a[k]); return e; };

  host.insertAdjacentHTML("beforeend",
    '<div class="legend">' +
    '<span><i class="sw bar" style="background:var(--null)"></i>null &mdash; a different cell in the same place</span>' +
    '<span><i class="sw bar" style="background:var(--match)"></i>other matched cells</span>' +
    '<span><i class="sw sel"></i>this cell</span>' +
    '<span class="sub">thick bar = middle half &middot; thin line = 10th&ndash;90th &middot; tick = median</span>' +
    '</div>');

  const W = 1000, rowH = 34, L = 208, R = 150, top = 14;
  const svg = mk("svg", {viewBox: `0 0 ${W} ${rowH * comps.length + top + 8}`});
  const tx = (x, y, t, col, anchor, size) => {
    const e = mk("text", {x, y, fill: col, "font-size": size || 11,
                          "text-anchor": anchor || "start",
                          "dominant-baseline": "middle"});
    e.textContent = t; svg.append(e); return e; };

  comps.forEach((cp, i) => {
    const q = D.pools[cp.key];
    const sc = v => L + Math.max(0, Math.min(1,
      (v - q.lo) / ((q.hi - q.lo) || 1e-9))) * (W - L - R);
    const y = top + i * rowH + rowH / 2 - 4;

    // the two populations, offset so they can be told apart at a glance
    [["null", css("--null"), -6], ["matched", css("--match"), 6]].forEach(([k, col, off]) => {
      const s2 = q.q[k]; if (!s2) return;
      svg.append(mk("line", {x1: sc(s2[1]), y1: y + off, x2: sc(s2[5]), y2: y + off,
                             stroke: col, "stroke-width": 1.3, opacity: .75,
                             "stroke-linecap": "round"}));            // 10-90
      svg.append(mk("line", {x1: sc(s2[2]), y1: y + off, x2: sc(s2[4]), y2: y + off,
                             stroke: col, "stroke-width": 7, opacity: .5,
                             "stroke-linecap": "butt"}));             // middle half
      svg.append(mk("line", {x1: sc(s2[3]), y1: y + off - 5, x2: sc(s2[3]), y2: y + off + 5,
                             stroke: col, "stroke-width": 1.6}));     // median
    });
    svg.append(mk("circle", {cx: sc(cp.value), cy: y, r: 4.8, fill: css("--sel"),
                             stroke: css("--panel"), "stroke-width": 1.2}));

    attachTip(tx(L - 10, y, cp.label, css("--fg"), "end"), HELP[cp.key]);
    if (!cp.independent)
      tx(L - 10, y + 12, "used by the matcher", css("--mut"), "end", 9.5);
    else
      tx(L - 10, y + 12, cp.higherIsBetter ? "higher = same cell"
                                           : "lower = same cell", css("--mut"), "end", 9.5);
    // scale ends, so the strip has units rather than being purely relative
    tx(L, y + 18, q.lo.toFixed(2), css("--mut"), "start", 9);
    tx(W - R, y + 18, q.hi.toFixed(2), css("--mut"), "end", 9);

    tx(W - R + 12, y - 6, `${cp.value.toFixed(3)}`, css("--sel"), "start", 11.5);
    tx(W - R + 12, y + 8,
       cp.pct === null ? "n/a" : `beats ${cp.pct.toFixed(0)}% of null`,
       cp.pct !== null && cp.pct >= 50 ? css("--hi") : css("--lo"), "start", 10.5);
  });
  host.append(svg);
  const anyDep = comps.some(x => !x.independent);
  host.insertAdjacentHTML("beforeend",
    '<div class="sub" style="margin-top:6px">n = ' +
    Object.values(D.pools)[0].nullN + ' null / ' +
    Object.values(D.pools)[0].matchedN + ' matched comparisons' +
    (anyDep ? ' &middot; metrics marked <i>used by the matcher</i> are description, not evidence' : '') +
    '</div>');
}

// ── wiring ───────────────────────────────────────────────────────────────────
function applyFilter(){
  const q = $("#search").value.trim().toLowerCase();
  order = cells.map((_, i) => i).filter(i => !q || String(cells[i].cluster).includes(q));
  order.sort((a, b) => {
    const A = cells[a].fingerprint, B = cells[b].fingerprint;
    return (A === null ? -Infinity : A) - (B === null ? -Infinity : B);
  });
  buildList(); select(0);
}
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT") return;
  if (e.key === "ArrowDown" || e.key === "j"){ select(sel + 1); e.preventDefault(); }
  if (e.key === "ArrowUp" || e.key === "k"){ select(sel - 1); e.preventDefault(); }
});
window.addEventListener("DOMContentLoaded", () => {
  $("#search").addEventListener("input", applyFilter);
  $("#showall").addEventListener("change", e => {
    showAll = e.target.checked; redrawFov();
  });
  $("#shownocard").addEventListener("change", e => {
    showNoCard = e.target.checked; redrawFov();
  });
  $("#bg").addEventListener("change", e => {
    background = e.target.value; redrawFov();
  });
  attachTip($("#h-fov"), HELP.fov);
  attachTip($("#h-listr"), HELP.listR);
  attachTip($("#h-strips"), HELP.fingerprint);
  attachTip($("#bg"), HELP.masks);
  $("#reset").addEventListener("click", resetView);
  buildFov(); applyFilter();
});
"""

#: The page is usually shown inside the run viewer, which owns the theme. It
#: arrives as ``?theme=light|dark``; with no parameter the page falls back to
#: the browser's own preference, which is what it does when opened directly.
_THEME_JS = """
(function () {
  var t = new URLSearchParams(location.search).get("theme");
  if (t === "light" || t === "dark")
    document.documentElement.setAttribute("data-theme", t);
})();
"""

_NOTE = """The <b>field of view</b> shows each day's mean projection with every ROI
drawn &mdash; tracked cells solid, untracked faint, the selected cell ringed and
crosshaired on every day at once. Click a tracked ROI to jump to it. The
<b>fingerprint</b> compares this cell's correlation to every other tracked cell
across two days and is independent of the match; the percentage is against the
nearest-neighbour null, a different cell in essentially the same place. Around
68% is this dataset's average &mdash; enough to describe a match, not to decide
one. Move with <span class="kbd">&uarr;</span> <span class="kbd">&darr;</span>
or <span class="kbd">j</span> <span class="kbd">k</span>."""


def render_page(payload: dict, *, note: str = _NOTE) -> str:
    """Turn a stored payload back into the page.

    Split from :func:`build_page` so a bundle can carry the payload alone and
    the viewer can rebuild the page from it on request -- which is how every
    other figure family in a bundle works.
    """
    title = payload.get("chain", "Tracked cells")
    subtitle = payload.get("subtitle", "")
    return f"""<title>{html.escape(title)}</title>
<style>{_CSS}</style>
<h1>{html.escape(title)}</h1>
<div class="sub">{subtitle}</div>
<div class="box"><h2 id="h-fov">field of view</h2><div class="fov" id="fov"></div>
  <div class="ctl" style="margin:8px 0 0">
    <label>background
      <select id="bg">
        <option value="mean">mean image</option>
        <option value="masks">cell masks</option>
        <option value="none">none</option>
      </select></label>
    <label><input type="checkbox" id="shownocard" checked> tracked, no card</label>
    <label><input type="checkbox" id="showall" checked> untracked</label>
    <span>scroll to zoom &middot; drag to pan &middot; all days move together</span>
    <span id="zoom">1.0&times;</span>
    <button id="reset" type="button">reset view</button>
  </div>
  <div class="legend" id="fovlegend" style="margin:6px 0 0">
    <span><i class="sw dot" style="background:var(--match)"></i>click to select</span>
    <span><i class="sw ring" style="border-color:var(--lo)"></i>tracked, no card &mdash; not selectable</span>
    <span><i class="sw dot small" style="background:var(--null)"></i>untracked</span>
    <span><i class="sw ring" style="border-color:var(--sel);border-width:2px"></i>selected</span>
  </div></div>
<div class="wrap">
  <div class="side box"><h2>cells &middot; worst first</h2>
    <div class="ctl"><input type="search" id="search" placeholder="filter by cell id"></div>
    <div class="listhead"><span>cell &middot; days</span><span id="h-listr">fingerprint r</span></div>
    <ul id="list" role="listbox"></ul></div>
  <div class="main">
    <div class="box"><h2>selected cell</h2><div id="hdr" class="sub"></div>
      <div class="days" id="days"></div></div>
    <div class="box"><h2>fluorescence</h2><div id="traces"></div></div>
    <div class="box"><h2 id="h-strips">where this cell sits</h2><div id="strips"></div></div>
  </div>
</div>
<div class="note">{note}</div>
<script>window.__TRACK__ = {json.dumps(payload)};</script>
<script>{_THEME_JS}</script>
<script>{_JS}</script>
"""


def build_page(title: str, subtitle: str, cards: list[CellCard], fs: float,
               *, sessions: list[SessionView], frame_px: int,
               pools: dict[str, dict[str, np.ndarray]] | None = None,
               note: str = _NOTE) -> str:
    payload = build_payload(title, subtitle, cards, fs, sessions, pools)
    payload["frame"] = int(frame_px)
    return render_page(payload, note=note)


def write_page(dest: Path, title: str, subtitle: str, cards: list[CellCard],
               fs: float, *, sessions: list[SessionView] | None = None,
               frame_px: int = 1280,
               pools: dict[str, dict[str, np.ndarray]] | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(build_page(title, subtitle, cards, fs,
                               sessions=sessions or [], frame_px=frame_px,
                               pools=pools))
    return dest
