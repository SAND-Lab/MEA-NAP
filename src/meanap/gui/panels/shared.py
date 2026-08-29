"""The shared-run page of the Run tab: one batch, several computers.

Most people have more than one computer, and most of a run is per-recording
work. This page is the way to put the spare one to use without anything
being set up beyond a folder both can see.

There are two things a person can be here — the **main computer**, which
sets the run up and ends with the results, or a **helper**, which joins and
does a share — and each is a short wizard:

* *Set up a shared run…* asks for the shared folder and a name, times this
  computer, and asks where the pooled results should go. It ends with the
  run created and this page waiting for helpers to appear.
* *Join a shared run…* asks which run, checks the raw data can be found here,
  times this computer, and joins. From then on this computer waits for the
  main one to press Start, then works through its share.

In between, the table on this page is the whole state of the run: who has
joined, how fast each is, how many recordings each will do (editable, on the
main computer, until Start), and how far each has got. It is refreshed from
the shared folder every few seconds, which is the only channel there is.

The Run and Stop buttons are the Run tab's, shared with the other pages —
see :mod:`meanap.gui.panels.run` — so Start is the same button as Run.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QWizard, QWizardPage,
)

from meanap.gui.panels.paths import PathRow
from meanap.params import Params, is_remote_url
from meanap.pipeline.output_folders import next_free_output_name, output_name_taken
from meanap.shared.roles import MachineView, machine_views
from meanap.shared.workspace import (
    CANCELLED, DONE, FAILED, FINISHED, GATHERING, RUNNING, STOPPED, WAITING,
    WORKING, WORKSPACE_SUFFIX, MachineRecord, SharedRun, Workspace,
    create_workspace, default_machine_name, is_workspace, open_workspace,
    sanitize_name, split_by_score, split_recordings,
)
from meanap.version import meanap_version

__all__ = ["SharedRunPanel", "SetupWizard", "JoinWizard", "BenchmarkThread",
           "ROLE_MAIN", "ROLE_HELPER"]

ROLE_MAIN, ROLE_HELPER = "main", "helper"

#: How often the table is re-read from the shared folder.
REFRESH_MS = 3000

_STATUS_TEXT = {
    WAITING: "waiting", WORKING: "working", FINISHED: "done",
    FAILED: "failed", STOPPED: "stopped",
}


# ── Benchmarking off the UI thread ────────────────────────────────────────────

class BenchmarkThread(QThread):
    """Runs the timing benchmark; ~3–15 s depending on the machine."""

    done = pyqtSignal(object)      # BenchmarkResult
    failed = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def run(self) -> None:  # noqa: D401 - QThread entry point
        from meanap.shared.benchmark import run_benchmark

        try:
            self.done.emit(run_benchmark(log=self.log_message.emit))
        except Exception as e:                              # noqa: BLE001
            self.failed.emit(str(e))


# ── Wizard pages ──────────────────────────────────────────────────────────────

class _IntroPage(QWizardPage):
    def __init__(self, role: str) -> None:
        super().__init__()
        if role == ROLE_MAIN:
            self.setTitle("Share this analysis across your computers")
            text = (
                "<p>This computer will be the <b>main computer</b>: it sets the "
                "run up, does a share of the recordings, and ends up with the "
                "results — an ordinary MEA-NAP output folder, exactly as if it "
                "had done everything itself.</p>"
                "<p>You will need:</p><ul>"
                "<li>a <b>folder every computer can see</b> — a Dropbox, OneDrive "
                "or Google Drive folder, a network drive, or a shared disk;</li>"
                "<li>the <b>raw recordings reachable from each computer</b> — "
                "simplest is to keep them in that same folder, or to use a "
                "Dropbox link on the Data tab;</li>"
                "<li>the <b>same version of MEA-NAP</b> on each computer.</li></ul>"
                "<p>The analysis settings are the ones on the other tabs right now. "
                "Check them first — every computer will use them.</p>"
            )
        else:
            self.setTitle("Help another computer with its analysis")
            text = (
                "<p>This computer will be a <b>helper</b>: it joins a shared run "
                "another computer has set up, waits to be given a share of the "
                "recordings, analyses them, and leaves the results in the shared "
                "folder for the main computer to collect.</p>"
                "<p>You will need the shared run's folder — it ends in "
                f"<code>{WORKSPACE_SUFFIX}</code> and the main computer's Run tab "
                "shows where it is — and the raw recordings reachable from here.</p>"
                "<p>Nothing on the other tabs is used: the settings come from the "
                "main computer.</p>"
            )
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        layout = QVBoxLayout(self)
        layout.addWidget(label)


class _SharedFolderPage(QWizardPage):
    """Where the run lives, what it is called, and whether the data will be
    findable from the other computers."""

    def __init__(self, params: Params) -> None:
        super().__init__()
        self.params = params
        self.setTitle("The shared folder")
        self.setSubTitle("A folder every computer can see. The run's files — "
                         "settings, progress, each computer's results — go in "
                         "a sub-folder created here.")
        form = QFormLayout(self)
        self.folder = PathRow(self)
        self.folder.line_edit.textChanged.connect(self._revalidate)
        self.name = QLineEdit(_default_run_name(params))
        self.name.textChanged.connect(self._revalidate)
        form.addRow("Shared folder", self.folder)
        form.addRow("Run name", self.name)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        form.addRow(self.status)
        self.data_note = QLabel("")
        self.data_note.setWordWrap(True)
        form.addRow(self.data_note)
        self._ok = False

    def initializePage(self) -> None:  # noqa: N802 - Qt naming
        self._revalidate()

    def _revalidate(self, *_args) -> None:
        folder, name = self.folder.value.strip(), self.name.text().strip()
        problem = ""
        if not folder:
            problem = "Choose the shared folder."
        elif not Path(folder).is_dir():
            problem = "That folder does not exist."
        elif not name:
            problem = "Give the run a name."
        elif is_workspace(Path(folder) / f"{sanitize_name(name)}{WORKSPACE_SUFFIX}"):
            problem = (f"'{name}' already holds a shared run in that folder — "
                       "pick another name.")
        self._ok = not problem
        self.status.setText(problem if problem else
                            f"✓ Will create {sanitize_name(name)}{WORKSPACE_SUFFIX} in {folder}")
        self.data_note.setText(_describe_data_reach(self.params, folder) if folder else "")
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802 - Qt naming
        return self._ok


class _BenchmarkPage(QWizardPage):
    """Name this computer and time it, so the split can be proportional."""

    def __init__(self, role: str) -> None:
        super().__init__()
        self.role = role
        self.setTitle("This computer")
        self.setSubTitle("A short benchmark (a few seconds to a minute) measures how "
                         "fast this computer runs the pipeline, so the recordings "
                         "can be shared out in proportion.")
        form = QFormLayout(self)
        self.name = QLineEdit(default_machine_name())
        self.name.setToolTip("How this computer appears to the others. "
                             "Letters, digits, '-' and '_'.")
        form.addRow("Name", self.name)
        self.result_label = QLabel("Benchmark not run yet.")
        self.result_label.setWordWrap(True)
        form.addRow(self.result_label)
        row = QHBoxLayout()
        self.run_btn = QPushButton("Run benchmark")
        self.run_btn.clicked.connect(self.start_benchmark)
        self.skip = QCheckBox("Skip — split evenly with other un-benchmarked computers")
        self.skip.toggled.connect(lambda _v: self.completeChanged.emit())
        row.addWidget(self.run_btn)
        row.addWidget(self.skip)
        row.addStretch()
        form.addRow(row)
        self.result = None
        self._thread: BenchmarkThread | None = None
        self._auto_started = False

    def initializePage(self) -> None:  # noqa: N802 - Qt naming
        if not self._auto_started:
            self._auto_started = True
            self.start_benchmark()

    def start_benchmark(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self.run_btn.setEnabled(False)
        self.result_label.setText("Benchmarking… this computer will be busy for a moment.")
        self._thread = BenchmarkThread(self)
        self._thread.done.connect(self._on_done)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_done(self, result) -> None:
        self.result = result
        self.result_label.setText("\n".join(result.describe()))
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run again")
        self.completeChanged.emit()

    def _on_failed(self, message: str) -> None:
        self.result_label.setText(f"The benchmark failed: {message}\n"
                                  "You can skip it and share the work out evenly.")
        self.run_btn.setEnabled(True)
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802 - Qt naming
        return bool(self.name.text().strip()) and (self.result is not None or self.skip.isChecked())

    def machine_record(self) -> MachineRecord:
        record = MachineRecord.for_this_machine(self.name.text().strip(), self.role)
        if self.result is not None and not self.skip.isChecked():
            record.benchmark_seconds = self.result.seconds
            record.score = self.result.score
        return record

    def cleanupPage(self) -> None:  # noqa: N802 - Qt naming
        # Going back should not kill a benchmark in flight; it just finishes.
        pass


class _FinalOutputPage(QWizardPage):
    """Where the pooled results land on the main computer."""

    def __init__(self, params: Params) -> None:
        super().__init__()
        self.setTitle("Where the results go")
        self.setSubTitle("The main computer pools every share into one ordinary "
                         "output folder here. Each helper's part stays in the "
                         "shared folder too.")
        form = QFormLayout(self)
        self.folder = PathRow(self, initial=params.output_data_folder)
        self.folder.line_edit.textChanged.connect(self._revalidate)
        self.name = QLineEdit(params.output_data_folder_name or _default_run_name(params))
        self.name.textChanged.connect(self._revalidate)
        form.addRow("Output data folder", self.folder)
        form.addRow("Output folder name", self.name)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        form.addRow(self.status)
        self._ok = False

    def initializePage(self) -> None:  # noqa: N802 - Qt naming
        # A name already used would be *continued into* — pooled results must
        # not land on top of an unrelated run, so step aside up front.
        folder, name = self.folder.value.strip(), self.name.text().strip()
        if folder and name and output_name_taken(folder, name):
            self.name.setText(next_free_output_name(folder, name))
        self._revalidate()

    def _revalidate(self, *_args) -> None:
        folder, name = self.folder.value.strip(), self.name.text().strip()
        problem = ""
        if not folder:
            problem = "Choose the output data folder."
        elif not name:
            problem = "Give the output folder a name."
        elif output_name_taken(folder, name):
            problem = (f"'{name}' already holds a run — the pooled results would "
                       "be mixed into it. Use another name.")
        self._ok = not problem
        self.status.setText(problem or f"✓ Results will be in {Path(folder) / name}")
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802 - Qt naming
        return self._ok


class _PickWorkspacePage(QWizardPage):
    """Which shared run to join."""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Which shared run?")
        self.setSubTitle(f"Pick the folder ending in {WORKSPACE_SUFFIX} that the main "
                         "computer created — its Run tab shows the path.")
        form = QFormLayout(self)
        self.folder = PathRow(self)
        self.folder.line_edit.textChanged.connect(self._revalidate)
        form.addRow("Shared run folder", self.folder)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        form.addRow(self.status)
        self.workspace: Workspace | None = None
        self.run: SharedRun | None = None

    def _revalidate(self, *_args) -> None:
        self.workspace, self.run = None, None
        path = self.folder.value.strip()
        text = "Choose the shared run's folder."
        if path:
            try:
                ws = open_workspace(path)
                run = ws.read()
            except ValueError as e:
                text = str(e)
            else:
                self.workspace, self.run = ws, run
                lines = [f"✓ '{run.name}': {len(run.recordings)} recording(s), "
                         f"main computer '{run.main}'."]
                if run.status == CANCELLED:
                    lines.append("! This run was cancelled.")
                elif run.status == DONE:
                    lines.append("! This run has already finished.")
                elif run.started:
                    lines.append("! This run has already started — a computer joining "
                                 "now will not be given a share.")
                mine, theirs = meanap_version(), run.meanap_version
                if theirs and mine != theirs:
                    lines.append(f"! MEA-NAP {theirs} created this run; this computer has "
                                 f"{mine}. Results may differ — update so they match.")
                text = "\n".join(lines)
        self.status.setText(text)
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802 - Qt naming
        return self.run is not None and self.run.status not in (CANCELLED, DONE)


class _RawDataPage(QWizardPage):
    """Where this computer reads the recordings from."""

    def __init__(self, pick: _PickWorkspacePage) -> None:
        super().__init__()
        self.pick = pick
        self.setTitle("The raw recordings")
        self.setSubTitle("Where this computer reads the recordings from. Found "
                         "automatically when they are in the shared folder or "
                         "come from a link.")
        form = QFormLayout(self)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        form.addRow(self.status)
        self.folder = PathRow(self)
        self.folder.line_edit.textChanged.connect(self._revalidate)
        form.addRow("Recordings folder on this computer", self.folder)
        self.resolved: str | None = None
        self._needed = True

    def initializePage(self) -> None:  # noqa: N802 - Qt naming
        ws, run = self.pick.workspace, self.pick.run
        self._needed = int(run.params.get("start_analysis_step", 1) or 1) == 1
        found = ws.resolve_raw_data(run)
        if found:
            self.folder.set_value(found)
        elif run.raw_data.get("path"):
            self.folder.set_value(run.raw_data["path"])
        self._revalidate()

    def _revalidate(self, *_args) -> None:
        run = self.pick.run
        value = self.folder.value.strip()
        self.resolved = None
        if not self._needed:
            self.resolved = value
            self.status.setText("This run starts after spike detection, so the raw "
                                "recordings are not needed here.")
        elif is_remote_url(value):
            self.resolved = value
            self.status.setText("✓ The recordings come from a link, the same on every computer.")
        elif value and Workspace.holds_recordings(value, run):
            self.resolved = value
            self.status.setText(f"✓ Found the recordings at {value}")
        else:
            self.status.setText(
                "The recordings were not found where the main computer has them "
                f"({run.raw_data.get('path') or 'no path given'}). Choose the folder "
                "that holds them on this computer.")
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802 - Qt naming
        return self.resolved is not None


# ── The wizards ───────────────────────────────────────────────────────────────

class SetupWizard(QWizard):
    """Create a shared run on this, the main computer."""

    def __init__(self, params: Params, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set up a shared run")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(640, 460)
        self.params = params
        self.folder_page = _SharedFolderPage(params)
        self.machine_page = _BenchmarkPage(ROLE_MAIN)
        self.output_page = _FinalOutputPage(params)
        for page in (_IntroPage(ROLE_MAIN), self.folder_page, self.machine_page,
                     self.output_page):
            self.addPage(page)

    def create(self, log: Callable[[str], None]) -> Workspace:
        """What the wizard gathered, made real. Raises ``ValueError``."""
        return create_workspace(
            self.folder_page.folder.value.strip(), self.folder_page.name.text().strip(),
            self.params, self.machine_page.machine_record(), log=log)

    @property
    def output_folder(self) -> str:
        return self.output_page.folder.value.strip()

    @property
    def output_name(self) -> str:
        return self.output_page.name.text().strip()


class JoinWizard(QWizard):
    """Join a shared run as a helper."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Join a shared run")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(640, 460)
        self.pick_page = _PickWorkspacePage()
        self.raw_page = _RawDataPage(self.pick_page)
        self.machine_page = _BenchmarkPage(ROLE_HELPER)
        for page in (_IntroPage(ROLE_HELPER), self.pick_page, self.raw_page,
                     self.machine_page):
            self.addPage(page)

    def join(self) -> tuple[Workspace, MachineRecord, str | None]:
        ws = self.pick_page.workspace
        record = self.machine_page.machine_record()
        record.raw_data = self.raw_page.resolved or ""
        record = ws.join(record)
        return ws, record, self.raw_page.resolved


# ── The page ──────────────────────────────────────────────────────────────────

class SharedRunPanel(QWidget):
    """Set up or join a shared run, and watch it go."""

    log_message = pyqtSignal(str)
    #: Something the Run button's label or enablement depends on changed.
    changed = pyqtSignal()
    #: This computer joined as a helper: ``(workspace, machine name, raw data)``.
    #: The window starts the helper worker.
    helper_ready = pyqtSignal(object, str, object)
    #: The main computer wants to stop waiting for helpers.
    finish_now_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        #: Supplies the settings a shared run is created from — the window's
        #: ``_collect_params`` — so this page never reads other tabs itself.
        self.params_source: Callable[[], Params] | None = None
        self.workspace: Workspace | None = None
        self.role: str = ""
        self.machine_name: str = ""
        self.params: Params | None = None
        self.output_folder: str = ""
        self.output_name: str = ""
        self._running = False
        self._finished_text = ""
        self._counts: dict[str, int] = {}
        self._touched: set[str] = set()
        self._spins: dict[str, QSpinBox] = {}
        self._views: list[MachineView] = []
        self._run: SharedRun | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        intro = QLabel(
            "Use more than one computer on this batch. One is the <b>main "
            "computer</b> — it sets the run up and ends with the results; the "
            "others <b>join</b> and each take a share of the recordings. They "
            "communicate only through a folder they can all see (Dropbox, "
            "OneDrive, a network drive…), so there is nothing else to set up.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray;")
        layout.addWidget(intro)

        roles = QHBoxLayout()
        self.setup_btn = QPushButton("Set up a shared run on this computer…")
        self.setup_btn.setToolTip("This computer becomes the main computer.")
        self.setup_btn.clicked.connect(self._on_setup)
        self.join_btn = QPushButton("Join a shared run from another computer…")
        self.join_btn.setToolTip("This computer becomes a helper.")
        self.join_btn.clicked.connect(self._on_join)
        roles.addWidget(self.setup_btn)
        roles.addWidget(self.join_btn)
        roles.addStretch()
        layout.addLayout(roles)

        layout.addWidget(self._build_state_box(), stretch=1)
        # Keeps the intro and the two buttons at the top while the state box
        # is hidden; without it Qt spreads them over the empty page.
        layout.addStretch(0)

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._show_state(False)

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_state_box(self) -> QWidget:
        self.state_box = QGroupBox("This shared run")
        layout = QVBoxLayout(self.state_box)
        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.path_label)
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Computer", "Role", "Speed", "Recordings", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.table, stretch=1)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        self.even_btn = QPushButton("Split by speed")
        self.even_btn.setToolTip("Reset the recording counts to the benchmark-proportional split.")
        self.even_btn.clicked.connect(self._reset_split)
        self.finish_btn = QPushButton("Finish now — do the rest here")
        self.finish_btn.setToolTip(
            "Stop waiting for the other computers. Whatever they have finished "
            "is pooled; whatever they have not is analysed on this computer.")
        self.finish_btn.clicked.connect(self.finish_now_requested.emit)
        self.leave_btn = QPushButton("Leave")
        self.leave_btn.setToolTip("Forget this shared run on this computer. "
                                  "Nothing in the shared folder is deleted.")
        self.leave_btn.clicked.connect(self._on_leave)
        for b in (self.refresh_btn, self.even_btn, self.finish_btn, self.leave_btn):
            buttons.addWidget(b)
        buttons.addStretch()
        layout.addLayout(buttons)
        return self.state_box

    def _show_state(self, active: bool) -> None:
        self.state_box.setVisible(active)
        self.setup_btn.setVisible(not active)
        self.join_btn.setVisible(not active)
        if active:
            self._timer.start()
        else:
            self._timer.stop()

    # ── Setting up / joining ──────────────────────────────────────────────────

    def _on_setup(self) -> None:
        if self.params_source is None:
            return
        params = self.params_source()
        problems = []
        if not params.spreadsheet_file_name:
            problems.append("a spreadsheet (Data tab)")
        if not params.raw_data and params.start_analysis_step == 1:
            problems.append("the raw data folder (Data tab)")
        if problems:
            QMessageBox.warning(self, "Not ready to share",
                                "Set " + " and ".join(problems) + " first.")
            return
        wizard = SetupWizard(params, self)
        if wizard.exec() != QWizard.DialogCode.Accepted:
            return
        try:
            ws = wizard.create(self.log_message.emit)
        except ValueError as e:
            QMessageBox.warning(self, "Could not set up the shared run", str(e))
            return
        self.workspace, self.role = ws, ROLE_MAIN
        self.machine_name = ws.read().main
        self.params = params
        self.output_folder, self.output_name = wizard.output_folder, wizard.output_name
        self._counts, self._touched = {}, set()
        self._finished_text = ""
        self._show_state(True)
        self.log_message.emit(
            f"On each helper computer: open MEA-NAP, go to Run → 'Shared with other "
            f"computers' → 'Join a shared run…' and choose:\n    {ws.path}")
        self.refresh()

    def _on_join(self) -> None:
        wizard = JoinWizard(self)
        if wizard.exec() != QWizard.DialogCode.Accepted:
            return
        try:
            ws, record, raw = wizard.join()
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Could not join", str(e))
            return
        self.workspace, self.role, self.machine_name = ws, ROLE_HELPER, record.name
        self.params = None
        self._finished_text = ""
        self._show_state(True)
        self.refresh()
        self.helper_ready.emit(ws, record.name, raw)

    def _on_leave(self) -> None:
        if self._running:
            QMessageBox.information(self, "Still running",
                                    "Stop the run first (the Stop button), then leave.")
            return
        self.reset()

    def reset(self) -> None:
        self.workspace, self.role, self.machine_name = None, "", ""
        self.params, self._run, self._views = None, None, []
        self._counts, self._touched, self._spins = {}, set(), {}
        self.table.setRowCount(0)
        self._show_state(False)
        self.changed.emit()

    # ── State the window reads ────────────────────────────────────────────────

    def set_running(self, running: bool) -> None:
        self._running = running
        self._refresh_buttons()
        self.changed.emit()

    def mark_finished(self, text: str) -> None:
        self._finished_text = text
        self.refresh()

    def run_button_state(self) -> tuple[str, bool, str]:
        """``(label, enabled, tooltip)`` for the Run tab's one Run button."""
        if self.workspace is None:
            return ("▶  Start shared run", False,
                    "Set up a shared run, or join one, first.")
        if self.role == ROLE_HELPER:
            return ("Joined — the main computer starts the run", False, "")
        run = self._run
        if self._running:
            return ("Shared run in progress…", False, "")
        if run is not None and run.status == DONE:
            return ("Shared run finished", False, "")
        if run is not None and run.started:
            return ("▶  Resume the shared run", True,
                    "Continue this computer's share and pool the results.")
        n = len(self._views)
        if n < 2:
            return ("▶  Start shared run", False,
                    "Waiting for at least one other computer to join.")
        return (f"▶  Start shared run on {n} computers", True, "")

    def assignment(self) -> dict[str, list[str]]:
        """Who does which recordings, from the counts in the table. Main first."""
        run = self.workspace.read()
        if run.started:
            return dict(run.assignment)
        names = [v.machine.name for v in self._views]
        counts = self._current_counts(run, names)
        assignment, i = {}, 0
        for name in names:
            assignment[name] = run.recordings[i:i + counts[name]]
            i += counts[name]
        return assignment

    # ── Refreshing from the shared folder ─────────────────────────────────────

    def refresh(self) -> None:
        if self.workspace is None:
            return
        try:
            run = self.workspace.read()
            views = machine_views(self.workspace, run)
        except (ValueError, OSError):
            return   # mid-sync; next tick
        self._run, self._views = run, views
        self.path_label.setText(f"<b>{run.name}</b>  —  {self.workspace.path}")
        self.status_label.setText(self._status_text(run))
        self._fill_table(run, views)
        self._refresh_buttons()
        self.changed.emit()

    def _status_text(self, run: SharedRun) -> str:
        if self._finished_text:
            return self._finished_text
        if run.status == GATHERING:
            if self.role == ROLE_MAIN:
                return ("Waiting for helpers to join. Adjust the recording counts if "
                        "you like, then press Start.")
            return "Joined. Waiting for the main computer to start the run…"
        if run.status == RUNNING:
            return "Running." if self.role == ROLE_MAIN else \
                   "Running — this computer's share is shown in the progress bar below."
        if run.status == DONE:
            return "Finished."
        if run.status == CANCELLED:
            return "Cancelled by the main computer."
        return run.status

    def _refresh_buttons(self) -> None:
        run = self._run
        gathering = run is not None and run.status == GATHERING and self.role == ROLE_MAIN
        self.even_btn.setVisible(gathering)
        self.finish_btn.setVisible(
            self.role == ROLE_MAIN and self._running and run is not None
            and run.status == RUNNING)
        self.leave_btn.setEnabled(not self._running)

    def _current_counts(self, run: SharedRun, names: list[str]) -> dict[str, int]:
        """Recording counts per machine: the proportional split, with any
        counts the user has edited kept as typed."""
        by_name = {v.machine.name: v.machine for v in self._views}
        auto = split_by_score(run.recordings, [by_name[n] for n in names], run.main)
        total = len(run.recordings)
        kept = {n: self._counts[n] for n in names if n in self._touched and n in self._counts}
        remaining = total - sum(kept.values())
        others = [n for n in names if n not in kept]
        if others:
            weights = {n: (by_name[n].score or 1.0) for n in others}
            redistributed = split_recordings(list(range(max(remaining, 0))), weights)
            for n in others:
                auto[n] = redistributed[n]
        counts = {n: (kept[n] if n in kept else len(auto.get(n, []))) for n in names}
        return counts

    def _fill_table(self, run: SharedRun, views: list[MachineView]) -> None:
        names = [v.machine.name for v in views]
        editable = run.status == GATHERING and self.role == ROLE_MAIN and not self._running
        counts = self._current_counts(run, names) if not run.started else \
            {n: len(run.assigned_to(n)) for n in names}
        self._counts = dict(counts)

        self.table.setRowCount(0)
        self.table.setRowCount(len(views))
        self._spins = {}
        for row, view in enumerate(views):
            m = view.machine
            self.table.setItem(row, 0, QTableWidgetItem(
                m.name + ("  (this computer)" if m.name == self.machine_name else "")))
            self.table.setItem(row, 1, QTableWidgetItem(
                "main" if m.role == "main" else "helper"))
            speed = f"{m.score:.2f}" if m.score else "—"
            if m.cores:
                speed += f"  ({m.cores} cores)"
            self.table.setItem(row, 2, QTableWidgetItem(speed))
            if editable and m.name != run.main:
                spin = QSpinBox()
                spin.setRange(0, len(run.recordings))
                spin.setValue(counts[m.name])
                spin.valueChanged.connect(
                    lambda value, name=m.name: self._on_count_edited(name, value))
                self.table.setCellWidget(row, 3, spin)
                self._spins[m.name] = spin
            else:
                self.table.setItem(row, 3, QTableWidgetItem(str(counts[m.name])))
            self.table.setItem(row, 4, QTableWidgetItem(_progress_text(view, run)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def _on_count_edited(self, name: str, value: int) -> None:
        self._touched.add(name)
        self._counts[name] = value
        run = self._run
        if run is None:
            return
        names = [v.machine.name for v in self._views]
        counts = self._current_counts(run, names)
        # The main computer's row shows the remainder straight away.
        for row, view in enumerate(self._views):
            if view.machine.name not in self._spins:
                self.table.setItem(row, 3, QTableWidgetItem(str(counts[view.machine.name])))
        if counts.get(run.main, 0) < 0:
            self.status_label.setText(
                "The helpers' counts add up to more than the batch — reduce one.")
        else:
            self.status_label.setText(self._status_text(run))

    def _reset_split(self) -> None:
        self._touched.clear()
        self._counts.clear()
        self.refresh()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _default_run_name(params: Params) -> str:
    return params.output_data_folder_name or \
        f"SharedRun{datetime.date.today().strftime('%d%b%Y')}"


def _describe_data_reach(params: Params, shared_folder: str) -> str:
    """Whether the other computers will find the raw data without being asked."""
    raw = params.raw_data
    if params.start_analysis_step > 1:
        return ("The run starts after spike detection, so helpers need no raw data — "
                "but they do need the prior analysis folder at the same path.")
    if is_remote_url(raw):
        return "✓ The recordings come from a link, so every computer fetches its own."
    try:
        inside = Path(raw).resolve().is_relative_to(Path(shared_folder).resolve())
    except (OSError, ValueError):
        inside = False
    if inside:
        return ("✓ The recordings are inside the shared folder — the other computers "
                "will find them at the same place.")
    return (f"! The recordings are at {raw}, outside the shared folder. Each helper "
            "will be asked where its own copy is. To avoid that, move them into "
            "the shared folder, or use a Dropbox link on the Data tab.")


def _progress_text(view: MachineView, run: SharedRun) -> str:
    p = view.progress
    if p is None:
        return "joined"
    if not run.started:
        return "ready" if p.status == WAITING else _STATUS_TEXT.get(p.status, p.status)
    text = _STATUS_TEXT.get(p.status, p.status)
    if p.status == WORKING:
        text = f"{p.fraction * 100:.0f}%"
        if p.phase:
            text += f"  ·  {p.phase}"
        if p.detail:
            text += f"  ·  {p.detail}"
        if p.eta_s is not None:
            from meanap.pipeline.progress import format_duration
            text += f"  ·  ~{format_duration(p.eta_s)} left"
    elif p.status == FAILED and p.error:
        text += f": {p.error}"
    age = p.age_s()
    if p.status in (WORKING, WAITING) and age is not None and age > 300:
        text += f"   (no news for {age / 60:.0f} min)"
    return text
