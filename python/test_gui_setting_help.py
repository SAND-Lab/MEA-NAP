"""The run settings' explanation cards (ⓘ on the settings tabs).

    QT_QPA_PLATFORM=offscreen uv run python test_gui_setting_help.py
"""

from __future__ import annotations

import dataclasses
import sys
import time

from PyQt6.QtWidgets import QApplication, QFormLayout, QLabel

Check = tuple[str, bool, str]

#: Rows that say what was found rather than set anything, or that only choose
#: what the GUI shows: no card is wanted.
NO_CARD = {
    ("CAT-NAP (calcium imaging)", "Cells (iscell)"),
    ("CAT-NAP (calcium imaging)", "Sampling rate"),
    ("CAT-NAP (calcium imaging)", "Duration"),
    ("CAT-NAP (calcium imaging)", "Denoised data"),
    ("CAT-NAP (calcium imaging)", "Cells to preview"),
}
#: The tabs whose every setting should have a card.
COVERED_TABS = {"Data", "Spike detection", "Connectivity", "Stimulation",
                "CAT-NAP (calcium imaging)", "Stats & ML"}


def _wait(app, ms: int = 30) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(title)
    passed = 0
    for name, ok, detail in checks:
        passed += bool(ok)
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok or not detail else f"  — {detail}"))
    print(f"  → {passed}/{len(checks)} passed")
    return passed, len(checks)


def _card_checks() -> list[Check]:
    from meanap.gui.setting_help import settings_cards
    from meanap.metric_info import SETTINGS_DIR, lookup
    from meanap.params import Params

    cards = settings_cards()
    fields = {f.name for f in dataclasses.fields(Params)}
    checks: list[Check] = [("there are cards for the run settings", len(cards) >= 20,
                            str(len(cards)))]
    bad = [(k, f) for k, c in cards.items()
           for f in c.meta.get("params", "").split(",") if f.strip() and f.strip() not in fields]
    checks.append(("every setting a card names is a real params field", not bad, str(bad)))
    loose = [(k, r) for k, c in cards.items() for r in c.related
             if lookup(r, SETTINGS_DIR) is None]
    checks.append(("every related card exists", not loose, str(loose)))
    pictures = [(k, c.image) for k, c in cards.items()
                if c.image and not (SETTINGS_DIR / c.image).is_file()]
    checks.append(("every picture a card names is there", not pictures, str(pictures)))
    unplaced = [k for k, c in cards.items() if not c.meta.get("tab") or not c.labels]
    checks.append(("every card says which tab and labels it explains", not unplaced,
                   str(unplaced)))
    sections = [k for k, c in cards.items()
                if not all(f"## {h}" in c.body for h in ("What it does", "Choosing a value"))]
    checks.append(("each says what the setting does and how to choose it", not sections,
                   str(sections)))
    owners: dict[tuple, str] = {}
    twice = []
    from meanap.gui.setting_help import card_tabs, card_text

    for k, c in cards.items():
        for at in [(t, card_text(label)) for t in card_tabs(c) for label in c.labels]:
            if at in owners:
                twice.append((at, owners[at], k))
            owners[at] = k
    checks.append(("no label is explained by two cards", not twice, str(twice)))
    wavelets = cards.get("wavelets")
    checks.append(("the wavelet card shows what each wavelet looks like",
                   wavelets is not None and (wavelets.image or "![" in wavelets.body),
                   ""))
    return checks


def _window_checks(app) -> list[Check]:
    from meanap.gui.main_window import MainWindow
    from meanap.gui.setting_help import (
        LABEL, MARK, MARK_NAME, card_tabs, card_text, settings_cards,
    )
    from meanap.gui.settings_search import _plain, index_tabs

    checks: list[Check] = []
    cards = settings_cards()
    found: set[tuple] = set()
    uncovered: set[tuple] = set()
    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    _wait(app, 100)
    help_ = window._setting_help
    for mode in ("meanap", "meastim", "catnap"):
        window._apply_mode(mode)
        _wait(app, 50)
        tabs = window._tabs
        for i in range(tabs.count()):
            tab, page = _plain(tabs.tabText(i)), tabs.widget(i)
            for key, widgets in help_.marked.items():
                for widget in widgets:
                    if page.isAncestorOf(widget):
                        found.add((tab, widget.property(LABEL)))
            if tab not in COVERED_TABS:
                continue
            for form in page.findChildren(QFormLayout):
                for row in range(form.rowCount()):
                    item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                    label = item.widget() if item is not None else None
                    if isinstance(label, QLabel) and label.property("settingHelpKey") is None:
                        name = _plain(label.text())
                        if name and (tab, name) not in NO_CARD:
                            uncovered.add((tab, name))
    # A card on two tabs need only find each label on one of them.
    missing = sorted({(k, label) for k, c in cards.items() for label in c.labels
                      if not any((t, card_text(label)) in found for t in card_tabs(c))})
    checks.append(("every label a card names is on its tab, and marked", not missing,
                   str(missing)))
    checks.append(("every setting on the settings tabs has a card", not uncovered,
                   str(sorted(uncovered))))

    window._apply_mode("meanap")
    _wait(app, 50)
    titles = [e.title for e in index_tabs(window._tabs)]
    checks.append(("searching settings is not thrown by the mark",
                   not any(MARK in t for t in titles) and "Wavelet methods" in titles, ""))
    label = next(w for w in help_.marked.get("wavelets", []) if isinstance(w, QLabel))
    checks.append(("a marked label keeps its own text", label.text() == "Wavelet methods",
                   label.text()))
    link = label.findChild(QLabel, MARK_NAME)

    # The classic tabs.
    window._set_simple_view(False, remember=False)
    tabs = window._tabs
    tabs.setCurrentIndex(next(i for i in range(tabs.count())
                              if "Spike detection" in tabs.tabText(i)))
    _wait(app, 50)
    shown = link is not None and link.isVisible() \
        and link.geometry().right() <= label.width() \
        and link.x() >= label.fontMetrics().horizontalAdvance("Wavelet methods")
    checks.append(("its ⓘ sits just after the text, inside the label", shown,
                   "" if link is None else f"{link.geometry()} in {label.width()}"))
    link.linkActivated.emit("setting:wavelets")
    _wait(app, 80)
    card = help_.card
    checks.append(("clicking ⓘ opens the setting's card",
                   card.isVisible() and card.current == "wavelets", str(card.current)))
    checks.append(("below the tab strip, over the page",
                   card.geometry().top() >= tabs.tabBar().height()
                   and window._views.rect().contains(card.geometry()), str(card.geometry())))
    text = card.text.toPlainText()
    checks.append(("saying what it does, how to choose, and the params file names",
                   "What it does" in text and "Choosing a value" in text
                   and "wname_list" in text, ""))
    link.linkActivated.emit("setting:wavelets")
    _wait(app, 30)
    checks.append(("a second click closes it", not card.isVisible(), ""))
    link.linkActivated.emit("setting:wavelets")
    tabs.setCurrentIndex(0)
    _wait(app, 30)
    checks.append(("changing tab closes it", not card.isVisible(), ""))
    group = next((w for w in help_.marked.get("wavelets", []) if not isinstance(w, QLabel)),
                 None)
    group_link = group.findChild(QLabel, MARK_NAME) if group is not None else None
    checks.append(("a group title with a card is marked too, its title untouched",
                   group_link is not None and group.title() == "Wavelet"
                   and group_link.x() > 0, ""))
    section = next((w for k, ws in help_.marked.items() for w in ws
                    if w.property("settingHelpLabel") == "Bandpass filter"), None)
    checks.append(("so is a folding section's header",
                   section is not None and section.findChild(QLabel, MARK_NAME) is not None,
                   ""))

    # The simple view: the same widgets, borrowed into its drawer.
    window._set_simple_view(True, remember=False)
    simple = window._simple_view
    opened = False
    for area in simple.settings_card.areas():
        for index, section in enumerate(area.sections):
            if "Wavelet" in section.title:
                simple.open_section(area.key, index)
                opened = True
                break
        if opened:
            break
    _wait(app, 400)
    checks.append(("in the simple view the drawer shows the same mark",
                   opened and label.isVisible() and link.isVisible(), ""))
    link.linkActivated.emit("setting:wavelets")
    _wait(app, 80)
    panel = simple.drawer.panel
    left = simple.drawer.mapTo(window._views, panel.geometry().topLeft()).x()
    checks.append(("and the card opens beside the drawer, not under it",
                   card.isVisible() and card.geometry().right() <= left,
                   f"{card.geometry()} drawer from {left}"))
    simple.close_section()
    _wait(app, 30)
    checks.append(("closing the drawer closes the card", not card.isVisible(), ""))
    window.close()
    return checks


def main() -> int:
    app = QApplication.instance() or QApplication([])
    total = passed = 0
    for title, checks in (("A. The cards", _card_checks()),
                          ("B. On the settings tabs", _window_checks(app))):
        p, n = _report(title, checks)
        passed += p
        total += n
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
