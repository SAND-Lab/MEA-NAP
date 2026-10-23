"""Application entry point."""

import argparse
import sys
import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from meanap.frozen import is_frozen
from meanap.gui import theme
from meanap.gui.branding import logo_icon, logo_pixmap
from meanap.gui.modes import DEFAULT_MODE, MODES
from meanap.gui.versions_dialog import check_on_start, default_version

# Kept light on purpose: the main window imports the whole pipeline (scipy,
# numba, pandas, spikeinterface …), which takes seconds — on Windows, with
# antivirus scanning every library the first time, much longer. Everything
# imported up here comes before the splash screen can appear.


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="meanap-gui",
        description="Launch the MEA-NAP GUI.",
    )
    parser.add_argument(
        "--mode",
        choices=list(MODES),
        default=DEFAULT_MODE,
        help=("which pipeline to start in — the window shows only that "
              "pipeline's tabs, and you can switch at any time with the Mode "
              "selector in the toolbar. "
              + "; ".join(f"{key}: {mode.blurb}" for key, mode in MODES.items())),
    )
    parser.add_argument(
        "--here",
        action="store_true",
        help=("open this copy of MEA-NAP even when another version is set as "
              "the default in the versions dialog"),
    )
    return parser.parse_args(argv)


def _open_default_version(argv: list[str]) -> None:
    """Switch to the version chosen as default, if that is not this one.

    Before any window exists, so the user sees one window — the right one.
    Returns (and this copy opens) when there is nothing to switch to, or
    switching fails; otherwise it does not return.
    """
    from meanap import updates

    choice = default_version()
    if not choice:
        return
    try:
        folder = updates.default_folder(choice, updates.find_checkout())
    except updates.GitError as exc:
        print(f"MEA-NAP: could not open your default version, {choice} ({exc}). "
              "Opening this copy instead.", file=sys.stderr)
        return
    if folder is None:
        return
    name = "cutting edge (main)" if choice == updates.MAIN else choice
    print(f"MEA-NAP: opening your default version, {name}, from {folder}. "
          "Start with --here to open this copy instead.", file=sys.stderr)
    updates.exec_into(updates.launch_plan(folder), tuple(argv))


def _show_splash(app: QApplication, mode: str) -> QSplashScreen | None:
    """The logo, on screen while the main window's imports load."""
    ratio = app.devicePixelRatio()
    logo = logo_pixmap(200, ratio, mode=mode)
    if logo is None:
        return None
    # On a white card, with room for the message below: the logo itself is
    # transparent, which a frameless window may show as black.
    pad, below = 24, 36
    width = round(logo.width() / ratio) + 2 * pad
    height = round(logo.height() / ratio) + pad + below
    card = QPixmap(round(width * ratio), round(height * ratio))
    card.setDevicePixelRatio(ratio)
    card.fill(QColor("white"))
    painter = QPainter(card)
    painter.drawPixmap(pad, pad, logo)
    painter.setPen(QColor("#c8c8c8"))
    painter.drawRect(0, 0, width - 1, height - 1)
    painter.end()
    splash = QSplashScreen(card)
    splash.showMessage("Starting MEA-NAP …",
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                       QColor("#555555"))
    splash.show()
    app.processEvents()
    return splash


def main() -> None:
    started = time.perf_counter()
    args = _parse_args(sys.argv[1:])
    # The desktop app is one fixed version, with no clone to open another from.
    if not args.here and not is_frozen():
        _open_default_version(sys.argv[1:])

    theme.enable_hi_dpi()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("MEA-NAP")
    app.setOrganizationName("SAND Lab")
    # Set on the application so dialogs and the taskbar entry pick it up too,
    # not just the main window.
    app.setWindowIcon(logo_icon())

    theme.apply(app)
    splash = _show_splash(app, args.mode)

    from meanap.gui.main_window import MainWindow

    window = MainWindow(mode=args.mode)
    window.show()
    if splash is not None:
        splash.finish(window)
    print(f"MEA-NAP: window ready {time.perf_counter() - started:.1f} s after start",
          file=sys.stderr)
    window.report_app_update()
    if check_on_start():
        window.start_update_check()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
