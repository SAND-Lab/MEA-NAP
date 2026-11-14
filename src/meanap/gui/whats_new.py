"""Tell people who update MEA-NAP what changed, once.

A notice is a Markdown file in ``assets/notices/``, with a short header::

    ---
    version: 1.40.0
    title: Edges are no longer thresholded by significance
    link: https://analysis-pipeline.readthedocs.io/en/latest/news/...
    ---
    What changed and what it means for you, in a few lines.

On start, MEA-NAP shows every notice newer than the version this computer
last ran and no newer than the version running now, then remembers the
running version. A first install records its version and shows nothing:
a notice says what *changed*, and nothing changed for someone who never
used the old behaviour. Downgrading shows nothing either.

Notices are for changes a user must know about to read their results
correctly, such as a new default. Ordinary features belong in the release
notes, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QTextBrowser,
                             QVBoxLayout, QWidget)

NOTICES_DIR = Path(__file__).parent / "assets" / "notices"
SETTINGS_KEY = "whats_new/last_seen_version"
_HEADER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass(frozen=True)
class Notice:
    version: str
    title: str
    body: str
    link: str | None = None

    @property
    def key(self) -> tuple[int, ...]:
        return version_key(self.version)


def version_key(version: str | None) -> tuple[int, ...]:
    """``"v1.36.0-dev.4"`` -> ``(1, 36, 0)``. A development build counts as the
    release it is numbered from, so its notices show with that release's."""
    if not version:
        return ()
    m = re.match(r"v?(\d+(?:\.\d+)*)", str(version).strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def parse(text: str) -> Notice | None:
    m = _HEADER.match(text)
    if not m:
        return None
    fields = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep:
            fields[k.strip().lower()] = v.strip()
    if not version_key(fields.get("version")) or not fields.get("title"):
        return None
    return Notice(version=fields["version"], title=fields["title"],
                  body=text[m.end():].strip(), link=fields.get("link") or None)


def notices(folder: Path = NOTICES_DIR) -> list[Notice]:
    """Every notice shipped with this copy, oldest first."""
    found = []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        n = parse(path.read_text(encoding="utf-8"))
        if n is not None:
            found.append(n)
    return sorted(found, key=lambda n: n.key)


def due(last_seen: str | None, running: str, available: list[Notice]) -> list[Notice]:
    """The notices for an update from *last_seen* to *running*."""
    old, new = version_key(last_seen), version_key(running)
    if not old or not new or new <= old:
        return []
    return [n for n in available if old < n.key <= new]


class WhatsNewDialog(QDialog):
    def __init__(self, items: list[Notice], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("What's new in MEA-NAP")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        intro = QLabel("Since you last used MEA-NAP, something changed that affects "
                       "how results read:" if len(items) == 1 else
                       "Since you last used MEA-NAP, some things changed that affect "
                       "how results read:")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        parts = []
        for n in reversed(items):  # newest first
            more = f"\n\n[Read the full explanation]({n.link})" if n.link else ""
            parts.append(f"## {n.title}\n\n*MEA-NAP {n.version}*\n\n{n.body}{more}")
        self.text.setMarkdown("\n\n---\n\n".join(parts))
        lay.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        links = [n.link for n in items if n.link]
        if links:
            read = buttons.addButton("Read the full explanation",
                                     QDialogButtonBox.ButtonRole.HelpRole)
            read.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(links[-1])))
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)
        self.setWindowModality(Qt.WindowModality.WindowModal)


def _settings() -> QSettings:
    return QSettings("SAND Lab", "MEA-NAP")


def show_if_due(parent: QWidget | None = None, *, running: str | None = None,
                settings: QSettings | None = None,
                available: list[Notice] | None = None) -> WhatsNewDialog | None:
    """Show this update's notices (if any) and remember the running version.

    Returns the dialog it opened, if any (non-blocking, so start-up carries on).
    """
    from meanap.version import meanap_version

    running = running or meanap_version()
    settings = settings or _settings()
    last = settings.value(SETTINGS_KEY, None)
    items = due(last, running, notices() if available is None else available)
    if version_key(running) and version_key(running) > version_key(last):
        settings.setValue(SETTINGS_KEY, running)
    if not items:
        return None
    dialog = WhatsNewDialog(items, parent)
    dialog.show()
    return dialog
