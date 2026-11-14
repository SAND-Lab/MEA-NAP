"""Figures for a viewer that shows the figure itself, not a picture of it.

The web viewer asks :class:`~meanap.viewer.server.ViewerService` for a file and
shows it in an ``<img>``. A Qt viewer can do better with the same drawing code:
host the matplotlib figure, so it can be zoomed and its marks pointed at. This
runs the service's own render functions with the save intercepted
(:func:`meanap.pipeline.figure_output.capture_figures`) and returns what they
drew.

No Qt here, so it can be tested without a display. The figure is created on the
calling thread and must not be touched by it after it is handed on.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from meanap.pipeline.figure_output import capture_figures

__all__ = ["Live", "live_figure", "KINDS", "GROUP_KINDS"]

#: The per-recording figure families, in the order a reader meets them...
KINDS = ("activity", "network", "spike_check", "sorting_check", "edge_check", "stim",
         "stim_check")
#: ...and the ones that span recordings.
GROUP_KINDS = ("comparison", "lag_series", "stats")


@dataclass
class Live:
    """One drawn figure, or — for a plotter that saves by another route — its file."""

    figure: object | None
    image: Path | None
    #: Crop to the artists, as the plotter's own ``bbox_inches="tight"`` would.
    tight: bool
    pad_inches: float
    #: Seconds spent drawing, for the viewer to show.
    seconds: float


def live_figure(service, kind: str, recording: str | None = None, name: str | None = None, *,
                lag: int | str | None = None, overrides: dict | None = None,
                variant: str | None = None, keep_dir: Path | None = None,
                family: str | None = None, level: str | None = None,
                split: str | None = None, metric: str | None = None,
                series: str | None = None, key: str | None = None) -> Live:
    """Draw one per-recording figure and hand it back live.

    *kind* is one of :data:`KINDS` — addressed by *recording* and *name* — or of
    :data:`GROUP_KINDS`: a ``comparison`` by *family*, *level*, *split*,
    *metric* (and *lag*), a ``lag_series`` by *series* and *key*, a ``stats``
    figure by *lag* (its folder name) and *key*. ``overrides`` is what
    :func:`meanap.viewer.controls.parse_overrides` returns. *variant* is the
    scale (``"plain"``, ``"scaled"``, ``"combined"``) of a network figure
    (``"plain"`` if None) or of an activity raster or heatmap (both panels, as
    saved, if None). A plotter that does
    not go through the shared ``savefig`` cannot be intercepted; its file is
    written under *keep_dir* and returned as ``image`` instead.
    """
    from meanap.pipeline import render

    ctx = service.ctx
    out_dir = Path(keep_dir) if keep_dir is not None else Path(tempfile.mkdtemp(
        prefix="meanap-live-"))
    started = time.perf_counter()
    path = None
    with capture_figures() as got:
        try:
            if kind == "network":
                path = render.render_figure(
                    ctx, recording, int(lag), name, out_dir,
                    overrides=overrides or None, variant=variant or "plain")
            elif kind == "activity":
                path = render.render_activity_figure(
                    ctx, recording, name, out_dir, overrides=overrides or None)
            elif kind == "spike_check":
                path = render.render_spike_check_figure(
                    ctx, recording, name, out_dir)
            elif kind == "sorting_check":
                path = render.render_sorting_check_figure(
                    ctx, recording, name, out_dir)
            elif kind == "edge_check":
                path = render.render_edge_check_figure(
                    ctx, recording, int(lag), out_dir)
            elif kind == "stim":
                path = render.render_stim_figure(ctx, recording, name, out_dir)
            elif kind == "stim_check":
                path = render.render_stim_check_figure(ctx, recording, name, out_dir)
            elif kind == "comparison":
                path = render.render_comparison_figure(
                    ctx, family, level, split, metric, out_dir,
                    lag=None if lag is None else int(lag), overrides=overrides or None)
            elif kind == "lag_series":
                path = render.render_lag_series_figure(
                    ctx, series, key, out_dir, overrides=overrides or None)
            elif kind == "stats":
                path = render.render_stats_figure(
                    ctx, str(lag), key, out_dir, overrides=overrides or None)
            else:
                raise ValueError(f"Unknown figure kind: {kind!r}")
        except ValueError:
            # The renderers report "nothing was written" as an error, and with
            # the save intercepted nothing is. Only a real failure — nothing
            # drawn either — is one here.
            if not got:
                raise
    seconds = time.perf_counter() - started
    if got:
        # A plotter asked for one figure may still draw its siblings; the one
        # wanted is the one whose file name was asked for, else the last.
        wanted = ([c for c in got if Path(c.path).stem.endswith(Path(name).stem)]
                  if name else [])
        pick = (wanted or got)[-1]
        figure = pick.figure
        if kind == "activity" and variant is not None:
            # The raster and heatmaps hold both scales; show the one asked for.
            figure = render.pick_scale(figure, variant)
        return Live(figure, None, pick.tight, pick.pad_inches, seconds)
    return Live(None, Path(path), False, 0.0, seconds)
