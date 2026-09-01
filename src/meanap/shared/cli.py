"""``meanap-shared`` — take part in a shared run from a terminal.

The GUI walks through all of this; the command exists for the computer that
has no screen attached (a lab workstation reached over SSH) and for scripts.

::

    meanap-shared benchmark
    meanap-shared create  --params run.json --shared-folder ~/Dropbox/MEA-NAP --name Run1
    meanap-shared join    ~/Dropbox/MEA-NAP/Run1.meanap-shared [--name laptop] [--raw-data DIR]
    meanap-shared start   ~/Dropbox/MEA-NAP/Run1.meanap-shared
    meanap-shared main    ~/Dropbox/MEA-NAP/Run1.meanap-shared --output-folder ~/MEA-NAP --output-name Run1
    meanap-shared status  ~/Dropbox/MEA-NAP/Run1.meanap-shared

``join`` blocks until the run starts and this machine's share is done;
``main`` runs the main computer's whole sequence, including the wait.
Ctrl-C stops either cleanly, recording *stopped* in the shared folder.
"""

from __future__ import annotations

import argparse
import signal
import sys

from meanap.pipeline.cancellation import PipelineCancelled
from meanap.shared.workspace import (
    MachineRecord, create_workspace, default_machine_name,
    open_workspace, split_by_score,
)


def _log(message: str) -> None:
    print(message, flush=True)


def _cancel_on_sigint():
    """A ``should_cancel`` that flips on Ctrl-C, so the pipeline unwinds at its
    next checkpoint rather than dying mid-write."""
    flag = {"stop": False}

    def handler(_sig, _frame):
        if flag["stop"]:
            raise KeyboardInterrupt      # second Ctrl-C: really stop
        flag["stop"] = True
        _log("\nStop requested — finishing the current recording, then halting…")

    signal.signal(signal.SIGINT, handler)
    return lambda: flag["stop"]


def _benchmark(record: MachineRecord, skip: bool) -> MachineRecord:
    if skip:
        return record
    from meanap.shared.benchmark import run_benchmark

    result = run_benchmark(log=_log)
    record.benchmark_seconds = result.seconds
    record.score = result.score
    return record


def cmd_benchmark(args) -> int:
    from meanap.shared.benchmark import run_benchmark

    run_benchmark(log=_log)
    return 0


def cmd_create(args) -> int:
    from meanap.params import load_params

    params, unknown = load_params(args.params)
    if unknown:
        _log(f"Ignoring unknown parameter(s) in {args.params}: {', '.join(unknown)}")
    record = _benchmark(
        MachineRecord.for_this_machine(args.machine or default_machine_name(), "main"),
        args.no_benchmark)
    ws = create_workspace(args.shared_folder, args.name, params, record, log=_log)
    _log("On each helper computer, run:")
    _log(f"  meanap-shared join \"{ws.path}\"")
    _log("then, back here, once they have joined:")
    _log(f"  meanap-shared start \"{ws.path}\"")
    _log(f"  meanap-shared main \"{ws.path}\" --output-folder <folder> --output-name {args.name}")
    return 0


def cmd_join(args) -> int:
    from meanap.shared.roles import run_helper

    ws = open_workspace(args.workspace)
    run = ws.read()
    record = _benchmark(
        MachineRecord.for_this_machine(args.name or default_machine_name()),
        args.no_benchmark)
    raw = args.raw_data or ws.resolve_raw_data(run)
    if raw is None and run.params.get("start_analysis_step", 1) == 1:
        _log("The raw recordings were not found on this computer. Pass their "
             "folder with --raw-data.")
        return 2
    record.raw_data = raw or ""
    record = ws.join(record)
    _log(f"Joined as '{record.name}'.")
    try:
        run_helper(ws, record.name, raw_data=raw, log=_log,
                   should_cancel=_cancel_on_sigint())
    except PipelineCancelled:
        _log("Stopped.")
        return 130
    return 0


def cmd_start(args) -> int:
    ws = open_workspace(args.workspace)
    run = ws.read()
    if run.started:
        _log("Already started.")
        return 0
    machines = ws.machines()
    assignment = split_by_score(run.recordings, machines, run.main)
    for name, recs in assignment.items():
        _log(f"  {name}: {len(recs)} recording(s)")
    ws.start(assignment)
    _log("Started.")
    return 0


def cmd_main(args) -> int:
    from meanap.shared.roles import run_main

    ws = open_workspace(args.workspace)
    run = ws.read()
    if not run.started:
        _log("Not started yet — run `meanap-shared start` first.")
        return 2
    try:
        root = run_main(ws, run.main, output_data_folder=args.output_folder,
                        output_data_folder_name=args.output_name or run.name,
                        raw_data=args.raw_data, log=_log,
                        should_cancel=_cancel_on_sigint())
    except PipelineCancelled:
        _log("Stopped.")
        return 130
    _log(str(root))
    return 0


def cmd_status(args) -> int:
    ws = open_workspace(args.workspace)
    for line in ws.describe():
        _log(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="meanap-shared", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("benchmark", help="time this computer").set_defaults(fn=cmd_benchmark)

    p = sub.add_parser("create", help="set up a shared run from a saved parameter file")
    p.add_argument("--params", required=True, help="a params .json saved from the GUI")
    p.add_argument("--shared-folder", required=True)
    p.add_argument("--name", required=True, help="the run's name")
    p.add_argument("--machine", help="this computer's name (default: hostname)")
    p.add_argument("--no-benchmark", action="store_true")
    p.set_defaults(fn=cmd_create)

    p = sub.add_parser("join", help="take part as a helper")
    p.add_argument("workspace", help="the <name>.meanap-shared folder")
    p.add_argument("--name", help="this computer's name (default: hostname)")
    p.add_argument("--raw-data", help="where the raw recordings are on this computer")
    p.add_argument("--no-benchmark", action="store_true")
    p.set_defaults(fn=cmd_join)

    p = sub.add_parser("start", help="split the batch among the machines that have joined")
    p.add_argument("workspace")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("main", help="run the main computer's part and pool the results")
    p.add_argument("workspace")
    p.add_argument("--output-folder", required=True)
    p.add_argument("--output-name", help="default: the run's name")
    p.add_argument("--raw-data")
    p.set_defaults(fn=cmd_main)

    p = sub.add_parser("status", help="who has joined and how far they are")
    p.add_argument("workspace")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ValueError as e:
        _log(f"error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
