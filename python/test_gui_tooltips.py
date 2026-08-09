"""Test GUI behaviour that is easy to break and hard to notice: tooltip
wrapping, and the express-mode toggle.

Run from the repo root::

    uv run python python/test_gui_tooltips.py

Qt lays a plain-text tooltip out on one line however long it is. Before this,
the widest in the app rendered at **1468 px** — most of a laptop screen, one
line tall, usually covering the control it was describing.

The checks measure what Qt would actually draw, via ``QTextDocument``, rather
than counting characters: a character count passes on the developer's font and
fails on someone else's. Runs headless (``QT_QPA_PLATFORM=offscreen``), so no
display is needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtGui import QAction, QFontMetrics, QTextDocument  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from meanap.gui.tooltip import (  # noqa: E402
    MAX_TOOLTIP_PX, TOOLTIP_QSS, format_tooltip, install_tooltip_style,
    set_tooltip, wrap_to_width, wrap_tooltips,
)

Check = tuple[str, bool, str]

#: Allow a little slack over the target: a wrapped line is at most the limit
#: plus whatever the final word overhangs by, and rich text adds padding.
LIMIT_PX = MAX_TOOLTIP_PX + 40


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


def _drawn_width(text: str, font) -> int:
    """How wide Qt will actually render this tooltip."""
    doc = QTextDocument()
    doc.setDefaultFont(font)
    if text.strip().startswith("<"):
        doc.setHtml(text)
    else:
        doc.setPlainText(text)
    doc.setTextWidth(-1)
    return int(doc.idealWidth())


def _wrapping_checks(app: QApplication) -> list[Check]:
    checks: list[Check] = []
    metrics = QFontMetrics(app.font())

    long_text = (
        "Folder holding your recordings — or paste a Dropbox folder share link "
        "to analyse them without downloading the whole dataset, which is useful "
        "when the batch is larger than the disk you have available.")
    lines = wrap_to_width(long_text, metrics, MAX_TOOLTIP_PX)
    checks.append(("long text is split into several lines", len(lines) > 2,
                   f"{len(lines)}"))
    checks.append(("every line fits the target width",
                   all(metrics.horizontalAdvance(ln) <= MAX_TOOLTIP_PX for ln in lines),
                   f"{max(metrics.horizontalAdvance(ln) for ln in lines)} px"))
    checks.append(("no words are lost or duplicated",
                   " ".join(lines).split() == long_text.split(), ""))

    # Deliberate line breaks must survive.
    shaped = wrap_to_width("first line\nsecond line", metrics, MAX_TOOLTIP_PX)
    checks.append(("existing newlines are kept as breaks",
                   shaped == ["first line", "second line"], f"{shaped}"))

    # A single over-long word is left intact rather than broken mid-word.
    huge = "supercalifragilistic_expialidocious_identifier_that_is_very_long"
    checks.append(("an unbreakable word is not split",
                   wrap_to_width(huge, metrics, 50) == [huge], ""))
    return checks


def _format_checks(app: QApplication) -> list[Check]:
    checks: list[Check] = []

    short = "Step to stop at, inclusive (1–4)"
    checks.append(("short text is left alone",
                   format_tooltip(short) == short, ""))

    rich = "<b>already</b> markup"
    checks.append(("existing rich text is not re-wrapped",
                   format_tooltip(rich) == rich, ""))
    checks.append(("empty text is left alone", format_tooltip("") == "", ""))

    long_text = "word " * 80
    out = format_tooltip(long_text)
    checks.append(("long text becomes rich text with breaks",
                   out.startswith("<div>") and "<br>" in out, out[:40]))
    checks.append(("…and renders within the limit",
                   _drawn_width(out, app.font()) <= LIMIT_PX,
                   f"{_drawn_width(out, app.font())} px"))

    # Text with markup characters must be escaped, not interpreted.
    tricky = format_tooltip("compare a < b and " + "pad " * 60)
    checks.append(("angle brackets in text are escaped",
                   "&lt;" in tricky, tricky[:60]))

    # Formatting is idempotent — wrap_tooltips runs once, but a second call
    # (a re-shown window, say) must not nest markup.
    checks.append(("formatting twice changes nothing",
                   format_tooltip(out) == out, ""))
    return checks


def _window_checks(app: QApplication) -> list[Check]:
    from meanap.gui.main_window import MainWindow

    checks: list[Check] = []
    window = MainWindow()

    targets = [window, *window.findChildren(QWidget), *window.findChildren(QAction)]
    tips = [(t, t.toolTip()) for t in targets if t.toolTip()]
    checks.append(("the window has tooltips to check", len(tips) > 10, f"{len(tips)}"))

    widest, worst = 0, ""
    for target, text in tips:
        font = target.font() if hasattr(target, "font") else app.font()
        px = _drawn_width(text, font)
        if px > widest:
            widest, worst = px, text
    checks.append((f"no tooltip is wider than {LIMIT_PX} px (worst {widest} px)",
                   widest <= LIMIT_PX, worst[:70]))

    multiline = [t for _, t in tips if "<br>" in t]
    checks.append(("the long ones actually wrapped", len(multiline) >= 3,
                   f"{len(multiline)}"))

    # Toolbar tooltips live on QAction, not QWidget — the case originally missed.
    actions = [a for a in window.findChildren(QAction) if a.toolTip()]
    checks.append(("action tooltips are covered too", len(actions) > 0,
                   f"{len(actions)}"))
    action_widths = [_drawn_width(a.toolTip(), app.font()) for a in actions]
    checks.append(("…and are within the limit",
                   all(px <= LIMIT_PX for px in action_widths),
                   f"{max(action_widths) if action_widths else 0} px"))

    checks.append(("tooltip styling is installed",
                   "QToolTip" in (app.styleSheet() or ""), ""))
    checks.append(("…matching the tutorial bubble's panel colour",
                   "#2d323b" in TOOLTIP_QSS, ""))

    # Running the pass again must be a no-op, not a second wrap.
    again = wrap_tooltips(window)
    checks.append(("a second wrapping pass changes nothing", again == 0, f"{again}"))

    # And the styling install must not clobber an existing theme.
    before = app.styleSheet()
    install_tooltip_style(app)
    checks.append(("re-installing the style is idempotent",
                   app.styleSheet() == before, ""))
    return checks


def _express_toggle_checks(app: QApplication) -> list[Check]:
    """The express-mode checkbox must reach an actual run, not just Params.

    A control that sets a field nobody reads is worse than no control: the user
    ticks it, the run behaves as before, and nothing says why.
    """
    from meanap.gui.main_window import MainWindow
    from meanap.params import Params

    checks: list[Check] = []
    window = MainWindow()
    pipe = window._pipeline_panel

    checks.append(("the Run tab has an express-mode toggle",
                   hasattr(pipe, "express_mode"), ""))
    checks.append(("it is off by default, matching Params",
                   pipe.express_mode.isChecked() is False
                   and Params().express_mode is False, ""))

    pipe.load(Params(express_mode=True))
    checks.append(("loading a run with express on ticks it",
                   pipe.express_mode.isChecked(), ""))
    pipe.load(Params(express_mode=False))
    checks.append(("…and off unticks it",
                   not pipe.express_mode.isChecked(), ""))

    pipe.express_mode.setChecked(True)
    saved = Params()
    pipe.save(saved)
    checks.append(("ticking it sets Params.express_mode", saved.express_mode, ""))
    pipe.express_mode.setChecked(False)
    saved2 = Params(express_mode=True)
    pipe.save(saved2)
    checks.append(("unticking it clears Params.express_mode",
                   not saved2.express_mode, ""))

    # _collect_params is what the Run button actually builds a run from, so
    # that is the path worth asserting on — not just the panel's own save().
    window._pipeline_panel.express_mode.setChecked(True)
    collected = window._collect_params()
    checks.append(("the params a run is built from carry it",
                   collected.express_mode, ""))
    window._pipeline_panel.express_mode.setChecked(False)
    checks.append(("…and reflect it being turned off",
                   not window._collect_params().express_mode, ""))

    checks.append(("the toggle explains what it does",
                   len(pipe.express_mode.toolTip()) > 80, ""))
    checks.append(("…and that tooltip is wrapped like the rest",
                   pipe.express_mode.toolTip().startswith("<div>"),
                   pipe.express_mode.toolTip()[:30]))
    return checks


def _bundle_notice_checks(app: QApplication) -> list[Check]:
    """The express bundle must be findable after the run that wrote it.

    It lands *beside* the output folder, not inside it, and the runner logs it
    before the timing lines — so without a closing notice the one file the run
    exists to produce scrolls out of sight in the place nobody looks.
    """
    import tempfile

    from meanap.gui.main_window import MainWindow
    from meanap.params import Params
    from meanap.pipeline.bundle import BUNDLE_SUFFIX

    checks: list[Check] = []
    window = MainWindow()

    with tempfile.TemporaryDirectory() as tmp:
        out_root = Path(tmp) / "OutputData01Jan2026"
        out_root.mkdir()
        bundle = out_root.with_suffix(BUNDLE_SUFFIX)
        bundle.write_bytes(b"x" * 2_200_000)

        window._params = Params(express_mode=True)
        window._run_panel.log.clear()
        window._on_pipeline_finished(out_root)
        text = window._run_panel.log.toPlainText()
        checks.append(("an express run names the bundle at the end",
                       str(bundle) in text, text[-120:]))
        checks.append(("…says it sits beside the output folder",
                       "beside the output folder" in text, ""))
        checks.append(("…gives the command that opens it",
                       "meanap-viewer" in text, ""))
        checks.append(("…after the 'Done.' line, so it reads last",
                       text.index(str(bundle)) > text.index("Done."), ""))
        checks.append(("the run remembers the bundle for later",
                       window._last_bundle == bundle, str(window._last_bundle)))

        # A non-express run must stay quiet even when a bundle from an earlier
        # express run of the same day is still sitting next to the folder.
        window._params = Params(express_mode=False)
        window._run_panel.log.clear()
        window._on_pipeline_finished(out_root)
        checks.append(("a full run says nothing about bundles",
                       "meanap-viewer" not in window._run_panel.log.toPlainText(), ""))

        # Express on, but packing failed (the runner only warns) — no notice.
        bundle.unlink()
        window._params = Params(express_mode=True)
        window._run_panel.log.clear()
        window._on_pipeline_finished(out_root)
        checks.append(("no notice when no bundle was written",
                       "meanap-viewer" not in window._run_panel.log.toPlainText(), ""))

    return checks


def _helper_checks(app: QApplication) -> list[Check]:
    checks: list[Check] = []
    w = QWidget()
    set_tooltip(w, "short")
    checks.append(("set_tooltip leaves short text plain", w.toolTip() == "short", ""))
    set_tooltip(w, "word " * 80)
    checks.append(("set_tooltip wraps long text", "<br>" in w.toolTip(), ""))
    checks.append(("…within the limit",
                   _drawn_width(w.toolTip(), w.font()) <= LIMIT_PX,
                   f"{_drawn_width(w.toolTip(), w.font())} px"))
    return checks


def main() -> int:
    app = QApplication.instance() or QApplication([])
    print("=" * 70)
    print("GUI: tooltips and the express-mode toggle")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — wrapping by measured width:", _wrapping_checks),
        ("B — formatting rules:", _format_checks),
        ("C — the real window:", _window_checks),
        ("D — the express-mode toggle:", _express_toggle_checks),
        ("E — the end-of-run bundle notice:", _bundle_notice_checks),
        ("F — the set_tooltip helper:", _helper_checks),
    ]:
        p, n = _report(title, build(app))
        total_pass += p
        total += n
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
