"""Continuing an earlier run: what it holds, and what continuing it will do.

The pipeline already knows how to pick a run up again. ``continue_interrupted``
fills in the recordings a run did not finish and follows a spreadsheet that has
gained or lost rows; ``prune_removed_recordings`` takes a removed recording's
figures out of the folder; and starting at a later step with the run's own
folder as the output re-runs the later steps over what the earlier ones wrote
(:func:`~meanap.pipeline.runner.resumes_in_place`).

What it did not have is a way to *ask* for any of that without knowing those
three switches exist. This module is the part of the simple view's **Continue a
run** page that is not Qt: it reads a run back (its folder or its ``.meanap``),
says which recordings it finished, writes the edited spreadsheet a continued run
uses, and turns "what do you want to do" into the settings a run needs.

The four answers:

``finish``
    Fill in what the run did not get to. Same spreadsheet.
``add``
    Analyse recordings the run did not include; the others are kept.
``remove``
    Leave recordings out, and by default delete their figures.
``rerun``
    Redo the steps from one onwards, for every recording, with whatever
    settings are now set. The earlier steps' results are read from the run.

Everything pooled across recordings (the group comparisons, batch-scaled axes,
cartography boundaries) is redone in every case, since it depends on which
recordings are in the batch.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from meanap.params import PARAMS_FILENAME, Params, load_params, mode_for_params

__all__ = [
    "ACTIONS", "CONTINUED_SUFFIX", "RERUN_STEPS", "RunSummary", "continued_sheet_path",
    "finished_recordings", "plan_lines", "read_run", "run_overrides",
    "write_continued_sheet",
]

#: The answers to "what do you want to do", with how the page labels them.
ACTIONS = {
    "finish": "Finish an interrupted run",
    "add": "Add recordings",
    "remove": "Remove recordings",
    "rerun": "Re-run later steps with new settings",
}

#: The steps a re-run can start at, per pipeline, with their names. CAT-NAP has
#: no step 1 or 3 (adjacency is built in step 2), so step 4 is its only
#: boundary — see ``catnap.pipeline.RESUME_STEP``.
RERUN_STEPS = {
    "meanap": ((2, "Step 2 · neuronal activity"), (3, "Step 3 · functional connectivity"),
               (4, "Step 4 · network activity")),
    "meastim": ((2, "Step 2 · neuronal activity"), (3, "Step 3 · functional connectivity"),
                (4, "Step 4 · network activity")),
    "catnap": ((4, "Step 4 · network activity"),),
}

#: Added to a spreadsheet's name for the copy a continued run uses. Never
#: stacked: continuing a continued run rewrites the same copy.
CONTINUED_SUFFIX = "_continued"


@dataclass
class RunSummary:
    """An earlier run, read back far enough to continue it."""

    #: What was picked: the run's folder or its ``.meanap``.
    path: Path
    #: The folder the run's folder sits in (``Params.output_data_folder``)…
    parent: Path
    #: …and its name (``Params.output_data_folder_name``).
    name: str
    params: Params
    mode: str
    #: "v1.46.0", or "" for a run made before runs were stamped.
    version: str = ""
    #: Only the ``.meanap`` is left (an express run): the pipeline unpacks its
    #: data into the folder when the run is continued.
    bundle_only: bool = False
    #: The recordings the run's spreadsheet lists; ``[]`` if it has gone.
    sheet_names: list[str] = field(default_factory=list)
    #: The recordings whose per-recording work is all there.
    finished: set[str] = field(default_factory=set)
    #: The recordings whose spike times are there (step 1 done).
    detected: set[str] = field(default_factory=set)

    @property
    def sheet(self) -> str:
        return self.params.spreadsheet_file_name

    @property
    def recordings(self) -> list[str]:
        """The run's recordings: its spreadsheet's, or failing that, the finished ones."""
        return list(self.sheet_names) or sorted(self.finished)

    def describe(self) -> str:
        """A few words for the folded card."""
        n = len(self.recordings)
        done = len(self.finished & set(self.recordings)) if self.sheet_names else n
        bits = [self.name, f"{n} recording{'s' * (n != 1)}"]
        if done < n:
            bits[-1] += f", {done} finished"
        if self.version:
            bits.append(self.version)
        return " · ".join(bits)


# ── Reading a run back ───────────────────────────────────────────────────────

def _bundle_contents(bundle: Path) -> tuple[dict, list[str]]:
    """A bundle's ``params.json`` (as written) and its member names."""
    with zipfile.ZipFile(bundle) as zf:
        names = zf.namelist()
        if PARAMS_FILENAME not in names:
            raise ValueError(f"{bundle.name} has no {PARAMS_FILENAME}, so its settings "
                             "can't be read back.")
        raw = json.loads(zf.read(PARAMS_FILENAME))
    return raw, names


def _params_from_raw(raw: dict) -> Params:
    import dataclasses

    known = {f.name for f in dataclasses.fields(Params)}
    return Params(**{k: v for k, v in raw.items() if k in known})


def _version_of(raw: dict) -> str:
    stamp = raw.get("_meanap") if isinstance(raw, dict) else None
    version = stamp.get("version", "") if isinstance(stamp, dict) else ""
    return f"v{version}" if version and not str(version).startswith("v") else str(version)


def _with_suffix(files, suffix: str) -> set[str]:
    out = set()
    for f in files:
        name = Path(str(f)).name
        if name.endswith(suffix):
            out.add(name[: -len(suffix)])
    return out


def finished_recordings(files, params: Params) -> set[str]:
    """Which recordings *files* (paths or names) hold all their per-recording work for.

    A continued run skips spike detection (step 1) and connectivity (step 3)
    for a recording whose file is already there, and CAT-NAP skips the whole
    per-recording step; step 4 is pooled and always redone. So a recording is
    finished when the file for the last per-recording step it ran is there.
    """
    if params.suite2p_mode:
        suffix = "_catnap.npz"
    elif params.stop_analysis_step >= 3:
        suffix = "_adjM.npz"
    else:
        suffix = "_spikes.npz"
    return _with_suffix(files, suffix)


def _sheet_names(params: Params) -> list[str]:
    from meanap.pipeline.spreadsheet import read_recording_names

    sheet = params.spreadsheet_file_name
    if not sheet or not Path(sheet).is_file():
        return []
    try:
        return read_recording_names(sheet, params.spreadsheet_range)
    except Exception:  # an unreadable sheet is the spreadsheet step's to report
        return []


def read_run(path: str | Path) -> RunSummary:
    """Read the run at *path* — its folder or its ``.meanap`` — far enough to continue it.

    Raises :class:`ValueError` saying what is wrong in words a person can act
    on: the folder is not a run, or is the folder *holding* the runs.
    """
    from meanap.pipeline.bundle import BUNDLE_SUFFIX

    path = Path(str(path).strip()).expanduser()
    if path.suffix == BUNDLE_SUFFIX:
        if not path.is_file():
            raise ValueError("This file doesn't exist.")
        try:
            raw, members = _bundle_contents(path)
        except zipfile.BadZipFile:
            raise ValueError(f"{path.name} isn't a readable MEA-NAP bundle.") from None
        folder = path.with_suffix("")
        bundle_only = not (folder / PARAMS_FILENAME).is_file()
        if not bundle_only:
            # The folder is the fuller copy: read the run from there.
            return read_run(folder)
        params = _params_from_raw(raw)
        files = members
    else:
        if not path.is_dir():
            raise ValueError("This folder doesn't exist.")
        params_file = path / PARAMS_FILENAME
        if not params_file.is_file():
            if any((child / PARAMS_FILENAME).is_file() for child in path.iterdir()
                   if child.is_dir()):
                raise ValueError("This folder holds several runs. Choose the one to "
                                 "continue (an OutputData… folder inside it).")
            if any((path / sub).is_dir() for sub in (
                    "1_SpikeDetection", "2_NeuronalActivity", "4_NetworkActivity",
                    "ExperimentMatFiles")):
                raise ValueError(
                    f"This run has no {PARAMS_FILENAME}: it was made by MATLAB, or "
                    "by a Python version from before runs saved their settings, so "
                    "this page can't tell what it was run with. To continue it, "
                    "set the same settings in the Classic view and tick Continue "
                    "previous run on its Run tab.")
            raise ValueError(f"This isn't a MEA-NAP results folder: it has no "
                             f"{PARAMS_FILENAME}.")
        params, _unknown = load_params(params_file)
        with open(params_file) as fh:
            raw = json.load(fh)
        folder, bundle_only = path, False
        files = [p.name for sub in ("ExperimentMatFiles", "1_SpikeDetection")
                 if (path / sub).is_dir() for p in (path / sub).rglob("*.npz")]

    # The run is wherever it is now, not where it was made: a folder moved to
    # another disk continues there.
    params.output_data_folder = str(folder.parent)
    params.output_data_folder_name = folder.name
    return RunSummary(
        path=path, parent=folder.parent, name=folder.name, params=params,
        mode=mode_for_params(params), version=_version_of(raw),
        bundle_only=bundle_only, sheet_names=_sheet_names(params),
        finished=finished_recordings(files, params),
        detected=_with_suffix(files, "_spikes.npz"),
    )


# ── The spreadsheet a continued run uses ─────────────────────────────────────

def continued_sheet_path(sheet: str | Path) -> Path:
    """Where the edited copy of *sheet* goes: beside it, as ``<name>_continued.csv``."""
    sheet = Path(sheet)
    stem = sheet.stem
    if not stem.endswith(CONTINUED_SUFFIX):
        stem += CONTINUED_SUFFIX
    return sheet.with_name(stem + ".csv")


def write_continued_sheet(base: str | Path, keep: set[str] | None = None,
                          extra=None, dest: str | Path | None = None) -> Path:
    """Write the run's spreadsheet *base* with only the rows *keep* names.

    *extra* is a table of rows to append (the recordings being added). The
    original is never touched: the copy goes to *dest*, by default
    :func:`continued_sheet_path`. Returns the path written.
    """
    import pandas as pd

    from meanap.pipeline.spreadsheet import read_recording_table, write_recording_table

    table = read_recording_table(base)
    if keep is not None and not table.empty:
        names = table.iloc[:, 0].astype(str).str.strip()
        table = table[names.isin(keep)]
    if extra is not None and len(extra):
        extra = extra.copy()
        extra.columns = list(table.columns[: extra.shape[1]]) + list(
            extra.columns[table.shape[1]:])
        table = pd.concat([table, extra], ignore_index=True).fillna("")
    return write_recording_table(dest or continued_sheet_path(base), table)


# ── What continuing does ─────────────────────────────────────────────────────

def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def plan_lines(run: RunSummary, sheet_names: list[str], action: str,
               from_step: int = 4, prune: bool = True) -> list[str]:
    """What a run started now would do, line by line, for the page to show."""
    current = list(dict.fromkeys(sheet_names))
    if action == "rerun":
        label = dict(RERUN_STEPS.get(run.mode, ())).get(from_step, f"Step {from_step}")
        name = label.split("·", 1)[-1].strip()
        last = max(run.params.stop_analysis_step, from_step)
        steps = f"Step {from_step}" if last == from_step else f"Steps {from_step}–{last}"
        before = ("the run's spike times and adjacency"
                  if from_step == 4 and run.mode != "catnap" else
                  "the run's spike times" if from_step == 3 else
                  "the run's per-recording results")
        return [
            f"{steps} ({name}{' onwards' if last > from_step else ''}) "
            f"{'is' if last == from_step else 'are'} redone for all "
            f"{_plural(len(current), 'recording')}, with the settings as they are now.",
            f"Earlier steps aren't repeated: {before} are read from the run.",
            f"Results are written into {run.name}, replacing those steps' figures and CSVs.",
        ]

    sheet = set(current)
    before = set(run.recordings)
    done = run.finished & sheet
    todo = [n for n in current if n not in run.finished]
    removed = sorted(before - sheet) if before else []
    lines = []
    if todo:
        new = [n for n in todo if n not in before]
        unfinished = len(todo) - len(new)
        bits = []
        if new:
            bits.append(f"{len(new)} new")
        if unfinished:
            bits.append(f"{unfinished} unfinished")
        lines.append(f"{_plural(len(todo), 'recording')} to analyse ({', '.join(bits)}).")
    elif action != "remove":
        lines.append("Every recording in the spreadsheet is already analysed.")
    if done:
        lines.append(f"{_plural(len(done), 'recording')} kept as they are: their spikes "
                     "and connectivity are reused.")
    if removed:
        fate = ("their figures are deleted, their data kept" if prune else
                "their figures stay in the folder")
        lines.append(f"{_plural(len(removed), 'recording')} left out ({fate}).")
    lines.append(f"Group comparisons, and everything pooled across recordings, are "
                 f"redone over {_plural(len(current), 'recording')}.")
    return lines


def run_overrides(run: RunSummary, action: str, from_step: int = 4,
                  prune: bool = True, sheet_names=None) -> dict:
    """The settings, on top of the window's, that make a run do *action* to *run*.

    Applied to a copy of the run's settings, never saved into the window: a
    continuation is a decision about one run, not a setting for the next.
    """
    where = {"output_data_folder": str(run.parent), "output_data_folder_name": run.name}
    if action == "rerun":
        # Into the run's own folder, recomputing every recording from here on:
        # so not "continue", which would skip every recording already there.
        return {**where, "start_analysis_step": from_step, "continue_interrupted": False,
                "prune_removed_recordings": False, "overwrite_existing_output": True}
    out = {**where, "continue_interrupted": True,
           "prune_removed_recordings": bool(prune) and action == "remove"}
    # Where to start. The run's own start step is right for what it already
    # has, but a recording it never got to needs the steps before that: a run
    # that was itself re-run from step 3 says "start at 3", and a recording
    # added to it would have no spikes. So start early enough for the earliest
    # step any recording still needs; continuing skips the ones already done.
    # A run that reads its earlier steps from elsewhere keeps doing so.
    p = run.params
    if run.mode != "catnap" and not p.prior_analysis and not p.spike_detected_data:
        names = list(sheet_names) if sheet_names is not None else run.recordings
        todo = [n for n in names if n not in run.finished]
        needs = [1 if n not in run.detected else 2 for n in todo]
        if needs:
            out["start_analysis_step"] = min([p.start_analysis_step, *needs])
    return out
