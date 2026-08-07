"""Test the pre-flight check.

Run from the repo root::

    uv run python python/test_remote_preflight.py

Pre-flight exists to stop one specific failure: a batch that runs, finishes, and
reports results computed from a fraction of the recordings you asked for.
Because the node-cartography boundaries and every group comparison are derived
from whichever recordings actually ran, a silently-shortened batch produces
numbers that look complete and aren't.

So the checks here are mostly about *refusing*: an empty match set is a problem
rather than a warning, and a folder that exists under a slightly different name
is called out by name rather than counted as absent.

Runs against a synthetic tree through :class:`LocalStore`; no network.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.remote.local import LocalStore  # noqa: E402
from meanap.remote.preflight import (  # noqa: E402
    CATNAP_REQUIRED, MAX_LISTED, find_spreadsheet, run_preflight,
)

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


def _plane0(root: Path, name: str, *, files=CATNAP_REQUIRED,
            denoised=False, junk=True) -> None:
    d = root / name / "suite2p" / "plane0"
    d.mkdir(parents=True)
    for f in files:
        (d / f).write_bytes(b"x" * 1_000_000)
    if denoised:
        (d / "Fdenoised.npy").write_bytes(b"x" * 500_000)
    if junk:
        # The files the pipeline never opens — must be counted as skipped, not
        # fetched, since not fetching them is a fifth of the transfer.
        (d / "F.csv").write_bytes(b"x" * 2_000_000)
        (d / "Fneu.npy").write_bytes(b"x" * 1_000_000)


def _catnap_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plane0(root, "recA", denoised=True)
        _plane0(root, "recB")                                  # needs denoising
        _plane0(root, "recC", files=("stat.npy", "F.npy"))     # incomplete
        (root / "recD").mkdir()                                # no suite2p
        (root / "extra").mkdir()                               # unreferenced
        (root / "batch.csv").write_bytes(b"x" * 100)

        store = LocalStore(root)
        rep = run_preflight(store, ["recA", "recB", "recC", "recD", "recE"],
                            mode="catnap")

        by = {r.name: r for r in rep.recordings}
        checks.append(("a complete recording is ready", by["recA"].ok, ""))
        checks.append(("a recording without denoising is still ready",
                       by["recB"].ok and by["recB"].needs_denoising, ""))
        checks.append(("an incomplete plane0 names the missing files",
                       not by["recC"].ok
                       and set(by["recC"].missing) == {"iscell.npy", "ops.npy"},
                       f"{by['recC'].missing}"))
        checks.append(("a folder without suite2p/plane0 is not found",
                       not by["recD"].found and by["recD"].missing == ["suite2p/plane0"],
                       f"{by['recD'].missing}"))
        checks.append(("a recording absent entirely is not found",
                       not by["recE"].found, ""))
        checks.append(("folders not in the spreadsheet are reported",
                       "extra" in rep.unreferenced, f"{rep.unreferenced}"))

        checks.append(("only files the pipeline opens are counted for download",
                       by["recA"].fetch_bytes == 4_500_000,
                       f"{by['recA'].fetch_bytes}"))
        checks.append(("the rest is counted as skipped",
                       by["recA"].skipped_bytes == 3_000_000,
                       f"{by['recA'].skipped_bytes}"))

        checks.append(("usable counts only fully-ready recordings",
                       {r.name for r in rep.usable} == {"recA", "recB"},
                       f"{[r.name for r in rep.usable]}"))
        checks.append(("a partial batch warns about batch-wide statistics",
                       any("node-cartography" in w for w in rep.warnings), ""))
    return checks


def _ephys_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "recA.mat").write_bytes(b"x" * 3_000_000)
        (root / "recB.h5").write_bytes(b"x" * 2_000_000)
        (root / "recC.txt").write_bytes(b"x" * 10)

        rep = run_preflight(LocalStore(root), ["recA", "recB", "recC"],
                            mode="ephys")
        by = {r.name: r for r in rep.recordings}
        checks.append((".mat is found", by["recA"].ok
                       and by["recA"].fetch_bytes == 3_000_000, ""))
        checks.append((".h5 is found", by["recB"].ok, ""))
        checks.append(("an unsupported extension is not a recording",
                       not by["recC"].found, ""))
        checks.append(("the expected extensions are named in the failure",
                       ".mat" in by["recC"].missing[0], f"{by['recC'].missing}"))
    return checks


def _rename_checks() -> list[Check]:
    """The failure that motivated this: folders renamed away from the spreadsheet."""
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plane0(root, "rec_DIV21 Some Person", denoised=True)
        _plane0(root, "rec_DIV28 Some Person", denoised=True)
        _plane0(root, "rec_DIV35", denoised=True)

        rep = run_preflight(LocalStore(root),
                            ["rec_DIV21", "rec_DIV28", "rec_DIV35"],
                            mode="catnap")
        by = {r.name: r for r in rep.recordings}
        checks.append(("an exactly-named folder is ready", by["rec_DIV35"].ok, ""))
        checks.append(("a renamed folder is matched to its spreadsheet row",
                       by["rec_DIV21"].suggestion == "rec_DIV21 Some Person",
                       f"{by['rec_DIV21'].suggestion}"))
        checks.append(("each rename is matched once, not shared",
                       by["rec_DIV28"].suggestion == "rec_DIV28 Some Person",
                       f"{by['rec_DIV28'].suggestion}"))
        checks.append(("renames are a problem, not a warning",
                       any("different folder name" in p for p in rep.problems), ""))
        checks.append(("…so the run is refused", not rep.ok, ""))
        checks.append(("the message shows both names",
                       "rec_DIV21" in rep.problems[0]
                       and "Some Person" in rep.problems[0], rep.problems[0][:60]))

        rendered = rep.render()
        checks.append(("the report points at the renamed folder",
                       "under a different name" in rendered, ""))
        # It may appear in the hint and in the problem text; what must not
        # happen is it *also* being listed as an unrelated stray folder, which
        # would read as two separate issues instead of one.
        stray = [ln for ln in rendered.splitlines()
                 if ln.startswith("  ! ") and "Some Person" in ln]
        checks.append(("a matched rename is not also listed as unreferenced",
                       not stray, f"{stray}"))
    return checks


def _report_shape_checks() -> list[Check]:
    """A 381-row spreadsheet must not produce a 381-line report."""
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plane0(root, "good", denoised=True)
        names = ["good"] + [f"missing{i}" for i in range(50)]
        rep = run_preflight(LocalStore(root), names, mode="catnap")
        text = rep.render()

        checks.append(("the summary line counts the whole batch",
                       "1 of 51 recordings ready" in text, text.splitlines()[4]))
        listed = sum(1 for line in text.splitlines() if line.startswith("  ✗ missing"))
        checks.append((f"at most {MAX_LISTED} failures are spelled out",
                       listed <= MAX_LISTED, f"{listed}"))
        checks.append(("the rest are summarised",
                       "and 42 more not found" in text, ""))
        checks.append(("the report stays short",
                       len(text.splitlines()) < 30, f"{len(text.splitlines())} lines"))
    return checks


def _budget_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plane0(root, "recA", denoised=True)
        store = LocalStore(root)

        # A local store copies nothing, so budgeting doesn't apply to it.
        rep = run_preflight(store, ["recA"], mode="catnap",
                            cache_dir=root / "cache")
        checks.append(("a local source needs no cache budget",
                       rep.budget_bytes == 0 and rep.ok, ""))

        # A copying store does. Fake one by flipping the flag.
        class Copying(LocalStore):
            copies = True

        store2 = Copying(root)
        rep2 = run_preflight(store2, ["recA"], mode="catnap",
                             cache_dir=root / "cache", prefetch_depth=1)
        checks.append(("peak storage is the largest recording times depth+1",
                       rep2.peak_bytes == 4_500_000 * 2, f"{rep2.peak_bytes}"))
        checks.append(("a budget is resolved", rep2.budget_bytes > 0, ""))
        checks.append(("free disk is reported", rep2.free_bytes > 0, ""))

        rep3 = run_preflight(store2, ["recA"], mode="catnap",
                             cache_dir=root / "cache", cache_budget_gb=0.000001)
        checks.append(("a budget too small for one recording is a problem",
                       any("resident at once" in p for p in rep3.problems),
                       f"{rep3.problems[:1]}"))
        checks.append(("…so the run is refused", not rep3.ok, ""))
    return checks


def _spreadsheet_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "only.csv").write_bytes(b"x")
        store = LocalStore(root)
        checks.append(("a lone csv at the top level is found",
                       find_spreadsheet(store) == "only.csv",
                       f"{find_spreadsheet(store)}"))
        checks.append(("a configured name is preferred",
                       find_spreadsheet(store, "only.csv") == "only.csv", ""))
        checks.append(("a configured name that isn't there returns None",
                       find_spreadsheet(store, "nope.csv") is None, ""))

        (root / "second.csv").write_bytes(b"x")
        checks.append(("two candidates is ambiguous, not a guess",
                       find_spreadsheet(store) is None, ""))
    return checks


def _empty_source_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        rep = run_preflight(LocalStore(Path(tmp)), ["recA", "recB"], mode="catnap")
        checks.append(("nothing usable is a problem, not a warning",
                       rep.problems and not rep.ok, ""))
        checks.append(("the message suggests the likely cause",
                       "same dataset" in rep.problems[0], rep.problems[0][:60]))
    return checks


def main() -> int:
    print("=" * 70)
    print("Pre-flight: can this dataset actually be analysed?")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — CAT-NAP requirements and byte accounting:", _catnap_checks),
        ("B — electrophysiology recordings:", _ephys_checks),
        ("C — folders renamed away from the spreadsheet:", _rename_checks),
        ("D — report stays readable at batch scale:", _report_shape_checks),
        ("E — storage budget:", _budget_checks),
        ("F — locating the spreadsheet:", _spreadsheet_checks),
        ("G — an empty or mismatched source:", _empty_source_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
