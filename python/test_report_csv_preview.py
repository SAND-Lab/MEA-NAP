"""Test the HTML report's embedded CSV previews.

Run from the repo root::

    uv run python python/test_report_csv_preview.py

The report is meant to be opened straight off disk. A page on a ``file://``
origin cannot fetch its sibling files — browsers give each one an opaque origin
— so the preview rows cannot be loaded lazily in the viewer and are instead
embedded by ``generate_report``. These checks cover that embedding: the right
rows and counts get captured, wide/long/awkward files are truncated rather than
dropped, and nothing in a CSV can break out of the ``<script>`` block it ends up
inside.

All synthetic; no dataset needed, so this always runs.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline import report as rp  # noqa: E402

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _tree_json(html: str) -> dict:
    """Pull the embedded tree back out of the generated page."""
    m = re.search(r"const TREE = (\{.*?\});\n", html, re.S)
    assert m, "tree not found in report HTML"
    return json.loads(m.group(1))


def _find(node: dict, name: str) -> dict | None:
    if node.get("name") == name and node.get("type") != "folder":
        return node
    for child in node.get("children", []):
        hit = _find(child, name)
        if hit:
            return hit
    return None


# ── Section A — the preview extractor ─────────────────────────────────────────

def _preview_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        n_rows = rp.CSV_PREVIEW_ROWS * 3
        _write_csv(root / "long.csv", ["FileName", "Grp", "Dens"],
                   [[f"rec{i}", "WT", round(i / 100, 3)] for i in range(n_rows)])
        pv = rp.csv_preview(root / "long.csv")
        checks.append(("row count is the whole file, not the preview",
                       pv["totalRows"] == n_rows, f"{pv['totalRows']}"))
        checks.append(("only the capped number of rows is embedded",
                       len(pv["rows"]) == rp.CSV_PREVIEW_ROWS, f"{len(pv['rows'])}"))
        checks.append(("header is captured separately from the rows",
                       pv["columns"] == ["FileName", "Grp", "Dens"], f"{pv['columns']}"))
        checks.append(("values are the literal text in the file",
                       pv["rows"][0] == ["rec0", "WT", "0.0"], f"{pv['rows'][0]}"))
        checks.append(("size is reported",
                       pv["sizeBytes"] == (root / "long.csv").stat().st_size, ""))

        wide_cols = [f"m{i}" for i in range(rp.CSV_PREVIEW_MAX_COLS + 15)]
        _write_csv(root / "wide.csv", wide_cols, [list(range(len(wide_cols)))])
        pv = rp.csv_preview(root / "wide.csv")
        checks.append(("wide files are cut to the column cap",
                       len(pv["columns"]) == rp.CSV_PREVIEW_MAX_COLS, f"{len(pv['columns'])}"))
        checks.append(("the full column count is still reported",
                       pv["totalCols"] == len(wide_cols) and pv["truncatedCols"], f"{pv}"))
        checks.append(("data rows are cut to the same width",
                       all(len(r) <= rp.CSV_PREVIEW_MAX_COLS for r in pv["rows"]), ""))

        long_cell = "x" * (rp.CSV_PREVIEW_CELL_CHARS * 3)
        _write_csv(root / "longcell.csv", ["a"], [[long_cell]])
        pv = rp.csv_preview(root / "longcell.csv")
        checks.append(("over-long cells are clipped with an ellipsis",
                       len(pv["rows"][0][0]) == rp.CSV_PREVIEW_CELL_CHARS
                       and pv["rows"][0][0].endswith("…"), f"{len(pv['rows'][0][0])}"))

        _write_csv(root / "headeronly.csv", ["a", "b"], [])
        pv = rp.csv_preview(root / "headeronly.csv")
        checks.append(("a header-only file previews as zero rows",
                       pv["totalRows"] == 0 and pv["columns"] == ["a", "b"], f"{pv}"))

        (root / "empty.csv").write_text("")
        pv = rp.csv_preview(root / "empty.csv")
        checks.append(("a completely empty file is handled",
                       pv is not None and pv["columns"] == [], f"{pv}"))

        # Quoted fields containing commas and newlines must not be miscounted —
        # this is why the row count comes from a CSV parser, not line counting.
        (root / "quoted.csv").write_text('a,b\n"x,1","line1\nline2"\n"y,2","z"\n')
        pv = rp.csv_preview(root / "quoted.csv")
        checks.append(("embedded newlines don't inflate the row count",
                       pv["totalRows"] == 2, f"{pv['totalRows']}"))
        checks.append(("quoted commas stay in one cell",
                       pv["rows"][0][0] == "x,1", f"{pv['rows'][0]}"))

        checks.append(("a missing file returns None, not an error",
                       rp.csv_preview(root / "nope.csv") is None, ""))
    return checks


# ── Section B — the generated page ────────────────────────────────────────────

def _report_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "OutputTest"
        net = root / "4_NetworkActivity"
        _write_csv(net / "NetworkActivity_RecordingLevel.csv",
                   ["FileName", "Grp", "DIV", "Dens"],
                   [["rec0", "WT", "14", "0.42"], ["rec1", "KO", "21", "0.51"]])
        # A non-CSV data file, which must not gain a preview.
        (net / "netmet_results.json").write_text("{}")

        html_path = rp.generate_report(root)
        html = html_path.read_text()
        tree = _tree_json(html)

        csv_node = _find(tree, "NetworkActivity_RecordingLevel.csv")
        json_node = _find(tree, "netmet_results.json")
        checks.append(("the CSV node carries a preview",
                       csv_node is not None and "preview" in csv_node, ""))
        checks.append(("non-CSV data files get no preview",
                       json_node is not None and "preview" not in json_node, ""))
        checks.append(("the preview holds the real rows",
                       csv_node["preview"]["rows"][1] == ["rec1", "KO", "21", "0.51"],
                       f"{csv_node['preview']['rows']}"))
        checks.append(("the caption is still attached",
                       bool(csv_node.get("caption")), ""))

        for hook in ("buildCsvPreview", "renderCsvTable", "csv-toggle", "csv-scroll"):
            checks.append((f"viewer includes {hook}", hook in html, ""))
        checks.append(("the page stays self-contained (no external requests)",
                       "http://" not in html and "https://" not in html, ""))
    return checks


# ── Section C — nothing in a CSV can break the page ───────────────────────────

def _injection_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "OutputTest"
        net = root / "4_NetworkActivity"
        nasty = "</script><script>window.__pwned=1</script>"
        _write_csv(net / "Subnetwork_NodeLevel.csv",
                   ["Group", "note"], [[nasty, "<b>bold</b>"]])

        html = rp.generate_report(root).read_text()
        checks.append(("no raw </script> ends up in the page",
                       "</script><script>" not in html, ""))
        checks.append(("the injected marker is not live script",
                       "window.__pwned" not in html or "\\u003c" in html, ""))

        tree = _tree_json(html.replace("\\u003c", "<"))
        node = _find(tree, "Subnetwork_NodeLevel.csv")
        checks.append(("the value survives intact for display",
                       node["preview"]["rows"][0][0].startswith("</script>"),
                       f"{node['preview']['rows'][0][0]!r}"))

        # The escape must not corrupt ordinary content elsewhere in the tree.
        checks.append(("the tree still parses as JSON after escaping",
                       isinstance(tree, dict) and tree.get("type") == "folder", ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("HTML report — CSV previews")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [
        ("Section A — preview extraction:", _preview_checks),
        ("Section B — generated page:", _report_checks),
        ("Section C — script-injection safety:", _injection_checks),
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
