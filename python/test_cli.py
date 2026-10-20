"""Test the ``meanap`` command line.

Run from the repo root::

    uv run python python/test_cli.py

The claim is that ``meanap run params.json`` does what the GUI's Run button
does with the same file — the same output, number for number — and that what
the command line adds on top (overrides, a queue, Ctrl-C) behaves.

Checked here:

  - ``--set`` values are typed by the Params field, not guessed from the text,
    and a misspelt field name is refused with a suggestion;
  - the named options and ``--set`` land on the right fields, ``--set`` last;
  - the missing-input checks the GUI makes before a run;
  - ``params new`` / ``params show``, and a run's output folder accepted in
    place of its parameter file;
  - Ctrl-C: once asks the pipeline to stop, twice stops now;
  - end to end, in a *separate process*: ``meanap run`` against
    ``run_pipeline`` on the same parameters; a queue of two with one broken
    run; exit codes.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from meanap import cli  # noqa: E402
from meanap.params import Params, load_params  # noqa: E402
from meanap.pipeline.io import save_spike_times_npz  # noqa: E402
from meanap.pipeline.runner import run_pipeline  # noqa: E402

Check = tuple[str, bool, str]

RECS = ["rec_a", "rec_b", "rec_c"]
N_CH, FS, LAG = 12, 25000.0, 10
SRC = Path(__file__).resolve().parents[1] / "src"


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


def _raises(fn, exc=cli.UsageError) -> tuple[bool, str]:
    try:
        fn()
    except exc as e:
        return True, str(e)
    return False, "did not raise"


def _args(*argv: str):
    return cli.build_parser().parse_args(["run", "unused.json", *argv])


def _meanap(*argv: str, timeout: float = 600) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run([sys.executable, "-m", "meanap.cli", *argv],
                          capture_output=True, text=True, env=env, timeout=timeout)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _write_sheet(path: Path) -> Path:
    pd.DataFrame([{"Recording Filename": r, "DIV group": 21,
                   "Genotype": "WT" if i % 2 else "KO"}
                  for i, r in enumerate(RECS)]).to_csv(path, index=False)
    return path


def _seed_spikes(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i, rec in enumerate(RECS):
        rng = np.random.default_rng(i)
        spikes = {ch: {"bior1p5": np.sort(rng.uniform(0, 60, 80 + ch))}
                  for ch in range(N_CH)}
        save_spike_times_npz(folder / f"{rec}_spikes.npz", spikes,
                             np.arange(1, N_CH + 1), FS, duration_s=60.0)


def _params(tmp: Path, sheet: Path, spikes: Path, name: str) -> Params:
    """Steps 3–4 from pre-detected spikes, seeded, so two runs can be compared."""
    return Params(
        raw_data="", spreadsheet_file_name=str(sheet), spreadsheet_range="2:100",
        spike_detected_data=str(spikes),
        output_data_folder=str(tmp / "out"), output_data_folder_name=name,
        start_analysis_step=3, stop_analysis_step=4,
        func_con_lag_val=[LAG], prob_thresh_rep_num=20, channel_layout="MCS60",
        min_number_of_nodes_to_cal_net_met=2, random_seed=5,
        recording_workers=1, express_mode=True,
    )


def _save(params: Params, path: Path) -> Path:
    """As the GUI's File → Save parameters writes it."""
    import dataclasses

    path.write_text(json.dumps(dataclasses.asdict(params), indent=2))
    return path


def _table(root: Path) -> pd.DataFrame:
    from meanap.pipeline.bundle import is_bundle, open_bundle

    rel = Path("4_NetworkActivity") / "NetworkActivity_RecordingLevel.csv"
    if is_bundle(root):
        with open_bundle(root) as b:
            df = pd.read_csv(b.root / rel)
    else:
        df = pd.read_csv(root / rel)
    return df.sort_values(df.columns[0]).reset_index(drop=True)


def _output_of(stdout: str) -> Path | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith("Done → "):
            return Path(line[len("Done → "):].strip())
    return None


# ── Typed --set ───────────────────────────────────────────────────────────────

def _coerce_checks() -> list[Check]:
    c = cli.coerce_value
    checks: list[Check] = [
        ("a float field takes a number", c("fs", "20000") == 20000.0
         and isinstance(c("fs", "20000"), float), repr(c("fs", "20000"))),
        ("a str field keeps digits as text", c("spreadsheet_range", "10") == "10", ""),
        ("bools take true/false/yes/0",
         [c("express_mode", v) for v in ("true", "False", "yes", "0")]
         == [True, False, True, False], ""),
        ("int lists take commas", c("func_con_lag_val", "10, 25,50") == [10, 25, 50],
         repr(c("func_con_lag_val", "10, 25,50"))),
        ("int lists take JSON", c("func_con_lag_val", "[5, 15]") == [5, 15], ""),
        ("str lists take commas", c("custom_grp_order", "KO,WT") == ["KO", "WT"], ""),
        ("an optional field clears with 'none'", c("random_seed", "none") is None, ""),
        ("an optional int is an int", c("random_seed", "7") == 7, ""),
    ]
    ok, msg = _raises(lambda: c("spike_method", "thr4"))
    checks.append(("a misspelt field is refused, with the right name suggested",
                   ok and "spikes_method" in msg, msg))
    ok, msg = _raises(lambda: c("fs", "fast"))
    checks.append(("a bad number names the setting", ok and "fs" in msg, msg))
    ok, msg = _raises(lambda: c("express_mode", "maybe"))
    checks.append(("a bad bool is refused", ok, msg))
    ok, msg = _raises(lambda: cli.parse_assignment("fs"))
    checks.append(("--set without '=' is refused", ok, msg))
    checks.append(("--steps 2-4 and --steps 3",
                   cli.parse_steps("2-4") == (2, 4) and cli.parse_steps("3") == (3, 3), ""))
    for bad in ("4-2", "0-3", "1-5", "x"):
        ok, msg = _raises(lambda b=bad: cli.parse_steps(b))
        checks.append((f"--steps {bad} is refused", ok, msg))
    return checks


# ── Overrides and checks ──────────────────────────────────────────────────────

def _override_checks() -> list[Check]:
    checks: list[Check] = []
    p = Params()
    changed = cli.apply_overrides(p, _args(
        "--raw-data", "/data", "--spreadsheet", "s.csv", "-o", "/out", "--name", "Run1",
        "--steps", "2-3", "--lags", "10,25", "--express", "--workers", "2",
        "--seed", "3", "--verbose", "--set", "spikes_method=thr4"))
    checks.append(("each option lands on its field", (
        p.raw_data, p.spreadsheet_file_name, p.output_data_folder, p.output_data_folder_name,
        p.start_analysis_step, p.stop_analysis_step, p.func_con_lag_val, p.express_mode,
        p.recording_workers, p.random_seed, p.verbose_level, p.spikes_method,
    ) == ("/data", "s.csv", "/out", "Run1", 2, 3, [10, 25], True, 2, 3, "Verbose", "thr4"),
        str(p.__dict__)[:300]))
    checks.append(("the changes are reported", len(changed) == 12, "\n".join(changed)))

    p = Params()
    cli.apply_overrides(p, _args("--steps", "1-4", "--set", "stop_analysis_step=2",
                                 "--debug", "--verbose"))
    checks.append(("--set has the last word", p.stop_analysis_step == 2, str(p.stop_analysis_step)))
    checks.append(("--debug wins over --verbose", p.verbose_level == "Debug", p.verbose_level))

    p = Params()
    changed = cli.apply_overrides(p, _args("--set", f"channel_layout={p.channel_layout}"))
    checks.append(("setting a field to its current value isn't reported as a change",
                   changed == [], str(changed)))

    missing = cli.missing_inputs(Params())
    checks.append(("an empty run is missing raw data, output and spreadsheet",
                   len(missing) == 3 and "--raw-data" in missing[0], str(missing)))
    p = Params(output_data_folder="/o", spreadsheet_file_name="s.csv", start_analysis_step=3)
    missing = cli.missing_inputs(p)
    checks.append(("starting at step 3 needs no raw data, but earlier output",
                   len(missing) == 1 and "step 3" in missing[0], str(missing)))
    p.output_data_folder_name = "Existing"
    checks.append(("…which naming an existing run provides", cli.missing_inputs(p) == [],
                   str(cli.missing_inputs(p))))
    return checks


# ── Parameter files ───────────────────────────────────────────────────────────

def _params_file_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "p.json"
        rc = cli.main(["params", "new", "-o", str(out), "--mode", "catnap",
                       "--set", "spikes_method=thr5"])
        params, unknown = load_params(out)
        checks.append(("params new writes a loadable file", rc == 0 and unknown == [], str(unknown)))
        checks.append(("…with the mode's flags and lags",
                       params.suite2p_mode and params.func_con_lag_val == [1000, 2500, 5000],
                       str(params.func_con_lag_val)))
        checks.append(("…and --set applied", params.spikes_method == "thr5", params.spikes_method))
        checks.append(("params new won't replace a file without --force",
                       cli.main(["params", "new", "-o", str(out)]) == cli.EXIT_USAGE, ""))

        from meanap.params_summary import summarise_params
        fresh = tmp / "fresh.json"
        cli.main(["params", "new", "-o", str(fresh)])
        checks.append(("a file of defaults shows no changes (tuple defaults included)",
                       summarise_params(load_params(fresh)[0]).changed == 0,
                       str([e.name for g in summarise_params(load_params(fresh)[0]).groups
                            for e in g.entries if e.changed])))

        run_dir = tmp / "OutputData01Jan2026"
        run_dir.mkdir()
        (run_dir / "params.json").write_text(out.read_text())
        checks.append(("a run folder resolves to its params.json",
                       cli.resolve_params_path(str(run_dir)) == run_dir / "params.json", ""))
        ok, msg = _raises(lambda: cli.resolve_params_path(str(tmp)))
        checks.append(("a folder without one is refused", ok, msg))
        ok, msg = _raises(lambda: cli.resolve_params_path(str(tmp / "nope.json")))
        checks.append(("a missing file is refused", ok, msg))
    return checks


# ── Ctrl-C ────────────────────────────────────────────────────────────────────

def _ctrl_c_checks() -> list[Check]:
    checks: list[Check] = []
    before = signal.getsignal(signal.SIGINT)
    second = False
    with cli.CtrlC() as stop:
        checks.append(("not requested to begin with", stop() is False, ""))
        os.kill(os.getpid(), signal.SIGINT)
        checks.append(("the first Ctrl-C asks the run to stop", stop() is True, ""))
        try:
            os.kill(os.getpid(), signal.SIGINT)
        except KeyboardInterrupt:
            second = True
    checks.append(("the second one stops now", second, ""))
    checks.append(("the previous handler is put back", signal.getsignal(signal.SIGINT) is before, ""))
    return checks


# ── End to end ────────────────────────────────────────────────────────────────

def _end_to_end_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        spikes = tmp / "spikes"
        _seed_spikes(spikes)
        sheet = _write_sheet(tmp / "recs.csv")

        ref = run_pipeline(_params(tmp, sheet, spikes, "Ref"), log=lambda m: None)

        # The file as the GUI saves it, with one thing the command line changes.
        path = _save(_params(tmp, sheet, spikes, "FromFile"), tmp / "run.json")
        proc = _meanap("run", str(path), "--name", "FromCLI")
        root = _output_of(proc.stdout)
        checks.append(("meanap run exits 0", proc.returncode == 0,
                       (proc.stdout + proc.stderr)[-1500:]))
        checks.append(("…into the folder --name gave",
                       root is not None and root.name.startswith("FromCLI"), str(root)))
        if root is not None and proc.returncode == 0:
            a, b = _table(ref), _table(root)
            same = a.shape == b.shape and np.allclose(
                a.select_dtypes("number").to_numpy(), b.select_dtypes("number").to_numpy(),
                equal_nan=True)
            checks.append(("…with run_pipeline's numbers, recording for recording", same,
                           f"{a.shape} vs {b.shape}"))
        checks.append(("progress is printed",
                       any(l.startswith("[") and "%" in l for l in proc.stdout.splitlines()),
                       proc.stdout[-500:]))

        # Rerunning a finished run from what it left: express gives a bundle.
        if root is not None:
            proc = _meanap("run", str(root), "--name", "Again", "-n")
            checks.append(("a finished run's bundle can be rerun (dry run)",
                           proc.returncode == 0 and "Dry run" in proc.stdout
                           and "steps 3–4" in proc.stdout,
                           (proc.stdout + proc.stderr)[-800:]))
            proc = _meanap("params", "show", str(root))
            checks.append(("…and its settings shown", proc.returncode == 0
                           and "spike_detected_data" in proc.stdout, proc.stdout[-500:]))

        proc = _meanap("run", str(path), "--set", "spreadsheet_file_name=")
        checks.append(("missing inputs exit 2 before anything runs",
                       proc.returncode == cli.EXIT_USAGE and "spreadsheet" in proc.stdout,
                       proc.stdout[-500:]))

        # A queue of two, the first broken: the second still runs.
        broken = _save(_params(tmp, sheet, tmp / "no_spikes_here", "Broken"), tmp / "broken.json")
        good = _save(_params(tmp, sheet, spikes, "Queued"), tmp / "good.json")
        proc = _meanap("run", str(broken), str(good))
        checks.append(("a queue with a failed run exits 1", proc.returncode == cli.EXIT_FAILED,
                       (proc.stdout + proc.stderr)[-1500:]))
        checks.append(("…after running the rest",
                       any((tmp / "out").glob("Queued*")) and "Queue summary" in proc.stdout,
                       str(sorted(p.name for p in (tmp / "out").iterdir()))))
        proc = _meanap("run", str(broken), str(good), "--name", "X")
        checks.append(("--name with several files is refused",
                       proc.returncode == cli.EXIT_USAGE, proc.stdout[-300:]))

        proc = _meanap("stats", "--help")
        checks.append(("forwarded tools get their own arguments",
                       proc.returncode == 0 and "--decode" in proc.stdout, proc.stdout[-300:]))
        proc = _meanap("--version")
        checks.append(("--version names MEA-NAP", proc.returncode == 0 and "MEA-NAP" in proc.stdout,
                       proc.stdout))
    return checks


def main() -> int:
    passed = total = 0
    sections = [
        ("Typed --set", _coerce_checks),
        ("Overrides and checks", _override_checks),
        ("Parameter files", _params_file_checks),
        ("Ctrl-C", _ctrl_c_checks),
        ("End to end: meanap run in its own process", _end_to_end_checks),
    ]
    for title, fn in sections:
        p, t = _report(title, fn())
        passed += p
        total += t
    print(f"\n{'ALL PASSED' if passed == total else 'FAILURES'}: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
