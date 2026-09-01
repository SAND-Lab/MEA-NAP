"""The shared folder a multi-computer run goes through, and what is in it.

A shared run lives in one directory inside whatever folder the machines have
in common — ``<shared folder>/<run name>.meanap-shared/``::

    Run1.meanap-shared/
        shared_run.json           what the run is: settings, recordings, who
                                  does which, and whether it has started
        recordings.csv            the whole batch, copied from the spreadsheet
        machines/
            desktop/
                machine.json      who this is: name, speed, version
                progress.json     how far it has got (rewritten as it goes)
                recordings.csv    its share of the batch
                output/           an ordinary MEA-NAP output folder for that
                                  share (or output.meanap, in express mode)
            laptop/
                ...

Nothing here is a lock or a queue. The main computer decides the split before
anything starts and writes it into ``shared_run.json``; from then on every
machine only ever *reads* that file and *writes* its own ``machines/<name>/``
subtree. Two machines never write the same file, which is what lets this work
over a sync service — Dropbox and its kind resolve concurrent writes to one
file by making a "conflicted copy", and a design that never causes one has
nothing to recover from.

Every JSON file is written atomically (:mod:`meanap.pipeline.atomic`) so a
reader on another machine sees the previous version or the new one, never a
half-synced one; and every read tolerates an unreadable file by reporting
"nothing yet", because on a syncing folder that is what an in-flight write
looks like from the other side.
"""

from __future__ import annotations

import dataclasses
import datetime
import math
import os
import platform
import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable


from meanap.params import Params, is_remote_url, mode_for_params
from meanap.pipeline.atomic import atomic_write_json
from meanap.pipeline.spreadsheet import (
    read_recording_csv, read_recording_table, write_recording_table,
)
from meanap.version import meanap_version

__all__ = [
    "WORKSPACE_SUFFIX", "FORMAT_VERSION",
    "GATHERING", "RUNNING", "DONE", "CANCELLED",
    "WAITING", "WORKING", "FINISHED", "FAILED", "STOPPED",
    "MachineRecord", "ProgressRecord", "SharedRun", "Workspace",
    "create_workspace", "open_workspace", "is_workspace",
    "split_recordings", "default_machine_name", "local_cache_dir", "utc_now",
]

WORKSPACE_SUFFIX = ".meanap-shared"
FORMAT_VERSION = 1

MANIFEST_NAME = "shared_run.json"
SPREADSHEET_NAME = "recordings.csv"
MACHINES_DIR = "machines"
MACHINE_FILE = "machine.json"
PROGRESS_FILE = "progress.json"
#: Inside ``machines/<name>/``: that machine's share of the batch, and where
#: its results go. The output is a plain ``output_data_folder_name`` so the
#: part is an ordinary run in every respect — resumable, openable, exportable.
PART_SPREADSHEET = "recordings.csv"
PART_OUTPUT = "output"

#: The run as a whole.
GATHERING, RUNNING, DONE, CANCELLED = "gathering", "running", "done", "cancelled"
#: One machine within it.
WAITING, WORKING, FINISHED, FAILED, STOPPED = (
    "waiting", "running", "done", "failed", "stopped")

#: The spreadsheet column that names a recording — what every part file is
#: filtered on.
_NAME_COLUMN = "Recording Filename"
#: Every row: the part spreadsheets are written whole, so the range is not
#: carried across from the original (which selected rows of a different file).
_ALL_ROWS = "A2:A100000"


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _parse_time(stamp: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None


def default_machine_name() -> str:
    """Something a person will recognise this computer by, filesystem-safe."""
    return sanitize_name(socket.gethostname().split(".")[0] or "computer")


def sanitize_name(name: str) -> str:
    """A machine name as a directory name: letters, digits, ``-`` and ``_``."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-_")
    return cleaned or "computer"


def local_cache_dir() -> Path:
    """Where a shared run's worker keeps fetched remote data — *not* in the
    shared folder, or every byte streamed in would be synced straight back out."""
    return Path.home() / "MEA-NAP" / "MEANAP-cache"


# ── Records ───────────────────────────────────────────────────────────────────

@dataclass
class MachineRecord:
    """One computer taking part."""

    name: str
    role: str = "helper"                 # "main" | "helper"
    hostname: str = ""
    platform: str = ""
    cores: int = 0
    ram_gb: float = 0.0
    meanap_version: str = ""
    #: From :mod:`meanap.shared.benchmark`. ``score`` is relative speed —
    #: higher is faster — and is what the split is proportional to.
    benchmark_seconds: float | None = None
    score: float | None = None
    joined_at: str = ""
    #: Where *this* machine reads the raw recordings from. Recorded so the
    #: main computer's log can say where each part's data came from.
    raw_data: str = ""

    @classmethod
    def for_this_machine(cls, name: str, role: str = "helper") -> "MachineRecord":
        from meanap.pipeline.parallel import available_ram_gb, physical_cores

        try:
            import psutil
            ram = psutil.virtual_memory().total / 1e9
        except Exception:                                   # noqa: BLE001
            ram = available_ram_gb()
        return cls(
            name=sanitize_name(name), role=role,
            hostname=socket.gethostname(),
            platform=f"{platform.system()} {platform.release()}".strip(),
            cores=physical_cores(), ram_gb=round(ram, 1),
            meanap_version=meanap_version(), joined_at=utc_now(),
        )


@dataclass
class ProgressRecord:
    """How far one machine has got. Rewritten by that machine as it goes."""

    status: str = WAITING
    phase: str = ""
    detail: str = ""
    fraction: float = 0.0
    elapsed_s: float = 0.0
    eta_s: float | None = None
    #: How many recordings this machine was given.
    recordings: int = 0
    updated_at: str = ""
    error: str = ""

    @property
    def finished(self) -> bool:
        """Nothing more will come from this machine, one way or another."""
        return self.status in (FINISHED, FAILED, STOPPED)

    def age_s(self, now: datetime.datetime | None = None) -> float | None:
        """Seconds since this was written, by the writer's clock. ``None`` if
        the stamp is missing or unreadable."""
        then = _parse_time(self.updated_at)
        if then is None:
            return None
        now = now or datetime.datetime.now(datetime.timezone.utc)
        if then.tzinfo is None:
            then = then.replace(tzinfo=datetime.timezone.utc)
        return max(0.0, (now - then).total_seconds())


@dataclass
class SharedRun:
    """``shared_run.json`` — the run's description, written by the main computer."""

    name: str
    main: str
    mode: str
    params: dict[str, Any]
    #: ``{"path": absolute, "relative": relative to the workspace or "",
    #: "remote": bool}`` — see :meth:`Workspace.resolve_raw_data`.
    raw_data: dict[str, Any]
    recordings: list[str]
    status: str = GATHERING
    assignment: dict[str, list[str]] = field(default_factory=dict)
    format: int = FORMAT_VERSION
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    meanap_version: str = ""
    #: Where the main computer pools everything — recorded so a main that is
    #: restarted mid-way finishes into the same folder rather than a new one.
    final_output: str = ""

    @property
    def started(self) -> bool:
        return self.status in (RUNNING, DONE, CANCELLED) and bool(self.assignment)

    def assigned_to(self, machine: str) -> list[str]:
        return list(self.assignment.get(machine, []))

    def to_params(self) -> Params:
        """The settings the run was created with, as a fresh ``Params``.

        Unknown keys are dropped rather than raised on, as ``load_params``
        does: a helper on a slightly different version should still be able
        to take part, and a field it does not know is one it would not read.
        """
        known = {f.name for f in dataclasses.fields(Params)}
        return Params(**{k: v for k, v in self.params.items() if k in known})


# ── JSON on a syncing folder ──────────────────────────────────────────────────

def _write_json(path: Path, payload: dict, attempts: int = 5) -> None:
    """Atomic write, retried: a sync client can hold a file open for a moment
    on Windows, and the retry is cheaper than explaining the traceback."""
    for attempt in range(attempts):
        try:
            atomic_write_json(path, payload, indent=2)
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.3 * (attempt + 1))


def _read_json(path: Path) -> dict | None:
    """The object in *path*, or ``None`` when there isn't a readable one yet."""
    import json

    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _from_dict(cls, data: dict):
    known = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in known})


# ── The workspace ─────────────────────────────────────────────────────────────

def is_workspace(path: Path | str) -> bool:
    p = Path(path)
    return p.is_dir() and (p / MANIFEST_NAME).is_file()


class Workspace:
    """One ``<name>.meanap-shared/`` directory and the records inside it."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def __repr__(self) -> str:
        return f"Workspace({str(self.path)!r})"

    # ── Paths ─────────────────────────────────────────────────────────────────

    @property
    def manifest_path(self) -> Path:
        return self.path / MANIFEST_NAME

    @property
    def spreadsheet_path(self) -> Path:
        return self.path / SPREADSHEET_NAME

    @property
    def machines_dir(self) -> Path:
        return self.path / MACHINES_DIR

    def machine_dir(self, name: str) -> Path:
        return self.machines_dir / name

    def part_spreadsheet(self, name: str) -> Path:
        return self.machine_dir(name) / PART_SPREADSHEET

    def part_output(self, name: str) -> Path:
        """The output *folder* a machine's share is written to."""
        return self.machine_dir(name) / PART_OUTPUT

    def part_results(self, name: str) -> Path | None:
        """What a machine has produced: its output folder, or the bundle an
        express run leaves in its place. ``None`` when there is nothing yet."""
        from meanap.pipeline.bundle import BUNDLE_SUFFIX

        folder = self.part_output(name)
        bundle = folder.with_suffix(BUNDLE_SUFFIX)
        if bundle.is_file():
            return bundle
        if folder.is_dir() and any(p.is_file() for p in folder.rglob("*")):
            return folder
        return None

    # ── The manifest ──────────────────────────────────────────────────────────

    def read(self) -> SharedRun:
        data = _read_json(self.manifest_path)
        if data is None:
            raise ValueError(
                f"{self.path} is not a shared run — no readable {MANIFEST_NAME} in it. "
                f"Pick the folder ending in '{WORKSPACE_SUFFIX}' that the main "
                "computer created.")
        fmt = int(data.get("format", 0))
        if fmt > FORMAT_VERSION:
            raise ValueError(
                f"This shared run was created by a newer MEA-NAP (format {fmt}; "
                f"this version reads up to {FORMAT_VERSION}). Update MEA-NAP on "
                "this computer to join it.")
        return _from_dict(SharedRun, data)

    def write(self, run: SharedRun) -> None:
        _write_json(self.manifest_path, dataclasses.asdict(run))

    def set_status(self, status: str) -> SharedRun:
        run = self.read()
        run.status = status
        if status in (DONE, CANCELLED):
            run.finished_at = utc_now()
        self.write(run)
        return run

    # ── Machines ──────────────────────────────────────────────────────────────

    def join(self, record: MachineRecord) -> MachineRecord:
        """Register a machine, giving it a name nobody else here has.

        The same computer joining again — MEA-NAP restarted, say — keeps its
        name, so its progress and any partial results stay attached to it. A
        *different* computer asking for a taken name gets ``name-2``.
        """
        base = sanitize_name(record.name)
        name, n = base, 1
        while True:
            existing = self.machine(name)
            if existing is None or existing.hostname == record.hostname:
                break
            n += 1
            name = f"{base}-{n}"
        record.name = name
        if not record.joined_at:
            record.joined_at = utc_now()
        self.machine_dir(name).mkdir(parents=True, exist_ok=True)
        _write_json(self.machine_dir(name) / MACHINE_FILE, dataclasses.asdict(record))
        # A fresh record is waiting until it is told otherwise; without this a
        # machine that joined and was never assigned reads as "never heard from".
        if self.read_progress(name) is None:
            self.write_progress(name, ProgressRecord(status=WAITING))
        return record

    def machine(self, name: str) -> MachineRecord | None:
        data = _read_json(self.machine_dir(name) / MACHINE_FILE)
        return _from_dict(MachineRecord, data) if data else None

    def machines(self) -> list[MachineRecord]:
        """Everyone who has joined — the main computer first, then by name."""
        found: list[MachineRecord] = []
        if self.machines_dir.is_dir():
            for entry in sorted(self.machines_dir.iterdir()):
                if entry.is_dir():
                    rec = self.machine(entry.name)
                    if rec is not None:
                        found.append(rec)
        found.sort(key=lambda m: (m.role != "main", m.name.lower()))
        return found

    # ── Progress ──────────────────────────────────────────────────────────────

    def write_progress(self, name: str, record: ProgressRecord) -> None:
        record.updated_at = utc_now()
        self.machine_dir(name).mkdir(parents=True, exist_ok=True)
        _write_json(self.machine_dir(name) / PROGRESS_FILE, dataclasses.asdict(record))

    def read_progress(self, name: str) -> ProgressRecord | None:
        data = _read_json(self.machine_dir(name) / PROGRESS_FILE)
        return _from_dict(ProgressRecord, data) if data else None

    # ── Starting ──────────────────────────────────────────────────────────────

    def start(self, assignment: dict[str, list[str]]) -> SharedRun:
        """Fix who does what and open the run.

        Writes each machine's share as its own spreadsheet — the same columns
        as the original, only the rows it was given — and only then flips the
        manifest to *running*, so a helper that sees the flag can rely on its
        part file being there.
        """
        run = self.read()
        given = [r for recs in assignment.values() for r in recs]
        if sorted(given) != sorted(run.recordings):
            raise ValueError(
                "The split must cover every recording exactly once: "
                f"{len(given)} assigned, {len(run.recordings)} in the batch.")
        table = read_recording_table(self.spreadsheet_path)
        for name, recs in assignment.items():
            wanted = set(recs)
            part = table[table[_NAME_COLUMN].isin(wanted)]
            write_recording_table(self.part_spreadsheet(name), part)
            progress = self.read_progress(name) or ProgressRecord()
            progress.recordings = len(recs)
            self.write_progress(name, progress)
        run.assignment = {name: list(recs) for name, recs in assignment.items()}
        run.status = RUNNING
        run.started_at = utc_now()
        self.write(run)
        return run

    # ── Raw data ──────────────────────────────────────────────────────────────

    def resolve_raw_data(self, run: SharedRun | None = None) -> str | None:
        """Where the raw recordings are *on this machine*, if that can be told.

        A remote source is the same everywhere. A local one is tried relative
        to the workspace first — the case where the data sits in the same
        synced folder, so the layout is identical on every machine — and then
        at the absolute path the main computer used. Either is accepted only
        if it actually holds one of the batch's recordings: a path that merely
        exists could be anything.
        """
        run = run or self.read()
        info = run.raw_data or {}
        path = str(info.get("path") or "")
        if info.get("remote") or is_remote_url(path):
            return path or None
        candidates: list[Path] = []
        rel = info.get("relative") or ""
        if rel:
            candidates.append((self.path / rel).resolve())
        if path:
            candidates.append(Path(path))
        for candidate in candidates:
            if candidate.is_dir() and self.holds_recordings(candidate, run):
                return str(candidate)
        return None

    @staticmethod
    def holds_recordings(folder: Path | str, run: SharedRun) -> bool:
        """Whether *folder* contains any of the batch's recordings."""
        folder = Path(folder)
        if not folder.is_dir():
            return False
        # A few is enough to tell a data folder from a folder; every recording
        # would mean listing a large directory once per candidate.
        for name in run.recordings[:5]:
            if _holds_recording(folder, name, run.mode):
                return True
        return False

    # ── Parameters for each kind of run ───────────────────────────────────────

    def worker_params(self, name: str, raw_data: str | None = None,
                      run: SharedRun | None = None) -> Params:
        """The settings for one machine's share.

        The same analysis as the manifest describes, pointed at that machine's
        part spreadsheet and its own output folder in the workspace, and set to
        *continue* — so a machine that stopped partway (closed lid, reboot)
        picks up rather than starts over.
        """
        run = run or self.read()
        p = run.to_params()
        p.spreadsheet_file_name = str(self.part_spreadsheet(name))
        p.spreadsheet_range = _ALL_ROWS
        p.output_data_folder = str(self.machine_dir(name))
        p.output_data_folder_name = PART_OUTPUT
        p.continue_interrupted = True
        p.overwrite_existing_output = False
        p.prune_removed_recordings = False
        p.raw_data = raw_data if raw_data is not None else (self.resolve_raw_data(run) or "")
        if is_remote_url(p.raw_data):
            # Streamed data must not land in the shared folder, where it
            # would sync straight back out to every other machine.
            if not p.cache_dir:
                p.cache_dir = str(local_cache_dir())
            if p.suite2p_mode and not p.derived_data_folder:
                p.derived_data_folder = str(local_cache_dir() / "derived")
        return p

    def final_params(self, output_data_folder: str | Path,
                     output_data_folder_name: str, raw_data: str | None = None,
                     run: SharedRun | None = None) -> Params:
        """The settings for the pooled run on the main computer.

        Over the *whole* spreadsheet, into the folder the parts were merged
        into, continuing — which is exactly the mechanism that adds a recording
        to an existing run: everything per-recording is already there and is
        skipped, everything computed across the batch is redone over all of it.
        """
        run = run or self.read()
        p = run.to_params()
        p.spreadsheet_file_name = str(self.spreadsheet_path)
        p.spreadsheet_range = _ALL_ROWS
        p.output_data_folder = str(output_data_folder)
        p.output_data_folder_name = output_data_folder_name
        p.continue_interrupted = True
        p.overwrite_existing_output = False
        p.prune_removed_recordings = False
        p.raw_data = raw_data if raw_data is not None else (self.resolve_raw_data(run) or "")
        if is_remote_url(p.raw_data) and not p.cache_dir:
            p.cache_dir = str(local_cache_dir())
        return p

    # ── Reading the state at a glance ─────────────────────────────────────────

    def describe(self) -> list[str]:
        run = self.read()
        lines = [f"Shared run '{run.name}' — {run.status}, "
                 f"{len(run.recordings)} recording(s), main computer: {run.main}"]
        for m in self.machines():
            prog = self.read_progress(m.name)
            share = len(run.assigned_to(m.name)) if run.assignment else None
            bits = [f"{m.name} ({m.role})"]
            if m.score is not None:
                bits.append(f"speed {m.score:.2f}")
            if share is not None:
                bits.append(f"{share} recording(s)")
            if prog is not None:
                state = prog.status
                if prog.status == WORKING:
                    state += f" {prog.fraction * 100:.0f}%"
                    if prog.detail:
                        state += f" · {prog.detail}"
                bits.append(state)
            lines.append("  " + " · ".join(bits))
        return lines


def _holds_recording(folder: Path, name: str, mode: str) -> bool:
    if mode == "catnap":
        # suite2p output: a directory per recording, named for it.
        return (folder / name).is_dir() or any(
            p.is_dir() and p.name.startswith(name) for p in folder.iterdir())
    from meanap.pipeline.io import find_raw_file

    return find_raw_file(folder, name) is not None


# ── Creating one ──────────────────────────────────────────────────────────────

def create_workspace(
    shared_folder: Path | str,
    name: str,
    params: Params,
    main: MachineRecord,
    *,
    log: Callable[[str], None] | None = None,
) -> Workspace:
    """Set up ``<shared_folder>/<name>.meanap-shared/`` from *params*.

    Copies the batch (the rows the spreadsheet range selects) into the
    workspace so every machine reads the same list, records where the raw
    data is in both absolute and workspace-relative form, and registers the
    main computer. Refuses to reuse a directory that already holds a run.
    """
    shared_folder = Path(shared_folder)
    if not shared_folder.is_dir():
        raise ValueError(f"The shared folder does not exist: {shared_folder}")
    if not params.spreadsheet_file_name:
        raise ValueError("A spreadsheet is needed to know which recordings to share out.")
    if not params.raw_data and params.start_analysis_step == 1:
        raise ValueError("The raw data folder is needed to run step 1 on every machine.")

    path = shared_folder / f"{sanitize_name(name)}{WORKSPACE_SUFFIX}"
    if is_workspace(path):
        raise ValueError(
            f"{path.name} already holds a shared run. Pick another name, or "
            "delete that folder if the run is finished with.")
    path.mkdir(parents=True, exist_ok=True)

    recordings = read_recording_csv(params.spreadsheet_file_name, params.spreadsheet_range)
    if not recordings:
        raise ValueError("No recordings found in the given spreadsheet range.")
    names = [r.filename for r in recordings]
    table = read_recording_table(params.spreadsheet_file_name)
    table = table[table[_NAME_COLUMN].isin(set(names))]
    write_recording_table(path / SPREADSHEET_NAME, table)

    raw = params.raw_data or ""
    raw_info: dict[str, Any] = {"path": raw, "relative": "", "remote": is_remote_url(raw)}
    if raw and not raw_info["remote"]:
        raw_abs = Path(raw).resolve()
        raw_info["path"] = str(raw_abs)
        try:
            raw_info["relative"] = os.path.relpath(raw_abs, path.resolve())
        except ValueError:      # different drives on Windows
            raw_info["relative"] = ""

    stored = dataclasses.asdict(params)
    # These are decided per machine and per role — see worker_params /
    # final_params — so what the main computer had in them must not leak.
    for key in ("spreadsheet_file_name", "output_data_folder",
                "output_data_folder_name", "continue_interrupted",
                "overwrite_existing_output", "prune_removed_recordings"):
        stored[key] = Params().__getattribute__(key)
    stored["spreadsheet_range"] = _ALL_ROWS

    run = SharedRun(
        name=name, main=sanitize_name(main.name), mode=mode_for_params(params),
        params=stored, raw_data=raw_info, recordings=names, status=GATHERING,
        created_at=utc_now(), meanap_version=meanap_version(),
    )
    ws = Workspace(path)
    ws.write(run)
    main.role = "main"
    main.raw_data = raw
    ws.join(main)
    if log:
        log(f"Shared run created: {path}")
        log(f"  {len(names)} recording(s); the batch is in {SPREADSHEET_NAME}.")
    return ws


def open_workspace(path: Path | str) -> Workspace:
    """A :class:`Workspace` for *path*, which must already hold a run."""
    ws = Workspace(path)
    ws.read()   # validates
    return ws


# ── Splitting the batch ───────────────────────────────────────────────────────

def split_recordings(
    recordings: list[str], weights: dict[str, float],
) -> dict[str, list[str]]:
    """Share *recordings* out in proportion to *weights*, as contiguous runs.

    Largest-remainder rounding, so the counts add up exactly; ties go to the
    machine listed first (the main computer, by convention). A machine with no
    positive weight gets nothing. Contiguous rather than interleaved because
    "desktop: recordings 1–7, laptop: 8–10" is something a person can check
    against the spreadsheet at a glance.
    """
    names = list(weights)
    if not names:
        return {}
    positive = {m: max(float(weights[m] or 0.0), 0.0) for m in names}
    total = sum(positive.values())
    if total <= 0:
        positive = {m: 1.0 for m in names}
        total = float(len(names))
    n = len(recordings)
    exact = {m: n * positive[m] / total for m in names}
    counts = {m: int(math.floor(exact[m])) for m in names}
    leftover = n - sum(counts.values())
    for m in sorted(names, key=lambda m: exact[m] - counts[m], reverse=True)[:leftover]:
        counts[m] += 1

    out: dict[str, list[str]] = {}
    i = 0
    for m in names:
        out[m] = list(recordings[i:i + counts[m]])
        i += counts[m]
    return out


def split_by_score(recordings: list[str], machines: Iterable[MachineRecord],
                   main: str) -> dict[str, list[str]]:
    """The default split: proportional to benchmark score, main computer first.

    A machine without a score counts as average — it joined without
    benchmarking, and guessing it slow would leave it idle, guessing it fast
    would make everyone wait for it.
    """
    machines = list(machines)
    scores = [m.score for m in machines if m.score]
    fallback = sum(scores) / len(scores) if scores else 1.0
    ordered = sorted(machines, key=lambda m: (m.name != main, m.name.lower()))
    return split_recordings(
        recordings, {m.name: (m.score or fallback) for m in ordered})
