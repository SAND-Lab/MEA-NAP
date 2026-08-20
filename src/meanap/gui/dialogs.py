"""Confirmation dialogs that look the same on every platform.

Qt lays dialog buttons out the way the host platform does, and the platforms
disagree about which end the affirmative button belongs on: Windows and most
Linux desktops put it first, macOS puts it last and focuses the other one. Left
to itself, "Reset all parameters to defaults?" therefore offers **Yes** on the
left with **No** beside it on Linux, and **No** on the left — highlighted, so
it is what Return picks — on a Mac.

That is a reasonable thing for Qt to do and a bad thing for this GUI. The two
buttons swap places between the machine a lab writes its instructions on and
the machine someone follows them on, so "click the left-hand button" means the
opposite thing depending on who is reading, and muscle memory built on one
platform hits the other answer on the other. Screenshots in the docs are wrong
for half the readers.

So the order is pinned to one arrangement everywhere — Yes first and focused,
No second, which is what Linux and Windows already did — rather than left to
the platform. macOS is the one that changes.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QMessageBox,
    QProxyStyle,
    QStyle,
    QWidget,
)


class _FixedButtonLayout(QProxyStyle):
    """A style that answers the button-order question the Windows/Linux way.

    Everything else is delegated to the real style, so the dialog is still
    drawn and spaced natively — only the left-to-right order is overridden.
    """

    def styleHint(self, hint, option=None, widget=None, returnData=None) -> int:  # noqa: D102, N803
        if hint == QStyle.StyleHint.SH_DialogButtonLayout:
            return QDialogButtonBox.ButtonLayout.WinLayout.value
        return super().styleHint(hint, option, widget, returnData)


def build_yes_no(parent: QWidget | None, title: str, text: str) -> QMessageBox:
    """A Yes/No question with Yes first and focused, whatever the platform.

    Separate from :func:`ask_yes_no` only so the button order can be checked
    without a dialog that blocks waiting to be clicked.
    """
    box = QMessageBox(
        QMessageBox.Icon.Question, title, text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        parent,
    )
    buttons = box.findChild(QDialogButtonBox)
    if buttons is not None:
        # Parented to the button box so it outlives this call: a QProxyStyle
        # collected while a live widget is still using it takes the process
        # down with it.
        style = _FixedButtonLayout()
        style.setParent(buttons)
        buttons.setStyle(style)
    # Explicit rather than relying on Yes-is-first also meaning Yes-is-focused.
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    return box


def ask_yes_no(parent: QWidget | None, title: str, text: str) -> bool:
    """Ask *text* and return whether the answer was Yes."""
    box = build_yes_no(parent, title, text)
    box.exec()
    return box.clickedButton() is box.button(QMessageBox.StandardButton.Yes)
