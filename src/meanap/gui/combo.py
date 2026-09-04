"""Make a combo box's popup as wide as the options it lists.

Qt opens a combo box's popup at the width of the *box*, and the box is sized
by the form it sits in — so a narrow field lists its options in a narrow strip.
That would be harmless if the list drew its items the way the box does, but it
does not: the popup adds a check-mark column to the left of every row (18px
under this theme, plus its spacing), and that column comes out of the same
width. The text is what gives way. On the Pipeline tab's "Verbose level" the
box is 82px and the popup gives its rows 72 of that, of which the check column
takes 24 — so "Verbose" is drawn into 48px of a 50px word and comes out a few
pixels short: enough to read as broken, not enough to guess at.

So the popup is given a minimum width covering what it actually has to draw:

    what the box would need for the widest option
      + the check column + its spacing + the popup's own frame

Every term comes from the style rather than from a constant — the check column
and the paddings are the theme's (``qdarktheme``'s) and would move if the theme
did. The **box** is left exactly as it was: widening those would reflow every
settings form to suit the longest word in a dropdown.

Installed on the application, like the wheel guard, so it covers combo boxes
built later — the cell-type rows and the results pickers add theirs as you use
them, and those are the ones with the long labels.
"""

from __future__ import annotations

import atexit

from PyQt6.QtCore import QEvent, QObject, QSize
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QStyle, QStyleOptionComboBox,
)

__all__ = ["popup_width", "fit_popup", "install_combo_popup_fit"]

#: Marks a combo box whose popup this module already keeps up to date, so a
#: second polish — ``setStyleSheet`` triggers one — doesn't stack connections.
_FITTED = "_meanap_popup_fitted"


def popup_width(combo: QComboBox) -> int:
    """The width *combo*'s popup needs to draw its longest option in full.

    A *minimum*, not a size: Qt already opens the popup at the width of the
    box, so this only ever widens it. Deliberately not clamped up to
    ``combo.width()`` — the box has not been laid out yet when this is first
    called, and a stale placeholder width would be baked in as a floor.

    Capped at the screen the box will open on, so one very long option cannot
    produce a popup that runs off the edge.
    """
    if combo.count() == 0:
        return 0

    view = combo.view()
    metrics = QFontMetrics(view.font())

    icon_width = 0
    if any(not combo.itemIcon(i).isNull() for i in range(combo.count())):
        # Matching QComboBoxPrivate::computeWidthHint: the icon and the gap
        # after it, for the widest item, whether or not that item has one.
        icon_width = combo.iconSize().width() + 4

    text_width = max(metrics.horizontalAdvance(combo.itemText(i))
                     for i in range(combo.count()))

    # What the *box* would have to be to show that text — the same question Qt
    # answers for AdjustToContents, so the theme's own horizontal padding round
    # a label is included rather than guessed at. It also counts the drop-down
    # arrow, which the popup does not draw; that surplus is the slack that
    # keeps this from landing a pixel short when a font substitutes.
    option = QStyleOptionComboBox()
    combo.initStyleOption(option)
    width = combo.style().sizeFromContents(
        QStyle.ContentsType.CT_ComboBox, option,
        QSize(text_width + icon_width, metrics.height()), combo,
    ).width()

    def pm(metric: QStyle.PixelMetric) -> int:
        return view.style().pixelMetric(metric, None, view)

    # Then what the popup draws and the box does not.
    width += (
        2 * view.frameWidth()                               # its border and padding
        + pm(QStyle.PixelMetric.PM_IndicatorWidth)          # the check column
        + pm(QStyle.PixelMetric.PM_CheckBoxLabelSpacing)    # …and the gap after it
    )
    # A list longer than the popup shows scrolls, and the scroll bar is inside
    # the width — so without this the fix would clip the text again on exactly
    # the long lists that need it most.
    if combo.count() > combo.maxVisibleItems():
        width += pm(QStyle.PixelMetric.PM_ScrollBarExtent)

    screen = combo.screen()
    if screen is not None:
        width = min(width, screen.availableGeometry().width())
    return width


def fit_popup(combo: QComboBox) -> None:
    """Size *combo*'s popup to its options. Cheap; safe to call again."""
    combo.view().setMinimumWidth(popup_width(combo))


def _track(combo: QComboBox) -> None:
    """Fit *combo* now, and again whenever its options change.

    A combo box is usually polished before it is filled — and several here are
    refilled as the run's output changes — so fitting once at install time
    would size the popups of exactly the lists that never change.
    """
    if combo.property(_FITTED):
        return
    combo.setProperty(_FITTED, True)

    def refit(*_args: object) -> None:
        # The Python wrapper outlives the C++ widget, and a model signal can
        # still arrive after the combo has been deleted — during teardown, or
        # when a panel rebuilds its rows.
        try:
            fit_popup(combo)
        except RuntimeError:
            pass

    model = combo.model()
    model.rowsInserted.connect(refit)
    model.rowsRemoved.connect(refit)
    model.modelReset.connect(refit)
    model.dataChanged.connect(refit)
    refit()


class _PopupFitter(QObject):
    """Application event filter that tracks every combo box it meets."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: D102
        # Polish, as in wheel.py: every widget is polished before it is first
        # shown, so this covers the rows and dialogs built as the app is used.
        if event.type() == QEvent.Type.Polish and isinstance(obj, QComboBox):
            _track(obj)
        return False


#: Module-level so the filter outlives the call that installed it.
_FITTER: _PopupFitter | None = None


def install_combo_popup_fit(app: QApplication | None = None) -> None:
    """Install the fitter on *app*. Safe to call more than once."""
    global _FITTER
    app = app or QApplication.instance()
    if app is None or _FITTER is not None:
        return
    _FITTER = _PopupFitter()
    app.installEventFilter(_FITTER)
    # Everything already built: the filter only sees a widget from its next
    # event on, and the window's own combo boxes are polished by then.
    for widget in app.allWidgets():
        if isinstance(widget, QComboBox):
            _track(widget)
    # Removed before the QApplication is torn down — an application event
    # filter that outlives it crashes the process during shutdown. See the
    # same note in wheel.py.
    atexit.register(_uninstall, app)


def _uninstall(app: QApplication) -> None:
    global _FITTER
    if _FITTER is None:
        return
    try:
        app.removeEventFilter(_FITTER)
    except RuntimeError:
        pass        # the application went first; nothing left to detach from
    _FITTER = None
