"""Choosing which MEA-NAP to run, and keeping the cutting edge current.

Opened from the version number beside the Mode selector. Two jobs:

**Stay current.** Someone following ``main`` gets new work as it lands, but only
if they pull it — and most MEA-NAP users do not live in a terminal. The window
checks GitHub when it opens (see :meth:`MainWindow.start_update_check`), marks
the version number when there is something new, and here offers to fetch it
and restart into it.

**Run a specific release.** For reproducing a published analysis. Each release
opens in its own folder alongside the clone (see :mod:`meanap.updates` for why
not in place), in this GUI if the release has it and in MATLAB if it predates
it.

All git work runs off the UI thread: a fetch can take seconds on a slow
connection, and a first checkout of a release a few more.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from meanap import updates
from meanap.version import meanap_version

__all__ = ["VersionsDialog", "Background", "check_on_start", "set_check_on_start",
           "default_version", "set_default_version"]

_SETTINGS_KEY = "updates/check_on_start"

_DEFAULT_KEY = "versions/default"

#: How many development builds the list shows. There is one per merge, so the
#: whole history would bury the official releases; the newest few cover
#: "the build from before that last change", which is what people reach for.
#: The running and default builds are always listed, however old.
DEV_BUILDS_SHOWN = 5

#: The list item that means "the clone, on main" rather than a release tag.
#: The same string is what is stored as the default.
CUTTING_EDGE = updates.MAIN


def check_on_start() -> bool:
    return QSettings("SAND Lab", "MEA-NAP").value(_SETTINGS_KEY, True, type=bool)


def set_check_on_start(on: bool) -> None:
    QSettings("SAND Lab", "MEA-NAP").setValue(_SETTINGS_KEY, bool(on))


def default_version() -> str | None:
    """The version ``meanap-gui`` opens: ``"main"``, a release tag, or ``None``.

    ``None`` — never chosen — means no switching: whichever copy is started is
    the one that opens, which is how MEA-NAP behaved before there was a choice.
    """
    value = QSettings("SAND Lab", "MEA-NAP").value(_DEFAULT_KEY, "", type=str)
    return value or None


def set_default_version(choice: str | None) -> None:
    QSettings("SAND Lab", "MEA-NAP").setValue(_DEFAULT_KEY, choice or "")


class Background(QObject):
    """Run *fn* on a daemon thread and deliver its result on the UI thread.

    A plain Python thread rather than a QThread: a QThread destroyed while it
    runs takes the whole application down, and a version check still waiting
    on the network when the user closes the window is the ordinary case, not
    an edge one. A daemon thread simply dies with the process.
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable[[], object], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def wait(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:   # noqa: BLE001 - shown to the user as text
            try:
                self.failed.emit(str(exc))
            except RuntimeError:   # the dialog went away first
                pass
            return
        try:
            self.done.emit(result)
        except RuntimeError:
            pass


def status_summary(status: updates.Status | None) -> str:
    """One line about the running copy's freshness, for the dialog and tooltip."""
    if status is None:
        return "Checking GitHub for updates…"
    co = status.checkout
    if co is None:
        return status.error or "Not a git clone."
    if co.is_main:
        if status.behind:
            n = status.behind
            return (f"{n} new commit{'s' if n != 1 else ''} on GitHub since this "
                    "copy was last updated.")
        if status.behind == 0:
            return ("Up to date with GitHub." if not status.error else
                    f"Up to date as of the last check. {status.error}")
    elif co.is_release:
        newer = status.newer_version
        if newer:
            kind = "development build" if updates.is_dev_tag(newer) else "release"
            return f"A newer {kind}, {newer}, is available — choose it below."
        if co.is_dev:
            return "This is the latest development build."
        if status.latest_release:
            return "This is the latest official release."
    else:
        return (f"This copy is on {co.describe()}, which is not tracked "
                "for updates.")
    return status.error or ""


class VersionsDialog(QDialog):
    """Which MEA-NAP is running, what else could, and whether it is current."""

    #: Emitted with a fresh status whenever the dialog re-checks, so the
    #: toolbar badge follows what the dialog shows.
    status_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None, *,
                 checkout: updates.Checkout | None = None,
                 is_busy: Callable[[], bool] = lambda: False,
                 restart_args: Callable[[], tuple[str, ...]] = tuple,
                 on_restart: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MEA-NAP versions")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(560, 520)
        self._checkout = checkout if checkout is not None else updates.find_checkout()
        self._is_busy = is_busy
        self._restart_args = restart_args
        self._on_restart = on_restart
        self._status: updates.Status | None = None
        self._releases: dict[str, updates.Release] = {}
        self._jobs: list[Background] = []

        layout = QVBoxLayout(self)

        # ── What is running ──
        running = QGroupBox("Running now")
        rl = QVBoxLayout(running)
        self._running_label = QLabel()
        self._running_label.setWordWrap(True)
        self._running_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(self._running_label)
        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        rl.addWidget(self._status_label)
        row = QHBoxLayout()
        self._check_button = QPushButton("Check again")
        self._check_button.clicked.connect(self.refresh)
        self._update_button = QPushButton("Download update")
        self._update_button.setToolTip(
            "Fast-forward this clone's 'main' to GitHub's. Refuses, and changes "
            "nothing, if you have local edits the update would overwrite.")
        self._update_button.clicked.connect(self._on_update)
        # The dialog is usually opened *because* of the update badge, so that
        # is the button Enter should press — not the first one Qt comes to.
        self._check_button.setAutoDefault(False)
        self._update_button.setDefault(True)
        self._restart_button = QPushButton("Restart MEA-NAP")
        self._restart_button.setToolTip(
            "Close this window and open a new one running the updated code.")
        self._restart_button.clicked.connect(self._on_restart_clicked)
        row.addWidget(self._check_button)
        row.addWidget(self._update_button)
        row.addWidget(self._restart_button)
        row.addStretch(1)
        rl.addLayout(row)
        self._update_message = QLabel()
        self._update_message.setWordWrap(True)
        self._update_message.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(self._update_message)
        layout.addWidget(running)

        # ── Choose one ──
        choose = QGroupBox("Choose a version to run")
        cl = QVBoxLayout(choose)
        hint = QLabel(
            "Cutting edge has the newest features and fixes, and changes as "
            "they land. An official release is tested and written up; a "
            "development build is main as it was after one change, named so "
            "you can come back to it. Either stays exactly as published — use "
            "one to reproduce an analysis. Each opens from its own folder in "
            f"{updates.versions_dir()}; your MEA-NAP folder is not touched.")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection)
        self._list.itemDoubleClicked.connect(lambda _item: self._on_open())
        cl.addWidget(self._list, 1)
        self._choice_label = QLabel()
        self._choice_label.setWordWrap(True)
        cl.addWidget(self._choice_label)
        orow = QHBoxLayout()
        self._open_button = QPushButton("Open selected version")
        self._open_button.clicked.connect(self._on_open)
        self._default_button = QPushButton("Set as default")
        self._default_button.setToolTip(
            "Open this version whenever MEA-NAP starts. Start with "
            "'meanap-gui --here' to open a different copy just once.")
        self._default_button.clicked.connect(self._on_set_default)
        self._folder_button = QPushButton("Show folder")
        self._folder_button.clicked.connect(self._on_show_folder)
        orow.addWidget(self._open_button)
        orow.addWidget(self._default_button)
        orow.addWidget(self._folder_button)
        orow.addStretch(1)
        cl.addLayout(orow)
        self._default_label = QLabel()
        self._default_label.setWordWrap(True)
        self._default_label.setStyleSheet("color: palette(mid);")
        cl.addWidget(self._default_label)
        layout.addWidget(choose, 1)

        self._auto_check = QCheckBox("Check for updates when MEA-NAP starts")
        self._auto_check.setChecked(check_on_start())
        self._auto_check.toggled.connect(set_check_on_start)
        layout.addWidget(self._auto_check)

        self._restart_button.hide()
        self._render()

    # ── State → widgets ──────────────────────────────────────────────────────

    def set_status(self, status: updates.Status | None) -> None:
        """Show *status* — from the startup check, or one of our own."""
        self._status = status
        if status is not None and status.checkout is not None:
            self._checkout = status.checkout
        self._render()

    def _render(self) -> None:
        co = self._checkout
        if co is None:
            self._running_label.setText(
                f"MEA-NAP {meanap_version()}, not from a git clone.")
        else:
            kind = ("cutting edge (main)" if co.is_main else
                    f"development build {co.tag}" if co.is_dev else
                    f"release {co.tag}" if co.is_release else co.describe())
            self._running_label.setText(
                f"<b>MEA-NAP {meanap_version()}</b> — {kind}, commit "
                f"<code>{co.commit[:7]}</code><br>"
                f"<span style='color: palette(mid)'>{co.root}</span>")
        self._status_label.setText(status_summary(self._status))
        can_update = bool(co and co.is_main and self._status
                          and self._status.behind)
        self._update_button.setVisible(can_update)
        self._check_button.setEnabled(co is not None)
        self._fill_list()

    def _fill_list(self) -> None:
        keep = self._selected()
        self._list.blockSignals(True)
        self._list.clear()
        co = self._checkout
        edge = QListWidgetItem("Cutting edge (main) — latest development code")
        edge.setData(Qt.ItemDataRole.UserRole, CUTTING_EDGE)
        if co is not None and co.is_main:
            edge.setText(edge.text() + "   ● running")
        default = default_version()
        if default == CUTTING_EDGE:
            edge.setText(edge.text() + "   ★ default")
        self._list.addItem(edge)
        self._releases = {r.tag: r for r in (
            self._status.releases if self._status else
            updates.releases(co.clone) if co is not None else [])}
        official = [r for r in self._releases.values() if not r.dev]
        dev = [r for r in self._releases.values() if r.dev]
        keep_dev = {co.tag if co is not None else None, default}
        dev = [r for i, r in enumerate(dev)
               if i < DEV_BUILDS_SHOWN or r.tag in keep_dev]
        # Newest first throughout: the development builds sit between cutting
        # edge and the last release, in time as in the list — and above the
        # long tail of old releases rather than scrolled away beneath it.
        if dev:
            self._add_header("Development builds — one per change to main, "
                             "without release notes")
        for rel in dev:
            self._add_version(rel, "built", co, default)
        if official:
            self._add_header("Official releases")
        for rel in official:
            self._add_version(rel, "released", co, default)
        self._list.blockSignals(False)
        for i in range(self._list.count()):
            if keep is not None and self._list.item(i).data(Qt.ItemDataRole.UserRole) == keep:
                self._list.setCurrentRow(i)
                break
        else:
            self._list.setCurrentRow(0)
        self._on_selection()

    def _add_header(self, text: str) -> None:
        """A section title in the list: not selectable, so never "opened"."""
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self._list.addItem(item)

    def _add_version(self, rel: updates.Release, verb: str,
                     co: updates.Checkout | None, default: str | None) -> None:
        text = f"{rel.tag}   {verb} {rel.date}"
        if not rel.python_gui:
            text += "   (MATLAB)"
        if co is not None and co.is_release and co.tag == rel.tag:
            text += "   ● running"
        if default == rel.tag:
            text += "   ★ default"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, rel.tag)
        self._list.addItem(item)

    def _selected(self) -> str | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _is_running(self, choice: str | None) -> bool:
        co = self._checkout
        if co is None or choice is None:
            return False
        return co.is_main if choice == CUTTING_EDGE else (co.is_release and co.tag == choice)

    def _can_be_default(self, choice: str | None) -> bool:
        """Only a version that opens in this GUI; see :func:`updates.default_folder`."""
        if choice is None or self._checkout is None:
            return False
        if choice == CUTTING_EDGE:
            return True
        rel = self._releases.get(choice)
        return rel is not None and rel.python_gui

    def _on_selection(self, *_args) -> None:
        choice = self._selected()
        co = self._checkout
        default = default_version()
        self._default_button.setEnabled(
            self._can_be_default(choice) and choice != default)
        if choice is not None and co is not None and not self._can_be_default(choice):
            self._default_button.setToolTip(
                "Releases that run in MATLAB cannot be the default: MEA-NAP "
                "would open MATLAB instead of this window every time it starts.")
        else:
            self._default_button.setToolTip(
                "Open this version whenever MEA-NAP starts. Start with "
                "'meanap-gui --here' to open a different copy just once.")
        if default is None:
            self._default_label.setText(
                "No default is set, so MEA-NAP opens whichever copy you start. "
                "Opening a version from this list makes it the default, unless "
                "it runs in MATLAB.")
        else:
            name = "cutting edge (main)" if default == CUTTING_EDGE else default
            self._default_label.setText(
                f"MEA-NAP opens {name} when it starts (★). Opening another "
                "version from this list makes that the default instead, "
                "unless it runs in MATLAB; 'meanap-gui --here' skips it once.")
        self._open_button.setEnabled(
            co is not None and choice is not None and not self._is_running(choice))
        self._folder_button.setEnabled(co is not None and choice is not None)
        if choice is None or co is None:
            self._choice_label.setText("")
        elif self._is_running(choice):
            self._choice_label.setText("This is the version running now.")
        elif choice == CUTTING_EDGE:
            self._choice_label.setText(
                f"Opens MEA-NAP from {co.clone} in a new window.")
        else:
            where = updates.release_dir(choice)
            first = "" if where.exists() else " (set up on first use, from the history already in your clone)"
            rel = self._releases.get(choice)
            engine = ("in MATLAB" if rel is not None and not rel.python_gui
                      else "in a new window")
            self._choice_label.setText(f"Opens {choice} {engine}, from {where}{first}.")

    # ── Actions ──────────────────────────────────────────────────────────────

    def _run(self, fn, on_done, on_failed=None) -> Background:
        job = Background(fn, self)
        job.done.connect(on_done)
        job.failed.connect(on_failed or self._show_error)
        job.done.connect(lambda _r, j=job: self._forget(j))
        job.failed.connect(lambda _m, j=job: self._forget(j))
        self._jobs.append(job)
        job.start()
        return job

    def _forget(self, job: Background) -> None:
        if job in self._jobs:
            self._jobs.remove(job)

    def _show_error(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.warning(self, "MEA-NAP versions", message)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        for b in (self._check_button, self._update_button, self._open_button):
            b.setEnabled(not busy)
        if message:
            self._status_label.setText(message)
        if not busy:
            self._render()

    def refresh(self) -> None:
        """Fetch from GitHub again and redraw."""
        if self._checkout is None:
            return
        self._set_busy(True, "Checking GitHub for updates…")
        co = self._checkout
        remote = self._status.remote if self._status else None
        self._run(lambda: updates.check(co, remote=remote), self._on_checked)

    def _on_checked(self, status: updates.Status) -> None:
        self.set_status(status)
        self._set_busy(False)
        self.status_changed.emit(status)

    def _on_update(self) -> None:
        co = self._checkout
        remote = (self._status.remote if self._status else None) or "origin"
        self._set_busy(True, "Downloading the update…")
        self._run(lambda: updates.update_main(co, remote), self._on_updated)

    def _on_updated(self, result: updates.UpdateResult) -> None:
        text = result.message
        if result.ok and result.dependencies_changed:
            text += ("\n\nThis update changes MEA-NAP's Python dependencies ("
                     + ", ".join(result.dependencies_changed)
                     + "). Before restarting, run 'uv sync' (or 'pip install -e .') "
                       "in the MEA-NAP folder, or the new version may fail to start.")
        elif result.ok and result.old != result.new:
            text += " Restart MEA-NAP to use it."
        self._update_message.setText(text)
        self._restart_button.setVisible(result.ok and result.old != result.new)
        if result.ok and self._status is not None:
            self._status.behind = 0
            self._status.ahead = 0
            self._checkout = updates.find_checkout(self._checkout.root) or self._checkout
            self._status.checkout = self._checkout
            self.status_changed.emit(self._status)
        self._set_busy(False)

    def _confirm_leaving(self, what: str) -> bool:
        if self._is_busy():
            QMessageBox.information(
                self, "MEA-NAP versions",
                f"A run is in progress. Let it finish or stop it before you {what}.")
            return False
        return True

    def _on_restart_clicked(self) -> None:
        if not self._confirm_leaving("restart"):
            return
        answer = QMessageBox.question(
            self, "Restart MEA-NAP",
            "Close this window and reopen MEA-NAP with the updated code?\n\n"
            "Settings on screen that you have not saved will not carry over.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            updates.launch(updates.launch_plan(self._checkout.root),
                           self._restart_args())
        except Exception as exc:   # noqa: BLE001
            self._show_error(f"Could not restart MEA-NAP: {exc}")
            return
        self.close()
        if self._on_restart is not None:
            self._on_restart()

    def _on_open(self) -> None:
        choice = self._selected()
        co = self._checkout
        if co is None or choice is None or self._is_running(choice):
            return
        if choice == CUTTING_EDGE:
            self._launch_folder(co.clone, choice)
            return
        self._set_busy(True, f"Setting up {choice}…")
        self._run(lambda: updates.ensure_release(co.clone, choice),
                  lambda folder: self._on_release_ready(folder, choice))

    def _on_release_ready(self, folder: Path, choice: str) -> None:
        self._set_busy(False)
        self._launch_folder(folder, choice)

    def _on_set_default(self) -> None:
        choice = self._selected()
        if self._can_be_default(choice):
            set_default_version(choice)
            self._fill_list()

    def _launch_folder(self, folder: Path, choice: str) -> None:
        plan = updates.launch_plan(folder)
        if plan.kind == "manual":
            QMessageBox.information(self, "MEA-NAP versions", plan.explanation)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
            return
        try:
            updates.launch(plan, self._restart_args() if plan.kind == "python" else ())
        except Exception as exc:   # noqa: BLE001
            self._show_error(f"Could not open MEA-NAP from {folder}: {exc}")
            return
        # The last version opened is the one wanted next time — but only one
        # that opens here; a MATLAB release leaves the default as it was.
        if plan.kind == "python" and self._can_be_default(choice):
            set_default_version(choice)
            self._fill_list()
        self._update_message.setText(
            f"Opening MEA-NAP from {folder}. " + plan.explanation
            + " This window stays open; close it when you no longer need it.")

    def _on_show_folder(self) -> None:
        choice = self._selected()
        co = self._checkout
        if co is None or choice is None:
            return
        folder = co.clone if choice == CUTTING_EDGE else updates.release_dir(choice)
        if not folder.exists():
            QMessageBox.information(
                self, "MEA-NAP versions",
                f"{choice} has not been set up yet. Open it once and its "
                f"folder will be created at {folder}.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
