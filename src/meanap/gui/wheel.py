"""Stop scrolling *past* a settings field from changing what it says.

A spin box or a combo box takes the wheel whenever the pointer happens to be
over it. On a tab that is itself a scrolling column of settings — which is most
of them — rolling the wheel to get further down the page silently retunes
whichever field the pointer crossed on the way. Nothing says it happened: the
page keeps scrolling, the number is simply different afterwards, and the run
uses it.

The rule here is the one people expect from a form: a field responds to the
wheel once you have clicked into it, and until then the wheel belongs to the
page. Two things have to be true for that.

*The field must not accept the wheel while unfocused.* It is not enough to
swallow the event — the page still has to scroll — so the event is handed on
to the enclosing scroll area instead.

*A wheel turn must not be what gives a field focus.* Qt starts these widgets on
``WheelFocus``, so the first turn focuses the field and every turn after that
edits it, which would make this guard hold only until it was needed. They are
put on ``StrongFocus``: click and Tab still focus them, the wheel does not.

That second part has to happen *before* the field is ever scrolled over, not on
the way past. For a real wheel turn Qt hands out focus in ``QApplication::notify``,
which runs before the application's event filters — so a guard that downgrades
the policy when it sees a wheel event has already been overtaken: the field took
focus a moment ago, and this filter, finding it focused, stands politely aside.
That is a first turn on every field doing exactly what the guard exists to
prevent, and it hides itself, because the same turn fixes the policy and the
second turn behaves. So every field is defused up front, and again on
``Polish`` for fields built later.

Installed on the application, so it covers every field on every tab, including
ones built later — a per-widget opt-in would be one ``setFocusPolicy`` call
away from a silent hole, in a bug whose whole nature is that nobody notices it.
"""

from __future__ import annotations

import atexit

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import (
    QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QSlider,
    QWidget,
)

__all__ = ["install_wheel_guard"]

#: Widgets whose value a wheel turn changes. Deliberately not
#: ``QAbstractSlider``: that is also a scroll *bar*, and guarding those would
#: stop the very scrolling this exists to protect.
GUARDED = (QAbstractSpinBox, QComboBox, QSlider)


def _guarded_widget(obj: QObject) -> QWidget | None:
    """The field *obj* belongs to, if any.

    Walks up from the receiving widget because the wheel event is delivered to
    whatever is under the pointer, and for a spin box that is usually its
    internal line edit rather than the box itself.

    Stops at a window boundary: an open combo box's popup is its own window,
    and scrolling *that* list is a real thing to want.
    """
    widget = obj if isinstance(obj, QWidget) else None
    while widget is not None:
        if isinstance(widget, GUARDED):
            return widget
        if widget.isWindow():
            return None
        widget = widget.parentWidget()
    return None


def _scrolling_ancestor(widget: QWidget) -> QAbstractScrollArea | None:
    """The scroll area the wheel turn was meant for."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return parent
        if parent.isWindow():
            return None
        parent = parent.parentWidget()
    return None


def _defuse(widget: QObject) -> None:
    """Take the wheel out of *widget*'s focus policy, if it is a field."""
    if (isinstance(widget, GUARDED)
            and widget.focusPolicy() == Qt.FocusPolicy.WheelFocus):
        widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class _WheelGuard(QObject):
    """Application event filter implementing the rule in the module docstring."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: D102
        event_type = event.type()

        # Every widget is polished before it is first shown, so this catches
        # dialogs and the rows panels add as you use them — anything built
        # after the sweep at install time.
        if event_type == QEvent.Type.Polish:
            _defuse(obj)
            return False

        if event_type != QEvent.Type.Wheel:
            return False

        field = _guarded_widget(obj)
        if field is None:
            return False

        # A backstop only. By the time a wheel event arrives Qt has already
        # decided about focus, so this cannot be what makes the rule hold —
        # see the module docstring.
        _defuse(field)

        if field.hasFocus():
            return False        # clicked into: the wheel is theirs

        area = _scrolling_ancestor(field)
        if area is not None:
            # Swallowing it would leave the page stuck under the pointer, which
            # reads as a broken scroll wheel. Hand it to the page instead.
            QApplication.sendEvent(area.viewport(), event)
        return True


#: Module-level so the filter outlives the call that installed it — a filter
#: that is garbage collected stops filtering, silently.
_GUARD: _WheelGuard | None = None


def install_wheel_guard(app: QApplication | None = None) -> None:
    """Install the guard on *app*. Safe to call more than once."""
    global _GUARD
    app = app or QApplication.instance()
    if app is None or _GUARD is not None:
        return
    _GUARD = _WheelGuard()
    app.installEventFilter(_GUARD)
    # Everything already built. The filter only sees a widget from its next
    # event onwards, and for a field that has been polished already that is one
    # event too late.
    for widget in app.allWidgets():
        _defuse(widget)
    # Taken off again before the interpreter tears the module down. Left
    # installed while the QApplication is destroyed, this filter segfaults the
    # process during shutdown — after everything has already run and passed, so
    # it surfaces as a crash with no Python frame to point at. Removing it
    # first is what stops that; parenting it to the application instead does
    # not.
    atexit.register(_uninstall, app)


def _uninstall(app: QApplication) -> None:
    global _GUARD
    if _GUARD is None:
        return
    try:
        app.removeEventFilter(_GUARD)
    except RuntimeError:
        pass        # the application went first; nothing left to detach from
    _GUARD = None
