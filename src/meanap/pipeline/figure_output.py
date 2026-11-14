"""Resolution control for saved figures.

Every plotting routine hard-codes the resolution it was tuned for — 150 dpi for
network plots, 300 for the dense multi-panel ones. Those are the right numbers
for a figure you are going to look at closely, and the wrong ones for a gallery
of 109 thumbnails: at 96 dpi the same batch renders in roughly half the time and
a quarter of the bytes, and nobody can tell the difference in a 300-pixel-wide
tile.

Rather than thread a ``dpi`` argument through a dozen plot functions and three
layers of callers, the override lives in a :class:`~contextvars.ContextVar` and
the plotters resolve it at save time via :func:`savefig`. A
:class:`contextvars.ContextVar` — not a module global — because a viewer serves
requests concurrently, and two requests asking for different resolutions must
not race. Each thread gets its own value, and :func:`figure_dpi` restores the
previous one on exit.

The default is ``None``, meaning "whatever the plot function asked for", so
nothing changes for the pipeline and figure parity is unaffected.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DEFAULT_THUMBNAIL_DPI", "figure_dpi", "current_dpi", "savefig", "capture_native",
           "Captured", "capture_figures"]

#: Resolution for gallery thumbnails. Chosen by measurement: against the
#: as-authored mix of 150/300 dpi, 96 dpi cut a 109-figure batch from 11.5 s to
#: 6.1 s and from 8.0 MB to 2.1 MB. Below this the axis labels start to suffer.
DEFAULT_THUMBNAIL_DPI = 96

_dpi_override: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "meanap_figure_dpi", default=None,
)


@contextmanager
def figure_dpi(dpi: int | None):
    """Render figures at *dpi* within this block; ``None`` leaves them alone."""
    token = _dpi_override.set(dpi)
    try:
        yield
    finally:
        _dpi_override.reset(token)


def current_dpi() -> int | None:
    """The resolution override in force, or ``None``."""
    return _dpi_override.get()


@dataclass
class Captured:
    """A figure a plotter was about to save, handed over live instead."""

    figure: object
    path: Path
    #: Whether the plotter saved with ``bbox_inches="tight"`` — the file would
    #: have been cropped to the artists, so a live view should crop too.
    tight: bool
    pad_inches: float


_capture: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "meanap_figure_capture", default=None,
)


@contextmanager
def capture_figures():
    """Collect the figures drawn in this block instead of writing them.

    The native viewer shows the matplotlib figure itself — zoomable, with the
    artists still there to hover over — and the only way to get that from
    plotters that end in ``savefig(...); plt.close(fig)`` without touching each
    of them is to intercept the save. Nothing is written while a capture is
    active, so the plotter's drawing cost is paid and its encoding cost is not.
    ``plt.close`` afterwards only detaches the figure from pyplot; the object
    lives on and can be given a new canvas.

    A :class:`~contextvars.ContextVar` for the same reason as the resolution
    override: renders run on worker threads and must not see each other's.
    """
    captured: list[Captured] = []
    token = _capture.set(captured)
    try:
        yield captured
    finally:
        _capture.reset(token)


def capture_native(figure, path: Path) -> bool:
    """Hand a Qt-drawn figure to an active capture. ``False`` if there is none.

    *figure* is a :class:`meanap.native.output.NativeFigure`: the scene and its
    painter, which a viewer shows live rather than as a picture.
    """
    captured = _capture.get()
    if captured is None:
        return False
    captured.append(Captured(figure, Path(path), tight=False, pad_inches=0.0))
    return True


def savefig(fig, path: Path, *, default_dpi: int, **kwargs) -> None:
    """Save *fig*, honouring any active override in preference to *default_dpi*.

    Creates the parent directory, so callers don't each repeat that.
    """
    path = Path(path)
    captured = _capture.get()
    if captured is not None:
        captured.append(Captured(
            fig, path, tight=kwargs.get("bbox_inches") == "tight",
            pad_inches=float(kwargs.get("pad_inches", 0.1))))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=current_dpi() or default_dpi, **kwargs)
