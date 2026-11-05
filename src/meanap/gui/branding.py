"""Logo assets for the GUI, per pipeline.

Three pipelines share one window, so the logo follows the mode — the same way
the tab set and the version label do. All three have artwork now; a mode whose
file is missing falls back to MEA-NAP's, so a missing asset never breaks the GUI.

**To change one**: replace its file in ``assets/`` (see :data:`LOGO_FILES`).
Nothing else needs to change — the lookup is by mode key, and
:func:`available_logos` reports which modes have their own. A wide, short image
works best: it is drawn at :data:`CORNER_LOGO_HEIGHT` in the tab strip's corner
and 96 px in the tutorial, and the corner has room for roughly 4:1 before it
starts competing with the tabs for width.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap

ASSETS = Path(__file__).resolve().parent / "assets"

#: Artwork per mode key. Absent files fall back to MEA-NAP's.
LOGO_FILES = {
    "meanap": "mea-nap-logo.png",
    "catnap": "catnap-logo.png",
    "meastim": "meastim-logo.png",
}

#: The fallback, and the window/taskbar icon. MEA-NAP is the suite's identity
#: even when a sub-pipeline is running, so an unbranded mode borrowing it reads
#: as intended rather than as a missing asset.
LOGO_PATH = ASSETS / LOGO_FILES["meanap"]

#: Height of the logo in the tab strip's corner.
#:
#: Bounded by the tabs, not chosen freely: Qt gives a ``QTabWidget`` corner
#: widget the height of a *tab*, so anything taller is drawn clipped rather
#: than making room for itself. (Growing the tab bar alone does not help —
#: the corner keeps the tab's height and the extra space goes to a gap.) The
#: tabs are padded in ``theme._EXTRA_QSS`` to make a 70 px tab, which is what
#: this may fill; raising one without the other either clips the logo or
#: leaves a gap beside it.
CORNER_LOGO_HEIGHT = 69


def logo_path(mode: str = "meanap") -> Path:
    """Artwork for *mode*, falling back to MEA-NAP's when it has none of its own."""
    candidate = ASSETS / LOGO_FILES.get(mode, LOGO_FILES["meanap"])
    return candidate if candidate.is_file() else LOGO_PATH


@lru_cache(maxsize=1)
def available_logos() -> tuple[str, ...]:
    """Mode keys that have their *own* artwork, not the fallback.

    Cached: the answer changes only when a file is added, which needs a restart
    to take effect anyway.
    """
    return tuple(mode for mode, name in LOGO_FILES.items()
                 if (ASSETS / name).is_file())


def logo_pixmap(height: int, device_pixel_ratio: float = 1.0,
                mode: str = "meanap") -> QPixmap | None:
    """The logo for *mode*, scaled to *height* pixels, or ``None`` if unavailable.

    Rendered at ``device_pixel_ratio`` times the requested size and tagged as
    such, so the artwork stays sharp on HiDPI screens while still laying out as
    ``height`` logical pixels. Returns ``None`` rather than raising if the asset
    is missing — a missing logo should never stop the GUI from opening.
    """
    path = logo_path(mode)
    if not path.exists():
        return None
    source = QPixmap(str(path))
    if source.isNull():
        return None

    ratio = max(1.0, float(device_pixel_ratio))
    scaled = source.scaledToHeight(
        int(round(height * ratio)),
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(ratio)
    return scaled


def logo_icon(mode: str = "meanap") -> QIcon:
    """The logo as a window/taskbar icon (empty QIcon if the asset is missing)."""
    path = logo_path(mode)
    return QIcon(str(path)) if path.exists() else QIcon()
