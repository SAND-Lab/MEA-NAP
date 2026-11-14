"""The "What's new" window shown once after an update (meanap.gui.whats_new).

Run: ``uv run python test_whats_new.py`` (from ``python/``; a few seconds).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


NOTE = """---
version: {v}
title: Change {v}
link: https://example.org/{v}
---
Body of {v}.
"""


def logic_checks() -> None:
    from meanap.gui.whats_new import due, notices, parse, version_key

    print("Which notices are due")
    check("versions read with or without v, dev builds as their release",
          version_key("v1.36.0-dev.4") == (1, 36, 0) and version_key("1.40.0") == (1, 40, 0)
          and version_key(None) == () and version_key("main") == ())
    n = parse(NOTE.format(v="1.38.0"))
    check("a notice is parsed: version, title, link, body",
          n is not None and n.version == "1.38.0" and n.title == "Change 1.38.0"
          and n.link == "https://example.org/1.38.0" and n.body == "Body of 1.38.0.")
    check("a file without a header is not a notice", parse("# Just a README\n") is None)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for v in ("1.38.0", "1.40.0", "1.42.0"):
            (folder / f"{v}.md").write_text(NOTE.format(v=v))
        (folder / "README.md").write_text("# Notices\n")
        found = notices(folder)
        check("every notice in the folder, oldest first, README skipped",
              [x.version for x in found] == ["1.38.0", "1.40.0", "1.42.0"])
        check("an update shows what it crossed, and no further",
              [x.version for x in due("1.37.0", "1.40.0", found)] == ["1.38.0", "1.40.0"])
        check("the notice of the version you updated *to* is included, not the one you were on",
              [x.version for x in due("1.38.0", "1.42.0", found)] == ["1.40.0", "1.42.0"])
        check("a first install sees nothing", due(None, "1.42.0", found) == [])
        check("nor does staying put or going back",
              due("1.42.0", "1.42.0", found) == [] and due("1.42.0", "1.38.0", found) == [])
        check("a development build after a release counts as that release",
              [x.version for x in due("1.39.0", "v1.40.0-dev.3", found)] == ["1.40.0"])


def gui_checks() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    from meanap.gui.whats_new import SETTINGS_KEY, notices, parse, show_if_due

    print("The window")
    app = QApplication.instance() or QApplication([])
    items = [parse(NOTE.format(v=v)) for v in ("1.38.0", "1.40.0")]
    with tempfile.TemporaryDirectory() as tmp:
        settings = QSettings(str(Path(tmp) / "s.ini"), QSettings.Format.IniFormat)
        first = show_if_due(running="1.40.0", settings=settings, available=items)
        check("first start: nothing shown, the version remembered",
              first is None and settings.value(SETTINGS_KEY) == "1.40.0")
        settings.setValue(SETTINGS_KEY, "1.37.0")
        dlg = show_if_due(running="1.40.0", settings=settings, available=items)
        text = dlg.text.toPlainText() if dlg else ""
        check("after an update: both notices, newest first, with their links",
              dlg is not None and text.index("Change 1.40.0") < text.index("Change 1.38.0")
              and "Read the full explanation" in text)
        check("and the update is remembered, so it shows only once",
              settings.value(SETTINGS_KEY) == "1.40.0"
              and show_if_due(running="1.40.0", settings=settings, available=items) is None)
        settings.setValue(SETTINGS_KEY, "1.40.0")
        show_if_due(running="1.38.0", settings=settings, available=items)
        check("running an older version does not forget the newer one",
              settings.value(SETTINGS_KEY) == "1.40.0")
        if dlg:
            dlg.close()
    shipped = [p for p in (Path(__file__).resolve().parents[1]
                           / "src/meanap/gui/assets/notices").glob("*.md") if p.name != "README.md"]
    check("every notice shipped with MEA-NAP parses",
          all(parse(p.read_text()) is not None for p in shipped),
          ", ".join(p.name for p in shipped if parse(p.read_text()) is None))
    check("and is found by the loader", len(notices()) == len(shipped))
    del app


def main() -> int:
    logic_checks()
    gui_checks()
    print(f"\nFAILURES: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
