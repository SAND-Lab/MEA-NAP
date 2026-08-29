"""What each computer does in a shared run, from joining to done.

Two roles. A **helper** waits until the main computer has started the run,
analyses the recordings it was given into its own corner of the shared
folder, and reports progress there as it goes. The **main computer** does
the same for its own share, then waits for the helpers, pools every part into
one output folder (:mod:`meanap.shared.merge`) and runs the batch-wide work
over all of it.

Both are ordinary calls to :func:`~meanap.pipeline.runner.run_pipeline` on
parameters the workspace derives; the only thing new here is the waiting,
and the waiting is deliberately dumb: read the other machines' progress files
every few seconds and stop when they all say they are done. There is no
timeout — a laptop that went to sleep will wake and carry on, and the person
at the main computer can see who is late and press *finish now* instead,
which does the missing recordings locally and pools whatever did arrive.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from meanap.params import Params
from meanap.pipeline.cancellation import PipelineCancelled, check_cancel
from meanap.pipeline.progress import Progress
from meanap.pipeline.runner import run_pipeline
from meanap.shared.merge import merge_outputs
from meanap.shared.workspace import (
    CANCELLED, DONE, FAILED, FINISHED, RUNNING, STOPPED, WAITING, WORKING,
    MachineRecord, ProgressRecord, SharedRun, Workspace,
)

__all__ = ["run_helper", "run_main", "MachineView", "machine_views"]

LogFn = Callable[[str], None]
CancelFn = Callable[[], bool] | None
ProgressFn = Callable[[Progress], None] | None

#: How often the shared folder is re-read while waiting. Sync services take
#: seconds to propagate a file, so anything much faster only burns disk.
DEFAULT_POLL_S = 5.0
#: A running machine that has not written progress for this long is called
#: out in the log — once — as possibly asleep or offline.
STALE_AFTER_S = 10 * 60
#: How often the progress file is rewritten during a run, at most.
PROGRESS_EVERY_S = 3.0


class MachineView:
    """One row of "who is doing what": a machine and its latest progress."""

    def __init__(self, machine: MachineRecord, progress: ProgressRecord | None,
                 assigned: int) -> None:
        self.machine = machine
        self.progress = progress
        self.assigned = assigned

    @property
    def status(self) -> str:
        return self.progress.status if self.progress else WAITING

    @property
    def finished(self) -> bool:
        return bool(self.progress and self.progress.finished)

    def describe(self) -> str:
        m, p = self.machine, self.progress
        text = f"{m.name}: {self.status}"
        if p is not None and p.status == WORKING:
            text += f" {p.fraction * 100:.0f}%"
            if p.detail:
                text += f" · {p.detail}"
        if p is not None and p.status == FAILED and p.error:
            text += f" — {p.error}"
        return text


def machine_views(ws: Workspace, run: SharedRun | None = None) -> list[MachineView]:
    run = run or ws.read()
    return [MachineView(m, ws.read_progress(m.name), len(run.assigned_to(m.name)))
            for m in ws.machines()]


# ── Shared plumbing ───────────────────────────────────────────────────────────

class _PartReporter:
    """Turns the pipeline's progress callback into the machine's progress file
    — throttled, because the file is on a syncing folder — and forwards each
    snapshot to the caller's own callback."""

    def __init__(self, ws: Workspace, name: str, assigned: int,
                 forward: ProgressFn, every_s: float = PROGRESS_EVERY_S) -> None:
        self.ws, self.name, self.assigned = ws, name, assigned
        self.forward = forward
        self.every_s = every_s
        self._last_write = 0.0
        self._last_phase = ""

    def __call__(self, snapshot: Progress) -> None:
        if self.forward is not None:
            self.forward(snapshot)
        now = time.monotonic()
        changed = snapshot.phase != self._last_phase
        if not changed and now - self._last_write < self.every_s:
            return
        self._last_write, self._last_phase = now, snapshot.phase
        self._write(WORKING, snapshot)

    def _write(self, status: str, snapshot: Progress | None = None,
               error: str = "") -> None:
        record = ProgressRecord(status=status, recordings=self.assigned, error=error)
        if snapshot is not None:
            record.phase = snapshot.phase
            record.detail = snapshot.detail
            record.fraction = snapshot.fraction
            record.elapsed_s = snapshot.elapsed_s
            record.eta_s = snapshot.eta_s
        elif status == FINISHED:
            record.fraction = 1.0
        try:
            self.ws.write_progress(self.name, record)
        except OSError:
            # Progress is advisory; the results are what matter, and they
            # are written by the pipeline with its own retries.
            pass


def _run_part(
    ws: Workspace, name: str, params: Params, *, assigned: int,
    log: LogFn, should_cancel: CancelFn, progress: ProgressFn,
    watch_manifest: bool = True,
) -> Path:
    """One machine's share, with its progress file kept current throughout.

    Also stops when the main computer cancels the run (the manifest flips to
    *cancelled*) — checked at most every few seconds, on the pipeline's own
    cancellation checkpoints, so a helper is not left grinding through
    recordings nobody will collect.
    """
    reporter = _PartReporter(ws, name, assigned, progress)
    last_check = {"at": 0.0, "cancelled": False}

    def cancelled() -> bool:
        if should_cancel is not None and should_cancel():
            return True
        if not watch_manifest:
            return False
        now = time.monotonic()
        if now - last_check["at"] > DEFAULT_POLL_S:
            last_check["at"] = now
            try:
                last_check["cancelled"] = ws.read().status == CANCELLED
            except ValueError:
                pass
        return last_check["cancelled"]

    reporter._write(WORKING)
    try:
        root = run_pipeline(params, log=log, should_cancel=cancelled, progress=reporter)
    except PipelineCancelled:
        reporter._write(STOPPED)
        raise
    except Exception as e:                                   # noqa: BLE001
        reporter._write(FAILED, error=str(e))
        raise
    reporter._write(FINISHED)
    return root


def _sleep(seconds: float, should_cancel: CancelFn) -> None:
    """Wait, but notice a Stop within a fraction of a second."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        check_cancel(should_cancel)
        time.sleep(min(0.25, max(0.0, end - time.monotonic())))


# ── Helper ────────────────────────────────────────────────────────────────────

def run_helper(
    ws: Workspace, name: str, *,
    raw_data: str | None = None,
    log: LogFn = print,
    should_cancel: CancelFn = None,
    progress: ProgressFn = None,
    poll_s: float = DEFAULT_POLL_S,
) -> str:
    """Take part as a helper. Returns the machine's final status.

    Blocks until the main computer starts the run, does this machine's share,
    and returns. Raises :class:`PipelineCancelled` if stopped from this end;
    a cancel from the main computer's end returns :data:`STOPPED` instead,
    since nothing here went wrong.
    """
    run = ws.read()
    log(f"Joined shared run '{run.name}' as '{name}'.")
    if run.status == CANCELLED:
        log("This run was cancelled by the main computer.")
        return STOPPED
    if run.status == DONE:
        log("This run has already finished.")
        return FINISHED
    if not run.started:
        ws.write_progress(name, ProgressRecord(status=WAITING))
        log(f"Waiting for '{run.main}' to start the run… (this window can stay "
            "open; it will begin on its own)")
        while not run.started:
            try:
                _sleep(poll_s, should_cancel)
            except PipelineCancelled:
                ws.write_progress(name, ProgressRecord(status=STOPPED))
                raise
            try:
                run = ws.read()
            except ValueError:
                continue    # mid-sync; try again next tick
            if run.status == CANCELLED:
                log("The main computer cancelled the run before it started.")
                ws.write_progress(name, ProgressRecord(status=STOPPED))
                return STOPPED

    mine = run.assigned_to(name)
    if not mine:
        log("The run started without a share for this computer (it joined after "
            "the split was made). Nothing to do here.")
        ws.write_progress(name, ProgressRecord(status=FINISHED, fraction=1.0))
        return FINISHED

    log(f"This computer's share: {len(mine)} of {len(run.recordings)} recording(s).")
    if raw_data is None:
        raw_data = ws.resolve_raw_data(run)
    if raw_data:
        log(f"Raw data: {raw_data}")
    params = ws.worker_params(name, raw_data=raw_data, run=run)
    if not params.raw_data and params.start_analysis_step == 1:
        ws.write_progress(name, ProgressRecord(
            status=FAILED, recordings=len(mine),
            error="raw data folder not found on this computer"))
        raise ValueError(
            "The raw recordings could not be found on this computer. Give their "
            "location when joining (or put them in the shared folder).")

    _run_part(ws, name, params, assigned=len(mine), log=log,
              should_cancel=should_cancel, progress=progress)
    log(f"\nThis computer's share is done — {len(mine)} recording(s) are in the "
        f"shared folder. '{run.main}' will collect them; this window can be closed.")
    return FINISHED


# ── Main computer ─────────────────────────────────────────────────────────────

def run_main(
    ws: Workspace, name: str, *,
    output_data_folder: str | Path,
    output_data_folder_name: str,
    raw_data: str | None = None,
    log: LogFn = print,
    should_cancel: CancelFn = None,
    progress: ProgressFn = None,
    finish_now: Callable[[], bool] | None = None,
    on_machines: Callable[[list[MachineView]], None] | None = None,
    poll_s: float = DEFAULT_POLL_S,
) -> Path:
    """Take part as the main computer, and end with the pooled output folder.

    The run must already have been started (:meth:`Workspace.start`). Steps:
    this machine's own share; wait for every helper to finish, unless
    *finish_now* says to stop waiting; merge every part that exists into
    ``<output_data_folder>/<output_data_folder_name>``; run the batch-wide
    work there. Whatever a late or failed helper did not finish is computed
    in that last step, so the result is complete either way.
    """
    run = ws.read()
    if run.status != RUNNING or not run.assignment:
        raise ValueError("The shared run has not been started (no split has been made).")
    if raw_data is None:
        raw_data = ws.resolve_raw_data(run)

    final_root = Path(output_data_folder) / output_data_folder_name
    if run.final_output and Path(run.final_output) != final_root:
        log(f"Note: this run was previously pooling into {run.final_output}; "
            f"now pooling into {final_root}.")
    run.final_output = str(final_root)
    ws.write(run)

    mine = run.assigned_to(name)
    helpers = [m for m in run.assignment if m != name]
    log(f"Shared run '{run.name}': {len(run.recordings)} recording(s) across "
        f"{len(run.assignment)} computer(s).")
    for m, recs in run.assignment.items():
        log(f"  {m}{' (this computer)' if m == name else ''}: {len(recs)}")

    # ── 1. Own share ─────────────────────────────────────────────────────────
    if mine:
        log(f"\n=== This computer's share ({len(mine)} recording(s)) ===")
        _run_part(ws, name, ws.worker_params(name, raw_data=raw_data, run=run),
                  assigned=len(mine), log=log, should_cancel=should_cancel,
                  progress=progress, watch_manifest=False)
    else:
        ws.write_progress(name, ProgressRecord(status=FINISHED, fraction=1.0))

    # ── 2. Wait for the helpers ──────────────────────────────────────────────
    if helpers:
        log(f"\n=== Waiting for {', '.join(helpers)} ===")
        _wait_for_helpers(ws, helpers, log=log, should_cancel=should_cancel,
                          finish_now=finish_now, on_machines=on_machines,
                          poll_s=poll_s)

    # ── 3. Pool the parts ────────────────────────────────────────────────────
    check_cancel(should_cancel)
    log(f"\n=== Pooling results into {final_root} ===")
    sources = []
    for m in run.assignment:
        part = ws.part_results(m)
        if part is None:
            log(f"  {m}: nothing to pool yet")
        else:
            sources.append(part)
    report = merge_outputs(sources, final_root, log=log)
    missing = sorted(set(run.recordings) - report.recordings)
    if missing:
        log(f"  {len(missing)} recording(s) have no results yet and will be "
            f"analysed here: {', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}")

    # ── 4. Batch-wide work over everything ───────────────────────────────────
    check_cancel(should_cancel)
    log("\n=== Pooled analysis over the whole batch ===")
    final = ws.final_params(output_data_folder, output_data_folder_name,
                            raw_data=raw_data, run=run)
    if missing and not final.raw_data and final.start_analysis_step == 1:
        raise ValueError(
            "Some recordings still need step 1, and the raw data folder could "
            "not be found on this computer.")
    try:
        root = run_pipeline(final, log=log, should_cancel=should_cancel, progress=progress)
    except PipelineCancelled:
        raise
    except Exception:
        # Left as *running* on purpose: the parts are intact and a retry pools
        # them again without the helpers having to do anything.
        raise
    ws.set_status(DONE)
    log(f"\nShared run finished. Pooled output: {root}")
    return root


def _wait_for_helpers(
    ws: Workspace, helpers: list[str], *, log: LogFn, should_cancel: CancelFn,
    finish_now: Callable[[], bool] | None, on_machines, poll_s: float,
) -> None:
    last_status: dict[str, str] = {}
    warned_stale: set[str] = set()
    last_summary = 0.0
    while True:
        try:
            run = ws.read()
        except ValueError:
            run = None
        views = machine_views(ws, run) if run else []
        if on_machines is not None:
            on_machines(views)
        by_name = {v.machine.name: v for v in views}

        pending: list[str] = []
        for h in helpers:
            view = by_name.get(h)
            status = view.status if view else WAITING
            if last_status.get(h) != status:
                last_status[h] = status
                log(f"  {view.describe() if view else f'{h}: {status}'}")
            if view is None or not view.finished:
                pending.append(h)
            if (view is not None and view.progress is not None
                    and view.status in (WORKING, WAITING) and h not in warned_stale):
                age = view.progress.age_s()
                if age is not None and age > STALE_AFTER_S:
                    warned_stale.add(h)
                    log(f"  ! No news from {h} for {age / 60:.0f} min — it may be "
                        "asleep, offline, or not syncing. Its recordings will "
                        "be analysed here if you choose to finish now.")
        if not pending:
            log("  Every computer has finished its share.")
            return
        if finish_now is not None and finish_now():
            log(f"  Finishing now — {', '.join(pending)} still had work; whatever "
                "they have not done will be analysed here.")
            return
        now = time.monotonic()
        if now - last_summary > 60:
            last_summary = now
            working = [by_name[h].describe() for h in pending if h in by_name]
            if working:
                log("  still waiting: " + "; ".join(working))
        _sleep(poll_s, should_cancel)
