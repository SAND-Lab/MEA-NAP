"""Small widget helpers shared by the tabs."""

from __future__ import annotations

from PyQt6.QtWidgets import QPushButton, QScrollArea, QWidget


def scrollable(widget: QWidget) -> QScrollArea:
    """Put *widget* in a frameless scroll area that resizes with it.

    A column of settings has a minimum height it cannot lay out below. Left
    to itself that minimum becomes a floor for the whole window, and on a
    screen too short to satisfy it Qt lays the rows out below their minimum
    anyway — buttons lose their bottom half and neighbouring rows overlap.
    Scrolling is what makes the column fit any height honestly.
    """
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    return area


def pin_width(button: QPushButton, minimum: int) -> None:
    """Hold *button* to *minimum* pixels, or to its label if that is wider.

    A width in pixels is a width measured in one machine's UI font. Where the
    font is larger the button keeps the pixel width and clips its own label
    instead — which is how "Load markers" arrived as "Load marker" on a
    collaborator's screen. Keeping the number as a floor leaves every layout
    that already fitted exactly as it was, and lets the odd button grow.
    """
    button.setFixedWidth(max(minimum, button.sizeHint().width()))
