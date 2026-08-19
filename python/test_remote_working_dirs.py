"""Test what a remote run leaves behind, and that it says so.

Run from the repo root::

    uv run python python/test_remote_working_dirs.py

Express mode's claim is that the ``.meanap`` bundle is the whole run. That is
true of the *output folder*, which is removed once the bundle reads back — but
it was never true of the two directories a **remote** run needs:

  * the streamed-file cache, which evicts each recording's files as it goes but
    leaves the directories that held them, so a fully-drained cache still looks
    like megabytes of structure — and accumulates a fresh subtree per share
    link;
  * the derived denoising outputs, kept on purpose (they are what lets a re-run
    skip denoising) and routinely far larger than the bundle itself — 5.7 GB
    against 182 MB on a 378-recording batch.

Neither was disclosed and neither was configurable, so ticking "Express mode"
to avoid a large output produced a small file beside gigabytes of ``.npy``.

Checked here:
  A. the end-of-run report: what it says, and that a local run stays silent;
  B. the sweep: empty cache skeletons go, anything holding a file stays;
  C. the GUI: both paths and the cache ceiling round-trip through Params.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.params import Params  # noqa: E402
from meanap.pipeline.runner import (  # noqa: E402
    _human_bytes, _report_working_dirs, _sweep_empty_dirs,
)

Check = tuple[str, bool, str]
REMOTE = "https://www.dropbox.com/scl/fo/KEY/HASH?rlkey=RL"


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


def _layout(out: Path, *, cache_files: bool = False, derived: int = 3) -> None:
    """A finished remote run's working directories."""
    for link in ("linkA", "linkB"):
        for rec in ("rec1", "rec2"):
            d = out / "MEANAP-cache" / link / rec / "suite2p" / "plane0"
            d.mkdir(parents=True, exist_ok=True)
            if cache_files:
                (d / "F.npy").write_bytes(b"x" * 2_000_000)
    for i in range(derived):
        d = out / "MEANAP-derived" / f"rec{i}" / "plane0"
        d.mkdir(parents=True, exist_ok=True)
        (d / "Fdenoised.npy").write_bytes(b"x" * 3_000_000)


def _report_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _layout(out)
        logs: list[str] = []
        _report_working_dirs(
            Params(raw_data=REMOTE, output_data_folder=str(out)), logs.append)
        text = "\n".join(logs)

        checks.append(("a remote run reports the derived data",
                       "Derived data:" in text, text))
        checks.append(("…with its size and recording count",
                       "8.6 MB" in text and "3 recording(s)" in text, text))
        checks.append(("…and why it was kept, not just that it exists",
                       "re-run skips denoising" in text, text))
        checks.append(("…and the path, so it can be found",
                       str(out / "MEANAP-derived") in text, text))
        checks.append(("a drained cache is reported as emptied",
                       "Cache: emptied" in text, text))

        # A cache that still holds data must say so, and must not claim to have
        # been emptied.
        out2 = Path(tempfile.mkdtemp())
        _layout(out2, cache_files=True)
        logs2: list[str] = []
        _report_working_dirs(
            Params(raw_data=REMOTE, output_data_folder=str(out2)), logs2.append)
        t2 = "\n".join(logs2)
        checks.append(("a cache holding data reports its size",
                       "Cache: 7.6 MB" in t2, t2))
        checks.append(("…and says it is safe to delete",
                       "safe to delete" in t2, t2))
        checks.append(("…without claiming it was emptied",
                       "emptied" not in t2, t2))

        # A local run has neither directory and must not invent them.
        logs3: list[str] = []
        _report_working_dirs(
            Params(raw_data=str(out), output_data_folder=str(out)), logs3.append)
        checks.append(("a local run says nothing at all", logs3 == [], f"{logs3}"))

        checks.append(("sizes are human-readable",
                       (_human_bytes(999), _human_bytes(5_368_709_120))
                       == ("999 B", "5.0 GB"),
                       f"{_human_bytes(999)}, {_human_bytes(5_368_709_120)}"))
    return checks


def _sweep_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _layout(out)
        cache = out / "MEANAP-cache"
        before = sum(1 for p in cache.rglob("*") if p.is_dir())
        removed = _sweep_empty_dirs(cache)
        after = [p for p in cache.rglob("*") if p.is_dir()]
        checks.append(("every empty directory under the cache is removed",
                       after == [], f"{[str(p) for p in after]}"))
        checks.append(("…and counted", removed == before, f"{removed} of {before}"))
        checks.append(("the cache root itself survives", cache.is_dir(), ""))

        # Anything still holding a file must be left alone — this runs after a
        # run, and a partially-drained cache is a resumable one.
        _layout(out, cache_files=True)
        kept = out / "MEANAP-cache" / "linkA" / "rec1" / "suite2p" / "plane0"
        _sweep_empty_dirs(cache)
        checks.append(("a directory holding a file is kept",
                       (kept / "F.npy").is_file(), ""))
        checks.append(("…and so are its parents", kept.is_dir(), ""))
    return checks


def _gui_checks() -> list[Check]:
    from PyQt6.QtWidgets import QApplication

    # Must exist before any QWidget is constructed, hence inside this function
    # and before the panel import chain pulls widgets in.
    app = QApplication.instance() or QApplication([])
    assert app is not None
    from meanap.gui.panels.data import DataPanel

    checks: list[Check] = []
    panel = DataPanel()

    panel.load(Params())
    checks.append(("defaults show as unset, not as a guessed path",
                   panel.cache_dir.value == ""
                   and panel.derived_data_folder.value == "", ""))
    checks.append(("…and the budget reads Automatic, not 0",
                   panel.cache_budget_gb.text() == "Automatic",
                   panel.cache_budget_gb.text()))

    panel.cache_dir.set_value("/scratch/cache")
    panel.derived_data_folder.set_value("/scratch/derived")
    panel.cache_budget_gb.setValue(25.0)
    out = Params()
    panel.save(out)
    checks.append(("edits reach Params",
                   (out.cache_dir, out.derived_data_folder, out.cache_budget_gb)
                   == ("/scratch/cache", "/scratch/derived", 25.0),
                   f"{(out.cache_dir, out.derived_data_folder, out.cache_budget_gb)}"))

    # 0 and "automatic" are different: None lets resolve_budget size it from
    # free disk, 0 would be a cache that can hold nothing.
    panel.cache_budget_gb.setValue(0.0)
    zero = Params()
    panel.save(zero)
    checks.append(("Automatic saves as None, not 0.0",
                   zero.cache_budget_gb is None, f"{zero.cache_budget_gb!r}"))

    loaded = Params(cache_dir="/a", derived_data_folder="/b", cache_budget_gb=12.5)
    panel.load(loaded)
    back = Params()
    panel.save(back)
    checks.append(("load → save is the identity",
                   (back.cache_dir, back.derived_data_folder, back.cache_budget_gb)
                   == ("/a", "/b", 12.5),
                   f"{(back.cache_dir, back.derived_data_folder, back.cache_budget_gb)}"))

    # The defaults these override must still be what the runner computes.
    from meanap.params import default_cache_dir, default_derived_dir
    p = Params(output_data_folder="/out")
    checks.append(("an unset cache folder still defaults under the output folder",
                   default_cache_dir(p) == Path("/out/MEANAP-cache"),
                   str(default_cache_dir(p))))
    checks.append(("…and an unset derived folder likewise, when remote",
                   default_derived_dir(p, remote=True) == "/out/MEANAP-derived",
                   default_derived_dir(p, remote=True)))
    checks.append(("…but stays beside the inputs when local",
                   default_derived_dir(p, remote=False) == "", ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("What a remote run leaves behind")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — the end-of-run report:", _report_checks),
        ("B — sweeping the drained cache:", _sweep_checks),
        ("C — steering both paths from the GUI:", _gui_checks),
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
