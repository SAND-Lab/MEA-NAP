"""Application entry point."""

import argparse
import sys

from PyQt6.QtWidgets import QApplication

from meanap.gui import theme
from meanap.gui.branding import logo_icon
from meanap.gui.main_window import MainWindow
from meanap.gui.modes import DEFAULT_MODE, MODES


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
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])

    app = QApplication(sys.argv[:1])
    app.setApplicationName("MEA-NAP")
    app.setOrganizationName("SAND Lab")
    # Set on the application so dialogs and the taskbar entry pick it up too,
    # not just the main window.
    app.setWindowIcon(logo_icon())

    theme.apply(app, theme="auto")

    window = MainWindow(mode=args.mode)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
