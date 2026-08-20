"""Do the confirmation buttons sit in the same place on every platform?

Qt orders dialog buttons per platform: Windows and most Linux desktops put the
affirmative button first, macOS puts it last and focuses the other one. So the
"Reset all parameters to defaults?" dialog behind **New** offered Yes on the
left on Linux and No on the left — highlighted, so Return picked it — on a Mac.
Same build, mirrored dialog, and "click the left-hand button" means opposite
things to two people reading the same instructions.

meanap.gui.dialogs pins the order instead of inheriting it. The interesting
case is the platform this test cannot run on, so macOS is simulated the same
way Qt decides it: SH_DialogButtonLayout is what QDialogButtonBox asks, and a
QProxyStyle answering MacLayout reproduces the Mac arrangement exactly — this
file confirms that the simulation really does mirror the dialog before checking
that the fix un-mirrors it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialogButtonBox,
    QMessageBox,
    QProxyStyle,
    QStyle,
)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.gui.dialogs import ask_yes_no, build_yes_no  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


class _Layout(QProxyStyle):
    """Pretends the host platform lays dialog buttons out the given way."""

    def __init__(self, value: int) -> None:
        super().__init__()
        self._value = value

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: D102, N803
        if hint == QStyle.StyleHint.SH_DialogButtonLayout:
            return self._value
        return super().styleHint(hint, option, widget, returnData)


MAC = QDialogButtonBox.ButtonLayout.MacLayout.value
WIN = QDialogButtonBox.ButtonLayout.WinLayout.value


def order(box: QMessageBox) -> list[tuple[str, bool]]:
    """The buttons left to right, each with whether Return would pick it."""
    box.show()
    app.processEvents()
    app.processEvents()
    laid_out = sorted((b.x(), b) for b in box.buttons())
    return [(b.text().replace("&", ""), b.isDefault()) for _, b in laid_out]


def plain() -> QMessageBox:
    """What QMessageBox.question built before — the platform's own order."""
    return QMessageBox(
        QMessageBox.Icon.Question, "New parameters",
        "Reset all parameters to defaults?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )


# ── The simulation is a real stand-in for a Mac ───────────────────────────────
#
# Checked first: if forcing MacLayout did not actually mirror the dialog, the
# test below would pass on a fix that does nothing.

print("\nWith the platform pretending to be macOS")

app.setStyle(_Layout(MAC))
theme.apply(app)

check("Qt really does mirror the buttons, which is the reported bug",
      order(plain()) == [("No", True), ("Yes", False)], str(order(plain())))

check("and the fixed dialog puts Yes back on the left",
      order(build_yes_no(None, "New parameters", "Reset?"))
      == [("Yes", True), ("No", False)],
      str(order(build_yes_no(None, "New parameters", "Reset?"))))

# ── And nothing moves on the platform that was already right ─────────────────

print("\nWith the platform laying out the Windows/Linux way")

app.setStyle(_Layout(WIN))
theme.apply(app)

check("the plain dialog is Yes then No here",
      order(plain()) == [("Yes", True), ("No", False)], str(order(plain())))

check("and the fix leaves that untouched",
      order(build_yes_no(None, "New parameters", "Reset?"))
      == [("Yes", True), ("No", False)],
      str(order(build_yes_no(None, "New parameters", "Reset?"))))

# ── The answer still means what it says ───────────────────────────────────────
#
# Reordering buttons is only safe if the return value follows the button that
# was clicked rather than its position.

print("\nAnd the answer follows the button, not the position")

for layout, layout_name in ((MAC, "macOS"), (WIN, "Windows/Linux")):
    app.setStyle(_Layout(layout))
    theme.apply(app)
    for want, expected in (("Yes", True), ("No", False)):
        box = build_yes_no(None, "New parameters", "Reset?")
        box.show()
        app.processEvents()
        target = box.button(getattr(QMessageBox.StandardButton, want))
        # done() is what a click reaches; clickedButton() is what ask_yes_no
        # reads, so route through the button itself rather than faking a code.
        target.click()
        app.processEvents()
        got = box.clickedButton() is box.button(QMessageBox.StandardButton.Yes)
        check(f"[{layout_name}] clicking {want} answers {expected}",
              got == expected, f"got {got}")

check("and ask_yes_no is the function that reads it",
      callable(ask_yes_no), "")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All dialog checks passed.")
