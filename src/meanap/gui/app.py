"""Application entry point."""

import argparse
import sys

from PyQt6.QtWidgets import QApplication

from meanap.gui import theme
from meanap.gui.branding import logo_icon
from meanap.gui.main_window import MainWindow
from meanap.gui.modes import DEFAULT_MODE, MODES
from meanap.gui.versions_dialog import check_on_start, default_version


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


def main() -> None:
    args = _parse_args(sys.argv[1:])
    if not args.here:
        _open_default_version(sys.argv[1:])

    app = QApplication(sys.argv[:1])
    app.setApplicationName("MEA-NAP")
    app.setOrganizationName("SAND Lab")
    # Set on the application so dialogs and the taskbar entry pick it up too,
    # not just the main window.
    app.setWindowIcon(logo_icon())

    theme.apply(app)

    window = MainWindow(mode=args.mode)
    window.show()
    if check_on_start():
        window.start_update_check()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
