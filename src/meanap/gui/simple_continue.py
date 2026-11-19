"""The simple view's **Continue a run** page: pick a run, then say what to do with it.

The questions, one at a time like a new analysis:

1. **Run to continue** — its results folder or its ``.meanap``. Its settings
   are loaded into the window, so the questions after it start answered.
2. **What do you want to do?** — finish it, add recordings, remove recordings,
   or re-run the later steps with new settings.
3. **Recordings** and 4. **Spreadsheet** — the run's own, already filled in;
   asked again only because data moves between disks. A re-run reads the
   earlier steps from the run, so it does not need the recordings at all.
5. **Recordings to add** or **Recordings to remove**, for those two answers.
   The run's spreadsheet is never edited: the changes go into a copy beside
   it, ``<name>_continued.csv``, which the run then uses.

Before Run, the page says what the run will do (see
:func:`meanap.pipeline.continuation.plan_lines`), and the run gets the
settings that do it on top of the window's
(:func:`~meanap.pipeline.continuation.run_overrides`).

The Qt-free half — reading a run back, the spreadsheet copy, the plan — is in
:mod:`meanap.pipeline.continuation`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

from meanap.gui.simple_checks import Check, check_recordings_folder, recording_names
from meanap.pipeline.continuation import (
    ACTIONS, RERUN_STEPS, RunSummary, continued_sheet_path, plan_lines, read_run,
    run_overrides, write_continued_sheet,
)

if TYPE_CHECKING:  # pragma: no cover
    from meanap.gui.simple_view import SimpleView

__all__ = ["ContinueFlow", "ACTION_HINTS"]

#: One line under each answer to "what do you want to do".
ACTION_HINTS = {
    "finish": "Analyse the recordings it didn't get to. Finished ones are kept.",
    "add": "Analyse more recordings alongside the ones it has.",
    "remove": "Leave some recordings out of the results.",
    "rerun": "Redo the steps from one onwards for every recording, after changing "
             "settings under Other settings.",
}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class ContinueFlow:
    """The state and the questions of **Continue a run**, for one :class:`SimpleView`.

    Holds what the questions are about (the run, the answer to "what do you
    want to do") so it survives the view rebuilding its cards, which it does
    on every pipeline switch and whenever that answer changes which questions
    follow it.
    """

    def __init__(self, view: "SimpleView") -> None:
        self.view = view
        #: What is typed in the run field, kept across rebuilds of the cards.
        self.run_text = ""
        #: The run whose settings are loaded into the window, and from where.
        self.run: RunSummary | None = None
        self._loaded_from = ""
        #: read_run's answer for a path, so a check does not re-walk the folder.
        self._cache: dict[str, RunSummary | str] = {}
        self.action = ""
        self.from_step = 4
        #: Remove: delete the figures of recordings left out.
        self.prune = True
        #: Remove: Continue was pressed (unticked nothing is not an answer).
        self._remove_confirmed = False
        #: The spreadsheet copy this page wrote and pointed the run at, if any.
        self._copy_written = ""

    # ── The run ───────────────────────────────────────────────────────────────

    def forget_cache(self) -> None:
        """Re-read runs from disk: a run just finished, so what is done has changed."""
        self._cache.clear()
        if self.run is not None:
            summary = self._read(self._loaded_from)
            if isinstance(summary, RunSummary):
                self.run = summary

    def _read(self, text: str) -> RunSummary | str:
        if text not in self._cache:
            try:
                self._cache[text] = read_run(text)
            except (ValueError, OSError) as exc:
                self._cache[text] = str(exc)
        return self._cache[text]

    def run_check(self) -> Check | None:
        text = self.run_text.strip()
        if not text:
            return None
        summary = self._read(text)
        if isinstance(summary, str):
            return Check("error", summary)
        if text != self._loaded_from:
            # Loaded after this check returns: loading can switch pipeline,
            # which rebuilds the cards this check is being asked about.
            QTimer.singleShot(0, lambda s=summary, t=text: self._adopt(s, t))
        elif summary.mode != self.view._mode:
            from meanap.gui.modes import MODES

            return Check("error", f"This run was made with "
                         f"{MODES[summary.mode].label.split('·')[0].strip()}. Switch "
                         "back to that pipeline to continue it.")
        bits = [f"{_plural(len(summary.recordings), 'recording')}"]
        unfinished = len(set(summary.recordings) - summary.finished)
        if summary.sheet_names and unfinished:
            bits.append(f"{unfinished} not finished")
        made = f"Made with {summary.version}. " if summary.version else ""
        note = (" Only its .meanap is left: its data is unpacked into a folder beside "
                "it when the run continues." if summary.bundle_only else "")
        return Check("ok", f"{made}{', '.join(bits)}. Its settings are loaded.{note}",
                     summary.describe())

    def _adopt(self, summary: RunSummary, text: str) -> None:
        """Load *summary*'s settings into the window, so the next questions are answered."""
        if self.run_text.strip() != text or self._loaded_from == text:
            return
        self._loaded_from = text
        self.run = summary
        self._remove_confirmed = False
        self._copy_written = ""
        view = self.view
        loader = view.run_loader
        if loader is not None:
            loader(summary.params)      # may switch pipeline, rebuilding the cards
        else:
            view._data.load(summary.params)
        # The steps' own answers ("Continue" on recording settings) carry over;
        # this one is new to each run.
        view._confirmed.discard("action")
        view.evaluate(animate=True, commit=True)

    def pick_run(self, edit: QLineEdit, bundle: bool) -> None:
        """A run's folder, or (*bundle*) its ``.meanap`` file.

        Two dialogs rather than one: a folder dialog cannot hand back a file
        (choosing a ``.meanap`` in it returns the folder it is in), and a file
        dialog cannot hand back a folder.
        """
        start = (edit.text().strip() or self.view._data.output_data_folder.value
                 or str(Path.home()))
        if Path(start).is_file():
            start = str(Path(start).parent)
        if bundle:
            path, _ = QFileDialog.getOpenFileName(
                self.view, "Choose the run's .meanap file", start,
                "MEA-NAP runs (*.meanap)")
        else:
            from meanap.gui.simple_view import _pick_folder

            path = _pick_folder(self.view, "Choose the run's results folder", start)
        if path:
            edit.setText(path)
            self.view.evaluate(animate=True, commit=True)

    # ── The questions ─────────────────────────────────────────────────────────

    def build(self, add, recordings_step, spreadsheet_step) -> None:
        """Add this page's questions through the view's *add*.

        *recordings_step* and *spreadsheet_step* add the new-analysis page's
        own questions, wrapped in a check of this page's.
        """
        view = self.view
        mode = view._mode

        edit = QLineEdit(self.run_text)
        edit.setPlaceholderText("The run's results folder, or its .meanap file")
        edit.textChanged.connect(lambda t: setattr(self, "run_text", t))
        edit.returnPressed.connect(lambda: view.evaluate(animate=True, commit=True))
        row = QWidget()
        row.setObjectName("stepRow")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        line.addWidget(edit, 1)
        for text, bundle, tip in (
                ("Folder…", False, "The run's results folder (OutputData…)"),
                (".meanap…", True, "The run's .meanap file, e.g. from an express run")):
            browse = QPushButton(text)
            browse.setCursor(Qt.CursorShape.PointingHandCursor)
            browse.setToolTip(tip)
            browse.clicked.connect(lambda _=False, b=bundle: self.pick_run(edit, b))
            line.addWidget(browse)
        row.edit = edit
        add("run", "Run to continue",
            "The results folder of an earlier run (OutputData…), or its .meanap file.",
            row, self.run_check, focus=edit, watch=[edit])

        add("action", "What do you want to do?", "", self._action_body(mode),
            self._action_check, confirm=True)

        # A re-run reads every step before it from the run, so the recordings
        # themselves are not needed — only the spreadsheet saying which they are.
        recordings_step(self._recordings_check)
        spreadsheet_step()

        if self.action == "add" and "action" in view._confirmed:
            add("changes", "Recordings to add",
                "They go into a copy of the spreadsheet, so the run's own is "
                "left as it was.", self._add_body(), self._add_check)
        elif self.action == "remove" and "action" in view._confirmed:
            add("changes", "Recordings to remove",
                "Untick the ones to leave out. The run's spreadsheet is left as "
                "it was: the rest go into a copy beside it.",
                self._remove_body(), self._remove_check)

    def _needs_recordings(self) -> bool:
        """Whether this run will have to detect spikes, so read the recordings."""
        if self.action == "add":
            return True
        if self.action == "rerun" or self.run is None or self.run.mode == "catnap":
            return self.action != "rerun"
        return any(n not in self.run.detected for n in self.run.recordings)

    def spreadsheet_folder(self) -> str:
        """The folder to look for the spreadsheet's recordings in, or ``""``.

        Only when the run will read them. A removal or a re-run reads every
        recording from the run, so a spreadsheet naming recordings that are on
        another disk now, in sub-folders, or never raw files at all (spikes
        imported from a sorter) is still the right spreadsheet.
        """
        if self.action and not self._needs_recordings():
            return ""
        return self.view._folder_text()

    def _recordings_check(self) -> Check | None:
        if self.action and not self._needs_recordings():
            why = ("re-run later steps" if self.action == "rerun" else
                   "continue: every recording's spikes are in the run")
            found = check_recordings_folder(self.view._folder_text(), self.view._mode)
            if found is None or not found.complete:
                return Check("ok", f"Not needed to {why}.", "Not needed")
        return check_recordings_folder(self.view._folder_text(), self.view._mode)

    # What to do ────────────────────────────────────────────────────────────

    def _action_body(self, mode: str) -> QWidget:
        body = QWidget()
        body.setObjectName("stepRow")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        group = QButtonGroup(body)
        self._step_combo = QComboBox()
        for step, label in RERUN_STEPS.get(mode, ()):
            self._step_combo.addItem(label, step)
        index = self._step_combo.findData(self.from_step)
        self._step_combo.setCurrentIndex(index if index >= 0 else
                                         self._step_combo.count() - 1)
        self.from_step = self._step_combo.currentData() or 4
        self._step_combo.currentIndexChanged.connect(self._on_step_changed)
        self._radios: dict[str, QRadioButton] = {}
        for key, label in ACTIONS.items():
            radio = QRadioButton(label)
            radio.setChecked(key == self.action)
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(radio)
            radio.toggled.connect(lambda on, k=key: on and self._on_action(k))
            hint = QLabel(ACTION_HINTS[key])
            hint.setObjectName("stepHint")
            hint.setWordWrap(True)
            hint.setContentsMargins(24, 0, 0, 6)
            layout.addWidget(radio)
            if key == "rerun":
                pick = QHBoxLayout()
                pick.setContentsMargins(24, 0, 0, 0)
                label_from = QLabel("From")
                label_from.setObjectName("stepHint")
                pick.addWidget(label_from)
                pick.addWidget(self._step_combo)
                pick.addStretch(1)
                layout.addWidget(hint)
                layout.addLayout(pick)
            else:
                layout.addWidget(hint)
            self._radios[key] = radio
        self._step_combo.setEnabled(self.action == "rerun")

        done = QPushButton("Continue")
        done.setObjectName("primary")
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.clicked.connect(self._confirm_action)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(done)
        layout.addLayout(actions)
        self._action_done = done
        done.setEnabled(bool(self.action))
        return body

    def _on_action(self, key: str) -> None:
        self.action = key
        self._remove_confirmed = False
        self._step_combo.setEnabled(key == "rerun")
        self._action_done.setEnabled(True)
        # A different answer is a new answer: it waits for Continue.
        self.view._confirmed.discard("action")
        self.view.evaluate(animate=True)

    def _on_step_changed(self, _index: int) -> None:
        self.from_step = self._step_combo.currentData() or 4
        self.view.refresh_plan()

    def _confirm_action(self) -> None:
        if not self.action:
            return
        # A new answer starts from the run's own spreadsheet: a copy written
        # for removing recordings is not what adding or re-running is about.
        if self.run is not None and self._copy_written:
            data = self.view._data
            if data.spreadsheet.value.strip() == self._copy_written:
                data.spreadsheet.set_value(self.run.sheet)
            self._copy_written = ""
        self.view._confirmed.add("action")
        # Which questions follow depends on the answer: rebuild, then move on.
        self.view.rebuild_steps()
        self.view.evaluate(animate=True, commit=True)

    def _action_check(self) -> Check | None:
        if not self.action or "action" not in self.view._confirmed:
            return None
        summary = ACTIONS[self.action]
        if self.action == "rerun":
            summary = f"Re-run from step {self.from_step}"
        return Check("ok", "", summary)

    # Adding ──────────────────────────────────────────────────────────────────

    def _sheet_now(self) -> list[str]:
        from meanap.pipeline.spreadsheet import read_recording_names

        path = self.view._data.spreadsheet.value.strip()
        if not path or not Path(path).is_file():
            return []
        try:
            return read_recording_names(path, self.view._data.spreadsheet_range.text())
        except Exception:
            return []

    def _candidates(self) -> list[str]:
        """Recordings in the folder that the run doesn't have."""
        have = set(self.run.recordings) if self.run else set()
        return [n for n in recording_names(self.view._folder_text(), self.view._mode)
                if n not in have]

    def _add_body(self) -> QWidget:
        body = QWidget()
        body.setObjectName("stepRow")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._add_label = QLabel()
        self._add_label.setWordWrap(True)
        self._add_button = QPushButton("Add them to a copy of the spreadsheet…")
        self._add_button.setObjectName("primary")
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_button.clicked.connect(self.open_add_editor)
        layout.addWidget(self._add_label)
        layout.addWidget(self._add_button, 0, Qt.AlignmentFlag.AlignLeft)
        return body

    def open_add_editor(self) -> None:
        """The spreadsheet editor, with the run's rows and one per new recording."""
        import pandas as pd

        from meanap.gui.panels.spreadsheet_editor import edit_spreadsheet
        from meanap.pipeline.spreadsheet import new_recording_table, read_recording_table

        base = self.run.sheet if self.run else ""
        if not base or not Path(base).is_file():
            base = self.view._data.spreadsheet.value.strip()
        current = self.view._data.spreadsheet.value.strip()
        target = continued_sheet_path(base)
        # Adding twice builds on the first time's copy, not the original.
        source = current if Path(current).is_file() and Path(current) == target else base
        table = read_recording_table(source)
        have = set(table.iloc[:, 0].astype(str).str.strip()) if not table.empty else set()
        new = [n for n in self._candidates() if n not in have]
        if new:
            extra = new_recording_table(new)
            extra.columns = list(table.columns[:extra.shape[1]]) + list(
                extra.columns[table.shape[1]:])
            table = pd.concat([table, extra], ignore_index=True).fillna("")
        path = edit_spreadsheet(self.view, path="", table=table,
                                suggested_path=str(target), suggest=bool(new))
        if path:
            self._copy_written = path
            self.view._data.spreadsheet.set_value(path)
            self.view.evaluate(animate=True, commit=True)

    def _add_check(self) -> Check | None:
        have = set(self.run.recordings) if self.run else set()
        added = [n for n in self._sheet_now() if n not in have]
        candidates = self._candidates()
        if hasattr(self, "_add_label"):
            if candidates:
                shown = ", ".join(candidates[:4]) + (
                    f" and {len(candidates) - 4} more" if len(candidates) > 4 else "")
                self._add_label.setText(
                    f"{_plural(len(candidates), 'recording')} in the recordings folder "
                    f"aren't in this run: {shown}. Give each a DIV and a group.")
                self._add_button.setText("Add them to a copy of the spreadsheet…")
            else:
                self._add_label.setText(
                    "Every recording in the recordings folder is already in this run. "
                    "To add others, choose the folder they are in under Recordings, "
                    "or add rows by hand.")
                self._add_button.setText("Edit a copy of the spreadsheet…")
        if not added:
            return None
        total = len(self._sheet_now())
        return Check("ok", f"{_plural(len(added), 'recording')} added: "
                     f"{', '.join(added[:4])}{'…' if len(added) > 4 else ''}",
                     f"{len(added)} added ({total} in all)")

    # Removing ────────────────────────────────────────────────────────────────

    def _remove_body(self) -> QWidget:
        body = QWidget()
        body.setObjectName("stepRow")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._remove_list = QListWidget()
        self._remove_list.setMaximumHeight(220)
        now = set(self._sheet_now())
        for name in (self.run.recordings if self.run else []):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if not now or name in now
                               else Qt.CheckState.Unchecked)
            self._remove_list.addItem(item)
        self._remove_list.itemChanged.connect(self._on_remove_ticked)
        self._prune_box = QCheckBox("Delete the figures of the recordings left out")
        self._prune_box.setChecked(self.prune)
        self._prune_box.setToolTip(
            "Left in the folder, their figures look like part of the analysis, "
            "though no CSV or group comparison includes them any more. Their "
            "data files are kept either way, so putting one back is quick.")
        self._prune_box.toggled.connect(self._on_prune)
        done = QPushButton("Continue")
        done.setObjectName("primary")
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.clicked.connect(self.apply_removal)
        actions = QHBoxLayout()
        actions.addWidget(self._prune_box)
        actions.addStretch(1)
        actions.addWidget(done)
        layout.addWidget(self._remove_list)
        layout.addLayout(actions)
        return body

    def _on_prune(self, on: bool) -> None:
        self.prune = on
        self.view.refresh_plan()

    def _on_remove_ticked(self, _item) -> None:
        self._remove_confirmed = False
        self.view.evaluate(animate=True)

    def _kept(self) -> list[str]:
        items = [self._remove_list.item(i) for i in range(self._remove_list.count())]
        return [i.text() for i in items if i.checkState() == Qt.CheckState.Checked]

    def apply_removal(self) -> None:
        """Write the copy of the spreadsheet without the unticked recordings, and use it."""
        if self.run is None:
            return
        kept = self._kept()
        self._remove_confirmed = True
        if kept and len(kept) < len(self.run.recordings):
            base = self.run.sheet
            path = write_continued_sheet(base, keep=set(kept))
            self._copy_written = str(path)
            self.view._data.spreadsheet.set_value(str(path))
        self.view.evaluate(animate=True, commit=True)

    def _remove_check(self) -> Check | None:
        if self.run is None or not self._remove_confirmed:
            return None
        kept = self._kept()
        if not kept:
            return Check("error", "Keep at least one recording.")
        removed = [n for n in self.run.recordings if n not in set(self._sheet_now())]
        if not removed:
            return Check("error", "Untick the recordings to leave out, then Continue.")
        return Check("ok", f"Leaving out {', '.join(removed[:4])}"
                     f"{'…' if len(removed) > 4 else ''}",
                     f"{len(removed)} removed ({len(kept)} left)")

    # ── The run ───────────────────────────────────────────────────────────────

    def plan(self) -> list[str]:
        if self.run is None or not self.action:
            return []
        return plan_lines(self.run, self._sheet_now(), self.action, self.from_step,
                          self.prune)

    def overrides(self) -> dict | None:
        if self.run is None or not self.action:
            return None
        return run_overrides(self.run, self.action, self.from_step, self.prune,
                             self._sheet_now())

    def run_label(self) -> str:
        if self.run is None:
            return "Continue"
        if self.action == "rerun":
            return f"Re-run {self.run.name} from step {self.from_step}"
        return f"Continue {self.run.name}"
