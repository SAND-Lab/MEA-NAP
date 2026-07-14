"""Application entry point."""

import sys

from PyQt6.QtWidgets import QApplication

from meanap.gui import theme
from meanap.gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MEA-NAP")
    app.setOrganizationName("SAND Lab")

    theme.apply(app, theme="auto")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
