"""``meanap`` — run MEA-NAP from a shell.

The GUI is where a run is set up; this is where it is run when there is no
screen to run it on — an HPC node, a server over ssh, a script that analyses
every new plate as it arrives. The two meet at the parameter file: **File →
Save parameters** in the GUI writes the same ``params.json`` every output
folder carries, and ``meanap run`` takes either one.

    meanap run my_params.json                     # one run
    meanap run my_params.json --steps 3-4         # part of one
    meanap run a.json b.json c.json               # a queue, one after another
    meanap run old_output_folder/ --express       # rerun a finished run
    meanap example                                # the GUI's "Test pipeline"
    meanap params new -o my_params.json           # defaults, to edit by hand
    meanap params show my_params.json             # what a file changes

The command-line options cover the settings that change from one run of the
same analysis to the next — where the data is, where results go, which steps.
Anything else is ``--set name=value``, by its :class:`~meanap.params.Params`
field name, so nothing in the parameter file is out of reach.

The other ``meanap-*`` tools are here too, under one name: ``meanap gui``,
``meanap viewer``, ``meanap stats``, ``meanap shared`` and
``meanap preflight`` hand their arguments straight on.
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import json
import signal
import sys
import types
import typing
from pathlib import Path
from typing import Any, Callable

from meanap.params import PARAMS_FILENAME, Params, load_params

#: Exit codes. 130 is what a shell reports for a process stopped by Ctrl-C, so
#: a script checking ``$?`` sees a stopped run the way it would see any other.
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_CANCELLED = 0, 1, 2, 130

#: Subcommands that are other entry points, imported only when used: the GUI
#: pulls in Qt, and a headless node should not need it to run ``meanap run``.
FORWARDED = {
    "gui": ("meanap.gui.app", "the desktop app (same as meanap-gui)"),
    "viewer": ("meanap.viewer.server", "the network viewer (same as meanap-viewer)"),
    "stats": ("meanap.stats.cli", "step 5 on a finished run (same as meanap-stats)"),
    "shared": ("meanap.shared.cli", "split a run across computers (same as meanap-shared)"),
    "preflight": ("meanap.remote.cli", "check a remote data source (same as meanap-preflight)"),
}


class UsageError(ValueError):
    """A problem with what was asked for, reported without a traceback."""


def _log(message: str) -> None:
    print(message, flush=True)


# ── Parameter overrides ──────────────────────────────────────────────────────


def _fields() -> dict[str, dataclasses.Field]:
    return {f.name: f for f in dataclasses.fields(Params)}


def _unknown_field(name: str) -> UsageError:
    close = difflib.get_close_matches(name, _fields(), n=3)
    hint = f" Did you mean {', '.join(close)}?" if close else ""
    return UsageError(f"Params has no setting called '{name}'.{hint}")


def _strip_optional(tp: Any) -> tuple[Any, bool]:
    """``int | None`` → ``(int, True)``; anything else → ``(tp, False)``."""
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0], len(args) < len(typing.get_args(tp))
    return tp, False


def _parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"'{text}' is not true or false")


def _parse_scalar(tp: Any, text: str) -> Any:
    if tp is bool:
        return _parse_bool(text)
    if tp in (int, float):
        return tp(text)
    if tp is str:
        return text
    if typing.get_origin(tp) is typing.Literal:
        allowed = typing.get_args(tp)
        if text not in allowed:
            raise ValueError(f"must be one of {', '.join(map(str, allowed))}")
        return text
    raise TypeError


def coerce_value(name: str, text: str) -> Any:
    """Turn the text after ``name=`` into the type the field holds.

    Typed by the field's annotation rather than guessed from the text, so
    ``--set spreadsheet_range=10`` stays a string and ``--set fs=25000`` is a
    float. Lists take either JSON (``[10, 25]``) or commas (``10,25``); an
    empty value or ``none`` clears an optional field. Anything the annotation
    can't describe simply (dicts, unions) has to be JSON.
    """
    fields = _fields()
    if name not in fields:
        raise _unknown_field(name)
    tp, optional = _strip_optional(fields[name].type)

    try:
        if optional and text.strip().lower() in ("", "none", "null"):
            return None
        origin = typing.get_origin(tp)
        if origin in (list, tuple):
            stripped = text.strip()
            if stripped.startswith("["):
                items = json.loads(stripped)
            else:
                items = [s.strip() for s in stripped.split(",") if s.strip()]
            args = [a for a in typing.get_args(tp) if a is not Ellipsis]
            item_tp = args[0] if args else str
            parsed = [_parse_scalar(item_tp, str(i)) for i in items]
            return tuple(parsed) if origin is tuple else parsed
        try:
            return _parse_scalar(tp, text)
        except TypeError:
            return json.loads(text)
    except (ValueError, json.JSONDecodeError) as e:
        raise UsageError(f"--set {name}={text}: {e}") from e


def parse_assignment(text: str) -> tuple[str, Any]:
    """``"name=value"`` → ``(name, value)``, typed by :func:`coerce_value`."""
    if "=" not in text:
        raise UsageError(f"--set expects name=value, got '{text}'")
    name, _, value = text.partition("=")
    name = name.strip()
    return name, coerce_value(name, value)


def parse_steps(text: str) -> tuple[int, int]:
    """``"2-4"`` → ``(2, 4)``; ``"3"`` → ``(3, 3)``."""
    start, sep, stop = text.partition("-")
    try:
        first = int(start)
        last = int(stop) if sep else first
    except ValueError:
        raise UsageError(f"--steps expects a step or a range like 2-4, got '{text}'")
    if not 1 <= first <= last <= 4:
        raise UsageError(f"--steps must lie within 1-4 with start ≤ stop, got '{text}'")
    return first, last


def apply_overrides(params: Params, args: argparse.Namespace) -> list[str]:
    """Apply the command line to *params*, returning a line per change made.

    The named options first and ``--set`` last, so ``--set`` can always say
    the final word on a field however else it was reached.
    """
    # ``meanap example`` has only some of these options, hence getattr.
    opt = lambda name: getattr(args, name, None)        # noqa: E731
    changes: dict[str, Any] = {}
    if opt("raw_data") is not None:
        changes["raw_data"] = opt("raw_data")
    if opt("spreadsheet") is not None:
        changes["spreadsheet_file_name"] = opt("spreadsheet")
    if opt("output") is not None:
        changes["output_data_folder"] = opt("output")
    if opt("name") is not None:
        changes["output_data_folder_name"] = opt("name")
    if opt("steps") is not None:
        changes["start_analysis_step"], changes["stop_analysis_step"] = parse_steps(opt("steps"))
    if opt("lags") is not None:
        changes["func_con_lag_val"] = coerce_value("func_con_lag_val", opt("lags"))
    if opt("express"):
        changes["express_mode"] = True
    if opt("workers") is not None:
        changes["recording_workers"] = opt("workers")
    if opt("seed") is not None:
        changes["random_seed"] = opt("seed")
    if opt("overwrite"):
        changes["overwrite_existing_output"] = True
    if opt("resume"):
        changes["continue_interrupted"] = True
    if opt("debug"):
        changes["verbose_level"] = "Debug"
    elif opt("verbose"):
        changes["verbose_level"] = "Verbose"
    for assignment in args.set or []:
        name, value = parse_assignment(assignment)
        changes[name] = value

    lines = []
    for name, value in changes.items():
        if getattr(params, name) != value:
            lines.append(f"  {name} = {value!r}")
        setattr(params, name, value)
    return lines


def missing_inputs(params: Params) -> list[str]:
    """What a run needs and doesn't have, named by the option that supplies it.

    The same checks the GUI's Run button makes (``MainWindow._on_run``), in
    command-line terms — run_pipeline itself only finds out about some of
    these several minutes in.
    """
    missing = []
    if not params.raw_data and params.start_analysis_step == 1:
        missing.append("the raw data folder (--raw-data), which step 1 reads")
    if not params.output_data_folder:
        missing.append("an output folder (--output)")
    if not params.spreadsheet_file_name:
        missing.append("the recording spreadsheet (--spreadsheet)")
    if params.prior_analysis and not params.prior_analysis_path:
        missing.append("the previous analysis folder (--set prior_analysis_path=…), "
                       "which prior_analysis needs")
    if (params.start_analysis_step > 1 and not params.prior_analysis
            and not params.spike_detected_data and not params.output_data_folder_name):
        missing.append(
            f"the earlier steps' output: starting at step {params.start_analysis_step} "
            "needs --name (an existing run in --output to continue) or "
            "--set prior_analysis=true --set prior_analysis_path=…")
    return missing


# ── Running ──────────────────────────────────────────────────────────────────


class CtrlC:
    """First Ctrl-C stops at the next checkpoint; a second one stops now.

    The pipeline already polls a cancel flag between recordings (that is how
    the GUI's Stop button works), so the first press goes there and the run
    unwinds cleanly with everything finished so far on disk. A run in the
    middle of a long recording can take a while to reach a checkpoint, hence
    the second press.
    """

    def __init__(self) -> None:
        self.requested = False
        self._previous = None

    def __enter__(self) -> "CtrlC":
        self._previous = signal.signal(signal.SIGINT, self._handle)
        return self

    def __exit__(self, *exc) -> None:
        signal.signal(signal.SIGINT, self._previous)

    def _handle(self, signum, frame) -> None:
        if self.requested:
            raise KeyboardInterrupt
        self.requested = True
        _log("\nStopping at the next checkpoint — press Ctrl-C again to stop now.")

    def __call__(self) -> bool:
        return self.requested


class ProgressPrinter:
    """Print the GUI's progress line, but only when it has moved on.

    Snapshots arrive as each recording finishes. Printing every one is fine on
    a small batch and a wall of near-identical lines on a big one, so a line
    is printed when the phase changes or every 5 % within it.
    """

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
        self._last: tuple[str, int] | None = None

    def __call__(self, snapshot) -> None:
        key = (snapshot.phase, snapshot.percent // 5)
        if key == self._last:
            return
        self._last = key
        _log(f"{self.prefix}[{snapshot.describe()}]")


def resolve_params_path(entry: str) -> Path:
    """A parameter file, a finished run's folder, or its ``.meanap`` bundle.

    The last two carry the ``params.json`` that produced them, so a run can be
    repeated — or redone with a change — from its own results.
    """
    path = Path(entry).expanduser()
    if path.is_dir():
        inner = path / PARAMS_FILENAME
        if not inner.is_file():
            raise UsageError(f"{path} is a folder with no {PARAMS_FILENAME} in it")
        return inner
    if not path.is_file():
        raise UsageError(f"Parameter file not found: {path}")
    return path


def read_params(path: Path) -> tuple[Params, list[str]]:
    """:func:`~meanap.params.load_params`, reaching inside a bundle if need be."""
    from meanap.pipeline.bundle import is_bundle, open_bundle

    if not is_bundle(path):
        return load_params(path)
    with open_bundle(path) as bundle:
        inner = bundle.root / PARAMS_FILENAME
        if not inner.is_file():
            raise ValueError(f"the bundle has no {PARAMS_FILENAME} (made before "
                             "runs recorded their settings)")
        return load_params(inner)


def _load(entry: str, args: argparse.Namespace) -> tuple[Params, Path]:
    path = resolve_params_path(entry)
    try:
        params, unknown = read_params(path)
    except (OSError, ValueError, TypeError) as e:
        raise UsageError(f"Could not read {path}: {e}") from e
    _log(f"Parameters: {path}")
    if unknown:
        _log(f"  note: {len(unknown)} setting(s) not known to this version were "
             f"ignored: {', '.join(unknown[:5])}{' …' if len(unknown) > 5 else ''}")
    changed = apply_overrides(params, args)
    if changed:
        _log("Changed from the file:")
        for line in changed:
            _log(line)
    return params, path


def _check(params: Params, label: str) -> None:
    missing = missing_inputs(params)
    if missing:
        raise UsageError(f"{label} is missing:\n  • " + "\n  • ".join(missing))


def _describe(params: Params) -> str:
    from meanap.gui.modes import MODES, mode_for_params

    bits = [MODES[mode_for_params(params)].label.replace("  ", " "),
            f"steps {params.start_analysis_step}–{params.stop_analysis_step}"]
    if params.express_mode:
        bits.append("express")
    if params.continue_interrupted:
        bits.append("continuing")
    return " · ".join(bits)


def run_one(params: Params, dry_run: bool) -> int:
    from meanap.pipeline.cancellation import PipelineCancelled
    from meanap.pipeline.runner import run_pipeline

    _check(params, "This run")
    _log(f"Run: {_describe(params)}")
    _log(f"  raw data:    {params.raw_data or '(not needed)'}")
    _log(f"  spreadsheet: {params.spreadsheet_file_name}")
    _log(f"  output:      {params.output_data_folder}"
         + (f" / {params.output_data_folder_name}" if params.output_data_folder_name else ""))
    if dry_run:
        _log("Dry run: the settings are complete; nothing was run.")
        return EXIT_OK

    with CtrlC() as stop:
        try:
            output = run_pipeline(params, log=_log, should_cancel=stop,
                                  progress=ProgressPrinter())
        except PipelineCancelled:
            _log("Run stopped. Whatever finished is in the output folder; "
                 "rerun with --resume to carry on from there.")
            return EXIT_CANCELLED
        except Exception as e:                            # noqa: BLE001
            # The traceback is for a bug report, not for a missing file.
            if params.verbose_level == "Debug":
                import traceback
                traceback.print_exc()
            _log(f"Run FAILED: {e}")
            return EXIT_FAILED
    _log(f"Done → {Path(output).resolve()}")
    return EXIT_OK


def run_many(runs: list[tuple[Params, Path]], dry_run: bool) -> int:
    from meanap.pipeline.queue import QueuedRun, run_queue

    queued = [QueuedRun(params=p, source=path) for p, path in runs]
    # Checked in full before the first starts, as the GUI's queue does: a
    # missing path in run five should be found now, not after runs one to four.
    for i, run in enumerate(queued, start=1):
        _check(run.params, f"Run {i} ({run.label})")
    if dry_run:
        for i, run in enumerate(queued, start=1):
            _log(f"  {i}. {run.label}: {_describe(run.params)}")
        _log(f"Dry run: all {len(queued)} runs are complete; nothing was run.")
        return EXIT_OK

    printers: dict[int, ProgressPrinter] = {}

    def progress(index: int, run: QueuedRun, snapshot) -> None:
        printer = printers.setdefault(
            index, ProgressPrinter(prefix=f"run {index + 1}/{len(queued)} "))
        printer(snapshot)

    with CtrlC() as stop:
        result = run_queue(queued, log=_log, should_cancel=stop, progress=progress)
    if result.cancelled or stop.requested:
        return EXIT_CANCELLED
    return EXIT_FAILED if result.failed else EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    if len(args.params) > 1 and args.name is not None:
        raise UsageError("--name names one output folder, so it can't be given "
                         "with several parameter files")
    runs = [_load(entry, args) for entry in args.params]
    if len(runs) == 1:
        return run_one(runs[0][0], args.dry_run)
    return run_many(runs, args.dry_run)


def cmd_example(args: argparse.Namespace) -> int:
    """The GUI's Test pipeline button: fetch the example data and run it."""
    from meanap.pipeline.example_data import download_example_data
    from meanap.pipeline.spreadsheet import read_recording_csv

    params = Params()
    args.output = args.output or str(Path.home() / "MEA-NAP")

    _log(f"Example data → {Path(args.output) / 'ExampleData'}")
    if not args.dry_run:
        example_dir = download_example_data(Path(args.output), log=_log)
    else:
        example_dir = Path(args.output) / "ExampleData"

    # The settings the GUI's button applies (and MATLAB's TestPipelineButton).
    params.raw_data = str(example_dir)
    params.spreadsheet_file_name = str(example_dir / "exampleData.csv")
    params.spreadsheet_range = "A2:A3"
    params.start_analysis_step, params.stop_analysis_step = 1, 4
    if not args.dry_run:
        recordings = read_recording_csv(example_dir / "exampleData.csv", "A2:A3")
        params.custom_grp_order = list(dict.fromkeys(r.group for r in recordings))
    for line in apply_overrides(params, args):
        _log(line)
    return run_one(params, args.dry_run)


def cmd_params_new(args: argparse.Namespace) -> int:
    from meanap.gui.modes import MODES, apply_mode_to_params

    out = Path(args.out).expanduser()
    if out.exists() and not args.force:
        raise UsageError(f"{out} already exists (use --force to replace it)")
    params = Params()
    apply_mode_to_params(args.mode, params)
    params.func_con_lag_val = list(MODES[args.mode].default_lags)
    for assignment in args.set or []:
        name, value = parse_assignment(assignment)
        setattr(params, name, value)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Without the version stamp save_params adds: this is a template to edit,
    # not the record of a run, and is what the GUI's Save parameters writes.
    with open(out, "w") as fh:
        json.dump(dataclasses.asdict(params), fh, indent=2)
    _log(f"Wrote {out} ({MODES[args.mode].label.replace('  ', ' ')} defaults). "
         "Edit it, or open it in the GUI, then: meanap run " + str(out))
    return EXIT_OK


def cmd_params_show(args: argparse.Namespace) -> int:
    from meanap.params_summary import summarise_params

    path = resolve_params_path(args.file)
    try:
        params, unknown = read_params(path)
    except (OSError, ValueError, TypeError) as e:
        raise UsageError(f"Could not read {path}: {e}") from e
    summary = summarise_params(params)
    _log(f"{path}: {summary.changed} of {summary.total} settings differ from the defaults"
         + ("" if args.all else " (--all to list every setting)"))
    for group in summary.groups:
        entries = group.entries if args.all else [e for e in group.entries if e.changed]
        if not entries:
            continue
        _log(f"\n{group.name}")
        width = max(len(e.name) for e in entries)
        for e in entries:
            mark = "*" if e.changed else " "
            _log(f" {mark} {e.name:<{width}}  {e.value!r}")
    if unknown:
        _log(f"\nNot known to this version (ignored): {', '.join(unknown)}")
    return EXIT_OK


def cmd_version(args: argparse.Namespace) -> int:
    from meanap.version import PIPELINE_NAMES, all_versions, build_label

    for key, number in all_versions().items():
        _log(f"{PIPELINE_NAMES[key]:<9} {number}")
    label = build_label()
    if label:
        _log(f"build     {label}")
    return EXIT_OK


# ── Parser ───────────────────────────────────────────────────────────────────


def _add_run_options(p: argparse.ArgumentParser, *, example: bool = False) -> None:
    where = p.add_argument_group("data and output")
    if not example:
        where.add_argument("--raw-data", help="folder of raw recordings, or a remote share link")
        where.add_argument("--spreadsheet", help="the recording spreadsheet (.csv/.xlsx)")
    where.add_argument("-o", "--output", help="folder the run's output folder is created in"
                       + (" (default: ~/MEA-NAP)" if example else ""))
    if not example:
        where.add_argument("--name", help="name of the output folder; an existing "
                           "one is continued or (with --overwrite) replaced")
    where.add_argument("--overwrite", action="store_true",
                       help="replace an existing output folder of the same name")

    what = p.add_argument_group("what to run")
    if not example:
        what.add_argument("--steps", help="a step or a range, e.g. 1-4 (default: the file's)")
        what.add_argument("--lags", help="STTC lags in ms, e.g. 10,25,50")
        what.add_argument("--resume", action="store_true",
                          help="continue an interrupted run, skipping finished recordings")
    what.add_argument("--express", action="store_true",
                      help="save the data and a .meanap bundle, not every figure")
    what.add_argument("--set", action="append", metavar="NAME=VALUE",
                      help="any Params field, e.g. --set spikes_method=thr4 "
                           "(repeatable; see `meanap params show --all`)")

    how = p.add_argument_group("how")
    how.add_argument("--workers", type=int,
                     help="recordings processed at once (default: sized to CPU and RAM)")
    how.add_argument("--seed", type=int, help="random seed, for a reproducible run")
    how.add_argument("-v", "--verbose", action="store_true", help="more detail in the log")
    how.add_argument("--debug", action="store_true", help="everything, for a bug report")
    how.add_argument("-n", "--dry-run", action="store_true",
                     help="check the settings and say what would run, without running it")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meanap",
        description="Run MEA-NAP from the command line.",
        epilog="Set a run up in the GUI, save its parameters (File → Save "
               "parameters), and run the file here — on this computer or any other.",
    )
    parser.add_argument("--version", action="store_true", help="print the versions and exit")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("run", help="run the pipeline from a parameter file",
                       description="Run the pipeline from saved parameters. Several "
                                   "files run one after another, like the GUI's queue; "
                                   "one failing doesn't stop the rest.")
    p.add_argument("params", nargs="+",
                   help="params .json saved from the GUI, or a finished run's "
                        "output folder or .meanap bundle")
    _add_run_options(p)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("example", help="download the example data and run steps 1-4",
                       description="The GUI's Test pipeline button: fetches the two "
                                   "example recordings and runs the full pipeline on them.")
    _add_run_options(p, example=True)
    p.set_defaults(fn=cmd_example)

    p = sub.add_parser("params", help="write or inspect a parameter file")
    psub = p.add_subparsers(dest="params_command", metavar="ACTION", required=True)
    q = psub.add_parser("new", help="write a parameter file of defaults")
    q.add_argument("-o", "--out", default="meanap_params.json",
                   help="where to write it (default: meanap_params.json)")
    q.add_argument("--mode", choices=["meanap", "meastim", "catnap"], default="meanap",
                   help="which pipeline's defaults (default: meanap)")
    q.add_argument("--set", action="append", metavar="NAME=VALUE",
                   help="set a field as it is written (repeatable)")
    q.add_argument("--force", action="store_true", help="replace an existing file")
    q.set_defaults(fn=cmd_params_new)
    q = psub.add_parser("show", help="list the settings a file changes from the defaults")
    q.add_argument("file", help="params .json, or a run's output folder or .meanap bundle")
    q.add_argument("--all", action="store_true", help="list every setting, not just changed ones")
    q.set_defaults(fn=cmd_params_show)

    sub.add_parser("version", help="print the versions").set_defaults(fn=cmd_version)

    for name, (_, help_text) in FORWARDED.items():
        # Parsed by the tool itself; listed here so `meanap -h` shows them.
        sub.add_parser(name, help=help_text, add_help=False)
    return parser


def _forward(name: str, argv: list[str]) -> int:
    import importlib

    module = importlib.import_module(FORWARDED[name][0])
    # Each tool parses sys.argv itself (some take no argv parameter), so it is
    # handed the arguments the way it would have received them as meanap-<name>.
    sys.argv = [f"meanap {name}", *argv]
    result = module.main()
    return result if isinstance(result, int) else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in FORWARDED:
        return _forward(argv[0], argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        return cmd_version(args)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.fn(args)
    except UsageError as e:
        _log(f"error: {e}")
        return EXIT_USAGE
    except KeyboardInterrupt:
        _log("Stopped.")
        return EXIT_CANCELLED


if __name__ == "__main__":
    sys.exit(main())
