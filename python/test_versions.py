"""Test per-pipeline version numbers: where they come from, and where they go.

Run from the repo root::

    uv run python python/test_versions.py

Three pipelines ship from this repository and move at different speeds, so a
single number cannot describe them — and a result is only reproducible if it
records the version of the pipeline that actually ran.

The constraint that shapes the design: **MEA-NAP's version must stay in
``version.txt`` and nowhere else.** MATLAB's ``getParamsFromApp.m`` reads that
file into ``Params.version``, and ``getVersion.m`` compares it against the copy
on GitHub to tell users they are out of date. A second copy in Python could
drift from the one users are told to check. The two newer subsystems have no
such history and live in ``versions.json`` beside it.

Checked here:
  A. the source of truth: version.txt for MEA-NAP, versions.json for the rest,
     and graceful degradation when either is missing;
  B. the stamp written into ``params.json`` and the bundle manifest, including
     that it does not masquerade as a setting;
  C. the GUI: the toolbar shows the *running* mode's version and follows a
     mode switch.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap import version as V  # noqa: E402
from meanap.params import (  # noqa: E402
    Params, load_params, params_version_stamp, save_params,
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


def _source_checks() -> list[Check]:
    checks: list[Check] = []

    txt = (REPO_ROOT / "version.txt").read_text().strip()
    checks.append(("MEA-NAP's version comes from version.txt",
                   V.meanap_version() == txt, f"{V.meanap_version()} vs {txt}"))
    checks.append(("…which is the file MATLAB reads, not a Python copy",
                   (REPO_ROOT / "version.txt").is_file()
                   and "meanap" not in json.loads(
                       (REPO_ROOT / "versions.json").read_text()),
                   "versions.json must not also carry meanap"))

    every = V.all_versions()
    checks.append(("all three pipelines have a version",
                   set(every) == {"meanap", "catnap", "meastim"}
                   and all(v != V.UNKNOWN for v in every.values()),
                   f"{every}"))
    checks.append(("labels read as a person would write them",
                   V.pipeline_label("catnap") == f"CAT-NAP {every['catnap']}",
                   V.pipeline_label("catnap")))

    # An unknown mode is stamped, not raised on: this runs while writing output.
    checks.append(("an unknown pipeline degrades to 'unknown'",
                   V.pipeline_version("nope") == V.UNKNOWN,
                   V.pipeline_version("nope")))

    # Missing files must not break a run. Exercised by pointing the resolver at
    # an empty directory, since the real files are present.
    orig = V._version_file
    try:
        with tempfile.TemporaryDirectory() as tmp:
            V._version_file = lambda name: None
            V.meanap_version.cache_clear()
            V._subsystem_versions.cache_clear()
            checks.append(("a missing version.txt yields 'unknown', not an error",
                           V.meanap_version() == V.UNKNOWN, V.meanap_version()))
            checks.append(("…and a missing versions.json likewise",
                           V.pipeline_version("catnap") == V.UNKNOWN, ""))
    finally:
        V._version_file = orig
        V.meanap_version.cache_clear()
        V._subsystem_versions.cache_clear()
    checks.append(("…and the real values come back afterwards",
                   V.meanap_version() == txt, V.meanap_version()))
    return checks


def _stamp_checks() -> list[Check]:
    from meanap.pipeline.bundle import build_manifest

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        # The stamp must follow the *mode*, not the repo.
        for flags, mode, name in ((dict(suite2p_mode=True), "catnap", "CAT-NAP"),
                                  (dict(stimulation_mode=True), "meastim", "MEA-Stim"),
                                  ({}, "meanap", "MEA-NAP")):
            d = Path(tmp) / mode
            d.mkdir()
            path = save_params(Params(**flags), d)
            stamp = params_version_stamp(path)
            checks.append((f"a {name} run stamps itself as {mode}",
                           stamp.get("pipeline") == mode
                           and stamp.get("version") == V.pipeline_version(mode),
                           f"{stamp.get('pipeline')} {stamp.get('version')}"))

        path = save_params(Params(suite2p_mode=True), Path(tmp) / "catnap")
        raw = json.loads(path.read_text())
        checks.append(("the stamp records all three versions, not just the one",
                       raw["_meanap"]["versions"] == V.all_versions(), ""))
        checks.append(("…under a reserved key, so it cannot collide with a setting",
                       "_meanap" in raw and not any(
                           k.startswith("_") and k != "_meanap" for k in raw), ""))

        back, unknown = load_params(path)
        checks.append(("loading a stamped file reports no unknown keys",
                       unknown == [], f"{unknown}"))
        checks.append(("…and still restores the settings",
                       back.suite2p_mode is True, ""))

        # A run from before stamping is not an error.
        old = Path(tmp) / "old.json"
        old.write_text('{"raw_data": "/x"}')
        checks.append(("an unstamped params.json yields {} rather than raising",
                       params_version_stamp(old) == {}, ""))
        checks.append(("a missing file likewise",
                       params_version_stamp(Path(tmp) / "nope.json") == {}, ""))

    man = build_manifest(Params(suite2p_mode=True), [], mode="catnap")
    checks.append(("the bundle manifest carries the stamp",
                   man.get("version") == V.pipeline_version("catnap")
                   and man.get("pipeline_name") == "CAT-NAP",
                   f"{man.get('pipeline_name')} {man.get('version')}"))
    checks.append(("…without disturbing the bundle format number",
                   isinstance(man.get("format"), int)
                   and man["format"] != man["version"],
                   f"format={man.get('format')} version={man.get('version')}"))
    return checks


def _gui_checks() -> list[Check]:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert app is not None
    from meanap.gui.main_window import MainWindow

    checks: list[Check] = []
    w = MainWindow()
    checks.append(("the toolbar shows a version",
                   w._version_label.text() == f"v{V.pipeline_version(w._mode)}",
                   w._version_label.text()))

    # The number must follow the mode, or it says the wrong thing about the
    # pipeline that would actually run.
    seen = {}
    for mode in ("catnap", "meastim", "meanap"):
        w._apply_mode(mode)
        seen[mode] = w._version_label.text()
    checks.append(("…which changes with the mode",
                   seen == {m: f"v{V.pipeline_version(m)}" for m in seen},
                   f"{seen}"))
    checks.append(("…and differs between modes, so it is not a constant",
                   len(set(seen.values())) == 3, f"{seen}"))

    tip = w._version_label.toolTip()
    checks.append(("the tooltip lists every pipeline",
                   all(n in tip for n in V.PIPELINE_NAMES.values()), tip))
    checks.append(("…and says where the version is recorded",
                   "params.json" in tip and "manifest" in tip, tip))
    return checks


def main() -> int:
    print("=" * 70)
    print("Pipeline version numbers")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — where the numbers come from:", _source_checks),
        ("B — stamped into output and bundles:", _stamp_checks),
        ("C — shown in the GUI:", _gui_checks),
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
