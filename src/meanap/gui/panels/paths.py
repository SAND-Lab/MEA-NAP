"""The label + line-edit + Browse row that every path setting is made of.

The panel this used to be is now :mod:`meanap.gui.panels.data`; what is left is
the widget the folder settings across the window are all built from.
"""

from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget,
)

__all__ = ["PathRow"]


def _browse_dir(line_edit: QLineEdit, parent: QWidget) -> None:
    path = QFileDialog.getExistingDirectory(parent, "Select folder", line_edit.text())
    if path:
        line_edit.setText(path)


def _browse_file(line_edit: QLineEdit, parent: QWidget, filter: str = "") -> None:
    path, _ = QFileDialog.getOpenFileName(parent, "Select file", line_edit.text(), filter)
    if path:
        line_edit.setText(path)


class PathRow(QWidget):
    """A label + line-edit + browse button row."""

    def __init__(self, parent: QWidget, initial: str = "", is_file: bool = False, file_filter: str = "") -> None:
        super().__init__(parent)
        self._is_file = is_file
        self._file_filter = file_filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit = QLineEdit(initial)
        btn = QPushButton("Browse…")
        btn.setFixedWidth(80)
        btn.clicked.connect(self._browse)

        layout.addWidget(self.line_edit)
        layout.addWidget(btn)

    def _browse(self) -> None:
        if self._is_file:
            _browse_file(self.line_edit, self, self._file_filter)
        else:
            _browse_dir(self.line_edit, self)

    @property
    def value(self) -> str:
        return self.line_edit.text()

    def set_value(self, v: str) -> None:
        self.line_edit.setText(v)
