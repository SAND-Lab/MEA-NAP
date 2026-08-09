"""Test the run-parameter summary shown in the report and the viewer.

Run from the repo root::

    uv run python python/test_params_summary.py

``params.json`` is the authoritative record of how a result was produced, and is
unreadable as a flat object of ~140 keys in declaration order. The summary
groups it and marks what differs from the defaults, which is the question a
reader actually has.

Two things here are load-bearing beyond "it renders". The grouping is read off
the ``Params`` source rather than kept in a list, so a field added later lands
in its section with nothing to update — asserted by checking every field is
covered. And a report is a file people attach to papers, so a share link in one
is a credential: the summary redacts the same fields the bundle does.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.params import Params, SECRET_URL_FIELDS, save_params  # noqa: E402
from meanap.params_summary import (  # noqa: E402
    REDACTED, field_sections, summarise_params, summary_from_file,
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


def _grouping_checks() -> list[Check]:
    checks: list[Check] = []
    sections = field_sections()
    fields = {f.name for f in dataclasses.fields(Params)}

    checks.append(("every Params field is assigned a section",
                   set(sections) == fields,
                   f"unmapped: {sorted(fields - set(sections))[:5]}"))
    checks.append(("the sections come from the dataclass, not a list here",
                   "Spike detection" in sections.values()
                   and "Two-photon / CAT-NAP" in sections.values(), ""))
    checks.append(("fields land in the section they are declared under",
                   sections.get("fs") == "Recording"
                   and sections.get("suite2p_mode") == "Two-photon / CAT-NAP"
                   and sections.get("express_mode") == "Pipeline control",
                   f"{sections.get('fs')}, {sections.get('suite2p_mode')}"))

    summary = summarise_params(Params())
    checks.append(("a default run covers every field and changes none",
                   summary.total == len(fields) and summary.changed == 0,
                   f"{summary.changed}/{summary.total} of {len(fields)}"))
    checks.append(("groups keep declaration order",
                   [g.name for g in summary.groups][:3]
                   == ["Paths", "Recording", "Spike detection"],
                   str([g.name for g in summary.groups][:3])))
    return checks


def _change_checks() -> list[Check]:
    checks: list[Check] = []
    p = Params(fs=12500.0, express_mode=True, random_seed=7,
               func_con_lag_val=[25])
    summary = summarise_params(p)

    changed = {e.name: e for g in summary.groups for e in g.entries if e.changed}
    checks.append(("exactly the changed fields are marked",
                   set(changed) == {"fs", "express_mode", "random_seed",
                                    "func_con_lag_val"},
                   str(sorted(changed))))
    checks.append(("each carries the default it departed from",
                   changed["fs"].default == 25000.0
                   and changed["random_seed"].default is None,
                   f"{changed['fs'].default}"))
    checks.append(("a list field compares by value, not identity",
                   # func_con_lag_val's default comes from a factory; comparing
                   # objects rather than values would mark it changed always.
                   changed["func_con_lag_val"].value == [25]
                   and changed["func_con_lag_val"].default == [10, 15, 25], ""))
    checks.append(("a field left alone is not marked",
                   not any(e.changed for g in summary.groups
                           for e in g.entries if e.name == "ref_period"), ""))
    checks.append(("the counts add up",
                   summary.changed == 4
                   and sum(g.changed for g in summary.groups) == 4,
                   str(summary.changed)))
    return checks


def _redaction_checks() -> list[Check]:
    checks: list[Check] = []
    link = "https://www.dropbox.com/scl/fo/abc/def?rlkey=SUPERSECRET"
    summary = summarise_params(Params(raw_data=link))
    entry = next(e for g in summary.groups for e in g.entries
                 if e.name == "raw_data")

    checks.append(("a share link is replaced, not shown",
                   entry.value == REDACTED and entry.redacted,
                   str(entry.value)))
    checks.append(("and the secret appears nowhere in the summary",
                   "SUPERSECRET" not in json.dumps(summary.as_dict()), ""))
    checks.append(("but it still reads as changed",
                   entry.changed, ""))
    checks.append(("a local path in the same field is left alone",
                   next(e for g in summarise_params(Params(raw_data="/data/x")).groups
                        for e in g.entries if e.name == "raw_data").value == "/data/x",
                   ""))
    checks.append(("every secret field is present to be redacted",
                   all(any(e.name == f for g in summary.groups for e in g.entries)
                       for f in SECRET_URL_FIELDS), str(SECRET_URL_FIELDS)))
    return checks


def _file_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        save_params(Params(fs=9000.0), tmp)
        summary = summary_from_file(tmp / "params.json")
        checks.append(("a written params.json round-trips",
                       summary is not None and summary.changed == 1,
                       str(summary.changed if summary else None)))

        checks.append(("a missing file is None, not an exception",
                       summary_from_file(tmp / "nope.json") is None, ""))
        (tmp / "broken.json").write_text("{not json")
        checks.append(("an unparseable file is None too",
                       summary_from_file(tmp / "broken.json") is None, ""))
        (tmp / "list.json").write_text("[1,2,3]")
        checks.append(("so is one that isn't an object",
                       summary_from_file(tmp / "list.json") is None, ""))

        # A file from a newer version carries fields this build has no slot for.
        raw = json.loads((tmp / "params.json").read_text())
        raw["some_future_setting"] = 42
        (tmp / "future.json").write_text(json.dumps(raw))
        s = summary_from_file(tmp / "future.json")
        checks.append(("unknown keys are surfaced, not dropped",
                       s is not None and "some_future_setting" in s.unknown,
                       str(s.unknown if s else None)))
    return checks


def _report_checks() -> list[Check]:
    from meanap.pipeline.output_folders import create_output_folders
    from meanap.pipeline.report import generate_report

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = create_output_folders(Path(tmp), "Run", ["WT"])
        link = "https://www.dropbox.com/scl/fo/a/b?rlkey=LEAKME"
        save_params(Params(fs=12500.0, express_mode=True, raw_data=link), root)
        html = generate_report(root).read_text()

        checks.append(("the report offers a parameters view",
                       'id="params-link"' in html and "function renderParams" in html,
                       ""))
        checks.append(("with the summary embedded, not fetched",
                       '"groups":' in html and '"changed":' in html, ""))
        checks.append(("a changed value is in there",
                       "12500" in html, ""))
        checks.append(("the share link is not",
                       "LEAKME" not in html, ""))

        # An output folder with no params.json must still produce a report.
        bare = create_output_folders(Path(tmp), "Bare", ["WT"])
        bare_html = generate_report(bare).read_text()
        checks.append(("a run without params.json still builds a report",
                       "const PARAMS = null" in bare_html, ""))
    return checks


def _viewer_checks() -> list[Check]:
    from meanap.viewer import page, server

    checks: list[Check] = []
    html = page.PAGE_HTML
    for label, needle in [
        ("a Parameters tab", 'data-tab="params"'),
        ("its own side panel", 'id="side-params"'),
        ("a pane to render into", 'id="params"'),
        ("a renderer", "function showParams"),
        ("section filtering", "PARAM_SECTION"),
        ("a show-all toggle", "PARAM_ALL"),
        ("the tab hidden when the run recorded nothing",
         "if (!MANIFEST.params)"),
        ("the pane put away when a figure is shown",
         '$("params").classList.add("hidden")'),
    ]:
        checks.append((label, needle in html, needle))

    src = Path(server.__file__).read_text()
    checks.append(("the server puts the summary in its manifest",
                   '"params": self._params_summary()' in src, ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("Run parameter summary")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [("Grouping:", _grouping_checks),
                         ("Changes:", _change_checks),
                         ("Redaction:", _redaction_checks),
                         ("Reading params.json:", _file_checks),
                         ("In report.html:", _report_checks),
                         ("In the viewer:", _viewer_checks)]:
        p, n = _report(title, build())
        total_pass += p
        total += n
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
